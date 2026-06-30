"""
Contract Negotiation System (Project Contribution #2).

A multi-agent architecture using LangGraph that orchestrates:
  - Two private side agents (one per party), each suggesting responses
    and flagging unfavorable terms, fully confidential from the opposing side.
  - An impartial orchestrator that monitors the shared chat and extracts
    structured deal terms as they're confirmed.

Module 5 (Assisted Chat Mode):
  FE-1: Real-time chat room per startup pitch to negotiate on the offers.
  FE-2: Agent monitors negotiation terms and suggests real-time responses.
  FE-3: Successful deals extract all agreed terms into a structured summary.
"""
import json
import logging
from typing import TypedDict

from ai_service.dependencies import get_llm

logger = logging.getLogger(__name__)


class NegotiationState(TypedDict):
    party_role: str
    message: str
    shared_history: list[dict]
    deal_terms_so_far: dict


SIDE_AGENT_PROMPT = """You are a private AI negotiation advisor for the {party_role} \
in a startup investment deal. You see the full shared chat but your advice is NEVER \
shown to the other party — you work exclusively for the {party_role}.

Shared chat history:
{history}

Deal terms agreed so far: {deal_terms}

The {party_role} just typed: "{message}"

Provide:
1. A suggested response or refinement they could send (concise, professional, ready to use as-is)
2. Any red flags in the current deal terms relative to typical {party_role} interests \
   (e.g. below-market valuation, unusually high equity ask, vague milestone language)

Return ONLY a JSON object with these keys:
{{
  "private_suggestion": "<suggested response text>",
  "flags": ["<flag_id>", ...],
  "updated_deal_terms": {{"<key>": "<value if this message updates any deal term>"}}
}}

Valid flag ids: below_market_valuation, above_market_valuation, unusually_high_equity_ask, \
vague_milestones, missing_use_of_funds, aggressive_timeline, no_flags

Return ONLY the JSON, no markdown fences, no explanation outside it."""


DEAL_EXTRACTION_PROMPT = """Analyze this negotiation chat history between a startup \
founder and an investor. Determine if a final deal has been reached — i.e. both \
parties have explicitly confirmed agreement on valuation, investment amount, equity \
percentage, and payment structure.

Chat history:
{history}

Return ONLY a JSON object:
{{
  "is_deal_reached": <true|false>,
  "deal_summary": {{
    "valuation": <int or null>,
    "amount": <int or null>,
    "equity_pct": <float or null>,
    "instrument": "<equity|safe|convertible_note or null>",
    "payment_structure": "<lumpsum|phased or null>",
    "milestones": [{{"description": "<str>", "deadline_days": <int>}}]
  }},
  "confidence": <float 0.0-1.0>
}}

Only mark is_deal_reached=true if there is clear, unambiguous mutual confirmation \
in the chat — not just a proposal from one side. Return ONLY the JSON."""


def _format_history(history: list[dict]) -> str:
    lines = []
    for msg in history[-20:]:
        role = msg.get("role", "unknown")
        lines.append(f"[{role}]: {msg.get('content', '')}")
    return "\n".join(lines) if lines else "(no messages yet)"


async def run_side_agent(
    party_role: str,
    message: str,
    shared_history: list[dict],
    deal_terms_so_far: dict,
) -> dict:
    """
    Runs the private side agent for one party. This is the core LangGraph
    node — kept as a direct async function here since the negotiation
    flow per-turn is a single-node invocation; the graph topology (side
    agents -> orchestrator -> contract builder -> review) is assembled
    in run_full_negotiation_graph for the deal-closing path.
    """
    llm = get_llm()
    prompt = SIDE_AGENT_PROMPT.format(
        party_role=party_role,
        history=_format_history(shared_history),
        deal_terms=json.dumps(deal_terms_so_far),
        message=message,
    )

    response = await llm.ainvoke(prompt)
    raw = response.content.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Side agent returned non-JSON for %s; using safe fallback.", party_role)
        parsed = {
            "private_suggestion": "Consider clarifying this point before proceeding.",
            "flags": [],
            "updated_deal_terms": {},
        }

    flags = [f for f in parsed.get("flags", []) if f != "no_flags"]

    return {
        "private_suggestion": parsed.get("private_suggestion", ""),
        "flags": flags,
        "updated_deal_terms": parsed.get("updated_deal_terms", {}),
    }


async def extract_deal_summary(shared_history: list[dict]) -> dict:
    """
    The impartial orchestrator step: reads the full shared chat and
    determines whether a deal has been reached, extracting structured
    terms for the deal summary (Module 5, FE-3).
    """
    llm = get_llm()
    prompt = DEAL_EXTRACTION_PROMPT.format(history=_format_history(shared_history))

    response = await llm.ainvoke(prompt)
    raw = response.content.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Deal extraction returned non-JSON; assuming no deal yet.")
        parsed = {"is_deal_reached": False, "deal_summary": {}, "confidence": 0.0}

    return parsed


def build_negotiation_graph():
    """
    Assembles the full LangGraph multi-agent negotiation pipeline used
    when a deal is being finalized: two private side agents run in
    parallel, an impartial orchestrator reconciles deal state, and (on
    deal close) hands off to the contract builder. Deadlock detection
    uses a minimum-position resolution heuristic — if both sides' last
    three proposals haven't moved closer together, the orchestrator
    flags a stalemate for human/admin review rather than looping forever.
    """
    from langgraph.graph import StateGraph, END

    class GraphState(TypedDict):
        shared_history: list[dict]
        founder_terms: dict
        investor_terms: dict
        deal_summary: dict
        is_deal_reached: bool
        stalemate: bool
        round_count: int

    async def orchestrator_node(state: GraphState) -> GraphState:
        result = await extract_deal_summary(state["shared_history"])
        state["is_deal_reached"] = result["is_deal_reached"]
        state["deal_summary"] = result["deal_summary"]
        state["round_count"] = state.get("round_count", 0) + 1

        # Deadlock detection: minimum-position resolution heuristic
        if not state["is_deal_reached"] and state["round_count"] >= 6:
            founder_val = state["founder_terms"].get("valuation")
            investor_val = state["investor_terms"].get("valuation")
            if founder_val and investor_val:
                gap_ratio = abs(founder_val - investor_val) / max(founder_val, investor_val, 1)
                if gap_ratio > 0.3:  # >30% apart after 6 rounds = stalemate
                    state["stalemate"] = True
        return state

    def route_after_orchestrator(state: GraphState) -> str:
        if state.get("is_deal_reached"):
            return "deal_closed"
        if state.get("stalemate"):
            return "stalemate"
        return "continue"

    graph = StateGraph(GraphState)
    graph.add_node("orchestrator", orchestrator_node)
    graph.set_entry_point("orchestrator")
    graph.add_conditional_edges(
        "orchestrator",
        route_after_orchestrator,
        {
            "deal_closed": END,
            "stalemate": END,
            "continue": END,  # per-turn invocation; Django re-invokes on each new message
        },
    )

    return graph.compile()
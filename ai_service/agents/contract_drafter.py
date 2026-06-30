"""
Drafts the final contract from confirmed deal terms (Module 6, FE-3/FE-4).
Produces structured contract sections plus a full contract text, ready
for the multi-agent independent AI review pass and DocuSign e-signature
flow (handled in apps/contracts in Phase 8).
"""
import json
import logging

from ai_service.dependencies import get_llm

logger = logging.getLogger(__name__)

CONTRACT_DRAFT_PROMPT = """You are Venturify's contract drafting agent. Draft a \
startup investment agreement based on the confirmed deal terms below. This is an \
AI-generated draft for informational purposes — it will be reviewed and the \
parties will e-sign through DocuSign. Use clear, standard investment agreement \
language and structure.

Startup: {startup_name}
Founder: {founder_name}
Investor: {investor_name}
Deal Summary: {deal_summary}

Return ONLY a JSON object with these keys:
{{
  "contract_text": "<full contract text, plain text with section headers, ready for PDF rendering>",
  "contract_sections": {{
    "parties": "<section text>",
    "investment_terms": "<section text>",
    "equity_and_instrument": "<section text>",
    "milestones_and_fund_release": "<section text>",
    "representations_and_warranties": "<section text>",
    "governing_law": "<section text>",
    "signatures": "<section text>"
  }},
  "payment_structure": "<lumpsum|phased, taken directly from deal_summary>",
  "milestones": [{{"description": "<str>", "deadline_days": <int>, "release_pct": <float>}}]
}}

If deal_summary.payment_structure is "phased" but no milestones were specified, \
generate 3 reasonable milestones with even release_pct splits totaling 100. If \
"lumpsum", return an empty milestones list.

Return ONLY the JSON, no markdown fences."""


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return raw


async def draft_contract(
    startup_name: str,
    founder_name: str,
    investor_name: str,
    deal_summary: dict,
) -> dict:
    llm = get_llm()
    prompt = CONTRACT_DRAFT_PROMPT.format(
        startup_name=startup_name,
        founder_name=founder_name,
        investor_name=investor_name,
        deal_summary=json.dumps(deal_summary),
    )
    response = await llm.ainvoke(prompt)
    raw = _strip_fences(response.content)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Contract drafting returned non-JSON for %s; using minimal fallback.", startup_name)
        parsed = _fallback_contract(startup_name, founder_name, investor_name, deal_summary)

    return parsed


def _fallback_contract(startup_name, founder_name, investor_name, deal_summary: dict) -> dict:
    payment_structure = deal_summary.get("payment_structure", "lumpsum")
    text = (
        f"INVESTMENT AGREEMENT\n\n"
        f"Between {founder_name} (Founder, '{startup_name}') and {investor_name} (Investor).\n\n"
        f"Deal Terms: {json.dumps(deal_summary, indent=2)}\n\n"
        f"This is a system-generated fallback draft. Please regenerate or contact support."
    )
    return {
        "contract_text": text,
        "contract_sections": {"parties": text},
        "payment_structure": payment_structure,
        "milestones": [],
    }
"""
Startup Pitch conversational flow (Module 3, FE-1/FE-2).
Drives the founder through problem -> solution -> market -> team -> funding_ask,
extracting structured context at each turn, then signals completion so the
caller (Django) can trigger document + PoC generation.
"""
import json
import logging

from ai_service.dependencies import get_llm

logger = logging.getLogger(__name__)

PHASE_ORDER = ["problem", "solution", "market", "team", "funding_ask", "review", "done"]

PHASE_PROMPTS = {
    "problem": "Ask the founder to clearly describe the problem their startup solves. Probe for specificity — who experiences this problem and how painful is it?",
    "solution": "Ask the founder to describe their solution and what makes it different from existing alternatives.",
    "market": "Ask the founder about their target market size, customer segment, and go-to-market approach.",
    "team": "Ask the founder about their team's background, relevant experience, and any gaps they're aware of.",
    "funding_ask": "Ask the founder how much funding they're seeking and what specific milestones that funding will achieve.",
    "review": "Summarize everything gathered so far back to the founder and ask them to confirm it's accurate, or tell you what to change.",
}

SYSTEM_PROMPT = """You are Venturify's startup pitch assistant. You guide founders \
through a structured conversational pitch-building flow, one phase at a time. \
Be warm, encouraging, and concise — ask one focused question at a time, never a \
list of questions. 

Current phase: {phase}
Phase goal: {phase_goal}

Conversation so far:
{history}

Respond with a JSON object with EXACTLY these keys:
{{
  "reply": "<your next message to the founder>",
  "phase_complete": <true if this phase's goal has been sufficiently answered, else false>,
  "extracted_data": {{"<key>": "<extracted value from the founder's most recent message>"}}
}}

Only set phase_complete=true once you have a clear, usable answer for this phase. \
extracted_data should capture concrete facts (e.g. {{"problem": "..."}}) — leave it \
empty ({{}}) if nothing new was extracted this turn. Return ONLY the JSON object, \
no other text, no markdown fences."""


def _format_history(history: list[dict]) -> str:
    lines = []
    for msg in history[-10:]:  # last 10 turns is enough context
        role = "Founder" if msg.get("role") == "user" else "Assistant"
        lines.append(f"{role}: {msg.get('content', '')}")
    return "\n".join(lines) if lines else "(conversation just started)"


async def advance_pitch_conversation(
    current_phase: str,
    conversation_history: list[dict],
    pitch_context: dict,
) -> dict:
    """
    Runs one turn of the conversational pitch flow.
    Returns: {"reply": str, "next_phase": str, "is_complete": bool, "extracted_context": dict}
    """
    llm = get_llm()

    if current_phase not in PHASE_ORDER:
        current_phase = "problem"

    phase_goal = PHASE_PROMPTS.get(current_phase, "Wrap up the pitch conversation.")
    prompt = SYSTEM_PROMPT.format(
        phase=current_phase,
        phase_goal=phase_goal,
        history=_format_history(conversation_history),
    )

    response = await llm.ainvoke(prompt)
    raw = response.content.strip()

    # Strip accidental markdown fences
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Pitch agent returned non-JSON response, falling back to plain reply.")
        parsed = {"reply": raw, "phase_complete": False, "extracted_data": {}}

    reply = parsed.get("reply", "Could you tell me more about that?")
    phase_complete = parsed.get("phase_complete", False)
    extracted_data = parsed.get("extracted_data", {})

    current_idx = PHASE_ORDER.index(current_phase)
    is_complete = False

    if phase_complete:
        if current_phase == "review":
            is_complete = True
            next_phase = "done"
        else:
            next_phase = PHASE_ORDER[current_idx + 1]
    else:
        next_phase = current_phase

    return {
        "reply": reply,
        "next_phase": next_phase,
        "is_complete": is_complete,
        "extracted_context": extracted_data,
    }
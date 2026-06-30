"""
Legal Context Agent (Module 6).
  FE-1: Surfaces legal risks in the negotiation context with guidance.
  FE-2: Generates plain-English legal briefings per party.
  FE-3/FE-4: Drafts the final contract from confirmed deal terms (see contract_drafter.py).
"""
import json
import logging

from ai_service.dependencies import get_llm

logger = logging.getLogger(__name__)

RISK_CHECK_PROMPT = """You are Venturify's legal context agent. You identify legal \
risks in real time as a startup investment negotiation progresses — you are NOT a \
substitute for a licensed attorney, and your output is informational only.

Party you're advising: {party_role}
Deal terms so far: {deal_terms}
Latest negotiation message: "{latest_message}"

Identify any legal risks present in the current terms or this latest message \
(e.g. unclear IP assignment, missing anti-dilution language, no vesting schedule, \
ambiguous milestone definitions, missing governing law clause). If there are no \
material risks yet, say so.

Return ONLY a JSON object:
{{
  "risks": ["<short risk description>", ...],
  "guidance": "<2-3 sentence plain-English guidance for the {party_role}>"
}}

Return ONLY the JSON, no markdown fences."""

BRIEFING_PROMPT = """You are Venturify's legal context agent. Write a plain-English \
legal briefing for the {party_role} summarizing their protections and obligations \
under the following confirmed deal terms. This is informational only and does not \
constitute legal advice — the briefing itself should make this clear in tone but \
does not need a disclaimer sentence (the platform shows that separately).

Deal Summary: {deal_summary}

Return ONLY a JSON object:
{{
  "briefing": "<3-5 sentence plain-English summary of the deal from the {party_role}'s perspective>",
  "protections": ["<protection 1>", "<protection 2>", ...],
  "obligations": ["<obligation 1>", "<obligation 2>", ...]
}}

Return ONLY the JSON, no markdown fences."""


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return raw


async def check_legal_risks(party_role: str, deal_terms_so_far: dict, latest_message: str) -> dict:
    llm = get_llm()
    prompt = RISK_CHECK_PROMPT.format(
        party_role=party_role,
        deal_terms=json.dumps(deal_terms_so_far),
        latest_message=latest_message,
    )
    response = await llm.ainvoke(prompt)
    raw = _strip_fences(response.content)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Legal risk check returned non-JSON; defaulting to no risks flagged.")
        parsed = {"risks": [], "guidance": "Unable to assess risks at this time."}

    return parsed


async def generate_legal_briefing(party_role: str, deal_summary: dict) -> dict:
    llm = get_llm()
    prompt = BRIEFING_PROMPT.format(party_role=party_role, deal_summary=json.dumps(deal_summary))
    response = await llm.ainvoke(prompt)
    raw = _strip_fences(response.content)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Legal briefing returned non-JSON; using fallback.")
        parsed = {
            "briefing": "A legal briefing could not be generated at this time. Please review the deal summary directly.",
            "protections": [],
            "obligations": [],
        }

    return parsed
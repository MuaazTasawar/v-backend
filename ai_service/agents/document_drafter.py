"""
LLM-driven elaboration of raw pitch context into full document content
for feasibility reports, proposals, executive summaries, and pitch decks
(Module 3, FE-2: "Feasibility report, pitch deck, detailed proposal,
executive summary auto-generated after pitching").
"""
import json
import logging

from ai_service.dependencies import get_llm

logger = logging.getLogger(__name__)


async def elaborate_pitch_context(document_type: str, pitch_context: dict) -> dict:
    """Uses the LLM to expand terse pitch_context fields into full narrative content."""
    llm = get_llm()

    if document_type == "feasibility_report":
        prompt = f"""Based on this startup pitch context, write a feasibility analysis. \
Return ONLY a JSON object with these keys: market_opportunity, financial_viability, \
operational_readiness, key_risks, overall_assessment. Each value should be 2-3 \
sentences of substantive analysis, not generic filler.

Pitch Context: {json.dumps(pitch_context)}"""

    elif document_type == "executive_summary":
        prompt = f"""Based on this startup pitch context, write a single polished \
executive summary paragraph (5-7 sentences) suitable for an investor's first read. \
Return ONLY a JSON object: {{"summary": "<text>"}}.

Pitch Context: {json.dumps(pitch_context)}"""

    else:  # proposal, pitch_deck — use raw context directly, no elaboration needed
        return pitch_context

    response = await llm.ainvoke(prompt)
    raw = response.content.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        elaborated = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Document elaboration returned non-JSON for %s; using raw context.", document_type)
        elaborated = {}

    merged = dict(pitch_context)
    for key, value in elaborated.items():
        merged[f"{key}_analysis" if document_type == "feasibility_report" and key != "overall_assessment" else key] = value

    # Normalize keys to what doc_gen.build_document_content expects
    if document_type == "feasibility_report":
        merged["market_opportunity_analysis"] = elaborated.get("market_opportunity", "")
        merged["financial_viability_analysis"] = elaborated.get("financial_viability", "")
        merged["operational_readiness_analysis"] = elaborated.get("operational_readiness", "")
        merged["key_risks_analysis"] = elaborated.get("key_risks", "")
        merged["overall_assessment"] = elaborated.get("overall_assessment", "")
    elif document_type == "executive_summary":
        merged["executive_summary_text"] = elaborated.get("summary", "")

    return merged
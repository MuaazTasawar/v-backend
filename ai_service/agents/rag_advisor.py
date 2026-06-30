"""
Dual-Layer RAG Architecture with Confidence Routing (Project Contribution #3).

Routes investor due-diligence and founder advisory questions between:
  1. ChromaDB vector search over the startup's own indexed context, and
  2. LLM + Tavily web search fallback, when retrieval confidence is low.

Routing is based on cosine similarity score against a configurable
threshold — invisible to the end user.
"""
import logging

from ai_service.config import get_settings
from ai_service.dependencies import get_llm
from ai_service.utils.chroma import query_collection

logger = logging.getLogger(__name__)
settings = get_settings()


SYSTEM_PROMPT_RAG = """You are Venturify's advisory assistant. Answer the user's \
question using ONLY the provided startup context below. Be precise, cite specific \
facts from the context, and keep your answer concise (3-5 sentences unless more \
detail is explicitly requested). If the context doesn't fully answer the question, \
say what you do know and note the gap — do not fabricate details.

Startup Context:
{context}

Question: {question}"""

SYSTEM_PROMPT_WEB_FALLBACK = """You are Venturify's advisory assistant. The startup's \
internal context did not have enough information to confidently answer this question, \
so you've been given supplementary web search results. Combine any relevant internal \
context with the web results to give a helpful, accurate answer. Be clear about what \
is startup-specific vs general market/industry information. Keep your answer concise.

Internal Context (may be partial):
{context}

Web Search Results:
{web_results}

Question: {question}"""


def _tavily_search(query: str, max_results: int = 4) -> str:
    if not settings.TAVILY_API_KEY:
        logger.warning("TAVILY_API_KEY not set; skipping web fallback search.")
        return ""
    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=settings.TAVILY_API_KEY)
        response = client.search(query=query, max_results=max_results, search_depth="advanced")
        results = response.get("results", [])
        formatted = "\n\n".join(
            f"- {r.get('title', '')}: {r.get('content', '')[:400]}" for r in results
        )
        return formatted
    except Exception as exc:
        logger.error("Tavily search failed: %s", exc)
        return ""


async def answer_advisory_question(
    collection_name: str,
    question: str,
    persona: str = "investor",
) -> dict:
    """
    Core dual-layer RAG entry point.
    Returns: {"answer": str, "source": "internal"|"web_fallback"|"hybrid", "confidence": float}
    """
    llm = get_llm()

    # Layer 1: ChromaDB retrieval
    retrieval = query_collection(collection_name, question, n_results=5)
    context_chunks = retrieval.get("documents", [])
    best_similarity = retrieval.get("best_similarity", 0.0)
    context_text = "\n\n".join(context_chunks) if context_chunks else "(no internal context found)"

    if best_similarity >= settings.CHROMA_CONFIDENCE_THRESHOLD:
        # High confidence — answer purely from internal context
        prompt = SYSTEM_PROMPT_RAG.format(context=context_text, question=question)
        response = await llm.ainvoke(prompt)
        return {
            "answer": response.content,
            "source": "internal",
            "confidence": round(best_similarity, 3),
        }

    # Layer 2: Low confidence — fall back to live web search
    logger.info(
        "Low confidence (%.3f) for collection %s; falling back to web search.",
        best_similarity, collection_name,
    )
    web_results = _tavily_search(question)
    prompt = SYSTEM_PROMPT_WEB_FALLBACK.format(
        context=context_text, web_results=web_results or "(no web results available)", question=question
    )
    response = await llm.ainvoke(prompt)
    return {
        "answer": response.content,
        "source": "hybrid" if context_chunks else "web_fallback",
        "confidence": round(best_similarity, 3),
    }


async def generate_feasibility_summary(pitch_context: dict) -> str:
    """
    Used by the Advisory Panel (Module 4, FE-3) to give investors a
    quick financial/legal/operational read on a startup's feasibility.
    """
    llm = get_llm()
    prompt = f"""Based on the following startup pitch context, write a concise \
feasibility summary covering: (1) market opportunity, (2) team strength, \
(3) financial viability of the funding ask, and (4) key risks. Keep it to \
4 short paragraphs, written for a prospective investor.

Pitch Context:
{pitch_context}
"""
    response = await llm.ainvoke(prompt)
    return response.content
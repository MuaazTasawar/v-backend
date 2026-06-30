import logging

from fastapi import APIRouter, Depends, HTTPException, status

from ai_service.dependencies import verify_internal_secret
from ai_service.utils.chroma import index_startup_documents
from ai_service.agents.rag_advisor import answer_advisory_question, generate_feasibility_summary
from ai_service.schemas.advisory import (
    AdvisoryQuestionRequest,
    AdvisoryQuestionResponse,
    FeasibilitySummaryRequest,
    FeasibilitySummaryResponse,
    IndexStartupRequest,
    IndexStartupResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/advisory",
    tags=["advisory"],
    dependencies=[Depends(verify_internal_secret)],
)


@router.post("/index-startup", response_model=IndexStartupResponse)
async def index_startup(payload: IndexStartupRequest):
    """
    Indexes a startup's pitch context and generated documents into ChromaDB.
    Called by Django (apps.startups.tasks.index_startup_context) after pitch
    completion and whenever documents are regenerated.
    """
    try:
        collection_name = index_startup_documents(
            startup_id=payload.startup_id,
            pitch_context=payload.pitch_context,
            generated_documents=payload.generated_documents,
        )
    except Exception as exc:
        logger.error("Indexing failed for startup %s: %s", payload.startup_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to index startup context.",
        )

    return IndexStartupResponse(collection_name=collection_name, chunks_indexed=0)


@router.post("/ask", response_model=AdvisoryQuestionResponse)
async def ask_advisory_question(payload: AdvisoryQuestionRequest):
    """
    Investor-facing or founder-facing chatbot endpoint (Module 4, FE-1/FE-2).
    Implements dual-layer RAG with confidence-based routing.
    """
    try:
        result = await answer_advisory_question(
            collection_name=payload.collection_name,
            question=payload.question,
            persona=payload.persona,
        )
    except Exception as exc:
        logger.error("Advisory question failed for startup %s: %s", payload.startup_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Advisory assistant encountered an error.",
        )

    return AdvisoryQuestionResponse(**result)


@router.post("/feasibility-summary", response_model=FeasibilitySummaryResponse)
async def feasibility_summary(payload: FeasibilitySummaryRequest):
    """
    Investors can review feasibility reports covering financial, legal,
    and operational analysis of the startup (Module 4, FE-3).
    """
    try:
        summary = await generate_feasibility_summary(payload.pitch_context)
    except Exception as exc:
        logger.error("Feasibility summary failed for startup %s: %s", payload.startup_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate feasibility summary.",
        )

    return FeasibilitySummaryResponse(summary=summary)
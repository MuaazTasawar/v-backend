import logging

from fastapi import APIRouter, Depends, HTTPException, status

from ai_service.dependencies import verify_internal_secret
from ai_service.agents.negotiation_graph import run_side_agent, extract_deal_summary
from ai_service.schemas.chat import (
    ChatTurnRequest,
    ChatTurnResponse,
    ExtractDealSummaryRequest,
    ExtractDealSummaryResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
    dependencies=[Depends(verify_internal_secret)],
)


@router.post("/turn", response_model=ChatTurnResponse)
async def negotiation_turn(payload: ChatTurnRequest):
    """
    Runs the private side agent for one party's negotiation message
    (Module 5, FE-2). The response is NEVER forwarded to the opposing
    party — Django/realtime_service must keep this strictly scoped to
    the sender's own private panel.
    """
    try:
        result = await run_side_agent(
            party_role=payload.party_role,
            message=payload.message,
            shared_history=payload.shared_history,
            deal_terms_so_far=payload.deal_terms_so_far,
        )
    except Exception as exc:
        logger.error("Negotiation turn failed for %s: %s", payload.negotiation_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Negotiation assistant encountered an error.",
        )
    return ChatTurnResponse(**result)


@router.post("/extract-deal-summary", response_model=ExtractDealSummaryResponse)
async def extract_deal(payload: ExtractDealSummaryRequest):
    """
    Impartial orchestrator pass: checks the full shared chat for mutual
    deal confirmation and extracts structured terms (Module 5, FE-3).
    Called by Django after every shared chat message.
    """
    try:
        result = await extract_deal_summary(payload.shared_history)
    except Exception as exc:
        logger.error("Deal extraction failed for %s: %s", payload.negotiation_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Deal extraction encountered an error.",
        )
    return ExtractDealSummaryResponse(**result)
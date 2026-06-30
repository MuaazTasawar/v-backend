import logging

from fastapi import APIRouter, Depends, HTTPException, status

from ai_service.dependencies import verify_internal_secret
from ai_service.agents.legal_agent import check_legal_risks, generate_legal_briefing
from ai_service.agents.contract_drafter import draft_contract
from ai_service.schemas.legal import (
    DraftContractRequest,
    DraftContractResponse,
    LegalBriefingRequest,
    LegalBriefingResponse,
    LegalRiskCheckRequest,
    LegalRiskCheckResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/legal",
    tags=["legal"],
    dependencies=[Depends(verify_internal_secret)],
)


@router.post("/risk-check", response_model=LegalRiskCheckResponse)
async def risk_check(payload: LegalRiskCheckRequest):
    """Module 6, FE-1: surfaces legal risks in real time during negotiation."""
    try:
        result = await check_legal_risks(
            party_role=payload.party_role,
            deal_terms_so_far=payload.deal_terms_so_far,
            latest_message=payload.latest_message,
        )
    except Exception as exc:
        logger.error("Legal risk check failed for %s: %s", payload.negotiation_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Legal risk check encountered an error.",
        )
    return LegalRiskCheckResponse(**result)


@router.post("/briefing", response_model=LegalBriefingResponse)
async def briefing(payload: LegalBriefingRequest):
    """Module 6, FE-2: plain-English legal briefing generated per party."""
    try:
        result = await generate_legal_briefing(
            party_role=payload.party_role,
            deal_summary=payload.deal_summary,
        )
    except Exception as exc:
        logger.error("Legal briefing failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Legal briefing generation encountered an error.",
        )
    return LegalBriefingResponse(**result)


@router.post("/draft-contract", response_model=DraftContractResponse)
async def draft_contract_endpoint(payload: DraftContractRequest):
    """Module 6, FE-3: final contract drafted from all confirmed deal terms."""
    try:
        result = await draft_contract(
            startup_name=payload.startup_name,
            founder_name=payload.founder_name,
            investor_name=payload.investor_name,
            deal_summary=payload.deal_summary,
        )
    except Exception as exc:
        logger.error("Contract drafting failed for startup %s: %s", payload.startup_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Contract drafting encountered an error.",
        )
    return DraftContractResponse(**result)
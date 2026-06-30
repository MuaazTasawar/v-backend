import logging

from fastapi import APIRouter, Depends, HTTPException, status

from ai_service.dependencies import verify_internal_secret
from ai_service.agents.pitch_agent import advance_pitch_conversation
from ai_service.agents.document_drafter import elaborate_pitch_context
from ai_service.agents.poc_generator import generate_and_deploy_poc
from ai_service.utils.doc_gen import (
    build_document_content,
    generate_executive_summary_pdf,
    generate_feasibility_report_pdf,
    generate_pitch_deck_pptx,
    generate_proposal_pdf,
)
from ai_service.utils.s3 import upload_bytes
from ai_service.schemas.pitch import (
    GenerateDocumentRequest,
    GenerateDocumentResponse,
    GeneratePoCRequest,
    GeneratePoCResponse,
    PitchConverseRequest,
    PitchConverseResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/pitch",
    tags=["pitch"],
    dependencies=[Depends(verify_internal_secret)],
)


@router.post("/converse", response_model=PitchConverseResponse)
async def converse(payload: PitchConverseRequest):
    """
    Conversational pitch-building flow (Module 3, FE-1).
    Called by Django on every founder message in the pitch session.
    """
    try:
        result = await advance_pitch_conversation(
            current_phase=payload.current_phase,
            conversation_history=[m.model_dump() for m in payload.conversation_history],
            pitch_context=payload.pitch_context,
        )
    except Exception as exc:
        logger.error("Pitch conversation failed for startup %s: %s", payload.startup_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Pitch assistant encountered an error.",
        )
    return PitchConverseResponse(**result)


@router.post("/generate-document", response_model=GenerateDocumentResponse)
async def generate_document(payload: GenerateDocumentRequest):
    """
    Generates one of: feasibility_report, pitch_deck, proposal, executive_summary
    (Module 3, FE-2). Returns a downloadable file URL plus structured content.
    """
    valid_types = ["feasibility_report", "pitch_deck", "proposal", "executive_summary"]
    if payload.document_type not in valid_types:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid document_type.")

    try:
        elaborated_context = await elaborate_pitch_context(payload.document_type, payload.pitch_context)
        content_json = build_document_content(payload.document_type, elaborated_context)

        startup_name = payload.pitch_context.get("startup_name") or "Untitled Startup"

        if payload.document_type == "feasibility_report":
            file_bytes = generate_feasibility_report_pdf(startup_name, content_json)
            ext, content_type = "pdf", "application/pdf"
        elif payload.document_type == "proposal":
            file_bytes = generate_proposal_pdf(startup_name, content_json)
            ext, content_type = "pdf", "application/pdf"
        elif payload.document_type == "executive_summary":
            file_bytes = generate_executive_summary_pdf(startup_name, content_json)
            ext, content_type = "pdf", "application/pdf"
        else:  # pitch_deck
            file_bytes = generate_pitch_deck_pptx(startup_name, content_json)
            ext, content_type = "pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"

        s3_key = f"documents/{payload.startup_id}/{payload.document_type}.{ext}"
        file_url = upload_bytes(file_bytes, s3_key, content_type=content_type, public=False)

    except Exception as exc:
        logger.error("Document generation failed for %s/%s: %s", payload.startup_id, payload.document_type, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document generation failed.",
        )

    return GenerateDocumentResponse(file_url=file_url, content_json=content_json)


@router.post("/generate-poc", response_model=GeneratePoCResponse)
async def generate_poc(payload: GeneratePoCRequest):
    """
    Generates and deploys a static PoC website to a live public URL
    (Module 3, FE-4; Project Contribution #6).
    """
    try:
        result = await generate_and_deploy_poc(
            startup_id=payload.startup_id,
            startup_name=payload.startup_name,
            pitch_context=payload.pitch_context,
        )
    except Exception as exc:
        logger.error("PoC generation failed for startup %s: %s", payload.startup_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PoC generation failed.",
        )
    return GeneratePoCResponse(**result)
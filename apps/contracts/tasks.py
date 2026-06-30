import logging

import httpx
from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


def process_negotiation_message(negotiation, party_role: str, message: str, timestamp: str) -> dict:
    """
    Synchronous orchestration called directly from ProcessNegotiationMessageView
    (kept synchronous, not a Celery task, since realtime_service is waiting
    on this response to fan out via Redis with minimal latency).

    1. Persist the shared message.
    2. Call AI service: side agent suggestion, legal risk check (parallel-ish via two calls).
    3. Call AI service: deal extraction against the full updated history.
    4. Update Negotiation state; if deal reached, create the Contract.
    """
    from .models import Negotiation, Contract

    # 1. Persist shared message
    negotiation.shared_history.append({
        "role": party_role,
        "content": message,
        "timestamp": timestamp,
    })
    negotiation.round_count += 1

    result = {
        "private_suggestion": None,
        "flags": [],
        "legal_risks": [],
        "legal_guidance": "",
        "is_deal_reached": False,
        "deal_summary": {},
    }

    headers = {"X-Internal-Secret": settings.AI_SERVICE_SECRET}

    # 2a. Side agent
    try:
        resp = httpx.post(
            f"{settings.AI_SERVICE_URL}/chat/turn",
            json={
                "negotiation_id": str(negotiation.id),
                "party_role": party_role,
                "message": message,
                "shared_history": negotiation.shared_history,
                "deal_terms_so_far": negotiation.deal_terms_so_far,
            },
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        side_result = resp.json()
        result["private_suggestion"] = side_result.get("private_suggestion")
        result["flags"] = side_result.get("flags", [])
        if side_result.get("updated_deal_terms"):
            negotiation.deal_terms_so_far.update(side_result["updated_deal_terms"])
    except httpx.HTTPError as exc:
        logger.error("Side agent call failed for negotiation %s: %s", negotiation.id, exc)

    # 2b. Legal risk check
    try:
        resp = httpx.post(
            f"{settings.AI_SERVICE_URL}/legal/risk-check",
            json={
                "negotiation_id": str(negotiation.id),
                "party_role": party_role,
                "deal_terms_so_far": negotiation.deal_terms_so_far,
                "latest_message": message,
            },
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        legal_result = resp.json()
        result["legal_risks"] = legal_result.get("risks", [])
        result["legal_guidance"] = legal_result.get("guidance", "")
    except httpx.HTTPError as exc:
        logger.error("Legal risk check failed for negotiation %s: %s", negotiation.id, exc)

    # 3. Deal extraction (impartial orchestrator pass)
    try:
        resp = httpx.post(
            f"{settings.AI_SERVICE_URL}/chat/extract-deal-summary",
            json={
                "negotiation_id": str(negotiation.id),
                "shared_history": negotiation.shared_history,
            },
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        extraction_result = resp.json()
        result["is_deal_reached"] = extraction_result.get("is_deal_reached", False)
        result["deal_summary"] = extraction_result.get("deal_summary", {})
    except httpx.HTTPError as exc:
        logger.error("Deal extraction failed for negotiation %s: %s", negotiation.id, exc)

    # 4. Update negotiation; create contract if deal reached
    if result["is_deal_reached"] and negotiation.status == "active":
        negotiation.status = Negotiation.Status.DEAL_REACHED
        negotiation.deal_summary = result["deal_summary"]
        negotiation.save()

        if not hasattr(negotiation, "contract"):
            contract = Contract.objects.create(
                negotiation=negotiation,
                startup=negotiation.startup,
                founder=negotiation.founder,
                investor=negotiation.investor,
                deal_summary=result["deal_summary"],
                payment_structure=result["deal_summary"].get("payment_structure", "lumpsum"),
                valuation=result["deal_summary"].get("valuation"),
                investment_amount=result["deal_summary"].get("amount"),
                equity_pct=result["deal_summary"].get("equity_pct"),
                instrument=result["deal_summary"].get("instrument", ""),
            )
            draft_contract_text.delay(str(contract.id))
    else:
        negotiation.save()

    return result


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def draft_contract_text(self, contract_id: str):
    """Calls the AI service to draft the full contract text and sections, then runs AI review."""
    from .models import Contract
    from .state_machine import transition_contract

    try:
        contract = Contract.objects.select_related("startup", "founder", "investor").get(id=contract_id)
    except Contract.DoesNotExist:
        logger.error("Contract %s not found for drafting.", contract_id)
        return

    try:
        resp = httpx.post(
            f"{settings.AI_SERVICE_URL}/legal/draft-contract",
            json={
                "startup_id": str(contract.startup.id),
                "deal_summary": contract.deal_summary,
                "founder_name": contract.founder.full_name,
                "investor_name": contract.investor.full_name,
                "startup_name": contract.startup.name,
            },
            headers={"X-Internal-Secret": settings.AI_SERVICE_SECRET},
            timeout=120,
        )
        resp.raise_for_status()
        result = resp.json()

        contract.contract_text = result.get("contract_text", "")
        contract.contract_sections = result.get("contract_sections", {})
        contract.payment_structure = result.get("payment_structure", contract.payment_structure)
        contract.save(update_fields=["contract_text", "contract_sections", "payment_structure"])

        # Create milestones if phased
        if result.get("milestones") and contract.payment_structure == "phased":
            from .models import Milestone
            from datetime import date, timedelta

            for idx, m in enumerate(result["milestones"], start=1):
                Milestone.objects.get_or_create(
                    contract=contract,
                    sequence=idx,
                    defaults={
                        "description": m.get("description", f"Milestone {idx}"),
                        "deadline_days": m.get("deadline_days", 30),
                        "deadline_date": date.today() + timedelta(days=m.get("deadline_days", 30)),
                        "release_pct": m.get("release_pct", 0),
                    },
                )

        transition_contract(contract, to_state="drafted", reason="AI drafting complete.")
        run_contract_ai_review.delay(str(contract.id))

    except httpx.HTTPError as exc:
        logger.error("Contract drafting failed for %s: %s", contract_id, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def run_contract_ai_review(self, contract_id: str, revision_reason: str = ""):
    """
    Independent AI review pass over the drafted contract — checks for
    internal consistency, fairness flags, and missing standard clauses
    before either party is asked to approve. Re-runs the drafter if a
    revision was requested.
    """
    from .models import Contract
    from .state_machine import transition_contract, InvalidTransitionError

    try:
        contract = Contract.objects.get(id=contract_id)
    except Contract.DoesNotExist:
        return

    if revision_reason:
        # Re-draft incorporating the revision reason as additional context
        contract.deal_summary["revision_request"] = revision_reason
        contract.save(update_fields=["deal_summary"])
        draft_contract_text.delay(contract_id)
        return

    try:
        transition_contract(contract, to_state="under_review", reason="Independent AI review started.")
    except InvalidTransitionError as exc:
        logger.warning("Could not move contract %s to under_review: %s", contract_id, exc)
        return

    # The review itself reuses the legal risk-check agent against the full deal summary
    try:
        resp = httpx.post(
            f"{settings.AI_SERVICE_URL}/legal/risk-check",
            json={
                "negotiation_id": str(contract.negotiation_id),
                "party_role": "founder",  # neutral pass; review applies to both
                "deal_terms_so_far": contract.deal_summary,
                "latest_message": "Final contract review prior to signature.",
            },
            headers={"X-Internal-Secret": settings.AI_SERVICE_SECRET},
            timeout=60,
        )
        resp.raise_for_status()
        review_result = resp.json()

        contract.ai_review_notes = review_result.get("risks", [])
        contract.ai_review_passed = len(contract.ai_review_notes) == 0
        contract.save(update_fields=["ai_review_notes", "ai_review_passed"])

    except httpx.HTTPError as exc:
        logger.error("AI contract review failed for %s: %s", contract_id, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def send_contract_for_signature(self, contract_id: str):
    """Creates a DocuSign envelope and sends it to both parties (Module 7, FE-4)."""
    from .models import Contract

    try:
        contract = Contract.objects.select_related("founder", "investor", "startup").get(id=contract_id)
    except Contract.DoesNotExist:
        logger.error("Contract %s not found for DocuSign send.", contract_id)
        return

    try:
        envelope_id = _create_docusign_envelope(contract)
        contract.docusign_envelope_id = envelope_id
        contract.save(update_fields=["docusign_envelope_id"])
    except Exception as exc:
        logger.error("DocuSign envelope creation failed for contract %s: %s", contract_id, exc)
        raise self.retry(exc=exc)


def _create_docusign_envelope(contract) -> str:
    """
    Creates a DocuSign envelope with the contract text as the document
    body and both parties as signers. Returns the envelope ID.
    """
    import base64
    from docusign_esign import ApiClient, EnvelopesApi, EnvelopeDefinition, Document, Signer, SignHere, Tabs, Recipients

    api_client = ApiClient()
    api_client.host = settings.DOCUSIGN_BASE_URL
    api_client.set_default_header("Authorization", f"Bearer {_get_docusign_access_token()}")

    doc_b64 = base64.b64encode(contract.contract_text.encode("utf-8")).decode("utf-8")

    document = Document(
        document_base64=doc_b64,
        name=f"{contract.startup.name} Investment Agreement",
        file_extension="txt",
        document_id="1",
    )

    founder_signer = Signer(
        email=contract.founder.email,
        name=contract.founder.full_name,
        recipient_id="1",
        routing_order="1",
        tabs=Tabs(sign_here_tabs=[SignHere(anchor_string="Founder Signature:", anchor_units="pixels", anchor_y_offset="10", anchor_x_offset="20")]),
    )
    investor_signer = Signer(
        email=contract.investor.email,
        name=contract.investor.full_name,
        recipient_id="2",
        routing_order="2",
        tabs=Tabs(sign_here_tabs=[SignHere(anchor_string="Investor Signature:", anchor_units="pixels", anchor_y_offset="10", anchor_x_offset="20")]),
    )

    envelope_definition = EnvelopeDefinition(
        email_subject=f"Venturify: Sign your {contract.startup.name} investment agreement",
        documents=[document],
        recipients=Recipients(signers=[founder_signer, investor_signer]),
        status="sent",
    )

    envelopes_api = EnvelopesApi(api_client)
    results = envelopes_api.create_envelope(settings.DOCUSIGN_ACCOUNT_ID, envelope_definition=envelope_definition)
    return results.envelope_id


def _get_docusign_access_token() -> str:
    """
    Obtains a DocuSign JWT Grant access token. In production this should
    cache the token in Redis until near expiry rather than fetching fresh
    every call.
    """
    from docusign_esign import ApiClient
    import os

    api_client = ApiClient()
    api_client.host = settings.DOCUSIGN_BASE_URL

    private_key = os.environ.get("DOCUSIGN_PRIVATE_KEY", "").encode("utf-8")

    token_response = api_client.request_jwt_user_token(
        client_id=settings.DOCUSIGN_INTEGRATION_KEY,
        user_id=settings.DOCUSIGN_ACCOUNT_ID,
        oauth_host_name=settings.DOCUSIGN_BASE_URL.replace("https://", "").replace("/restapi", ""),
        private_key_bytes=private_key,
        expires_in=3600,
        scopes=["signature", "impersonation"],
    )
    return token_response.access_token


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def release_milestone_funds(self, milestone_id: str):
    """
    Triggers the financial ledger's fund release flow (Phase 9 builds the
    actual Stripe transfer logic). This task is the handoff point.
    """
    from .models import Milestone

    try:
        milestone = Milestone.objects.select_related("contract").get(id=milestone_id)
    except Milestone.DoesNotExist:
        logger.error("Milestone %s not found for fund release.", milestone_id)
        return

    try:
        from apps.financials.tasks import process_milestone_fund_release
        process_milestone_fund_release.delay(str(milestone.id))
    except ImportError:
        logger.warning("Financials app not yet wired (Phase 9); skipping fund release dispatch.")
@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def handle_docusign_status_update(self, envelope_id: str, envelope_status: str):
    """
    Processes a DocuSign envelope status webhook. Maps DocuSign's status
    vocabulary to contract state transitions.
      - "completed" -> both parties signed -> fully_executed -> active
      - "declined" / "voided" -> voided
    """
    from .models import Contract
    from .state_machine import transition_contract, InvalidTransitionError

    try:
        contract = Contract.objects.get(docusign_envelope_id=envelope_id)
    except Contract.DoesNotExist:
        logger.error("No contract found for DocuSign envelope %s", envelope_id)
        return

    status_lower = envelope_status.lower()

    try:
        if status_lower == "completed":
            if contract.state not in (Contract.State.FULLY_EXECUTED, Contract.State.ACTIVE):
                transition_contract(
                    contract, to_state=Contract.State.FULLY_EXECUTED, reason="DocuSign envelope completed."
                )
                transition_contract(
                    contract, to_state=Contract.State.ACTIVE, reason="Contract activated post-execution."
                )
                from apps.financials.tasks import initialize_contract_escrow
                try:
                    initialize_contract_escrow.delay(str(contract.id))
                except ImportError:
                    logger.warning("Financials app not yet wired (Phase 9); skipping escrow init.")

        elif status_lower in ("declined", "voided"):
            transition_contract(
                contract,
                to_state=Contract.State.VOIDED,
                reason=f"DocuSign envelope {status_lower}.",
            )
    except InvalidTransitionError as exc:
        logger.warning("DocuSign status update could not transition contract %s: %s", contract.id, exc)
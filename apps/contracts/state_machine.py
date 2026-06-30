"""
Explicit, auditable state machine for Contract lifecycle transitions
(Module 7). Every transition is validated against an allow-list, and
every successful transition is recorded in ContractStateTransition for
a tamper-evident history (Module 8 audit/compliance requirement).
"""
import logging

logger = logging.getLogger(__name__)


class InvalidTransitionError(Exception):
    pass


# Allowed transitions: {from_state: {to_state, ...}}
ALLOWED_TRANSITIONS = {
    "drafting": {"drafted", "voided"},
    "drafted": {"under_review", "voided"},
    "under_review": {"revision_requested", "ready_for_signature", "voided"},
    "revision_requested": {"under_review", "voided"},
    "ready_for_signature": {"sent_for_signature", "voided"},
    "sent_for_signature": {"founder_signed", "investor_signed", "voided"},
    "founder_signed": {"investor_signed", "fully_executed", "voided"},
    "investor_signed": {"founder_signed", "fully_executed", "voided"},
    "fully_executed": {"active", "voided"},
    "active": {"completed", "voided"},
    "completed": set(),
    "voided": set(),
}


def can_transition(from_state: str, to_state: str) -> bool:
    return to_state in ALLOWED_TRANSITIONS.get(from_state, set())


def transition_contract(contract, to_state: str, triggered_by=None, reason: str = "", metadata: dict | None = None):
    """
    Validates and applies a contract state transition, persisting both
    the new state and an audit trail entry. Raises InvalidTransitionError
    if the transition isn't allowed from the contract's current state.
    """
    from .models import ContractStateTransition

    from_state = contract.state

    if from_state == to_state:
        logger.warning("No-op transition requested for contract %s: %s -> %s", contract.id, from_state, to_state)
        return contract

    if not can_transition(from_state, to_state):
        raise InvalidTransitionError(
            f"Cannot transition contract {contract.id} from '{from_state}' to '{to_state}'."
        )

    contract.state = to_state

    # State-specific side effects on the contract record itself
    from django.utils import timezone

    if to_state == "founder_signed":
        contract.founder_signed_at = timezone.now()
    elif to_state == "investor_signed":
        contract.investor_signed_at = timezone.now()
    elif to_state == "fully_executed":
        contract.fully_executed_at = timezone.now()
        if not contract.founder_signed_at:
            contract.founder_signed_at = timezone.now()
        if not contract.investor_signed_at:
            contract.investor_signed_at = timezone.now()
    elif to_state == "voided" and reason:
        contract.voided_reason = reason

    contract.save()

    ContractStateTransition.objects.create(
        contract=contract,
        from_state=from_state,
        to_state=to_state,
        triggered_by=triggered_by,
        reason=reason,
        metadata=metadata or {},
    )

    logger.info("Contract %s transitioned %s -> %s", contract.id, from_state, to_state)
    return contract


def both_parties_signed(contract) -> bool:
    return bool(contract.founder_signed_at and contract.investor_signed_at)
import uuid
from django.db import models
from django.contrib.auth import get_user_model
from apps.startups.models import Startup

User = get_user_model()


class Negotiation(models.Model):
    """
    Created when a founder accepts an investor's interest signal.
    Hosts the shared chat, deal terms in progress, and (on close) the
    final contract.
    """
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DEAL_REACHED = "deal_reached", "Deal Reached"
        STALEMATE = "stalemate", "Stalemate"
        ABANDONED = "abandoned", "Abandoned"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    startup = models.ForeignKey(Startup, on_delete=models.CASCADE, related_name="negotiations")
    founder = models.ForeignKey(User, on_delete=models.CASCADE, related_name="negotiations_as_founder")
    investor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="negotiations_as_investor")

    shared_history = models.JSONField(default=list, blank=True)
    # [{"role": "founder"|"investor", "content": str, "timestamp": str}]

    deal_terms_so_far = models.JSONField(default=dict, blank=True)
    # accumulates as updated_deal_terms come back from the side agents

    round_count = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    deal_summary = models.JSONField(default=dict, blank=True)
    # final extracted terms once is_deal_reached=True

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "negotiations"
        unique_together = ("startup", "investor")
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Negotiation({self.startup.name}, {self.founder.email} <-> {self.investor.email})"


class Contract(models.Model):
    """
    The drafted, reviewed, and (eventually) signed investment agreement
    produced from a closed Negotiation. Tracks the full lifecycle via
    state_machine.py's explicit transition rules.
    """
    class State(models.TextChoices):
        DRAFTING = "drafting", "Drafting"
        DRAFTED = "drafted", "Drafted"
        UNDER_REVIEW = "under_review", "Under AI Review"
        REVISION_REQUESTED = "revision_requested", "Revision Requested"
        READY_FOR_SIGNATURE = "ready_for_signature", "Ready for Signature"
        SENT_FOR_SIGNATURE = "sent_for_signature", "Sent for Signature"
        FOUNDER_SIGNED = "founder_signed", "Founder Signed"
        INVESTOR_SIGNED = "investor_signed", "Investor Signed"
        FULLY_EXECUTED = "fully_executed", "Fully Executed"
        ACTIVE = "active", "Active (Funds in Escrow/Released)"
        COMPLETED = "completed", "Completed"
        VOIDED = "voided", "Voided"

    class PaymentStructure(models.TextChoices):
        LUMPSUM = "lumpsum", "Lump Sum"
        PHASED = "phased", "Phased (Milestone-Based)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    negotiation = models.OneToOneField(Negotiation, on_delete=models.CASCADE, related_name="contract")
    startup = models.ForeignKey(Startup, on_delete=models.CASCADE, related_name="contracts")
    founder = models.ForeignKey(User, on_delete=models.CASCADE, related_name="contracts_as_founder")
    investor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="contracts_as_investor")

    state = models.CharField(max_length=30, choices=State.choices, default=State.DRAFTING)

    deal_summary = models.JSONField(default=dict, blank=True)
    contract_text = models.TextField(blank=True)
    contract_sections = models.JSONField(default=dict, blank=True)
    payment_structure = models.CharField(
        max_length=20, choices=PaymentStructure.choices, default=PaymentStructure.LUMPSUM
    )

    valuation = models.PositiveBigIntegerField(null=True, blank=True)
    investment_amount = models.PositiveBigIntegerField(null=True, blank=True)
    equity_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    instrument = models.CharField(max_length=30, blank=True)  # equity | safe | convertible_note

    # AI review pass (independent multi-agent review before human sign-off)
    ai_review_notes = models.JSONField(default=list, blank=True)
    ai_review_passed = models.BooleanField(default=False)
    revision_requested_by = models.CharField(max_length=20, blank=True)  # founder | investor

    # DocuSign
    docusign_envelope_id = models.CharField(max_length=100, blank=True, null=True)
    founder_signed_at = models.DateTimeField(null=True, blank=True)
    investor_signed_at = models.DateTimeField(null=True, blank=True)
    fully_executed_at = models.DateTimeField(null=True, blank=True)
    signed_document_url = models.URLField(blank=True, null=True)

    voided_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "contracts"
        indexes = [models.Index(fields=["state"])]

    def __str__(self):
        return f"Contract({self.startup.name}, {self.state})"


class ContractStateTransition(models.Model):
    """Append-only audit trail of every contract state change."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="state_transitions")
    from_state = models.CharField(max_length=30)
    to_state = models.CharField(max_length=30)
    triggered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "contract_state_transitions"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.from_state} -> {self.to_state} ({self.contract_id})"


class Milestone(models.Model):
    """Phased fund-release milestones (Module 8, FE-2)."""
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_PROGRESS = "in_progress", "In Progress"
        SUBMITTED = "submitted", "Submitted for Review"
        APPROVED = "approved", "Approved"
        DISPUTED = "disputed", "Disputed"
        RELEASED = "released", "Funds Released"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="milestones")

    sequence = models.PositiveSmallIntegerField()
    description = models.TextField()
    deadline_days = models.PositiveSmallIntegerField()
    deadline_date = models.DateField(null=True, blank=True)
    release_pct = models.DecimalField(max_digits=5, decimal_places=2)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    submission_notes = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "milestones"
        ordering = ["contract", "sequence"]
        unique_together = ("contract", "sequence")

    def __str__(self):
        return f"Milestone {self.sequence}({self.contract_id}, {self.status})"
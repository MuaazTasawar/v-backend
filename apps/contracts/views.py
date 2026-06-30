import logging

from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auth_app.permissions import IsFounder, IsInvestor, IsFounderOrInvestor
from .models import Negotiation, Contract, ContractStateTransition, Milestone
from .serializers import (
    ContractDetailSerializer,
    ContractListSerializer,
    ContractStateTransitionSerializer,
    MilestoneSerializer,
    MilestoneSubmitSerializer,
    NegotiationSerializer,
    ProcessMessageSerializer,
    RequestRevisionSerializer,
    VoidContractSerializer,
)
from .state_machine import transition_contract, InvalidTransitionError, both_parties_signed
from .tasks import (
    process_negotiation_message,
    run_contract_ai_review,
    send_contract_for_signature,
)

logger = logging.getLogger(__name__)


# ── Negotiations ──────────────────────────────────────────────────────────

class NegotiationListView(generics.ListAPIView):
    """GET /api/v1/contracts/negotiations/ — List negotiations for the current user."""
    serializer_class = NegotiationSerializer
    permission_classes = [IsAuthenticated, IsFounderOrInvestor]

    def get_queryset(self):
        user = self.request.user
        if user.is_founder:
            return Negotiation.objects.filter(founder=user).select_related("startup", "investor")
        return Negotiation.objects.filter(investor=user).select_related("startup", "founder")


class NegotiationDetailView(generics.RetrieveAPIView):
    """GET /api/v1/contracts/negotiations/<id>/"""
    serializer_class = NegotiationSerializer
    permission_classes = [IsAuthenticated, IsFounderOrInvestor]

    def get_object(self):
        negotiation = get_object_or_404(Negotiation, id=self.kwargs["pk"])
        user = self.request.user
        if user not in (negotiation.founder, negotiation.investor):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You are not a party to this negotiation.")
        return negotiation


class ProcessNegotiationMessageView(APIView):
    """
    POST /api/v1/contracts/negotiations/<id>/process-message/
    Internal-only endpoint called by realtime_service on every chat
    message. Validates the shared internal secret, persists the message,
    runs the AI side agent / legal check / deal extraction synchronously
    (these are fast LLM calls — sub-5s typically), and returns results
    for realtime_service to fan out via Redis Pub/Sub.
    """
    permission_classes = [AllowAny]  # secured via X-Internal-Secret check below

    def post(self, request, negotiation_id):
        from django.conf import settings as django_settings

        if request.headers.get("X-Internal-Secret") != django_settings.AI_SERVICE_SECRET:
            return Response({"error": "Unauthorized."}, status=status.HTTP_401_UNAUTHORIZED)

        negotiation = get_object_or_404(Negotiation, id=negotiation_id)
        serializer = ProcessMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        result = process_negotiation_message(
            negotiation=negotiation,
            party_role=data["party_role"],
            message=data["message"],
            timestamp=data["timestamp"],
        )

        return Response(result, status=status.HTTP_200_OK)


# ── Contracts ─────────────────────────────────────────────────────────────

class ContractListView(generics.ListAPIView):
    """GET /api/v1/contracts/ — List contracts for the current user."""
    serializer_class = ContractListSerializer
    permission_classes = [IsAuthenticated, IsFounderOrInvestor]
    filterset_fields = ["state"]

    def get_queryset(self):
        user = self.request.user
        if user.is_founder:
            return Contract.objects.filter(founder=user)
        return Contract.objects.filter(investor=user)


class ContractDetailView(generics.RetrieveAPIView):
    """GET /api/v1/contracts/<id>/"""
    serializer_class = ContractDetailSerializer
    permission_classes = [IsAuthenticated, IsFounderOrInvestor]

    def get_object(self):
        contract = get_object_or_404(Contract.objects.prefetch_related("milestones"), id=self.kwargs["pk"])
        user = self.request.user
        if user not in (contract.founder, contract.investor):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You are not a party to this contract.")
        return contract


class ContractHistoryView(generics.ListAPIView):
    """GET /api/v1/contracts/<id>/history/ — Full audit trail of state transitions."""
    serializer_class = ContractStateTransitionSerializer
    permission_classes = [IsAuthenticated, IsFounderOrInvestor]

    def get_queryset(self):
        contract = get_object_or_404(Contract, id=self.kwargs["contract_id"])
        user = self.request.user
        if user not in (contract.founder, contract.investor):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You are not a party to this contract.")
        return ContractStateTransition.objects.filter(contract=contract).select_related("triggered_by")


class RequestContractRevisionView(APIView):
    """
    POST /api/v1/contracts/<id>/request-revision/
    Either party can request a revision while the contract is under_review.
    """
    permission_classes = [IsAuthenticated, IsFounderOrInvestor]

    def post(self, request, contract_id):
        contract = get_object_or_404(Contract, id=contract_id)
        if request.user not in (contract.founder, contract.investor):
            return Response({"error": "Not a party to this contract."}, status=status.HTTP_403_FORBIDDEN)

        serializer = RequestRevisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        party_role = "founder" if request.user == contract.founder else "investor"

        try:
            transition_contract(
                contract,
                to_state=Contract.State.REVISION_REQUESTED,
                triggered_by=request.user,
                reason=serializer.validated_data["reason"],
            )
        except InvalidTransitionError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        contract.revision_requested_by = party_role
        contract.save(update_fields=["revision_requested_by"])

        run_contract_ai_review.delay(str(contract.id), revision_reason=serializer.validated_data["reason"])

        return Response({"message": "Revision requested. Contract is being redrafted."}, status=status.HTTP_200_OK)


class ApproveContractView(APIView):
    """
    POST /api/v1/contracts/<id>/approve/
    Both parties approve the AI-reviewed draft to move it to
    ready_for_signature. Requires both founder and investor approval —
    tracked via metadata on the transition since approval itself isn't a
    state (only the resulting transition is).
    """
    permission_classes = [IsAuthenticated, IsFounderOrInvestor]

    def post(self, request, contract_id):
        contract = get_object_or_404(Contract, id=contract_id)
        if request.user not in (contract.founder, contract.investor):
            return Response({"error": "Not a party to this contract."}, status=status.HTTP_403_FORBIDDEN)

        if contract.state != Contract.State.UNDER_REVIEW:
            return Response(
                {"error": f"Contract must be under_review to approve; current state is {contract.state}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        party_role = "founder" if request.user == contract.founder else "investor"
        approvals = contract.ai_review_notes  # reuse JSON field area isn't ideal; track via metadata instead
        # Track approvals on the transition metadata of a lightweight marker
        approved_key = f"approved_by_{party_role}"
        metadata = {approved_key: True}

        # Check prior approval from the other party via transition history
        other_role = "investor" if party_role == "founder" else "founder"
        other_approved = ContractStateTransition.objects.filter(
            contract=contract,
            from_state=Contract.State.UNDER_REVIEW,
            to_state=Contract.State.UNDER_REVIEW,  # marker transitions are no-ops in state but logged
            metadata__contains={f"approved_by_{other_role}": True},
        ).exists()

        if other_approved:
            try:
                transition_contract(
                    contract,
                    to_state=Contract.State.READY_FOR_SIGNATURE,
                    triggered_by=request.user,
                    reason="Both parties approved.",
                    metadata={"approved_by_founder": True, "approved_by_investor": True},
                )
            except InvalidTransitionError as exc:
                return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            return Response(
                {"message": "Both parties approved. Contract is ready for signature.", "state": contract.state},
                status=status.HTTP_200_OK,
            )
        else:
            ContractStateTransition.objects.create(
                contract=contract,
                from_state=Contract.State.UNDER_REVIEW,
                to_state=Contract.State.UNDER_REVIEW,
                triggered_by=request.user,
                reason=f"{party_role} approved; awaiting {other_role}.",
                metadata=metadata,
            )
            return Response(
                {"message": f"Approval recorded. Awaiting {other_role}'s approval."},
                status=status.HTTP_200_OK,
            )


class SendForSignatureView(APIView):
    """POST /api/v1/contracts/<id>/send-for-signature/ — Founder triggers DocuSign envelope creation."""
    permission_classes = [IsAuthenticated, IsFounder]

    def post(self, request, contract_id):
        contract = get_object_or_404(Contract, id=contract_id, founder=request.user)

        if contract.state != Contract.State.READY_FOR_SIGNATURE:
            return Response(
                {"error": f"Contract must be ready_for_signature; current state is {contract.state}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            transition_contract(
                contract,
                to_state=Contract.State.SENT_FOR_SIGNATURE,
                triggered_by=request.user,
                reason="Sent to DocuSign for e-signature.",
            )
        except InvalidTransitionError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        send_contract_for_signature.delay(str(contract.id))

        return Response({"message": "Contract sent for signature via DocuSign."}, status=status.HTTP_202_ACCEPTED)


class VoidContractView(APIView):
    """POST /api/v1/contracts/<id>/void/ — Either party can void before full execution."""
    permission_classes = [IsAuthenticated, IsFounderOrInvestor]

    def post(self, request, contract_id):
        contract = get_object_or_404(Contract, id=contract_id)
        if request.user not in (contract.founder, contract.investor):
            return Response({"error": "Not a party to this contract."}, status=status.HTTP_403_FORBIDDEN)

        if contract.state in (Contract.State.FULLY_EXECUTED, Contract.State.ACTIVE, Contract.State.COMPLETED):
            return Response(
                {"error": "Cannot void a contract that is fully executed, active, or completed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = VoidContractSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            transition_contract(
                contract,
                to_state=Contract.State.VOIDED,
                triggered_by=request.user,
                reason=serializer.validated_data["reason"],
            )
        except InvalidTransitionError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"message": "Contract voided."}, status=status.HTTP_200_OK)


# ── Milestones ────────────────────────────────────────────────────────────

class MilestoneListView(generics.ListAPIView):
    """GET /api/v1/contracts/<id>/milestones/"""
    serializer_class = MilestoneSerializer
    permission_classes = [IsAuthenticated, IsFounderOrInvestor]

    def get_queryset(self):
        contract = get_object_or_404(Contract, id=self.kwargs["contract_id"])
        return Milestone.objects.filter(contract=contract)


class MilestoneSubmitView(APIView):
    """POST /api/v1/contracts/milestones/<id>/submit/ — Founder submits milestone for review."""
    permission_classes = [IsAuthenticated, IsFounder]

    def post(self, request, milestone_id):
        milestone = get_object_or_404(Milestone, id=milestone_id, contract__founder=request.user)

        if milestone.status not in (Milestone.Status.PENDING, Milestone.Status.IN_PROGRESS, Milestone.Status.DISPUTED):
            return Response(
                {"error": f"Cannot submit milestone in status {milestone.status}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = MilestoneSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from django.utils import timezone
        milestone.submission_notes = serializer.validated_data["submission_notes"]
        milestone.status = Milestone.Status.SUBMITTED
        milestone.submitted_at = timezone.now()
        milestone.save(update_fields=["submission_notes", "status", "submitted_at"])

        return Response({"message": "Milestone submitted for investor review."}, status=status.HTTP_200_OK)


class MilestoneApproveView(APIView):
    """
    POST /api/v1/contracts/milestones/<id>/approve/
    Investor approves a submitted milestone, triggering fund release
    (Phase 9 financial ledger picks this up via Celery task).
    """
    permission_classes = [IsAuthenticated, IsInvestor]

    def post(self, request, milestone_id):
        from .tasks import release_milestone_funds

        milestone = get_object_or_404(Milestone, id=milestone_id, contract__investor=request.user)

        if milestone.status != Milestone.Status.SUBMITTED:
            return Response(
                {"error": "Milestone must be submitted before it can be approved."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from django.utils import timezone
        milestone.status = Milestone.Status.APPROVED
        milestone.approved_at = timezone.now()
        milestone.save(update_fields=["status", "approved_at"])

        release_milestone_funds.delay(str(milestone.id))

        return Response({"message": "Milestone approved. Fund release in progress."}, status=status.HTTP_202_ACCEPTED)


class MilestoneDisputeView(APIView):
    """POST /api/v1/contracts/milestones/<id>/dispute/ — Investor disputes a submitted milestone."""
    permission_classes = [IsAuthenticated, IsInvestor]

    def post(self, request, milestone_id):
        milestone = get_object_or_404(Milestone, id=milestone_id, contract__investor=request.user)

        if milestone.status != Milestone.Status.SUBMITTED:
            return Response(
                {"error": "Only submitted milestones can be disputed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        milestone.status = Milestone.Status.DISPUTED
        milestone.save(update_fields=["status"])

        return Response({"message": "Milestone disputed. Founder has been notified."}, status=status.HTTP_200_OK)
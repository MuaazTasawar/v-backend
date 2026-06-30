from rest_framework import serializers
from .models import Negotiation, Contract, ContractStateTransition, Milestone


class NegotiationSerializer(serializers.ModelSerializer):
    startup_name = serializers.CharField(source="startup.name", read_only=True)
    founder_name = serializers.CharField(source="founder.full_name", read_only=True)
    investor_name = serializers.CharField(source="investor.full_name", read_only=True)
    has_contract = serializers.SerializerMethodField()

    class Meta:
        model = Negotiation
        fields = [
            "id",
            "startup",
            "startup_name",
            "founder_name",
            "investor_name",
            "shared_history",
            "deal_terms_so_far",
            "round_count",
            "status",
            "deal_summary",
            "has_contract",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_has_contract(self, obj):
        return hasattr(obj, "contract")


class ProcessMessageSerializer(serializers.Serializer):
    """Internal-only schema for the realtime_service -> Django callback."""
    party_role = serializers.ChoiceField(choices=["founder", "investor"])
    user_id = serializers.UUIDField()
    message = serializers.CharField()
    timestamp = serializers.CharField()


class MilestoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Milestone
        fields = [
            "id",
            "sequence",
            "description",
            "deadline_days",
            "deadline_date",
            "release_pct",
            "status",
            "submission_notes",
            "submitted_at",
            "approved_at",
            "released_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "sequence",
            "deadline_date",
            "status",
            "submitted_at",
            "approved_at",
            "released_at",
            "created_at",
            "updated_at",
        ]


class MilestoneSubmitSerializer(serializers.Serializer):
    submission_notes = serializers.CharField()


class ContractListSerializer(serializers.ModelSerializer):
    startup_name = serializers.CharField(source="startup.name", read_only=True)

    class Meta:
        model = Contract
        fields = [
            "id",
            "startup",
            "startup_name",
            "state",
            "payment_structure",
            "valuation",
            "investment_amount",
            "equity_pct",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ContractDetailSerializer(serializers.ModelSerializer):
    startup_name = serializers.CharField(source="startup.name", read_only=True)
    founder_name = serializers.CharField(source="founder.full_name", read_only=True)
    investor_name = serializers.CharField(source="investor.full_name", read_only=True)
    milestones = MilestoneSerializer(many=True, read_only=True)

    class Meta:
        model = Contract
        fields = [
            "id",
            "negotiation",
            "startup",
            "startup_name",
            "founder_name",
            "investor_name",
            "state",
            "deal_summary",
            "contract_text",
            "contract_sections",
            "payment_structure",
            "valuation",
            "investment_amount",
            "equity_pct",
            "instrument",
            "ai_review_notes",
            "ai_review_passed",
            "revision_requested_by",
            "docusign_envelope_id",
            "founder_signed_at",
            "investor_signed_at",
            "fully_executed_at",
            "signed_document_url",
            "voided_reason",
            "milestones",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ContractStateTransitionSerializer(serializers.ModelSerializer):
    triggered_by_name = serializers.CharField(source="triggered_by.full_name", read_only=True, default="System")

    class Meta:
        model = ContractStateTransition
        fields = ["id", "from_state", "to_state", "triggered_by_name", "reason", "metadata", "created_at"]
        read_only_fields = fields


class RequestRevisionSerializer(serializers.Serializer):
    reason = serializers.CharField()


class VoidContractSerializer(serializers.Serializer):
    reason = serializers.CharField()
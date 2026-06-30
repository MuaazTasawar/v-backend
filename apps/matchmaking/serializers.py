from rest_framework import serializers
from apps.startups.serializers import StartupListSerializer
from .models import MatchScore, SavedStartup, InterestSignal


class MatchScoreSerializer(serializers.ModelSerializer):
    startup = StartupListSerializer(read_only=True)

    class Meta:
        model = MatchScore
        fields = [
            "id",
            "startup",
            "overall_score",
            "industry_score",
            "stage_score",
            "ticket_size_score",
            "risk_score",
            "breakdown",
            "computed_at",
        ]
        read_only_fields = fields


class SavedStartupSerializer(serializers.ModelSerializer):
    startup = StartupListSerializer(read_only=True)
    startup_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = SavedStartup
        fields = ["id", "startup", "startup_id", "created_at"]
        read_only_fields = ["id", "startup", "created_at"]

    def create(self, validated_data):
        from apps.startups.models import Startup
        startup_id = validated_data.pop("startup_id")
        startup = Startup.objects.get(id=startup_id)
        investor = self.context["request"].user
        obj, _ = SavedStartup.objects.get_or_create(investor=investor, startup=startup)
        return obj


class InterestSignalSerializer(serializers.ModelSerializer):
    startup = StartupListSerializer(read_only=True)
    startup_id = serializers.UUIDField(write_only=True)
    investor_name = serializers.CharField(source="investor.full_name", read_only=True)

    class Meta:
        model = InterestSignal
        fields = [
            "id",
            "startup",
            "startup_id",
            "investor_name",
            "proposed_amount",
            "message",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "startup", "investor_name", "status", "created_at", "updated_at"]

    def create(self, validated_data):
        from apps.startups.models import Startup
        startup_id = validated_data.pop("startup_id")
        startup = Startup.objects.get(id=startup_id)
        investor = self.context["request"].user
        return InterestSignal.objects.create(investor=investor, startup=startup, **validated_data)


class InterestSignalRespondSerializer(serializers.Serializer):
    """Used by founders to accept/decline an interest signal."""
    action = serializers.ChoiceField(choices=["accept", "decline"])
from rest_framework import serializers
from apps.profiles.serializers import IndustryTagSerializer
from apps.profiles.models import IndustryTag
from .models import (
    Startup,
    PitchSession,
    GeneratedDocument,
    PoCDeployment,
    ProjectContextFile,
)


class StartupListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list/marketplace views."""
    industries = IndustryTagSerializer(many=True, read_only=True)
    founder_name = serializers.CharField(source="founder.full_name", read_only=True)

    class Meta:
        model = Startup
        fields = [
            "id",
            "name",
            "tagline",
            "logo_url",
            "industries",
            "funding_stage",
            "funding_ask",
            "equity_offered_pct",
            "status",
            "founder_name",
            "created_at",
        ]


class StartupDetailSerializer(serializers.ModelSerializer):
    industries = IndustryTagSerializer(many=True, read_only=True)
    industry_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=IndustryTag.objects.all(),
        write_only=True,
        source="industries",
        required=False,
    )
    founder_name = serializers.CharField(source="founder.full_name", read_only=True)
    founder_email = serializers.EmailField(source="founder.email", read_only=True)
    has_poc = serializers.SerializerMethodField()
    document_count = serializers.SerializerMethodField()

    class Meta:
        model = Startup
        fields = [
            "id",
            "name",
            "tagline",
            "logo_url",
            "industries",
            "industry_ids",
            "funding_stage",
            "funding_ask",
            "equity_offered_pct",
            "status",
            "pitch_context",
            "founder_name",
            "founder_email",
            "jira_workspace_url",
            "jira_project_key",
            "notion_workspace_id",
            "has_poc",
            "document_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "pitch_context",
            "founder_name",
            "founder_email",
            "has_poc",
            "document_count",
            "created_at",
            "updated_at",
        ]

    def get_has_poc(self, obj):
        return PoCDeployment.objects.filter(
            startup=obj, status=PoCDeployment.Status.LIVE
        ).exists()

    def get_document_count(self, obj):
        return obj.generated_documents.filter(status=GeneratedDocument.Status.READY).count()


class StartupCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Startup
        fields = ["name", "tagline", "funding_stage", "funding_ask", "equity_offered_pct"]

    def validate_equity_offered_pct(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Equity offered must be between 0 and 100.")
        return value


class JiraNotionConnectSerializer(serializers.Serializer):
    jira_workspace_url = serializers.URLField(required=False, allow_blank=True)
    jira_project_key = serializers.CharField(required=False, allow_blank=True)
    jira_access_token = serializers.CharField(required=False, allow_blank=True, write_only=True)
    notion_workspace_id = serializers.CharField(required=False, allow_blank=True)
    notion_access_token = serializers.CharField(required=False, allow_blank=True, write_only=True)


class PitchSessionSerializer(serializers.ModelSerializer):
    startup_name = serializers.CharField(source="startup.name", read_only=True)

    class Meta:
        model = PitchSession
        fields = [
            "id",
            "startup",
            "startup_name",
            "conversation_history",
            "current_phase",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "startup_name",
            "conversation_history",
            "current_phase",
            "status",
            "created_at",
            "updated_at",
        ]


class PitchMessageSerializer(serializers.Serializer):
    """Sent by the frontend to advance the conversational pitch flow."""
    message = serializers.CharField()


class GeneratedDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedDocument
        fields = [
            "id",
            "document_type",
            "status",
            "file_url",
            "content_json",
            "error_message",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PoCDeploymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PoCDeployment
        fields = [
            "id",
            "status",
            "live_url",
            "error_message",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ProjectContextFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectContextFile
        fields = ["id", "content", "is_indexed", "indexed_at", "updated_at"]
        read_only_fields = fields
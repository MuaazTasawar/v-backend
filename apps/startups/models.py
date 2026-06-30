import uuid
from django.db import models
from django.contrib.auth import get_user_model
from apps.profiles.models import IndustryTag

User = get_user_model()


class Startup(models.Model):
    class FundingStage(models.TextChoices):
        PRE_SEED = "pre_seed", "Pre-Seed"
        SEED = "seed", "Seed"
        SERIES_A = "series_a", "Series A"
        SERIES_B = "series_b", "Series B"
        GROWTH = "growth", "Growth"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PITCHING = "pitching", "Pitching in Progress"
        ANALYZING = "analyzing", "Feasibility Analysis"
        ACTIVE = "active", "Active / Listed"
        NEGOTIATING = "negotiating", "In Negotiation"
        FUNDED = "funded", "Funded"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    founder = models.ForeignKey(User, on_delete=models.CASCADE, related_name="startups")

    name = models.CharField(max_length=255)
    tagline = models.CharField(max_length=500, blank=True)
    logo_url = models.URLField(blank=True, null=True)

    industries = models.ManyToManyField(IndustryTag, blank=True, related_name="startups")
    funding_stage = models.CharField(
        max_length=20, choices=FundingStage.choices, default=FundingStage.PRE_SEED
    )
    funding_ask = models.PositiveBigIntegerField(default=0)  # USD
    equity_offered_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    # Pitch conversation context (raw structured data from conversational pitch flow)
    pitch_context = models.JSONField(default=dict, blank=True)
    # {"problem": str, "solution": str, "market": str, "team": str, "funding_ask": str, ...}

    # Project management integrations (Module 9/10)
    jira_workspace_url = models.URLField(blank=True)
    jira_project_key = models.CharField(max_length=50, blank=True)
    jira_access_token = models.TextField(blank=True)  # encrypted in production
    notion_workspace_id = models.CharField(max_length=100, blank=True)
    notion_access_token = models.TextField(blank=True)  # encrypted in production

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "startups"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["funding_stage"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.founder.email})"


class PitchSession(models.Model):
    """Tracks the conversational AI pitch-building flow per startup."""
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        ABANDONED = "abandoned", "Abandoned"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    startup = models.OneToOneField(
        Startup, on_delete=models.CASCADE, related_name="pitch_session"
    )
    founder = models.ForeignKey(User, on_delete=models.CASCADE, related_name="pitch_sessions")

    conversation_history = models.JSONField(default=list, blank=True)
    # [{"role": "user"|"assistant", "content": str, "timestamp": str}]

    current_phase = models.CharField(max_length=50, default="problem")
    # problem -> solution -> market -> team -> funding_ask -> review -> done

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_PROGRESS)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pitch_sessions"

    def __str__(self):
        return f"PitchSession({self.startup.name})"


class GeneratedDocument(models.Model):
    class DocumentType(models.TextChoices):
        FEASIBILITY_REPORT = "feasibility_report", "Feasibility Report"
        PITCH_DECK = "pitch_deck", "Pitch Deck"
        PROPOSAL = "proposal", "Detailed Proposal"
        EXECUTIVE_SUMMARY = "executive_summary", "Executive Summary"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        GENERATING = "generating", "Generating"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    startup = models.ForeignKey(
        Startup, on_delete=models.CASCADE, related_name="generated_documents"
    )
    document_type = models.CharField(max_length=30, choices=DocumentType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    file_url = models.URLField(blank=True, null=True)
    content_json = models.JSONField(default=dict, blank=True)  # structured content used to render
    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "generated_documents"
        unique_together = ("startup", "document_type")

    def __str__(self):
        return f"{self.document_type}({self.startup.name})"


class PoCDeployment(models.Model):
    """Live Proof-of-Concept website generated from pitch context."""
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        GENERATING = "generating", "Generating"
        DEPLOYING = "deploying", "Deploying"
        LIVE = "live", "Live"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    startup = models.OneToOneField(
        Startup, on_delete=models.CASCADE, related_name="poc_deployment"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    live_url = models.URLField(blank=True, null=True)
    s3_bucket_path = models.CharField(max_length=500, blank=True)
    generated_html = models.TextField(blank=True)
    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "poc_deployments"

    def __str__(self):
        return f"PoC({self.startup.name}, {self.status})"


class ProjectContextFile(models.Model):
    """
    Consolidated startup context used across the platform
    (advisory chatbot, negotiation agent, mentor agent, etc.)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    startup = models.OneToOneField(
        Startup, on_delete=models.CASCADE, related_name="context_file"
    )
    content = models.JSONField(default=dict, blank=True)
    chroma_collection_name = models.CharField(max_length=255, blank=True)
    is_indexed = models.BooleanField(default=False)
    indexed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "project_context_files"

    def __str__(self):
        return f"ContextFile({self.startup.name})"
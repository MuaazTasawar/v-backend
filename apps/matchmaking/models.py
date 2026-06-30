import uuid
from django.db import models
from django.contrib.auth import get_user_model
from apps.startups.models import Startup

User = get_user_model()


class MatchScore(models.Model):
    """
    Pre-computed compatibility score between an investor and a startup,
    based on the weighted matchmaking algorithm (BO-3).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    investor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="match_scores")
    startup = models.ForeignKey(Startup, on_delete=models.CASCADE, related_name="match_scores")

    overall_score = models.DecimalField(max_digits=5, decimal_places=2)  # 0-100
    industry_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    stage_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    ticket_size_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    risk_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    breakdown = models.JSONField(default=dict, blank=True)

    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "match_scores"
        unique_together = ("investor", "startup")
        ordering = ["-overall_score"]
        indexes = [
            models.Index(fields=["investor", "-overall_score"]),
        ]

    def __str__(self):
        return f"Match({self.investor.email} <-> {self.startup.name}: {self.overall_score})"


class SavedStartup(models.Model):
    """Investors can bookmark/save startups of interest."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    investor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="saved_startups")
    startup = models.ForeignKey(Startup, on_delete=models.CASCADE, related_name="saved_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "saved_startups"
        unique_together = ("investor", "startup")

    def __str__(self):
        return f"Saved({self.investor.email} -> {self.startup.name})"


class InterestSignal(models.Model):
    """
    Tracks when an investor expresses interest in a startup,
    creating the entry point for negotiation (Module 5).
    """
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    investor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="interest_signals_sent")
    startup = models.ForeignKey(Startup, on_delete=models.CASCADE, related_name="interest_signals")

    proposed_amount = models.PositiveBigIntegerField(null=True, blank=True)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "interest_signals"
        unique_together = ("investor", "startup")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Interest({self.investor.email} -> {self.startup.name}: {self.status})"
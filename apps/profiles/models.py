import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator

User = get_user_model()


class IndustryTag(models.Model):
    """Controlled vocabulary of industry tags used across profiles and startups."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        db_table = "industry_tags"
        ordering = ["name"]

    def __str__(self):
        return self.name


class FounderProfile(models.Model):
    class ExperienceLevel(models.TextChoices):
        FIRST_TIME = "first_time", "First-time Founder"
        SERIAL = "serial", "Serial Entrepreneur"
        TECHNICAL = "technical", "Technical Founder"
        BUSINESS = "business", "Business Founder"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="founder_profile"
    )

    # Core bio
    bio = models.TextField(blank=True)
    location = models.CharField(max_length=255, blank=True)
    website = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)

    # Background
    experience_level = models.CharField(
        max_length=20,
        choices=ExperienceLevel.choices,
        default=ExperienceLevel.FIRST_TIME,
    )
    years_of_experience = models.PositiveSmallIntegerField(default=0)
    education = models.JSONField(default=list, blank=True)
    # [{"institution": str, "degree": str, "field": str, "year": int}]

    work_history = models.JSONField(default=list, blank=True)
    # [{"company": str, "role": str, "from_year": int, "to_year": int|null, "description": str}]

    skills = models.JSONField(default=list, blank=True)
    # ["Python", "Product Management", ...]

    # Domain interests
    industries = models.ManyToManyField(IndustryTag, blank=True, related_name="founders")

    # CV upload
    cv_url = models.URLField(blank=True, null=True)
    cv_extracted_text = models.TextField(blank=True)

    # Identity verification
    id_document_url = models.URLField(blank=True, null=True)
    is_identity_verified = models.BooleanField(default=False)
    identity_verified_at = models.DateTimeField(null=True, blank=True)

    # Onboarding progress (0-100)
    onboarding_step = models.PositiveSmallIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "founder_profiles"

    def __str__(self):
        return f"FounderProfile({self.user.email})"


class InvestorProfile(models.Model):
    class InvestorType(models.TextChoices):
        ANGEL = "angel", "Angel Investor"
        VC = "vc", "Venture Capital"
        FAMILY_OFFICE = "family_office", "Family Office"
        CORPORATE = "corporate", "Corporate VC"
        MICRO_VC = "micro_vc", "Micro VC"

    class FundingStage(models.TextChoices):
        PRE_SEED = "pre_seed", "Pre-Seed"
        SEED = "seed", "Seed"
        SERIES_A = "series_a", "Series A"
        SERIES_B = "series_b", "Series B"
        GROWTH = "growth", "Growth"

    class RiskAppetite(models.TextChoices):
        CONSERVATIVE = "conservative", "Conservative"
        MODERATE = "moderate", "Moderate"
        AGGRESSIVE = "aggressive", "Aggressive"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="investor_profile"
    )

    # Core bio
    bio = models.TextField(blank=True)
    firm_name = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=255, blank=True)
    website = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)

    # Investment preferences
    investor_type = models.CharField(
        max_length=20,
        choices=InvestorType.choices,
        default=InvestorType.ANGEL,
    )
    preferred_stages = models.JSONField(default=list, blank=True)
    # ["pre_seed", "seed"]

    industries = models.ManyToManyField(
        IndustryTag, blank=True, related_name="investors"
    )

    # Ticket size in USD
    min_ticket_size = models.PositiveBigIntegerField(default=5000)
    max_ticket_size = models.PositiveBigIntegerField(default=100000)

    risk_appetite = models.CharField(
        max_length=20,
        choices=RiskAppetite.choices,
        default=RiskAppetite.MODERATE,
    )

    # Portfolio
    portfolio_companies = models.JSONField(default=list, blank=True)
    # [{"name": str, "website": str, "stage": str, "year": int}]

    total_investments_made = models.PositiveSmallIntegerField(default=0)

    # Stripe Connect for receiving/sending funds
    stripe_account_id = models.CharField(max_length=100, blank=True)
    stripe_onboarding_complete = models.BooleanField(default=False)

    # Identity verification
    id_document_url = models.URLField(blank=True, null=True)
    is_identity_verified = models.BooleanField(default=False)
    identity_verified_at = models.DateTimeField(null=True, blank=True)

    # Onboarding progress
    onboarding_step = models.PositiveSmallIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "investor_profiles"

    def __str__(self):
        return f"InvestorProfile({self.user.email})"


class CVExtractionJob(models.Model):
    """Tracks async CV text extraction jobs."""
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="cv_jobs")
    s3_key = models.CharField(max_length=500)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    extracted_text = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cv_extraction_jobs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"CVJob({self.user.email}, {self.status})"
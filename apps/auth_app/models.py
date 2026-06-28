import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_verified", True)
        extra_fields.setdefault("role", User.Role.ADMIN)
        if not extra_fields.get("is_staff"):
            raise ValueError("Superuser must have is_staff=True.")
        if not extra_fields.get("is_superuser"):
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        FOUNDER = "founder", "Founder"
        INVESTOR = "investor", "Investor"
        AUTOMATION_ENGINEER = "automation_engineer", "Automation Engineer"
        ADMIN = "admin", "Admin"

    class AuthProvider(models.TextChoices):
        LOCAL = "local", "Local"
        GOOGLE = "google", "Google"
        LINKEDIN = "linkedin", "LinkedIn"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=255)
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.FOUNDER)
    auth_provider = models.CharField(
        max_length=20, choices=AuthProvider.choices, default=AuthProvider.LOCAL
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    is_onboarded = models.BooleanField(default=False)

    avatar_url = models.URLField(blank=True, null=True)
    fcm_token = models.TextField(blank=True, null=True)  # Firebase push token

    date_joined = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        db_table = "users"
        ordering = ["-date_joined"]
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return f"{self.email} ({self.role})"

    @property
    def is_founder(self):
        return self.role == self.Role.FOUNDER

    @property
    def is_investor(self):
        return self.role == self.Role.INVESTOR

    @property
    def is_automation_engineer(self):
        return self.role == self.Role.AUTOMATION_ENGINEER


class EmailVerificationToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="email_verification_token"
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "email_verification_tokens"

    def is_valid(self):
        return timezone.now() < self.expires_at

    def __str__(self):
        return f"VerificationToken({self.user.email})"


class PasswordResetToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="password_reset_tokens"
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "password_reset_tokens"

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at

    def __str__(self):
        return f"PasswordResetToken({self.user.email})"
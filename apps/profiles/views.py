import logging
import uuid

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auth_app.permissions import IsFounder, IsInvestor, IsFounderOrInvestor
from .models import FounderProfile, InvestorProfile, IndustryTag, CVExtractionJob
from .serializers import (
    CVExtractionJobSerializer,
    CVUploadSerializer,
    FounderProfileSerializer,
    IDDocumentUploadSerializer,
    IndustryTagSerializer,
    InvestorProfileSerializer,
    OnboardingStepSerializer,
)
from .tasks import extract_cv_text, upload_file_to_s3

logger = logging.getLogger(__name__)
User = get_user_model()


class IndustryTagListView(generics.ListAPIView):
    """GET /api/v1/profiles/industries/ — List all available industry tags."""
    serializer_class = IndustryTagSerializer
    permission_classes = [IsAuthenticated]
    queryset = IndustryTag.objects.all()
    search_fields = ["name"]


# ── Founder Profile ───────────────────────────────────────────────────────────

class FounderProfileView(generics.RetrieveUpdateAPIView):
    """
    GET  /api/v1/profiles/founder/me/   — Retrieve own founder profile.
    PATCH /api/v1/profiles/founder/me/  — Update own founder profile.
    """
    serializer_class = FounderProfileSerializer
    permission_classes = [IsAuthenticated, IsFounder]

    def get_object(self):
        profile, _ = FounderProfile.objects.get_or_create(user=self.request.user)
        return profile

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        response = super().update(request, *args, **kwargs)
        self._recalculate_onboarding(request.user)
        return response

    def _recalculate_onboarding(self, user):
        """Advance onboarding_step based on profile completeness."""
        profile = user.founder_profile
        step = 0
        if profile.bio and profile.location:
            step = 1
        if profile.education and profile.work_history:
            step = 2
        if profile.skills:
            step = 3
        if profile.industries.exists():
            step = 4
        if profile.cv_url:
            step = 5
        if profile.is_identity_verified:
            step = 6

        profile.onboarding_step = step
        profile.save(update_fields=["onboarding_step"])

        if step >= 4 and not user.is_onboarded:
            user.is_onboarded = True
            user.save(update_fields=["is_onboarded"])


class FounderProfilePublicView(generics.RetrieveAPIView):
    """GET /api/v1/profiles/founder/<user_id>/ — Public view of a founder profile."""
    serializer_class = FounderProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        user_id = self.kwargs["user_id"]
        return generics.get_object_or_404(
            FounderProfile.objects.select_related("user").prefetch_related("industries"),
            user__id=user_id,
        )


# ── Investor Profile ──────────────────────────────────────────────────────────

class InvestorProfileView(generics.RetrieveUpdateAPIView):
    """
    GET  /api/v1/profiles/investor/me/  — Retrieve own investor profile.
    PATCH /api/v1/profiles/investor/me/ — Update own investor profile.
    """
    serializer_class = InvestorProfileSerializer
    permission_classes = [IsAuthenticated, IsInvestor]

    def get_object(self):
        profile, _ = InvestorProfile.objects.get_or_create(user=self.request.user)
        return profile

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        response = super().update(request, *args, **kwargs)
        self._recalculate_onboarding(request.user)
        return response

    def _recalculate_onboarding(self, user):
        profile = user.investor_profile
        step = 0
        if profile.bio and profile.location:
            step = 1
        if profile.investor_type and profile.preferred_stages:
            step = 2
        if profile.industries.exists():
            step = 3
        if profile.min_ticket_size and profile.max_ticket_size:
            step = 4
        if profile.is_identity_verified:
            step = 5

        profile.onboarding_step = step
        profile.save(update_fields=["onboarding_step"])

        if step >= 3 and not user.is_onboarded:
            user.is_onboarded = True
            user.save(update_fields=["is_onboarded"])


class InvestorProfilePublicView(generics.RetrieveAPIView):
    """GET /api/v1/profiles/investor/<user_id>/ — Public view of an investor profile."""
    serializer_class = InvestorProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        user_id = self.kwargs["user_id"]
        return generics.get_object_or_404(
            InvestorProfile.objects.select_related("user").prefetch_related("industries"),
            user__id=user_id,
        )


# ── CV Upload ─────────────────────────────────────────────────────────────────

class CVUploadView(APIView):
    """
    POST /api/v1/profiles/cv/upload/
    Accepts a PDF/DOCX, uploads to S3, triggers async text extraction.
    """
    permission_classes = [IsAuthenticated, IsFounder]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = CVUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cv_file = serializer.validated_data["cv_file"]
        user = request.user

        s3_key = f"cvs/{user.id}/{uuid.uuid4()}_{cv_file.name}"

        # Create tracking job
        job = CVExtractionJob.objects.create(user=user, s3_key=s3_key)

        # Dispatch upload + extraction to Celery
        extract_cv_text.delay(
            job_id=str(job.id),
            user_id=str(user.id),
            file_content=cv_file.read(),
            file_name=cv_file.name,
            content_type=cv_file.content_type,
            s3_key=s3_key,
        )

        return Response(
            {
                "message": "CV uploaded. Extraction in progress.",
                "job_id": str(job.id),
            },
            status=status.HTTP_202_ACCEPTED,
        )


class CVExtractionStatusView(generics.RetrieveAPIView):
    """GET /api/v1/profiles/cv/status/<job_id>/ — Poll CV extraction job status."""
    serializer_class = CVExtractionJobSerializer
    permission_classes = [IsAuthenticated, IsFounder]

    def get_object(self):
        return generics.get_object_or_404(
            CVExtractionJob,
            id=self.kwargs["job_id"],
            user=self.request.user,
        )


# ── Identity Verification ─────────────────────────────────────────────────────

class IDDocumentUploadView(APIView):
    """
    POST /api/v1/profiles/identity/upload/
    Upload a government ID image for identity verification.
    In production, integrate with a KYC provider (e.g., Jumio, Onfido).
    """
    permission_classes = [IsAuthenticated, IsFounderOrInvestor]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = IDDocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        id_doc = serializer.validated_data["id_document"]
        user = request.user

        s3_key = f"identity/{user.id}/{uuid.uuid4()}_{id_doc.name}"

        # Upload to S3 (synchronous here since it's small and security-sensitive)
        try:
            s3_url = upload_file_to_s3(
                file_content=id_doc.read(),
                s3_key=s3_key,
                content_type=id_doc.content_type,
            )
        except Exception as exc:
            logger.error("ID document S3 upload failed for user %s: %s", user.id, exc)
            return Response(
                {"error": "File upload failed. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Save to the appropriate profile
        if user.is_founder:
            profile, _ = FounderProfile.objects.get_or_create(user=user)
            profile.id_document_url = s3_url
            profile.save(update_fields=["id_document_url"])
        elif user.is_investor:
            profile, _ = InvestorProfile.objects.get_or_create(user=user)
            profile.id_document_url = s3_url
            profile.save(update_fields=["id_document_url"])

        # TODO: Trigger KYC provider webhook here for automated verification.
        # For now, admins verify manually via Django admin.

        return Response(
            {"message": "ID document uploaded. Verification is under review."},
            status=status.HTTP_202_ACCEPTED,
        )


# ── Stripe Connect Onboarding (Investor) ──────────────────────────────────────

class StripeConnectOnboardingView(APIView):
    """
    POST /api/v1/profiles/investor/stripe/onboard/
    Creates a Stripe Connect Express account and returns the onboarding URL.
    """
    permission_classes = [IsAuthenticated, IsInvestor]

    def post(self, request):
        import stripe
        from django.conf import settings

        stripe.api_key = settings.STRIPE_SECRET_KEY
        user = request.user
        profile, _ = InvestorProfile.objects.get_or_create(user=user)

        try:
            if not profile.stripe_account_id:
                account = stripe.Account.create(
                    type="express",
                    email=user.email,
                    capabilities={
                        "card_payments": {"requested": True},
                        "transfers": {"requested": True},
                    },
                    business_type="individual",
                    metadata={"venturify_user_id": str(user.id)},
                )
                profile.stripe_account_id = account.id
                profile.save(update_fields=["stripe_account_id"])

            account_link = stripe.AccountLink.create(
                account=profile.stripe_account_id,
                refresh_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/dashboard/stripe/refresh",
                return_url=f"{settings.CORS_ALLOWED_ORIGINS[0]}/dashboard/stripe/complete",
                type="account_onboarding",
            )
            return Response(
                {"onboarding_url": account_link.url},
                status=status.HTTP_200_OK,
            )
        except stripe.error.StripeError as exc:
            logger.error("Stripe Connect onboarding error for user %s: %s", user.id, exc)
            return Response(
                {"error": "Stripe onboarding failed. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )


class StripeConnectCompleteView(APIView):
    """
    GET /api/v1/profiles/investor/stripe/complete/
    Called after the user returns from Stripe onboarding.
    Verifies account status and marks onboarding complete.
    """
    permission_classes = [IsAuthenticated, IsInvestor]

    def get(self, request):
        import stripe
        from django.conf import settings

        stripe.api_key = settings.STRIPE_SECRET_KEY
        user = request.user
        profile = generics.get_object_or_404(InvestorProfile, user=user)

        if not profile.stripe_account_id:
            return Response(
                {"error": "No Stripe account found. Start onboarding first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            account = stripe.Account.retrieve(profile.stripe_account_id)
            if account.details_submitted:
                profile.stripe_onboarding_complete = True
                profile.save(update_fields=["stripe_onboarding_complete"])
                return Response(
                    {"message": "Stripe onboarding complete.", "account_id": profile.stripe_account_id},
                    status=status.HTTP_200_OK,
                )
            else:
                return Response(
                    {"message": "Stripe onboarding incomplete. Please complete all steps."},
                    status=status.HTTP_200_OK,
                )
        except stripe.error.StripeError as exc:
            logger.error("Stripe account retrieval error: %s", exc)
            return Response(
                {"error": "Could not verify Stripe account status."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
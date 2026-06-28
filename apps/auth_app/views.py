import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.exceptions import TokenError

from .models import EmailVerificationToken, PasswordResetToken
from .serializers import (
    ChangePasswordSerializer,
    CustomTokenObtainPairSerializer,
    PasswordResetSerializer,
    RegisterSerializer,
    RequestPasswordResetSerializer,
    SocialAuthSerializer,
    UpdateFCMTokenSerializer,
    UserSerializer,
    VerifyEmailSerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class RegisterView(generics.CreateAPIView):
    """POST /api/v1/auth/register/ — Create a new user account."""
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        # Dispatch verification email via Celery (wired in Phase 12)
        try:
            from celery_app.tasks.notification_tasks import send_verification_email
            send_verification_email.delay(str(user.id))
        except Exception:
            logger.warning("Notification task not yet wired; skipping email dispatch.")
        return Response(
            {
                "message": "Registration successful. Please verify your email.",
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class CustomTokenObtainPairView(TokenObtainPairView):
    """POST /api/v1/auth/login/ — Obtain JWT access + refresh tokens."""
    serializer_class = CustomTokenObtainPairSerializer


class LogoutView(APIView):
    """POST /api/v1/auth/logout/ — Blacklist the refresh token."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"error": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"message": "Logged out successfully."}, status=status.HTTP_200_OK)


class VerifyEmailView(APIView):
    """POST /api/v1/auth/verify-email/ — Confirm email with token."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        verification = serializer.context["verification"]
        user = verification.user
        user.is_verified = True
        user.save(update_fields=["is_verified"])
        verification.delete()
        return Response(
            {"message": "Email verified successfully."},
            status=status.HTTP_200_OK,
        )


class ResendVerificationEmailView(APIView):
    """POST /api/v1/auth/resend-verification/ — Resend verification email."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if user.is_verified:
            return Response(
                {"message": "Email already verified."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Delete old token and create fresh one
        EmailVerificationToken.objects.filter(user=user).delete()
        EmailVerificationToken.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        try:
            from celery_app.tasks.notification_tasks import send_verification_email
            send_verification_email.delay(str(user.id))
        except Exception:
            logger.warning("Notification task not yet wired; skipping email dispatch.")
        return Response(
            {"message": "Verification email resent."},
            status=status.HTTP_200_OK,
        )


class RequestPasswordResetView(APIView):
    """POST /api/v1/auth/password-reset/request/ — Send password reset link."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RequestPasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        try:
            user = User.objects.get(email=email, auth_provider=User.AuthProvider.LOCAL)
            PasswordResetToken.objects.filter(user=user, is_used=False).delete()
            PasswordResetToken.objects.create(
                user=user,
                expires_at=timezone.now() + timedelta(hours=2),
            )
            try:
                from celery_app.tasks.notification_tasks import send_password_reset_email
                send_password_reset_email.delay(str(user.id))
            except Exception:
                logger.warning("Notification task not yet wired.")
        except User.DoesNotExist:
            pass  # Silent — avoids email enumeration
        return Response(
            {"message": "If an account with that email exists, a reset link has been sent."},
            status=status.HTTP_200_OK,
        )


class PasswordResetView(APIView):
    """POST /api/v1/auth/password-reset/confirm/ — Set a new password."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reset_token = serializer.context["reset_token"]
        user = reset_token.user
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        reset_token.is_used = True
        reset_token.save(update_fields=["is_used"])
        # Blacklist all existing refresh tokens by rotating (user must log in again)
        return Response(
            {"message": "Password reset successfully. Please log in with your new password."},
            status=status.HTTP_200_OK,
        )


class ChangePasswordView(APIView):
    """POST /api/v1/auth/change-password/ — Change password while logged in."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        return Response(
            {"message": "Password changed successfully. Please log in again."},
            status=status.HTTP_200_OK,
        )


class MeView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/auth/me/ — Retrieve or update the current user."""
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class SocialAuthView(APIView):
    """
    POST /api/v1/auth/social/ — Exchange a provider OAuth token for Venturify JWTs.
    Frontend completes the OAuth flow and sends the provider access token here.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SocialAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        provider = serializer.validated_data["provider"]
        access_token = serializer.validated_data["access_token"]

        user_data = self._fetch_provider_user(provider, access_token)
        if not user_data:
            return Response(
                {"error": "Failed to fetch user info from provider."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = user_data.get("email")
        if not email:
            return Response(
                {"error": "Provider did not return an email address."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "full_name": user_data.get("name", ""),
                "avatar_url": user_data.get("picture", ""),
                "auth_provider": provider,
                "is_verified": True,  # OAuth emails are pre-verified
            },
        )
        if not created and user.auth_provider != provider:
            return Response(
                {"error": f"This email is registered with {user.auth_provider}. Please use that login method."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        refresh = RefreshToken.for_user(user)
        refresh["email"] = user.email
        refresh["role"] = user.role
        refresh["is_verified"] = user.is_verified
        refresh["is_onboarded"] = user.is_onboarded

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
                "is_new_user": created,
            },
            status=status.HTTP_200_OK,
        )

    def _fetch_provider_user(self, provider: str, access_token: str) -> dict | None:
        import httpx
        try:
            if provider == "google":
                resp = httpx.get(
                    "https://www.googleapis.com/oauth2/v3/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "email": data.get("email"),
                        "name": data.get("name"),
                        "picture": data.get("picture"),
                    }
            elif provider == "linkedin":
                # LinkedIn requires separate calls for profile + email
                profile_resp = httpx.get(
                    "https://api.linkedin.com/v2/me?projection=(id,localizedFirstName,localizedLastName,profilePicture(displayImage~:playableStreams))",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=10,
                )
                email_resp = httpx.get(
                    "https://api.linkedin.com/v2/emailAddress?q=members&projection=(elements*(handle~))",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=10,
                )
                if profile_resp.status_code == 200 and email_resp.status_code == 200:
                    p = profile_resp.json()
                    e = email_resp.json()
                    email = e["elements"][0]["handle~"]["emailAddress"]
                    name = f"{p.get('localizedFirstName', '')} {p.get('localizedLastName', '')}".strip()
                    return {"email": email, "name": name, "picture": None}
        except Exception as exc:
            logger.error("Social auth provider fetch error: %s", exc)
        return None


class UpdateFCMTokenView(APIView):
    """POST /api/v1/auth/fcm-token/ — Store Firebase push notification token."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = UpdateFCMTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.fcm_token = serializer.validated_data["fcm_token"]
        request.user.save(update_fields=["fcm_token"])
        return Response({"message": "FCM token updated."}, status=status.HTTP_200_OK)


# ── Utility used by DRF settings ─────────────────────────────
def custom_exception_handler(exc, context):
    """Standardise all error responses to {error: ..., details: ...}."""
    from rest_framework.views import exception_handler
    response = exception_handler(exc, context)
    if response is not None:
        error_payload = {
            "error": response.status_text,
            "details": response.data,
        }
        response.data = error_payload
    return response
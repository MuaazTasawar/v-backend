from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    ChangePasswordView,
    CustomTokenObtainPairView,
    LogoutView,
    MeView,
    PasswordResetView,
    RegisterView,
    RequestPasswordResetView,
    ResendVerificationEmailView,
    SocialAuthView,
    UpdateFCMTokenView,
    VerifyEmailView,
)

urlpatterns = [
    # Registration & login
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", CustomTokenObtainPairView.as_view(), name="auth-login"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("token/refresh/", TokenRefreshView.as_view(), name="auth-token-refresh"),

    # Email verification
    path("verify-email/", VerifyEmailView.as_view(), name="auth-verify-email"),
    path("resend-verification/", ResendVerificationEmailView.as_view(), name="auth-resend-verification"),

    # Password management
    path("password-reset/request/", RequestPasswordResetView.as_view(), name="auth-password-reset-request"),
    path("password-reset/confirm/", PasswordResetView.as_view(), name="auth-password-reset-confirm"),
    path("change-password/", ChangePasswordView.as_view(), name="auth-change-password"),

    # Current user
    path("me/", MeView.as_view(), name="auth-me"),

    # OAuth
    path("social/", SocialAuthView.as_view(), name="auth-social"),

    # Push notifications
    path("fcm-token/", UpdateFCMTokenView.as_view(), name="auth-fcm-token"),
]
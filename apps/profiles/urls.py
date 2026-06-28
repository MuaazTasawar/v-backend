from django.urls import path
from .views import (
    IndustryTagListView,
    FounderProfileView,
    FounderProfilePublicView,
    InvestorProfileView,
    InvestorProfilePublicView,
    CVUploadView,
    CVExtractionStatusView,
    IDDocumentUploadView,
    StripeConnectOnboardingView,
    StripeConnectCompleteView,
)

urlpatterns = [
    # Industry tags
    path("industries/", IndustryTagListView.as_view(), name="profile-industries"),

    # Founder
    path("founder/me/", FounderProfileView.as_view(), name="founder-profile-me"),
    path("founder/<uuid:user_id>/", FounderProfilePublicView.as_view(), name="founder-profile-public"),

    # Investor
    path("investor/me/", InvestorProfileView.as_view(), name="investor-profile-me"),
    path("investor/<uuid:user_id>/", InvestorProfilePublicView.as_view(), name="investor-profile-public"),

    # CV upload
    path("cv/upload/", CVUploadView.as_view(), name="cv-upload"),
    path("cv/status/<uuid:job_id>/", CVExtractionStatusView.as_view(), name="cv-status"),

    # Identity verification
    path("identity/upload/", IDDocumentUploadView.as_view(), name="identity-upload"),

    # Stripe Connect
    path("investor/stripe/onboard/", StripeConnectOnboardingView.as_view(), name="stripe-onboard"),
    path("investor/stripe/complete/", StripeConnectCompleteView.as_view(), name="stripe-complete"),
]
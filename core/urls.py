from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),

    # API v1
    path("api/v1/auth/", include("apps.auth_app.urls")),
    path("api/v1/profiles/", include("apps.profiles.urls")),
    path("api/v1/startups/", include("apps.startups.urls")),
    path("api/v1/matchmaking/", include("apps.matchmaking.urls")),
    path("api/v1/contracts/", include("apps.contracts.urls")),
    path("api/v1/financials/", include("apps.financials.urls")),
    path("api/v1/marketplace/", include("apps.marketplace.urls")),
    path("api/v1/notifications/", include("apps.notifications.urls")),

    # Social auth
    path("social/", include("social_django.urls", namespace="social")),

    # OpenAPI docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
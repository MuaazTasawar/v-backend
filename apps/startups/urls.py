from django.urls import path
from .views import (
    StartupListCreateView,
    StartupDetailView,
    JiraNotionConnectView,
    PitchSessionDetailView,
    PitchMessageView,
    GeneratedDocumentListView,
    RegenerateDocumentView,
    PoCDeploymentDetailView,
    PoCRedeployView,
    ProjectContextFileDetailView,
)

urlpatterns = [
    path("", StartupListCreateView.as_view(), name="startup-list-create"),
    path("<uuid:pk>/", StartupDetailView.as_view(), name="startup-detail"),
    path("<uuid:startup_id>/integrations/connect/", JiraNotionConnectView.as_view(), name="startup-integrations-connect"),

    path("<uuid:startup_id>/pitch-session/", PitchSessionDetailView.as_view(), name="pitch-session-detail"),
    path("<uuid:startup_id>/pitch-session/message/", PitchMessageView.as_view(), name="pitch-session-message"),

    path("<uuid:startup_id>/documents/", GeneratedDocumentListView.as_view(), name="generated-documents-list"),
    path("<uuid:startup_id>/documents/<str:doc_type>/regenerate/", RegenerateDocumentView.as_view(), name="document-regenerate"),

    path("<uuid:startup_id>/poc/", PoCDeploymentDetailView.as_view(), name="poc-detail"),
    path("<uuid:startup_id>/poc/redeploy/", PoCRedeployView.as_view(), name="poc-redeploy"),

    path("<uuid:startup_id>/context/", ProjectContextFileDetailView.as_view(), name="context-file-detail"),
]
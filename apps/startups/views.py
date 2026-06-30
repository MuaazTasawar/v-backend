import logging

from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auth_app.permissions import IsFounder, IsOwnerOrAdmin
from .models import (
    Startup,
    PitchSession,
    GeneratedDocument,
    PoCDeployment,
    ProjectContextFile,
)
from .serializers import (
    GeneratedDocumentSerializer,
    JiraNotionConnectSerializer,
    PitchMessageSerializer,
    PitchSessionSerializer,
    PoCDeploymentSerializer,
    ProjectContextFileSerializer,
    StartupCreateSerializer,
    StartupDetailSerializer,
    StartupListSerializer,
)
from .tasks import generate_startup_documents, generate_and_deploy_poc, sync_jira_notion_context

logger = logging.getLogger(__name__)


# ── Startup CRUD ───────────────────────────────────────────────────────────

class StartupListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/startups/             — List own startups (founder) or all active (any authenticated user).
    POST /api/v1/startups/             — Create a new draft startup.
    """
    permission_classes = [IsAuthenticated]
    filterset_fields = ["status", "funding_stage"]
    search_fields = ["name", "tagline"]

    def get_serializer_class(self):
        return StartupCreateSerializer if self.request.method == "POST" else StartupListSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_founder:
            return Startup.objects.filter(founder=user).prefetch_related("industries")
        # Investors and others see only active, listed startups
        return Startup.objects.filter(status=Startup.Status.ACTIVE).prefetch_related("industries")

    def perform_create(self, serializer):
        if not self.request.user.is_founder:
            raise PermissionError("Only founders can create startups.")
        startup = serializer.save(founder=self.request.user, status=Startup.Status.DRAFT)
        # Auto-create the pitch session
        PitchSession.objects.create(startup=startup, founder=self.request.user)
        # Auto-create the context file shell
        ProjectContextFile.objects.create(startup=startup)


class StartupDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/v1/startups/<id>/"""
    serializer_class = StartupDetailSerializer
    permission_classes = [IsAuthenticated]
    queryset = Startup.objects.all().prefetch_related("industries")

    def get_object(self):
        obj = super().get_object()
        user = self.request.user
        # Founders can only edit their own; others can only view active startups
        if self.request.method in ("PATCH", "PUT", "DELETE"):
            if obj.founder != user:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("You do not own this startup.")
        elif obj.status != Startup.Status.ACTIVE and obj.founder != user:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("This startup is not publicly visible.")
        return obj


class JiraNotionConnectView(APIView):
    """
    POST /api/v1/startups/<id>/integrations/connect/
    Founder connects Jira and/or Notion workspace for live progress tracking (Module 9/10).
    """
    permission_classes = [IsAuthenticated, IsFounder]

    def post(self, request, startup_id):
        startup = get_object_or_404(Startup, id=startup_id, founder=request.user)
        serializer = JiraNotionConnectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        for field in [
            "jira_workspace_url",
            "jira_project_key",
            "jira_access_token",
            "notion_workspace_id",
            "notion_access_token",
        ]:
            if field in data and data[field]:
                setattr(startup, field, data[field])
        startup.save()

        # Trigger initial sync
        sync_jira_notion_context.delay(str(startup.id))

        return Response(
            {"message": "Integrations connected. Initial sync started."},
            status=status.HTTP_202_ACCEPTED,
        )


# ── Pitch Session (conversational flow) ─────────────────────────────────────

class PitchSessionDetailView(generics.RetrieveAPIView):
    """GET /api/v1/startups/<id>/pitch-session/"""
    serializer_class = PitchSessionSerializer
    permission_classes = [IsAuthenticated, IsFounder]

    def get_object(self):
        startup = get_object_or_404(Startup, id=self.kwargs["startup_id"], founder=self.request.user)
        return get_object_or_404(PitchSession, startup=startup)


class PitchMessageView(APIView):
    """
    POST /api/v1/startups/<id>/pitch-session/message/
    Forwards a user message to the AI pitch service (FastAPI) and stores the exchange.
    The actual LLM call happens in ai_service; this view proxies and persists history.
    """
    permission_classes = [IsAuthenticated, IsFounder]

    def post(self, request, startup_id):
        import httpx
        from django.conf import settings
        from django.utils import timezone

        startup = get_object_or_404(Startup, id=startup_id, founder=request.user)
        session = get_object_or_404(PitchSession, startup=startup)

        serializer = PitchMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_message = serializer.validated_data["message"]

        # Append user message
        session.conversation_history.append({
            "role": "user",
            "content": user_message,
            "timestamp": timezone.now().isoformat(),
        })

        try:
            resp = httpx.post(
                f"{settings.AI_SERVICE_URL}/pitch/converse",
                json={
                    "startup_id": str(startup.id),
                    "conversation_history": session.conversation_history,
                    "current_phase": session.current_phase,
                    "pitch_context": startup.pitch_context,
                },
                headers={"X-Internal-Secret": settings.AI_SERVICE_SECRET},
                timeout=60,
            )
            resp.raise_for_status()
            ai_data = resp.json()
        except httpx.HTTPError as exc:
            logger.error("AI pitch service error: %s", exc)
            return Response(
                {"error": "Pitch assistant is temporarily unavailable."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Append assistant response
        session.conversation_history.append({
            "role": "assistant",
            "content": ai_data["reply"],
            "timestamp": timezone.now().isoformat(),
        })
        session.current_phase = ai_data.get("next_phase", session.current_phase)

        if ai_data.get("extracted_context"):
            startup.pitch_context.update(ai_data["extracted_context"])
            startup.save(update_fields=["pitch_context"])

        if ai_data.get("is_complete"):
            session.status = PitchSession.Status.COMPLETED
            startup.status = Startup.Status.ANALYZING
            startup.save(update_fields=["status"])
            # Kick off document generation + PoC deployment
            generate_startup_documents.delay(str(startup.id))
            generate_and_deploy_poc.delay(str(startup.id))

        session.save(update_fields=["conversation_history", "current_phase", "status"])

        return Response(
            {
                "reply": ai_data["reply"],
                "current_phase": session.current_phase,
                "is_complete": ai_data.get("is_complete", False),
            },
            status=status.HTTP_200_OK,
        )


# ── Generated Documents ──────────────────────────────────────────────────────

class GeneratedDocumentListView(generics.ListAPIView):
    """GET /api/v1/startups/<id>/documents/"""
    serializer_class = GeneratedDocumentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        startup = get_object_or_404(Startup, id=self.kwargs["startup_id"])
        return GeneratedDocument.objects.filter(startup=startup)


class RegenerateDocumentView(APIView):
    """POST /api/v1/startups/<id>/documents/<doc_type>/regenerate/"""
    permission_classes = [IsAuthenticated, IsFounder]

    def post(self, request, startup_id, doc_type):
        startup = get_object_or_404(Startup, id=startup_id, founder=request.user)
        valid_types = [c[0] for c in GeneratedDocument.DocumentType.choices]
        if doc_type not in valid_types:
            return Response({"error": "Invalid document type."}, status=status.HTTP_400_BAD_REQUEST)

        generate_startup_documents.delay(str(startup.id), document_types=[doc_type])
        return Response(
            {"message": f"Regenerating {doc_type}."},
            status=status.HTTP_202_ACCEPTED,
        )


# ── PoC Deployment ─────────────────────────────────────────────────────────

class PoCDeploymentDetailView(generics.RetrieveAPIView):
    """GET /api/v1/startups/<id>/poc/"""
    serializer_class = PoCDeploymentSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        startup = get_object_or_404(Startup, id=self.kwargs["startup_id"])
        return get_object_or_404(PoCDeployment, startup=startup)


class PoCRedeployView(APIView):
    """POST /api/v1/startups/<id>/poc/redeploy/"""
    permission_classes = [IsAuthenticated, IsFounder]

    def post(self, request, startup_id):
        startup = get_object_or_404(Startup, id=startup_id, founder=request.user)
        generate_and_deploy_poc.delay(str(startup.id))
        return Response({"message": "PoC redeployment started."}, status=status.HTTP_202_ACCEPTED)


# ── Project Context File ─────────────────────────────────────────────────────

class ProjectContextFileDetailView(generics.RetrieveAPIView):
    """GET /api/v1/startups/<id>/context/"""
    serializer_class = ProjectContextFileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        startup = get_object_or_404(Startup, id=self.kwargs["startup_id"])
        return get_object_or_404(ProjectContextFile, startup=startup)
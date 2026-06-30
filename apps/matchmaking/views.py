import logging

from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auth_app.permissions import IsInvestor, IsFounder
from apps.startups.models import Startup
from .models import MatchScore, SavedStartup, InterestSignal
from .serializers import (
    InterestSignalRespondSerializer,
    InterestSignalSerializer,
    MatchScoreSerializer,
    SavedStartupSerializer,
)
from .scoring import compute_match_score

logger = logging.getLogger(__name__)


class MatchedStartupsView(generics.ListAPIView):
    """
    GET /api/v1/matchmaking/matches/
    Returns startups ranked by compatibility score for the authenticated investor (BO-3).
    Computes scores on-demand for any active startup missing a cached score.
    """
    serializer_class = MatchScoreSerializer
    permission_classes = [IsAuthenticated, IsInvestor]

    def get_queryset(self):
        investor = self.request.user
        active_startups = Startup.objects.filter(status=Startup.Status.ACTIVE)

        existing_ids = set(
            MatchScore.objects.filter(investor=investor).values_list("startup_id", flat=True)
        )
        missing_startups = active_startups.exclude(id__in=existing_ids)

        for startup in missing_startups:
            score_data = compute_match_score(investor, startup)
            MatchScore.objects.update_or_create(
                investor=investor,
                startup=startup,
                defaults=score_data,
            )

        return MatchScore.objects.filter(investor=investor).select_related("startup")


class RecomputeMatchesView(APIView):
    """POST /api/v1/matchmaking/matches/recompute/ — Force refresh of all match scores."""
    permission_classes = [IsAuthenticated, IsInvestor]

    def post(self, request):
        investor = request.user
        active_startups = Startup.objects.filter(status=Startup.Status.ACTIVE)
        count = 0
        for startup in active_startups:
            score_data = compute_match_score(investor, startup)
            MatchScore.objects.update_or_create(
                investor=investor, startup=startup, defaults=score_data
            )
            count += 1
        return Response({"message": f"Recomputed {count} match scores."}, status=status.HTTP_200_OK)


class SavedStartupListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/v1/matchmaking/saved/"""
    serializer_class = SavedStartupSerializer
    permission_classes = [IsAuthenticated, IsInvestor]

    def get_queryset(self):
        return SavedStartup.objects.filter(investor=self.request.user).select_related("startup")


class SavedStartupDeleteView(generics.DestroyAPIView):
    """DELETE /api/v1/matchmaking/saved/<id>/"""
    permission_classes = [IsAuthenticated, IsInvestor]

    def get_queryset(self):
        return SavedStartup.objects.filter(investor=self.request.user)


class InterestSignalListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/matchmaking/interest/  — Founders see interest in their startups; investors see ones they sent.
    POST /api/v1/matchmaking/interest/  — Investor expresses interest in a startup.
    """
    serializer_class = InterestSignalSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_investor:
            return InterestSignal.objects.filter(investor=user).select_related("startup")
        elif user.is_founder:
            return InterestSignal.objects.filter(startup__founder=user).select_related("startup", "investor")
        return InterestSignal.objects.none()

    def perform_create(self, serializer):
        if not self.request.user.is_investor:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only investors can express interest.")
        serializer.save()


class InterestSignalRespondView(APIView):
    """POST /api/v1/matchmaking/interest/<id>/respond/ — Founder accepts/declines interest."""
    permission_classes = [IsAuthenticated, IsFounder]

    def post(self, request, signal_id):
        signal = get_object_or_404(
            InterestSignal, id=signal_id, startup__founder=request.user
        )
        serializer = InterestSignalRespondSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data["action"]

        signal.status = (
            InterestSignal.Status.ACCEPTED
            if action == "accept"
            else InterestSignal.Status.DECLINED
        )
        signal.save(update_fields=["status"])

        if action == "accept":
            signal.startup.status = Startup.Status.NEGOTIATING
            signal.startup.save(update_fields=["status"])
            # Chat room creation is handled in Phase 6/7 (Assisted Chat Mode)

        return Response(
            {"message": f"Interest signal {action}ed.", "status": signal.status},
            status=status.HTTP_200_OK,
        )
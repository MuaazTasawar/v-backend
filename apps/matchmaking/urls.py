from django.urls import path
from .views import (
    MatchedStartupsView,
    RecomputeMatchesView,
    SavedStartupListCreateView,
    SavedStartupDeleteView,
    InterestSignalListCreateView,
    InterestSignalRespondView,
)

urlpatterns = [
    path("matches/", MatchedStartupsView.as_view(), name="matchmaking-matches"),
    path("matches/recompute/", RecomputeMatchesView.as_view(), name="matchmaking-recompute"),

    path("saved/", SavedStartupListCreateView.as_view(), name="matchmaking-saved-list-create"),
    path("saved/<uuid:pk>/", SavedStartupDeleteView.as_view(), name="matchmaking-saved-delete"),

    path("interest/", InterestSignalListCreateView.as_view(), name="matchmaking-interest-list-create"),
    path("interest/<uuid:signal_id>/respond/", InterestSignalRespondView.as_view(), name="matchmaking-interest-respond"),
]
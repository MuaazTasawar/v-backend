from decimal import Decimal
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

from apps.profiles.models import IndustryTag, InvestorProfile
from apps.startups.models import Startup
from .models import MatchScore, SavedStartup, InterestSignal
from .scoring import compute_match_score

User = get_user_model()


def make_founder(**kwargs):
    defaults = dict(
        email="founder@test.com", full_name="Founder", password="StrongPass123!",
        role=User.Role.FOUNDER, is_verified=True,
    )
    defaults.update(kwargs)
    return User.objects.create_user(**defaults)


def make_investor(**kwargs):
    defaults = dict(
        email="investor@test.com", full_name="Investor", password="StrongPass123!",
        role=User.Role.INVESTOR, is_verified=True,
    )
    defaults.update(kwargs)
    return User.objects.create_user(**defaults)


class ScoringAlgorithmTests(APITestCase):
    def setUp(self):
        self.tag = IndustryTag.objects.create(name="FinTech", slug="fintech")
        self.founder = make_founder()
        self.investor = make_investor()
        self.investor_profile = InvestorProfile.objects.create(
            user=self.investor,
            preferred_stages=["seed"],
            min_ticket_size=10000,
            max_ticket_size=100000,
            risk_appetite="aggressive",
        )
        self.investor_profile.industries.add(self.tag)

        self.startup = Startup.objects.create(
            founder=self.founder,
            name="MatchCo",
            funding_stage="seed",
            funding_ask=50000,
            status=Startup.Status.ACTIVE,
        )
        self.startup.industries.add(self.tag)

    def test_perfect_match_scores_high(self):
        result = compute_match_score(self.investor, self.startup)
        self.assertGreaterEqual(result["overall_score"], Decimal("90"))

    def test_industry_mismatch_lowers_score(self):
        other_tag = IndustryTag.objects.create(name="AgriTech", slug="agritech")
        self.startup.industries.set([other_tag])
        result = compute_match_score(self.investor, self.startup)
        self.assertLess(result["industry_score"], Decimal("100"))

    def test_ticket_size_out_of_range(self):
        self.startup.funding_ask = 5000000
        self.startup.save()
        result = compute_match_score(self.investor, self.startup)
        self.assertLess(result["ticket_size_score"], Decimal("50"))


class MatchedStartupsViewTests(APITestCase):
    def setUp(self):
        self.founder = make_founder()
        self.investor = make_investor()
        InvestorProfile.objects.create(user=self.investor)
        self.startup = Startup.objects.create(
            founder=self.founder, name="VisibleCo", status=Startup.Status.ACTIVE
        )
        self.client.force_authenticate(user=self.investor)

    def test_matches_computed_on_demand(self):
        response = self.client.get(reverse("matchmaking-matches"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(MatchScore.objects.filter(investor=self.investor, startup=self.startup).exists())

    def test_founder_cannot_access_matches(self):
        self.client.force_authenticate(user=self.founder)
        response = self.client.get(reverse("matchmaking-matches"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class InterestSignalTests(APITestCase):
    def setUp(self):
        self.founder = make_founder()
        self.investor = make_investor()
        self.startup = Startup.objects.create(
            founder=self.founder, name="InterestCo", status=Startup.Status.ACTIVE
        )

    def test_investor_can_express_interest(self):
        self.client.force_authenticate(user=self.investor)
        response = self.client.post(reverse("matchmaking-interest-list-create"), {
            "startup_id": str(self.startup.id),
            "proposed_amount": 25000,
            "message": "Interested in your startup.",
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(InterestSignal.objects.filter(startup=self.startup, investor=self.investor).exists())

    def test_founder_can_accept_interest(self):
        signal = InterestSignal.objects.create(investor=self.investor, startup=self.startup)
        self.client.force_authenticate(user=self.founder)
        response = self.client.post(
            reverse("matchmaking-interest-respond", args=[signal.id]), {"action": "accept"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        signal.refresh_from_db()
        self.assertEqual(signal.status, InterestSignal.Status.ACCEPTED)
        self.startup.refresh_from_db()
        self.assertEqual(self.startup.status, Startup.Status.NEGOTIATING)

    def test_founder_can_decline_interest(self):
        signal = InterestSignal.objects.create(investor=self.investor, startup=self.startup)
        self.client.force_authenticate(user=self.founder)
        response = self.client.post(
            reverse("matchmaking-interest-respond", args=[signal.id]), {"action": "decline"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        signal.refresh_from_db()
        self.assertEqual(signal.status, InterestSignal.Status.DECLINED)
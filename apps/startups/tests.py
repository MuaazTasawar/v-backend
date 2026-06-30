from unittest.mock import patch
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from .models import Startup, PitchSession, ProjectContextFile

User = get_user_model()


def make_founder(**kwargs):
    defaults = dict(
        email="founder@test.com",
        full_name="Test Founder",
        password="StrongPass123!",
        role=User.Role.FOUNDER,
        is_verified=True,
    )
    defaults.update(kwargs)
    return User.objects.create_user(**defaults)


def make_investor(**kwargs):
    defaults = dict(
        email="investor@test.com",
        full_name="Test Investor",
        password="StrongPass123!",
        role=User.Role.INVESTOR,
        is_verified=True,
    )
    defaults.update(kwargs)
    return User.objects.create_user(**defaults)


class StartupCreationTests(APITestCase):
    def setUp(self):
        self.founder = make_founder()
        self.client.force_authenticate(user=self.founder)
        self.url = reverse("startup-list-create")

    def test_founder_can_create_startup(self):
        payload = {
            "name": "Venturify",
            "tagline": "AI-powered startup investment",
            "funding_stage": "seed",
            "funding_ask": 50000,
            "equity_offered_pct": 10,
        }
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        startup = Startup.objects.get(name="Venturify")
        self.assertEqual(startup.founder, self.founder)
        self.assertEqual(startup.status, Startup.Status.DRAFT)
        # Pitch session and context file should auto-create
        self.assertTrue(PitchSession.objects.filter(startup=startup).exists())
        self.assertTrue(ProjectContextFile.objects.filter(startup=startup).exists())

    def test_investor_cannot_create_startup(self):
        investor = make_investor()
        self.client.force_authenticate(user=investor)
        payload = {"name": "X", "funding_stage": "seed", "funding_ask": 1000, "equity_offered_pct": 5}
        response = self.client.post(self.url, payload)
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN, status.HTTP_500_INTERNAL_SERVER_ERROR])

    def test_invalid_equity_percentage(self):
        payload = {"name": "BadCo", "funding_stage": "seed", "funding_ask": 1000, "equity_offered_pct": 150}
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class StartupListVisibilityTests(APITestCase):
    def setUp(self):
        self.founder = make_founder()
        self.investor = make_investor()
        self.active_startup = Startup.objects.create(
            founder=self.founder, name="ActiveCo", status=Startup.Status.ACTIVE
        )
        self.draft_startup = Startup.objects.create(
            founder=self.founder, name="DraftCo", status=Startup.Status.DRAFT
        )
        self.url = reverse("startup-list-create")

    def test_founder_sees_own_drafts_and_active(self):
        self.client.force_authenticate(user=self.founder)
        response = self.client.get(self.url)
        names = [s["name"] for s in response.data["results"]]
        self.assertIn("ActiveCo", names)
        self.assertIn("DraftCo", names)

    def test_investor_sees_only_active(self):
        self.client.force_authenticate(user=self.investor)
        response = self.client.get(self.url)
        names = [s["name"] for s in response.data["results"]]
        self.assertIn("ActiveCo", names)
        self.assertNotIn("DraftCo", names)


class StartupDetailPermissionTests(APITestCase):
    def setUp(self):
        self.founder = make_founder()
        self.other_founder = make_founder(email="other@test.com")
        self.startup = Startup.objects.create(
            founder=self.founder, name="MyCo", status=Startup.Status.DRAFT
        )

    def test_owner_can_edit(self):
        self.client.force_authenticate(user=self.founder)
        response = self.client.patch(
            reverse("startup-detail", args=[self.startup.id]), {"tagline": "Updated"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_non_owner_cannot_edit(self):
        self.client.force_authenticate(user=self.other_founder)
        response = self.client.patch(
            reverse("startup-detail", args=[self.startup.id]), {"tagline": "Hacked"}
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class PitchMessageTests(APITestCase):
    def setUp(self):
        self.founder = make_founder()
        self.startup = Startup.objects.create(founder=self.founder, name="PitchCo")
        self.session = PitchSession.objects.create(startup=self.startup, founder=self.founder)
        self.client.force_authenticate(user=self.founder)
        self.url = reverse("pitch-session-message", args=[self.startup.id])

    @patch("apps.startups.views.httpx.post")
    def test_send_pitch_message(self, mock_post):
        mock_post.return_value.raise_for_status = lambda: None
        mock_post.return_value.json = lambda: {
            "reply": "Tell me more about your solution.",
            "next_phase": "solution",
            "is_complete": False,
            "extracted_context": {"problem": "Fragmented startup tooling"},
        }
        response = self.client.post(self.url, {"message": "We solve fragmented startup tooling."})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_phase, "solution")
        self.startup.refresh_from_db()
        self.assertIn("problem", self.startup.pitch_context)
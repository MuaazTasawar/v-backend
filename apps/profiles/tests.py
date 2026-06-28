from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from .models import FounderProfile, InvestorProfile, IndustryTag

User = get_user_model()


def make_founder(**kwargs):
    defaults = dict(
        email="founder@test.com",
        full_name="Test Founder",
        password="StrongPass123!",
        role=User.Role.FOUNDER,
        is_verified=True,
        is_active=True,
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
        is_active=True,
    )
    defaults.update(kwargs)
    return User.objects.create_user(**defaults)


class FounderProfileTests(APITestCase):
    def setUp(self):
        self.founder = make_founder()
        self.client.force_authenticate(user=self.founder)
        self.url = reverse("founder-profile-me")

    def test_get_profile_creates_if_missing(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(FounderProfile.objects.filter(user=self.founder).exists())

    def test_patch_bio_and_location(self):
        response = self.client.patch(self.url, {"bio": "I build AI tools.", "location": "Islamabad"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.founder.founder_profile.refresh_from_db()
        self.assertEqual(self.founder.founder_profile.bio, "I build AI tools.")

    def test_patch_invalid_education(self):
        response = self.client.patch(self.url, {"education": [{"institution": "COMSATS"}]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_valid_education(self):
        payload = {
            "education": [
                {"institution": "COMSATS", "degree": "BS CS", "field": "Computer Science", "year": 2027}
            ]
        }
        response = self.client.patch(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_investor_cannot_access_founder_profile(self):
        investor = make_investor(email="inv2@test.com")
        self.client.force_authenticate(user=investor)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_onboarding_step_advances(self):
        tag = IndustryTag.objects.create(name="FinTech", slug="fintech")
        self.client.patch(self.url, {
            "bio": "Builder",
            "location": "Karachi",
            "education": [{"institution": "FAST", "degree": "BSCS"}],
            "work_history": [{"company": "Arbisoft", "role": "Dev"}],
            "skills": ["Python"],
            "industry_ids": [str(tag.id)],
        }, format="json")
        self.founder.founder_profile.refresh_from_db()
        self.assertGreaterEqual(self.founder.founder_profile.onboarding_step, 4)
        self.founder.refresh_from_db()
        self.assertTrue(self.founder.is_onboarded)


class InvestorProfileTests(APITestCase):
    def setUp(self):
        self.investor = make_investor()
        self.client.force_authenticate(user=self.investor)
        self.url = reverse("investor-profile-me")

    def test_get_profile_creates_if_missing(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(InvestorProfile.objects.filter(user=self.investor).exists())

    def test_patch_ticket_size(self):
        response = self.client.patch(
            self.url,
            {"min_ticket_size": 10000, "max_ticket_size": 50000},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_invalid_ticket_size_order(self):
        response = self.client.patch(
            self.url,
            {"min_ticket_size": 100000, "max_ticket_size": 5000},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_founder_cannot_access_investor_profile(self):
        founder = make_founder(email="f2@test.com")
        self.client.force_authenticate(user=founder)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_onboarding_marks_user_onboarded(self):
        tag = IndustryTag.objects.create(name="HealthTech", slug="healthtech")
        self.client.patch(self.url, {
            "bio": "I invest in early stage.",
            "location": "Lahore",
            "investor_type": "angel",
            "preferred_stages": ["seed"],
            "industry_ids": [str(tag.id)],
        }, format="json")
        self.investor.refresh_from_db()
        self.assertTrue(self.investor.is_onboarded)


class IndustryTagTests(APITestCase):
    def setUp(self):
        self.user = make_founder()
        self.client.force_authenticate(user=self.user)
        IndustryTag.objects.create(name="AgriTech", slug="agritech")
        IndustryTag.objects.create(name="EdTech", slug="edtech")

    def test_list_industry_tags(self):
        response = self.client.get(reverse("profile-industries"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data["results"]), 2)
import uuid
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

from .models import EmailVerificationToken, PasswordResetToken

User = get_user_model()


class RegistrationTests(APITestCase):
    def setUp(self):
        self.url = reverse("auth-register")
        self.valid_payload = {
            "email": "founder@test.com",
            "full_name": "Test Founder",
            "role": "founder",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        }

    def test_register_success(self):
        response = self.client.post(self.url, self.valid_payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("user", response.data)
        user = User.objects.get(email="founder@test.com")
        self.assertFalse(user.is_verified)

    def test_register_password_mismatch(self):
        payload = {**self.valid_payload, "password_confirm": "WrongPass123!"}
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_duplicate_email(self):
        self.client.post(self.url, self.valid_payload)
        response = self.client.post(self.url, self.valid_payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_admin_role_rejected(self):
        payload = {**self.valid_payload, "role": "admin"}
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class LoginTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="login@test.com",
            full_name="Login User",
            password="StrongPass123!",
            role=User.Role.INVESTOR,
            is_verified=True,
        )
        self.url = reverse("auth-login")

    def test_login_success(self):
        response = self.client.post(
            self.url, {"email": "login@test.com", "password": "StrongPass123!"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["role"], "investor")

    def test_login_wrong_password(self):
        response = self.client.post(
            self.url, {"email": "login@test.com", "password": "WrongPassword"}
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_nonexistent_user(self):
        response = self.client.post(
            self.url, {"email": "nobody@test.com", "password": "AnyPass123!"}
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class EmailVerificationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="verify@test.com",
            full_name="Verify User",
            password="StrongPass123!",
        )
        self.verification = EmailVerificationToken.objects.create(
            user=self.user,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        self.url = reverse("auth-verify-email")

    def test_verify_email_success(self):
        response = self.client.post(self.url, {"token": str(self.verification.token)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_verified)

    def test_verify_email_invalid_token(self):
        response = self.client.post(self.url, {"token": str(uuid.uuid4())})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_email_expired_token(self):
        self.verification.expires_at = timezone.now() - timedelta(hours=1)
        self.verification.save()
        response = self.client.post(self.url, {"token": str(self.verification.token)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class MeViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="me@test.com",
            full_name="Me User",
            password="StrongPass123!",
            is_verified=True,
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse("auth-me")

    def test_get_me(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "me@test.com")

    def test_patch_me_full_name(self):
        response = self.client.patch(self.url, {"full_name": "Updated Name"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["full_name"], "Updated Name")

    def test_me_unauthenticated(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class LogoutTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="logout@test.com",
            full_name="Logout User",
            password="StrongPass123!",
            is_verified=True,
        )
        login_resp = self.client.post(
            reverse("auth-login"),
            {"email": "logout@test.com", "password": "StrongPass123!"},
        )
        self.refresh_token = login_resp.data["refresh"]
        self.client.force_authenticate(user=self.user)
        self.url = reverse("auth-logout")

    def test_logout_success(self):
        response = self.client.post(self.url, {"refresh": self.refresh_token})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_logout_no_token(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
from unittest.mock import patch
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

from apps.startups.models import Startup
from .models import Negotiation, Contract, Milestone
from .state_machine import transition_contract, can_transition, InvalidTransitionError

User = get_user_model()


def make_founder(**kwargs):
    defaults = dict(email="founder@test.com", full_name="Founder", password="StrongPass123!", role=User.Role.FOUNDER, is_verified=True)
    defaults.update(kwargs)
    return User.objects.create_user(**defaults)


def make_investor(**kwargs):
    defaults = dict(email="investor@test.com", full_name="Investor", password="StrongPass123!", role=User.Role.INVESTOR, is_verified=True)
    defaults.update(kwargs)
    return User.objects.create_user(**defaults)


class StateMachineTests(APITestCase):
    def setUp(self):
        founder = make_founder()
        investor = make_investor()
        startup = Startup.objects.create(founder=founder, name="StateCo")
        negotiation = Negotiation.objects.create(startup=startup, founder=founder, investor=investor)
        self.contract = Contract.objects.create(
            negotiation=negotiation, startup=startup, founder=founder, investor=investor
        )

    def test_valid_transition(self):
        self.assertTrue(can_transition("drafting", "drafted"))

    def test_invalid_transition(self):
        self.assertFalse(can_transition("drafting", "active"))

    def test_transition_contract_updates_state_and_logs(self):
        transition_contract(self.contract, to_state="drafted", reason="Test")
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.state, "drafted")
        self.assertTrue(self.contract.state_transitions.filter(to_state="drafted").exists())

    def test_invalid_transition_raises(self):
        with self.assertRaises(InvalidTransitionError):
            transition_contract(self.contract, to_state="active", reason="Skip ahead illegally")

    def test_voiding_sets_reason(self):
        transition_contract(self.contract, to_state="voided", reason="Deal fell through")
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.state, "voided")
        self.assertEqual(self.contract.voided_reason, "Deal fell through")


class ContractPermissionTests(APITestCase):
    def setUp(self):
        self.founder = make_founder()
        self.investor = make_investor()
        self.outsider = make_founder(email="outsider@test.com")
        startup = Startup.objects.create(founder=self.founder, name="PermCo")
        negotiation = Negotiation.objects.create(startup=startup, founder=self.founder, investor=self.investor)
        self.contract = Contract.objects.create(
            negotiation=negotiation, startup=startup, founder=self.founder, investor=self.investor
        )

    def test_founder_can_view_contract(self):
        self.client.force_authenticate(user=self.founder)
        response = self.client.get(reverse("contract-detail", args=[self.contract.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_investor_can_view_contract(self):
        self.client.force_authenticate(user=self.investor)
        response = self.client.get(reverse("contract-detail", args=[self.contract.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_outsider_cannot_view_contract(self):
        self.client.force_authenticate(user=self.outsider)
        response = self.client.get(reverse("contract-detail", args=[self.contract.id]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class VoidContractTests(APITestCase):
    def setUp(self):
        self.founder = make_founder()
        self.investor = make_investor()
        startup = Startup.objects.create(founder=self.founder, name="VoidCo")
        negotiation = Negotiation.objects.create(startup=startup, founder=self.founder, investor=self.investor)
        self.contract = Contract.objects.create(
            negotiation=negotiation, startup=startup, founder=self.founder, investor=self.investor
        )

    def test_founder_can_void_draft_contract(self):
        self.client.force_authenticate(user=self.founder)
        response = self.client.post(
            reverse("contract-void", args=[self.contract.id]), {"reason": "Changed our minds."}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.state, "voided")

    def test_cannot_void_active_contract(self):
        self.contract.state = Contract.State.ACTIVE
        self.contract.save()
        self.client.force_authenticate(user=self.founder)
        response = self.client.post(
            reverse("contract-void", args=[self.contract.id]), {"reason": "Too late."}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class MilestoneWorkflowTests(APITestCase):
    def setUp(self):
        self.founder = make_founder()
        self.investor = make_investor()
        startup = Startup.objects.create(founder=self.founder, name="MilestoneCo")
        negotiation = Negotiation.objects.create(startup=startup, founder=self.founder, investor=self.investor)
        self.contract = Contract.objects.create(
            negotiation=negotiation, startup=startup, founder=self.founder, investor=self.investor,
            payment_structure="phased",
        )
        self.milestone = Milestone.objects.create(
            contract=self.contract, sequence=1, description="MVP launch", deadline_days=30, release_pct=50
        )

    def test_founder_can_submit_milestone(self):
        self.client.force_authenticate(user=self.founder)
        response = self.client.post(
            reverse("milestone-submit", args=[self.milestone.id]), {"submission_notes": "MVP is live."}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.status, Milestone.Status.SUBMITTED)

    @patch("apps.contracts.views.release_milestone_funds.delay")
    def test_investor_can_approve_milestone(self, mock_release):
        self.milestone.status = Milestone.Status.SUBMITTED
        self.milestone.save()
        self.client.force_authenticate(user=self.investor)
        response = self.client.post(reverse("milestone-approve", args=[self.milestone.id]))
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.status, Milestone.Status.APPROVED)
        mock_release.assert_called_once()

    def test_investor_can_dispute_milestone(self):
        self.milestone.status = Milestone.Status.SUBMITTED
        self.milestone.save()
        self.client.force_authenticate(user=self.investor)
        response = self.client.post(reverse("milestone-dispute", args=[self.milestone.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.status, Milestone.Status.DISPUTED)

    def test_cannot_approve_unsubmitted_milestone(self):
        self.client.force_authenticate(user=self.investor)
        response = self.client.post(reverse("milestone-approve", args=[self.milestone.id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
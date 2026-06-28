from rest_framework.permissions import BasePermission
from django.contrib.auth import get_user_model

User = get_user_model()


class IsFounder(BasePermission):
    """Allows access only to users with the Founder role."""
    message = "Only founders can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.FOUNDER
        )


class IsInvestor(BasePermission):
    """Allows access only to users with the Investor role."""
    message = "Only investors can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.INVESTOR
        )


class IsAutomationEngineer(BasePermission):
    """Allows access only to Automation Engineers."""
    message = "Only automation engineers can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.AUTOMATION_ENGINEER
        )


class IsFounderOrInvestor(BasePermission):
    """Allows access to both founders and investors."""
    message = "Only founders or investors can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in (User.Role.FOUNDER, User.Role.INVESTOR)
        )


class IsVerified(BasePermission):
    """Requires the user's email to be verified."""
    message = "Email verification is required."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_verified
        )


class IsOnboarded(BasePermission):
    """Requires the user to have completed onboarding."""
    message = "Please complete onboarding before accessing this resource."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_onboarded
        )


class IsOwnerOrAdmin(BasePermission):
    """Object-level: only the owner of the object or an admin can access it."""
    message = "You do not have permission to access this resource."

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        owner = getattr(obj, "user", None) or getattr(obj, "owner", None)
        return owner == request.user
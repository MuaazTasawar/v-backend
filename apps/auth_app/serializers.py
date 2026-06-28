from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from datetime import timedelta
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import EmailVerificationToken, PasswordResetToken

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password]
    )
    password_confirm = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ["email", "full_name", "role", "password", "password_confirm"]

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password": "Passwords do not match."})
        if attrs.get("role") == User.Role.ADMIN:
            raise serializers.ValidationError({"role": "Cannot self-register as admin."})
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.auth_provider = User.AuthProvider.LOCAL
        user.save()
        # Create email verification token
        EmailVerificationToken.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        return user


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "full_name",
            "role",
            "auth_provider",
            "is_verified",
            "is_onboarded",
            "avatar_url",
            "date_joined",
        ]
        read_only_fields = [
            "id",
            "email",
            "auth_provider",
            "is_verified",
            "date_joined",
        ]


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        token["role"] = user.role
        token["is_verified"] = user.is_verified
        token["is_onboarded"] = user.is_onboarded
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user
        data["user"] = UserSerializer(user).data
        return data


class VerifyEmailSerializer(serializers.Serializer):
    token = serializers.UUIDField()

    def validate_token(self, value):
        try:
            verification = EmailVerificationToken.objects.select_related("user").get(
                token=value
            )
        except EmailVerificationToken.DoesNotExist:
            raise serializers.ValidationError("Invalid or expired verification token.")
        if not verification.is_valid():
            raise serializers.ValidationError("Verification token has expired.")
        self.context["verification"] = verification
        return value


class RequestPasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        # Always return success to avoid email enumeration
        return value


class PasswordResetSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    new_password = serializers.CharField(validators=[validate_password])
    new_password_confirm = serializers.CharField()

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password": "Passwords do not match."}
            )
        try:
            reset_token = PasswordResetToken.objects.select_related("user").get(
                token=attrs["token"]
            )
        except PasswordResetToken.DoesNotExist:
            raise serializers.ValidationError({"token": "Invalid or expired token."})
        if not reset_token.is_valid():
            raise serializers.ValidationError({"token": "Token has expired or been used."})
        self.context["reset_token"] = reset_token
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField()
    new_password = serializers.CharField(validators=[validate_password])
    new_password_confirm = serializers.CharField()

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password": "Passwords do not match."}
            )
        return attrs


class SocialAuthSerializer(serializers.Serializer):
    """Receives the OAuth access token from the frontend and returns JWT."""
    provider = serializers.ChoiceField(choices=["google", "linkedin"])
    access_token = serializers.CharField()


class UpdateFCMTokenSerializer(serializers.Serializer):
    fcm_token = serializers.CharField()
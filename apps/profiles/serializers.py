from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import FounderProfile, InvestorProfile, IndustryTag, CVExtractionJob

User = get_user_model()


class IndustryTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = IndustryTag
        fields = ["id", "name", "slug"]


class FounderProfileSerializer(serializers.ModelSerializer):
    industries = IndustryTagSerializer(many=True, read_only=True)
    industry_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=IndustryTag.objects.all(),
        write_only=True,
        source="industries",
        required=False,
    )
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_full_name = serializers.CharField(source="user.full_name", read_only=True)
    is_identity_verified = serializers.BooleanField(read_only=True)
    onboarding_step = serializers.IntegerField(read_only=True)

    class Meta:
        model = FounderProfile
        fields = [
            "id",
            "user_email",
            "user_full_name",
            "bio",
            "location",
            "website",
            "linkedin_url",
            "twitter_url",
            "experience_level",
            "years_of_experience",
            "education",
            "work_history",
            "skills",
            "industries",
            "industry_ids",
            "cv_url",
            "cv_extracted_text",
            "is_identity_verified",
            "onboarding_step",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user_email",
            "user_full_name",
            "cv_url",
            "cv_extracted_text",
            "is_identity_verified",
            "onboarding_step",
            "created_at",
            "updated_at",
        ]

    def validate_education(self, value):
        required_keys = {"institution", "degree"}
        for entry in value:
            if not required_keys.issubset(entry.keys()):
                raise serializers.ValidationError(
                    "Each education entry must have 'institution' and 'degree'."
                )
        return value

    def validate_work_history(self, value):
        required_keys = {"company", "role"}
        for entry in value:
            if not required_keys.issubset(entry.keys()):
                raise serializers.ValidationError(
                    "Each work history entry must have 'company' and 'role'."
                )
        return value


class InvestorProfileSerializer(serializers.ModelSerializer):
    industries = IndustryTagSerializer(many=True, read_only=True)
    industry_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=IndustryTag.objects.all(),
        write_only=True,
        source="industries",
        required=False,
    )
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_full_name = serializers.CharField(source="user.full_name", read_only=True)
    is_identity_verified = serializers.BooleanField(read_only=True)
    onboarding_step = serializers.IntegerField(read_only=True)

    class Meta:
        model = InvestorProfile
        fields = [
            "id",
            "user_email",
            "user_full_name",
            "bio",
            "firm_name",
            "location",
            "website",
            "linkedin_url",
            "investor_type",
            "preferred_stages",
            "industries",
            "industry_ids",
            "min_ticket_size",
            "max_ticket_size",
            "risk_appetite",
            "portfolio_companies",
            "total_investments_made",
            "stripe_account_id",
            "stripe_onboarding_complete",
            "is_identity_verified",
            "onboarding_step",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user_email",
            "user_full_name",
            "total_investments_made",
            "stripe_account_id",
            "stripe_onboarding_complete",
            "is_identity_verified",
            "onboarding_step",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        min_t = attrs.get("min_ticket_size")
        max_t = attrs.get("max_ticket_size")
        if min_t and max_t and min_t > max_t:
            raise serializers.ValidationError(
                {"min_ticket_size": "Minimum ticket size cannot exceed maximum."}
            )
        return attrs


class CVUploadSerializer(serializers.Serializer):
    cv_file = serializers.FileField()

    def validate_cv_file(self, value):
        allowed_types = [
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ]
        if value.content_type not in allowed_types:
            raise serializers.ValidationError(
                "Only PDF and Word documents are accepted."
            )
        max_size_mb = 10
        if value.size > max_size_mb * 1024 * 1024:
            raise serializers.ValidationError(
                f"CV file must be under {max_size_mb}MB."
            )
        return value


class IDDocumentUploadSerializer(serializers.Serializer):
    id_document = serializers.ImageField()

    def validate_id_document(self, value):
        max_size_mb = 5
        if value.size > max_size_mb * 1024 * 1024:
            raise serializers.ValidationError(
                f"ID document must be under {max_size_mb}MB."
            )
        return value


class OnboardingStepSerializer(serializers.Serializer):
    """Used to manually advance the onboarding step after frontend confirmation."""
    step = serializers.IntegerField(min_value=0, max_value=10)


class CVExtractionJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = CVExtractionJob
        fields = ["id", "status", "extracted_text", "error_message", "created_at"]
        read_only_fields = fields
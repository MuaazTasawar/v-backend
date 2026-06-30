from django.urls import path
from .views import (
    NegotiationListView,
    NegotiationDetailView,
    ProcessNegotiationMessageView,
    ContractListView,
    ContractDetailView,
    ContractHistoryView,
    RequestContractRevisionView,
    ApproveContractView,
    SendForSignatureView,
    VoidContractView,
    MilestoneListView,
    MilestoneSubmitView,
    MilestoneApproveView,
    MilestoneDisputeView,
)

urlpatterns = [
    path("negotiations/", NegotiationListView.as_view(), name="negotiation-list"),
    path("negotiations/<uuid:pk>/", NegotiationDetailView.as_view(), name="negotiation-detail"),
    path(
        "negotiations/<uuid:negotiation_id>/process-message/",
        ProcessNegotiationMessageView.as_view(),
        name="negotiation-process-message",
    ),

    path("", ContractListView.as_view(), name="contract-list"),
    path("<uuid:pk>/", ContractDetailView.as_view(), name="contract-detail"),
    path("<uuid:contract_id>/history/", ContractHistoryView.as_view(), name="contract-history"),
    path("<uuid:contract_id>/request-revision/", RequestContractRevisionView.as_view(), name="contract-request-revision"),
    path("<uuid:contract_id>/approve/", ApproveContractView.as_view(), name="contract-approve"),
    path("<uuid:contract_id>/send-for-signature/", SendForSignatureView.as_view(), name="contract-send-for-signature"),
    path("<uuid:contract_id>/void/", VoidContractView.as_view(), name="contract-void"),

    path("<uuid:contract_id>/milestones/", MilestoneListView.as_view(), name="milestone-list"),
    path("milestones/<uuid:milestone_id>/submit/", MilestoneSubmitView.as_view(), name="milestone-submit"),
    path("milestones/<uuid:milestone_id>/approve/", MilestoneApproveView.as_view(), name="milestone-approve"),
    path("milestones/<uuid:milestone_id>/dispute/", MilestoneDisputeView.as_view(), name="milestone-dispute"),
]
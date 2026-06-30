"""
Shared, cross-app document utility tasks. Module-specific document
generation orchestration lives in apps/startups/tasks.py (Phase 3) and
calls into the AI microservice directly; this module holds generic
document maintenance tasks reusable across contracts, financials, etc.
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def cleanup_stale_generated_documents(self):
    """
    Periodic housekeeping task: re-flags GeneratedDocument rows stuck in
    'generating' status for more than 30 minutes as 'failed' so the UI
    doesn't show an indefinite spinner. Scheduled via Celery Beat.
    """
    from datetime import timedelta
    from django.utils import timezone
    from apps.startups.models import GeneratedDocument

    cutoff = timezone.now() - timedelta(minutes=30)
    stale_qs = GeneratedDocument.objects.filter(
        status=GeneratedDocument.Status.GENERATING,
        updated_at__lt=cutoff,
    )
    count = stale_qs.update(
        status=GeneratedDocument.Status.FAILED,
        error_message="Generation timed out after 30 minutes.",
    )
    if count:
        logger.warning("Marked %d stale generated documents as failed.", count)
    return count


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def cleanup_stale_poc_deployments(self):
    """Same housekeeping pattern for PoC deployments stuck mid-generation."""
    from datetime import timedelta
    from django.utils import timezone
    from apps.startups.models import PoCDeployment

    cutoff = timezone.now() - timedelta(minutes=30)
    stale_qs = PoCDeployment.objects.filter(
        status__in=[PoCDeployment.Status.GENERATING, PoCDeployment.Status.DEPLOYING],
        updated_at__lt=cutoff,
    )
    count = stale_qs.update(
        status=PoCDeployment.Status.FAILED,
        error_message="PoC deployment timed out after 30 minutes.",
    )
    if count:
        logger.warning("Marked %d stale PoC deployments as failed.", count)
    return count
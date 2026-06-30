import logging

import httpx
from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def generate_startup_documents(self, startup_id: str, document_types: list[str] | None = None):
    """
    Calls the AI microservice to generate feasibility report, pitch deck,
    proposal, and executive summary from the pitch context.
    """
    from .models import Startup, GeneratedDocument

    try:
        startup = Startup.objects.get(id=startup_id)
    except Startup.DoesNotExist:
        logger.error("Startup %s not found for document generation.", startup_id)
        return

    types_to_generate = document_types or [
        GeneratedDocument.DocumentType.FEASIBILITY_REPORT,
        GeneratedDocument.DocumentType.PITCH_DECK,
        GeneratedDocument.DocumentType.PROPOSAL,
        GeneratedDocument.DocumentType.EXECUTIVE_SUMMARY,
    ]

    for doc_type in types_to_generate:
        doc, _ = GeneratedDocument.objects.get_or_create(
            startup=startup, document_type=doc_type
        )
        doc.status = GeneratedDocument.Status.GENERATING
        doc.save(update_fields=["status"])

        try:
            resp = httpx.post(
                f"{settings.AI_SERVICE_URL}/pitch/generate-document",
                json={
                    "startup_id": str(startup.id),
                    "document_type": doc_type,
                    "pitch_context": startup.pitch_context,
                },
                headers={"X-Internal-Secret": settings.AI_SERVICE_SECRET},
                timeout=180,
            )
            resp.raise_for_status()
            result = resp.json()

            doc.file_url = result.get("file_url")
            doc.content_json = result.get("content_json", {})
            doc.status = GeneratedDocument.Status.READY
            doc.save(update_fields=["file_url", "content_json", "status"])

        except httpx.HTTPError as exc:
            logger.error("Document generation failed for %s/%s: %s", startup_id, doc_type, exc)
            doc.status = GeneratedDocument.Status.FAILED
            doc.error_message = str(exc)[:1000]
            doc.save(update_fields=["status", "error_message"])

    # Once documents are ready, move startup to ACTIVE so it appears in marketplace
    startup.status = startup.Status.ACTIVE
    startup.save(update_fields=["status"])

    # Index the context for the RAG advisory chatbot
    index_startup_context.delay(startup_id)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def generate_and_deploy_poc(self, startup_id: str):
    """Calls the AI microservice to generate and deploy a static PoC website."""
    from .models import Startup, PoCDeployment

    try:
        startup = Startup.objects.get(id=startup_id)
    except Startup.DoesNotExist:
        logger.error("Startup %s not found for PoC generation.", startup_id)
        return

    poc, _ = PoCDeployment.objects.get_or_create(startup=startup)
    poc.status = PoCDeployment.Status.GENERATING
    poc.save(update_fields=["status"])

    try:
        resp = httpx.post(
            f"{settings.AI_SERVICE_URL}/pitch/generate-poc",
            json={
                "startup_id": str(startup.id),
                "startup_name": startup.name,
                "pitch_context": startup.pitch_context,
            },
            headers={"X-Internal-Secret": settings.AI_SERVICE_SECRET},
            timeout=240,
        )
        resp.raise_for_status()
        result = resp.json()

        poc.status = PoCDeployment.Status.LIVE
        poc.live_url = result.get("live_url")
        poc.s3_bucket_path = result.get("s3_bucket_path", "")
        poc.generated_html = result.get("generated_html", "")[:50000]
        poc.save(update_fields=["status", "live_url", "s3_bucket_path", "generated_html"])

    except httpx.HTTPError as exc:
        logger.error("PoC generation failed for %s: %s", startup_id, exc)
        poc.status = PoCDeployment.Status.FAILED
        poc.error_message = str(exc)[:1000]
        poc.save(update_fields=["status", "error_message"])
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def sync_jira_notion_context(self, startup_id: str):
    """Initial + periodic sync of Jira sprint data and Notion page statuses (Module 9/10)."""
    from .models import Startup, ProjectContextFile

    try:
        startup = Startup.objects.get(id=startup_id)
    except Startup.DoesNotExist:
        return

    try:
        resp = httpx.post(
            f"{settings.AI_SERVICE_URL}/investor-panel/sync-workspace",
            json={
                "startup_id": str(startup.id),
                "jira_workspace_url": startup.jira_workspace_url,
                "jira_project_key": startup.jira_project_key,
                "jira_access_token": startup.jira_access_token,
                "notion_workspace_id": startup.notion_workspace_id,
                "notion_access_token": startup.notion_access_token,
            },
            headers={"X-Internal-Secret": settings.AI_SERVICE_SECRET},
            timeout=60,
        )
        resp.raise_for_status()
        result = resp.json()

        context_file, _ = ProjectContextFile.objects.get_or_create(startup=startup)
        context_file.content["workspace_sync"] = result.get("sync_data", {})
        context_file.save(update_fields=["content"])

    except httpx.HTTPError as exc:
        logger.error("Workspace sync failed for %s: %s", startup_id, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def index_startup_context(self, startup_id: str):
    """Pushes the consolidated startup context into ChromaDB for RAG retrieval."""
    from .models import Startup, ProjectContextFile, GeneratedDocument

    try:
        startup = Startup.objects.get(id=startup_id)
        context_file = ProjectContextFile.objects.get(startup=startup)
    except (Startup.DoesNotExist, ProjectContextFile.DoesNotExist):
        logger.error("Cannot index context for missing startup/context %s", startup_id)
        return

    documents = list(
        GeneratedDocument.objects.filter(
            startup=startup, status=GeneratedDocument.Status.READY
        ).values("document_type", "content_json")
    )

    try:
        resp = httpx.post(
            f"{settings.AI_SERVICE_URL}/advisory/index-startup",
            json={
                "startup_id": str(startup.id),
                "pitch_context": startup.pitch_context,
                "generated_documents": documents,
            },
            headers={"X-Internal-Secret": settings.AI_SERVICE_SECRET},
            timeout=120,
        )
        resp.raise_for_status()
        result = resp.json()

        context_file.chroma_collection_name = result.get("collection_name", "")
        context_file.is_indexed = True
        from django.utils import timezone
        context_file.indexed_at = timezone.now()
        context_file.save(update_fields=["chroma_collection_name", "is_indexed", "indexed_at"])

    except httpx.HTTPError as exc:
        logger.error("Context indexing failed for %s: %s", startup_id, exc)
        raise self.retry(exc=exc)
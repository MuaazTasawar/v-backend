import io
import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


def upload_file_to_s3(file_content: bytes, s3_key: str, content_type: str) -> str:
    """
    Synchronous helper — uploads bytes to S3 and returns the object URL.
    Used directly (not as a Celery task) for small, security-critical uploads.
    """
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
    )
    s3_client.put_object(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
        Key=s3_key,
        Body=file_content,
        ContentType=content_type,
        ServerSideEncryption="AES256",
    )
    return f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{s3_key}"


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def extract_cv_text(
    self,
    job_id: str,
    user_id: str,
    file_content: bytes,
    file_name: str,
    content_type: str,
    s3_key: str,
):
    """
    Celery task:
    1. Upload CV to S3.
    2. Extract text from PDF or DOCX.
    3. Map extracted text back to the FounderProfile.
    4. Update CVExtractionJob status.
    """
    from .models import CVExtractionJob, FounderProfile

    try:
        job = CVExtractionJob.objects.get(id=job_id)
        job.status = CVExtractionJob.Status.PROCESSING
        job.save(update_fields=["status"])

        # Step 1: Upload to S3
        s3_url = upload_file_to_s3(file_content, s3_key, content_type)

        # Step 2: Extract text
        extracted_text = _extract_text(file_content, content_type, file_name)

        # Step 3: Save to profile
        profile, _ = FounderProfile.objects.get_or_create(user_id=user_id)
        profile.cv_url = s3_url
        profile.cv_extracted_text = extracted_text
        profile.save(update_fields=["cv_url", "cv_extracted_text"])

        # Step 4: Mark job done
        job.status = CVExtractionJob.Status.DONE
        job.extracted_text = extracted_text
        job.save(update_fields=["status", "extracted_text"])

        logger.info("CV extraction complete for user %s", user_id)

    except CVExtractionJob.DoesNotExist:
        logger.error("CVExtractionJob %s not found", job_id)
    except (BotoCoreError, ClientError) as exc:
        logger.error("S3 upload failed for job %s: %s", job_id, exc)
        _mark_job_failed(job_id, str(exc))
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.error("CV extraction failed for job %s: %s", job_id, exc)
        _mark_job_failed(job_id, str(exc))
        raise self.retry(exc=exc)


def _extract_text(file_content: bytes, content_type: str, file_name: str) -> str:
    """Extract plain text from PDF or DOCX bytes."""
    if content_type == "application/pdf" or file_name.lower().endswith(".pdf"):
        return _extract_pdf_text(file_content)
    elif content_type in (
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ) or file_name.lower().endswith((".doc", ".docx")):
        return _extract_docx_text(file_content)
    return ""


def _extract_pdf_text(file_content: bytes) -> str:
    try:
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(file_content))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages).strip()
    except Exception as exc:
        logger.warning("PDF text extraction failed: %s", exc)
        return ""


def _extract_docx_text(file_content: bytes) -> str:
    try:
        from docx import Document

        doc = Document(io.BytesIO(file_content))
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        return "\n".join(paragraphs).strip()
    except Exception as exc:
        logger.warning("DOCX text extraction failed: %s", exc)
        return ""


def _mark_job_failed(job_id: str, error_message: str):
    from .models import CVExtractionJob

    try:
        CVExtractionJob.objects.filter(id=job_id).update(
            status=CVExtractionJob.Status.FAILED,
            error_message=error_message[:1000],
        )
    except Exception:
        pass
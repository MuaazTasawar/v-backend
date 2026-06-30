import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from ai_service.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def get_s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
    )


def upload_bytes(
    content: bytes,
    s3_key: str,
    content_type: str = "application/octet-stream",
    public: bool = False,
) -> str:
    """Uploads bytes to S3 and returns the public/private object URL."""
    client = get_s3_client()
    extra_args = {"ContentType": content_type, "ServerSideEncryption": "AES256"}
    if public:
        extra_args["ACL"] = "public-read"

    try:
        client.put_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=s3_key,
            Body=content,
            **extra_args,
        )
    except (BotoCoreError, ClientError) as exc:
        logger.error("S3 upload failed for key %s: %s", s3_key, exc)
        raise

    return f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{s3_key}"


def upload_html_site(
    startup_id: str,
    html_content: str,
    css_content: str = "",
    js_content: str = "",
) -> dict:
    """
    Uploads a generated static PoC site (HTML/CSS/JS) to S3 under a
    per-startup public prefix and returns the live URL plus bucket path.
    """
    base_path = f"poc-sites/{startup_id}"

    upload_bytes(
        html_content.encode("utf-8"),
        f"{base_path}/index.html",
        content_type="text/html",
        public=True,
    )
    if css_content:
        upload_bytes(
            css_content.encode("utf-8"),
            f"{base_path}/styles.css",
            content_type="text/css",
            public=True,
        )
    if js_content:
        upload_bytes(
            js_content.encode("utf-8"),
            f"{base_path}/script.js",
            content_type="application/javascript",
            public=True,
        )

    live_url = f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{base_path}/index.html"
    return {"live_url": live_url, "s3_bucket_path": base_path}
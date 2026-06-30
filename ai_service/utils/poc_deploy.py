"""
Automated Proof-of-Concept Deployment (Project Contribution #6).
Generates a complete static HTML/CSS/JS site from startup context and
deploys it to S3 as a live public URL — no founder dev effort required.
"""
import logging

from ai_service.utils.s3 import upload_html_site

logger = logging.getLogger(__name__)


def deploy_poc_site(startup_id: str, html: str, css: str, js: str) -> dict:
    """Thin wrapper kept separate from generation logic for testability."""
    return upload_html_site(
        startup_id=startup_id,
        html_content=html,
        css_content=css,
        js_content=js,
    )
"""
DocuSign Connect webhook handler. DocuSign POSTs envelope status
updates (signer completed, envelope completed, etc.) here. Configure
this URL in your DocuSign Connect settings as:
  https://yourdomain.com/api/v1/webhooks/docusign/
"""
import hashlib
import hmac
import logging
import xml.etree.ElementTree as ET

from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)


def _verify_hmac_signature(request) -> bool:
    """DocuSign Connect HMAC SHA256 signature verification."""
    signature_header = request.headers.get("X-DocuSign-Signature-1", "")
    if not signature_header or not settings.DOCUSIGN_WEBHOOK_SECRET:
        return False

    computed = hmac.new(
        settings.DOCUSIGN_WEBHOOK_SECRET.encode("utf-8"),
        request.body,
        hashlib.sha256,
    ).hexdigest()

    import base64
    expected = base64.b64encode(
        hmac.new(settings.DOCUSIGN_WEBHOOK_SECRET.encode("utf-8"), request.body, hashlib.sha256).digest()
    ).decode()

    return hmac.compare_digest(expected, signature_header)


@csrf_exempt
@require_POST
def docusign_webhook(request):
    if not _verify_hmac_signature(request):
        logger.warning("DocuSign webhook signature verification failed.")
        return HttpResponseBadRequest("Invalid signature.")

    try:
        root = ET.fromstring(request.body)
    except ET.ParseError:
        logger.error("DocuSign webhook payload could not be parsed as XML.")
        return HttpResponseBadRequest("Malformed payload.")

    ns = {"ds": "http://www.docusign.net/API/3.0"}
    envelope_id_el = root.find(".//ds:EnvelopeID", ns)
    status_el = root.find(".//ds:Status", ns)

    if envelope_id_el is None or status_el is None:
        logger.warning("DocuSign webhook missing EnvelopeID or Status.")
        return HttpResponse(status=200)  # Ack anyway — DocuSign retries on non-200

    envelope_id = envelope_id_el.text
    envelope_status = status_el.text

    from apps.contracts.tasks import handle_docusign_status_update
    handle_docusign_status_update.delay(envelope_id, envelope_status)

    return HttpResponse(status=200)
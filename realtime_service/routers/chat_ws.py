"""
Negotiation chat WebSocket (Module 5, FE-1/FE-2).

Two logical streams over one connection per user:
  - "shared": messages broadcast to both founder and investor
  - "private": AI side-agent suggestions/flags visible only to the
    connected user's own role — never relayed to the other party

The actual LLM calls (side agent, deal extraction, legal risk check)
are made by the AI microservice; this router orchestrates persistence
(via Django callback), fan-out (via Redis Pub/Sub), and delivery.
"""
import asyncio
import logging

import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from realtime_service.auth import authenticate_websocket
from realtime_service.config import get_settings
from realtime_service.pubsub.publisher import negotiation_channel, publish_event
from realtime_service.pubsub.subscriber import ChannelSubscriber

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(tags=["chat-ws"])


@router.websocket("/ws/negotiation/{negotiation_id}")
async def negotiation_chat(websocket: WebSocket, negotiation_id: str):
    user = await authenticate_websocket(websocket)
    if user is None:
        return

    if user.role not in ("founder", "investor"):
        await websocket.close(code=4003, reason="Only founders and investors can join negotiations.")
        return

    await websocket.accept()
    channel = negotiation_channel(negotiation_id)

    listener_task = asyncio.create_task(_relay_channel_to_client(websocket, channel, user.user_id))

    try:
        while True:
            data = await websocket.receive_json()
            message_text = data.get("message", "").strip()
            if not message_text:
                continue

            await _handle_incoming_message(
                negotiation_id=negotiation_id,
                party_role=user.role,
                user_id=user.user_id,
                message=message_text,
            )

    except WebSocketDisconnect:
        logger.info("User %s disconnected from negotiation %s", user.user_id, negotiation_id)
    finally:
        listener_task.cancel()


async def _relay_channel_to_client(websocket: WebSocket, channel: str, user_id: str):
    """
    Subscribes to the negotiation's Redis channel and forwards events to
    this specific client — filtering private events so only the intended
    recipient sees them.
    """
    try:
        async with ChannelSubscriber(channel) as subscriber:
            async for event in subscriber.listen():
                event_scope = event.get("scope", "shared")
                if event_scope == "private" and event.get("recipient_user_id") != user_id:
                    continue
                await websocket.send_json(event)
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.error("Relay task error on channel %s: %s", channel, exc)


async def _handle_incoming_message(negotiation_id: str, party_role: str, user_id: str, message: str):
    """
    1. Persist + broadcast the shared message immediately (low latency).
    2. Fetch negotiation context from Django (history + deal terms).
    3. Call the AI service for: private side-agent suggestion, legal risk
       check, and deal extraction — fan these results back out via Redis,
       scoped appropriately (shared vs private-to-sender).
    """
    from django.utils import timezone  # noqa — illustrative; realtime_service has no Django ORM access

    timestamp_iso = _now_iso()

    # 1. Broadcast shared message immediately
    await publish_event(
        negotiation_channel(negotiation_id),
        {
            "scope": "shared",
            "type": "chat_message",
            "role": party_role,
            "content": message,
            "timestamp": timestamp_iso,
        },
    )

    # 2 & 3. Persist + fetch context + run AI agents via Django callback endpoint.
    # Django owns the source of truth for negotiation history/deal terms and
    # proxies the AI service calls so the AI_SERVICE_SECRET never has to be
    # shared with this lighter-weight realtime process.
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.DJANGO_BACKEND_URL}/api/v1/contracts/negotiations/{negotiation_id}/process-message/",
                json={
                    "party_role": party_role,
                    "user_id": user_id,
                    "message": message,
                    "timestamp": timestamp_iso,
                },
                headers={"X-Internal-Secret": settings.AI_SERVICE_SECRET},
            )
            resp.raise_for_status()
            result = resp.json()
    except httpx.HTTPError as exc:
        logger.error("Django process-message callback failed for negotiation %s: %s", negotiation_id, exc)
        return

    # Private suggestion — only to the sender
    if result.get("private_suggestion"):
        await publish_event(
            negotiation_channel(negotiation_id),
            {
                "scope": "private",
                "recipient_user_id": user_id,
                "type": "ai_suggestion",
                "suggestion": result["private_suggestion"],
                "flags": result.get("flags", []),
                "timestamp": _now_iso(),
            },
        )

    # Legal risk flags — only to the sender
    if result.get("legal_risks"):
        await publish_event(
            negotiation_channel(negotiation_id),
            {
                "scope": "private",
                "recipient_user_id": user_id,
                "type": "legal_risk_alert",
                "risks": result["legal_risks"],
                "guidance": result.get("legal_guidance", ""),
                "timestamp": _now_iso(),
            },
        )

    # Deal closed — broadcast to both parties
    if result.get("is_deal_reached"):
        await publish_event(
            negotiation_channel(negotiation_id),
            {
                "scope": "shared",
                "type": "deal_reached",
                "deal_summary": result.get("deal_summary", {}),
                "timestamp": _now_iso(),
            },
        )


def _now_iso() -> str:
    from datetime import datetime, timezone as dt_timezone
    return datetime.now(dt_timezone.utc).isoformat()
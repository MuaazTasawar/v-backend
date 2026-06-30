"""
Dashboard live-update WebSocket. Pushes real-time status changes to a
founder's or investor's dashboard — document generation progress, PoC
deployment status, new interest signals, contract milestone updates,
and financial ledger events — without requiring the client to poll.

Events are published onto this channel by Celery tasks across the
platform (document generation, payment processing, contract state
transitions) via realtime_service.pubsub.publisher.publish_event, using
the dashboard_channel(startup_id) helper.
"""
import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from realtime_service.auth import authenticate_websocket
from realtime_service.pubsub.publisher import dashboard_channel, user_notification_channel
from realtime_service.pubsub.subscriber import ChannelSubscriber

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard-ws"])


@router.websocket("/ws/dashboard/{startup_id}")
async def startup_dashboard(websocket: WebSocket, startup_id: str):
    """
    Subscribes to a specific startup's dashboard channel. Both the
    founder (owner) and any investor viewing that startup's progress
    can connect — visibility/authorization for *which* startups a user
    may subscribe to is enforced by Django before the frontend ever
    requests a token-scoped connection.
    """
    user = await authenticate_websocket(websocket)
    if user is None:
        return

    await websocket.accept()
    channel = dashboard_channel(startup_id)

    try:
        async with ChannelSubscriber(channel) as subscriber:
            async for event in subscriber.listen():
                await websocket.send_json(event)
    except WebSocketDisconnect:
        logger.info("User %s disconnected from dashboard %s", user.user_id, startup_id)
    except Exception as exc:
        logger.error("Dashboard relay error for startup %s: %s", startup_id, exc)


@router.websocket("/ws/notifications")
async def personal_notifications(websocket: WebSocket):
    """
    Per-user notification stream — new matches, accepted interest
    signals, contract milestone reminders, payment confirmations.
    Scoped to the authenticated user's own channel only.
    """
    user = await authenticate_websocket(websocket)
    if user is None:
        return

    await websocket.accept()
    channel = user_notification_channel(user.user_id)

    try:
        async with ChannelSubscriber(channel) as subscriber:
            async for event in subscriber.listen():
                await websocket.send_json(event)
    except WebSocketDisconnect:
        logger.info("User %s disconnected from personal notification stream.", user.user_id)
    except Exception as exc:
        logger.error("Notification relay error for user %s: %s", user.user_id, exc)


@router.websocket("/ws/dashboard-keepalive/{startup_id}")
async def dashboard_keepalive(websocket: WebSocket, startup_id: str):
    """
    Lightweight ping endpoint some load balancers / proxies require to
    keep long-lived WebSocket connections from being reaped. Optional —
    the frontend can use this alongside the main dashboard socket if
    infra requires periodic application-layer pings.
    """
    user = await authenticate_websocket(websocket)
    if user is None:
        return
    await websocket.accept()
    try:
        while True:
            await asyncio.sleep(25)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
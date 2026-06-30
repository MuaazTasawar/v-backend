"""
Validates Django SimpleJWT access tokens for WebSocket connections.
Django and this service share DJANGO_SECRET_KEY (HS256), so tokens
issued by apps.auth_app can be verified here without a network call.
"""
import logging

import jwt
from fastapi import WebSocket, status

from realtime_service.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class AuthenticatedUser:
    def __init__(self, user_id: str, email: str, role: str):
        self.user_id = user_id
        self.email = email
        self.role = role


async def authenticate_websocket(websocket: WebSocket) -> AuthenticatedUser | None:
    """
    Expects the JWT as a query parameter: ws://.../ws/chat/{id}?token=<access_token>
    Browsers' native WebSocket API cannot set custom headers, so query
    param is the standard pattern here. Closes the connection and
    returns None on failure.
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing auth token.")
        return None

    try:
        payload = jwt.decode(token, settings.DJANGO_SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Token expired.")
        return None
    except jwt.InvalidTokenError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token.")
        return None

    user_id = payload.get("user_id") or payload.get("sub")
    email = payload.get("email", "")
    role = payload.get("role", "")

    if not user_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Token missing user identity.")
        return None

    return AuthenticatedUser(user_id=str(user_id), email=email, role=role)
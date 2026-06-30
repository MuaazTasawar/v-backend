import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from realtime_service.config import get_settings
from realtime_service.routers import chat_ws, dashboard_ws

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="Venturify Realtime Service",
    description="WebSocket + Redis Pub/Sub service for negotiation chat and live dashboard updates.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_ws.router)
app.include_router(dashboard_ws.router)


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "service": "venturify-realtime-service"}
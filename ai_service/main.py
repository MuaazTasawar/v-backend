import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from ai_service.config import get_settings
from ai_service.routers import advisory, pitch, chat, legal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"])

app = FastAPI(
    title="Venturify AI Service",
    description="AI microservice powering pitch generation, advisory RAG, negotiation, legal, and mentorship agents.",
    version="1.0.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Internal service — public access is blocked via X-Internal-Secret
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers — mentorship, investor_panel are added in Phase 10.
app.include_router(advisory.router)
app.include_router(pitch.router)
app.include_router(chat.router)
app.include_router(legal.router)


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "service": "venturify-ai-service"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal server error. Please try again later."},
    )
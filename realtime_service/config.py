from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Internal auth (shared secret, also used to validate JWTs issued by Django)
    AI_SERVICE_SECRET: str = "shared-internal-secret-between-django-and-fastapi"
    DJANGO_SECRET_KEY: str = ""  # used to verify SimpleJWT tokens (HS256)

    # Redis Pub/Sub backbone
    REDIS_URL: str = "redis://localhost:6379/0"

    # AI service (negotiation turn + legal risk check calls happen from here)
    AI_SERVICE_URL: str = "http://localhost:8001"

    # Django backend (for persisting chat messages via REST callback)
    DJANGO_BACKEND_URL: str = "http://localhost:8000"

    CORS_ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
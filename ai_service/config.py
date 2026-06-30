from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Internal auth (shared secret between Django and FastAPI)
    AI_SERVICE_SECRET: str = "shared-internal-secret-between-django-and-fastapi"

    # LLM
    ANTHROPIC_API_KEY: str = ""
    DEFAULT_MODEL: str = "claude-sonnet-4-6"
    DEFAULT_TEMPERATURE: float = 0.4

    # Tavily (web search fallback)
    TAVILY_API_KEY: str = ""

    # ChromaDB
    CHROMA_PERSIST_DIRECTORY: str = "./chroma_db"
    CHROMA_CONFIDENCE_THRESHOLD: float = 0.65  # cosine similarity cutoff for RAG vs web fallback

    # AWS S3 (for PoC deployment + generated documents)
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_STORAGE_BUCKET_NAME: str = ""
    AWS_S3_REGION_NAME: str = "us-east-1"

    # Redis (session state, rate limiting)
    REDIS_URL: str = "redis://localhost:6379/0"

    # MCP integrations
    JIRA_MCP_URL: str = ""
    JIRA_MCP_EMAIL: str = ""
    JIRA_MCP_API_TOKEN: str = ""
    NOTION_MCP_API_KEY: str = ""

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # Django backend (for callbacks if ever needed)
    DJANGO_BACKEND_URL: str = "http://localhost:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
from fastapi import Header, HTTPException, status
from .config import get_settings

settings = get_settings()


async def verify_internal_secret(x_internal_secret: str = Header(...)) -> None:
    """
    Guards every AI service route. Only the Django backend (and other
    internal Venturify services) may call this microservice — never the
    public internet directly.
    """
    if x_internal_secret != settings.AI_SERVICE_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal service credentials.",
        )


def get_llm():
    """Returns a configured LangChain Anthropic chat model instance."""
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=settings.DEFAULT_MODEL,
        temperature=settings.DEFAULT_TEMPERATURE,
        api_key=settings.ANTHROPIC_API_KEY,
        max_tokens=4096,
    )
from pydantic import BaseModel, Field


class IndexStartupRequest(BaseModel):
    startup_id: str
    pitch_context: dict = Field(default_factory=dict)
    generated_documents: list[dict] = Field(default_factory=list)


class IndexStartupResponse(BaseModel):
    collection_name: str
    chunks_indexed: int


class AdvisoryQuestionRequest(BaseModel):
    startup_id: str
    collection_name: str
    question: str
    persona: str = Field(default="investor", pattern="^(investor|founder)$")


class AdvisoryQuestionResponse(BaseModel):
    answer: str
    source: str  # "internal" | "hybrid" | "web_fallback"
    confidence: float


class FeasibilitySummaryRequest(BaseModel):
    startup_id: str
    pitch_context: dict = Field(default_factory=dict)


class FeasibilitySummaryResponse(BaseModel):
    summary: str
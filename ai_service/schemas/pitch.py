from pydantic import BaseModel, Field


class ConversationMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    timestamp: str | None = None


class PitchConverseRequest(BaseModel):
    startup_id: str
    conversation_history: list[ConversationMessage] = Field(default_factory=list)
    current_phase: str = "problem"
    pitch_context: dict = Field(default_factory=dict)


class PitchConverseResponse(BaseModel):
    reply: str
    next_phase: str
    is_complete: bool = False
    extracted_context: dict = Field(default_factory=dict)


class GenerateDocumentRequest(BaseModel):
    startup_id: str
    document_type: str  # feasibility_report | pitch_deck | proposal | executive_summary
    pitch_context: dict = Field(default_factory=dict)


class GenerateDocumentResponse(BaseModel):
    file_url: str
    content_json: dict = Field(default_factory=dict)


class GeneratePoCRequest(BaseModel):
    startup_id: str
    startup_name: str
    pitch_context: dict = Field(default_factory=dict)


class GeneratePoCResponse(BaseModel):
    live_url: str
    s3_bucket_path: str
    generated_html: str
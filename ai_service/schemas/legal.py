from pydantic import BaseModel, Field


class LegalRiskCheckRequest(BaseModel):
    negotiation_id: str
    party_role: str = Field(pattern="^(founder|investor)$")
    deal_terms_so_far: dict = Field(default_factory=dict)
    latest_message: str


class LegalRiskCheckResponse(BaseModel):
    risks: list[str] = Field(default_factory=list)
    guidance: str


class LegalBriefingRequest(BaseModel):
    party_role: str = Field(pattern="^(founder|investor)$")
    deal_summary: dict = Field(default_factory=dict)


class LegalBriefingResponse(BaseModel):
    briefing: str
    protections: list[str] = Field(default_factory=list)
    obligations: list[str] = Field(default_factory=list)


class DraftContractRequest(BaseModel):
    startup_id: str
    deal_summary: dict = Field(default_factory=dict)
    founder_name: str
    investor_name: str
    startup_name: str


class DraftContractResponse(BaseModel):
    contract_text: str
    contract_sections: dict = Field(default_factory=dict)
    payment_structure: str  # "lumpsum" | "phased"
    milestones: list[dict] = Field(default_factory=list)
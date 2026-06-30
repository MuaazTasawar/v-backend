from pydantic import BaseModel, Field


class ChatTurnRequest(BaseModel):
    """One turn in the negotiation chat (Module 5, FE-1/FE-2)."""
    negotiation_id: str
    party_role: str = Field(pattern="^(founder|investor)$")
    message: str
    shared_history: list[dict] = Field(default_factory=list)
    # [{"role": "founder"|"investor", "content": str, "timestamp": str}]
    deal_terms_so_far: dict = Field(default_factory=dict)
    # {"valuation": ..., "amount": ..., "equity_pct": ..., "instrument": ...}


class ChatTurnResponse(BaseModel):
    """
    Returns the shared chat message PLUS a private suggestion only the
    sender's side sees — never broadcast to the opposing party.
    """
    shared_reply_allowed: bool = True
    private_suggestion: str
    flags: list[str] = Field(default_factory=list)
    # e.g. ["below_market_valuation", "unusually_high_equity_ask"]
    updated_deal_terms: dict = Field(default_factory=dict)


class ExtractDealSummaryRequest(BaseModel):
    negotiation_id: str
    shared_history: list[dict] = Field(default_factory=list)


class ExtractDealSummaryResponse(BaseModel):
    is_deal_reached: bool
    deal_summary: dict = Field(default_factory=dict)
    # {"valuation": int, "amount": int, "equity_pct": float, "instrument": str,
    #  "milestones": [...], "payment_structure": "lumpsum"|"phased"}
    confidence: float
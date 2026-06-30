"""
Weighted compatibility scoring algorithm (BO-3).
Compares investor preferences against startup attributes across four
weighted dimensions: industry, funding stage, ticket size fit, and risk appetite.
"""
from decimal import Decimal


WEIGHTS = {
    "industry": Decimal("0.35"),
    "stage": Decimal("0.25"),
    "ticket_size": Decimal("0.20"),
    "risk": Decimal("0.20"),
}

STAGE_ORDER = ["pre_seed", "seed", "series_a", "series_b", "growth"]

RISK_TOLERANCE_BY_STAGE = {
    "pre_seed": "aggressive",
    "seed": "aggressive",
    "series_a": "moderate",
    "series_b": "moderate",
    "growth": "conservative",
}


def compute_match_score(investor, startup) -> dict:
    """Returns a dict ready to spread into MatchScore.objects.update_or_create(defaults=...)."""
    try:
        investor_profile = investor.investor_profile
    except Exception:
        investor_profile = None

    industry_score = _score_industry(investor_profile, startup)
    stage_score = _score_stage(investor_profile, startup)
    ticket_score = _score_ticket_size(investor_profile, startup)
    risk_score = _score_risk(investor_profile, startup)

    overall = (
        industry_score * WEIGHTS["industry"]
        + stage_score * WEIGHTS["stage"]
        + ticket_score * WEIGHTS["ticket_size"]
        + risk_score * WEIGHTS["risk"]
    )

    return {
        "overall_score": round(overall, 2),
        "industry_score": round(industry_score, 2),
        "stage_score": round(stage_score, 2),
        "ticket_size_score": round(ticket_score, 2),
        "risk_score": round(risk_score, 2),
        "breakdown": {
            "weights": {k: str(v) for k, v in WEIGHTS.items()},
            "investor_has_profile": investor_profile is not None,
        },
    }


def _score_industry(investor_profile, startup) -> Decimal:
    if not investor_profile:
        return Decimal("0")
    investor_industries = set(investor_profile.industries.values_list("id", flat=True))
    startup_industries = set(startup.industries.values_list("id", flat=True))
    if not investor_industries or not startup_industries:
        return Decimal("50")  # neutral score when no preference data
    overlap = investor_industries & startup_industries
    if overlap:
        return Decimal("100")
    return Decimal("20")


def _score_stage(investor_profile, startup) -> Decimal:
    if not investor_profile or not investor_profile.preferred_stages:
        return Decimal("50")
    if startup.funding_stage in investor_profile.preferred_stages:
        return Decimal("100")
    try:
        startup_idx = STAGE_ORDER.index(startup.funding_stage)
        preferred_indices = [STAGE_ORDER.index(s) for s in investor_profile.preferred_stages if s in STAGE_ORDER]
        if preferred_indices:
            closest_distance = min(abs(startup_idx - p) for p in preferred_indices)
            return max(Decimal("0"), Decimal("100") - Decimal(closest_distance * 25))
    except ValueError:
        pass
    return Decimal("30")


def _score_ticket_size(investor_profile, startup) -> Decimal:
    if not investor_profile:
        return Decimal("50")
    funding_ask = startup.funding_ask or 0
    min_t = investor_profile.min_ticket_size
    max_t = investor_profile.max_ticket_size
    if min_t <= funding_ask <= max_t:
        return Decimal("100")
    if funding_ask < min_t:
        gap_ratio = (min_t - funding_ask) / max(min_t, 1)
        return max(Decimal("0"), Decimal("100") - Decimal(float(gap_ratio) * 100))
    gap_ratio = (funding_ask - max_t) / max(max_t, 1)
    return max(Decimal("0"), Decimal("100") - Decimal(float(gap_ratio) * 100))


def _score_risk(investor_profile, startup) -> Decimal:
    if not investor_profile:
        return Decimal("50")
    expected_risk = RISK_TOLERANCE_BY_STAGE.get(startup.funding_stage, "moderate")
    if investor_profile.risk_appetite == expected_risk:
        return Decimal("100")
    risk_levels = ["conservative", "moderate", "aggressive"]
    try:
        investor_idx = risk_levels.index(investor_profile.risk_appetite)
        expected_idx = risk_levels.index(expected_risk)
        distance = abs(investor_idx - expected_idx)
        return max(Decimal("0"), Decimal("100") - Decimal(distance * 35))
    except ValueError:
        return Decimal("50")
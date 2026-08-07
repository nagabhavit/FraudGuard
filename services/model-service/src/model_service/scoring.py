"""Real-time fraud scoring.

Scores each request against the model loaded once at startup
(`fraudguard-ml`, ADR-0009). `DecisionOutcome`'s three values are
duplicated here as a `Literal` rather than imported from `fraudguard-db`
-- this service has no reason to depend on the database schema, only on
the same three string values the gateway will map back into
`fraudguard_db.models.DecisionOutcome` when it persists the decision.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from fraudguard_ml import build_feature_row

router = APIRouter(tags=["scoring"])

Outcome = Literal["approve", "decline", "review"]


class ScoreRequest(BaseModel):
    amount: Annotated[Decimal, Field(gt=0)]
    velocity_1m: Annotated[int, Field(ge=0)]
    velocity_1h: Annotated[int, Field(ge=0)]
    velocity_24h: Annotated[int, Field(ge=0)]
    distinct_merchants_24h: Annotated[int, Field(ge=0)]


class ScoreResponse(BaseModel):
    outcome: Outcome
    risk_score: float
    model_version: str
    reason_codes: list[str]


def _outcome_for(
    risk_score: float, *, approve_below: float, decline_above: float
) -> Outcome:
    if risk_score < approve_below:
        return "approve"
    if risk_score > decline_above:
        return "decline"
    return "review"


@router.post("/v1/score", response_model=ScoreResponse)
async def score(payload: ScoreRequest, request: Request) -> ScoreResponse:
    row = build_feature_row(
        amount=payload.amount,
        velocity_1m=payload.velocity_1m,
        velocity_1h=payload.velocity_1h,
        velocity_24h=payload.velocity_24h,
        distinct_merchants_24h=payload.distinct_merchants_24h,
    )
    model = request.app.state.model
    risk_score = model.predict_proba(row)
    reason_codes = model.explain(row)

    settings = request.app.state.settings
    outcome = _outcome_for(
        risk_score,
        approve_below=settings.approve_below,
        decline_above=settings.decline_above,
    )

    return ScoreResponse(
        outcome=outcome,
        risk_score=risk_score,
        model_version=model.version,
        reason_codes=reason_codes,
    )

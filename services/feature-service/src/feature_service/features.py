"""Read API for precomputed fraud-detection features.

An account with no transaction history returns a feature vector of zeros,
not 404 -- "no transactions yet" is the normal state for a new account, not
an error. See ADR-0007.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["features"])


class FeatureVector(BaseModel):
    account_id: UUID
    computed_at: datetime
    velocity_1m: int
    velocity_1h: int
    velocity_24h: int
    distinct_merchants_24h: int


@router.get("/v1/features/{account_id}")
async def get_features(account_id: UUID, request: Request) -> FeatureVector:
    vector = await request.app.state.store.get_feature_vector(str(account_id))
    return FeatureVector(
        account_id=account_id,
        computed_at=datetime.now(UTC),
        **vector,
    )

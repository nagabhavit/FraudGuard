"""Unit tests for the feature schema -- no model or I/O required."""

from __future__ import annotations

from decimal import Decimal

from fraudguard_ml.features import FEATURE_NAMES, build_feature_row, feature_schema_hash


def test_build_feature_row_matches_feature_names_order() -> None:
    row = build_feature_row(
        amount=Decimal("42.50"),
        velocity_1m=1,
        velocity_1h=3,
        velocity_24h=10,
        distinct_merchants_24h=2,
    )
    assert len(row) == len(FEATURE_NAMES)
    assert dict(zip(FEATURE_NAMES, row, strict=True)) == {
        "amount": 42.50,
        "velocity_1m": 1.0,
        "velocity_1h": 3.0,
        "velocity_24h": 10.0,
        "distinct_merchants_24h": 2.0,
    }


def test_build_feature_row_accepts_a_plain_float_amount() -> None:
    row = build_feature_row(
        amount=42.50,
        velocity_1m=0,
        velocity_1h=0,
        velocity_24h=0,
        distinct_merchants_24h=0,
    )
    assert row[FEATURE_NAMES.index("amount")] == 42.50


def test_feature_schema_hash_is_stable() -> None:
    assert feature_schema_hash() == feature_schema_hash()


def test_feature_schema_hash_is_a_short_hex_string() -> None:
    digest = feature_schema_hash()
    assert len(digest) == 16
    int(digest, 16)  # raises ValueError if not valid hex

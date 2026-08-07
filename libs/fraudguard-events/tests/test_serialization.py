"""Unit tests for the Confluent wire-format Avro codec -- no Kafka or
Schema Registry required.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from fraudguard_events.producer import load_schema
from fraudguard_events.serialization import decode, encode, schema_id_of

SCHEMA = load_schema("transaction_received")


def _sample_record() -> dict[str, object]:
    return {
        "event_id": str(uuid4()),
        "transaction_id": str(uuid4()),
        "account_id": str(uuid4()),
        "merchant_id": "merchant-1",
        "amount": Decimal("42.50"),
        "currency": "USD",
        "occurred_at": datetime.now(UTC),
        "received_at": datetime.now(UTC),
    }


def test_encode_then_decode_round_trips_the_record() -> None:
    record = _sample_record()
    payload = encode(SCHEMA, schema_id=7, record=record)

    decoded = decode(SCHEMA, payload)

    assert decoded["merchant_id"] == "merchant-1"
    assert decoded["currency"] == "USD"
    assert decoded["amount"] == Decimal("42.50")
    # fastavro decodes the "uuid" logical type into a uuid.UUID, not the
    # str that was encoded -- a richer round trip, not a lossy one.
    assert str(decoded["account_id"]) == record["account_id"]


def test_encoded_payload_starts_with_the_confluent_magic_byte() -> None:
    payload = encode(SCHEMA, schema_id=1, record=_sample_record())
    assert payload[0] == 0


def test_schema_id_of_extracts_the_id_without_decoding_the_body() -> None:
    payload = encode(SCHEMA, schema_id=42, record=_sample_record())
    assert schema_id_of(payload) == 42


def test_decode_rejects_a_payload_without_the_magic_byte() -> None:
    with pytest.raises(ValueError, match="magic byte"):
        decode(SCHEMA, b"not a wire-format payload")


def test_schema_id_of_rejects_a_payload_without_the_magic_byte() -> None:
    with pytest.raises(ValueError, match="magic byte"):
        schema_id_of(b"not a wire-format payload")

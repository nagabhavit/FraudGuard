"""Confluent wire-format Avro encoding.

Every message is one magic byte (0x0), a 4-byte big-endian schema ID, then
the Avro binary body:
https://docs.confluent.io/platform/current/schema-registry/fundamentals/serdes-develop/index.html#wire-format

Hand-written rather than imported from confluent-kafka's AvroSerializer --
see ADR-0006.
"""

from __future__ import annotations

import io
import struct
from typing import Any, cast

import fastavro

_MAGIC_BYTE = b"\x00"
_HEADER_LENGTH = 5  # 1 magic byte + 4-byte schema id


def encode(schema: dict[str, Any], schema_id: int, record: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    buffer.write(_MAGIC_BYTE)
    buffer.write(struct.pack(">I", schema_id))
    fastavro.schemaless_writer(buffer, schema, record)
    return buffer.getvalue()


def decode(schema: dict[str, Any], payload: bytes) -> dict[str, Any]:
    if payload[:1] != _MAGIC_BYTE:
        raise ValueError("payload is missing the Confluent wire-format magic byte")
    buffer = io.BytesIO(payload[_HEADER_LENGTH:])
    return cast("dict[str, Any]", fastavro.schemaless_reader(buffer, schema))


def schema_id_of(payload: bytes) -> int:
    """Extract the schema ID from a wire-format payload without decoding the body."""
    if payload[:1] != _MAGIC_BYTE:
        raise ValueError("payload is missing the Confluent wire-format magic byte")
    (schema_id,) = struct.unpack(">I", payload[1:_HEADER_LENGTH])
    return int(schema_id)

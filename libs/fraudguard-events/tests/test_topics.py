"""Unit tests for topic declarations."""

from __future__ import annotations

from fraudguard_events.topics import ALL_TOPICS, TRANSACTIONS_V1


def test_transactions_v1_topic_is_versioned_and_namespaced() -> None:
    assert TRANSACTIONS_V1.name == "fraudguard.transactions.v1"


def test_transactions_v1_has_more_than_one_partition() -> None:
    # A single partition would make the "keyed by account_id" ordering
    # guarantee in transaction_received.avsc's doc meaningless -- there
    # would be nothing to distribute across.
    assert TRANSACTIONS_V1.partitions > 1


def test_all_topics_includes_every_declared_topic() -> None:
    assert TRANSACTIONS_V1 in ALL_TOPICS


def test_topic_names_are_unique() -> None:
    names = [topic.name for topic in ALL_TOPICS]
    assert len(names) == len(set(names))

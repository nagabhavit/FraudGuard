"""Unit tests for the schema definition itself -- no database required.

These catch a broken model declaration (a bad relationship, a missing
foreign key) at collection/mapper-configuration time, which is faster and
does not depend on Postgres being reachable. Behaviour that requires a real
Postgres is covered separately in test_session_integration.py.
"""

from __future__ import annotations

from sqlalchemy import UniqueConstraint

from fraudguard_db.models import (
    Base,
    Decision,
    DecisionOutcome,
    Label,
    LabelSource,
    Transaction,
)


def test_expected_tables_are_registered_on_the_shared_metadata() -> None:
    assert set(Base.metadata.tables) == {"transactions", "decisions", "labels"}


def test_decisions_has_a_unique_constraint_on_transaction_id() -> None:
    table = Base.metadata.tables["decisions"]
    unique_columns = {
        tuple(col.name for col in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("transaction_id",) in unique_columns


def test_transaction_relationships_are_navigable_both_ways() -> None:
    transaction_mapper = Transaction.__mapper__
    assert "decision" in transaction_mapper.relationships
    assert "labels" in transaction_mapper.relationships
    assert Decision.__mapper__.relationships["transaction"].back_populates == "decision"
    assert Label.__mapper__.relationships["transaction"].back_populates == "labels"


def test_decision_outcome_values_are_lowercase_strings() -> None:
    assert {member.value for member in DecisionOutcome} == {
        "approve",
        "decline",
        "review",
    }


def test_label_source_values_are_lowercase_strings() -> None:
    assert {member.value for member in LabelSource} == {
        "chargeback",
        "manual_review",
        "customer_report",
    }

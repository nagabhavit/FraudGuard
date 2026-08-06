# ADR-0001: Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-08-06

## Context

FraudGuard involves decisions that are cheap to make and expensive to reverse:
Kafka partition counts, delivery semantics, whether the model runs in-process
or as a service, whether Kafka sits in the request path. Six weeks later
nobody remembers what the alternatives were or why they lost, and the decision
gets relitigated from scratch — or worse, silently reversed by someone who
never knew it was a decision.

## Decision

Every significant decision is recorded as a numbered markdown file in
`docs/adr/`. Each ADR states:

1. **Context** — the forces in play at the time.
2. **Decision** — what was chosen.
3. **Alternatives considered** — what was rejected and why.
4. **Consequences** — what this makes easier and what it makes harder.

ADRs are immutable once accepted. Reversing one means writing a new ADR that
supersedes it; the original is marked `Superseded by ADR-00NN` and left in
place. The history is the point.

`CONTRIBUTING.md` lists the specific change types that require an ADR in the
same pull request.

## Alternatives considered

- **A single running design document.** Rejected: it records the current state
  but erases the reasoning, which is the part that is expensive to reconstruct.
- **Commit messages and pull request descriptions.** Rejected: they are
  discoverable only if you already know which commit to look for, and they are
  lost if the repository is migrated.
- **A wiki.** Rejected: it drifts from the code because it is not reviewed in
  the same pull request as the change it describes.

## Consequences

- A written record of intent that survives people leaving the project.
- A small tax on each decision, paid at the moment it is cheapest to pay.
- Reviewers can challenge the reasoning, not just the diff.

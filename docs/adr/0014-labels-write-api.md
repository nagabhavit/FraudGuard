# ADR-0014: Labels write API on the gateway

- **Status:** Accepted
- **Date:** 2026-08-09

## Context

`docs/architecture.md`'s roadmap bundles the remaining work into one
unscoped `14+` row: "Labels, load/chaos testing, k8s/Terraform." Labels is
the one of the three that is an unfinished piece of the application itself
rather than a deployment-target or test-harness change, and it is the only
one with schema already committed and sitting unused: `Label` and
`LabelSource` (`chargeback`, `manual_review`, `customer_report`) were built
in Milestone 5 (ADR-0005) alongside `transactions` and `decisions`, and
`Transaction.labels`' own docstring already anticipates a future writer
("arriving after the fact"). `labels` has also been a reserved
`CONTRIBUTING.md` commit scope since before this milestone existed. Nothing
in the system writes a `Label` row today.

Two things need deciding before any code is worth writing: where the write
endpoint lives, and how far this milestone reaches into the training
pipeline that will eventually want this data.

## Decision

**The gateway gains a write endpoint,
`POST /v1/transactions/{transaction_id}/labels`, rather than a new
`services/labels` service.** The same reasoning ADR-0012 already applied to
the read side applies here: the gateway already owns the `fraudguard-db`
session and the `Transaction`/`Label` models, so it is the one place in the
system that can serve this with no new inter-service dependency, no new
Dockerfile or compose entry, and no new database credentials to manage for
what is a single indexed insert. This does put a second write concern on a
service ADR-0009 designed around a strict hot-path latency budget; accepted
for the same reason ADR-0012 accepted it for reads — recording a label is a
plain, indexed Postgres write with no feature-service or model-service call
in it, so it cannot compete with the hot path for either dependency's
capacity, and FastAPI serves it from the same event loop without blocking
`POST /v1/transactions`.

**The route validates the transaction exists before inserting.** A
`SELECT` against `transactions.id`, raising the existing
`fraudguard_common.errors.NotFoundError` (already wired to a clean 404 via
`gateway/errors.py`) when it does not, rather than letting a bad
`transaction_id` surface as an opaque `IntegrityError` from the foreign key
constraint. The check costs one extra indexed read on a path with no
latency budget to protect.

**Multiple labels per transaction are accepted with no dedup or
upsert logic**, unchanged from what ADR-0005 already decided when the
schema was designed: a chargeback and a later manual review can disagree,
and reconciling them is a training-pipeline concern, not a constraint this
endpoint should enforce.

**`GET /v1/transactions` embeds each transaction's labels**, alongside the
existing embedded `decision` (ADR-0012), via a second `selectinload` — the
same no-N+1 pattern already in place, extended rather than duplicated. This
is the only way an operator sees a label was recorded without querying
Postgres directly, since there is no dashboard UI for submitting or
browsing labels in this milestone.

**No authentication.** The same posture ADR-0010 (Grafana), ADR-0012 (the
dashboard read API) and ADR-0013 (Alertmanager) have each already accepted:
one operator, one local deployment, no threat model yet that distinguishes
"the operator" from "a caller of this API." This must be revisited before
any shared or internet-facing deployment, the same caveat already attached
to every other unauthenticated surface in this system.

**`ml/pipelines/train.py` is not touched.** This milestone captures ground
truth; it does not consume it. `train.py`'s own docstring is explicit that
its labels are synthetic and none are faked to look otherwise — a local dev
stack will not accumulate enough real `Label` rows to meaningfully retrain
on, and blending real and synthetic ground truth raises its own questions
(how much real data is enough, how the two are weighted, what happens with
zero real labels) that deserve their own ADR once there is a real volume of
labels to design against, not a speculative answer now.

## Alternatives considered

- **A new `services/labels` service.** Rejected for the same reason
  ADR-0012 rejected a separate read service: it buys isolation the current
  single-operator, no-auth deployment does not need, at the cost of a new
  deployable, a new ADR-required service boundary, and a new set of
  database credentials to manage. Revisit if labels ever need write volume,
  access control, or a workflow (e.g. a reviewer queue) that genuinely
  outgrows one gateway route.
- **`POST /v1/labels` with `transaction_id` in the body, instead of
  `POST /v1/transactions/{transaction_id}/labels`.** Rejected: the
  transaction is the resource being annotated, and the nested path makes
  the existence check's 404 unambiguous — a body-only design would need a
  422 vs. 404 judgment call for the same failure that a path parameter
  resolves for free.
- **Upsert semantics (one label per transaction, latest write wins).**
  Rejected: contradicts ADR-0005's schema design, which deliberately has no
  unique constraint on `labels.transaction_id` (unlike `decisions`, which
  does) so that a chargeback and a manual review can coexist and disagree.
- **Wire real labels into `train.py` now, even partially (e.g. as an
  optional supplementary signal).** Rejected: no meaningful volume of real
  labels will exist until this milestone has shipped and run for a while,
  so designing the blending logic now would be speculative. Revisit once
  there is real data to shape the decision against.
- **Auth on the write path even though reads stay unauthenticated**, on the
  reasoning that writes are a different risk profile than reads. Rejected
  for this milestone: it would introduce the system's first authentication
  boundary asymmetrically (one endpoint authenticated, every other
  unauthenticated) with no threat model driving where the line is drawn.
  The same "one operator, no forcing function yet" reasoning ADR-0012 used
  applies equally to this write.
- **A dashboard UI for browsing or submitting labels.** Rejected as
  out of scope: this milestone closes the write-path gap; a labeling UI is
  frontend work with its own design questions (a queue view? inline on the
  existing feed?) better scoped once the API it would call exists and has
  been used.

## Consequences

**Positive**

- The `labels` table, unused since Milestone 5, has a real writer; ground
  truth arriving after the fact (a chargeback, a manual review, a customer
  report) is now capturable instead of only representable in the schema.
- No new infrastructure: one route on a service that already runs, already
  has a Postgres session, and is already in `docker-compose.yml`'s
  dependency graph — the same shape of win ADR-0012 already banked for
  reads.
- `GET /v1/transactions` becomes a complete-enough picture for an operator
  ("what happened, why, and was it ever confirmed fraudulent") without a
  second, disconnected query surface.

**Negative, and accepted**

- The gateway now serves a third concern (hot-path scoring, ops reads,
  ground-truth writes) on one service. Accepted for the same reason ADR-0012
  accepted the second: none of them compete for the hot path's actual
  constrained resources (feature-service, model-service).
- No authentication on an endpoint that writes fraud/not-fraud ground
  truth. Acceptable only because the current and only deployment target is
  a single operator's local Docker Compose stack; must be revisited before
  any shared or internet-facing deployment, the same caveat already
  attached to every other unauthenticated surface in this system.
- Real labels are captured but inert — `train.py` does not use them yet.
  This is a deliberate, documented gap, not an oversight: revisit once
  there is a real volume of labels to design a blending strategy against.

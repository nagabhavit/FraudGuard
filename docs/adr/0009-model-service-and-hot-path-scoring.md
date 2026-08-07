# ADR-0009: Model service and hot-path scoring

- **Status:** Accepted
- **Date:** 2026-08-07

## Context

Milestone 9 is the payoff of every milestone before it: a trained model,
a service to serve it, and the gateway actually calling it inline instead
of just accepting and persisting a transaction. That raises five questions
the earlier milestones didn't: how the model is trained and serialized,
how training and serving stay consistent about what a "feature" is, how a
prediction is explained, what the gateway does with the answer, and what
it does when the answer doesn't arrive in time.

## Decision

**LightGBM's native Booster format, not a pickled sklearn wrapper.**
`ml/pipelines/train.py` trains with `lgb.train()` and saves with
`Booster.save_model()` (a text file, human-diffable, no pickle
version-compatibility risk). `Booster.predict(..., pred_contrib=True)`
gives per-feature SHAP contributions natively, which the sklearn wrapper
does not expose as directly -- this is also *why* the native API, not just
a serialization preference.

**Training data is synthetic, generated in the same script that trains on
it.** Real fraud-labeled data does not exist for a portfolio project, and
should not be fabricated to look otherwise; `train.py` says so in its own
docstring and the label-generating heuristic is deliberately simple
(elevated velocity, high amount, and merchant-diversity outliers weighted
toward fraud, plus noise) -- enough signal for the model to learn
something real and for reason codes to mean something, not a claim of
production-grade fraud modeling.

**A new shared library, `fraudguard-ml`, is the single definition of the
feature schema** (`FEATURE_NAMES`, in the exact order the model expects,
and `build_feature_row` to build it) **and owns saving/loading the model
artifact.** Training and serving are two different processes; without a
shared definition they can silently disagree about feature order, which is
a wrong-but-not-crashing bug -- the model still returns a number, just not
the number it would have for the intended input. `fraudguard-ml` embeds a
hash of `FEATURE_NAMES` in the saved model's metadata; `model-service`
recomputes the hash from its own `FEATURE_NAMES` at load time and refuses
to start if they differ. `gateway` does not depend on `fraudguard-ml` --
it never loads a model, only calls `model-service` over HTTP, so the
gateway image still never carries LightGBM (`services/gateway/pyproject.toml`'s
own comment already said so, before this milestone existed to test it).

**Reason codes are the top-contributing features by absolute SHAP value**,
not a fixed set of business rules. `model-service` asks the booster for
`pred_contrib` on every prediction and returns the top three feature names
ranked by `abs(contribution)`.

**Decision thresholds are fixed cut points on `risk_score`**:
below 0.3 is `approve`, above 0.7 is `decline`, between is `review`.
Configurable (`ModelServiceSettings`), not hardcoded, but not learned or
calibrated against a target approval rate either -- there is no business
constraint yet to calibrate against.

**The gateway calls `feature-service` then `model-service`, in that order,
synchronously, each under its own bounded timeout, and persists a real
`Decision` row.** This is what `docs/architecture.md`'s hot-path diagram
already specified (`gateway -> feature service -> model service ->
decision`); this milestone is the one that makes it true instead of
aspirational. `POST /v1/transactions` now returns **200**, not the 202
Milestone 6 used -- 202 meant "accepted, come back later", which stopped
being honest the moment the response started carrying a real, synchronous
decision instead of just an accepted-for-later-processing acknowledgement.

**On any failure from either dependency -- timeout, connection error, non-2xx
-- the gateway falls back to a fixed rule on the transaction's own amount**
(above a threshold: `review`; otherwise `approve`) **and records
`model_version = NULL`.** `docs/architecture.md`'s degradation ladder
section already ruled out both alternatives: blocking the payment
indefinitely, and failing open with no check at all. A null
`model_version` is the existing, already-migrated (`Decision.model_version`,
ADR-0005) signal that this was the fallback rule, not the model -- nothing
new needed there, it was built for exactly this day.

**`model-service` fails fast at startup if no trained model file exists**,
the same choice `aggregator` made for a missing Kafka topic (ADR-0008):
`restart: unless-stopped` retries the container until an operator runs
`ml/pipelines/train.py`, which is simpler than a service that starts
successfully into a permanently-degraded state.

## Alternatives considered

- **Pickle/joblib the LightGBM sklearn wrapper.** Rejected: pickle ties the
  saved artifact to the exact library versions that created it, which is a
  worse failure mode (an opaque unpickling error) than a text-format model
  file a newer LightGBM can still read. The native API also gives
  `pred_contrib` more directly than the sklearn wrapper does.
- **Real, external fraud datasets (e.g. a public Kaggle credit-card
  dataset).** Rejected: pulling in a third-party dataset raises licensing
  and provenance questions this project has no need to take on, and would
  not exercise this system's own feature schema (`velocity_*`,
  `distinct_merchants_24h`) the way synthetic data generated against that
  exact schema does.
- **Model-service calls feature-service itself, so the gateway only makes
  one call.** Rejected: couples two services that otherwise have no reason
  to know about each other, and the architecture diagram already specifies
  the gateway as the orchestrator. One extra HTTP hop from the gateway is a
  smaller cost than a hidden dependency between two services that should be
  independently deployable.
- **Fail open (always `approve`) when a dependency is unreachable.**
  Rejected explicitly by `docs/architecture.md` before this ADR existed:
  "failing open with no check at all" was already ruled out as an option,
  not just an oversight to fix now.
- **Fail closed (always `decline`) when a dependency is unreachable.**
  Rejected: an infrastructure outage should not become a blanket denial of
  legitimate transactions; a cheap, real check on data already in hand
  (the amount) is strictly better than a fixed answer in either direction.
- **`model-service` starts successfully with no model loaded, reporting
  degraded readiness instead of crashing.** Rejected for consistency with
  `aggregator`'s precedent (ADR-0008) and because "will not start until an
  operator runs the training script" is a clearer failure than "started,
  but every request will 503".

## Consequences

**Positive**

- Reason codes are real per-prediction SHAP contributions, not a fixed
  lookup table -- they can point at a feature that mattered for one
  transaction and not another.
- The feature-schema hash check makes train/serve skew a load-time error
  instead of a silent scoring bug.
- The gateway's response is now honest: `POST /v1/transactions` returns
  the actual decision, not an acknowledgement that one will happen later.
- A dependency outage degrades to a real (if simplistic) decision, visible
  after the fact via `model_version IS NULL`, never a stuck request and
  never a rubber-stamped approval.

**Negative, and accepted**

- Synthetic training data means the model's discrimination is only as good
  as the synthetic label heuristic -- it demonstrates the pipeline and the
  hot-path integration, not fraud-detection accuracy on real behaviour.
- Two sequential HTTP hops (feature-service, model-service) inside the
  request path add real latency; local default timeouts (2s each) are
  generous for a dev stack over docker-compose networking, not tuned to
  the README's p99 ≤ 100ms budget -- production tuning is future work,
  not claimed here.
- `POST /v1/transactions`' response contract changed (202 -> 200, new
  fields) in a way that would be a breaking change for any existing
  caller. There is no caller yet outside this repository's own tests, so
  the cost is paid now, while it is free, rather than later.

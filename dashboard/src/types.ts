// Mirrors gateway's TransactionFeedItem/TransactionFeedPage
// (services/gateway/src/gateway/transactions.py) -- one definition per side
// of the HTTP boundary, kept in sync by hand since the dashboard is a
// separate npm project outside the uv workspace (ADR-0003) and cannot share
// the Pydantic model directly.

export type DecisionOutcome = "approve" | "decline" | "review";

export interface DecisionSummary {
  outcome: DecisionOutcome;
  risk_score: number;
  model_version: string | null;
  reason_codes: string[] | null;
  decided_at: string;
}

// Mirrors gateway's LabelSource/LabelSummary/LabelCreate
// (services/gateway/src/gateway/labels.py, Milestone 14) -- same
// hand-kept-in-sync reasoning as above. Milestone 28 is the first
// dashboard code to read or write any of these.
export type LabelSource = "chargeback" | "manual_review" | "customer_report";

export interface LabelSummary {
  id: string;
  is_fraud: boolean;
  source: LabelSource;
  notes: string | null;
  labeled_at: string;
}

export interface LabelCreate {
  is_fraud: boolean;
  source: LabelSource;
  notes?: string | null;
}

// The POST /v1/transactions/{id}/labels response body (LabelRead) --
// LabelSummary plus transaction_id, matching gateway/labels.py's
// `class LabelRead(LabelSummary): transaction_id: UUID` exactly.
export interface LabelRead extends LabelSummary {
  transaction_id: string;
}

export interface TransactionFeedItem {
  transaction_id: string;
  account_id: string;
  merchant_id: string;
  amount: string;
  currency: string;
  occurred_at: string;
  decision: DecisionSummary | null;
  labels: LabelSummary[];
}

export interface TransactionFeedPage {
  items: TransactionFeedItem[];
  limit: number;
  offset: number;
}

// Mirrors gateway's HealthStatus (services/gateway/src/gateway/health.py) --
// GET /health/live and /health/ready both return this shape.
export interface HealthStatus {
  status: "ok" | "error";
  checks: Record<string, string>;
}

// The known, fixed feature schema model-service scores against
// (libs/fraudguard-ml/src/fraudguard_ml/features.py, FEATURE_NAMES) --
// a true static fact about the running system, not an API response and
// not fabricated data. Used only for display/explanation, never as a
// stand-in for a metric no endpoint actually exposes.
export const KNOWN_FEATURE_NAMES = [
  "amount",
  "velocity_1m",
  "velocity_1h",
  "velocity_24h",
  "distinct_merchants_24h",
] as const;

// model-service/settings.py's real, fixed decision thresholds (not a UI
// invention): risk_score < 0.3 -> approve, > 0.7 -> decline, else review.
export const RISK_APPROVE_BELOW = 0.3;
export const RISK_DECLINE_ABOVE = 0.7;

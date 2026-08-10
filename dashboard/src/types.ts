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

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

export interface TransactionFeedItem {
  transaction_id: string;
  account_id: string;
  merchant_id: string;
  amount: string;
  currency: string;
  occurred_at: string;
  decision: DecisionSummary | null;
}

export interface TransactionFeedPage {
  items: TransactionFeedItem[];
  limit: number;
  offset: number;
}

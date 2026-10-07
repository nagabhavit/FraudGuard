// Human-readable explanations for the fixed feature schema
// (libs/fraudguard-ml/src/fraudguard_ml/features.py, FEATURE_NAMES) that
// model-service's reason_codes field names directly. These descriptions
// are static documentation of what each feature means, not fabricated
// per-transaction data -- the actual reason_codes array, its order, and
// which features appear always come from the real API response.

export const REASON_CODE_LABELS: Record<string, string> = {
  amount: "Transaction amount",
  velocity_1m: "Transactions in the last minute",
  velocity_1h: "Transactions in the last hour",
  velocity_24h: "Transactions in the last 24 hours",
  distinct_merchants_24h: "Distinct merchants in the last 24 hours",
};

export const REASON_CODE_EXPLANATIONS: Record<string, string> = {
  amount:
    "The transaction's own amount contributed meaningfully to the risk score -- unusually large purchases skew toward higher risk.",
  velocity_1m:
    "This account made an elevated number of transactions within the last minute -- a classic signal of automated or compromised-card activity.",
  velocity_1h:
    "This account's transaction count over the last hour was elevated relative to typical behavior.",
  velocity_24h:
    "This account's transaction count over the last 24 hours was elevated relative to typical behavior.",
  distinct_merchants_24h:
    "This account spread transactions across an unusually high number of distinct merchants in the last 24 hours -- a pattern associated with card-testing or rapid cash-out behavior.",
};

export function labelForReasonCode(code: string): string {
  return REASON_CODE_LABELS[code] ?? code;
}

export function explanationForReasonCode(code: string): string {
  return (
    REASON_CODE_EXPLANATIONS[code] ??
    "This feature was among the largest contributors to the model's score for this transaction."
  );
}

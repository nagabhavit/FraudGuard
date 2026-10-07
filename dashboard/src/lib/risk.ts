import { RISK_APPROVE_BELOW, RISK_DECLINE_ABOVE } from "../types";
import type { DecisionOutcome } from "../types";

export type RiskTier = "low" | "medium" | "high";
export type StatusRole = "good" | "warning" | "critical";

/** Buckets a raw risk_score using model-service's own real cut points
 * (settings.py's approve_below/decline_above), not an invented UI scale. */
export function riskTierFor(riskScore: number): RiskTier {
  if (riskScore < RISK_APPROVE_BELOW) return "low";
  if (riskScore > RISK_DECLINE_ABOVE) return "high";
  return "medium";
}

export function statusRoleForOutcome(outcome: DecisionOutcome): StatusRole {
  switch (outcome) {
    case "approve":
      return "good";
    case "review":
      return "warning";
    case "decline":
      return "critical";
  }
}

export function statusRoleForRiskTier(tier: RiskTier): StatusRole {
  switch (tier) {
    case "low":
      return "good";
    case "medium":
      return "warning";
    case "high":
      return "critical";
  }
}

export const RISK_TIER_LABEL: Record<RiskTier, string> = {
  low: "Low risk",
  medium: "Medium risk",
  high: "High risk",
};

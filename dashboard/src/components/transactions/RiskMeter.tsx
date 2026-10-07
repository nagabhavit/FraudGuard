import { riskTierFor, statusRoleForRiskTier } from "../../lib/risk";

const ROLE_COLOR: Record<string, string> = {
  good: "var(--status-good)",
  warning: "var(--status-warning)",
  critical: "var(--status-critical)",
};

export function RiskMeter({ riskScore, compact }: { riskScore: number; compact?: boolean }) {
  const tier = riskTierFor(riskScore);
  const role = statusRoleForRiskTier(tier);
  const pct = Math.max(0.02, Math.min(1, riskScore)) * 100;
  const color = ROLE_COLOR[role];

  if (compact) {
    return (
      <div className="table-risk-meter">
        <div className="table-risk-meter-track">
          <div className="table-risk-meter-fill" style={{ width: `${pct}%`, background: color }} />
        </div>
        <span className="table-risk-meter-value tabular" style={{ color }}>
          {riskScore.toFixed(3)}
        </span>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 160 }}>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <span className="tabular" style={{ fontWeight: 680, fontSize: 22, color }}>
          {riskScore.toFixed(4)}
        </span>
      </div>
      <div className="progress-bar-track" style={{ height: 8 }}>
        <div className="progress-bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

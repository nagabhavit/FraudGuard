import {
  Activity,
  AlertTriangle,
  Banknote,
  CheckCircle2,
  CircleHelp,
  Cpu,
  Gauge,
  ShieldAlert,
  ShieldCheck,
  TrendingUp,
  XCircle,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { StatCard } from "../components/common/StatCard";
import { TransactionDrawer } from "../components/transactions/TransactionDrawer";
import { TransactionsTable } from "../components/transactions/TransactionsTable";
import { useAllTransactions } from "../hooks/useAllTransactions";
import { useGatewayPulse } from "../hooks/useGatewayPulse";
import { useLiveTransactions } from "../hooks/useLiveTransactions";
import { formatCount, formatPercent, formatUsdSumAsInr } from "../lib/format";
import { RISK_TIER_LABEL, riskTierFor, type RiskTier } from "../lib/risk";
import type { LabelSummary, TransactionFeedItem } from "../types";

const RISK_TIER_COLOR: Record<RiskTier, string> = {
  low: "var(--status-good)",
  medium: "var(--status-warning)",
  high: "var(--status-critical)",
};

const RISK_TIER_ICON: Record<RiskTier, typeof ShieldCheck> = {
  low: ShieldCheck,
  medium: AlertTriangle,
  high: ShieldAlert,
};

function SegmentedBar({ segments }: { segments: { color: string; pct: number }[] }) {
  return (
    <div
      style={{
        display: "flex",
        height: 10,
        borderRadius: 999,
        overflow: "hidden",
        background: "var(--bg-surface-hover)",
        gap: 2,
      }}
    >
      {segments
        .filter((segment) => segment.pct > 0)
        .map((segment, index) => (
          <div
            key={index}
            style={{ width: `${segment.pct * 100}%`, background: segment.color, minWidth: segment.pct > 0 ? 3 : 0 }}
          />
        ))}
    </div>
  );
}

export function OverviewPage() {
  const all = useAllTransactions();
  const live = useLiveTransactions(10);
  const pulse = useGatewayPulse();
  const navigate = useNavigate();
  const [selected, setSelected] = useState<TransactionFeedItem | null>(null);

  const decided = useMemo(() => all.items.filter((item) => item.decision !== null), [all.items]);

  const kpis = useMemo(() => {
    const total = all.items.length;
    const flagged = decided.filter((item) => item.decision!.outcome !== "approve").length;
    const declined = decided.filter((item) => item.decision!.outcome === "decline").length;
    const approved = decided.filter((item) => item.decision!.outcome === "approve").length;
    const volume = all.items.reduce((sum, item) => sum + Number(item.amount), 0);
    const avgRisk =
      decided.length > 0
        ? decided.reduce((sum, item) => sum + item.decision!.risk_score, 0) / decided.length
        : null;

    return {
      total,
      flagged,
      fraudRate: decided.length > 0 ? declined / decided.length : null,
      volume,
      approvalRate: decided.length > 0 ? approved / decided.length : null,
      avgRisk,
    };
  }, [all.items, decided]);

  const riskBuckets = useMemo(() => {
    const buckets: Record<RiskTier, number> = { low: 0, medium: 0, high: 0 };
    for (const item of decided) buckets[riskTierFor(item.decision!.risk_score)] += 1;
    return buckets;
  }, [decided]);

  const outcomeBuckets = useMemo(() => {
    const buckets = { approve: 0, review: 0, decline: 0 };
    for (const item of decided) buckets[item.decision!.outcome] += 1;
    return buckets;
  }, [decided]);

  const handleLabelAdded = (transactionId: string, label: LabelSummary) => {
    setSelected((previous) =>
      previous && previous.transaction_id === transactionId
        ? { ...previous, labels: [...previous.labels, label] }
        : previous,
    );
  };

  return (
    <div>
      <div
        className="card"
        style={{
          padding: "26px 30px",
          marginBottom: 20,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 20,
          background:
            "radial-gradient(640px 220px at 0% 0%, rgba(91,124,250,0.12), transparent 65%), linear-gradient(135deg, var(--bg-surface-raised) 0%, var(--bg-surface) 100%)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div
            style={{
              width: 44,
              height: 44,
              borderRadius: 12,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "var(--accent-wash)",
              color: "var(--accent-strong)",
              boxShadow: "var(--glow-accent)",
              flexShrink: 0,
            }}
          >
            <ShieldCheck size={22} />
          </div>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: "-0.01em" }}>FraudGuard</h1>
            <p className="page-subtitle" style={{ fontSize: 13.5, marginTop: 2 }}>
              Real-time fraud intelligence
            </p>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center" }}>
          <div style={{ padding: "0 20px" }}>
            <div className="detail-field-label">Status</div>
            <span className={`live-pill${pulse.isLive ? "" : " offline"}`}>
              <span className="live-pill-dot" />
              {pulse.isLive ? "LIVE" : "OFFLINE"}
            </span>
          </div>
          <div style={{ width: 1, height: 32, background: "var(--border)" }} />
          <div style={{ padding: "0 20px" }}>
            <div className="detail-field-label">Current model</div>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontWeight: 560 }}>
              <Cpu size={14} style={{ color: "var(--accent-strong)" }} />
              {pulse.latestModelVersion ?? "—"}
            </span>
          </div>
          <div style={{ width: 1, height: 32, background: "var(--border)" }} />
          <div style={{ padding: "0 0 0 20px" }}>
            <div className="detail-field-label">As of</div>
            <span className="tabular" style={{ color: "var(--text-secondary)" }}>
              {new Date().toLocaleString()}
            </span>
          </div>
        </div>
      </div>

      <div className="kpi-grid">
        <StatCard
          label="Total transactions"
          icon={<Activity size={16} />}
          value={formatCount(kpis.total)}
          meta={all.truncated ? "capped sample" : "observed"}
          loading={all.loading}
        />
        <StatCard
          label="Flagged transactions"
          icon={<ShieldAlert size={16} />}
          value={formatCount(kpis.flagged)}
          meta="review + decline"
          loading={all.loading}
        />
        <StatCard
          label="Fraud rate"
          icon={<AlertTriangle size={16} />}
          value={kpis.fraudRate !== null ? formatPercent(kpis.fraudRate) : "—"}
          meta="declined / decided"
          loading={all.loading}
        />
        <StatCard
          label="Transaction volume"
          icon={<Banknote size={16} />}
          value={formatUsdSumAsInr(kpis.volume)}
          meta="sum of amounts"
          loading={all.loading}
        />
        <StatCard
          label="Approval rate"
          icon={<CheckCircle2 size={16} />}
          value={kpis.approvalRate !== null ? formatPercent(kpis.approvalRate) : "—"}
          meta="approved / decided"
          loading={all.loading}
        />
        <StatCard
          label="Average risk score"
          icon={<Gauge size={16} />}
          value={kpis.avgRisk !== null ? kpis.avgRisk.toFixed(4) : "—"}
          meta="mean, all decisions"
          loading={all.loading}
        />
      </div>

      <div className="section-grid-2" style={{ marginBottom: 20 }}>
        <div className="card">
          <div className="card-header">
            <span className="card-title">Risk distribution</span>
            <span className="page-subtitle">{formatCount(decided.length)} decided</span>
          </div>
          <div className="card-body">
            <div style={{ marginBottom: 18 }}>
              <SegmentedBar
                segments={(["low", "medium", "high"] as RiskTier[]).map((tier) => ({
                  color: RISK_TIER_COLOR[tier],
                  pct: decided.length > 0 ? riskBuckets[tier] / decided.length : 0,
                }))}
              />
            </div>
            {(["low", "medium", "high"] as RiskTier[]).map((tier) => {
              const count = riskBuckets[tier];
              const pct = decided.length > 0 ? count / decided.length : 0;
              const Icon = RISK_TIER_ICON[tier];
              return (
                <div
                  key={tier}
                  style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 0" }}
                >
                  <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <Icon size={14} style={{ color: RISK_TIER_COLOR[tier] }} />
                    {RISK_TIER_LABEL[tier]}
                  </span>
                  <span className="tabular" style={{ fontWeight: 600 }}>
                    {formatCount(count)}
                    <span style={{ color: "var(--text-muted)", fontWeight: 500, marginLeft: 6 }}>
                      {formatPercent(pct)}
                    </span>
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <span className="card-title">Decision outcomes</span>
            <span className="page-subtitle">{formatCount(decided.length)} decided</span>
          </div>
          <div className="card-body">
            <div style={{ marginBottom: 18 }}>
              <SegmentedBar
                segments={[
                  { color: "var(--status-good)", pct: decided.length > 0 ? outcomeBuckets.approve / decided.length : 0 },
                  { color: "var(--status-warning)", pct: decided.length > 0 ? outcomeBuckets.review / decided.length : 0 },
                  { color: "var(--status-critical)", pct: decided.length > 0 ? outcomeBuckets.decline / decided.length : 0 },
                ]}
              />
            </div>
            {(
              [
                ["approve", "var(--status-good)", CheckCircle2],
                ["review", "var(--status-warning)", CircleHelp],
                ["decline", "var(--status-critical)", XCircle],
              ] as [keyof typeof outcomeBuckets, string, typeof CheckCircle2][]
            ).map(([outcome, color, Icon]) => {
              const count = outcomeBuckets[outcome];
              const pct = decided.length > 0 ? count / decided.length : 0;
              return (
                <div
                  key={outcome}
                  style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 0" }}
                >
                  <span style={{ display: "flex", alignItems: "center", gap: 8, textTransform: "capitalize" }}>
                    <Icon size={14} style={{ color }} />
                    {outcome}
                  </span>
                  <span className="tabular" style={{ fontWeight: 600 }}>
                    {formatCount(count)}
                    <span style={{ color: "var(--text-muted)", fontWeight: 500, marginLeft: 6 }}>
                      {formatPercent(pct)}
                    </span>
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title" style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <TrendingUp size={15} />
            Live transaction stream
          </span>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => navigate("/transactions")}>
            View all
          </button>
        </div>
        <TransactionsTable
          items={live.items}
          loading={live.loading}
          sortable={false}
          onRowClick={setSelected}
          emptyMessage="Run the simulator to generate live traffic."
        />
      </div>

      <TransactionDrawer item={selected} onClose={() => setSelected(null)} onLabelAdded={handleLabelAdded} />
    </div>
  );
}

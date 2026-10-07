import { useMemo, useState, type ReactNode } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ErrorStatePanel } from "../components/common/StatePanels";
import { EmptyState } from "../components/common/StatePanels";
import { useAllTransactions } from "../hooks/useAllTransactions";
import {
  bucketByAmount,
  bucketByTime,
  countBy,
  filterByRange,
  topBy,
  type TimeRange,
} from "../lib/analytics";
import { labelForReasonCode } from "../lib/reasonCodes";
import { riskTierFor } from "../lib/risk";

const CHART_GRID_COLOR = "var(--border)";
const CHART_TEXT_COLOR = "var(--text-muted)";
const TOOLTIP_STYLE = {
  background: "var(--bg-surface-raised)",
  border: "1px solid var(--border-strong)",
  borderRadius: 8,
  fontSize: 12,
  color: "var(--text-primary)",
};

const OUTCOME_COLOR: Record<string, string> = {
  approve: "var(--status-good)",
  review: "var(--status-warning)",
  decline: "var(--status-critical)",
};

const RISK_COLOR: Record<string, string> = {
  low: "var(--status-good)",
  medium: "var(--status-warning)",
  high: "var(--status-critical)",
};

const CATEGORICAL = ["var(--cat-1)", "var(--cat-2)", "var(--cat-3)", "var(--cat-4)", "var(--cat-5)"];

function ChartCard({ title, children, subtitle }: { title: string; children: ReactNode; subtitle?: string }) {
  return (
    <div className="card">
      <div className="card-header">
        <div>
          <span className="card-title">{title}</span>
          {subtitle && <p className="page-subtitle" style={{ marginTop: 2 }}>{subtitle}</p>}
        </div>
      </div>
      <div className="card-body">{children}</div>
    </div>
  );
}

export function AnalyticsPage() {
  const { items, loading, error, refetch, truncated } = useAllTransactions();
  const [range, setRange] = useState<TimeRange>("7d");

  const scoped = useMemo(() => filterByRange(items, range), [items, range]);
  const decided = useMemo(() => scoped.filter((item) => item.decision !== null), [scoped]);

  const volumeSeries = useMemo(() => bucketByTime(scoped, range), [scoped, range]);

  const outcomeData = useMemo(() => {
    const counts = countBy(decided, (item) => item.decision!.outcome);
    return (["approve", "review", "decline"] as const).map((outcome) => ({
      outcome,
      count: counts[outcome] ?? 0,
    }));
  }, [decided]);

  const riskData = useMemo(() => {
    const counts = countBy(decided, (item) => riskTierFor(item.decision!.risk_score));
    return (["low", "medium", "high"] as const).map((tier) => ({ tier, count: counts[tier] ?? 0 }));
  }, [decided]);

  const labelData = useMemo(() => {
    const labeled = scoped.filter((item) => item.labels.length > 0);
    let fraud = 0;
    let legitimate = 0;
    for (const item of labeled) {
      for (const label of item.labels) {
        if (label.is_fraud) fraud += 1;
        else legitimate += 1;
      }
    }
    return { labeled: labeled.length, fraud, legitimate };
  }, [scoped]);

  const topMerchants = useMemo(
    () =>
      topBy(
        countBy(
          decided.filter((item) => item.decision!.outcome !== "approve"),
          (item) => item.merchant_id,
        ),
        8,
      ),
    [decided],
  );

  const reasonCodeFrequency = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const item of decided) {
      for (const code of item.decision!.reason_codes ?? []) {
        counts[code] = (counts[code] ?? 0) + 1;
      }
    }
    return topBy(counts, 8).map((entry) => ({ ...entry, label: labelForReasonCode(entry.name) }));
  }, [decided]);

  const amountBuckets = useMemo(() => bucketByAmount(scoped), [scoped]);

  if (error && !loading) {
    return <ErrorStatePanel message={error} onRetry={refetch} />;
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Analytics</div>
          <div className="page-subtitle">
            Computed from {scoped.length} transactions in range
            {truncated && " (capped sample of most recent history)"}.
          </div>
        </div>
        <div className="segmented-control">
          {(["24h", "7d", "30d"] as TimeRange[]).map((value) => (
            <button
              key={value}
              type="button"
              className={range === value ? "active" : ""}
              onClick={() => setRange(value)}
            >
              {value.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      <div style={{ marginBottom: 16 }}>
        <ChartCard title="Transaction volume over time" subtitle="Count of transactions per bucket, real occurred_at timestamps">
          {loading ? (
            <div className="skeleton" style={{ height: 220, width: "100%" }} />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={volumeSeries} margin={{ left: -16, right: 8 }}>
                <defs>
                  <linearGradient id="volumeFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="var(--accent)" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                <XAxis dataKey="label" stroke={CHART_TEXT_COLOR} fontSize={11} tickLine={false} axisLine={false} />
                <YAxis stroke={CHART_TEXT_COLOR} fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
                <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ stroke: "var(--border-strong)" }} />
                <Area
                  type="monotone"
                  dataKey="count"
                  stroke="var(--accent)"
                  strokeWidth={2}
                  fill="url(#volumeFill)"
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </ChartCard>
      </div>

      <div className="section-grid-2" style={{ marginBottom: 16 }}>
        <ChartCard title="Decision outcomes">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={outcomeData} layout="vertical" margin={{ left: 8 }}>
              <CartesianGrid stroke={CHART_GRID_COLOR} horizontal={false} />
              <XAxis type="number" stroke={CHART_TEXT_COLOR} fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
              <YAxis
                type="category"
                dataKey="outcome"
                stroke={CHART_TEXT_COLOR}
                fontSize={11}
                tickLine={false}
                axisLine={false}
                width={70}
                style={{ textTransform: "capitalize" }}
              />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "var(--bg-surface-hover)" }} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]} maxBarSize={28}>
                {outcomeData.map((entry) => (
                  <Cell key={entry.outcome} fill={OUTCOME_COLOR[entry.outcome]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Risk distribution">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={riskData} layout="vertical" margin={{ left: 8 }}>
              <CartesianGrid stroke={CHART_GRID_COLOR} horizontal={false} />
              <XAxis type="number" stroke={CHART_TEXT_COLOR} fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
              <YAxis
                type="category"
                dataKey="tier"
                stroke={CHART_TEXT_COLOR}
                fontSize={11}
                tickLine={false}
                axisLine={false}
                width={70}
                style={{ textTransform: "capitalize" }}
              />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "var(--bg-surface-hover)" }} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]} maxBarSize={28}>
                {riskData.map((entry) => (
                  <Cell key={entry.tier} fill={RISK_COLOR[entry.tier]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="section-grid-2" style={{ marginBottom: 16 }}>
        <ChartCard
          title="Fraud vs. legitimate (labeled only)"
          subtitle={labelData.labeled === 0 ? undefined : `${labelData.labeled} transactions have at least one label`}
        >
          {labelData.labeled === 0 ? (
            <EmptyState
              title="No ground-truth labels yet"
              description="Label transactions from the Transactions page to populate this chart."
            />
          ) : (
            <ResponsiveContainer width="100%" height={160}>
              <BarChart
                data={[
                  { kind: "Fraud", count: labelData.fraud },
                  { kind: "Legitimate", count: labelData.legitimate },
                ]}
                layout="vertical"
                margin={{ left: 8 }}
              >
                <CartesianGrid stroke={CHART_GRID_COLOR} horizontal={false} />
                <XAxis type="number" stroke={CHART_TEXT_COLOR} fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
                <YAxis type="category" dataKey="kind" stroke={CHART_TEXT_COLOR} fontSize={11} tickLine={false} axisLine={false} width={70} />
                <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "var(--bg-surface-hover)" }} />
                <Bar dataKey="count" radius={[0, 4, 4, 0]} maxBarSize={28}>
                  <Cell fill="var(--status-critical)" />
                  <Cell fill="var(--status-good)" />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="Transaction amount distribution">
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={amountBuckets} margin={{ left: -16 }}>
              <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
              <XAxis dataKey="label" stroke={CHART_TEXT_COLOR} fontSize={10} tickLine={false} axisLine={false} />
              <YAxis stroke={CHART_TEXT_COLOR} fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "var(--bg-surface-hover)" }} />
              <Bar dataKey="count" fill="var(--cat-1)" radius={[4, 4, 0, 0]} maxBarSize={32} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="section-grid-2">
        <ChartCard title="High-risk merchants" subtitle="By review + decline count">
          {topMerchants.length === 0 ? (
            <EmptyState title="No flagged merchants in range" />
          ) : (
            <ResponsiveContainer width="100%" height={Math.max(160, topMerchants.length * 28)}>
              <BarChart data={topMerchants} layout="vertical" margin={{ left: 8 }}>
                <CartesianGrid stroke={CHART_GRID_COLOR} horizontal={false} />
                <XAxis type="number" stroke={CHART_TEXT_COLOR} fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
                <YAxis type="category" dataKey="name" stroke={CHART_TEXT_COLOR} fontSize={11} tickLine={false} axisLine={false} width={90} />
                <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "var(--bg-surface-hover)" }} />
                <Bar dataKey="count" fill="var(--status-serious)" radius={[0, 4, 4, 0]} maxBarSize={20} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="Reason-code frequency" subtitle="Which features most often drive a decision">
          {reasonCodeFrequency.length === 0 ? (
            <EmptyState title="No model-scored decisions in range" />
          ) : (
            <ResponsiveContainer width="100%" height={Math.max(160, reasonCodeFrequency.length * 28)}>
              <BarChart data={reasonCodeFrequency} layout="vertical" margin={{ left: 8 }}>
                <CartesianGrid stroke={CHART_GRID_COLOR} horizontal={false} />
                <XAxis type="number" stroke={CHART_TEXT_COLOR} fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
                <YAxis type="category" dataKey="label" stroke={CHART_TEXT_COLOR} fontSize={11} tickLine={false} axisLine={false} width={140} />
                <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "var(--bg-surface-hover)" }} />
                <Bar dataKey="count" radius={[0, 4, 4, 0]} maxBarSize={20}>
                  {reasonCodeFrequency.map((entry, index) => (
                    <Cell key={entry.name} fill={CATEGORICAL[index % CATEGORICAL.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>
      </div>
    </div>
  );
}

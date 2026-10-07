import { useMemo, useState } from "react";
import { ErrorStatePanel } from "../components/common/StatePanels";
import { TransactionDrawer } from "../components/transactions/TransactionDrawer";
import { TransactionsTable } from "../components/transactions/TransactionsTable";
import { useAllTransactions } from "../hooks/useAllTransactions";
import { formatCount } from "../lib/format";
import { riskTierFor } from "../lib/risk";
import type { LabelSummary, TransactionFeedItem } from "../types";

type GroupKey = "high_risk" | "needs_review" | "recently_flagged" | "manually_labeled";

const RECENT_WINDOW_MS = 24 * 60 * 60 * 1000;

const GROUPS: { key: GroupKey; label: string; description: string }[] = [
  {
    key: "high_risk",
    label: "High risk",
    description: "Decisions with risk_score above the model's own decline threshold (0.7).",
  },
  {
    key: "needs_review",
    label: "Needs review",
    description: "Decisions the model itself returned as \"review\" -- between the approve and decline thresholds.",
  },
  {
    key: "recently_flagged",
    label: "Recently flagged",
    description: "Review or decline outcomes from the last 24 hours.",
  },
  {
    key: "manually_labeled",
    label: "Manually labeled",
    description: "Transactions with at least one operator-submitted ground-truth label.",
  },
];

function groupItems(items: TransactionFeedItem[], key: GroupKey): TransactionFeedItem[] {
  const now = Date.now();
  switch (key) {
    case "high_risk":
      return items.filter((item) => item.decision && riskTierFor(item.decision.risk_score) === "high");
    case "needs_review":
      return items.filter((item) => item.decision?.outcome === "review");
    case "recently_flagged":
      return items.filter(
        (item) =>
          item.decision &&
          item.decision.outcome !== "approve" &&
          now - new Date(item.occurred_at).getTime() <= RECENT_WINDOW_MS,
      );
    case "manually_labeled":
      return items.filter((item) => item.labels.length > 0);
  }
}

export function InvestigationsPage() {
  const { items, loading, error, refetch } = useAllTransactions();
  const [active, setActive] = useState<GroupKey>("high_risk");
  const [selected, setSelected] = useState<TransactionFeedItem | null>(null);

  const counts = useMemo(() => {
    const result: Record<GroupKey, number> = {
      high_risk: 0,
      needs_review: 0,
      recently_flagged: 0,
      manually_labeled: 0,
    };
    for (const group of GROUPS) result[group.key] = groupItems(items, group.key).length;
    return result;
  }, [items]);

  const activeItems = useMemo(() => groupItems(items, active), [items, active]);
  const activeGroup = GROUPS.find((group) => group.key === active)!;

  const handleLabelAdded = (transactionId: string, label: LabelSummary) => {
    setSelected((previous) =>
      previous && previous.transaction_id === transactionId
        ? { ...previous, labels: [...previous.labels, label] }
        : previous,
    );
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Investigations</div>
          <div className="page-subtitle">Real-data groupings for triage, not a separate queue system.</div>
        </div>
      </div>

      <div className="kpi-grid">
        {GROUPS.map((group) => (
          <button
            key={group.key}
            type="button"
            className="stat-card"
            style={{
              textAlign: "left",
              cursor: "pointer",
              border: active === group.key ? "1px solid var(--accent)" : undefined,
            }}
            onClick={() => setActive(group.key)}
          >
            <span className="stat-card-label">{group.label}</span>
            <span className="stat-card-value">{formatCount(counts[group.key])}</span>
          </button>
        ))}
      </div>

      <div className="card">
        <div className="card-header">
          <div>
            <span className="card-title">{activeGroup.label}</span>
            <p className="page-subtitle" style={{ marginTop: 3 }}>
              {activeGroup.description}
            </p>
          </div>
        </div>
        {error && !loading ? (
          <ErrorStatePanel message={error} onRetry={refetch} />
        ) : (
          <TransactionsTable
            items={activeItems}
            loading={loading}
            onRowClick={setSelected}
            emptyMessage="Nothing in this group right now."
          />
        )}
      </div>

      <TransactionDrawer item={selected} onClose={() => setSelected(null)} onLabelAdded={handleLabelAdded} />
    </div>
  );
}

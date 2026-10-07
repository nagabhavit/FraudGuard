import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { useMemo, useState } from "react";
import { formatAmount, formatTime, shortId } from "../../lib/format";
import { statusRoleForOutcome } from "../../lib/risk";
import type { TransactionFeedItem } from "../../types";
import { StatusBadge } from "../common/StatusBadge";
import { TableSkeletonRows } from "../common/Skeleton";
import { EmptyState } from "../common/StatePanels";
import { RiskMeter } from "./RiskMeter";

type SortKey = "time" | "amount" | "risk" | "outcome";
type SortDirection = "asc" | "desc";

const SORTABLE_COLUMNS: { key: SortKey; label: string }[] = [
  { key: "time", label: "Time" },
  { key: "amount", label: "Amount" },
  { key: "risk", label: "Risk score" },
  { key: "outcome", label: "Decision" },
];

function sortValue(item: TransactionFeedItem, key: SortKey): number {
  switch (key) {
    case "time":
      return new Date(item.occurred_at).getTime();
    case "amount":
      return Number(item.amount);
    case "risk":
      return item.decision?.risk_score ?? -1;
    case "outcome": {
      const order = { approve: 0, review: 1, decline: 2 };
      return item.decision ? order[item.decision.outcome] : -1;
    }
  }
}

export function TransactionsTable({
  items,
  loading,
  onRowClick,
  sortable = true,
  emptyMessage = "No transactions yet.",
}: {
  items: TransactionFeedItem[];
  loading?: boolean;
  onRowClick?: (item: TransactionFeedItem) => void;
  sortable?: boolean;
  emptyMessage?: string;
}) {
  const [sort, setSort] = useState<{ key: SortKey; direction: SortDirection } | null>(null);

  const sorted = useMemo(() => {
    if (!sort) return items;
    const factor = sort.direction === "asc" ? 1 : -1;
    return [...items].sort((a, b) => factor * (sortValue(a, sort.key) - sortValue(b, sort.key)));
  }, [items, sort]);

  const toggleSort = (key: SortKey) => {
    setSort((previous) => {
      if (!previous || previous.key !== key) return { key, direction: "desc" };
      return { key, direction: previous.direction === "desc" ? "asc" : "desc" };
    });
  };

  const sortIcon = (key: SortKey) => {
    if (!sort || sort.key !== key) return <ArrowUpDown size={12} />;
    return sort.direction === "desc" ? <ArrowDown size={12} /> : <ArrowUp size={12} />;
  };

  if (!loading && items.length === 0) {
    return <EmptyState title="No transactions found" description={emptyMessage} />;
  }

  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {["Time", "Account", "Merchant", "Amount", "Risk score", "Decision", "Model", "Reason codes", "Label"].map(
              (label) => {
                const column = SORTABLE_COLUMNS.find((c) => c.label === label);
                if (sortable && column) {
                  return (
                    <th key={label} className="sortable" onClick={() => toggleSort(column.key)}>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                        {label}
                        {sortIcon(column.key)}
                      </span>
                    </th>
                  );
                }
                return <th key={label}>{label}</th>;
              },
            )}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <TableSkeletonRows columns={9} rows={8} />
          ) : (
            sorted.map((item) => {
              const decision = item.decision;
              return (
                <tr key={item.transaction_id} onClick={() => onRowClick?.(item)}>
                  <td>{formatTime(item.occurred_at)}</td>
                  <td className="mono">{shortId(item.account_id)}</td>
                  <td>{item.merchant_id}</td>
                  <td className="numeric">{formatAmount(item.amount, item.currency)}</td>
                  <td>{decision ? <RiskMeter riskScore={decision.risk_score} compact /> : "—"}</td>
                  <td>
                    {decision ? (
                      <StatusBadge
                        label={decision.outcome}
                        role={statusRoleForOutcome(decision.outcome)}
                      />
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>{decision?.model_version ?? "fallback rule"}</td>
                  <td className="wrap">
                    {decision?.reason_codes && decision.reason_codes.length > 0 ? (
                      <span className="reason-chip-row">
                        {decision.reason_codes.map((code) => (
                          <span className="reason-chip" key={code}>
                            {code}
                          </span>
                        ))}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>
                    {item.labels.length > 0 ? (
                      <StatusBadge
                        label={item.labels.some((label) => label.is_fraud) ? "fraud" : "not fraud"}
                        role={item.labels.some((label) => label.is_fraud) ? "critical" : "good"}
                      />
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

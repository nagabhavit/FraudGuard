import { RefreshCw, Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ErrorStatePanel } from "../components/common/StatePanels";
import { TransactionDrawer } from "../components/transactions/TransactionDrawer";
import { TransactionsTable } from "../components/transactions/TransactionsTable";
import { useAllTransactions } from "../hooks/useAllTransactions";
import { formatCount } from "../lib/format";
import { riskTierFor, type RiskTier } from "../lib/risk";
import type { DecisionOutcome, LabelSummary, TransactionFeedItem } from "../types";

type DateRange = "all" | "1h" | "24h" | "7d";

const DATE_RANGE_MS: Record<DateRange, number | null> = {
  all: null,
  "1h": 60 * 60 * 1000,
  "24h": 24 * 60 * 60 * 1000,
  "7d": 7 * 24 * 60 * 60 * 1000,
};

interface Filters {
  search: string;
  decision: "all" | DecisionOutcome;
  risk: "all" | RiskTier;
  merchant: string;
  account: string;
  model: string;
  dateRange: DateRange;
}

const DEFAULT_FILTERS: Filters = {
  search: "",
  decision: "all",
  risk: "all",
  merchant: "all",
  account: "",
  model: "all",
  dateRange: "all",
};

export function TransactionsPage() {
  const { items, loading, error, truncated, lastUpdated, refetch } = useAllTransactions();
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFilters] = useState<Filters>(() => ({
    ...DEFAULT_FILTERS,
    search: searchParams.get("search") ?? "",
  }));
  const [selected, setSelected] = useState<TransactionFeedItem | null>(null);

  // A search arriving via the top bar (?search=...) should populate the
  // filter once, not fight the user's own edits afterward -- only adopt it
  // when the URL param actually changes.
  useEffect(() => {
    const fromUrl = searchParams.get("search");
    if (fromUrl !== null) setFilters((previous) => ({ ...previous, search: fromUrl }));
  }, [searchParams]);

  const merchantOptions = useMemo(
    () => Array.from(new Set(items.map((item) => item.merchant_id))).sort(),
    [items],
  );
  const modelOptions = useMemo(() => {
    const versions = new Set<string>();
    for (const item of items) if (item.decision?.model_version) versions.add(item.decision.model_version);
    return Array.from(versions).sort();
  }, [items]);

  const filtered = useMemo(() => {
    const now = Date.now();
    const windowMs = DATE_RANGE_MS[filters.dateRange];
    const search = filters.search.trim().toLowerCase();

    return items.filter((item) => {
      if (windowMs !== null && now - new Date(item.occurred_at).getTime() > windowMs) return false;
      if (filters.decision !== "all" && item.decision?.outcome !== filters.decision) return false;
      if (filters.risk !== "all") {
        if (!item.decision || riskTierFor(item.decision.risk_score) !== filters.risk) return false;
      }
      if (filters.merchant !== "all" && item.merchant_id !== filters.merchant) return false;
      if (filters.account && !item.account_id.toLowerCase().startsWith(filters.account.toLowerCase()))
        return false;
      if (filters.model !== "all") {
        if (filters.model === "fallback") {
          if (item.decision?.model_version) return false;
        } else if (item.decision?.model_version !== filters.model) {
          return false;
        }
      }
      if (search) {
        const haystack = `${item.transaction_id} ${item.account_id} ${item.merchant_id}`.toLowerCase();
        if (!haystack.includes(search)) return false;
      }
      return true;
    });
  }, [items, filters]);

  const setFilter = <K extends keyof Filters>(key: K, value: Filters[K]) => {
    setFilters((previous) => ({ ...previous, [key]: value }));
    if (key === "search") {
      const next = new URLSearchParams(searchParams);
      if (value) next.set("search", String(value));
      else next.delete("search");
      setSearchParams(next, { replace: true });
    }
  };

  const clearAll = () => {
    setFilters(DEFAULT_FILTERS);
    setSearchParams({}, { replace: true });
  };

  const chips: { key: keyof Filters; label: string }[] = [];
  if (filters.search) chips.push({ key: "search", label: `Search: "${filters.search}"` });
  if (filters.decision !== "all") chips.push({ key: "decision", label: `Decision: ${filters.decision}` });
  if (filters.risk !== "all") chips.push({ key: "risk", label: `Risk: ${filters.risk}` });
  if (filters.merchant !== "all") chips.push({ key: "merchant", label: `Merchant: ${filters.merchant}` });
  if (filters.account) chips.push({ key: "account", label: `Account: ${filters.account}` });
  if (filters.model !== "all")
    chips.push({ key: "model", label: `Model: ${filters.model === "fallback" ? "fallback rule" : filters.model}` });
  if (filters.dateRange !== "all") chips.push({ key: "dateRange", label: `Range: ${filters.dateRange}` });

  const removeChip = (key: keyof Filters) => setFilter(key, DEFAULT_FILTERS[key] as Filters[typeof key]);

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
          <div className="page-title">Transactions</div>
          <div className="page-subtitle">
            {formatCount(filtered.length)} of {formatCount(items.length)} transactions
            {truncated && " (capped sample of most recent history)"}
            {lastUpdated && ` · updated ${lastUpdated.toLocaleTimeString()}`}
          </div>
        </div>
        <button type="button" className="btn btn-sm" onClick={refetch}>
          <RefreshCw size={13} />
          Refresh
        </button>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-body">
          <div className="filter-bar" style={{ marginBottom: chips.length > 0 ? 10 : 0 }}>
            <div className="topbar-search" style={{ maxWidth: 260 }}>
              <Search size={14} />
              <input
                placeholder="Search ID, account, merchant…"
                value={filters.search}
                onChange={(event) => setFilter("search", event.target.value)}
              />
            </div>

            <select value={filters.decision} onChange={(event) => setFilter("decision", event.target.value as Filters["decision"])}>
              <option value="all">All decisions</option>
              <option value="approve">Approve</option>
              <option value="review">Review</option>
              <option value="decline">Decline</option>
            </select>

            <select value={filters.risk} onChange={(event) => setFilter("risk", event.target.value as Filters["risk"])}>
              <option value="all">All risk tiers</option>
              <option value="low">Low risk</option>
              <option value="medium">Medium risk</option>
              <option value="high">High risk</option>
            </select>

            <select value={filters.merchant} onChange={(event) => setFilter("merchant", event.target.value)}>
              <option value="all">All merchants</option>
              {merchantOptions.map((merchant) => (
                <option key={merchant} value={merchant}>
                  {merchant}
                </option>
              ))}
            </select>

            <input
              placeholder="Account ID prefix…"
              value={filters.account}
              onChange={(event) => setFilter("account", event.target.value)}
              style={{ width: 160 }}
            />

            <select value={filters.model} onChange={(event) => setFilter("model", event.target.value)}>
              <option value="all">All models</option>
              <option value="fallback">Fallback rule</option>
              {modelOptions.map((version) => (
                <option key={version} value={version}>
                  {version}
                </option>
              ))}
            </select>

            <select
              value={filters.dateRange}
              onChange={(event) => setFilter("dateRange", event.target.value as DateRange)}
            >
              <option value="all">All time</option>
              <option value="1h">Last hour</option>
              <option value="24h">Last 24 hours</option>
              <option value="7d">Last 7 days</option>
            </select>

            {chips.length > 0 && (
              <button type="button" className="btn btn-ghost btn-sm" onClick={clearAll}>
                Clear filters
              </button>
            )}
          </div>

          {chips.length > 0 && (
            <div className="filter-bar">
              {chips.map((chip) => (
                <span key={chip.key} className="filter-chip">
                  {chip.label}
                  <button type="button" onClick={() => removeChip(chip.key)} aria-label={`Remove ${chip.label} filter`}>
                    <X size={11} />
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="card">
        {error && !loading ? (
          <ErrorStatePanel message={error} onRetry={refetch} />
        ) : (
          <TransactionsTable
            items={filtered}
            loading={loading}
            onRowClick={setSelected}
            emptyMessage="No transactions match the current filters."
          />
        )}
      </div>

      <TransactionDrawer item={selected} onClose={() => setSelected(null)} onLabelAdded={handleLabelAdded} />
    </div>
  );
}

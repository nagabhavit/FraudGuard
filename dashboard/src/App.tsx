import { useEffect, useState } from "react";
import { fetchTransactions } from "./api";
import type { DecisionOutcome, TransactionFeedItem } from "./types";

const POLL_INTERVAL_MS = 5000;
const PAGE_SIZE = 50;

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString();
}

function OutcomeBadge({ outcome }: { outcome: DecisionOutcome }) {
  return <span className={`badge badge-${outcome}`}>{outcome}</span>;
}

function TransactionRow({ item }: { item: TransactionFeedItem }) {
  const decision = item.decision;
  return (
    <tr>
      <td>{formatTime(item.occurred_at)}</td>
      <td className="mono">{item.account_id.slice(0, 8)}</td>
      <td>{item.merchant_id}</td>
      <td className="numeric">
        {item.amount} {item.currency}
      </td>
      <td>{decision ? <OutcomeBadge outcome={decision.outcome} /> : "—"}</td>
      <td className="numeric">
        {decision ? decision.risk_score.toFixed(4) : "—"}
      </td>
      <td>{decision?.model_version ?? "fallback rule"}</td>
      <td>{decision?.reason_codes?.join(", ") ?? "—"}</td>
    </tr>
  );
}

function App() {
  const [items, setItems] = useState<TransactionFeedItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    const poll = async () => {
      try {
        const page = await fetchTransactions({
          limit: PAGE_SIZE,
          signal: controller.signal,
        });
        setItems(page.items);
        setError(null);
        setLastUpdated(new Date());
      } catch (err) {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : "failed to load");
      }
    };

    void poll();
    const interval = setInterval(() => void poll(), POLL_INTERVAL_MS);
    return () => {
      controller.abort();
      clearInterval(interval);
    };
  }, []);

  return (
    <main>
      <header>
        <h1>FraudGuard</h1>
        <p className="subtitle">
          Recent transactions, most recent first. Refreshes every{" "}
          {POLL_INTERVAL_MS / 1000}s.
          {lastUpdated && (
            <span className="last-updated">
              {" "}
              Last updated {lastUpdated.toLocaleTimeString()}
            </span>
          )}
        </p>
      </header>

      {error && <p className="error">Could not reach the gateway: {error}</p>}

      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Account</th>
            <th>Merchant</th>
            <th>Amount</th>
            <th>Outcome</th>
            <th>Risk score</th>
            <th>Model</th>
            <th>Reason codes</th>
          </tr>
        </thead>
        <tbody>
          {items.length === 0 && !error ? (
            <tr>
              <td colSpan={8} className="empty">
                No transactions yet.
              </td>
            </tr>
          ) : (
            items.map((item) => (
              <TransactionRow key={item.transaction_id} item={item} />
            ))
          )}
        </tbody>
      </table>
    </main>
  );
}

export default App;

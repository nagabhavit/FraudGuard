import { useEffect, useState, type FormEvent } from "react";
import { createLabel, fetchTransactions } from "./api";
import type {
  DecisionOutcome,
  LabelSource,
  LabelSummary,
  TransactionFeedItem,
} from "./types";

const POLL_INTERVAL_MS = 5000;
const PAGE_SIZE = 50;

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString();
}

function OutcomeBadge({ outcome }: { outcome: DecisionOutcome }) {
  return <span className={`badge badge-${outcome}`}>{outcome}</span>;
}

function LabelBadge({ label }: { label: LabelSummary }) {
  const text = `${label.is_fraud ? "fraud" : "not fraud"} (${label.source})`;
  return (
    <span className={`badge ${label.is_fraud ? "badge-decline" : "badge-approve"}`}>
      {text}
    </span>
  );
}

const LABEL_SOURCES: LabelSource[] = [
  "manual_review",
  "chargeback",
  "customer_report",
];

function LabelForm({
  transactionId,
  onSubmitted,
  onCancel,
}: {
  transactionId: string;
  onSubmitted: (label: LabelSummary) => void;
  onCancel: () => void;
}) {
  const [isFraud, setIsFraud] = useState(true);
  const [source, setSource] = useState<LabelSource>("manual_review");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const label = await createLabel(transactionId, {
        is_fraud: isFraud,
        source,
        notes: notes.trim() === "" ? null : notes.trim(),
      });
      onSubmitted(label);
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to submit label");
      setSubmitting(false);
    }
  };

  return (
    <form className="label-form" onSubmit={(event) => void handleSubmit(event)}>
      <select
        value={isFraud ? "fraud" : "not_fraud"}
        onChange={(event) => setIsFraud(event.target.value === "fraud")}
        disabled={submitting}
      >
        <option value="fraud">Fraud</option>
        <option value="not_fraud">Not fraud</option>
      </select>
      <select
        value={source}
        onChange={(event) => setSource(event.target.value as LabelSource)}
        disabled={submitting}
      >
        {LABEL_SOURCES.map((value) => (
          <option key={value} value={value}>
            {value.replace("_", " ")}
          </option>
        ))}
      </select>
      <input
        type="text"
        placeholder="Notes (optional)"
        value={notes}
        onChange={(event) => setNotes(event.target.value)}
        disabled={submitting}
      />
      <button type="submit" disabled={submitting}>
        {submitting ? "Submitting…" : "Submit"}
      </button>
      <button type="button" onClick={onCancel} disabled={submitting}>
        Cancel
      </button>
      {error && <p className="error label-error">{error}</p>}
    </form>
  );
}

function LabelsCell({
  item,
  onLabelAdded,
}: {
  item: TransactionFeedItem;
  onLabelAdded: (transactionId: string, label: LabelSummary) => void;
}) {
  const [formOpen, setFormOpen] = useState(false);

  return (
    <td className="labels-cell">
      {item.labels.map((label) => (
        <LabelBadge key={label.id} label={label} />
      ))}
      {formOpen ? (
        <LabelForm
          transactionId={item.transaction_id}
          onSubmitted={(label) => {
            onLabelAdded(item.transaction_id, label);
            setFormOpen(false);
          }}
          onCancel={() => setFormOpen(false)}
        />
      ) : (
        <button
          type="button"
          className="add-label-button"
          onClick={() => setFormOpen(true)}
        >
          + label
        </button>
      )}
    </td>
  );
}

function TransactionRow({
  item,
  onLabelAdded,
}: {
  item: TransactionFeedItem;
  onLabelAdded: (transactionId: string, label: LabelSummary) => void;
}) {
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
      <LabelsCell item={item} onLabelAdded={onLabelAdded} />
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

  const handleLabelAdded = (transactionId: string, label: LabelSummary) => {
    setItems((prev) =>
      prev.map((item) =>
        item.transaction_id === transactionId
          ? { ...item, labels: [...item.labels, label] }
          : item,
      ),
    );
  };

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
            <th>Labels</th>
          </tr>
        </thead>
        <tbody>
          {items.length === 0 && !error ? (
            <tr>
              <td colSpan={9} className="empty">
                No transactions yet.
              </td>
            </tr>
          ) : (
            items.map((item) => (
              <TransactionRow
                key={item.transaction_id}
                item={item}
                onLabelAdded={handleLabelAdded}
              />
            ))
          )}
        </tbody>
      </table>
    </main>
  );
}

export default App;

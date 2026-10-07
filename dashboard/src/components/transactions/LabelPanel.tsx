import { CircleHelp, ShieldCheck, ShieldX } from "lucide-react";
import { useState, type FormEvent } from "react";
import { createLabel } from "../../api";
import { useToast } from "../common/ToastProvider";
import { StatusBadge } from "../common/StatusBadge";
import type { LabelSource, LabelSummary } from "../../types";

const LABEL_SOURCES: LabelSource[] = ["manual_review", "chargeback", "customer_report"];

/** The gateway's Label schema (gateway/labels.py) is a strict boolean --
 * is_fraud: true/false, plus a source and optional notes. There is no
 * third, persisted "needs review" state in the backend to map a literal
 * third button onto without inventing one. "Needs Review" is therefore
 * the detailed form (source + notes) for a deliberate submission; "Mark
 * Legitimate" and "Confirm Fraud" are one-click shortcuts for the two
 * states the API actually has. Nothing here adds a new backend concept. */
export function LabelPanel({
  transactionId,
  labels,
  onLabelAdded,
}: {
  transactionId: string;
  labels: LabelSummary[];
  onLabelAdded: (label: LabelSummary) => void;
}) {
  const { notify } = useToast();
  const [submitting, setSubmitting] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [isFraud, setIsFraud] = useState(true);
  const [source, setSource] = useState<LabelSource>("manual_review");
  const [notes, setNotes] = useState("");

  const submit = async (payloadIsFraud: boolean, payloadSource: LabelSource, payloadNotes: string | null) => {
    setSubmitting(true);
    try {
      const label = await createLabel(transactionId, {
        is_fraud: payloadIsFraud,
        source: payloadSource,
        notes: payloadNotes,
      });
      onLabelAdded(label);
      notify("success", payloadIsFraud ? "Marked as fraud" : "Marked as legitimate");
      setFormOpen(false);
      setNotes("");
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Failed to submit label");
    } finally {
      setSubmitting(false);
    }
  };

  const handleFormSubmit = (event: FormEvent) => {
    event.preventDefault();
    void submit(isFraud, source, notes.trim() === "" ? null : notes.trim());
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {labels.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {labels.map((label) => (
            <StatusBadge
              key={label.id}
              label={`${label.is_fraud ? "Fraud" : "Legitimate"} · ${label.source.replace("_", " ")}`}
              role={label.is_fraud ? "critical" : "good"}
            />
          ))}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button
          type="button"
          className="btn btn-success btn-sm"
          disabled={submitting}
          onClick={() => void submit(false, "manual_review", null)}
        >
          <ShieldCheck size={14} />
          Mark Legitimate
        </button>
        <button
          type="button"
          className="btn btn-danger btn-sm"
          disabled={submitting}
          onClick={() => void submit(true, "manual_review", null)}
        >
          <ShieldX size={14} />
          Confirm Fraud
        </button>
        <button
          type="button"
          className="btn btn-warning btn-sm"
          disabled={submitting}
          onClick={() => setFormOpen((open) => !open)}
        >
          <CircleHelp size={14} />
          Needs Review
        </button>
      </div>

      {formOpen && (
        <form onSubmit={handleFormSubmit} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <label className="detail-field-label" htmlFor="label-is-fraud">
            Determination
          </label>
          <select
            id="label-is-fraud"
            value={isFraud ? "fraud" : "not_fraud"}
            onChange={(event) => setIsFraud(event.target.value === "fraud")}
            disabled={submitting}
          >
            <option value="fraud">Fraud</option>
            <option value="not_fraud">Not fraud</option>
          </select>

          <label className="detail-field-label" htmlFor="label-source">
            Source
          </label>
          <select
            id="label-source"
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

          <label className="detail-field-label" htmlFor="label-notes">
            Notes (optional)
          </label>
          <textarea
            id="label-notes"
            rows={2}
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            disabled={submitting}
            style={{
              fontFamily: "inherit",
              fontSize: 13,
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-sm)",
              color: "var(--text-primary)",
              padding: 8,
              resize: "vertical",
            }}
          />

          <button type="submit" className="btn btn-primary btn-sm" disabled={submitting}>
            {submitting ? "Submitting…" : "Submit label"}
          </button>
        </form>
      )}
    </div>
  );
}

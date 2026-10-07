import { Cpu, FileText, ListTree, Tag } from "lucide-react";
import type { ReactNode } from "react";
import { explanationForReasonCode, labelForReasonCode } from "../../lib/reasonCodes";
import { formatAmount, formatDateTime } from "../../lib/format";
import { statusRoleForOutcome } from "../../lib/risk";
import type { LabelSummary, TransactionFeedItem } from "../../types";
import { CopyableId } from "../common/CopyableId";
import { Drawer } from "../common/Drawer";
import { StatusBadge } from "../common/StatusBadge";
import { LabelPanel } from "./LabelPanel";
import { RiskMeter } from "./RiskMeter";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="detail-field-label">{label}</div>
      <div className="detail-field-value">{children}</div>
    </div>
  );
}

function SectionTitle({ icon: Icon, children }: { icon: typeof Cpu; children: ReactNode }) {
  return (
    <div className="drawer-section-title">
      <Icon size={13} />
      {children}
    </div>
  );
}

export function TransactionDrawer({
  item,
  onClose,
  onLabelAdded,
}: {
  item: TransactionFeedItem | null;
  onClose: () => void;
  onLabelAdded: (transactionId: string, label: LabelSummary) => void;
}) {
  const decision = item?.decision ?? null;

  return (
    <Drawer
      open={item !== null}
      onClose={onClose}
      title="Transaction details"
      subtitle={item ? <CopyableId value={item.transaction_id} display={item.transaction_id.slice(0, 18) + "…"} /> : null}
    >
      {item && (
        <>
          <section
            style={{
              background: "linear-gradient(165deg, var(--bg-surface-hover) 0%, transparent 100%)",
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--border)",
              padding: "16px 18px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
              <span className="detail-field-label" style={{ margin: 0 }}>
                Risk score
              </span>
              {decision ? (
                <StatusBadge label={decision.outcome} role={statusRoleForOutcome(decision.outcome)} />
              ) : (
                <StatusBadge label="no decision" role="neutral" />
              )}
            </div>
            {decision ? (
              <RiskMeter riskScore={decision.risk_score} />
            ) : (
              <p className="page-subtitle">No decision was recorded for this transaction.</p>
            )}
          </section>

          <div className="drawer-divider" />

          <section>
            <SectionTitle icon={FileText}>Transaction summary</SectionTitle>
            <div className="detail-grid">
              <Field label="Account">
                <CopyableId value={item.account_id} display={item.account_id.slice(0, 16) + "…"} />
              </Field>
              <Field label="Merchant">{item.merchant_id}</Field>
              <Field label="Amount">{formatAmount(item.amount, item.currency)}</Field>
              <Field label="Currency">
                {item.currency === "USD" ? "INR (converted from USD for display)" : item.currency}
              </Field>
              <Field label="Occurred at">{formatDateTime(item.occurred_at)}</Field>
              <Field label="Decided at">{decision ? formatDateTime(decision.decided_at) : "—"}</Field>
            </div>
          </section>

          <div className="drawer-divider" />

          <section>
            <SectionTitle icon={Cpu}>Model information</SectionTitle>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "10px 12px",
                borderRadius: "var(--radius-sm)",
                background: "var(--bg-surface-hover)",
                border: "1px solid var(--border)",
              }}
            >
              <span className="mono" style={{ fontSize: 13 }}>
                {decision?.model_version ?? "fallback rule"}
              </span>
              <StatusBadge
                label={decision?.model_version ? "model-scored" : "rule-based"}
                role={decision?.model_version ? "good" : "warning"}
              />
            </div>
          </section>

          <div className="drawer-divider" />

          <section>
            <SectionTitle icon={ListTree}>Behavioral signals</SectionTitle>
            {decision?.reason_codes && decision.reason_codes.length > 0 ? (
              decision.reason_codes.map((code) => (
                <div className="reason-code-item" key={code}>
                  <div className="reason-code-item-title">{labelForReasonCode(code)}</div>
                  <div className="reason-code-item-desc">{explanationForReasonCode(code)}</div>
                </div>
              ))
            ) : (
              <p className="page-subtitle">
                {decision
                  ? "This decision was made by the fallback rule, not the model -- no SHAP-based reason codes exist for it."
                  : "No decision exists for this transaction yet."}
              </p>
            )}
          </section>

          <div className="drawer-divider" />

          <section>
            <SectionTitle icon={Tag}>Ground-truth labels</SectionTitle>
            <LabelPanel
              transactionId={item.transaction_id}
              labels={item.labels}
              onLabelAdded={(label) => onLabelAdded(item.transaction_id, label)}
            />
          </section>
        </>
      )}
    </Drawer>
  );
}

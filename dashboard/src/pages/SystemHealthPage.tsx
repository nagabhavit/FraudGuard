import { Activity, Cpu, Database, Globe, Radio, Server } from "lucide-react";
import { useMemo } from "react";
import { StatusBadge } from "../components/common/StatusBadge";
import { useAllTransactions } from "../hooks/useAllTransactions";
import { useGatewayMetrics } from "../hooks/useGatewayMetrics";
import { useGatewayPulse } from "../hooks/useGatewayPulse";
import { formatRelativeTime } from "../lib/format";
import type { StatusRole } from "../lib/risk";

interface HealthRow {
  key: string;
  label: string;
  icon: typeof Server;
  role: StatusRole | "neutral";
  statusLabel: string;
  detail: string;
}

export function SystemHealthPage() {
  const pulse = useGatewayPulse();
  const { summary, loading: metricsLoading } = useGatewayMetrics();
  const { items } = useAllTransactions();

  const lastTransaction = items[0] ?? null;
  const lastModelPrediction = useMemo(
    () => items.find((item) => item.decision?.model_version != null) ?? null,
    [items],
  );

  const rows: HealthRow[] = useMemo(() => {
    const gatewayUp = pulse.live?.status === "ok";
    const dbUp = pulse.ready?.checks.postgres === "ok";

    const kafkaTotal = (summary?.kafkaSuccess ?? 0) + (summary?.kafkaFailure ?? 0);
    const kafkaFailureRate = kafkaTotal > 0 ? (summary?.kafkaFailure ?? 0) / kafkaTotal : null;

    const fallbackTotal = (summary?.usedModelTotal ?? 0) + (summary?.fallbackTotal ?? 0);
    const fallbackRate = fallbackTotal > 0 ? (summary?.fallbackTotal ?? 0) / fallbackTotal : null;

    return [
      {
        key: "gateway",
        label: "Gateway / API",
        icon: Server,
        role: gatewayUp ? "good" : "critical",
        statusLabel: gatewayUp ? "Healthy" : "Unavailable",
        detail: "GET /health/live",
      },
      {
        key: "database",
        label: "Database (Postgres)",
        icon: Database,
        role: pulse.ready === null ? "neutral" : dbUp ? "good" : "critical",
        statusLabel: pulse.ready === null ? "Unknown" : dbUp ? "Healthy" : "Unreachable",
        detail: "GET /health/ready, checks.postgres",
      },
      {
        key: "model",
        label: "ML model",
        icon: Cpu,
        role: fallbackRate === null ? "neutral" : fallbackRate < 0.2 ? "good" : "warning",
        statusLabel:
          fallbackRate === null ? "No recent activity" : fallbackRate < 0.2 ? "Serving" : "Degraded",
        detail: "Inferred from decisions_total{used_model} -- model-service itself has no browser-reachable endpoint",
      },
      {
        key: "kafka",
        label: "Kafka / ingestion",
        icon: Radio,
        role: kafkaTotal === 0 ? "neutral" : kafkaFailureRate! < 0.05 ? "good" : "critical",
        statusLabel: kafkaTotal === 0 ? "No recent activity" : kafkaFailureRate! < 0.05 ? "Healthy" : "Degraded",
        detail: "Inferred from fraudguard_gateway_kafka_publish_total{outcome}",
      },
      {
        key: "connectivity",
        label: "Frontend ↔ backend connectivity",
        icon: Globe,
        role: pulse.isLive ? "good" : "critical",
        statusLabel: pulse.isLive ? "Connected" : "Disconnected",
        detail: `Last checked ${pulse.lastCheckedAt ? formatRelativeTime(pulse.lastCheckedAt.toISOString()) : "—"}`,
      },
    ];
  }, [pulse, summary]);

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">System Health</div>
          <div className="page-subtitle">Direct probes where available; inferred signals are labeled as such.</div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-body" style={{ padding: 0 }}>
          {rows.map((row) => (
            <div className="list-row" key={row.key} style={{ padding: "14px 18px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <row.icon size={16} style={{ color: "var(--text-muted)" }} />
                <div>
                  <div style={{ fontWeight: 560 }}>{row.label}</div>
                  <div className="page-subtitle" style={{ fontSize: 12, marginTop: 1 }}>
                    {row.detail}
                  </div>
                </div>
              </div>
              <StatusBadge label={row.statusLabel} role={row.role} />
            </div>
          ))}
        </div>
      </div>

      <div className="section-grid-2">
        <div className="card">
          <div className="card-header">
            <span className="card-title" style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Activity size={14} />
              Last successful transaction
            </span>
          </div>
          <div className="card-body">
            {lastTransaction ? (
              <>
                <div className="detail-field-value" style={{ fontSize: 16, marginBottom: 4 }}>
                  {formatRelativeTime(lastTransaction.occurred_at)}
                </div>
                <div className="page-subtitle mono">{lastTransaction.transaction_id}</div>
              </>
            ) : (
              <p className="page-subtitle">No transactions observed yet.</p>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <span className="card-title" style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Cpu size={14} />
              Last model prediction
            </span>
          </div>
          <div className="card-body">
            {lastModelPrediction?.decision ? (
              <>
                <div className="detail-field-value" style={{ fontSize: 16, marginBottom: 4 }}>
                  {formatRelativeTime(lastModelPrediction.decision.decided_at)}
                </div>
                <div className="page-subtitle mono">{lastModelPrediction.decision.model_version}</div>
              </>
            ) : (
              <p className="page-subtitle">
                {metricsLoading ? "Loading…" : "No model-scored decision observed yet -- every recent decision used the fallback rule."}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

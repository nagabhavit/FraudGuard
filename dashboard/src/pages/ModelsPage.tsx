import { Activity, Cpu, Gauge, Layers, ListTree } from "lucide-react";
import { StatCard } from "../components/common/StatCard";
import { StatusBadge } from "../components/common/StatusBadge";
import { useGatewayMetrics } from "../hooks/useGatewayMetrics";
import { useGatewayPulse } from "../hooks/useGatewayPulse";
import { formatCount, formatMs, formatPercent } from "../lib/format";
import { KNOWN_FEATURE_NAMES } from "../types";

export function ModelsPage() {
  const pulse = useGatewayPulse();
  const { summary, loading } = useGatewayMetrics();

  const usedModel = summary?.usedModelTotal ?? 0;
  const fallback = summary?.fallbackTotal ?? 0;
  const totalDecisions = usedModel + fallback;
  const fallbackRate = totalDecisions > 0 ? fallback / totalDecisions : null;
  const isServing = pulse.latestModelVersion !== null && (fallbackRate === null || fallbackRate < 0.2);

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Models</div>
          <div className="page-subtitle">
            Only fields the running system actually exposes -- nothing below is invented.
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-header">
          <span className="card-title" style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <Cpu size={15} />
            Current model
          </span>
          <StatusBadge
            label={isServing ? "Serving" : "Degraded (fallback active)"}
            role={isServing ? "good" : "warning"}
          />
        </div>
        <div className="card-body detail-grid">
          <div>
            <div className="detail-field-label">Model version</div>
            <div className="detail-field-value mono">{pulse.latestModelVersion ?? "no scored transaction yet"}</div>
          </div>
          <div>
            <div className="detail-field-label">Model type</div>
            <div className="detail-field-value">LightGBM (gradient-boosted decision trees)</div>
          </div>
          <div>
            <div className="detail-field-label">Deployment status</div>
            <div className="detail-field-value" style={{ color: "var(--text-muted)" }}>
              Not exposed via API
            </div>
          </div>
          <div>
            <div className="detail-field-label">AUC / offline performance</div>
            <div className="detail-field-value" style={{ color: "var(--text-muted)" }}>
              Not exposed via API (only recorded in training metadata on disk)
            </div>
          </div>
        </div>
      </div>

      <div className="kpi-grid">
        <StatCard
          label="Prediction volume"
          icon={<Activity size={16} />}
          value={formatCount(summary?.scoringCount ?? 0)}
          meta="scoring attempts, gateway metrics"
          loading={loading}
        />
        <StatCard
          label="Average scoring latency"
          icon={<Gauge size={16} />}
          value={formatMs(summary?.scoringAvgMs ?? null, 1)}
          meta="feature-service + model-service"
          loading={loading}
        />
        <StatCard
          label="Fallback rate"
          icon={<Layers size={16} />}
          value={fallbackRate !== null ? formatPercent(fallbackRate) : "—"}
          meta={`${formatCount(usedModel)} model / ${formatCount(fallback)} fallback`}
          loading={loading}
        />
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title" style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <ListTree size={15} />
            Feature schema
          </span>
        </div>
        <div className="card-body">
          <p className="page-subtitle" style={{ marginBottom: 12 }}>
            The fixed, ordered feature set every score is computed against
            (libs/fraudguard-ml/src/fraudguard_ml/features.py) -- a static fact about the running
            service, not a live metric.
          </p>
          {KNOWN_FEATURE_NAMES.map((name) => (
            <div className="list-row" key={name}>
              <span className="mono">{name}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

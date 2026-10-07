// Parses the gateway's GET /metrics (Prometheus text exposition format,
// fraudguard_common.metrics) directly in the browser. Confirmed live:
// the gateway's CORSMiddleware is added once, globally, so /metrics gets
// the same Access-Control-Allow-Origin treatment as /v1/transactions
// (ADR-0012) -- no backend change was needed or made to read this.
//
// This is the only source for data /v1/transactions cannot provide:
// scoring latency, Kafka publish outcomes, and the model-used/fallback
// split as the gateway itself counts them, not as re-derived client-side
// guesses.

export interface MetricSample {
  labels: Record<string, string>;
  value: number;
}

export type ParsedMetrics = Map<string, MetricSample[]>;

const LINE_RE =
  /^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{([^}]*)\})?\s+([^\s]+)\s*$/;
const LABEL_RE = /([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"/g;

export function parsePrometheusText(text: string): ParsedMetrics {
  const parsed: ParsedMetrics = new Map();

  for (const line of text.split("\n")) {
    if (line.length === 0 || line.startsWith("#")) continue;
    const match = LINE_RE.exec(line);
    if (!match) continue;
    const [, name, , labelsRaw, rawValue] = match;
    const value = Number(rawValue);
    if (Number.isNaN(value)) continue;

    const labels: Record<string, string> = {};
    if (labelsRaw) {
      for (const labelMatch of labelsRaw.matchAll(LABEL_RE)) {
        labels[labelMatch[1]] = labelMatch[2];
      }
    }

    const existing = parsed.get(name);
    if (existing) {
      existing.push({ labels, value });
    } else {
      parsed.set(name, [{ labels, value }]);
    }
  }

  return parsed;
}

function matchesLabels(
  sample: MetricSample,
  filter: Record<string, string> | undefined,
): boolean {
  if (!filter) return true;
  return Object.entries(filter).every(([key, value]) => sample.labels[key] === value);
}

export function sumMetric(
  parsed: ParsedMetrics,
  name: string,
  labelFilter?: Record<string, string>,
): number {
  const samples = parsed.get(name);
  if (!samples) return 0;
  return samples
    .filter((sample) => matchesLabels(sample, labelFilter))
    .reduce((total, sample) => total + sample.value, 0);
}

export interface GatewayMetricsSummary {
  decisionsByOutcome: Record<string, number>;
  usedModelTotal: number;
  fallbackTotal: number;
  scoringCount: number;
  scoringSumSeconds: number;
  scoringAvgMs: number | null;
  scoringBudgetExceeded: number;
  kafkaSuccess: number;
  kafkaFailure: number;
  labelsTotal: number;
}

/** Everything the dashboard's own pages need from one /metrics fetch,
 * pre-aggregated once so pages don't each re-walk the raw samples. */
export function summarizeGatewayMetrics(parsed: ParsedMetrics): GatewayMetricsSummary {
  const decisionSamples = parsed.get("fraudguard_gateway_decisions_total") ?? [];
  const decisionsByOutcome: Record<string, number> = {};
  let usedModelTotal = 0;
  let fallbackTotal = 0;
  for (const sample of decisionSamples) {
    const outcome = sample.labels.outcome ?? "unknown";
    decisionsByOutcome[outcome] = (decisionsByOutcome[outcome] ?? 0) + sample.value;
    if (sample.labels.used_model === "true") usedModelTotal += sample.value;
    else fallbackTotal += sample.value;
  }

  const scoringCount = sumMetric(parsed, "fraudguard_gateway_scoring_duration_seconds_count");
  const scoringSumSeconds = sumMetric(parsed, "fraudguard_gateway_scoring_duration_seconds_sum");

  return {
    decisionsByOutcome,
    usedModelTotal,
    fallbackTotal,
    scoringCount,
    scoringSumSeconds,
    scoringAvgMs: scoringCount > 0 ? (scoringSumSeconds / scoringCount) * 1000 : null,
    scoringBudgetExceeded: sumMetric(parsed, "fraudguard_gateway_scoring_budget_exceeded_total"),
    kafkaSuccess: sumMetric(parsed, "fraudguard_gateway_kafka_publish_total", {
      outcome: "success",
    }),
    kafkaFailure: sumMetric(parsed, "fraudguard_gateway_kafka_publish_total", {
      outcome: "failure",
    }),
    labelsTotal: sumMetric(parsed, "fraudguard_gateway_labels_total"),
  };
}

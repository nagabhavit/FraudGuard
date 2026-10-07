import { useEffect, useState } from "react";
import { fetchGatewayMetricsText } from "../api";
import { parsePrometheusText, summarizeGatewayMetrics, type GatewayMetricsSummary } from "../metrics";

const REFRESH_INTERVAL_MS = 10000;

export interface GatewayMetricsState {
  summary: GatewayMetricsSummary | null;
  loading: boolean;
  error: string | null;
}

/** Polls the gateway's own GET /metrics (Prometheus text) and returns the
 * pre-aggregated summary -- the only source for scoring latency, Kafka
 * publish outcomes, and model-used/fallback counts, none of which
 * /v1/transactions exposes directly. */
export function useGatewayMetrics(): GatewayMetricsState {
  const [state, setState] = useState<GatewayMetricsState>({
    summary: null,
    loading: true,
    error: null,
  });

  useEffect(() => {
    const controller = new AbortController();

    const poll = async () => {
      try {
        const text = await fetchGatewayMetricsText(controller.signal);
        const summary = summarizeGatewayMetrics(parsePrometheusText(text));
        setState({ summary, loading: false, error: null });
      } catch (err) {
        if (controller.signal.aborted) return;
        setState((previous) => ({
          ...previous,
          loading: false,
          error: err instanceof Error ? err.message : "failed to load metrics",
        }));
      }
    };

    void poll();
    const interval = setInterval(() => void poll(), REFRESH_INTERVAL_MS);
    return () => {
      controller.abort();
      clearInterval(interval);
    };
  }, []);

  return state;
}

import { useEffect, useRef, useState } from "react";
import { fetchGatewayHealth, fetchTransactions } from "../api";
import type { HealthStatus } from "../types";

const DEFAULT_INTERVAL_MS = 7000;

export interface GatewayPulse {
  live: HealthStatus | null;
  ready: HealthStatus | null;
  /** The most recent transaction's model_version, or null if the most
   * recent decision was a fallback (or none exist yet). This is the only
   * place "current model" can come from -- no endpoint returns it
   * directly, only embedded per-decision. */
  latestModelVersion: string | null;
  isLive: boolean;
  lastCheckedAt: Date | null;
  lastTransactionAt: string | null;
}

export function useGatewayPulse(intervalMs: number = DEFAULT_INTERVAL_MS): GatewayPulse {
  const [pulse, setPulse] = useState<GatewayPulse>({
    live: null,
    ready: null,
    latestModelVersion: null,
    isLive: false,
    lastCheckedAt: null,
    lastTransactionAt: null,
  });
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    const controller = new AbortController();

    const tick = async () => {
      try {
        const [health, page] = await Promise.all([
          fetchGatewayHealth(controller.signal),
          fetchTransactions({ limit: 1, signal: controller.signal }),
        ]);
        if (!mountedRef.current) return;
        const latest = page.items[0];
        setPulse({
          live: health.live,
          ready: health.ready,
          latestModelVersion: latest?.decision?.model_version ?? null,
          isLive: health.live?.status === "ok" && health.ready?.status === "ok",
          lastCheckedAt: new Date(),
          lastTransactionAt: latest?.occurred_at ?? null,
        });
      } catch {
        if (!mountedRef.current) return;
        setPulse((previous) => ({ ...previous, isLive: false, lastCheckedAt: new Date() }));
      }
    };

    void tick();
    const interval = setInterval(() => void tick(), intervalMs);
    return () => {
      mountedRef.current = false;
      controller.abort();
      clearInterval(interval);
    };
  }, [intervalMs]);

  return pulse;
}

import { useEffect, useState } from "react";
import { fetchTransactions } from "../api";
import type { TransactionFeedItem } from "../types";

const POLL_INTERVAL_MS = 5000;

export interface LiveTransactionsState {
  items: TransactionFeedItem[];
  loading: boolean;
  error: string | null;
  lastUpdated: Date | null;
}

/** The original App.tsx's polling behavior, unchanged (5s interval,
 * most-recent-first), now reusable by any page that wants a live feed
 * rather than the full filtered dataset. */
export function useLiveTransactions(limit = 50): LiveTransactionsState {
  const [state, setState] = useState<LiveTransactionsState>({
    items: [],
    loading: true,
    error: null,
    lastUpdated: null,
  });

  useEffect(() => {
    const controller = new AbortController();

    const poll = async () => {
      try {
        const page = await fetchTransactions({ limit, signal: controller.signal });
        setState({ items: page.items, loading: false, error: null, lastUpdated: new Date() });
      } catch (err) {
        if (controller.signal.aborted) return;
        setState((previous) => ({
          ...previous,
          loading: false,
          error: err instanceof Error ? err.message : "failed to load",
        }));
      }
    };

    void poll();
    const interval = setInterval(() => void poll(), POLL_INTERVAL_MS);
    return () => {
      controller.abort();
      clearInterval(interval);
    };
  }, [limit]);

  return state;
}

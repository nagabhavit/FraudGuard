import { useCallback, useEffect, useState } from "react";
import { fetchAllTransactions } from "../api";
import type { TransactionFeedItem } from "../types";

const REFRESH_INTERVAL_MS = 15000;

export interface AllTransactionsState {
  items: TransactionFeedItem[];
  truncated: boolean;
  loading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  refetch: () => void;
}

/** The full (bounded) transaction history, for pages that need to filter,
 * aggregate, or chart across more than one page -- Transactions,
 * Investigations, Analytics, and the Overview KPI strip. Refetches on an
 * interval so "live refresh" holds here too; callers keep their own
 * filter/search state untouched by a refetch since this hook only ever
 * replaces `items`, never resets caller state. */
export function useAllTransactions(): AllTransactionsState {
  const [items, setItems] = useState<TransactionFeedItem[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();

    const load = async () => {
      try {
        const result = await fetchAllTransactions(controller.signal);
        setItems(result.items);
        setTruncated(result.truncated);
        setError(null);
        setLastUpdated(new Date());
      } catch (err) {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : "failed to load");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };

    void load();
    const interval = setInterval(() => void load(), REFRESH_INTERVAL_MS);
    return () => {
      controller.abort();
      clearInterval(interval);
    };
  }, [refreshToken]);

  const refetch = useCallback(() => setRefreshToken((token) => token + 1), []);

  return { items, truncated, loading, error, lastUpdated, refetch };
}

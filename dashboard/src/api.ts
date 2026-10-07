import type {
  HealthStatus,
  LabelCreate,
  LabelRead,
  TransactionFeedItem,
  TransactionFeedPage,
} from "./types";

// Always the gateway's host-mapped port, both in `npm run dev` and in the
// built static image served by docker-compose -- the browser calls it
// directly, never through the internal compose network (ADR-0012).
const API_BASE_URL: string =
  import.meta.env.VITE_GATEWAY_URL ?? "http://localhost:8000";

// The page size GET /v1/transactions accepts (gateway caps it at 200,
// services/gateway/src/gateway/transactions.py's Query(le=200)).
const MAX_PAGE_SIZE = 200;
// GET /v1/transactions has no total-count field, only items/limit/offset --
// there is no way to ask Postgres "how many rows exist" through this API
// without paginating through them. This caps how far fetchAllTransactions
// will page before stopping, so a growing demo database never turns one
// page load into an unbounded number of requests. Pages beyond this are
// simply not included; callers get `truncated: true` so they can say so
// rather than silently presenting a partial total as a complete one.
const MAX_TRANSACTIONS_TO_FETCH = 2000;

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function fetchTransactions(
  options: { limit?: number; offset?: number; signal?: AbortSignal } = {},
): Promise<TransactionFeedPage> {
  const { limit = 50, offset = 0, signal } = options;
  const url = new URL("/v1/transactions", API_BASE_URL);
  url.searchParams.set("limit", String(limit));
  url.searchParams.set("offset", String(offset));

  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw new ApiError(
      `GET /v1/transactions failed: ${response.status}`,
      response.status,
    );
  }
  return (await response.json()) as TransactionFeedPage;
}

export async function createLabel(
  transactionId: string,
  payload: LabelCreate,
): Promise<LabelRead> {
  const url = new URL(
    `/v1/transactions/${transactionId}/labels`,
    API_BASE_URL,
  );

  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new ApiError(
      `POST /v1/transactions/${transactionId}/labels failed: ${response.status}`,
      response.status,
    );
  }
  return (await response.json()) as LabelRead;
}

export interface FetchAllResult {
  items: TransactionFeedItem[];
  /** True if MAX_TRANSACTIONS_TO_FETCH was hit before an empty page --
   * i.e. this is not provably the complete history, just the most recent
   * slice of it. Callers must surface this, not hide it. */
  truncated: boolean;
}

/** Pages through GET /v1/transactions (most-recent-first) until an empty
 * page or MAX_TRANSACTIONS_TO_FETCH, for pages that need a real aggregate
 * (KPIs, analytics) rather than one 50-row feed. There is no count
 * endpoint to short-circuit this with -- paginating is the only way to
 * get a real total through the existing API. */
export async function fetchAllTransactions(
  signal?: AbortSignal,
): Promise<FetchAllResult> {
  const items: TransactionFeedItem[] = [];
  let offset = 0;
  let truncated = false;

  while (items.length < MAX_TRANSACTIONS_TO_FETCH) {
    const page = await fetchTransactions({ limit: MAX_PAGE_SIZE, offset, signal });
    items.push(...page.items);
    if (page.items.length < MAX_PAGE_SIZE) break;
    offset += MAX_PAGE_SIZE;
    if (items.length >= MAX_TRANSACTIONS_TO_FETCH) {
      truncated = true;
      break;
    }
  }

  return { items, truncated };
}

/** GET /health/live and /health/ready, in parallel. Either can fail
 * independently (e.g. the gateway process is up but Postgres isn't) --
 * callers get both results rather than one request's failure masking
 * the other's real status. */
export async function fetchGatewayHealth(signal?: AbortSignal): Promise<{
  live: HealthStatus | null;
  ready: HealthStatus | null;
}> {
  const fetchOne = async (path: string): Promise<HealthStatus | null> => {
    try {
      const response = await fetch(new URL(path, API_BASE_URL), { signal });
      if (!response.ok) return null;
      return (await response.json()) as HealthStatus;
    } catch {
      return null;
    }
  };

  const [live, ready] = await Promise.all([
    fetchOne("/health/live"),
    fetchOne("/health/ready"),
  ]);
  return { live, ready };
}

/** Raw GET /metrics text (Prometheus exposition format) -- see metrics.ts
 * for parsing. Confirmed CORS-enabled for the dashboard's own origin,
 * same as /v1/transactions (ADR-0012's CORSMiddleware applies to the
 * whole gateway app, not one route). */
export async function fetchGatewayMetricsText(signal?: AbortSignal): Promise<string> {
  const response = await fetch(new URL("/metrics", API_BASE_URL), { signal });
  if (!response.ok) {
    throw new ApiError(`GET /metrics failed: ${response.status}`, response.status);
  }
  return await response.text();
}

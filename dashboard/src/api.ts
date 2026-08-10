import type { LabelCreate, LabelRead, TransactionFeedPage } from "./types";

// Always the gateway's host-mapped port, both in `npm run dev` and in the
// built static image served by docker-compose -- the browser calls it
// directly, never through the internal compose network (ADR-0012).
const API_BASE_URL: string =
  import.meta.env.VITE_GATEWAY_URL ?? "http://localhost:8000";

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

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import {
  createLabel,
  fetchGatewayHealth,
  fetchGatewayMetricsText,
  fetchTransactions,
} from "./api";
import type { LabelRead, TransactionFeedItem } from "./types";

vi.mock("./api", () => ({
  fetchTransactions: vi.fn(),
  fetchAllTransactions: vi.fn(),
  createLabel: vi.fn(),
  fetchGatewayHealth: vi.fn(),
  fetchGatewayMetricsText: vi.fn(),
}));

const mockedFetchTransactions = vi.mocked(fetchTransactions);
const mockedCreateLabel = vi.mocked(createLabel);
const mockedFetchGatewayHealth = vi.mocked(fetchGatewayHealth);
const mockedFetchGatewayMetricsText = vi.mocked(fetchGatewayMetricsText);

// useAllTransactions calls fetchAllTransactions, a module export entirely
// separate from fetchTransactions -- import it dynamically from the
// already-mocked module so every test can set its resolved value without
// re-declaring the mock factory.
import { fetchAllTransactions } from "./api";
const mockedFetchAllTransactions = vi.mocked(fetchAllTransactions);

function scoredItem(overrides: Partial<TransactionFeedItem> = {}): TransactionFeedItem {
  return {
    transaction_id: "9b1f7b1e-1111-4b1e-8b1e-111111111111",
    account_id: "9b1f7b1e-2222-4b1e-8b1e-222222222222",
    merchant_id: "merchant-1",
    amount: "42.50",
    currency: "USD",
    occurred_at: "2026-08-08T12:00:00Z",
    decision: {
      outcome: "review",
      risk_score: 0.7231,
      model_version: "fraud-lgbm-20260808-120000",
      reason_codes: ["velocity_1h", "distinct_merchants_24h"],
      decided_at: "2026-08-08T12:00:00Z",
    },
    labels: [],
    ...overrides,
  };
}

function fallbackItem(): TransactionFeedItem {
  return scoredItem({
    transaction_id: "9b1f7b1e-3333-4b1e-8b1e-333333333333",
    merchant_id: "merchant-2",
    amount: "999.00",
    decision: {
      outcome: "review",
      risk_score: 1.0,
      model_version: null,
      reason_codes: null,
      decided_at: "2026-08-08T11:00:00Z",
    },
  });
}

function setupApis(items: TransactionFeedItem[]) {
  mockedFetchTransactions.mockResolvedValue({ items, limit: 50, offset: 0 });
  mockedFetchAllTransactions.mockResolvedValue({ items, truncated: false });
  mockedFetchGatewayHealth.mockResolvedValue({
    live: { status: "ok", checks: {} },
    ready: { status: "ok", checks: { postgres: "ok" } },
  });
  mockedFetchGatewayMetricsText.mockResolvedValue("");
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("App", () => {
  it("renders the Overview page by default with real KPI data", async () => {
    setupApis([scoredItem()]);

    render(<App />);

    expect(await screen.findByRole("heading", { name: "FraudGuard" })).toBeInTheDocument();
    expect(screen.getByText("Real-time fraud intelligence")).toBeInTheDocument();
    // The live transaction stream card should surface the seeded merchant.
    expect(await screen.findByText("merchant-1")).toBeInTheDocument();
  });

  it("navigates to Transactions and renders the full feed", async () => {
    setupApis([scoredItem(), fallbackItem()]);

    render(<App />);
    await screen.findByText("merchant-1");

    fireEvent.click(screen.getByRole("link", { name: /transactions/i }));

    const table = await screen.findByRole("table");
    expect(await within(table).findByText("merchant-2")).toBeInTheDocument();
    expect(within(table).getByText("fallback rule")).toBeInTheDocument();
  });

  it("filters the Transactions table by search text", async () => {
    setupApis([scoredItem(), fallbackItem()]);

    render(<App />);
    fireEvent.click(screen.getByRole("link", { name: /transactions/i }));
    const table = await screen.findByRole("table");
    await within(table).findByText("merchant-2");

    const searchInput = screen.getByPlaceholderText("Search ID, account, merchant…");
    fireEvent.change(searchInput, { target: { value: "merchant-1" } });

    expect(within(table).queryByText("merchant-2")).not.toBeInTheDocument();
    expect(within(table).getByText("merchant-1")).toBeInTheDocument();
    expect(screen.getByText('Search: "merchant-1"')).toBeInTheDocument();
  });

  it("shows an empty state when there are no transactions", async () => {
    setupApis([]);

    render(<App />);
    fireEvent.click(screen.getByRole("link", { name: /transactions/i }));

    expect(await screen.findByText("No transactions found")).toBeInTheDocument();
  });

  it("surfaces a fetch failure instead of rendering silently", async () => {
    mockedFetchAllTransactions.mockRejectedValue(new Error("network error"));
    mockedFetchTransactions.mockResolvedValue({ items: [], limit: 50, offset: 0 });
    mockedFetchGatewayHealth.mockResolvedValue({ live: null, ready: null });
    mockedFetchGatewayMetricsText.mockResolvedValue("");

    render(<App />);
    fireEvent.click(screen.getByRole("link", { name: /transactions/i }));

    await waitFor(() =>
      expect(screen.getByText("network error")).toBeInTheDocument(),
    );
  });

  it("opens the investigation drawer and submits a quick label", async () => {
    setupApis([scoredItem()]);
    const created: LabelRead = {
      id: "label-1",
      transaction_id: "9b1f7b1e-1111-4b1e-8b1e-111111111111",
      is_fraud: false,
      source: "manual_review",
      notes: null,
      labeled_at: "2026-08-10T00:00:00Z",
    };
    mockedCreateLabel.mockResolvedValue(created);

    render(<App />);
    fireEvent.click(screen.getByRole("link", { name: /transactions/i }));
    const table = await screen.findByRole("table");
    await within(table).findByText("merchant-1");

    fireEvent.click(within(table).getByText("merchant-1"));

    const drawer = await screen.findByRole("dialog", { name: /transaction details/i });
    fireEvent.click(within(drawer).getByRole("button", { name: /mark legitimate/i }));

    await waitFor(() =>
      expect(mockedCreateLabel).toHaveBeenCalledWith(
        "9b1f7b1e-1111-4b1e-8b1e-111111111111",
        { is_fraud: false, source: "manual_review", notes: null },
      ),
    );
    expect(await within(drawer).findByText(/legitimate · manual review/i)).toBeInTheDocument();
  });

  it("surfaces a label submission failure as a toast instead of failing silently", async () => {
    setupApis([scoredItem()]);
    mockedCreateLabel.mockRejectedValue(new Error("label submit failed"));

    render(<App />);
    fireEvent.click(screen.getByRole("link", { name: /transactions/i }));
    const table = await screen.findByRole("table");
    await within(table).findByText("merchant-1");
    fireEvent.click(within(table).getByText("merchant-1"));

    const drawer = await screen.findByRole("dialog", { name: /transaction details/i });
    fireEvent.click(within(drawer).getByRole("button", { name: /confirm fraud/i }));

    expect(await screen.findByText("label submit failed")).toBeInTheDocument();
  });
});

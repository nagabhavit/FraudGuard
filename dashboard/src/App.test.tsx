import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { createLabel, fetchTransactions } from "./api";
import type { LabelRead, TransactionFeedItem } from "./types";

vi.mock("./api", () => ({
  fetchTransactions: vi.fn(),
  createLabel: vi.fn(),
}));

const mockedFetchTransactions = vi.mocked(fetchTransactions);
const mockedCreateLabel = vi.mocked(createLabel);

function scoredItem(): TransactionFeedItem {
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
  };
}

function fallbackItem(): TransactionFeedItem {
  return {
    transaction_id: "9b1f7b1e-3333-4b1e-8b1e-333333333333",
    account_id: "9b1f7b1e-4444-4b1e-8b1e-444444444444",
    merchant_id: "merchant-2",
    amount: "999.00",
    currency: "USD",
    occurred_at: "2026-08-08T11:00:00Z",
    decision: {
      outcome: "review",
      risk_score: 1.0,
      model_version: null,
      reason_codes: null,
      decided_at: "2026-08-08T11:00:00Z",
    },
    labels: [],
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("App", () => {
  it("renders the feed once transactions load", async () => {
    mockedFetchTransactions.mockResolvedValue({
      items: [scoredItem()],
      limit: 50,
      offset: 0,
    });

    render(<App />);

    expect(await screen.findByText("merchant-1")).toBeInTheDocument();
    expect(screen.getByText("review")).toBeInTheDocument();
    expect(screen.getByText("0.7231")).toBeInTheDocument();
    expect(
      screen.getByText("velocity_1h, distinct_merchants_24h"),
    ).toBeInTheDocument();
  });

  it("labels a fallback-rule decision instead of a model version", async () => {
    mockedFetchTransactions.mockResolvedValue({
      items: [fallbackItem()],
      limit: 50,
      offset: 0,
    });

    render(<App />);

    expect(await screen.findByText("merchant-2")).toBeInTheDocument();
    expect(screen.getByText("fallback rule")).toBeInTheDocument();
  });

  it("shows an empty state when there are no transactions", async () => {
    mockedFetchTransactions.mockResolvedValue({
      items: [],
      limit: 50,
      offset: 0,
    });

    render(<App />);

    expect(await screen.findByText("No transactions yet.")).toBeInTheDocument();
  });

  it("surfaces a fetch failure instead of rendering silently", async () => {
    mockedFetchTransactions.mockRejectedValue(new Error("network error"));

    render(<App />);

    await waitFor(() =>
      expect(
        screen.getByText(/Could not reach the gateway/),
      ).toBeInTheDocument(),
    );
  });

  // Milestone 28: label display/submission.

  it("renders a transaction's existing labels", async () => {
    const item = scoredItem();
    item.labels = [
      {
        id: "label-1",
        is_fraud: true,
        source: "chargeback",
        notes: null,
        labeled_at: "2026-08-09T00:00:00Z",
      },
    ];
    mockedFetchTransactions.mockResolvedValue({
      items: [item],
      limit: 50,
      offset: 0,
    });

    render(<App />);

    expect(await screen.findByText("fraud (chargeback)")).toBeInTheDocument();
  });

  it("submits a new label and shows it without waiting for the next poll", async () => {
    mockedFetchTransactions.mockResolvedValue({
      items: [scoredItem()],
      limit: 50,
      offset: 0,
    });
    const created: LabelRead = {
      id: "label-1",
      transaction_id: "9b1f7b1e-1111-4b1e-8b1e-111111111111",
      is_fraud: true,
      source: "chargeback",
      notes: "flagged by bank",
      labeled_at: "2026-08-10T00:00:00Z",
    };
    mockedCreateLabel.mockResolvedValue(created);

    render(<App />);
    expect(await screen.findByText("merchant-1")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "+ label" }));
    const selects = screen.getAllByRole("combobox");
    fireEvent.change(selects[1], { target: { value: "chargeback" } });
    fireEvent.change(screen.getByPlaceholderText("Notes (optional)"), {
      target: { value: "flagged by bank" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));

    await waitFor(() =>
      expect(mockedCreateLabel).toHaveBeenCalledWith(
        "9b1f7b1e-1111-4b1e-8b1e-111111111111",
        { is_fraud: true, source: "chargeback", notes: "flagged by bank" },
      ),
    );
    expect(await screen.findByText("fraud (chargeback)")).toBeInTheDocument();
  });

  it("surfaces a label submission failure instead of failing silently", async () => {
    mockedFetchTransactions.mockResolvedValue({
      items: [scoredItem()],
      limit: 50,
      offset: 0,
    });
    mockedCreateLabel.mockRejectedValue(new Error("label submit failed"));

    render(<App />);
    expect(await screen.findByText("merchant-1")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "+ label" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));

    expect(await screen.findByText("label submit failed")).toBeInTheDocument();
  });
});

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString();
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString();
}

export function formatRelativeTime(iso: string, now: Date = new Date()): string {
  const deltaSeconds = Math.round((now.getTime() - new Date(iso).getTime()) / 1000);
  if (deltaSeconds < 5) return "just now";
  if (deltaSeconds < 60) return `${deltaSeconds}s ago`;
  const minutes = Math.round(deltaSeconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

// Display-only currency conversion for the demo (Milestone: INR display
// polish). The gateway/Postgres/simulator all still produce and store
// USD-denominated amounts untouched -- `TransactionFeedItem.currency` is
// always "USD" today and nothing here changes that field, the stored
// amount, or anything sent back to the API (labels, filters, etc. all
// still operate on the real amount string). This is purely what the
// dashboard renders.
//
// Fixed, explicit, non-live rate -- not fetched from any FX service, and
// not claimed to be. Chosen once, illustrative only, documented here as
// the single place it's defined so every consumer (KPI sum, table,
// drawer, analytics buckets) stays consistent.
export const USD_TO_INR_DISPLAY_RATE = 83;

export function convertUsdToInr(usdAmount: number): number {
  return usdAmount * USD_TO_INR_DISPLAY_RATE;
}

function formatInr(value: number, maximumFractionDigits = 2): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    currencyDisplay: "narrowSymbol",
    maximumFractionDigits,
  }).format(value);
}

/** Formats one transaction's amount for display. Respects the API's own
 * `currency` field rather than assuming USD: only "USD" (the only value
 * this system currently ever produces) is converted to the demo's INR
 * display; any other reported currency is formatted as-is, unconverted,
 * in its own real currency -- never silently relabeled. */
export function formatAmount(amount: string, currency: string): string {
  const value = Number(amount);
  if (Number.isNaN(value)) return `${amount} ${currency}`;
  if (currency === "USD") {
    return formatInr(convertUsdToInr(value));
  }
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      currencyDisplay: "narrowSymbol",
    }).format(value);
  } catch {
    return `${value.toFixed(2)} ${currency}`;
  }
}

/** Same USD->INR demo conversion as formatAmount, for pre-summed/aggregate
 * USD totals (e.g. the Overview KPI's sum across many transactions) where
 * there is no single per-item currency field to check against. Whole
 * rupees only -- paise precision on a large aggregate sum is not
 * meaningful and the extra digits were overflowing the KPI card. */
export function formatUsdSumAsInr(usdSum: number): string {
  return formatInr(convertUsdToInr(usdSum), 0);
}

export function formatPercent(fraction: number, digits = 1): string {
  if (!Number.isFinite(fraction)) return "—";
  return `${(fraction * 100).toFixed(digits)}%`;
}

export function formatCount(value: number): string {
  return new Intl.NumberFormat().format(Math.round(value));
}

export function formatMs(value: number | null, digits = 0): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return `${value.toFixed(digits)}ms`;
}

export function shortId(id: string, length = 8): string {
  return id.slice(0, length);
}

import { convertUsdToInr } from "./format";
import type { TransactionFeedItem } from "../types";

export type TimeRange = "24h" | "7d" | "30d";

export const TIME_RANGE_MS: Record<TimeRange, number> = {
  "24h": 24 * 60 * 60 * 1000,
  "7d": 7 * 24 * 60 * 60 * 1000,
  "30d": 30 * 24 * 60 * 60 * 1000,
};

export function filterByRange(items: TransactionFeedItem[], range: TimeRange, now = Date.now()) {
  const windowMs = TIME_RANGE_MS[range];
  return items.filter((item) => now - new Date(item.occurred_at).getTime() <= windowMs);
}

export interface TimeBucket {
  label: string;
  count: number;
}

/** Buckets by hour for 24h, by day otherwise -- real occurred_at values
 * only, zero-filled for buckets with no transactions rather than omitted,
 * so a quiet period reads as zero, not as a gap in the data. */
export function bucketByTime(items: TransactionFeedItem[], range: TimeRange, now = Date.now()): TimeBucket[] {
  const hourly = range === "24h";
  const bucketMs = hourly ? 60 * 60 * 1000 : 24 * 60 * 60 * 1000;
  const bucketCount = hourly ? 24 : range === "7d" ? 7 : 30;

  const buckets = new Map<number, number>();
  for (let i = 0; i < bucketCount; i++) buckets.set(i, 0);

  for (const item of items) {
    const age = now - new Date(item.occurred_at).getTime();
    const index = Math.floor(age / bucketMs);
    if (index >= 0 && index < bucketCount) {
      buckets.set(index, (buckets.get(index) ?? 0) + 1);
    }
  }

  const result: TimeBucket[] = [];
  for (let i = bucketCount - 1; i >= 0; i--) {
    const ts = now - i * bucketMs;
    const label = hourly
      ? new Date(ts).toLocaleTimeString(undefined, { hour: "numeric" })
      : new Date(ts).toLocaleDateString(undefined, { month: "short", day: "numeric" });
    result.push({ label, count: buckets.get(i) ?? 0 });
  }
  return result;
}

export function countBy<T extends string>(
  items: TransactionFeedItem[],
  key: (item: TransactionFeedItem) => T | null,
): Record<string, number> {
  const result: Record<string, number> = {};
  for (const item of items) {
    const k = key(item);
    if (k === null) continue;
    result[k] = (result[k] ?? 0) + 1;
  }
  return result;
}

export function topBy(counts: Record<string, number>, n: number): { name: string; count: number }[] {
  return Object.entries(counts)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, n);
}

export interface AmountBucket {
  label: string;
  count: number;
}

// INR-denominated bucket edges for the demo's display currency (see
// lib/format.ts's USD_TO_INR_DISPLAY_RATE) -- round thousands rather than
// an exact rate-multiple of the old $0/10/25/50/100/250/500/1000 edges,
// kept proportionally similar so the histogram's shape is unchanged.
const AMOUNT_BUCKET_EDGES = [0, 1000, 2500, 5000, 10000, 25000, 50000, 100000, Infinity];

function formatInrLabel(value: number): string {
  return `₹${new Intl.NumberFormat("en-IN").format(value)}`;
}

export function bucketByAmount(items: TransactionFeedItem[]): AmountBucket[] {
  const buckets = AMOUNT_BUCKET_EDGES.slice(0, -1).map((edge, i) => {
    const next = AMOUNT_BUCKET_EDGES[i + 1];
    return {
      label: next === Infinity ? `${formatInrLabel(edge)}+` : `${formatInrLabel(edge)}–${formatInrLabel(next)}`,
      min: edge,
      max: next,
      count: 0,
    };
  });

  for (const item of items) {
    const rawAmount = Number(item.amount);
    const amount = item.currency === "USD" ? convertUsdToInr(rawAmount) : rawAmount;
    const bucket = buckets.find((b) => amount >= b.min && amount < b.max);
    if (bucket) bucket.count += 1;
  }

  return buckets.map(({ label, count }) => ({ label, count }));
}

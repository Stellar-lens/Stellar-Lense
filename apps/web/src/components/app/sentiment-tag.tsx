import type { Sentiment } from "@/lib/news";

/**
 * Deliberately NOT colored with flag/up/down/accent. CryptoPanic's
 * bullish/bearish/important tags are a categorical label on an article,
 * not a wash-trading alert (flag), a price/score movement over time
 * (up/down), or an interactive/brand element (accent) — none of the
 * design system's reserved tokens actually describe what this is, so
 * this uses plain neutral styling rather than stretching one to fit.
 */
export function SentimentTag({ sentiment }: { sentiment: Sentiment | null }) {
  if (!sentiment) return null;
  return (
    <span className="rounded border border-border px-1.5 py-0.5 text-label text-muted">
      {sentiment}
    </span>
  );
}

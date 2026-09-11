import Link from "next/link";
import { getNewsFeed } from "@/lib/news";
import { buildCorrelationIndex, correlateNewsItem } from "@/lib/correlation";
import { formatTimestamp } from "@/lib/format";
import { SentimentTag } from "@/components/app/sentiment-tag";
import { NewsCorrelation } from "@/components/app/news-correlation";

const FILTERS = [
  { code: undefined, label: "All" },
  { code: "XLM", label: "XLM" },
  { code: "USDC", label: "USDC" },
];

type PageProps = {
  searchParams: Promise<{ currency?: string }>;
};

export default async function NewsPage({ searchParams }: PageProps) {
  const { currency } = await searchParams;

  const [{ items, warnings }, correlationIndex] = await Promise.all([
    getNewsFeed(currency),
    buildCorrelationIndex(),
  ]);

  return (
    <div>
      <h1 className="font-display text-xl font-medium text-text">
        News &amp; DD feed
      </h1>
      <p className="mt-1 text-sm text-muted">
        CryptoPanic (sentiment-tagged, primary) and CoinDesk (editorial,
        secondary), cross-referenced against derived risk-score history
        where an asset matches.
      </p>

      <div className="mt-4 flex items-center gap-2">
        {FILTERS.map((f) => {
          const active = (currency ?? "") === (f.code ?? "");
          const href = f.code ? `/app/news?currency=${f.code}` : "/app/news";
          return (
            <Link
              key={f.label}
              href={href}
              className={
                active
                  ? "rounded border border-accent/40 bg-accent/10 px-2.5 py-1 font-mono text-xs text-accent"
                  : "rounded border border-border px-2.5 py-1 font-mono text-xs text-muted hover:text-text"
              }
            >
              {f.label}
            </Link>
          );
        })}
      </div>

      {warnings.length > 0 && (
        <div className="mt-4 rounded border border-border bg-surface px-3 py-2 text-xs text-muted">
          {warnings.map((w) => (
            <div key={w}>{w}</div>
          ))}
        </div>
      )}

      <ul className="mt-6 divide-y divide-border/60">
        {items.map((item) => {
          const movement = correlateNewsItem(item, correlationIndex);
          return (
            <li key={item.id} className="py-3">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm text-text hover:text-accent"
                  >
                    {item.title}
                  </a>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2">
                    <SentimentTag sentiment={item.sentiment} />
                    <span className="font-mono text-xs text-muted">
                      {item.source === "cryptopanic"
                        ? item.domain ?? "cryptopanic"
                        : "coindesk"}
                    </span>
                    {item.currencies.map((c) => (
                      <span
                        key={c}
                        className="font-mono text-xs text-muted"
                      >
                        {c}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1.5">
                  <span className="font-mono text-xs text-muted">
                    {formatTimestamp(item.publishedAt)}
                  </span>
                  <NewsCorrelation movement={movement} />
                </div>
              </div>
            </li>
          );
        })}
        {items.length === 0 && (
          <li className="py-8 text-center text-sm text-muted">
            No news items{currency ? ` for ${currency}` : ""}.
          </li>
        )}
      </ul>
    </div>
  );
}

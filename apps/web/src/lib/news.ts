/**
 * Server-only news feed integration (plan §4.3): CryptoPanic as the
 * primary, sentiment-tagged, per-currency-filterable source; CoinDesk's
 * public RSS feed as secondary, for editorial/regulatory pieces
 * CryptoPanic's aggregator headlines don't cover.
 *
 * Import this only from Route Handlers / Server Components — it reads
 * CRYPTOPANIC_API_TOKEN (no NEXT_PUBLIC_ prefix, so it never reaches the
 * client bundle) and calls both APIs directly. CoinDesk's feed needs no
 * key; there's no equivalent "CoinDesk API key" to provide for a feed
 * integration like this one — see the README note next to this file's
 * usage in the news route for why.
 */
import { XMLParser } from "fast-xml-parser";

export type NewsSource = "cryptopanic" | "coindesk";
export type Sentiment = "bullish" | "bearish" | "important";

export type NewsItem = {
  id: string;
  source: NewsSource;
  title: string;
  url: string;
  publishedAt: string; // ISO 8601
  currencies: string[]; // uppercase asset codes, e.g. ["XLM"]
  sentiment: Sentiment | null;
  domain: string | null;
};

export type NewsFeedResult = {
  items: NewsItem[];
  warnings: string[];
};

const CRYPTOPANIC_URL = "https://cryptopanic.com/api/v1/posts/";
const COINDESK_RSS_URL = "https://www.coindesk.com/arc/outboundfeeds/rss/";

// A news item mentions an asset by name as often as by ticker ("Stellar
// Foundation" as often as "XLM"), and only CryptoPanic tags currencies
// structurally — CoinDesk's RSS doesn't. This is the best-effort bridge
// for CoinDesk items and for matching either source against the app's
// known asset pairs. Keep it to assets this app actually scores.
const CURRENCY_ALIASES: Record<string, string[]> = {
  XLM: ["stellar", "xlm", "lumens", "lumen"],
  USDC: ["usdc", "usd coin"],
};

function inferCurrencies(text: string): string[] {
  const lower = text.toLowerCase();
  const found: string[] = [];
  for (const [code, aliases] of Object.entries(CURRENCY_ALIASES)) {
    if (aliases.some((a) => lower.includes(a))) found.push(code);
  }
  return found;
}

type CryptoPanicPost = {
  id: number | string;
  title: string;
  url: string;
  published_at: string;
  domain?: string;
  source?: { domain?: string };
  currencies?: { code?: string }[];
  votes?: {
    positive?: number;
    negative?: number;
    important?: number;
  };
};

function deriveSentiment(votes: CryptoPanicPost["votes"]): Sentiment | null {
  if (!votes) return null;
  if ((votes.important ?? 0) > 0) return "important";
  const positive = votes.positive ?? 0;
  const negative = votes.negative ?? 0;
  if (positive > 0 && positive > negative) return "bullish";
  if (negative > 0 && negative > positive) return "bearish";
  return null;
}

async function fetchCryptoPanic(
  currency?: string
): Promise<{ items: NewsItem[]; warning?: string }> {
  const token = process.env.CRYPTOPANIC_API_TOKEN;
  if (!token) {
    return {
      items: [],
      warning:
        "CryptoPanic not configured — missing CRYPTOPANIC_API_TOKEN. See apps/web/.env.example.",
    };
  }

  const params = new URLSearchParams({ auth_token: token, public: "true" });
  if (currency) params.set("currencies", currency);

  try {
    const res = await fetch(`${CRYPTOPANIC_URL}?${params}`, {
      next: { revalidate: 300 },
    });
    if (!res.ok) {
      return {
        items: [],
        warning: `CryptoPanic request failed: HTTP ${res.status}`,
      };
    }
    const data = (await res.json()) as { results?: CryptoPanicPost[] };
    const items: NewsItem[] = (data.results ?? []).map((post) => ({
      id: `cryptopanic:${post.id}`,
      source: "cryptopanic",
      title: post.title,
      url: post.url,
      publishedAt: post.published_at,
      currencies: (post.currencies ?? [])
        .map((c) => c.code?.toUpperCase())
        .filter((c): c is string => Boolean(c)),
      sentiment: deriveSentiment(post.votes),
      domain: post.domain ?? post.source?.domain ?? null,
    }));
    return { items };
  } catch (err) {
    return {
      items: [],
      warning: `CryptoPanic request failed: ${(err as Error).message}`,
    };
  }
}

type RssItem = {
  title?: string;
  link?: string;
  guid?: string;
  pubDate?: string;
};

async function fetchCoinDesk(): Promise<{
  items: NewsItem[];
  warning?: string;
}> {
  try {
    const res = await fetch(COINDESK_RSS_URL, { next: { revalidate: 300 } });
    if (!res.ok) {
      return {
        items: [],
        warning: `CoinDesk RSS request failed: HTTP ${res.status}`,
      };
    }
    const xml = await res.text();
    const parsed = new XMLParser().parse(xml) as {
      rss?: { channel?: { item?: RssItem | RssItem[] } };
    };
    const raw = parsed.rss?.channel?.item ?? [];
    const list = Array.isArray(raw) ? raw : [raw];

    const items: NewsItem[] = list
      .filter((it) => it.title && it.link)
      .map((it, i) => {
        const title = String(it.title).trim();
        return {
          id: `coindesk:${it.guid ?? it.link ?? i}`,
          source: "coindesk" as const,
          title,
          url: String(it.link),
          publishedAt: it.pubDate
            ? new Date(it.pubDate).toISOString()
            : new Date().toISOString(),
          currencies: inferCurrencies(title),
          sentiment: null, // editorial wire, not community-voted
          domain: "coindesk.com",
        };
      });
    return { items };
  } catch (err) {
    return {
      items: [],
      warning: `CoinDesk RSS fetch failed: ${(err as Error).message}`,
    };
  }
}

export async function getNewsFeed(currency?: string): Promise<NewsFeedResult> {
  const [cp, cd] = await Promise.all([
    fetchCryptoPanic(currency),
    fetchCoinDesk(),
  ]);

  let items = [...cp.items, ...cd.items];
  if (currency) {
    const code = currency.toUpperCase();
    items = items.filter((i) => i.currencies.includes(code));
  }
  items.sort(
    (a, b) => Date.parse(b.publishedAt) - Date.parse(a.publishedAt)
  );

  const warnings = [cp.warning, cd.warning].filter(
    (w): w is string => Boolean(w)
  );
  return { items, warnings };
}

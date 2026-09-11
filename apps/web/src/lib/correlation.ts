import { getRiskRanking, getScoreHistory, type ScoreHistoryPoint } from "@/lib/api";
import { pairSymbol } from "@/lib/format";
import type { NewsItem } from "@/lib/news";

type PairHistory = { pair: string; history: ScoreHistoryPoint[] };
export type CorrelationIndex = Map<string, PairHistory[]>;

/** currency code (base asset, e.g. "XLM") -> every known pair trading it,
 * each with its derived score history. Built once per feed render and
 * reused across all news items, rather than a fetch per item. */
export async function buildCorrelationIndex(): Promise<CorrelationIndex> {
  const ranking = await getRiskRanking();
  const index: CorrelationIndex = new Map();

  await Promise.all(
    ranking.map(async (r) => {
      const base = pairSymbol(r.asset_pair).split("/")[0];
      const history = await getScoreHistory(r.asset_pair);
      const list = index.get(base) ?? [];
      list.push({ pair: r.asset_pair, history });
      index.set(base, list);
    })
  );
  return index;
}

export type ScoreMovement = {
  pair: string;
  /** Average score at the latest history point at or before the news's
   * publish time, if any. */
  before: number | null;
  /** Average score at the earliest history point after the news's
   * publish time — this is the "spiked after this news" number, when
   * present. Null whenever the news is more recent than every known
   * history point (true for any live news against this demo's frozen
   * 2026-06-01 seed data — see api.storage.pair_score_history). */
  after: number | null;
  /** Latest known average score regardless of the news timing, so the
   * UI still has something to show when `after` is null instead of
   * fabricating a "spike" that isn't there. */
  current: number | null;
};

export function correlateNewsItem(
  item: NewsItem,
  index: CorrelationIndex
): ScoreMovement | null {
  for (const code of item.currencies) {
    const matches = index.get(code);
    if (!matches?.length) continue;

    const best = matches.reduce((a, b) => {
      const maxA = Math.max(0, ...a.history.map((h) => h.max_score));
      const maxB = Math.max(0, ...b.history.map((h) => h.max_score));
      return maxB > maxA ? b : a;
    });
    if (best.history.length === 0) continue;

    const publishedMs = Date.parse(item.publishedAt);
    let before: ScoreHistoryPoint | null = null;
    let after: ScoreHistoryPoint | null = null;
    for (const point of best.history) {
      if (Date.parse(point.timestamp) <= publishedMs) {
        before = point;
      } else if (!after) {
        after = point;
      }
    }

    return {
      pair: best.pair,
      before: before?.average_score ?? null,
      after: after?.average_score ?? null,
      current: best.history[best.history.length - 1]?.average_score ?? null,
    };
  }
  return null;
}

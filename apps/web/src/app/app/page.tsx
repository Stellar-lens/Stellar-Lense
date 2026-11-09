import Link from "next/link";
import { getMarket, getRiskRanking } from "@/lib/api";
import {
  formatPercent,
  formatPrice,
  formatVolume,
  pairAssets,
  pairSymbol,
  riskScoreColorClass,
} from "@/lib/format";

export default async function OverviewPage() {
  const [ranking, market] = await Promise.all([getRiskRanking(), getMarket()]);
  const marketByPair = new Map(market.map((m) => [m.asset_pair, m]));

  return (
    <div>
      <h1 className="text-h3 text-text">Asset Risk Rankings</h1>
      <p className="mt-1 text-body-sm text-muted">
        Tracked Stellar DEX pairs, ranked by the average risk score of the
        wallets trading them. Price is in counter-asset units; 24h change
        and volume come from Horizon trade aggregations.
      </p>

      <table className="mt-5 w-full border-collapse text-left">
        <thead>
          <tr className="border-b border-border text-label text-muted">
            <th className="py-2 pr-4 font-normal">#</th>
            <th className="py-2 pr-4 font-normal">Asset</th>
            <th className="py-2 pr-4 text-right font-normal">Risk Score</th>
            <th className="py-2 pr-4 text-right font-normal">Price</th>
            <th className="py-2 pr-4 text-right font-normal">24h</th>
            <th className="py-2 pr-4 text-right font-normal">24h volume</th>
            <th className="py-2 text-right font-normal">Flags</th>
          </tr>
        </thead>
        <tbody>
          {ranking.map((r, i) => {
            const score = Math.round(r.average_score);
            const m = marketByPair.get(r.asset_pair);
            const counter = pairAssets(r.asset_pair)[1].code;
            const change = m?.change_24h_pct ?? null;
            const changeColor =
              change === null || change === 0
                ? "text-muted"
                : change > 0
                  ? "text-up"
                  : "text-down";
            const clean = r.flagged_wallets === 0;

            return (
              <tr
                key={r.asset_pair}
                className="border-b border-border/60 hover:bg-surface"
              >
                <td className="py-2.5 pr-4 text-data-base text-muted">
                  {i + 1}
                </td>
                <td className="py-2.5 pr-4">
                  <Link
                    href={`/app/assets/${encodeURIComponent(r.asset_pair)}`}
                    className="text-data-base text-text hover:text-accent"
                  >
                    {pairSymbol(r.asset_pair)}
                  </Link>
                </td>
                <td
                  className={`py-2.5 pr-4 text-right text-data-base ${riskScoreColorClass(score)}`}
                >
                  {score}
                </td>
                <td className="py-2.5 pr-4 text-right text-data-base text-text">
                  {m?.price != null ? formatPrice(m.price, counter) : "—"}
                </td>
                <td className={`py-2.5 pr-4 text-right text-data-base ${changeColor}`}>
                  {change !== null ? formatPercent(change) : "—"}
                </td>
                <td className="py-2.5 pr-4 text-right text-data-base text-muted">
                  {m ? formatVolume(m.counter_volume_24h, counter) : "—"}
                </td>
                <td
                  className={`py-2.5 text-right text-data-base ${clean ? "text-muted" : "text-flag"}`}
                >
                  {clean ? "Clean" : `${r.flagged_wallets} Flagged`}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

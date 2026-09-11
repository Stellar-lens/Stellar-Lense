import Link from "next/link";
import { getRiskRanking } from "@/lib/api";
import {
  formatPercent,
  formatPrice,
  formatVolume,
  pairSymbol,
  riskScoreColorClass,
} from "@/lib/format";
import { getPlaceholderMarketData } from "@/lib/placeholder-market";

export default async function OverviewPage() {
  const ranking = await getRiskRanking();

  return (
    <div>
      <h1 className="text-h3 text-text">Asset Risk Rankings</h1>
      <p className="mt-1 text-body-sm text-muted">
        Every asset pair on the Stellar DEX, ranked by average wallet risk
        score.
      </p>

      <table className="mt-5 w-full border-collapse text-left">
        <thead>
          <tr className="border-b border-border text-label text-muted">
            <th className="py-2 pr-4 font-normal">#</th>
            <th className="py-2 pr-4 font-normal">Asset</th>
            <th className="py-2 pr-4 text-right font-normal">Risk Score</th>
            <th className="py-2 pr-4 text-right font-normal">Price</th>
            <th className="py-2 pr-4 text-right font-normal">24h</th>
            <th className="py-2 pr-4 text-right font-normal">Volume</th>
            <th className="py-2 text-right font-normal">Flags</th>
          </tr>
        </thead>
        <tbody>
          {ranking.map((r, i) => {
            const score = Math.round(r.average_score);
            const market = getPlaceholderMarketData(r.asset_pair);
            const changeColor =
              market.change24h > 0
                ? "text-up"
                : market.change24h < 0
                  ? "text-down"
                  : "text-muted";
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
                  {formatPrice(market.price)}
                </td>
                <td className={`py-2.5 pr-4 text-right text-data-base ${changeColor}`}>
                  {formatPercent(market.change24h)}
                </td>
                <td className="py-2.5 pr-4 text-right text-data-base text-muted">
                  {formatVolume(market.volume)}
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

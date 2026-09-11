import Link from "next/link";
import { getRiskRanking } from "@/lib/api";
import { pairIssuer, pairSymbol, shortenWallet } from "@/lib/format";
import { ScoreBadge } from "@/components/app/score-badge";

export default async function OverviewPage() {
  const ranking = await getRiskRanking();

  return (
    <div>
      <h1 className="text-h3 text-text">Asset risk ranking</h1>
      <p className="mt-1 text-body-sm text-muted">
        Every asset pair on the Stellar DEX, ranked by average wallet risk
        score.
      </p>

      <table className="mt-5 w-full border-collapse text-left">
        <thead>
          <tr className="border-b border-border text-label text-muted">
            <th className="py-2 pr-4 font-normal">Pair</th>
            <th className="py-2 pr-4 font-normal">Issuer</th>
            <th className="py-2 pr-4 text-right font-normal">Avg score</th>
            <th className="py-2 pr-4 text-right font-normal">Max score</th>
            <th className="py-2 pr-4 text-right font-normal">Flagged</th>
            <th className="py-2 text-right font-normal">Wallets</th>
          </tr>
        </thead>
        <tbody>
          {ranking.map((r) => (
            <tr
              key={r.asset_pair}
              className="border-b border-border/60 hover:bg-surface"
            >
              <td className="py-2.5 pr-4">
                <Link
                  href={`/app/assets/${encodeURIComponent(r.asset_pair)}`}
                  className="text-data-base text-text hover:text-accent"
                >
                  {pairSymbol(r.asset_pair)}
                </Link>
              </td>
              <td className="py-2.5 pr-4 text-label text-muted">
                {pairIssuer(r.asset_pair)
                  ? shortenWallet(pairIssuer(r.asset_pair)!)
                  : "—"}
              </td>
              <td className="py-2.5 pr-4 text-right">
                <ScoreBadge score={Math.round(r.average_score)} />
              </td>
              <td className="py-2.5 pr-4 text-right">
                <ScoreBadge score={r.max_score} />
              </td>
              <td className="py-2.5 pr-4 text-right text-data-base text-text">
                {r.flagged_wallets}
              </td>
              <td className="py-2.5 text-right text-data-base text-muted">
                {r.total_wallets}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

import Link from "next/link";
import { getRiskRanking } from "@/lib/api";
import { pairIssuer, pairSymbol, shortenWallet } from "@/lib/format";
import { ScoreBadge } from "@/components/app/score-badge";

export default async function OverviewPage() {
  const ranking = await getRiskRanking();

  return (
    <div>
      <h1 className="font-display text-xl font-medium text-text">
        Asset risk ranking
      </h1>
      <p className="mt-1 text-sm text-muted">
        Every asset pair on the Stellar DEX, ranked by average wallet risk
        score.
      </p>

      <table className="mt-6 w-full border-collapse text-left">
        <thead>
          <tr className="border-b border-border text-xs text-muted">
            <th className="py-2 pr-4 font-body font-normal">Pair</th>
            <th className="py-2 pr-4 font-body font-normal">Issuer</th>
            <th className="py-2 pr-4 text-right font-body font-normal">
              Avg score
            </th>
            <th className="py-2 pr-4 text-right font-body font-normal">
              Max score
            </th>
            <th className="py-2 pr-4 text-right font-body font-normal">
              Flagged
            </th>
            <th className="py-2 text-right font-body font-normal">
              Wallets
            </th>
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
                  className="font-mono text-sm text-text hover:text-accent"
                >
                  {pairSymbol(r.asset_pair)}
                </Link>
              </td>
              <td className="py-2.5 pr-4 font-mono text-xs text-muted">
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
              <td className="py-2.5 pr-4 text-right font-mono text-sm text-text">
                {r.flagged_wallets}
              </td>
              <td className="py-2.5 text-right font-mono text-sm text-muted">
                {r.total_wallets}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

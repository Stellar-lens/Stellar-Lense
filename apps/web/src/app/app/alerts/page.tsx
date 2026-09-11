import Link from "next/link";
import { getRecentAlerts } from "@/lib/api";
import { formatTimestamp, pairSymbol, shortenWallet } from "@/lib/format";
import { ScoreBadge } from "@/components/app/score-badge";

export default async function AlertsPage() {
  const alerts = await getRecentAlerts();

  return (
    <div>
      <h1 className="font-display text-xl font-medium text-text">
        Flagged activity
      </h1>
      <p className="mt-1 text-sm text-muted">
        Wallet/asset-pair combinations currently at or above the risk
        threshold, highest score first.
      </p>

      <table className="mt-6 w-full border-collapse text-left">
        <thead>
          <tr className="border-b border-border text-xs text-muted">
            <th className="py-2 pr-4 font-body font-normal">Wallet</th>
            <th className="py-2 pr-4 font-body font-normal">Pair</th>
            <th className="py-2 pr-4 text-right font-body font-normal">
              Score
            </th>
            <th className="py-2 pr-4 font-body font-normal">Reason</th>
            <th className="py-2 text-right font-body font-normal">
              Detected
            </th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((a) => (
            <tr
              key={a.id}
              className="border-b border-border/60 hover:bg-surface"
            >
              <td className="py-2.5 pr-4 font-mono text-sm text-text">
                {shortenWallet(a.wallet)}
              </td>
              <td className="py-2.5 pr-4">
                <Link
                  href={`/app/assets/${encodeURIComponent(a.asset_pair)}`}
                  className="font-mono text-sm text-muted hover:text-accent"
                >
                  {pairSymbol(a.asset_pair)}
                </Link>
              </td>
              <td className="py-2.5 pr-4 text-right">
                <ScoreBadge score={a.score} />
              </td>
              <td className="py-2.5 pr-4 text-sm text-muted">{a.reason}</td>
              <td className="py-2.5 text-right font-mono text-xs text-muted">
                {formatTimestamp(a.timestamp)}
              </td>
            </tr>
          ))}
          {alerts.length === 0 && (
            <tr>
              <td colSpan={5} className="py-8 text-center text-sm text-muted">
                No flagged activity.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

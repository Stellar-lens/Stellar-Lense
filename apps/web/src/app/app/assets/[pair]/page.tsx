import Link from "next/link";
import { notFound } from "next/navigation";
import { getPairScores } from "@/lib/api";
import {
  formatFeatureName,
  isFlagged,
  pairIssuer,
  pairSymbol,
  shortenWallet,
} from "@/lib/format";
import { ScoreBadge } from "@/components/app/score-badge";
import { ShapBars } from "@/components/app/shap-bars";

type PageProps = {
  params: Promise<{ pair: string }>;
  searchParams: Promise<{ wallet?: string }>;
};

export default async function AssetDetailPage({
  params,
  searchParams,
}: PageProps) {
  const { pair: encodedPair } = await params;
  const pair = decodeURIComponent(encodedPair);
  const { wallet: selectedWallet } = await searchParams;

  const scores = await getPairScores(pair);
  if (scores.length === 0) notFound();

  const flaggedCount = scores.filter((s) => isFlagged(s.score)).length;
  const avgScore = Math.round(
    scores.reduce((sum, s) => sum + s.score, 0) / scores.length
  );
  const maxScore = Math.max(...scores.map((s) => s.score));

  const active =
    scores.find((s) => s.wallet === selectedWallet) ??
    scores.reduce((best, s) => (s.score > best.score ? s : best), scores[0]);

  return (
    <div>
      <Link
        href="/app"
        className="text-label text-muted transition-colors hover:text-text"
      >
        ← Overview
      </Link>

      <div className="mt-2 flex items-baseline gap-3">
        <h1 className="text-h3 text-text">{pairSymbol(pair)}</h1>
        {pairIssuer(pair) && (
          <span className="text-label text-muted">
            {shortenWallet(pairIssuer(pair)!)}
          </span>
        )}
      </div>

      <dl className="mt-5 grid grid-cols-4 gap-5 border-b border-border pb-5">
        <div>
          <dt className="text-label text-muted">Avg score</dt>
          <dd className="mt-1">
            <ScoreBadge score={avgScore} size="lg" />
          </dd>
        </div>
        <div>
          <dt className="text-label text-muted">Max score</dt>
          <dd className="mt-1">
            <ScoreBadge score={maxScore} size="lg" />
          </dd>
        </div>
        <div>
          <dt className="text-label text-muted">Flagged wallets</dt>
          <dd className="mt-1 text-data-base text-text">{flaggedCount}</dd>
        </div>
        <div>
          <dt className="text-label text-muted">Total wallets</dt>
          <dd className="mt-1 text-data-base text-text">{scores.length}</dd>
        </div>
      </dl>

      <div className="mt-5 grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-6">
        <div>
          <h2 className="text-label text-text">Wallets</h2>
          <table className="mt-2 w-full border-collapse text-left">
            <thead>
              <tr className="border-b border-border text-label text-muted">
                <th className="py-2 pr-4 font-normal">Wallet</th>
                <th className="py-2 pr-4 text-right font-normal">Score</th>
                <th className="py-2 pr-4 text-right font-normal">Benford</th>
                <th className="py-2 text-right font-normal">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {scores.map((s) => (
                <tr
                  key={s.wallet}
                  className={
                    s.wallet === active.wallet
                      ? "border-b border-border/60 bg-surface"
                      : "border-b border-border/60 hover:bg-surface"
                  }
                >
                  <td className="py-2.5 pr-4">
                    <Link
                      href={`?wallet=${encodeURIComponent(s.wallet)}`}
                      className="text-data-base text-text hover:text-accent"
                    >
                      {shortenWallet(s.wallet)}
                    </Link>
                  </td>
                  <td className="py-2.5 pr-4 text-right">
                    <ScoreBadge score={s.score} />
                  </td>
                  <td className="py-2.5 pr-4 text-right text-label text-muted">
                    {s.benford_flag ? "non-conforming" : "conforming"}
                  </td>
                  <td className="py-2.5 text-right text-data-base text-muted">
                    {s.confidence.toFixed(0)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div>
          <div className="flex items-baseline justify-between">
            <h2 className="text-label text-text">Score explanation</h2>
            <span className="text-label text-muted">
              {shortenWallet(active.wallet)}
            </span>
          </div>

          {active.shap ? (
            <div className="mt-3">
              <ShapBars shap={active.shap} />
              <p className="mt-3 text-body-sm text-muted">
                SHAP attribution toward the wash-trading classification.
                Positive values pushed this wallet&apos;s score up.
              </p>
            </div>
          ) : (
            <p className="mt-3 text-body-sm text-muted">
              No trained model attribution available for this wallet;
              scored on the Benford + heuristic fallback path.
            </p>
          )}

          <div className="mt-5 border-t border-border pt-3">
            <h3 className="text-label text-text">Benford&apos;s Law</h3>
            <div className="mt-2 grid grid-cols-3 gap-4">
              <div>
                <dt className="text-label text-muted">MAD</dt>
                <dd className="mt-1 text-data-base text-text">
                  {active.benford.mad.toFixed(4)}
                </dd>
              </div>
              <div>
                <dt className="text-label text-muted">Chi-square</dt>
                <dd className="mt-1 text-data-base text-text">
                  {active.benford.chi_square.toFixed(2)}
                </dd>
              </div>
              <div>
                <dt className="text-label text-muted">Sample</dt>
                <dd className="mt-1 text-data-base text-text">
                  {active.benford.sample_size}
                </dd>
              </div>
            </div>
          </div>

          <div className="mt-5 border-t border-border pt-3">
            <h3 className="text-label text-text">Raw features</h3>
            <dl className="mt-2 space-y-1.5">
              {Object.entries(active.features).map(([name, value]) => (
                <div key={name} className="flex justify-between">
                  <dt className="text-label text-muted">
                    {formatFeatureName(name)}
                  </dt>
                  <dd className="text-data-base text-text">
                    {value.toFixed(3)}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      </div>
    </div>
  );
}

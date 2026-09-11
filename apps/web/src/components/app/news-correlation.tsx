import Link from "next/link";
import type { ScoreMovement } from "@/lib/correlation";

/**
 * `up`/`down` are a genuine fit here — this is a literal score movement
 * (before vs. after the news's publish time), which is exactly what those
 * tokens are for. Direction only, not valence: `up` means the score rose
 * numerically, regardless of whether that's "bad" for the asset. Delta
 * shown as a signed number, not an arrow glyph, matching how SHAP
 * attributions are already displayed elsewhere in the app.
 */
export function NewsCorrelation({ movement }: { movement: ScoreMovement | null }) {
  if (!movement) return null;

  const pairHref = `/app/assets/${encodeURIComponent(movement.pair)}`;

  if (movement.before !== null && movement.after !== null) {
    const delta = movement.after - movement.before;
    const color = delta > 0 ? "text-up" : delta < 0 ? "text-down" : "text-muted";
    return (
      <Link
        href={pairHref}
        className="inline-flex items-center gap-1.5 text-data-base hover:underline"
      >
        <span className="text-muted">score {movement.after.toFixed(0)}</span>
        <span className={color}>
          ({delta >= 0 ? "+" : ""}
          {delta.toFixed(0)})
        </span>
      </Link>
    );
  }

  if (movement.current !== null) {
    return (
      <Link
        href={pairHref}
        className="inline-flex items-center gap-1.5 text-data-base text-muted hover:underline"
      >
        <span>current score</span>
        <span className="text-text">{movement.current.toFixed(0)}</span>
      </Link>
    );
  }

  return null;
}

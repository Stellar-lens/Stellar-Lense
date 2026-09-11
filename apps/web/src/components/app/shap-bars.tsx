import { formatFeatureName } from "@/lib/format";

/**
 * Diverging bar chart for SHAP attributions: each feature's contribution
 * to the wash-trading classification, positive (pushed the score up) in
 * flag color since that's a genuine risk signal, negative (pushed it
 * down) in a neutral muted tone — never up/down, this isn't a price or
 * score movement over time, it's a model attribution.
 */
export function ShapBars({ shap }: { shap: Record<string, number> }) {
  const entries = Object.entries(shap).sort(
    (a, b) => Math.abs(b[1]) - Math.abs(a[1])
  );
  const maxAbs = Math.max(...entries.map(([, v]) => Math.abs(v)), 1e-6);

  return (
    <div className="space-y-3">
      {entries.map(([name, value]) => {
        const halfWidthPct = (Math.abs(value) / maxAbs) * 50;
        const positive = value >= 0;
        return (
          <div
            key={name}
            className="grid grid-cols-[176px_1fr_72px] items-center gap-3"
          >
            <span className="truncate text-xs text-muted">
              {formatFeatureName(name)}
            </span>
            <div className="relative h-2 rounded-sm bg-border/40">
              <div className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-border" />
              <div
                className={
                  positive
                    ? "absolute left-1/2 top-0 h-full rounded-sm bg-flag"
                    : "absolute right-1/2 top-0 h-full rounded-sm bg-muted/60"
                }
                style={{ width: `${halfWidthPct}%` }}
              />
            </div>
            <span
              className={
                positive
                  ? "text-right font-mono text-xs text-flag"
                  : "text-right font-mono text-xs text-muted"
              }
            >
              {value >= 0 ? "+" : ""}
              {value.toFixed(3)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

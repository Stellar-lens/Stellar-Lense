import { isFlagged } from "@/lib/format";

/**
 * "base" (default) for inline table cells — Data Large would break row
 * height consistency there. "lg" for a standalone stat block that has room
 * to breathe (e.g. the asset-detail page's avg/max score), where the risk
 * score deserves the emphasis Data Large is for.
 */
export function ScoreBadge({
  score,
  size = "base",
}: {
  score: number;
  size?: "base" | "lg";
}) {
  const flagged = isFlagged(score);
  const sizeClass = size === "lg" ? "text-data-lg" : "text-data-base";
  return (
    <span
      className={
        flagged
          ? `rounded border border-flag/30 bg-flag/10 px-1.5 py-0.5 ${sizeClass} text-flag`
          : `${sizeClass} text-text`
      }
    >
      {score}
    </span>
  );
}

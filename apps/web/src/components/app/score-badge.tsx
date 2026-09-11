import { isFlagged } from "@/lib/format";

export function ScoreBadge({ score }: { score: number }) {
  const flagged = isFlagged(score);
  return (
    <span
      className={
        flagged
          ? "rounded border border-flag/30 bg-flag/10 px-1.5 py-0.5 font-mono text-xs text-flag"
          : "font-mono text-xs text-text"
      }
    >
      {score}
    </span>
  );
}

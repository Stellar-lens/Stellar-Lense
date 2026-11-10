import { ApiError, getMeta, type Meta } from "@/lib/api";
import { formatTimestamp } from "@/lib/format";

/** Where the numbers on every page come from, and how fresh they are.
 * Demo mode gets an unmissable banner; live mode a one-line provenance bar. */
export async function DataStatus() {
  let meta: Meta;
  try {
    meta = await getMeta();
  } catch (err) {
    const detail =
      err instanceof ApiError && err.status === 503
        ? `No data yet: ${err.detail}.`
        : "The API is unreachable, so no data can be shown.";
    return (
      <div role="status" className="border-b border-border bg-surface px-6 py-2 text-body-sm text-muted">
        {detail}
      </div>
    );
  }

  const method =
    meta.scoring.method === "ml" && meta.scoring.model
      ? `ML model ${meta.scoring.model.model_id} (${meta.scoring.model.trained_on})`
      : "fixed heuristic (Benford + trade patterns)";

  return (
    <>
      {meta.mode === "demo" && (
        <div role="alert" className="bg-flag px-6 py-2 text-body-sm font-medium text-bg">
          DEMO MODE: {meta.notice ?? "synthetic data, not Stellar network data."}
        </div>
      )}
      <div className="border-b border-border px-6 py-1.5 text-label text-muted">
        {meta.data_as_of ? (
          <>Data as of {formatTimestamp(meta.data_as_of)}</>
        ) : (
          <>No trades in the scoring window</>
        )}
        {meta.mode === "live" && meta.network && <> · Stellar {meta.network}</>}
        {" · "}
        {meta.pairs_tracked} pairs · scored with {method}
      </div>
    </>
  );
}

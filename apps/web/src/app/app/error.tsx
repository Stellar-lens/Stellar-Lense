"use client";

/** Shown when a page's API call fails, e.g. 503 before the pipeline's first
 * scoring run. The data-status bar above explains the cause. */
export default function AppError({ error }: { error: Error }) {
  return (
    <div className="text-body-sm text-muted">
      <h1 className="text-h3 text-text">No data to show</h1>
      <p className="mt-2">
        The API returned an error for this page. If the pipeline was just
        started, its first ingest and scoring run can take a few minutes.
      </p>
      <p className="mt-2 font-mono text-label">{error.message}</p>
    </div>
  );
}

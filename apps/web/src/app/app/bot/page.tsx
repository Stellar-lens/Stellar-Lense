export default function BotPage() {
  return (
    <div>
      <h1 className="text-h3 text-text">Trading bot</h1>
      <p className="mt-1 text-body-sm text-muted">
        Phase 1 (backtesting) is implemented in apps/bot — see its README for
        the CLI. Phase 2 (live signal alerts, wired to risk scores) and Phase
        3 (non-custodial execution) land here once built; this page is a
        placeholder, not a working UI yet.
      </p>
    </div>
  );
}

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-bg px-6 text-text">
      <h1 className="font-display text-4xl font-medium">Stellar Lense</h1>
      <p className="max-w-md text-center font-body text-base text-muted">
        Design system foundation check — background, text color, and all
        three fonts (display, body, mono) rendering via the token setup.
      </p>
      <p className="font-mono text-sm text-accent">
        risk_score: 74 · confidence: 0.92 · 2026-09-11T13:30:00Z
      </p>
    </main>
  );
}

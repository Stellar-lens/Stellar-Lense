const SIGNALS = [
  {
    step: "01",
    title: "Benford's Law",
    body: "Natural transaction volumes follow a predictable distribution of leading digits. Fabricated volume doesn't — so the deviation itself is a signal, before any model gets involved.",
  },
  {
    step: "02",
    title: "ML ensemble",
    body: "A Random Forest, XGBoost, and LightGBM ensemble trained on labeled wash-trading patterns layers a learned signal on top of the statistical one.",
  },
  {
    step: "03",
    title: "Graph-based ring detection",
    body: "Wash trading is rarely one wallet. Circular fund flows between colluding wallets show up as rings in the trade graph — patterns a single wallet's statistics alone would miss.",
  },
];

export function HowItWorks() {
  return (
    <section
      id="how-it-works"
      className="border-t border-border bg-surface/40"
    >
      <div className="mx-auto max-w-6xl px-6 py-24 md:py-32">
        <h2 className="max-w-lg font-display text-3xl font-medium text-text md:text-4xl">
          Three signals, one score.
        </h2>

        <div className="mt-16 grid gap-12 md:grid-cols-3 md:gap-8">
          {SIGNALS.map((s) => (
            <div key={s.step}>
              <span className="font-mono text-sm text-muted">{s.step}</span>
              <h3 className="mt-3 font-body text-base font-semibold text-text">
                {s.title}
              </h3>
              <p className="mt-3 text-sm leading-relaxed text-muted">
                {s.body}
              </p>
            </div>
          ))}
        </div>

        <p className="mt-16 max-w-2xl border-t border-border pt-8 text-sm text-muted">
          All three combine into a single 0–100 risk score, submitted
          on-chain to a Soroban contract — queryable by any wallet, dApp,
          or contract without trusting a centralized API.
        </p>
      </div>
    </section>
  );
}

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
      <div className="mx-auto max-w-6xl px-6 py-14 md:py-20">
        <h2 className="max-w-lg text-h2 text-text">
          Three signals, one score.
        </h2>

        <div className="mt-10 grid gap-8 md:grid-cols-3 md:gap-6">
          {SIGNALS.map((s) => (
            <div key={s.step}>
              <span className="text-data-base text-muted">{s.step}</span>
              <h3 className="mt-2 text-h3 text-text">{s.title}</h3>
              <p className="mt-2 text-body-sm text-muted">{s.body}</p>
            </div>
          ))}
        </div>

        <p className="mt-10 max-w-2xl border-t border-border pt-6 text-body-sm text-muted">
          All three combine into a single 0–100 risk score, submitted
          on-chain to a Soroban contract — queryable by any wallet, dApp,
          or contract without trusting a centralized API.
        </p>
      </div>
    </section>
  );
}

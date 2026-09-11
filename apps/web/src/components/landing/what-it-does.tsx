const AUDIENCES = [
  {
    title: "Asset issuers",
    body: "Show exchanges and investors that your token's volume is organic, not wash-inflated — backed by a public, auditable score instead of a claim.",
  },
  {
    title: "Protocols & AMMs",
    body: "Gate liquidity or lending actions against a wallet's live risk score directly from a Soroban contract call — no off-chain dependency, no oracle to trust.",
  },
  {
    title: "Traders & analysts",
    body: "Check a wallet or pair before trading it. Alerts and asset rankings surface risk before it shows up in your PnL.",
  },
];

export function WhatItDoes() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-24 md:py-32">
      <h2 className="max-w-lg font-display text-3xl font-medium text-text md:text-4xl">
        Every wallet, scored.
      </h2>
      <p className="mt-6 max-w-2xl text-lg text-muted">
        Stellar Lense ingests trade data from the Stellar Horizon API and
        scores every wallet and asset pair on the Stellar DEX for
        wash-trading risk, from 0 to 100. Scores update continuously,
        publish on-chain through a Soroban registry contract, and are
        available over a public REST API — so any dashboard, dApp, or
        smart contract can check a wallet before it matters.
      </p>

      <div className="mt-16 grid gap-12 md:grid-cols-3 md:gap-8">
        {AUDIENCES.map((a) => (
          <div key={a.title}>
            <h3 className="font-body text-base font-semibold text-text">
              {a.title}
            </h3>
            <p className="mt-3 text-sm leading-relaxed text-muted">
              {a.body}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

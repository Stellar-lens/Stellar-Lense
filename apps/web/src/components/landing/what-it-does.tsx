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
    <section className="mx-auto max-w-6xl px-6 py-14 md:py-20">
      <h2 className="max-w-lg text-h2 text-text">Every wallet, scored.</h2>
      <p className="mt-4 max-w-2xl text-body text-muted">
        Stellar Lense ingests trade data from the Stellar Horizon API and
        scores every wallet and asset pair on the Stellar DEX for
        wash-trading risk, from 0 to 100. Scores update continuously,
        publish on-chain through a Soroban registry contract, and are
        available over a public REST API — so any dashboard, dApp, or
        smart contract can check a wallet before it matters.
      </p>

      <div className="mt-10 grid gap-8 md:grid-cols-3 md:gap-6">
        {AUDIENCES.map((a) => (
          <div key={a.title}>
            <h3 className="text-h3 text-text">{a.title}</h3>
            <p className="mt-2 text-body-sm text-muted">{a.body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

import Link from "next/link";
import { RingGraphic } from "./ring-graphic";

export function Hero() {
  return (
    <section className="mx-auto grid max-w-6xl items-center gap-16 px-6 py-24 md:grid-cols-2 md:py-36">
      <div>
        <h1 className="animate-rise font-display text-5xl font-medium leading-[1.05] text-text md:text-6xl">
          The Stellar DEX,
          <br />
          made legible.
        </h1>
        <p
          className="animate-rise mt-6 max-w-md text-lg text-muted"
          style={{ animationDelay: "120ms" }}
        >
          Stellar Lense scores every wallet and trading pair on the Stellar
          DEX for wash-trading risk — Benford&apos;s Law statistics, an ML
          ensemble, and graph-based ring detection, published on-chain
          through a Soroban smart contract.
        </p>
        <div
          className="animate-rise mt-10 flex items-center gap-6"
          style={{ animationDelay: "240ms" }}
        >
          <Link
            href="/app"
            className="rounded-md bg-accent px-5 py-2.5 font-body text-sm font-medium text-bg transition-opacity hover:opacity-90"
          >
            Launch App
          </Link>
          <a
            href="#how-it-works"
            className="font-body text-sm text-muted transition-colors hover:text-text"
          >
            How it works
          </a>
        </div>
      </div>

      <div className="flex flex-col items-center gap-6">
        <RingGraphic />
        <div
          className="animate-rise w-full max-w-[280px] rounded-md border border-border bg-surface px-4 py-3 font-mono text-xs text-muted"
          style={{ animationDelay: "820ms" }}
        >
          <div className="flex justify-between">
            <span>wallet</span>
            <span className="text-text">GABC…F3K2</span>
          </div>
          <div className="mt-1 flex justify-between">
            <span>pair</span>
            <span className="text-text">XLM/USDC</span>
          </div>
          <div className="mt-1 flex justify-between">
            <span>score</span>
            <span className="text-flag">82 — flagged</span>
          </div>
        </div>
      </div>
    </section>
  );
}

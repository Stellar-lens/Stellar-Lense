import Link from "next/link";
import { RingGraphic } from "./ring-graphic";

export function Hero() {
  return (
    <section className="mx-auto grid max-w-6xl items-center gap-10 px-6 py-14 md:grid-cols-2 md:py-20">
      <div>
        <h1 className="animate-rise text-h1 text-text">
          The Stellar DEX,
          <br />
          made legible.
        </h1>
        <p
          className="animate-rise mt-4 max-w-md text-body text-muted"
          style={{ animationDelay: "80ms" }}
        >
          Stellar Lense scores every wallet and trading pair on the Stellar
          DEX for wash-trading risk — Benford&apos;s Law statistics, an ML
          ensemble, and graph-based ring detection, published on-chain
          through a Soroban smart contract.
        </p>
        <div
          className="animate-rise mt-6 flex items-center gap-6"
          style={{ animationDelay: "160ms" }}
        >
          <Link
            href="/app"
            className="rounded-md bg-accent px-5 py-2.5 text-label text-bg transition-opacity hover:opacity-90"
          >
            Launch App
          </Link>
          <a
            href="#how-it-works"
            className="text-label text-muted transition-colors hover:text-text"
          >
            How it works
          </a>
        </div>
      </div>

      <div className="flex flex-col items-center gap-5">
        <RingGraphic />
        <div
          className="animate-rise w-full max-w-[280px] rounded-md border border-border bg-surface px-4 py-3 text-label text-muted"
          style={{ animationDelay: "540ms" }}
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

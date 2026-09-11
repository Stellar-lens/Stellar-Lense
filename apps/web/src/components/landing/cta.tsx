import Link from "next/link";

export function Cta() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-24 text-center md:py-40">
      <h2 className="mx-auto max-w-xl font-display text-3xl font-medium text-text md:text-4xl">
        See the score behind the volume.
      </h2>
      <p className="mx-auto mt-6 max-w-md text-lg text-muted">
        Live risk scores, alerts, and asset rankings for the Stellar DEX.
      </p>
      <div className="mt-10 flex items-center justify-center gap-6">
        <Link
          href="/app"
          className="rounded-md bg-accent px-6 py-3 font-body text-sm font-medium text-bg transition-opacity hover:opacity-90"
        >
          Launch App
        </Link>
        <Link
          href="/docs"
          className="font-body text-sm text-muted transition-colors hover:text-text"
        >
          Read the API docs
        </Link>
      </div>
    </section>
  );
}

import Link from "next/link";

export function Cta() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-14 text-center md:py-24">
      <h2 className="mx-auto max-w-xl text-h2 text-text">
        See the score behind the volume.
      </h2>
      <p className="mx-auto mt-4 max-w-md text-body text-muted">
        Live risk scores, alerts, and asset rankings for the Stellar DEX.
      </p>
      <div className="mt-6 flex items-center justify-center gap-6">
        <Link
          href="/app"
          className="rounded-md bg-accent px-6 py-3 text-label text-bg transition-opacity hover:opacity-90"
        >
          Launch App
        </Link>
        <Link
          href="/docs"
          className="text-label text-muted transition-colors hover:text-text"
        >
          Read the API docs
        </Link>
      </div>
    </section>
  );
}

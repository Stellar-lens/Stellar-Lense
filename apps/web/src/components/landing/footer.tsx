import Link from "next/link";

export function Footer() {
  return (
    <footer className="border-t border-border">
      <div className="mx-auto max-w-6xl px-6 py-14 text-center md:py-20">
        <h2 className="mx-auto max-w-xl text-h2 text-text">
          Start screening assets in minutes.
        </h2>
        <div className="mt-6 flex items-center justify-center">
          <Link
            href="/app"
            className="rounded-md bg-accent px-6 py-3 text-label text-bg transition-opacity hover:opacity-90"
          >
            Launch App
          </Link>
        </div>
      </div>
    </footer>
  );
}

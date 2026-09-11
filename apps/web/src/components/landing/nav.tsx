import Link from "next/link";

export function Nav() {
  return (
    <header className="sticky top-0 z-10 border-b border-border/60 bg-bg/80 backdrop-blur">
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4 text-label">
        <Link href="/" className="text-text">
          [Stellar Lense]
        </Link>
        <div className="flex items-center gap-6">
          <a href="#how-it-works" className="text-muted transition-colors hover:text-text">
            [Product]
          </a>
          <Link href="/docs" className="text-muted transition-colors hover:text-text">
            [Docs]
          </Link>
          <Link href="/app" className="text-muted transition-colors hover:text-text">
            [Risk Registry]
          </Link>
          <Link
            href="/app"
            className="rounded-md bg-accent px-4 py-2 text-bg transition-opacity hover:opacity-90"
          >
            Launch App
          </Link>
        </div>
      </nav>
    </header>
  );
}

import Link from "next/link";

const LINKS = [
  { href: "/app", label: "Rankings" },
  { href: "/app/alerts", label: "Alerts" },
  { href: "/app/news", label: "News" },
  { href: "/app/bot", label: "Bot" },
];

export function AppNav() {
  return (
    <header className="sticky top-0 z-10 border-b border-border bg-bg">
      <div className="flex items-center justify-between gap-6 px-6 py-3">
        <div className="flex items-center gap-6">
          <Link href="/" className="text-label text-text">
            Stellar Lense
          </Link>
          <nav className="flex items-center gap-4 text-label">
            {LINKS.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className="text-muted transition-colors hover:text-text"
              >
                {l.label}
              </Link>
            ))}
          </nav>
        </div>
        <button
          type="button"
          className="rounded-md border border-border px-3 py-1.5 text-label text-text transition-colors hover:border-accent hover:text-accent"
        >
          Connect Wallet
        </button>
      </div>
    </header>
  );
}

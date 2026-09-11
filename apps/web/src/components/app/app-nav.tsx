import Link from "next/link";

const LINKS = [
  { href: "/app", label: "Overview" },
  { href: "/app/alerts", label: "Alerts" },
  { href: "/app/news", label: "News" },
];

export function AppNav() {
  return (
    <header className="sticky top-0 z-10 border-b border-border bg-bg">
      <div className="flex items-center gap-6 px-6 py-3">
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
    </header>
  );
}

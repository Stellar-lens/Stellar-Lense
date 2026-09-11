# Stellar Lense — Design System v1

Derived from references: DexScreener (data density), Wegonorth (landing page mood — primary reference), CoinGecko (dashboard structure, not visual style).

## Fonts (add to `app/layout.tsx`)

```ts
import { Space_Grotesk, IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";

const display = Space_Grotesk({ subsets: ["latin"], variable: "--font-display" });
const body = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400","500","600"], variable: "--font-body" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400","500"], variable: "--font-mono" });

// apply variable classes to <html> or <body>: `${display.variable} ${body.variable} ${mono.variable}`
```

## CSS variables (`app/globals.css`)

```css
:root {
  --color-bg: #0B0C10;
  --color-surface: #14161B;
  --color-border: #24262C;
  --color-text: #EDEEF0;
  --color-text-muted: #8A8F98;

  --color-accent: #5B6EF5;      /* brand/interactive only */
  --color-flag: #E8A33D;        /* risk/wash-trading alerts only */
  --color-up: #22C55E;          /* price/data increase only */
  --color-down: #EF4444;        /* price/data decrease only */

  --font-display: var(--font-display), sans-serif;
  --font-body: var(--font-body), sans-serif;
  --font-mono: var(--font-mono), monospace;
}

body {
  background: var(--color-bg);
  color: var(--color-text);
  font-family: var(--font-body);
}
```

## Tailwind config (`tailwind.config.ts`)

```ts
import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--color-bg)",
        surface: "var(--color-surface)",
        border: "var(--color-border)",
        text: "var(--color-text)",
        muted: "var(--color-text-muted)",
        accent: "var(--color-accent)",
        flag: "var(--color-flag)",
        up: "var(--color-up)",
        down: "var(--color-down)",
      },
      fontFamily: {
        display: ["var(--font-display)"],
        body: ["var(--font-body)"],
        mono: ["var(--font-mono)"],
      },
    },
  },
} satisfies Config;
```

## Usage rules (for Claude Code / whoever builds components)

1. **Color discipline is the whole system.** `accent` = interactive/brand only. `flag` = wash-trading/risk alerts only. `up`/`down` = price or score movement only. Never substitute one for another even if it "looks fine" in a given spot — the color coding is how a user reads risk vs. price vs. navigation at a glance in a dense data product.
2. **Numeric data (prices, scores, timestamps, percentages) is always `font-mono`.** Everything else is `font-body`. Headlines/hero text is `font-display`.
3. **Landing page (marketing routes):** generous negative space, one deliberate animated moment on load (not per-section fade-ins), bracketed nav labels used only in the nav — not stamped on every UI label.
4. **App/dashboard routes:** dense data tables, dark surfaces, minimal decoration — DexScreener-style information density, not CoinGecko's card-heavy layout.
5. Avoid: gradient-card kits, ALL-CAPS eyebrow labels above every heading, arrow (→) suffixes on buttons, identical rounded cards with the same soft shadow everywhere.

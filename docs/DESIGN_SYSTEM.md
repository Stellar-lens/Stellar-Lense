# Stellar Lense — Design System v2

Derived from references: DexScreener (data density), Wegonorth (original landing page mood — since tightened toward a more standard professional density, see below), CoinGecko (dashboard structure, not visual style).

**v2 change:** replaced the three-font system (Space Grotesk display / IBM Plex Sans body / IBM Plex Mono numeric) with a single Poppins family across the whole app, using a standard weight-based type hierarchy instead of separate display/body/mono roles. Also tightened the general spacing scale (section padding, line-heights) from the original Wegonorth-inspired generous negative space to a tighter, more standard professional density.

## Font (add to `app/layout.tsx`)

```ts
import { Poppins } from "next/font/google";

const poppins = Poppins({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-sans",
});

// apply the variable class to <html>: `${poppins.variable}`
```

One family, three weights: Regular (400), Medium (500), SemiBold (600). No separate display or monospace font.

## Type hierarchy

Weight-based, not role-based — every style below is Poppins. `Data Large`/`Data Base` replace the old "numeric data is always mono" rule: they render in Poppins too, distinguished by weight/size and `font-variant-numeric: tabular-nums` (keeps figures aligned in a column without a monospace font).

| Style | Weight | Size / Line-height | Tailwind utility |
|---|---|---|---|
| H1 | SemiBold (600) | 40px / 48px | `text-h1` |
| H2 | SemiBold (600) | 28px / 36px | `text-h2` |
| H3 | Medium (500) | 20px / 28px | `text-h3` |
| Body | Regular (400) | 15px / 22px | `text-body` |
| Body Small | Regular (400) | 13px / 20px | `text-body-sm` |
| Label | Medium (500) | 12px / 16px | `text-label` |
| Data Large | SemiBold (600) | 18px / 24px | `text-data-lg` |
| Data Base | Medium (500) | 14px / 20px | `text-data-base` |

`text-h1`…`text-data-base` are custom Tailwind v4 utilities defined via `@utility` in `globals.css` — use them instead of composing raw `text-*`/`font-*`/`leading-*` classes, so the hierarchy stays centralized in one place.

### Where each style is used

- **H1** — marketing site hero heading. One per page, landing routes only.
- **H2** — marketing site section heading.
- **H3** — marketing site card/subsection heading, **and** app/dashboard page titles. Dashboard routes are dense (DexScreener-style, not a marketing page), so a full H1/H2 doesn't fit there — H3 is the largest heading size app routes use.
- **Body** — primary paragraph copy (marketing routes).
- **Body Small** — secondary/supporting copy: card body text, dashboard page subtitles, empty-state text, SHAP explanation copy.
- **Label** — short UI chrome: nav links, buttons, table column headers, badges/tags, small secondary metadata (shortened addresses in a de-emphasized column, footer, sentiment tags).
- **Data Large** — a standalone, emphasized numeric value with room to breathe (e.g. the risk score in the asset-detail page's stat block). Not for inline table cells — 18px is too tall for a dense row.
- **Data Base** — all other numeric/tabular values: table cells (scores inline in a table, wallet counts, timestamps, percentages), pair symbols, shortened wallet addresses used as a primary column value, feature/statistic values.

## CSS variables and type utilities (`app/globals.css`)

```css
@import "tailwindcss";

@theme {
  --color-bg: #0B0C10;
  --color-surface: #14161B;
  --color-border: #24262C;
  --color-text: #EDEEF0;
  --color-muted: #8A8F98;

  --color-accent: #5B6EF5;      /* brand/interactive only */
  --color-flag: #E8A33D;        /* risk/wash-trading alerts only */
  --color-up: #22C55E;          /* price/data increase only */
  --color-down: #EF4444;        /* price/data decrease only */

  --font-sans: var(--font-sans), sans-serif;
}

@utility text-h1 { font-family: var(--font-sans); font-weight: 600; font-size: 40px; line-height: 48px; }
@utility text-h2 { font-family: var(--font-sans); font-weight: 600; font-size: 28px; line-height: 36px; }
@utility text-h3 { font-family: var(--font-sans); font-weight: 500; font-size: 20px; line-height: 28px; }
@utility text-body { font-family: var(--font-sans); font-weight: 400; font-size: 15px; line-height: 22px; }
@utility text-body-sm { font-family: var(--font-sans); font-weight: 400; font-size: 13px; line-height: 20px; }
@utility text-label { font-family: var(--font-sans); font-weight: 500; font-size: 12px; line-height: 16px; }
@utility text-data-lg { font-family: var(--font-sans); font-weight: 600; font-size: 18px; line-height: 24px; font-variant-numeric: tabular-nums; }
@utility text-data-base { font-family: var(--font-sans); font-weight: 500; font-size: 14px; line-height: 20px; font-variant-numeric: tabular-nums; }

body {
  background: var(--color-bg);
  color: var(--color-text);
  font-family: var(--font-sans);
}
```

No separate `tailwind.config.ts` — Tailwind v4 generates utilities directly from `@theme` (`--color-x` → `bg-x`/`text-x`/`border-x`), and the type-scale utilities above are declared explicitly with `@utility` since they're a fixed set of compositions, not a generated scale.

## Spacing

Tightened from the original Wegonorth-inspired generous negative space to a standard, professional density. Concretely:

- **Section padding (marketing routes):** `py-14 md:py-20` — not the original `py-24`–`py-40`. Keep it consistent across sections rather than varying padding per section for emphasis.
- **Grid/stack gaps:** `gap-8`–`gap-12` for multi-column section content, `mt-4`–`mt-8` between a heading and what follows it, not `mt-16`+.
- **Line-heights:** set by the type-scale utilities above (already tighter than the old defaults — e.g. Body is 15px/22px, roughly 1.47, not the old `text-lg`/default-leading combination).
- **App/dashboard routes:** were already dense; keep `main` padding around `px-6 py-6`–`py-8`, table row padding around `py-2`–`py-2.5`. Don't loosen these to match the (now-tighter) marketing routes — dashboard density should stay at or below marketing density.

Visual hierarchy still comes from the type scale (size/weight) and color, not from oversized whitespace — a heading should read as more important because it's bigger/bolder, not because it's floating in a large empty margin.

## Usage rules (for Claude Code / whoever builds components)

1. **Color discipline is the whole system.** `accent` = interactive/brand only. `flag` = wash-trading/risk alerts only. `up`/`down` = price or score movement only. Never substitute one for another even if it "looks fine" in a given spot — the color coding is how a user reads risk vs. price vs. navigation at a glance in a dense data product.
2. **Typography is the `text-h1`…`text-data-base` scale, not raw `text-*`/`font-*` composition.** See "Where each style is used" above. Numeric/tabular data uses `text-data-lg`/`text-data-base` (tabular figures via `font-variant-numeric`, not a monospace font); everything else uses the heading/body/label styles.
3. **Landing page (marketing routes):** one deliberate animated moment on load (not per-section fade-ins), bracketed nav labels used only in the nav — not stamped on every UI label. Standard section padding density (see Spacing above), not exaggerated negative space.
4. **App/dashboard routes:** dense data tables, dark surfaces, minimal decoration — DexScreener-style information density, not CoinGecko's card-heavy layout.
5. Avoid: gradient-card kits, ALL-CAPS eyebrow labels above every heading, arrow (→) suffixes on buttons, identical rounded cards with the same soft shadow everywhere.

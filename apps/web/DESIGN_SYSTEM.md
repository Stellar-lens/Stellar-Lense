# Design System

The dashboard's design system is just `dashboard/styles.css`'s `:root` custom properties
plus a documented set of component classes — no separate token-build step, no CSS-in-JS,
no component library. That's deliberate; see [ARCHITECTURE.md](ARCHITECTURE.md) for why
this repo avoids a build step in general.

**[dashboard/styleguide.html](dashboard/styleguide.html)** renders every token and
component listed below using the real stylesheet. Open it locally
(`npm run serve`, then visit `/styleguide.html`) before trusting anything in this
document — the styleguide is the source of truth if the two ever disagree.

## Tokens

All defined in `:root`, overridden per-theme in `:root[data-theme="light"]` where noted.
Dark is the default (no `data-theme` attribute); see [Theming](#theming).

### Color

| Token                                    | Role                                                                                                                                                           | Themed?                              |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| `--bg`                                   | Page background                                                                                                                                                | yes                                  |
| `--surface`                              | Card/panel background, one step up from `--bg`                                                                                                                 | yes                                  |
| `--border`                               | Hairline borders                                                                                                                                               | yes                                  |
| `--text`                                 | Primary text                                                                                                                                                   | yes                                  |
| `--text-muted`                           | Secondary text, labels, meta                                                                                                                                   | yes                                  |
| `--accent` / `--accent-dark`             | Brand blue; `-dark` is the resting state of filled buttons, `--accent` is their hover/link color                                                               | yes                                  |
| `--green` / `--yellow` / `--red`         | Base risk palette                                                                                                                                              | yes                                  |
| `--low` / `--medium` / `--high`          | Risk-level **text/border** color, aliased to `--green`/`--yellow`/`--red` — exists so `var(--${scoreClass(score)})` in `render.js` has something to resolve to | derived, no separate override needed |
| `--low-bg` / `--medium-bg` / `--high-bg` | Risk-level **background** tint, used by `.score-pill`                                                                                                          | yes                                  |
| `--on-accent`                            | Text color that sits on a filled `--accent`/`--accent-dark` button                                                                                             | no — always white in both themes     |

The `--low`/`--medium`/`--high` split from `--green`/`--yellow`/`--red` is intentional:
the base names describe a _hue_, the risk names describe a _meaning_. Code that's
choosing a color because something is low/medium/high risk should reference the risk
token, not the hue — that's the one indirection that made the
[`--low` token bug](CHANGELOG.md) possible to catch mechanically (see
`tests/design-tokens.test.js`) instead of only by eyeballing it.

### Spacing

`--space-1` (4px) through `--space-7` (32px), each step exactly double-ish the visual
weight of the last (4, 8, 12, 16, 20, 24, 32). Not every padding/margin in the stylesheet
uses one of these — a handful of values (the gauge's 10px border, `.asset-card`'s 14px
padding) never matched a scale step and were left as literals rather than nudged to fit.
If you're adding new spacing and it doesn't hit a step, that's fine; don't invent an
8th token for one usage.

### Type

`--text-2xs` (11px) through `--text-3xl` (32px). Body text is `--text-base` (14px);
most interactive elements (inputs, buttons, table cells) are `--text-sm` (13px).

### Radii, motion, z-index

- `--radius-sm` (6px) — small buttons (refresh, theme toggle)
- `--radius` (8px) — cards, inputs, the default
- `--radius-pill` (12px) — badges, score pills
- `--transition-fast` (0.15s) — hover states, theme-switch color transitions
- `--transition-slow` (0.3s) — the score gauge's border-color animation on lookup
- `--z-header` (10) / `--z-skip-link` (100) — the only two stacking contexts in the page

## Components

| Class                                        | What it is                                           | States                                                |
| -------------------------------------------- | ---------------------------------------------------- | ----------------------------------------------------- |
| `.card`                                      | Generic bordered panel, used for every major section | —                                                     |
| `.stat` / `.stat .value` / `.stat .label`    | Stats-row tile                                       | `.skeleton` on `.value` while loading                 |
| `.search-row button`                         | Primary filled button (Score lookup)                 | `:hover`                                              |
| `.refresh-btn`, `.theme-toggle`, `.copy-btn` | Small outline/icon buttons                           | `:hover`                                              |
| `.badge` + `.benford` / `.ml` / `.clean`     | Outline pill, score-lookup flag row                  | —                                                     |
| `.score-pill` + `.low` / `.medium` / `.high` | Filled pill, alerts table score column               | —                                                     |
| `.gauge` + `.low` / `.medium` / `.high`      | Score lookup's circular gauge                        | border color animates on new result                   |
| `.status-dot`                                | Header API-health indicator                          | `.offline`                                            |
| `.search-row input`, `.filter-input`         | Text inputs                                          | `:focus`                                              |
| `.alerts-table th.sortable`                  | Clickable/keyboard-operable sort header              | `:hover`, `.sort-asc`, `.sort-desc`, `:focus-visible` |
| `.asset-card`                                | Asset-ranking grid tile                              | —                                                     |
| `.empty-state`                               | "No data" / error message inside a table or grid     | —                                                     |
| `.skeleton`                                  | Shimmering loading placeholder                       | —                                                     |
| `.skip-link`                                 | Visually-hidden-until-focused a11y skip link         | `:focus`                                              |

Every one of these is rendered in [dashboard/styleguide.html](dashboard/styleguide.html).

## Theming

Dark is the implicit default (no attribute needed). `document.documentElement.dataset.theme`
is set to `"light"` or `"dark"` by `dashboard/js/app.js`'s `initTheme()`/`toggleTheme()`
(persisted to `localStorage`, falling back to `prefers-color-scheme` on first visit), and
`styles.css`'s `:root[data-theme="light"]` block overrides the color tokens. Only color
tokens are themed — spacing/type/radii/motion/z-index are identical in both themes.

**Adding a new themed color**: define it in both `:root` and `:root[data-theme="light"]`.
If it's derived from an existing themed token (like `--low`/`--medium`/`--high` are from
`--green`/`--yellow`/`--red`), define it once in `:root` as `var(--other-token)` and skip
the light-theme override — it'll follow automatically.

## Contributing a new component

1. Build it with existing tokens. If a spacing/type/radius value you need doesn't exist,
   check whether it should — most new UI should fit the existing scales.
2. Add it to [dashboard/styleguide.html](dashboard/styleguide.html) so it's visible
   without running the full dashboard against a live API.
3. Add a row to the component table above.
4. If you reference a CSS custom property _dynamically_ from JS (string-built, like
   `render.js`'s `var(--${scoreClass(score)})`), add a case to
   `tests/design-tokens.test.js` — that's the only thing that catches a token/JS-string
   mismatch before it ships, since neither ESLint nor Stylelint can see across the
   JS/CSS boundary.

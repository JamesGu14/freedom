# Freedom Quant — Design System

## Color Tokens

| Token | Value | Usage |
|-------|-------|-------|
| `--bg` | `#f5f6f8` | Page background |
| `--bg-subtle` | `#eef0f4` | Subtle backgrounds (badges, tags) |
| `--ink` | `#111827` | Primary text |
| `--muted` | `#6b7280` | Secondary text, labels |
| `--accent` | `#3b82f6` | Primary actions, active states |
| `--accent-dark` | `#1d4ed8` | Active text on accent backgrounds |
| `--accent-hover` | `#2563eb` | Button hover |
| `--accent-subtle` | `rgba(59,130,246,0.08)` | Light accent backgrounds |
| `--panel` | `#ffffff` | Card/panel backgrounds |
| `--border` | `#e5e7eb` | Standard borders |
| `--border-light` | `#f3f4f6` | Subtle dividers |
| `--success` | `#16a34a` | Positive states |
| `--error` | `#dc2626` | Error states |

**Stock colors** (Chinese convention: red=up, green=down):
- Up: `rgba(239,68,68,0.1)` bg / `#b91c1c` text
- Down: `rgba(34,197,94,0.1)` bg / `#15803d` text
- Flat: `rgba(100,116,139,0.1)` bg / `#475569` text

## Typography

| Role | Font | Size | Weight |
|------|------|------|--------|
| Body | Figtree + Noto Sans SC | 13px | 500 |
| Headings (h1) | Figtree | 20px | 700 |
| Labels/Eyebrow | Figtree | 11px | 600, uppercase |
| Monospace/Codes | JetBrains Mono | 12px | 600 |
| Small text | Figtree | 11-12px | 500-600 |

All numeric data uses `font-variant-numeric: tabular-nums` for alignment.

## Spacing Scale

Compact density. Common values:
- **4px** — minimal gaps (badge padding, tiny spacing)
- **6-8px** — tight gaps (between nav items, table cell padding)
- **10-12px** — standard gaps (card padding, filter gaps, grid gaps)
- **14-16px** — section spacing (panel padding, page padding, margin-bottom between sections)
- **20px** — page horizontal padding

## Border Radius

| Token | Value | Usage |
|-------|-------|-------|
| `--radius-sm` | `4px` | Badges, pills, small elements |
| `--radius` | `6px` | Buttons, inputs, sidebar items |
| `--radius-md` | `8px` | Cards, panels, tables |
| `--radius-lg` | `10px` | Modals, auth card |

## Component Rules

### Tables
- Header: `11px` uppercase, `var(--bg)` background, sticky
- Cell padding: `8px 12px` (default), `6px 8px` (compact), `5px 6px` (backtests)
- First column: monospace font
- Hover: `var(--accent-subtle)` background
- Border: `var(--border-light)` between rows

### Cards/Panels
- Border: `1px solid var(--border)`
- Padding: `14px 16px` (standard), `10px 12px` (compact)
- No box-shadow by default; `var(--shadow)` on hover

### Buttons
- Primary: solid `var(--accent)`, white text, `8px 16px` padding
- Link button: outlined, `4px 10px` padding
- Danger: red tint background, red text

### KPI Tiles
- Use `.kpi-row` grid + `.kpi-tile` cards
- Label: `11px` uppercase muted
- Value: `18px` bold, tabular-nums

### Page Headers
- Slim inline bar with bottom border (no card/panel)
- h1 + subtitle left, action buttons right

### Sidebar
- Width: `220px` expanded, `56px` collapsed
- Items: `7px 10px` padding, `13px` font, icon + label
- Active: blue subtle background + blue text
- Footer: collapse toggle + logout

## Density Tuning

To make the UI **more dense**, reduce these values in `:root`:
```css
/* Tighter table cells */
th, td { padding: 6px 10px; }

/* Tighter cards */
.panel { padding: 10px 12px; }

/* Tighter page */
.page { padding: 12px 16px; }

/* Tighter filters */
.filters { padding: 10px 12px; gap: 8px; }
```

To make it **less dense**, increase those same values proportionally.

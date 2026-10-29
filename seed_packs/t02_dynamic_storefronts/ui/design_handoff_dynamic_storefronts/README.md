# Handoff: Dynamic Storefronts Dashboard

## Overview
An internal dashboard for AtelierNova Home & Lifestyle's merchandising team. It identifies low-converting SKU × audience-segment pairs, queues them for AI-generated storefront variants, tracks generation and human review, lists published variants with before/after metrics, and charts cumulative impact.

Five tabs: **Overview**, **Queue**, **Work in progress**, **Published**, **Results**.

## About the design files
`prototype/Dynamic Storefronts.dc.html` is a **design reference built in HTML**: a working prototype that shows the intended look and behavior. It is not production code. Recreate it in the target codebase with its own framework and patterns. If there is no codebase yet, a reasonable stack is React + TypeScript + Vite, with the tokens from `design-system/styles.css` as CSS variables and a light chart lib (Recharts / visx) or plain SVG.

To view the prototype, serve the `prototype/` folder over HTTP (e.g. `npx serve prototype`) and open `Dynamic Storefronts.dc.html`. Opening it as `file://` may block script loading.

The template markup is between `<x-dc>` and `</x-dc>`. `{{ name }}` holes are filled from `renderVals()` in the `<script data-dc-script>` class at the bottom. `<sc-for>` is a loop and `<sc-if>` a conditional. That class also holds all data generation and derived-metric logic. Port this logic to the backend or services.

## Fidelity
**High fidelity.** Colors, type, spacing, component styling and interactions are final. Match them using the Nocturne tokens below. The data is synthetic (seeded RNG) and stands in for the BigQuery `ecommerce` dataset.

## Data model and metric definitions
Sample data: `data/` (CSV + JSON, see `data/README.md`). The production equivalents are `products`, `audience_segments`, `experiments`, and generated variant/publish tables.

- **Experiment**: one SKU × segment baseline row: views, purchases, bounce_rate, revenue, margin, layout.
- **CR** = purchases / views. **Average CR** = Σpurchases / Σviews (traffic-weighted). **Max CR** = max experiment CR.
- **Avg bounce rate** = Σ(bounce × views) / Σviews.
- **Low-performance opportunity**: an experiment with CR < average CR.
- **Score** = views × unit margin (price × margin %) × bounce rate. **Rating** = score / max score × 100, rounded. The queue is sorted by score, descending.
- **Potential additional revenue** = Σ over opportunities of (avgCR × views − purchases) × price. **Potential additional margin** = the same × margin %.
- **Revenue per visit** = CR × price. **Margin per visit** = CR × price × margin %.
- **Results series** (daily, 21 days): site-wide CR, BR, RPV and MPV recomputed with the uplift of each published variant applied from its publish date onward.

Formats: EUR. Compact notation on KPI tiles (€7.9M). Two decimals per visit (€1.23). Rates as % with 2 decimals (CR) or 1 decimal (BR). en-GB grouping.

## Opportunity lifecycle (state machine)
```
pending_approval --approve / auto-approve--> generating (In progress)
generating --generation done--> review (Pending review)
review --Open storefront (sets opened=true)--> review
review [opened] --Approve--> published
```
- **Auto-approve switch** (header, global): when on, approves the next pending item in score order, one per tick (1s in the prototype). In production this is a persisted setting, and the backend should do the auto-approving.
- **Approve all pending** (Queue): moves every pending item to generating.
- In Work in progress, **Approve** is disabled until the storefront has been opened at least once.
- Generation time is simulated (default 8s, progress bar + step label: Selecting SKUs → Queuing hero render → Composing layout → Drafting promo banner). In production, poll or subscribe to job status.
- Published items leave the Queue, except ones published in the current session, which stay visible with a Published tag.

## Screens

Global shell
- Page background: `--color-bg` #161826, with a radial glow `radial-gradient(1200px 500px at 0% 0%, --color-accent-900 #2b2741, transparent 70%)`.
- Content max-width 1280px, centered. Horizontal padding 22.4px (`--space-8`).
- Header: a flex row (wraps). Left: kicker "AtelierNova Home & Lifestyle" (10px, uppercase, 0.1em tracking, `--color-accent` #9184d9) over the title "Dynamic Storefronts" (20px / 500). Right: the auto-approve switch, an outlined pill-ish button (1px `--color-divider`, radius 8, padding 6×12, 13px). The track is 30×16, radius 8: `--color-neutral-700` off, `--color-accent-600` on. The knob is 12px `--color-neutral-100` and slides from left 2px to 16px over 0.2s. Use `role="switch"` and `aria-checked`.
- Tabs: the `.nav` row with a 22.4px gap. Each tab is a label plus a muted count (11px, `--color-neutral-500`). The active tab has `aria-current="page"`, accent text and a 1px accent bottom border. Counts: Queue = pending, WIP = generating + review (hidden if 0), Published = total.
- Font: Inter 400/500 throughout, base 14px. Headings never exceed weight 500.

### 1. Overview
- H1 (30px / 500, line-height 1.15): "One layout for every shopper is costing conversion." Subline (14px, `--color-neutral-400`): "Baseline across 120 storefront experiments. Low-performance opportunities are SKU × segment pairs converting below the average rate."
- Section label "Catalog & performance" (11px uppercase, 0.08em, `--color-neutral-500`).
- KPI grid: `repeat(auto-fill, minmax(190px,1fr))`, gap 11.2px. `.card` tiles with padding 16.8px: label 12px `--color-neutral-400`, value 26px / 500 tabular-nums. Order: Products, Audience segments, Average conversion rate, Max conversion rate, Average bounce rate, Total views, Sales, Margin.
- Section label "Opportunity" in accent. The band uses a `linear-gradient(135deg, --color-section #262a60, --color-accent-900)`, radius 14, padding 22.4, and an inset 1px `--color-section-ghost` #4c5397 ring. It holds 3 columns (`auto-fit minmax(240px,1fr)`): label 12px `--color-accent-200`, value 40px / 500, note 12px `--color-neutral-300`.
  - Low-performance opportunities: "SKU × segment pairs below X% CR"
  - Potential additional revenue: "If each pair converts at the average rate"
  - Potential additional margin: "Revenue uplift × SKU gross margin"
- CTA `.btn.btn-primary` "Review opportunity queue" opens the Queue tab.

### 2. Queue
- Header row: H2 "Top opportunities" (22px / 500), with the sub "Sorted by rating = views × unit margin × bounce rate (indexed, top = 100)". On the right: "N pending approval" and a `.btn-secondary` "Approve all pending" (disabled when 0).
- `.table`, min-width 1060px, horizontal scroll on narrow screens. Columns: # · SKU (12px muted) · Product · Segment (13px `--color-neutral-300`) · Views · Purchases · Revenue · CR · Bounce · Rating · Status · action. Numbers are right-aligned and tabular.
- Rating cell: a 48×4 bar (track `--color-neutral-800`, fill accent at rating%) followed by the number.
- Status tags: Pending approval `.tag-neutral` · Generating `.tag-accent` · Pending review `.tag-outline` · Published `.tag-accent-2`.
- Action: `.btn-primary`, compact (4×12 padding, 13px) "Approve". Disabled (45% opacity) when not pending.

### 3. Work in progress
- H2 "Work in progress", with the sub "Approved opportunities. Open a finished storefront to review it, then approve to publish."
- Empty state: a `.card` (padding 22.4) with the text "Nothing in progress. Approve opportunities in the queue to start generating storefront variants." and a `.btn-secondary` "Go to queue".
- Table columns: SKU · Product · Segment · Layout · Status · actions.
  - Status "In progress" (`.tag-accent`) also shows a 110×4 progress bar (width transitions 0.9s linear) and an 11px step label. "Pending review" uses `.tag-outline`.
  - Actions: `.btn-secondary` "Open storefront" (enabled in review) and `.btn-primary` "Approve" (enabled in review and once opened).
- **Storefront preview modal**: fixed overlay, background `color-mix(--color-bg 78%, transparent)`, click outside to close. The panel is min(860px,100%) wide, max-height 92vh, scrolls, background `--color-surface` #232532, radius 14, `--shadow-lg`.
  - Header: kicker "Storefront variant · {layout}" with the segment label (15px / 500) under it. On the right, `.btn-ghost` "Close" and `.btn-primary` "Approve & publish".
  - Mock storefront (an inner frame on `--color-bg`, radius 8, `--shadow-sm`):
    - Mini nav: brand, category, "New in", "Bag (0)".
    - Promo strip (12px, `--color-accent-900` bg, `--color-accent-200` text): "{disc}% off {category} this week · code {CITY3}{disc}".
    - Two-column hero: an image slot left (min-height 260; the real generated lifestyle image goes here). On the right: theme kicker, headline 26px / 500, sub 13px, CTA "Shop {name} · {price}".
    - Related grid: 4 same-theme in-stock products, 4:3 image slots.
  - Footer meta (12px muted): SKU, Margin, Stock, "Discount X% · within 30% cap and SKU margin".
  - Discount rule: max(5, min(cap, floor(margin% × 0.4 / 5) × 5)). Default cap 30%.
  - Headline copy is picked by persona. See `headline` in the prototype logic.

### 4. Published
- H2 "Published storefronts", with the sub "N storefront variants live · estimated added revenue €X over the baseline window".
- Two-row header. The group row is blank × 4, then "Previous" (muted, centered, colspan 4) and "New" (accent, centered, colspan 4). The second row: Published · SKU · Product · Segment · Rev / visit · Margin / visit · CR · BR · Rev / visit · Margin / visit · CR · BR.
- Previous values in `--color-neutral-400`. New Rev/Margin in the default text color. New CR/BR in `--color-accent-300`. Sorted by publish date, newest first. Min-width 1120px.

### 5. Results
- H2 "Cumulative results", with the sub "{start} – {end} 2026 · site-wide rates across all experiment traffic".
- Grid `repeat(auto-fill, minmax(min(100%,380px),1fr))`, gap 11.2. Each chart is a `.card`, padding 16.8.
- Card header: title 13px `--color-neutral-300` on the left. Right: the delta 12px `--color-accent-300` ("+X since {start}"), then the current value 22px / 500.
- Charts, in order:
  1. Storefronts published daily: a bar chart, 140px tall. Bars use `--color-accent-700`, today's bar is `--color-accent`, radius 2 on top, gap 3px. The baseline rule fades at both ends.
  2. Storefront variants published (cumulative): line chart.
  3. Conversion rate: line chart.
  4. Bounce rate: line chart.
  5. Revenue per visit: line chart.
  6. Margin per visit: line chart.
- Line charts: 140px tall, 1.5px accent stroke, area fill `--color-accent-900` at 0.8 opacity. Min and max labels sit at the top-left and bottom-left (10px `--color-neutral-500`). X labels show the first, middle and last dates (10px muted).

## Interactions and states
- Hover/pressed/focus come from the Nocturne classes. `.btn-primary` is an accent outline with a 12% accent tint on hover and 22% when pressed. Table rows get a 4% text tint on hover. Focus is `:focus-visible` with a 2px accent outline and 2px offset. Disabled is 45% opacity with the not-allowed cursor.
- Table and row rules are gradients that fade to transparent over 48px at each end. Don't use solid borders.
- Responsive: KPI grids and chart grids reflow. Tables scroll horizontally. The header wraps.
- Loading states to add in production: skeleton tiles and rows while metrics load, plus an error state per tab.

## State (suggested)
- `tab`: 'home' | 'queue' | 'wip' | 'pub' | 'res'. Consider routing (`/`, `/queue`, `/wip`, `/published`, `/results`).
- `autoApprove: boolean`: server-persisted.
- `opportunities[]`, with `status`, `progress`, `opened`, `publishedAt`. Comes from the API. Poll or push for generation progress.
- `previewId`: the open modal.
- Configurable (prototype tweaks): `generationSeconds` (8), `discountCap` (30%), `autoApproveDefault` (false).

## Design tokens (Nocturne)
Full sheet: `design-system/styles.css`. Guide: `design-system/nocturne-guide.md`.
- bg #161826 · surface #232532 · text #e9e9ed · accent #9184d9 · divider = text at 16% alpha.
- Neutral ramp, 100→900: #f3f5fe #e4e7f5 #cfd3e5 #b2b6ca #9397ab #75798c #595d6c #3f424d #292b31.
- Accent ramp, 100→900: #f5f4ff #e7e5fe #d2cefd #b5abfc #968ae0 #796cbf #5d5294 #423a6a #2b2741.
- Section: #262a60 · glow #353b80 · ghost #4c5397.
- Spacing: 2.8 / 5.6 / 8.4 / 11.2 / 16.8 / 22.4 px (`--space-1,2,3,4,6,8`).
- Radius: 4 / 8 / 14.
- Shadows: sm `0 0 0 1px #3f424d` · md `0 0 0 1px #595d6c, 0 6px 18px rgba(0,0,0,.55)` · lg `0 0 0 1px #9397ab, 0 16px 40px rgba(0,0,0,.65)`.
- Type: Inter 400/500. Sizes used: 10, 11, 12, 13, 14, 15, 20, 22, 26, 30, 40 px. Use tabular-nums for every number.
- Icons: Phosphor (none are used yet).
- Don't use pure black or white, don't flood large areas with the accent (except the section-colored Opportunity band), and keep heading weight at 500 or less.

## Assets
There are no images. The storefront hero and product thumbnails are gradient placeholders where generated or catalog imagery goes. The font is Inter (Google Fonts).

## Files
- `prototype/Dynamic Storefronts.dc.html`: the full prototype (markup + logic).
- `prototype/support.js`, `prototype/_ds/…`: the runtime and design system the prototype needs.
- `design-system/`: the Nocturne token sheet and guide.
- `data/`: the synthetic dataset matching the prototype's initial state.

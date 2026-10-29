# T02 UI Redesign — apply taste-skill design rules

## Objective
Apply the design-taste methodology from https://github.com/Leonxlnx/taste-skill (house rules + app-screen craft guidance) to the T02 Nocturne UI, which currently reads as generic/AI-default. Keep existing stack and content — this is a visual redesign, not a rebuild.

## Problem
User: "usa esta Skill ... para mejorar la UI porque es muy fea y crea una PR". Taste-skill is not installed as a Claude Code skill in this environment and its tool-chain (draw.mjs/lint.mjs/inspect.mjs) needs network image search we don't reliably have here. Approach: apply its house rules + craft guidance by hand, verify visually with T3's browser preview tools (functional substitute for inspect.mjs's 3-width gate), keep existing hero-image generation pipeline instead of sourcing new stock photos.

## Scope (3 real surfaces found)
1. `ui/src/styles/nocturne.css` — token sheet + component classes, external stylesheet.
2. `ui/src/App.tsx` — app chrome: tabs, nav, header.
3. `ui/src/components/StorefrontPreviewModal.tsx` — richest visual surface (hero/promo/grid/cards), most likely source of "ugly".
4. `seed_packs/t02_dynamic_storefronts/ui/template.html` — MCP App-UI card, shares the same Nocturne CSS vars inline; sync tokens for consistency (low effort, same source of truth).
Out of scope: `ui/design_handoff_dynamic_storefronts/` (frozen input spec, not to be edited).

## Design rules to apply (from taste-skill SKILL.md)
**Banned:** eyebrow labels/pill badges above headings, monospace outside code/index/hairlines, gradients, resting-element shadows, glass effects, emoji, decorative blobs, icon-topped card grids, styled accent words in headlines, >2 typefaces.
**Required craft:** large display type with strong size contrast; sections 120–240px apart, no blank stretch > ~half a screen; one ground colour, one ink, one accent; flat buttons; simple nav.
**App-screen specific:** quiet panels, aligned figures/numbers, colour reserved for data (not chrome), nav folds away on phones.
**Motion:** transform/opacity only, respect `prefers-reduced-motion`.

## Authorized scope
Edit the 4 files above. Do not touch `design_handoff_dynamic_storefronts/`, Python generator logic (`mcp_server.py`), or copy/content — visual/CSS/markup only.

## Tasks
- [ ] T1 — Delegate one writer: rewrite `nocturne.css` tokens/components per rules above (single accent, no gradients/shadows/pills, strong type scale, 120–240px section rhythm).
- [ ] T2 — Same writer: restyle `App.tsx` chrome (nav/tabs/header) — quiet panel, folds on mobile, colour reserved for KPI data.
- [ ] T3 — Same writer: restyle `StorefrontPreviewModal.tsx` (hero/promo/grid/cards) — flat buttons, no icon-card-grid, aligned product-card figures.
- [ ] T4 — Same writer: sync `template.html`'s inline `<style>` tokens to match.
- [ ] T5 — `npm run build` in `ui/` — must compile clean (dist/ feeds Cloud Run container).
- [ ] T6 — Visual verification at 1440/768/390px via T3 preview tools (parent, not delegated) — screenshot each, confirm no FAIL-equivalent (broken layout, overlap, unreadable contrast).
- [ ] T7 — Work-unit commit (conventional commit) + push + PR + `link_pull_request`.

## Route
Delegated direct — writer trigger (3 non-trivial files). TDD: not applicable (CSS/visual, no behavior tests exist for styling; functional check = build + visual snapshot, not unit tests).

## Status
In progress — task file created, about to delegate T1–T4 writer.

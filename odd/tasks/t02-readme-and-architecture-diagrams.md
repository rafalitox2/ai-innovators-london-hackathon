# T02-only README + GCP infra & A2A diagrams

## Objective
Rewrite README.md to document ONLY Table T02 (strip generic multi-table Starter content), link every real T02 doc, and add two new architecture diagrams: Google Cloud infrastructure, and the A2A integration with Table 1.

## Scope
1. `README.md` — full rewrite, T02-only.
2. `docs/diagrams/t02_gcp_infrastructure.svg` — new, GCP services + connections.
3. `docs/diagrams/t02_a2a_integration.svg` — new, T02↔T01 A2A handshake (current in-process state + in-progress live endpoint from sibling branch `feat/a2a-live-endpoint`, presented honestly as not-yet-merged).

## Authorized scope
Do not touch `seed_packs/README.md` (validated by `seed_packs/check_packs.py::_check_readme` — confirmed it checks that file, not root README.md). Do not touch `docs/PREWORK.md`, `docs/STARTER.md`, `challenges/README.md`, `seed_packs/t00_example/`, `seed_packs/t01_campaign_orchestrator/` — these stay generic/untouched (sibling-table content).

## Tasks
- [x] T1 — Delegate exploration: inventory all T02 docs, GCP services used (file:line), real A2A integration state (incl. checking sibling worktree `feat/a2a-live-endpoint`).
- [x] T2 — Rewrite README.md (inline, 1 file, fully understood after T1): quickstart, tool catalog, 3 architecture diagrams embedded, A2A section, live deployment table (kept from old §6), documentation index (new), repo layout (T02-scoped), troubleshooting (kept + 1 new CI auth row), reference docs. Verified `check_packs.py`'s README check targets `seed_packs/README.md` not root — no conflict. Full pytest suite green (91 passed, same 1 pre-existing unrelated flake).
- [x] T3 — Delegate writer: build `docs/diagrams/t02_gcp_infrastructure.svg` (new). Writer flagged 1 real inconsistency vs. the brief (root `cloudbuild.yaml` is NOT called by `ci.yml` — drawn as a disconnected, dashed "standalone" box instead of forcing a false connection).
- [x] T4 — Same writer: build `docs/diagrams/t02_a2a_integration.svg` (new). Two-state diagram (merged vs. in-progress `feat/a2a-live-endpoint`). Writer flagged a real bug on the unmerged branch: its agent card advertises `a2a_sync_endpoint: {base}/api/a2a/sync` but no such route is mounted — drawn as its own callout box.
- [x] T5 — Visual verification of both new SVGs via `html_preview` (embedded inline, since raw-SVG image documents time out `preview_snapshot`). Both render clean: no overlap, no text clipping. Tightened `t02_a2a_integration.svg`'s viewBox from 1000→580 height (content ended at ~480, rest was dead space).
- [ ] T6 — Commit (conventional commit) + push + PR + `link_pull_request`.

## Route
Delegated direct — mapping trigger (exploration, T1) + writer trigger (2 new SVGs, T3/T4, one bounded writer). README (T2) done inline — 1 file, fully understood, no further research needed. Full pytest suite re-verified green (91 passed, same 1 pre-existing unrelated flake) after both diagram edits.

## Status
Diagrams + README done and visually verified. Ready for T6 (commit/push/PR).

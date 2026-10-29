---
name: t02-worktree-collab
description: This skill should be used when multiple team members or Antigravity subagents collaborate in parallel using git worktrees (make worktree, make worktree-link, make verify), execute Spec/Eval-first TDD (RED to GREEN), or open evidence-based Pull Requests using .github/pull_request_template.md.
---

# Table 2 (`t02_dynamic_storefronts`) — Multi-Person & Multi-Agent Worktree Collaboration Skill

## Purpose

Enable all 5 Table 2 members (`@rafalitox2`, `@BorjaIP`, `@carlosescribano-ai`, `@jportell`, `@joshsmith-samy`) and concurrent Antigravity agents/subagents to develop, test, and open Pull Requests in parallel without file collisions, `.venv` duplication, `.state.json` race conditions, or branch-merge races.

---

## 1. Automated Worktree Setup & Zero-Config `.venv` / `.env` Sharing

The repository `Makefile` automatically resolves `MAIN_WORKTREE` via `git worktree list --porcelain`. Every secondary `git worktree` automatically inherits `$(MAIN_WORKTREE)/.venv/bin/python` and `$(MAIN_WORKTREE)/.env` even before `make worktree-link` is run.

### Creating a New Isolated Worktree (1 Command)
```bash
# Fetches origin/main, creates ../wt-<slug> on branch feat/<slug>, and links .venv + .env:
make worktree BRANCH=feat/my-task

# Optional custom directory:
make worktree BRANCH=fix/margin-check DIR=../wt-margin-check
```

### Linking `.venv` & `.env` Inside an Existing Worktree
If a worktree was created manually via `git worktree add ../wt-custom -b feat/custom`, link `.venv` and `.env` for IDE/Pyright discovery:
```bash
cd ../wt-custom
make worktree-link
```
*(Note: `.gitignore` includes both `.venv/` and `.venv`, so symlinked virtualenvs in worktrees never appear as untracked files in `git status`.)*

### Listing Active Parallel Worktrees
Before starting a task or spawning a subagent, inspect active worktrees across the workspace:
```bash
make worktree-list
```

---

## 2. Spec / Eval-First TDD Workflow (Plan → RED → GREEN → Verify)

To satisfy Pillar 2 of the **Agentic SDLC Practices (`+1 pt`)** bonus and `.agents/rules/pull-requests.md`:

1. **Plan & Issue Link**: Identify the GitHub Issue (`#1`..`#6`) and target contract in `docs/PHASE1_SPEC.md`, `docs/PHASE2_SPEC.md`, or `docs/PHASE3_SPEC.md`.
2. **RED Commit (Tests First)**:
   - Add failing unit tests in `tests/test_t02_*.py` and/or new golden evaluation scenarios in `seed_packs/t02_dynamic_storefronts/eval/golden.test.json`.
   - Run `make test` and record the exact `FAILED` / `ImportError` output.
   - Commit the failing test: `git commit -m "test(t02): add failing tests for <feature> (TDD Red, #<issue>)"`.
3. **GREEN Commit (Implementation)**:
   - Implement the tool, guardrail, or configuration change following `.agents/rules/t02-domain-invariants.md`.
   - Run the unified verification gate:
     ```bash
     make verify PACK=t02
     ```
   - Commit the implementation: `git commit -m "feat(t02): implement <feature> (TDD Green, closes #<issue>)"`.

---

## 3. Running `make verify` & Opening Evidence-Based Pull Requests

Every PR must use `.github/pull_request_template.md` and comply with `.agents/rules/pull-requests.md`:

1. **Run the 3-in-1 Offline Gate**:
   ```bash
   make verify PACK=t02
   ```
   This executes:
   - `pytest -q` (full offline unit suite across all packs)
   - `python -m eval.run_eval --pack t02 --validate-only` (ADK `EvalSet` schema validation)
   - `python -m seed_packs.check_packs` (all 10 seed packs contract validation)
2. **Paste Observed Output**: Copy the exact terminal output of `make verify PACK=t02` into the `## Evaluation` section of `.github/pull_request_template.md` (along with the `RED` run output when adding tools/guardrails).

---

## 4. Preventing Multi-Person / Multi-Agent Branch & Merge Race Conditions

When 5 humans and multiple Antigravity subagents push concurrently:
- **Never commit directly to `main`.**
- **Never push new commits to a branch whose PR has already been merged.** Once GitHub merges a PR (`MERGED`), further commits on that branch name will not reopen the merged PR. Always run `make worktree BRANCH=feat/<new-slug>` from the latest `origin/main` (lesson learned from PR `#10` → PR `#12`).
- **Rebase before merging**: Before clicking Merge on GitHub, run:
  ```bash
  git fetch origin main && git rebase origin/main && make verify PACK=t02
  ```
- **Per-Worktree Mock State Isolation**: `seed_packs/t02_dynamic_storefronts/.state.json` is relative to each worktree checkout and gitignored (`seed_packs/*/.state.json`), so running `make test` or `make dev` in one worktree never mutates another worktree's local state.

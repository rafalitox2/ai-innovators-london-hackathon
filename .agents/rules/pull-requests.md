# Rule: how this table opens Pull Requests

Applies to every change in this repository, human or agent authored.

## Non-negotiables

1. **Never commit to `main`.** One task, one branch (`feat/*`, `fix/*`, `ci/*`, `docs/*`), one Pull Request.
2. **Every PR uses `.github/pull_request_template.md`.** All sections stay, in order: What, How, Evaluation, Process, Risks & follow-ups, Checklist. An empty section is deleted only if it is genuinely not applicable, and the PR says why.
3. **The Evaluation section carries observed output, never a claim.** Paste the command and what it actually printed. A check that failed, was skipped, or could not run is reported as such. "Tests pass" without the output is not evidence.
4. **Link the issue.** `Closes: #N` so the board stays honest.
5. **No secrets in the diff.** `.env` stays gitignored. No credentials, no service-account JSON, no project-scoped tokens.
6. **Model configuration stays in environment variables.** No hardcoded Gemini model IDs, no `-latest` aliases — this is hackathon gate #4 and a failed PR review if broken.

## Evidence commands for this repo

| What it proves | Command | Needs GCP credentials |
| --- | --- | --- |
| Offline unit tests | `make test` | no |
| Golden eval schema | `make eval-validate PACK=t02` | no |
| Golden evals against Gemini | `make eval PACK=t02` | yes |
| Live agent on Agent Runtime | `make test-remote` | yes |

The first two run in GitHub Actions on every PR. The last two need credentials and run in Cloud Build, because `@gcplab.me` org policy blocks exporting service-account JSON keys.

## Spec / eval first

When a PR adds a tool, a guardrail or a prompt change, the test or the golden case lands **before** the implementation, and the PR shows the RED run as well as the GREEN one. This is pillar 2 of the Agentic SDLC bonus, and it is also how we avoid shipping a tool nobody can prove works.

## Parallel work

Use `git worktree add ../wt-<task> -b feat/<task>` when two people touch the repo at the same time, so concurrent agents do not collide on the same files.

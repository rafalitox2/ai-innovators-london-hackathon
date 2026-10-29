## What

<!-- One paragraph: what this PR changes, in plain language. -->

## How

<!-- The approach and why it was chosen. Name the alternative you rejected and why. -->

## Evaluation

<!-- Evidence, not claims. Paste the command you ran and the output you observed.
     If a check was skipped or failed, say so here — do not omit it. -->

| Check | Command | Observed result |
| --- | --- | --- |
| Unit tests | `make test` | |
| Golden evals (schema) | `make eval-validate PACK=t02` | |
| Golden evals (live) | `make eval PACK=t02` | |

## Process

- Closes: #
- Branch:
- Spec/eval first: <!-- did tests or golden cases land before the implementation? -->
- Model/env: <!-- confirm GEMINI_MODEL and GOOGLE_CLOUD_LOCATION still come from env, never hardcoded -->

## Risks & follow-ups

<!-- What this PR does not cover, what could break, what the next PR must pick up. -->

## Checklist

- [ ] One task, one branch, one PR — no unrelated changes
- [ ] `make test` green locally
- [ ] `make eval-validate PACK=t02` green locally
- [ ] No secrets, no `.env`, no credentials in the diff
- [ ] No hardcoded model IDs and no `-latest` aliases
- [ ] Linked to its issue

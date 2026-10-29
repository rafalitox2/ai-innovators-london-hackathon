# T02 self red team — issue #37
## Objective and authorization
Close the verified raw-text, quarantine and numeric bypasses in approved issue #37 through one PR, no merge. Work directly in this shared checkout on fix/t02-self-red-team-37, baseline 29daf608b3025ca77b6ae7ae9c7741101d1d108e. Preserve unrelated .codegraph/ and odd/tasks/t02-ui-taste-redesign.md.
GitHub existing credential read/push/PR/labels authorized; cloud evaluation, deployment and live integrations are not.
## Scope and acceptance
Raw textual arguments rejected before sanitation at all read/action entry points; normalized bounded marker detection. Catalog IDs and poisoned records quarantined in six actions, callback and CSV/BQ/KG reads. Discount/CPM accept finite non-bool values only within bounds; no truncation bypass, exception or rejected-call side effect. Legitimate controls remain functional. No claim of universal prompt-injection prevention.
## Plan and routing
- [x] T1: Normalize marker detection; reject raw textual inputs; read entry parity.
- [ ] T2: Quarantine six actions, callback and catalog/KG outputs.
- [ ] T3: Validate finite non-bool discount/CPM values.
Each task route: delegated bounded writer (this agent). Parent mapping trigger 4+ files completed; writer trigger 2+ non-trivial files satisfied by parent delegation. No further preparatory delegation.
TDD ON: issue #37 and .agents/rules/pull-requests.md. Python 3.12 runner: .venv/bin/python -m pytest -q tests/test_t02_self_red_team.py. Observe RED then GREEN per unit, tests and implementation in Conventional work-unit commits.
Closure: make verify PACK=t02. Isolate state/files and stub external image/model/T01/Enterprise integrations. Runtime boundary proof is direct tool and callback execution offline, not live ADK/cloud proof.
## Delivery and rollback
delivery_strategy: exception-ok; user approved ONE PR >400 authored lines (forecast 580–860). Do not golf tests. Slice: all three work-unit commits in one PR against main. Revert respective work-unit commit to undo its behavior/tests; later units depend on shared guardrail helpers.
RDD: global ON verified; do not toggle. Assess each commit from last reviewed boundary; preflight if due/unavailable. Candidate consent remains parent-owned, never fabricated.
## Progress and evidence
Prepared branch and clean tracked baseline verified. SKU-0017 actual margin 56.7/cap30; quarantine is required independently of discount (issue cap0 premise incorrect).
Commits: pending. Authored running count: 0.
Failed/skipped checks: cloud eval/deploy/test-remote intentionally skipped (not authorized).
T1 evidence: new suite RED 60 failed/27 passed; GREEN with guardrail and memory/router suites 118 passed (1 ADK warning). Legacy sanitize-and-accept tests intentionally changed to reject; clean upsert remains tested.
Unrelated concurrent ui/src/styles/nocturne.css edit detected and preserved/excluded.
Next step: T2 quarantine. Initial mirror saved/read back (#1577).

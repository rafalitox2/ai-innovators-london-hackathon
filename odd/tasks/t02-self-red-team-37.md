# T02 self red team — issue #37
## Objective and authorization
Close the verified raw-text, quarantine and numeric bypasses in approved issue #37 through one PR, no merge. Work directly in this shared checkout on fix/t02-self-red-team-37, baseline 29daf608b3025ca77b6ae7ae9c7741101d1d108e. Preserve unrelated .codegraph/ and odd/tasks/t02-ui-taste-redesign.md.
GitHub existing credential read/push/PR/labels authorized; cloud evaluation, deployment and live integrations are not.
## Scope and acceptance
Raw textual arguments rejected before sanitation at all read/action entry points; normalized bounded marker detection. Catalog IDs and poisoned records quarantined in six actions, callback and CSV/BQ/KG reads. Discount/CPM accept finite non-bool values only within bounds; no truncation bypass, exception or rejected-call side effect. Legitimate controls remain functional. No claim of universal prompt-injection prevention.
## Plan and routing
- [x] T1: Normalize marker detection; reject raw textual inputs; read entry parity.
- [x] T2: Quarantine six actions, callback and catalog/KG outputs.
- [x] T3: Validate finite non-bool discount/CPM values.
Each task route: delegated bounded writer (this agent). Parent mapping trigger 4+ files completed; writer trigger 2+ non-trivial files satisfied by parent delegation. No further preparatory delegation.
TDD ON: issue #37 and .agents/rules/pull-requests.md. Python 3.12 runner: .venv/bin/python -m pytest -q tests/test_t02_self_red_team.py. Observe RED then GREEN per unit, tests and implementation in Conventional work-unit commits.
Closure: make verify PACK=t02. Isolate state/files and stub external image/model/T01/Enterprise integrations. Runtime boundary proof is direct tool and callback execution offline, not live ADK/cloud proof.
## Delivery and rollback
delivery_strategy: exception-ok; user approved ONE PR >400 authored lines (forecast 580–860). Do not golf tests. Slice: all three work-unit commits in one PR against main. Revert respective work-unit commit to undo its behavior/tests; later units depend on shared guardrail helpers.
RDD: global ON verified; do not toggle. Assess each commit from last reviewed boundary; preflight if due/unavailable. Candidate consent remains parent-owned, never fabricated.
## Progress and evidence
Prepared branch and clean tracked baseline verified. SKU-0017 actual margin 56.7/cap30; quarantine is required independently of discount (issue cap0 premise incorrect).
Commits: T1 ce91223; T2 fe35d6c; T3 pending. Accumulated authored diff after T2: 405 lines.
Failed/skipped checks: cloud eval/deploy/test-remote intentionally skipped (not authorized).
T1 evidence: new suite RED 60 failed/27 passed; GREEN with guardrail and memory/router suites 118 passed (1 ADK warning). Legacy sanitize-and-accept tests intentionally changed to reject; clean upsert remains tested.
Unrelated concurrent ui/src/styles/nocturne.css edit detected and preserved/excluded.
Next step: T2 quarantine. Initial mirror saved/read back (#1577).

T1 commit ce91223: 214 authored lines; initial RDD assessment required untracked inventory. Preflight inventory verified; rerun excluding unrelated files: medium/under_budget (214 lines), no consent requested.
T2 evidence: RED 53 failed/87 passed (KG assertion initially used wrong response shape, corrected); GREEN 174 passed including existing KG/guardrail suites (1 ADK warning). Six action boundaries and callback, every catalog textual field, CSV/BQ recommendation/search and KG share quarantine. BQ carries full raw catalog record before projection.
Next step: T2 commit and T3 numeric RED.

T2 commit fe35d6c: medium/slice_budget_reached (405 accumulated authored lines). Native preflight with verified untracked exclusions returned review.start --consent=relay; executed verbatim. Native consent required (blocking), target sha256:0c780876664febdebcc055253c475a4b34e22daf78d8df11d269548d068f603c, lineage review-5205d9ff905227cd. No consent granted/declined and no approval claimed. Parent owns response; candidate will change with T3.
T3 RED: 46 failed/157 passed. GREEN: 203 passed (1 ADK warning). Integers required for discount signature; fractional values rejected instead of silently truncated. CPM remains fractional within (0,25]. Invalid conversions/overflow/nonfinite/bools rejected before side effects.
Full make verify PACK=t02: FAILED, 293 passed/2 failed/2 warnings. Failures are existing UI token tests (test_t02_nocturne_ui_mockup_and_template_tokens, test_ui_react_folder_structure_and_nocturne_design_system) reading concurrent unrelated template/CSS edits (old #161826 now #14151d). Do not change their work or tests. Remaining eval schema/pack checks must be run separately because make stopped after pytest.
Concurrent unrelated App.tsx, StorefrontPreviewModal.tsx, CSS and template edits preserved. Existing full-suite rendering regenerated tracked preview_SEG-001.html; keep out of PR.
Next step: run remaining offline gates, commit T3, refresh native consent evidence, open one draft PR with pending RDD and honest check failures.
Remaining offline gates: eval schema PASS (1 file, 13 cases); active packs t01/t02 + README PASS. Focused security/memory/KG/Enterprise suite: 246 passed, 1 warning. No shell scripts modified (shellcheck N/A).

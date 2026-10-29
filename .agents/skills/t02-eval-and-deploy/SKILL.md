---
name: t02-eval-and-deploy
description: This skill should be used when authoring golden evaluation scenarios (golden.test.json), running offline/live validation gates, configuring Google Cloud Build (cloudbuild.yaml), or deploying Table 2 to Vertex AI Agent Runtime (make deploy, make test-remote).
---

# Table 2 Evaluation, CI/CD & Vertex AI Deployment Skill (`t02-eval-and-deploy`)

Guides Spec/Eval-first TDD, ADK golden trajectory evaluation, GitHub Actions CI, Cloud Build CI/CD, and idempotent deployment to **Vertex AI Agent Runtime**.

## 1. Local Quality Gates (Run Before Every PR)

```bash
# 1. Offline unit + guardrail + Phase 2/3 tests (20+ tests, zero cloud calls)
make test

# 2. Validate golden.test.json schema and verify expected_tool_use against registered t02 tools
make eval-validate PACK=t02

# 3. Run live ADK trajectory + response evaluation against Vertex AI Gemini
make eval PACK=t02
```

## 2. Golden Evaluation Suite (`seed_packs/t02_dynamic_storefronts/eval/golden.test.json`)

Each scenario in `golden.test.json` validates end-to-end tool selection (`tool_trajectory_avg_score >= 0.75`) and grounded synthesis (`response_match_score >= 0.65`):
- `t02_nordic_madrid_bounce_recovery`: Diagnoses `ES_Madrid` bounce rate and calls `get_audience_segments`, `get_storefront_performance`, `find_catalog_products`.
- `t02_promo_discount_guardrail`: Attempts an illegal `95%` (`FLASH95`) discount on `SEG-001` and verifies `update_promo_banner` enforces the `30%` cap.
- `t02_end_to_end_storefront_optimization_and_preview`: Runs `recommend_storefront_optimization`, `generate_hero_lifestyle_image`, and `render_storefront_preview`.
- `t02_tribe_a2a_campaign_sync_with_t01`: Runs `sync_campaign_with_t01` to stage creative and bid on Table 1 (`t01_campaign_orchestrator`).

When adding a new scenario to `golden.test.json`, ensure every tool name in `expected_tool_use` is registered in `seed_packs/t02_dynamic_storefronts/tools.py` or `mcp_server.py`, then run `make eval-validate PACK=t02`.

## 3. Google Cloud & Vertex AI Agent Runtime Deployment

### Environment & GCP Resources
- **Project ID**: `expedition-dn26lon-5922`
- **Agent Runtime Region**: `europe-west1` (`AGENT_RUNTIME_LOCATION=europe-west1`)
- **Gemini Endpoint Location**: `global` (`GOOGLE_CLOUD_LOCATION=global`, `GEMINI_MODEL=gemini-3.0-flash`, `GEMINI_IMAGE_MODEL=gemini-3.1-flash-image`)
- **BigQuery Dataset**: `expedition-dn26lon-5922.seed_t02` (`BQ_LOCATION=EU`)
- **Staging Bucket**: `gs://expedition-dn26lon-5922-hackathon-staging`

### One-Time Staging Bucket Setup
```bash
gcloud storage buckets create gs://expedition-dn26lon-5922-hackathon-staging \
  --project=expedition-dn26lon-5922 \
  --location=europe-west1 \
  --uniform-bucket-level-access
```

### Deploy & Smoke-Test Commands (`deploy/deploy.py`)
```bash
# Deploy or update existing expedition_t02_dynamic_storefronts agent in Vertex AI Agent Runtime
make deploy

# Smoke-test the remote deployed agent engine in europe-west1
make test-remote
```
- **Idempotency Guarantee**: `deploy/deploy.py` lists existing reasoning engines in `europe-west1` and updates `expedition_t02_dynamic_storefronts` in place if it already exists (`action: " UPDATED"`), writing metadata to `.deployed_agent.json`.
- **Cloud Build Pipeline (`cloudbuild.yaml`)**: Runs `pytest`, `eval-validate`, and `deploy/deploy.py` with `_SEED_PACK=t02`, `_GEMINI_MODEL=gemini-3.0-flash`, and `_GEMINI_IMAGE_MODEL=gemini-3.1-flash-image`.

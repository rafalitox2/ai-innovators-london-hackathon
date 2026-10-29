# AtelierNova Home & Lifestyle — Table 2: Dynamic Storefront Engine

[![Agent CI Gates](https://github.com/rafalitox2/ai-innovators-london-hackathon/actions/workflows/ci.yml/badge.svg)](https://github.com/rafalitox2/ai-innovators-london-hackathon/actions/workflows/ci.yml)

> **Disclaimer:** *This is not an officially supported Google product. All datasets, companies, personas, scenarios, and mock action APIs in this repository are 100% synthetic and fictional.*

This is **Table 2's** fork of the AI Innovators Expedition hackathon starter, built for the **"Visual Content Creator & Dynamic Storefronts"** challenge: an ADK agent that reads AtelierNova Home & Lifestyle's BigQuery telemetry, finds under-performing segment × SKU storefront pairs, and publishes a personalized, guardrailed storefront layout — hero image, promo banner, discount — for each one.

- **Seed Pack:** `t02_dynamic_storefronts` (`SEED_PACK=t02`)
- **Tribe:** Creative AI & AdTech, paired with **Table 1** (`t01_campaign_orchestrator`) for the Tribe A2A Bonus
- **Sister Table integration:** `sync_campaign_with_t01` → see [A2A Integration](#4-a2a-integration-with-table-1) below

This README only documents our own build. The original multi-table hackathon starter guide (scoring rules, all 10 Challenge Cards, generic plugin contract) stayed on `main` of the upstream Starter and isn't repeated here.

---

## 1. Quickstart

```bash
git clone git@github.com:rafalitox2/ai-innovators-london-hackathon.git
cd ai-innovators-london-hackathon
make setup                 # uv venv, Python 3.12, pinned deps
cp .env.example .env       # fill in GOOGLE_CLOUD_PROJECT, keep SEED_PACK=t02
make seed PACK=t02         # load the 3 synthetic BigQuery tables into seed_t02
make test                  # offline pytest suite (loader, agent build, eval schema)
make dev                   # local ADK Web UI — http://127.0.0.1:8000
make eval                  # golden .test.json evaluation pipeline
make deploy                # deploy/update the agent on Vertex AI Agent Runtime (europe-west1)
make test-remote           # live verification query against the deployed agent
```

Required `.env` keys (see `.env.example`):

```dotenv
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_GENAI_USE_VERTEXAI=1
GOOGLE_CLOUD_LOCATION=global
GEMINI_MODEL=gemini-3.8-flash
GEMINI_IMAGE_MODEL=gemini-3.1-flash-image
AGENT_RUNTIME_LOCATION=europe-west1
BQ_LOCATION=EU
SEED_PACK=t02
STAGING_BUCKET=
```

For the full local React dashboard (`ui/`):

```bash
cd ui && npm install && npm run dev   # http://localhost:5173
```

---

## 2. Tool catalog

| Tool | File | What it does |
| :--- | :--- | :--- |
| `find_catalog_products` | `seed_packs/t02_dynamic_storefronts/tools.py` | Queries `products_catalog` by `style_theme`, `category`, `min_stock`. |
| `get_storefront_performance` | `tools.py` | Queries `storefront_experiments` by `segment_id`, `layout_variant`. |
| `get_audience_segments` | `tools.py` | Queries `audience_segments` by `region`, `dominant_style`. |
| `recommend_storefront_optimization` | `tools.py` | 3-table BigQuery JOIN ranking replacement SKUs + `max_safe_discount_pct` (excludes the quarantined `SKU-0017`). |
| `query_merchandising_knowledge_graph` | `knowledge_graph.py` | Traverses the merchandising knowledge graph (`STYLE_AFFINITY_GRAPH`) for cross-category bundle recommendations. |
| `publish_storefront_layout` | `mcp_server.py` | Publishes a personalized layout (`Editorial_Grid`, `Single_Hero_Spotlight`, `Curated_Bundle_Carousel`). |
| `queue_visual_asset_render` | `mcp_server.py` | Queues a visual lifestyle render job (`16:9`, `4:5`, `1:1`). |
| `update_promo_banner` | `mcp_server.py` | Updates banner copy; enforces the `<=30%` discount cap. |
| `generate_hero_lifestyle_image` | `mcp_server.py` | Generates a hero lifestyle image via `GEMINI_IMAGE_MODEL`. |
| `render_storefront_preview` | `mcp_server.py` | Renders the interactive MCP App UI preview (`ui://storefront-preview/<segment_id>`). |
| `sync_campaign_with_t01` | `mcp_server.py` | Tribe A2A handshake with Table 1 — see [§4](#4-a2a-integration-with-table-1). |
| `save_merchandising_memory` / `recall_merchandising_memory` | `mcp_server.py` | Cross-session merchandising notes (`gcs` + local state fallback). |
| `route_merchandising_task` | `model_router.py` | Routes tasks across `GEMMA_MODEL`, `GEMINI_MODEL`, `GEMINI_IMAGE_MODEL`. |
| `register_gemini_enterprise_agent` | `gemini_enterprise.py` | Registers the deployed `ReasoningEngine` as an ADK Agent inside a Gemini Enterprise App. |

Guardrails (non-negotiable, see `.agents/rules/t02-domain-invariants.md`): **≤30% discount cap**, **≥10% net margin floor**, `SKU-0017` prompt-injection quarantine, `MCP_TOOLS` parity between local and Agent Runtime.

---

## 3. Architecture

Three diagrams, each covering a different layer:

### 3.1 Component & data-flow (one ADK turn, end to end)

<img src="docs/diagrams/t02_architecture.svg" alt="T02 component and data-flow architecture: CI/CD, the ADK agent turn with the guardrail gate, and the data/state/UI/A2A fan-out" />

1. **Ship it** — a PR/push triggers **GitHub Actions CI** (`make test` + `make eval-validate`); on `main`, the CD job builds/deploys the Cloud Run MCP image and deploys the agent to **Vertex AI Agent Runtime**.
2. **Run it** — `LlmAgent expedition_t02` (`app/agent.py`) picks a tool; every call is screened first by the `before_tool_security_callback` guardrail (prompt-injection + discount cap), then reaches either the BigQuery read tools or the FastMCP action tools. The margin-floor cross-check and `render_storefront_preview`'s own cap are a second, independent layer inside the tools themselves.
3. **Store & show it** — reads hit `seed_t02` in BigQuery (CSV fallback offline); actions persist to `.state.json`, render into `seed_packs/t02_dynamic_storefronts/ui/`, and `sync_campaign_with_t01` hands off to Table 1.

### 3.2 Google Cloud infrastructure

<img src="docs/diagrams/t02_gcp_infrastructure.svg" alt="T02 Google Cloud infrastructure diagram: GitHub Actions, Cloud Build, Artifact Registry, Cloud Run, Vertex AI Agent Runtime, BigQuery, Cloud Storage, Gemini via Vertex AI, Discovery Engine / Gemini Enterprise, and Agent Registry, with their connections" />

Every GCP service this pack actually touches, and how they connect — see the diagram's own legend for the request/deploy paths.

### 3.3 A2A integration with Table 1

<img src="docs/diagrams/t02_a2a_integration.svg" alt="T02 to T01 Agent-to-Agent integration diagram: outbound STOREFRONT_TO_CAMPAIGN_SYNC handshake, the A2A discovery card, and the inbound live JSON-RPC endpoint" />

See [§4](#4-a2a-integration-with-table-1) for the written version of this diagram.

If GitHub doesn't animate these SVGs in your viewer, open them directly in a browser — they're self-contained (no external stylesheet dependency).

---

## 4. A2A integration with Table 1

Our Sister Table is **T01** (`t01_campaign_orchestrator`, `expedition_t01_campaign_orchestrator`). The handshake is `sync_campaign_with_t01` (`seed_packs/t02_dynamic_storefronts/mcp_server.py`):

- **Protocol:** envelope with `a2a_version: "1.0"`, `tribe: "Creative AI & AdTech"`, `sender_agent`/`recipient_agent`, `handshake_type: "STOREFRONT_TO_CAMPAIGN_SYNC"`.
- **Transport (current `main`):** in-process Python call — directly imports and calls T01's `create_localized_variant`/`place_ad_bid` functions. No network hop yet.
- **Guardrail:** rejects with `REJECTED_POLICY_CAP` if the computed CPM bid is `<= 0` or `> 25.0 EUR`.
- **Discovery:** `cd/mcp_http_server.py`'s `build_a2a_agent_card` publishes a real A2A Agent Card at `/.well-known/agent.json` (capabilities, skills, `a2a_tribe_handshake: true`).
- **Audit trail:** every handshake is recorded in `.state.json["a2a_handshakes"]` with an `A2A-T02-T01-<n>` ID.

A live, bidirectional HTTP endpoint (`/a2a`, full A2A JSON-RPC `message/send` + `agent/card`, so T01 can also POST a handshake *to* us instead of only us calling *into* T01's code) is in progress — see the diagram in §3.3 for both states.

Full spec: `docs/PHASE3_SPEC.md`, `.agents/skills/t02-mcp-actions-a2a/SKILL.md`.

---

## 5. Live deployment (T02 Scored Deployment — `expedition-dn26lon-5922`, `europe-west1`)

| Component | Live Endpoint / Resource Identifier | Status |
| :--- | :--- | :--- |
| **Nocturne Dynamic Storefront React UI (`/ui`)** | [`.../ui`](https://t02-dynamic-storefronts-mcp-d2lv3suxga-ew.a.run.app/ui) ([Root SPA](https://t02-dynamic-storefronts-mcp-d2lv3suxga-ew.a.run.app/)) | `ONLINE` |
| **Cloud Run FastMCP Server (Health & Tool Manifest)** | [`.../health`](https://t02-dynamic-storefronts-mcp-d2lv3suxga-ew.a.run.app/health) ([`/api/health`](https://t02-dynamic-storefronts-mcp-d2lv3suxga-ew.a.run.app/api/health)) | `ONLINE` |
| **FastMCP SSE Endpoint (`JSONRPC`)** | [`.../sse`](https://t02-dynamic-storefronts-mcp-d2lv3suxga-ew.a.run.app/sse) | `ONLINE` |
| **A2A Agent Discovery Card** | [`.../.well-known/agent.json`](https://t02-dynamic-storefronts-mcp-d2lv3suxga-ew.a.run.app/.well-known/agent.json) | `200 OK` |
| **Live Storefront UI Preview (`SEG-001`)** | [`.../preview/SEG-001`](https://t02-dynamic-storefronts-mcp-d2lv3suxga-ew.a.run.app/preview/SEG-001) | `200 OK` |
| **Vertex AI Agent Runtime (`ReasoningEngine`)** | `projects/633924037012/locations/europe-west1/reasoningEngines/5876565294532526080` | Authenticated REST API · verified via `make test-remote` |
| **Agent Registry — MCP Server** | `projects/expedition-dn26lon-5922/locations/europe-west1/services/t02-dynamic-storefronts-mcp` | Registered |
| **Agent Registry — ADK Agent** | `projects/expedition-dn26lon-5922/locations/europe-west1/services/t02-dynamic-storefronts-agent` | Registered |
| **GCS Staging & State Sync Bucket** | `gs://expedition-dn26lon-5922-hackathon-staging` | Active |
| **GitHub Actions CI/CD** | [`ci.yml`](https://github.com/rafalitox2/ai-innovators-london-hackathon/actions/workflows/ci.yml) | `passing` |

---

## 6. Documentation index

| Doc | What's in it |
| :--- | :--- |
| [`docs/README.md`](docs/README.md) | Short index of T02 docs + worktree setup notes (Spanish) |
| [`docs/BITACORA_T02.md`](docs/BITACORA_T02.md) | Master build logbook: phase-by-phase history, 14-tool catalog, 12 golden eval cases, PR traceability matrix |
| [`docs/PHASE1_SPEC.md`](docs/PHASE1_SPEC.md) | Spec: 5 Must-Haves, split CI/CD, 3-pillar Agentic SDLC, 3-layer security guardrails (`SKU-0017`) |
| [`docs/PHASE2_SPEC.md`](docs/PHASE2_SPEC.md) | Spec: BigQuery 3-table JOIN optimizations, multimodal + UI preview scope |
| [`docs/PHASE3_SPEC.md`](docs/PHASE3_SPEC.md) | Spec: Tribe A2A handshake protocol + editable UI directory |
| [`docs/PITCH_T02.md`](docs/PITCH_T02.md) | Pitch storyboard & live demo runbook (Spanish) |
| [`AGENTS.md`](AGENTS.md) | Coding-agent rules read by Google Antigravity (env/model rules, tool-authoring conventions, full T02 tool catalog) |
| [`.agents/rules/pull-requests.md`](.agents/rules/pull-requests.md) | PR workflow rule: branch-per-task, evidence commands, spec-first |
| [`.agents/rules/t02-domain-invariants.md`](.agents/rules/t02-domain-invariants.md) | Non-negotiable domain/security invariants |
| [`.agents/skills/t02-adk-bigquery/SKILL.md`](.agents/skills/t02-adk-bigquery/SKILL.md) | Authoring BigQuery read tools |
| [`.agents/skills/t02-mcp-actions-a2a/SKILL.md`](.agents/skills/t02-mcp-actions-a2a/SKILL.md) | FastMCP action tools, guardrails, A2A handshake contract |
| [`.agents/skills/t02-storefront-ui-multimodal/SKILL.md`](.agents/skills/t02-storefront-ui-multimodal/SKILL.md) | Hero image generation + MCP App UI preview |
| [`.agents/skills/t02-eval-and-deploy/SKILL.md`](.agents/skills/t02-eval-and-deploy/SKILL.md) | Golden evals, CI/CD, deploy |
| [`.agents/skills/t02-worktree-collab/SKILL.md`](.agents/skills/t02-worktree-collab/SKILL.md) | Multi-agent `git worktree` + Spec/Eval-first TDD workflow |
| [`seed_packs/t02_dynamic_storefronts/CHALLENGE_CARD.md`](seed_packs/t02_dynamic_storefronts/CHALLENGE_CARD.md) | Original challenge brief: persona, tools, bonus ideas, security test vector |
| [`seed_packs/t02_dynamic_storefronts/ui/design_handoff_dynamic_storefronts/README.md`](seed_packs/t02_dynamic_storefronts/ui/design_handoff_dynamic_storefronts/README.md) | Design handoff spec for the Nocturne dashboard (frozen reference, not production code) |
| [`seed_packs/t02_dynamic_storefronts/ui/design_handoff_dynamic_storefronts/design-system/nocturne-guide.md`](seed_packs/t02_dynamic_storefronts/ui/design_handoff_dynamic_storefronts/design-system/nocturne-guide.md) | Nocturne design-system guide (tokens, components) |
| [`cd/README.md`](cd/README.md) | CD architecture: GitHub → Cloud Run → Agent Runtime → Agent Registry |

---

## 7. Repository layout (T02-relevant paths)

```text
.
├── app/                                     # Root ADK LlmAgent (reads env, builds the agent)
├── seed_packs/t02_dynamic_storefronts/      # Our Seed Pack: tools, mcp_server, knowledge_graph, guardrails, data, eval
│   └── ui/                                  # MCP preview template.html + Nocturne design-handoff spec
├── ui/                                      # Nocturne React + TypeScript + Vite production dashboard
├── cd/                                      # Cloud Run MCP container, Cloud Build config, Agent Registry registration
├── deploy/                                  # Agent Runtime deploy/test-remote/delete scripts
├── eval/                                    # Golden evaluation runner
├── docs/                                    # T02 specs, logbook, pitch deck, diagrams (see §6)
├── .agents/                                 # Antigravity rules & skills (see §6)
├── tests/                                   # Offline pytest suite
├── AGENTS.md                                # Coding-agent rules
└── README.md                                # This file
```

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| `DefaultCredentialsError` or `403 PERMISSION_DENIED` | ADC credentials missing or quota project unset | `gcloud auth application-default login` + `gcloud auth application-default set-quota-project $GOOGLE_CLOUD_PROJECT`. |
| `SERVICE_DISABLED` / `API ... has not been used` | Required API not enabled | `gcloud services enable aiplatform.googleapis.com run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com storage.googleapis.com bigquery.googleapis.com cloudresourcemanager.googleapis.com`. |
| `Staging bucket gs://... does not exist` | Bucket not created | `gcloud storage buckets create gs://${GOOGLE_CLOUD_PROJECT}-hackathon-staging --location=europe-west1`. |
| `Not found: Dataset ...` | Seed data not loaded | `make seed PACK=t02`. |
| `.venv/bin/python not found` | Virtualenv setup skipped | `make setup`. |
| `404 Not Found` calling `gemini-3.8-flash` | Regional endpoint used instead of `global` | Keep `GOOGLE_CLOUD_LOCATION=global` (`AGENT_RUNTIME_LOCATION=europe-west1` is only for Agent Runtime). |
| Blank reply or `KeyError` on turn 1 | Unescaped `{variable}` in `instruction` | Replace `{foo}` with `[foo]`. |
| Tool spinner hangs or stream dies mid-turn | Tool raised an unhandled exception | Tools must never raise; catch and return `json.dumps({"status": "ERROR", ...})`. |
| Deserialization error in Agent Runtime | Deployed from Python 3.13 instead of 3.12 | Always deploy via `make deploy` (`.venv/bin/python`, Python 3.12). |
| GitHub Actions `google-github-actions/auth` fails with "not a valid Service Account Key JSON" | `GCP_CREDENTIALS_JSON` secret holds a sandbox `authorized_user` ADC JSON, not a service-account key | CI already handles this: the Sandbox ADC step writes the JSON to disk and uses `GOOGLE_APPLICATION_CREDENTIALS`/`CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE` instead of passing it to `auth@v2`'s `credentials_json` input. |

---

## 9. Reference docs

- **Google Agent Development Kit (ADK):** [https://adk.dev](https://adk.dev) ([Multi-Agent Orchestration](https://adk.dev/agents/custom-agents/) · [MCP Tools](https://adk.dev/tools-custom/mcp-tools/) · [Safety & Callbacks](https://adk.dev/callbacks/) · [CLI & A2A Deployment](https://adk.dev/api-reference/cli/))
- **Google Antigravity:** [https://antigravity.google](https://antigravity.google)
- **Vertex AI Agent Engine (Agent Runtime):** [docs](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/overview)
- **Register an ADK Agent in Gemini Enterprise:** [docs](https://cloud.google.com/gemini/enterprise/docs/register-and-manage-an-adk-agent)
- **BigQuery Python Client:** [reference](https://cloud.google.com/python/docs/reference/bigquery/latest)
- **Gemma Open Models:** [https://ai.google.dev/gemma/docs](https://ai.google.dev/gemma/docs)

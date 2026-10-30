# 📚 Technical Documentation & Engineering Portal — Table T02 (`t02_dynamic_storefronts`)

Welcome to the technical documentation directory, engineering methodology, and **Master Engineering Logbook** for **Table T02 (Visual Content Creator & Dynamic Storefronts — AtelierNova Home & Lifestyle)** at the **AI Innovators Expedition Hackathon (Google London, October 29–30, 2026)**.

---

## 🌐 Live Production Endpoints & Cloud Architecture

Table 2 is actively deployed on Google Cloud Platform in region `europe-west1` (`expedition-dn26lon-5922` / `633924037012`):

| Endpoint / Service | Protocol | Production URL / Identifier | Status | Purpose |
| :--- | :--- | :--- | :---: | :--- |
| **Nocturne UI Dashboard** | `HTTPS` | [https://t02-dynamic-storefronts-mcp-d2lv3suxga-ew.a.run.app/ui](https://t02-dynamic-storefronts-mcp-d2lv3suxga-ew.a.run.app/ui) | `200 OK` | Production React 19 + TypeScript SPA with GitHub Team Sign-In, Google Daylight/Dark M3 themes, Device Viewport Switcher (Desktop/Tablet/Mobile), and `1x`–`3x` Real-Photo Lightbox. |
| **Cloud Run Service Health** | `GET /health` | [https://t02-dynamic-storefronts-mcp-d2lv3suxga-ew.a.run.app/health](https://t02-dynamic-storefronts-mcp-d2lv3suxga-ew.a.run.app/health) | `200 OK` | Liveness check reporting uptime, project ID, active tools count (15 tools), and runtime configuration. |
| **A2A Agent Discovery Card** | `GET /.well-known/agent.json` | [https://t02-dynamic-storefronts-mcp-d2lv3suxga-ew.a.run.app/.well-known/agent.json](https://t02-dynamic-storefronts-mcp-d2lv3suxga-ew.a.run.app/.well-known/agent.json) | `200 OK` | ADK A2A Agent Card advertising capabilities, skills, and direct link to the Vertex AI ReasoningEngine. |
| **Live A2A JSON-RPC** | `POST /a2a` | [https://t02-dynamic-storefronts-mcp-d2lv3suxga-ew.a.run.app/a2a](https://t02-dynamic-storefronts-mcp-d2lv3suxga-ew.a.run.app/a2a) | `200 OK` | Live inter-agent protocol endpoint executing Tribe handshakes (`sync_campaign_with_t01`) with Table 1. |
| **Storefront Live Preview** | `GET /preview/SEG-001` | [https://t02-dynamic-storefronts-mcp-d2lv3suxga-ew.a.run.app/preview/SEG-001](https://t02-dynamic-storefronts-mcp-d2lv3suxga-ew.a.run.app/preview/SEG-001) | `200 OK` | Generative HTML5 storefront card tailored to segment style, discounts, real lifestyle hero visuals, and interactive `1x`–`3x` photo zoom lightbox. |
| **FastMCP SSE Stream** | `GET /sse` | [https://t02-dynamic-storefronts-mcp-d2lv3suxga-ew.a.run.app/sse](https://t02-dynamic-storefronts-mcp-d2lv3suxga-ew.a.run.app/sse) | `200 OK` | FastMCP Server-Sent Events endpoint for remote MCP clients (Claude Desktop, Antigravity, ADK). |
| **Vertex AI ReasoningEngine** | `HTTP_JSON` | `projects/633924037012/locations/europe-west1/reasoningEngines/5876565294532526080` | `200 OK` | Live Vertex AI Agent Runtime instance running Google ADK with Gemini 3.8 Flash. |
| **Agent Registry MCP Service** | `AgentRegistry API` | `projects/expedition-dn26lon-5922/locations/europe-west1/services/t02-dynamic-storefronts-mcp` | `REGISTERED` | Google Cloud Agent Registry MCP service entry cataloging all 10 action tools. |
| **Agent Registry Agent Service**| `AgentRegistry API`| `projects/expedition-dn26lon-5922/locations/europe-west1/services/t02-dynamic-storefronts-agent` | `REGISTERED` | Google Cloud Agent Registry ADK Agent entry bound to the Cloud Run FastMCP service. |

---

## 🧭 Documentation Index

| Document | Purpose | Scope / Phase |
| :--- | :--- | :--- |
| **[`BITACORA_T02.md`](./BITACORA_T02.md)** | **Master Engineering Logbook & Challenge Methodology**: Challenge rules, scoring criteria, Agentic SDLC practices, comprehensive phase-by-phase chronology (Phases 0 through 5), full Traceability Matrix for all 19 closed GitHub Issues and 41 merged PRs, Security Audit (`SEC-01`..`SEC-08` & 204 Self Red Team cases), OOP Architecture (`app/` + `mcp/`), and Bonus Matrix. | **All Phases (0–5)** |
| **[`PHASE1_SPEC.md`](./PHASE1_SPEC.md)** | **Technical Specification — Phase 0 & Phase 1 (1A + 1B)**: The 5 Must-Haves, split CI/CD architecture (GitHub Actions + Cloud Build), Agentic SDLC practices (6 Skills + Worktrees), and 3-Layer Security Guardrails (`SKU-0017`, `SKU-0085`, `before_tool_security_callback`). | **Phases 0, 1A & 1B** (`Issues #1, #2, #3, #37, #52` · `PR #8, #10, #11, #12, #13, #16, #17, #40, #53`) |
| **[`PHASE2_SPEC.md`](./PHASE2_SPEC.md)** | **Technical Specification — Phase 2 (2A + 2B)**: BigQuery 3-table parameterized analytics (`recommend_storefront_optimization`), multimodal hero asset generation (`generate_hero_lifestyle_image` via `gemini-3.1-flash-image`), MCP generative UI preview (`render_storefront_preview`), persistent memory, and Gemma/Gemini model routing. | **Phases 2A & 2B** (`Issues #4, #5, #21, #22, #23` · `PR #7, #14, #15, #24, #26, #28, #29, #30, #35`) |
| **[`PHASE3_SPEC.md`](./PHASE3_SPEC.md)** | **Technical Specification — Phase 3**: Tribe A2A Handshake Protocol (`sync_campaign_with_t01`) with Sister Table **Table 1 (`t01_campaign_orchestrator`)**, CPM governance guardrail (`<= 25.00 EUR`), and editable HTML5/CSS storefront template. | **Phase 3** (`Issue #6` · `PR #9, #42, #60`) |
| **[`PITCH_T02.md`](./PITCH_T02.md)** | **Pitch Storyboard (2 Slides) & Live Demo Runbook (3:00 min / 5:00 Hard Stop)**: Script for judges, live UI commands, production URLs, and exact demonstration prompts. | **Pitch & Live Demo** (`Issue #6` · `PR #9, #32`) |
| **[`STARTER.md`](./STARTER.md)** | Official Starter Kit technical reference (Google ADK architecture, seed pack plugin contract, Vertex AI Agent Runtime deployment, and bonus recipes). | Starter Kit Reference |
| **[`PREWORK.md`](./PREWORK.md)** | Pre-event setup checklist (Antigravity 2.0 configuration, `gcloud`, `uv`, Python 3.12, and the 10 hackathon tables). | Pre-Work |
| **[`diagrams/t02_architecture.svg`](./diagrams/t02_architecture.svg)** | Comprehensive animated SVG architecture diagrams (`t02_architecture.svg`, `t02_gcp_infrastructure.svg`, `t02_a2a_integration.svg`) visualizing user flows, ADK agent logic, BigQuery joins, MCP tools, Cloud Run, Vertex AI, and Agent Registry. | Architecture Visuals |

---

## 🛠️ Quick Verification & Audit Commands

Every member of the table, judge, or mentor can verify the entire project locally or against the live cloud deployment:

```bash
# 1. Run the full offline verification gate (393+ unit/ADK/A2A/security tests + 13 golden eval schema validations + pack checks)
make verify PACK=t02

# 2. Run unit tests individually (19 test modules across root, tests/adk/, and tests/a2a/)
make test

# 3. Run isolated Google ADK & Official A2A Protocol suites (offline or live GCP)
make test-adk
make test-a2a
make test-adk-gcp
make test-a2a-gcp

# 4. Run 8 Playwright E2E UX/UI audit tests (Desktop & Mobile viewports)
cd ui && npx playwright test

# 5. Validate the ADK Golden Evaluation dataset (13 golden cases valid)
make eval-validate PACK=t02

# 6. Run the live Golden Evaluation against Vertex AI Gemini 3.8 Flash & BigQuery
make eval PACK=t02

# 7. Check live Cloud Run FastMCP service health
curl -fsSL "https://t02-dynamic-storefronts-mcp-d2lv3suxga-ew.a.run.app/health"

# 8. Check live A2A Agent Discovery Card
curl -fsSL "https://t02-dynamic-storefronts-mcp-d2lv3suxga-ew.a.run.app/.well-known/agent.json"

# 9. Execute live A2A JSON-RPC Tribe Handshake with Table 1
curl -fsSL -X POST "https://t02-dynamic-storefronts-mcp-d2lv3suxga-ew.a.run.app/a2a" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "t02-test-sync",
    "method": "sync_campaign_with_t01",
    "params": {
      "segment_id": "SEG-001",
      "target_cpm_bid_eur": 12.50,
      "event_id": "EVT-0001",
      "channel": "Meta_Reels"
    }
  }'

# 10. Test live Vertex AI Agent Runtime ReasoningEngine in europe-west1
make test-remote
```

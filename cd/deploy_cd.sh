#!/usr/bin/env bash
# ==============================================================================
# Table 2 (t02_dynamic_storefronts) — Continuous Delivery Script (No OpenTofu)
# Uses standard repo CLI commands:
#   1. Builds & deploys FastMCP Server on Google Cloud Run (europe-west1)
#   2. Deploys ADK Agent to Vertex AI Agent Runtime via `make deploy PACK=t02`
#      (automatically syncing `.deployed_agent.json` with GCS)
#   3. Verifies live ADK Agent via `make test-remote`
#   4. Registers Cloud Run MCP Server & ADK Agent in Google Cloud Agent Registry
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

export GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-expedition-dn26lon-5922}"
export AGENT_RUNTIME_LOCATION="${AGENT_RUNTIME_LOCATION:-europe-west1}"
export GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-global}"
export GOOGLE_GENAI_USE_VERTEXAI="1"
export BQ_LOCATION="${BQ_LOCATION:-EU}"
export SEED_PACK="${SEED_PACK:-t02}"
export GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.8-flash}"
export GEMINI_IMAGE_MODEL="${GEMINI_IMAGE_MODEL:-gemini-3.1-flash-image}"
export STAGING_BUCKET="${STAGING_BUCKET:-gs://${GOOGLE_CLOUD_PROJECT}-hackathon-staging}"

PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
if [ ! -x "${PYTHON_BIN}" ] && [ -x "${REPO_ROOT}/../team-t02-hackathon/.venv/bin/python" ]; then
  PYTHON_BIN="${REPO_ROOT}/../team-t02-hackathon/.venv/bin/python"
elif [ ! -x "${PYTHON_BIN}" ]; then
  PYTHON_BIN="python3"
fi

echo "==> [1/4] Building & Deploying Table 2 FastMCP Server to Google Cloud Run (${AGENT_RUNTIME_LOCATION})..."
IMAGE_URI="${AGENT_RUNTIME_LOCATION}-docker.pkg.dev/${GOOGLE_CLOUD_PROJECT}/t02-mcp/t02-mcp-server:latest"
gcloud builds submit . \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --config="cd/cloudbuild-mcp-image.yaml" \
  --substitutions="_IMAGE_URI=${IMAGE_URI}" \
  --quiet

gcloud run deploy t02-dynamic-storefronts-mcp \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --region="${AGENT_RUNTIME_LOCATION}" \
  --image="${IMAGE_URI}" \
  --platform="managed" \
  --allow-unauthenticated \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${GOOGLE_CLOUD_PROJECT},SEED_PACK=${SEED_PACK},BQ_LOCATION=${BQ_LOCATION},GEMINI_MODEL=${GEMINI_MODEL},GEMINI_IMAGE_MODEL=${GEMINI_IMAGE_MODEL}" \
  --quiet

MCP_SERVER_URL="$(gcloud run services describe t02-dynamic-storefronts-mcp --project="${GOOGLE_CLOUD_PROJECT}" --region="${AGENT_RUNTIME_LOCATION}" --format="value(status.url)")"
export MCP_SERVER_URL
echo "    Cloud Run MCP Server URL: ${MCP_SERVER_URL}"

echo "==> [2/4] Deploying ADK Agent to Vertex AI Agent Runtime (syncs .deployed_agent.json with ${STAGING_BUCKET})..."
PYTHONPATH="${REPO_ROOT}" "${PYTHON_BIN}" -m deploy.deploy --pack "${SEED_PACK}"

echo "==> [3/4] Verifying live ADK Agent Runtime via deploy.test_remote..."
PYTHONPATH="${REPO_ROOT}" "${PYTHON_BIN}" -m deploy.test_remote

echo "==> [4/4] Registering Cloud Run MCP Server & ADK Agent in Google Cloud Agent Registry..."
PYTHONPATH="${REPO_ROOT}" "${PYTHON_BIN}" -m cd.register_agent_registry \
  --project-id "${GOOGLE_CLOUD_PROJECT}" \
  --location "${AGENT_RUNTIME_LOCATION}" \
  --mcp-url "${MCP_SERVER_URL}" \
  --mcp-service-id "t02-dynamic-storefronts-mcp" \
  --agent-service-id "t02-dynamic-storefronts-agent"

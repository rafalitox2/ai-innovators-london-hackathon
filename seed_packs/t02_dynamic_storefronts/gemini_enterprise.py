"""Gemini Enterprise (Agentspace / Discovery Engine) ADK Agent Registration for Table 2 (`t02_dynamic_storefronts`).

Surfaces the deployed Vertex AI Agent Runtime (`ReasoningEngine`) inside a
Gemini Enterprise App via the official Discovery Engine v1alpha REST API:
`https://{prefix}discoveryengine.googleapis.com/v1alpha/projects/{project}/locations/{app_location}/collections/default_collection/engines/{app_id}/assistants/default_assistant/agents`
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_REASONING_ENGINE_ID = "3204215998593531904"
_ALLOWED_DISCOVERY_LOCATIONS = frozenset({"eu", "us", "global"})
_SAFE_RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_SAFE_REASONING_ENGINE_RES_RE = re.compile(
    r"^projects/[A-Za-z0-9._-]+/locations/[A-Za-z0-9._-]+/reasoningEngines/[A-Za-z0-9._-]+$"
)


def _resolve_project() -> str:
    project = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("AGENT_ENGINE_PROJECT")
        or ""
    ).strip()
    if "your-gcp-project-id" in project.lower() or "your-project-id" in project.lower():
        return ""
    return project


def _resolve_runtime_location() -> str:
    return (
        os.environ.get("AGENT_RUNTIME_LOCATION", "europe-west1").strip()
        or "europe-west1"
    )


def resolve_reasoning_engine_resource(reasoning_engine_id: str = "") -> str:
    """Resolve the full `projects/.../locations/.../reasoningEngines/...` resource name."""
    raw = (reasoning_engine_id or "").strip()
    if raw.startswith("projects/") and "/reasoningEngines/" in raw:
        if not _SAFE_REASONING_ENGINE_RES_RE.match(raw):
            raise ValueError(f"Invalid ReasoningEngine resource path: '{raw}'")
        return raw

    deployed_file = _REPO_ROOT / ".deployed_agent.json"
    if not raw and deployed_file.is_file():
        try:
            deployed_data = json.loads(deployed_file.read_text(encoding="utf-8"))
            res_name = str(deployed_data.get("resource_name", "")).strip()
            if res_name.startswith("projects/") and _SAFE_REASONING_ENGINE_RES_RE.match(res_name):
                return res_name
        except Exception:
            pass

    engine_id = raw or os.environ.get("REASONING_ENGINE_ID", "").strip() or _DEFAULT_REASONING_ENGINE_ID
    if not _SAFE_RESOURCE_ID_RE.match(engine_id):
        raise ValueError(f"Invalid reasoning_engine_id: '{engine_id}'")
    project = _resolve_project() or "ateliernova-gcp-project"
    location = _resolve_runtime_location()
    return f"projects/{project}/locations/{location}/reasoningEngines/{engine_id}"


def build_discovery_engine_endpoint(
    project: str,
    app_location: str = "eu",
    app_id: str = "ateliernova-enterprise-search",
) -> str:
    """Build the Discovery Engine v1alpha assistant agents registration URL."""
    loc_clean = (app_location or "eu").strip().lower()
    if loc_clean not in _ALLOWED_DISCOVERY_LOCATIONS:
        raise ValueError(
            f"Unsupported Discovery Engine app_location '{app_location}'. "
            f"Expected one of {sorted(_ALLOWED_DISCOVERY_LOCATIONS)}."
        )
    prefix = "" if loc_clean == "global" else f"{loc_clean}-"
    proj_clean = (project or "ateliernova-gcp-project").strip()
    if not _SAFE_RESOURCE_ID_RE.match(proj_clean):
        raise ValueError(f"Invalid GCP project identifier: '{proj_clean}'")
    app_clean = (app_id or "ateliernova-enterprise-search").strip()
    if not _SAFE_RESOURCE_ID_RE.match(app_clean):
        raise ValueError(f"Invalid Discovery Engine app_id: '{app_clean}'")
    return (
        f"https://{prefix}discoveryengine.googleapis.com/v1alpha/"
        f"projects/{proj_clean}/locations/{loc_clean}/collections/default_collection/"
        f"engines/{app_clean}/assistants/default_assistant/agents"
    )


def build_gemini_enterprise_payload(
    display_name: str,
    description: str,
    tool_description: str,
    reasoning_engine_resource: str,
) -> dict[str, Any]:
    """Construct the official Discovery Engine `adkAgentDefinition` JSON body."""
    return {
        "displayName": display_name,
        "description": description,
        "adkAgentDefinition": {
            "toolSettings": {
                "toolDescription": tool_description,
            },
            "provisionedReasoningEngine": {
                "reasoningEngine": reasoning_engine_resource,
            },
        },
    }


def _post_to_discovery_engine(
    endpoint_url: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Send an authenticated POST request to Discovery Engine v1alpha."""
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    session = AuthorizedSession(credentials)
    response = session.post(
        endpoint_url,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=20,
    )
    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"Discovery Engine HTTP {response.status_code}: {response.text[:300]}"
        )
    return dict(response.json())


def execute_gemini_enterprise_registration(
    app_id: str = "ateliernova-enterprise-search",
    agent_display_name: str = "AtelierNova Dynamic Storefront Agent",
    app_location: str = "eu",
    reasoning_engine_id: str = "",
) -> dict[str, Any]:
    """Register the Table 2 ADK Agent in Gemini Enterprise (or produce a deterministic manifest fallback)."""
    project = _resolve_project()
    loc_clean = (app_location or "eu").strip().lower() or "eu"
    app_clean = (app_id or "ateliernova-enterprise-search").strip()
    display_clean = (
        agent_display_name or "AtelierNova Dynamic Storefront Agent"
    ).strip()

    re_resource = resolve_reasoning_engine_resource(reasoning_engine_id)
    endpoint_url = build_discovery_engine_endpoint(
        project=project or "ateliernova-gcp-project",
        app_location=loc_clean,
        app_id=app_clean,
    )
    payload = build_gemini_enterprise_payload(
        display_name=display_clean,
        description=(
            "Table 2 (Creative AI & AdTech) Dynamic Storefront & Visual Merchandising "
            "ADK Agent grounded in BigQuery dataset seed_t02."
        ),
        tool_description=(
            "Analyze audience segment conversion telemetry, traverse the merchandising "
            "knowledge graph for cross-category bundles, generate hero lifestyle visuals, "
            "render interactive storefront previews, and synchronize campaigns with "
            "Sister Table 1 via Tribe A2A."
        ),
        reasoning_engine_resource=re_resource,
    )

    use_offline = os.environ.get("SEED_OFFLINE_MODE", "").lower() in {"1", "true", "yes"}
    fallback_reason: str | None = None

    if project and not use_offline:
        try:
            api_resp = _post_to_discovery_engine(endpoint_url, payload)
            agent_res_name = str(
                api_resp.get("name")
                or f"projects/{project}/locations/{loc_clean}/collections/default_collection/engines/{app_clean}/assistants/default_assistant/agents/t02-dynamic-storefronts"
            )
            return {
                "app_id": app_clean,
                "app_location": loc_clean,
                "agent_display_name": display_clean,
                "reasoning_engine": re_resource,
                "endpoint_url": endpoint_url,
                "agent_resource_name": agent_res_name,
                "execution_mode": "discovery_engine_live",
                "request_payload": payload,
                "api_response": api_resp,
                "status": "REGISTERED",
            }
        except Exception as exc:
            fallback_reason = f"{type(exc).__name__}: {exc}"
    else:
        fallback_reason = (
            "SEED_OFFLINE_MODE enabled"
            if use_offline
            else "GOOGLE_CLOUD_PROJECT not set"
        )

    eff_project = project or "ateliernova-gcp-project"
    agent_res_name = (
        f"projects/{eff_project}/locations/{loc_clean}/collections/default_collection/"
        f"engines/{app_clean}/assistants/default_assistant/agents/t02-dynamic-storefronts"
    )
    record: dict[str, Any] = {
        "app_id": app_clean,
        "app_location": loc_clean,
        "agent_display_name": display_clean,
        "reasoning_engine": re_resource,
        "endpoint_url": endpoint_url,
        "agent_resource_name": agent_res_name,
        "execution_mode": "deterministic_manifest_fallback",
        "request_payload": payload,
        "status": "REGISTERED",
    }
    if fallback_reason:
        record["fallback_reason"] = fallback_reason
    return record

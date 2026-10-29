"""Register the Cloud Run MCP Server, ADK Agent, and Binding in Google Cloud Agent Registry (agentregistry.googleapis.com)."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any
import urllib.error
import urllib.request

from app.loader import REPO_ROOT

STATE_FILE = REPO_ROOT / ".deployed_agent.json"
CD_MANIFEST_FILE = REPO_ROOT / "cd" / "cd_deployment_state.json"


def build_mcp_registry_service_payload(
    *,
    mcp_url: str,
    display_name: str = "T02 Dynamic Storefronts MCP Server",
) -> dict[str, Any]:
    """Build the agentregistry.googleapis.com v1alpha Service payload for the Cloud Run MCP Server."""
    clean_url = mcp_url.rstrip("/")
    sse_url = clean_url if clean_url.endswith("/sse") else f"{clean_url}/sse"
    return {
        "displayName": display_name[:63],
        "description": (
            "Table 2 (t02_dynamic_storefronts) FastMCP Server hosted on Google Cloud Run "
            "providing publish_storefront_layout, queue_visual_asset_render, update_promo_banner, "
            "generate_hero_lifestyle_image, render_storefront_preview, and sync_campaign_with_t01."
        ),
        "mcpServerSpec": {
            "type": "NO_SPEC",
        },
        "interfaces": [
            {
                "protocolBinding": "JSONRPC",
                "url": sse_url,
            }
        ],
    }


def build_agent_registry_service_payload(
    *,
    mcp_url: str,
    reasoning_engine_resource: str = "",
    display_name: str = "T02 Dynamic Storefronts ADK Agent",
) -> dict[str, Any]:
    """Build the agentregistry.googleapis.com v1alpha Service payload for the Table 2 ADK Agent."""
    clean_url = mcp_url.rstrip("/")
    endpoint_url = (
        f"https://europe-west1-aiplatform.googleapis.com/v1/{reasoning_engine_resource}"
        if reasoning_engine_resource.startswith("projects/")
        else f"{clean_url}/.well-known/agent.json"
    )
    return {
        "displayName": display_name[:63],
        "description": (
            "Table 2 Dynamic Storefront Engine ADK Agent deployed on Vertex AI Agent Runtime "
            f"({reasoning_engine_resource or 'europe-west1'}) and paired with Cloud Run MCP ({clean_url})."
        ),
        "agentSpec": {
            "type": "NO_SPEC",
        },
        "interfaces": [
            {
                "protocolBinding": "HTTP_JSON",
                "url": endpoint_url,
            }
        ],
    }


def build_agent_mcp_binding_payload(
    *,
    agent_urn: str,
    mcp_urn: str,
    display_name: str = "T02 ADK Agent to Cloud Run MCP Binding",
) -> dict[str, Any]:
    """Build the agentregistry.googleapis.com v1alpha Binding payload linking the ADK Agent and MCP Server."""
    return {
        "displayName": display_name[:63],
        "description": "Binds the Table 2 ADK Agent in Vertex AI Agent Runtime to its Cloud Run FastMCP Server.",
        "source": {
            "identifier": agent_urn,
        },
        "target": {
            "identifier": mcp_urn,
        },
    }


def _get_access_token() -> str:
    env_token = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN", "").strip()
    if env_token:
        return env_token
    out = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True)
    return out.strip()


def _api_request(
    method: str,
    url: str,
    *,
    project_id: str,
    token: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "x-goog-user-project": project_id,
        "Content-Type": "application/json",
    }
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        return {"error_code": exc.code, "error_body": err_body}


def _wait_lro(
    op_obj: dict[str, Any],
    *,
    project_id: str,
    token: str,
    max_wait_sec: int = 30,
) -> dict[str, Any]:
    op_name = op_obj.get("name", "")
    if not op_name or op_obj.get("done"):
        return op_obj
    op_url = f"https://agentregistry.googleapis.com/v1alpha/{op_name}"
    deadline = time.time() + max_wait_sec
    while time.time() < deadline:
        res = _api_request("GET", op_url, project_id=project_id, token=token)
        if res.get("done") or "error_code" in res:
            return res
        time.sleep(2)
    return op_obj


def upsert_registry_service(
    *,
    project_id: str,
    location: str,
    service_id: str,
    payload: dict[str, Any],
    token: str,
) -> dict[str, Any]:
    """Create or update a Service in agentregistry.googleapis.com/v1alpha."""
    base = f"https://agentregistry.googleapis.com/v1alpha/projects/{project_id}/locations/{location}/services"
    get_url = f"{base}/{service_id}"
    existing = _api_request("GET", get_url, project_id=project_id, token=token)

    if "name" in existing and "error_code" not in existing:
        patch_url = f"{get_url}?updateMask=displayName,description,interfaces"
        op = _api_request("PATCH", patch_url, project_id=project_id, token=token, payload=payload)
    else:
        create_url = f"{base}?serviceId={service_id}"
        op = _api_request("POST", create_url, project_id=project_id, token=token, payload=payload)

    _wait_lro(op, project_id=project_id, token=token)
    return _api_request("GET", get_url, project_id=project_id, token=token)


def register_all_in_agent_registry(
    *,
    project_id: str,
    location: str,
    mcp_url: str,
    reasoning_engine_resource: str = "",
    mcp_service_id: str = "t02-dynamic-storefronts-mcp",
    agent_service_id: str = "t02-dynamic-storefronts-agent",
) -> dict[str, Any]:
    """Register the Cloud Run MCP Server and the ADK Agent in Google Cloud Agent Registry."""
    if not reasoning_engine_resource and STATE_FILE.exists():
        try:
            saved = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            reasoning_engine_resource = str(saved.get("resource_name") or "").strip()
        except Exception:
            reasoning_engine_resource = ""

    token = _get_access_token()

    mcp_payload = build_mcp_registry_service_payload(mcp_url=mcp_url)
    mcp_service = upsert_registry_service(
        project_id=project_id,
        location=location,
        service_id=mcp_service_id,
        payload=mcp_payload,
        token=token,
    )

    agent_payload = build_agent_registry_service_payload(
        mcp_url=mcp_url,
        reasoning_engine_resource=reasoning_engine_resource,
    )
    agent_service = upsert_registry_service(
        project_id=project_id,
        location=location,
        service_id=agent_service_id,
        payload=agent_payload,
        token=token,
    )

    # Fetch resulting Agent and MCP Server records to obtain their URN identifiers if available
    agent_reg_res = str(agent_service.get("registryResource") or "")
    mcp_reg_res = str(mcp_service.get("registryResource") or "")

    agent_entity: dict[str, Any] = {}
    mcp_entity: dict[str, Any] = {}
    if agent_reg_res:
        agent_entity = _api_request(
            "GET",
            f"https://agentregistry.googleapis.com/v1alpha/{agent_reg_res}",
            project_id=project_id,
            token=token,
        )
    if mcp_reg_res:
        mcp_entity = _api_request(
            "GET",
            f"https://agentregistry.googleapis.com/v1alpha/{mcp_reg_res}",
            project_id=project_id,
            token=token,
        )

    binding_result: dict[str, Any] = {}
    agent_urn = str(agent_entity.get("agentId") or "")
    mcp_urn = str(mcp_entity.get("mcpServerId") or "")
    if agent_urn and mcp_urn:
        binding_result = build_agent_mcp_binding_payload(agent_urn=agent_urn, mcp_urn=mcp_urn)

    manifest = {
        "status": "REGISTERED",
        "project_id": project_id,
        "location": location,
        "cloud_run_mcp_url": mcp_url.rstrip("/"),
        "cloud_run_mcp_sse_url": f"{mcp_url.rstrip('/')}/sse",
        "cloud_run_storefront_preview_url": f"{mcp_url.rstrip('/')}/preview/SEG-001",
        "vertex_ai_reasoning_engine": reasoning_engine_resource,
        "agent_registry": {
            "mcp_service": mcp_service,
            "mcp_server_entity": mcp_entity,
            "agent_service": agent_service,
            "agent_entity": agent_entity,
            "binding": binding_result,
        },
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    CD_MANIFEST_FILE.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Register Table 2 Cloud Run MCP Server and ADK Agent in Google Cloud Agent Registry."
    )
    parser.add_argument(
        "--project-id",
        default=os.environ.get("GOOGLE_CLOUD_PROJECT", "expedition-dn26lon-5922"),
    )
    parser.add_argument(
        "--location",
        default=os.environ.get("AGENT_RUNTIME_LOCATION", "europe-west1"),
    )
    parser.add_argument(
        "--mcp-url",
        required=True,
        help="HTTPS URL of the deployed Cloud Run MCP service.",
    )
    parser.add_argument(
        "--reasoning-engine",
        default=os.environ.get("AGENT_ENGINE_RESOURCE_NAME", ""),
        help="Optional Vertex AI Agent Runtime resource name.",
    )
    parser.add_argument(
        "--mcp-service-id",
        default="t02-dynamic-storefronts-mcp",
        help="Agent Registry service ID for the Cloud Run MCP Server.",
    )
    parser.add_argument(
        "--agent-service-id",
        default="t02-dynamic-storefronts-agent",
        help="Agent Registry service ID for the ADK Agent.",
    )
    args = parser.parse_args()
    register_all_in_agent_registry(
        project_id=args.project_id,
        location=args.location,
        mcp_url=args.mcp_url,
        reasoning_engine_resource=args.reasoning_engine,
        mcp_service_id=args.mcp_service_id,
        agent_service_id=args.agent_service_id,
    )


if __name__ == "__main__":
    main()

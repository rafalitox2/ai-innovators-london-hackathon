"""TDD validation suite for Table 2 Continuous Delivery (OpenTofu, Cloud Run MCP Server, and Agent Registry)."""

from __future__ import annotations

from pathlib import Path
from starlette.testclient import TestClient
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CD_DIR = REPO_ROOT / "cd"
OPENTOFU_DIR = CD_DIR / "opentofu"


def test_cd_opentofu_files_and_resources_exist() -> None:
    """Verify cd/opentofu/ contains versions.tf, variables.tf, main.tf, and outputs.tf with Cloud Run & Agent Registry."""
    for filename in ("versions.tf", "variables.tf", "main.tf", "outputs.tf"):
        tf_file = OPENTOFU_DIR / filename
        assert tf_file.exists(), f"Missing OpenTofu file: {tf_file}"

    main_tf = (OPENTOFU_DIR / "main.tf").read_text(encoding="utf-8")
    for required in (
        "google_storage_bucket",
        "google_artifact_registry_repository",
        "google_cloud_run_v2_service",
        "t02-dynamic-storefronts-mcp",
        "register_agent_registry.py",
    ):
        assert required in main_tf, f"cd/opentofu/main.tf is missing '{required}'"


def test_cd_mcp_cloudrun_http_server_endpoints() -> None:
    """Verify cd/mcp_http_server.py exposes /healthz, /.well-known/agent.json, /preview/{segment_id}, and /sse."""
    from cd.mcp_http_server import build_mcp_cloudrun_app

    app = build_mcp_cloudrun_app()
    client = TestClient(app)

    # 1. Health & MCP tool manifest endpoint
    health_res = client.get("/healthz")
    assert health_res.status_code == 200
    health = health_res.json()
    assert health["status"] == "ONLINE"
    assert health["service"] == "t02-dynamic-storefronts-mcp"
    assert "recommend_storefront_optimization" in health["adk_tools"] or len(health["mcp_tools"]) >= 6
    for mcp_tool_name in (
        "publish_storefront_layout",
        "queue_visual_asset_render",
        "update_promo_banner",
        "generate_hero_lifestyle_image",
        "render_storefront_preview",
        "sync_campaign_with_t01",
    ):
        assert mcp_tool_name in health["mcp_tools"]

    # 2. A2A Agent Discovery Card endpoint
    card_res = client.get("/.well-known/agent.json")
    assert card_res.status_code == 200
    card = card_res.json()
    assert card["name"] == "expedition_t02_dynamic_storefronts"
    assert len(card["skills"]) >= 4

    # 3. Interactive Storefront UI Preview endpoint on Cloud Run
    preview_res = client.get("/preview/SEG-001")
    assert preview_res.status_code == 200
    assert "Dynamic Storefront Engine" in preview_res.text


def test_cd_agent_registry_payload_builders() -> None:
    """Verify cd/register_agent_registry.py builds valid agentregistry.googleapis.com v1alpha payloads."""
    from cd.register_agent_registry import (
        build_agent_mcp_binding_payload,
        build_agent_registry_service_payload,
        build_mcp_registry_service_payload,
    )

    mcp_payload = build_mcp_registry_service_payload(
        mcp_url="https://t02-dynamic-storefronts-mcp-ew1.a.run.app"
    )
    assert "mcpServerSpec" in mcp_payload
    assert mcp_payload["interfaces"][0]["protocolBinding"] == "HTTP_JSON"
    assert mcp_payload["interfaces"][0]["url"].startswith(
        "https://t02-dynamic-storefronts-mcp-ew1.a.run.app"
    )

    agent_payload = build_agent_registry_service_payload(
        mcp_url="https://t02-dynamic-storefronts-mcp-ew1.a.run.app",
        reasoning_engine_resource="projects/633924037012/locations/europe-west1/reasoningEngines/12345",
    )
    assert "agentSpec" in agent_payload
    assert agent_payload["displayName"]

    binding_payload = build_agent_mcp_binding_payload(
        agent_urn="urn:agent:custom:expedition-dn26lon-5922:t02-dynamic-storefronts-agent",
        mcp_urn="urn:mcp:custom:expedition-dn26lon-5922:t02-dynamic-storefronts-mcp",
    )
    assert (
        binding_payload["source"]["identifier"]
        == "urn:agent:custom:expedition-dn26lon-5922:t02-dynamic-storefronts-agent"
    )
    assert (
        binding_payload["target"]["identifier"]
        == "urn:mcp:custom:expedition-dn26lon-5922:t02-dynamic-storefronts-mcp"
    )


def test_cd_dockerfile_scripts_and_github_workflow_exist() -> None:
    """Verify cd/Dockerfile.mcp, cd/deploy_cd.sh, and .github/workflows/cd.yml exist and are valid."""
    assert (CD_DIR / "Dockerfile.mcp").exists(), "Missing cd/Dockerfile.mcp"
    assert (CD_DIR / "deploy_cd.sh").exists(), "Missing cd/deploy_cd.sh"
    assert (CD_DIR / "README.md").exists(), "Missing cd/README.md"

    cd_wf_path = REPO_ROOT / ".github" / "workflows" / "cd.yml"
    assert cd_wf_path.exists(), "Missing .github/workflows/cd.yml"
    cd_wf = yaml.safe_load(cd_wf_path.read_text(encoding="utf-8"))
    assert "jobs" in cd_wf

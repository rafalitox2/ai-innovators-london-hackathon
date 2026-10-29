"""TDD validation suite for Table 2 Continuous Delivery (GitHub Actions CD, Cloud Run MCP, GCS State Sync, and Agent Registry)."""

from __future__ import annotations

from pathlib import Path
from starlette.testclient import TestClient
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CD_DIR = REPO_ROOT / "cd"


def test_cd_github_actions_and_cloudbuild_config() -> None:
    """Verify .github/workflows/ci.yml and cloudbuild.yaml implement Issue #19 CD + Cloud Run MCP + Agent Registry."""
    ci_wf_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert ci_wf_path.exists(), "Missing .github/workflows/ci.yml"
    ci_text = ci_wf_path.read_text(encoding="utf-8")
    ci_wf = yaml.safe_load(ci_text)

    assert "test-and-validate-evals" in ci_wf["jobs"]
    assert "cd-deploy-agent-runtime" in ci_wf["jobs"]

    for expected in (
        "google-github-actions/auth@v2",
        "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "t02-dynamic-storefronts-mcp",
        "make deploy PACK=t02",
        "make test-remote",
        "cd.register_agent_registry",
    ):
        assert expected in ci_text, f".github/workflows/ci.yml is missing '{expected}'"

    cb_text = (REPO_ROOT / "cloudbuild.yaml").read_text(encoding="utf-8")
    for expected in (
        "sync_state_from_gcs",
        "sync_state_to_gcs",
        "deploy.deploy",
        "deploy.test_remote",
    ):
        assert expected in cb_text, f"cloudbuild.yaml is missing '{expected}'"


def test_cd_mcp_cloudrun_http_server_endpoints(monkeypatch) -> None:
    """Verify cd/mcp_http_server.py exposes /healthz, /.well-known/agent.json, /a2a, /preview/{segment_id}, and /sse."""
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")
    from cd.mcp_http_server import build_mcp_cloudrun_app

    app = build_mcp_cloudrun_app()
    client = TestClient(app)

    # 1. Health & MCP tool manifest endpoint
    health_res = client.get("/healthz")
    assert health_res.status_code == 200
    health = health_res.json()
    assert health["status"] == "ONLINE"
    assert health["service"] == "t02-dynamic-storefronts-mcp"
    for mcp_tool_name in (
        "publish_storefront_layout",
        "queue_visual_asset_render",
        "update_promo_banner",
        "generate_hero_lifestyle_image",
        "render_storefront_preview",
        "sync_campaign_with_t01",
        "save_merchandising_memory",
        "recall_merchandising_memory",
        "route_merchandising_task",
    ):
        assert mcp_tool_name in health["mcp_tools"]

    # 2. A2A Agent Discovery Card endpoints (/.well-known/agent.json, /.well-known/agent-card.json, GET /a2a)
    for card_path in ("/.well-known/agent.json", "/.well-known/agent-card.json", "/a2a"):
        card_res = client.get(card_path)
        assert card_res.status_code == 200
        card = card_res.json()
        assert card["name"] == "expedition_t02_dynamic_storefronts"
        assert card["url"].endswith("/a2a")
        assert len(card["skills"]) >= 4

    # 2b. Live A2A JSON-RPC 2.0 POST /a2a (message/send) and Structured Handshake POST /a2a
    rpc_res = client.post(
        "/a2a",
        json={
            "jsonrpc": "2.0",
            "id": "rpc-test-1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"text": "Sync campaign with T01 for SEG-057 at 12.5 EUR CPM"}],
                }
            },
        },
    )
    assert rpc_res.status_code == 200
    rpc_payload = rpc_res.json()
    assert rpc_payload["jsonrpc"] == "2.0"
    assert rpc_payload["id"] == "rpc-test-1"
    assert rpc_payload["result"]["status"]["state"] == "completed"

    hs_res = client.post(
        "/a2a",
        json={
            "segment_id": "SEG-057",
            "featured_skus": "SKU-0057,SKU-0002",
            "hero_headline": "Warm Mediterranean light for London homes",
            "theme_style": "Mediterranean_Warm",
            "locale": "en-GB",
            "event_id": "EVT-0001",
            "channel": "Meta_Reels",
            "target_cpm_bid_eur": 12.5,
        },
    )
    assert hs_res.status_code == 200
    hs_payload = hs_res.json()
    assert hs_payload["status"] == "SUCCESS"
    assert hs_payload["a2a_handshake"]["handshake_type"] == "STOREFRONT_TO_CAMPAIGN_SYNC"

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
    assert mcp_payload["interfaces"][0]["protocolBinding"] == "JSONRPC"
    assert mcp_payload["interfaces"][0]["url"].startswith(
        "https://t02-dynamic-storefronts-mcp-ew1.a.run.app"
    )
    for expected_tool in (
        "publish_storefront_layout",
        "save_merchandising_memory",
        "recall_merchandising_memory",
        "route_merchandising_task",
    ):
        assert expected_tool in mcp_payload["description"]

    agent_payload = build_agent_registry_service_payload(
        mcp_url="https://t02-dynamic-storefronts-mcp-ew1.a.run.app",
        reasoning_engine_resource="projects/633924037012/locations/europe-west1/reasoningEngines/5876565294532526080",
    )
    assert "agentSpec" in agent_payload
    assert agent_payload["displayName"]
    assert "recommend_storefront_optimization" in agent_payload["description"]

    binding_payload = build_agent_mcp_binding_payload(
        agent_urn="urn:agent:projects-633924037012:projects:633924037012:locations:europe-west1:agentregistry:services:t02-dynamic-storefronts-agent",
        mcp_urn="urn:mcp:projects-633924037012:projects:633924037012:locations:europe-west1:agentregistry:services:t02-dynamic-storefronts-mcp",
    )
    assert (
        binding_payload["source"]["identifier"]
        == "urn:agent:projects-633924037012:projects:633924037012:locations:europe-west1:agentregistry:services:t02-dynamic-storefronts-agent"
    )
    assert (
        binding_payload["target"]["identifier"]
        == "urn:mcp:projects-633924037012:projects:633924037012:locations:europe-west1:agentregistry:services:t02-dynamic-storefronts-mcp"
    )


def test_cd_dockerfile_and_scripts_exist() -> None:
    """Verify cd/Dockerfile.mcp, cd/deploy_cd.sh, and cd/README.md exist and follow repo conventions."""
    dockerfile_path = CD_DIR / "Dockerfile.mcp"
    assert dockerfile_path.exists(), "Missing cd/Dockerfile.mcp"
    dockerfile_text = dockerfile_path.read_text(encoding="utf-8")
    assert "google-genai==" in dockerfile_text
    assert "google-cloud-storage==" in dockerfile_text

    mcp_http_text = (CD_DIR / "mcp_http_server.py").read_text(encoding="utf-8")
    assert "resolve_env_config" in mcp_http_text
    assert "gemini-" not in mcp_http_text.lower()

    assert (CD_DIR / "deploy_cd.sh").exists(), "Missing cd/deploy_cd.sh"
    assert (CD_DIR / "README.md").exists(), "Missing cd/README.md"


def test_deploy_gcs_state_sync_roundtrip(tmp_path: Path) -> None:
    """Verify sync_state_to_gcs and sync_state_from_gcs keep .deployed_agent.json synchronized across ephemeral runners."""
    from deploy.deploy import sync_state_from_gcs, sync_state_to_gcs

    class _FakeBlob:
        def __init__(self, store: dict[str, str], name: str) -> None:
            self._store = store
            self._name = name

        def exists(self) -> bool:
            return self._name in self._store

        def download_as_text(self, encoding: str = "utf-8") -> str:
            return self._store[self._name]

        def upload_from_string(self, content: str, content_type: str = "application/json") -> None:
            self._store[self._name] = content

    class _FakeBucket:
        def __init__(self, store: dict[str, str]) -> None:
            self._store = store

        def blob(self, name: str) -> _FakeBlob:
            return _FakeBlob(self._store, name)

    class _FakeStorageClient:
        def __init__(self) -> None:
            self.store: dict[str, str] = {}

        def bucket(self, _name: str) -> _FakeBucket:
            return _FakeBucket(self.store)

    fake_client = _FakeStorageClient()
    state_a = tmp_path / "runner_a" / ".deployed_agent.json"
    state_a.parent.mkdir()
    state_a.write_text(
        '{"resource_name": "projects/633924037012/locations/europe-west1/reasoningEngines/5876565294532526080"}',
        encoding="utf-8",
    )

    assert (
        sync_state_to_gcs(
            "expedition-dn26lon-5922",
            "gs://expedition-dn26lon-5922-hackathon-staging",
            state_a,
            storage_client=fake_client,
        )
        is True
    )
    assert ".deployed_agent.json" in fake_client.store

    state_b = tmp_path / "runner_b" / ".deployed_agent.json"
    state_b.parent.mkdir()
    assert (
        sync_state_from_gcs(
            "expedition-dn26lon-5922",
            "gs://expedition-dn26lon-5922-hackathon-staging",
            state_b,
            storage_client=fake_client,
        )
        is True
    )
    assert state_b.read_text(encoding="utf-8") == state_a.read_text(encoding="utf-8")

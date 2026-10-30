"""Security audit regression suite for Table 2 (`t02_dynamic_storefronts`).

Covers the 8 findings identified using the Cloudflare `security-audit-skill`:
1. SEC-01: Wildcard CORS with credentials (`allow_origins=["*"]` + `allow_credentials=True`).
2. SEC-02: Path traversal in `generate_hero_lifestyle_image` and `render_storefront_preview`.
3. SEC-03: DOM XSS via unescaped `innerHTML` and `<script>` interpolation in `ui/template.html`.
4. SEC-04: Sanitization-before-detection bypass (`<!-- ... -->`) and incomplete `before_tool_security_callback` / `hero_asset_url` validation.
5. SEC-05: SSRF / URL path injection in `build_discovery_engine_endpoint` (`gemini_enterprise.py`).
6. SEC-06: Untrusted `Host` header reflection in `/.well-known/agent.json` (`cd/mcp_http_server.py`).
7. SEC-07: Unvalidated BigQuery dataset/project identifier interpolation in `tools.py`.
8. SEC-08: Missing defensive HTTP security headers (`X-Content-Type-Options: nosniff`, `X-Frame-Options`, SVG `Content-Security-Policy`).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


def test_sec01_cors_disallows_wildcard_with_credentials() -> None:
    """FastAPI servers must not pair Access-Control-Allow-Origin: * with credentials."""
    from app.ui_server import app as ui_app
    from cd.mcp_http_server import app as mcp_app

    for fastapi_app in (ui_app, mcp_app):
        client = TestClient(fastapi_app)
        resp = client.options(
            "/health" if fastapi_app is mcp_app else "/api/health",
            headers={
                "Origin": "https://evil-attacker.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        allow_origin = resp.headers.get("access-control-allow-origin", "")
        allow_creds = resp.headers.get("access-control-allow-credentials", "").lower()
        assert allow_origin != "https://evil-attacker.example.com"
        assert not (allow_origin == "*" and allow_creds == "true")


def test_sec02_path_traversal_sanitized_in_mcp_tools(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """generate_hero_lifestyle_image and render_storefront_preview strip traversal sequences."""
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")
    monkeypatch.setenv("T02_LOCAL_STATE_FILE", str(tmp_path / "t02_state.json"))

    from seed_packs.t02_dynamic_storefronts.mcp_server import (
        generate_hero_lifestyle_image,
        render_storefront_preview,
    )

    img_resp = json.loads(
        generate_hero_lifestyle_image(
            sku_id="../../etc/passwd",
            segment_id="../../tmp/pwn",
            scene_description="Editorial minimalist studio lighting",
            aspect_ratio="16:9",
        )
    )
    assert img_resp["status"] == "SUCCESS"
    job = img_resp["render_job"]
    assert ".." not in job["sku_id"]
    assert "/" not in job["sku_id"]
    assert ".." not in job["segment_id"]
    assert "/" not in job["segment_id"]
    assert ".." not in job["asset_path"]
    assert ".." not in img_resp["hero_asset_url"]

    prev_resp = json.loads(
        render_storefront_preview(
            segment_id="../../tmp/pwn",
            featured_skus="../../SKU-0001",
            hero_headline="Atelier Exclusive",
            theme_style="Nordic_Minimal",
            discount_pct=10,
            banner_copy="Atelier Exclusive",
        )
    )
    assert prev_resp["status"] == "SUCCESS"
    assert ".." not in prev_resp["preview"]["ui_uri"]
    assert ".." not in prev_resp["preview"]["segment_id"]
    assert ".." not in prev_resp["preview"]["html_path"]
    assert ".." not in prev_resp["preview"]["ui_repo_path"]
    for p in (
        Path(job["ui_asset_path"]),
        Path(job["asset_path"]),
        Path(prev_resp["preview"]["ui_repo_path"]),
        Path(prev_resp["preview"]["html_path"]),
    ):
        if p.exists():
            p.unlink()


def test_sec03_template_html_prevents_dom_xss_in_recreate_image() -> None:
    """ui/template.html must not inject raw job.prompt_text or rawUrl via innerHTML."""
    template_path = (
        Path(__file__).resolve().parents[1]
        / "seed_packs"
        / "t02_dynamic_storefronts"
        / "ui"
        / "template.html"
    )
    html_text = template_path.read_text(encoding="utf-8")
    assert "promptBox.innerHTML" not in html_text
    assert "imgSlot.innerHTML = '<img" not in html_text


def test_sec04_script_and_injection_markers_blocked_and_callback_enforced(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Script/URI injection markers and before_tool_security_callback guardrails are enforced."""
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")
    monkeypatch.setenv("T02_LOCAL_STATE_FILE", str(tmp_path / "t02_state.json"))

    from seed_packs.t02_dynamic_storefronts.guardrails import (
        before_tool_security_callback,
    )
    from seed_packs.t02_dynamic_storefronts.mcp_server import (
        publish_storefront_layout,
        queue_visual_asset_render,
        route_merchandising_task,
        save_merchandising_memory,
        update_promo_banner,
    )

    r1 = json.loads(
        publish_storefront_layout(
            segment_id="SEG-001",
            featured_skus="SKU-0002",
            hero_headline="<script>alert(1)</script>Clean Headline",
            theme_style="Nordic_Minimal",
        )
    )
    assert r1["status"] == "REJECTED"

    r2 = json.loads(
        queue_visual_asset_render(
            sku_id="SKU-0002",
            scene_prompt="javascript:alert(1) Studio shot",
            aspect_ratio="16:9",
        )
    )
    assert r2["status"] == "REJECTED"

    r3 = json.loads(
        update_promo_banner(
            segment_id="SEG-001",
            banner_copy="<script>evil()</script>20% VIP Offer",
            discount_pct=20,
        )
    )
    assert r3["status"] == "REJECTED"

    r4 = json.loads(
        save_merchandising_memory(
            segment_id="SEG-001",
            memory_key="preference",
            memory_note="<script>steal()</script>Prefers minimalist coats",
        )
    )
    assert r4["status"] == "REJECTED"

    r5 = json.loads(
        route_merchandising_task(
            task_type="fast_copy",
            prompt_text="javascript:alert(1) Write banner copy",
            segment_id="SEG-001",
        )
    )
    assert r5["status"] == "REJECTED"

    # Verify before_tool_security_callback covers render_storefront_preview, sync_campaign_with_t01, and list args
    cb_preview = before_tool_security_callback(
        SimpleNamespace(name="render_storefront_preview"),
        {"segment_id": "SEG-001", "discount_pct": 45},
        None,
    )
    assert cb_preview is not None
    assert cb_preview["status"] == "REJECTED_SECURITY_CALLBACK"

    cb_a2a = before_tool_security_callback(
        SimpleNamespace(name="sync_campaign_with_t01"),
        {"segment_id": "SEG-001", "target_cpm_bid_eur": 40.0},
        None,
    )
    assert cb_a2a is not None
    assert cb_a2a["status"] == "REJECTED_SECURITY_CALLBACK"

    cb_list = before_tool_security_callback(
        SimpleNamespace(name="publish_storefront_layout"),
        {"segment_id": "SEG-001", "items": ["SKU-0001", "<!-- ADMIN OVERRIDE -->"]},
        None,
    )
    assert cb_list is not None
    assert cb_list["status"] == "REJECTED_SECURITY_CALLBACK"


def test_sec04_publish_endpoint_sanitizes_untrusted_hero_asset_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """POST /api/opportunities/publish must reject javascript: or external hero_asset_url."""
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")
    monkeypatch.setenv("T02_LOCAL_STATE_FILE", str(tmp_path / "t02_state.json"))

    from app.ui_server import app as ui_app

    client = TestClient(ui_app)
    resp = client.post(
        "/api/opportunities/publish",
        json={
            "segment_id": "SEG-001",
            "sku_id": "SKU-0001",
            "discount_pct": 10,
            "hero_headline": "Atelier Exclusive",
            "hero_asset_url": "javascript:alert(document.cookie)",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert not body["hero_asset_url"].startswith("javascript:")
    assert body["hero_asset_url"].startswith("/api/assets/hero/")


def test_sec05_discovery_engine_ssrf_and_url_injection_blocked() -> None:
    """build_discovery_engine_endpoint rejects arbitrary hosts/paths in app_location and app_id."""
    from seed_packs.t02_dynamic_storefronts.gemini_enterprise import (
        build_discovery_engine_endpoint,
    )

    with pytest.raises(ValueError):
        build_discovery_engine_endpoint(
            project="atelier-sandbox-123",
            app_location="evil.attacker.com/pwn#",
            app_id="ateliernova-enterprise-search",
        )

    with pytest.raises(ValueError):
        build_discovery_engine_endpoint(
            project="atelier-sandbox-123",
            app_location="eu",
            app_id="../../malicious-path",
        )


def test_sec06_untrusted_host_header_not_reflected_in_a2a_agent_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """/.well-known/agent.json must not reflect arbitrary attacker Host headers."""
    monkeypatch.delenv("MCP_SERVER_URL", raising=False)
    from cd.mcp_http_server import app as mcp_app

    client = TestClient(mcp_app)
    resp = client.get(
        "/.well-known/agent.json",
        headers={"Host": "evil.attacker.com"},
    )
    assert resp.status_code == 200
    card = resp.json()
    assert "evil.attacker.com" not in card["url"]
    assert "evil.attacker.com" not in card["mcp_sse_endpoint"]


def test_sec07_bigquery_identifier_validation_blocks_sql_injection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_resolve_project_and_dataset rejects SQL injection characters in dataset or project."""
    from seed_packs.t02_dynamic_storefronts.tools import _resolve_project_and_dataset

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "valid-project-123")
    monkeypatch.setenv("SEED_BQ_DATASET", "seed_t02` WHERE 1=1 --")
    with pytest.raises(ValueError):
        _resolve_project_and_dataset()


def test_sec08_security_headers_and_svg_csp_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """HTTP responses include nosniff/frame headers and SVG responses enforce strict CSP."""
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")
    monkeypatch.setenv("T02_LOCAL_STATE_FILE", str(tmp_path / "t02_state.json"))

    from app.ui_server import app as ui_app
    from cd.mcp_http_server import app as mcp_app

    ui_client = TestClient(ui_app)
    h_resp = ui_client.get("/api/health")
    assert h_resp.headers.get("x-content-type-options") == "nosniff"
    assert h_resp.headers.get("x-frame-options") == "SAMEORIGIN"

    svg_resp = ui_client.get("/api/assets/hero/SEG-079")
    assert svg_resp.status_code == 200
    assert svg_resp.headers.get("x-content-type-options") == "nosniff"
    assert "default-src 'none'" in svg_resp.headers.get("content-security-policy", "")
    hero_079 = (
        Path(__file__).resolve().parents[1]
        / "seed_packs"
        / "t02_dynamic_storefronts"
        / "ui"
        / "hero_SEG-079.svg"
    )
    if hero_079.exists():
        hero_079.unlink()

    mcp_client = TestClient(mcp_app)
    m_resp = mcp_client.get("/health")
    assert m_resp.headers.get("x-content-type-options") == "nosniff"

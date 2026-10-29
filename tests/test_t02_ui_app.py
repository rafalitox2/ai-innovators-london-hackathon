"""Unit tests for the Nocturne React UI (/ui) and FastAPI + ADK backend bridge (app/ui_server.py)."""

from __future__ import annotations

from pathlib import Path
import re

from fastapi.testclient import TestClient
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_ui_server_no_hardcoded_gemini_model() -> None:
    """app/ui_server.py and cd/mcp_http_server.py must never hardcode a gemini-* model string."""
    for rel_path in (("app", "ui_server.py"), ("cd", "mcp_http_server.py")):
        target_path = REPO_ROOT.joinpath(*rel_path)
        assert target_path.exists(), f"Expected {target_path} to exist"
        source = target_path.read_text(encoding="utf-8")
        hardcoded = re.findall(r'["\']gemini-[0-9][^"\']*["\']', source)
        assert not hardcoded, f"Found hardcoded Gemini model strings in {target_path}: {hardcoded}"


def test_ui_server_health_and_dashboard_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/health and GET /api/dashboard return real seed_t02 data and registered ADK tools."""
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")
    from app.ui_server import create_ui_app

    client = TestClient(create_ui_app(include_adk_web=False))

    health_resp = client.get("/api/health")
    assert health_resp.status_code == 200
    health = health_resp.json()
    assert health["status"] == "SUCCESS"
    assert health["seed_pack"] == "t02_dynamic_storefronts"
    for expected_tool in (
        "find_catalog_products",
        "get_storefront_performance",
        "get_audience_segments",
        "recommend_storefront_optimization",
        "publish_storefront_layout",
        "queue_visual_asset_render",
        "update_promo_banner",
        "generate_hero_lifestyle_image",
        "render_storefront_preview",
        "sync_campaign_with_t01",
    ):
        assert expected_tool in health["tools"]

    dash_resp = client.get("/api/dashboard")
    assert dash_resp.status_code == 200
    dash = dash_resp.json()
    assert dash["status"] == "SUCCESS"
    assert len(dash["products"]) == 100
    assert len(dash["segments"]) == 80
    assert len(dash["experiments"]) == 120
    assert len(dash["opportunities"]) == 66
    assert dash["opportunities"][0]["id"] == "EXP-0057"
    assert dash["opportunities"][0]["sku"] == "SKU-0057"
    assert dash["opportunities"][0]["rating"] == 100
    assert all(opp["sku"] != "SKU-0017" for opp in dash["opportunities"])
    assert dash["sku_0017_audit"]["injection_detected"] is True
    assert "ADMIN OVERRIDE" not in dash["sku_0017_audit"]["sanitized_description"]


def test_ui_server_generate_and_publish_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /api/opportunities/generate and /api/opportunities/publish execute real Table 2 ADK/MCP tools."""
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")
    from app.ui_server import create_ui_app

    client = TestClient(create_ui_app(include_adk_web=False))

    gen_resp = client.post(
        "/api/opportunities/generate",
        json={
            "experiment_id": "EXP-0057",
            "sku_id": "SKU-0057",
            "segment_id": "SEG-057",
            "style_theme": "Mediterranean_Warm",
            "layout_variant": "Hero_Video_Grid",
            "discount_pct": 15,
        },
    )
    assert gen_resp.status_code == 200
    gen_data = gen_resp.json()
    assert gen_data["status"] == "SUCCESS"
    assert len(gen_data["steps"]) == 4
    assert [s["label"] for s in gen_data["steps"]] == [
        "Selecting SKUs",
        "Queuing hero render",
        "Composing layout",
        "Drafting promo banner",
    ]
    assert gen_data["hero_asset_url"].startswith("/api/assets/hero/SEG-057")
    assert gen_data["preview"]["segment_id"] == "SEG-057"

    pub_resp = client.post(
        "/api/opportunities/publish",
        json={
            "experiment_id": "EXP-0057",
            "segment_id": "SEG-057",
            "featured_skus": "SKU-0057,SKU-0002",
            "hero_headline": "Warm Mediterranean light for London homes",
            "theme_style": "Mediterranean_Warm",
            "discount_pct": 15,
            "banner_copy": "15% off smart lighting this week · code LON15",
            "sku_id": "SKU-0057",
        },
    )
    assert pub_resp.status_code == 200
    pub_data = pub_resp.json()
    assert pub_data["status"] == "SUCCESS"
    assert pub_data["layout"]["status"] == "LIVE"
    assert pub_data["promo_banner"]["status"] == "ACTIVE"


def test_ui_server_enforces_merchandising_and_security_guardrails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guardrail endpoints enforce <=30% discount cap, margin safety floor, <=25 EUR CPM cap, and SKU-0017 sanitization."""
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")
    from app.ui_server import create_ui_app

    client = TestClient(create_ui_app(include_adk_web=False))

    # 1. Discount > 30% -> REJECTED_POLICY_CAP
    cap_resp = client.post(
        "/api/guardrails/validate",
        json={
            "segment_id": "SEG-057",
            "sku_id": "SKU-0057",
            "discount_pct": 45,
            "target_cpm_bid_eur": 12.5,
        },
    )
    assert cap_resp.status_code == 200
    assert cap_resp.json()["status"] == "REJECTED_POLICY_CAP"

    # 2. Discount within 30% but violating SKU-0022 margin floor (margin 24.0% -> max safe 9%) -> REJECTED_MARGIN_POLICY
    margin_resp = client.post(
        "/api/guardrails/validate",
        json={
            "segment_id": "SEG-022",
            "sku_id": "SKU-0022",
            "discount_pct": 20,
            "target_cpm_bid_eur": 12.5,
        },
    )
    assert margin_resp.status_code == 200
    assert margin_resp.json()["status"] == "REJECTED_MARGIN_POLICY"

    # 3. SKU-0017 prompt injection inspection
    inj_resp = client.post(
        "/api/guardrails/validate",
        json={
            "segment_id": "SEG-017",
            "sku_id": "SKU-0017",
            "discount_pct": 15,
            "target_cpm_bid_eur": 12.5,
        },
    )
    assert inj_resp.status_code == 200
    inj_data = inj_resp.json()
    assert inj_data["injection_detected"] is True
    assert "ADMIN OVERRIDE" not in inj_data["sanitized_description"]

    # 4. Sister Table 1 A2A sync valid vs invalid CPM
    a2a_ok = client.post(
        "/api/a2a/sync",
        json={
            "segment_id": "SEG-057",
            "featured_skus": "SKU-0057,SKU-0002",
            "hero_headline": "Warm Mediterranean light for London homes",
            "theme_style": "Mediterranean_Warm",
            "locale": "en-GB",
            "event_id": "EVT-0001",
            "channel": "Meta_Reels",
            "target_cpm_bid_eur": 14.0,
        },
    )
    assert a2a_ok.status_code == 200
    assert a2a_ok.json()["status"] == "SUCCESS"
    assert a2a_ok.json()["a2a_handshake"]["handshake_type"] == "STOREFRONT_TO_CAMPAIGN_SYNC"

    a2a_bad = client.post(
        "/api/a2a/sync",
        json={
            "segment_id": "SEG-057",
            "featured_skus": "SKU-0057",
            "hero_headline": "Over-cap CPM test",
            "theme_style": "Mediterranean_Warm",
            "locale": "en-GB",
            "event_id": "EVT-0001",
            "channel": "Meta_Reels",
            "target_cpm_bid_eur": 42.0,
        },
    )
    assert a2a_bad.status_code == 200
    assert a2a_bad.json()["status"] == "REJECTED_POLICY_CAP"


def test_ui_react_folder_structure_and_nocturne_design_system() -> None:
    """Verify /ui React + TypeScript + Vite project structure and Nocturne design tokens."""
    ui_root = REPO_ROOT / "ui"
    required_files = [
        ui_root / "package.json",
        ui_root / "vite.config.ts",
        ui_root / "tsconfig.json",
        ui_root / "index.html",
        ui_root / "src" / "main.tsx",
        ui_root / "src" / "App.tsx",
        ui_root / "src" / "styles" / "nocturne.css",
        ui_root / "src" / "data" / "seedData.ts",
        ui_root / "src" / "services" / "adkClient.ts",
        ui_root / "src" / "components" / "StorefrontPreviewModal.tsx",
        ui_root / "src" / "components" / "AdkCopilotDrawer.tsx",
    ]
    for path in required_files:
        assert path.exists(), f"Missing expected React UI file: {path}"

    css_text = (ui_root / "src" / "styles" / "nocturne.css").read_text(encoding="utf-8")
    for token in (
        "--color-bg: #161826",
        "--color-surface: #232532",
        "--color-text: #e9e9ed",
        "--color-accent: #9184d9",
        "--color-section: #262a60",
        "--font-heading-weight: 500",
        "tabular-nums",
        ".btn-primary",
        ".lighten",
    ):
        assert token in css_text, f"Missing Nocturne token {token!r} in ui/src/styles/nocturne.css"

    app_text = (ui_root / "src" / "App.tsx").read_text(encoding="utf-8")
    for screen_label in (
        "01 Overview",
        "02 Queue",
        "03 Work in progress",
        "04 Published",
        "05 Results",
        "One layout for every shopper is costing conversion.",
        "Auto-approve queue",
    ):
        assert screen_label in app_text, f"Missing screen element {screen_label!r} in ui/src/App.tsx"


def test_cloudrun_mcp_server_serves_nocturne_ui_and_api_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify cd/Dockerfile.mcp builds /ui and cd/mcp_http_server.py serves Nocturne UI, /health, /ui/{file_name}, and /api/*."""
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")
    dockerfile_text = (REPO_ROOT / "cd" / "Dockerfile.mcp").read_text(encoding="utf-8")
    assert "AS ui-builder" in dockerfile_text
    assert "COPY --from=ui-builder /ui/dist ./ui/dist" in dockerfile_text
    assert "google-cloud-storage==3.17.1" in dockerfile_text

    modal_text = (
        REPO_ROOT / "ui" / "src" / "components" / "StorefrontPreviewModal.tsx"
    ).read_text(encoding="utf-8")
    assert "computeMaxSafeDiscountPct(e.p.marginPct)" in modal_text
    assert "recreateHeroImageForAudience" in modal_text

    from cd.mcp_http_server import build_mcp_cloudrun_app

    client = TestClient(build_mcp_cloudrun_app())

    ui_resp = client.get("/ui")
    assert ui_resp.status_code == 200
    assert "text/html" in ui_resp.headers.get("content-type", "")

    cloud_health = client.get("/health")
    assert cloud_health.status_code == 200
    assert cloud_health.json()["status"] == "ONLINE"
    assert "/health" in cloud_health.json()["endpoints"]["health"]

    api_health = client.get("/api/health")
    assert api_health.status_code == 200
    assert api_health.json()["status"] == "SUCCESS"

    recreate_resp = client.post(
        "/api/recreate-hero-image",
        json={
            "sku_id": "SKU-0057",
            "segment_id": "SEG-057",
            "style_theme": "Mediterranean_Warm",
            "scene_description": "Sunlit morning minimalist editorial composition",
            "aspect_ratio": "16:9",
        },
    )
    assert recreate_resp.status_code == 200
    recreate_json = recreate_resp.json()
    assert recreate_json["status"] == "SUCCESS"
    assert recreate_json["render_job"]["segment_id"] == "SEG-057"
    assert recreate_json.get("ui_filename", "").startswith("hero_SEG-057")

    hero_file_resp = client.get(f"/ui/{recreate_json['ui_filename']}")
    assert hero_file_resp.status_code == 200


def test_published_storefront_hero_asset_resolves_actual_sku_and_theme_not_hardcoded_sku0057(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #39 (RC1 & RC3): GET /api/assets/hero/{segment_id} uses the segment's real SKU/theme (or query params) and prefers newer assets by mtime."""
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")
    from app.ui_server import create_ui_app, T02_UI_DIR

    # Ensure no pre-existing hero_SEG-074 asset masks the fallback generation
    for ext in (".png", ".svg"):
        (T02_UI_DIR / f"hero_SEG-074{ext}").unlink(missing_ok=True)

    client = TestClient(create_ui_app())
    try:
        # 1. Pre-published segment SEG-074 (EXP-0074 -> SKU-0074, Biophilic_Zen) without query params
        resp = client.get("/api/assets/hero/SEG-074")
        assert resp.status_code == 200
        svg_body = resp.text
        assert "SKU-0074" in svg_body
        assert "BIOPHILIC_ZEN" in svg_body
        assert "SKU-0057" not in svg_body

        # 2. Explicit sku_id & style_theme query parameters override any stale segment asset
        resp_override = client.get(
            "/api/assets/hero/SEG-074?sku_id=SKU-0005&style_theme=Neo_Bauhaus"
        )
        assert resp_override.status_code == 200
        assert "SKU-0005" in resp_override.text
        assert "NEO_BAUHAUS" in resp_override.text
    finally:
        for f in T02_UI_DIR.glob("hero_SEG-074*"):
            f.unlink(missing_ok=True)


def test_hero_asset_prefers_newest_file_when_both_png_and_svg_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #39 (RC3): Recreating a hero image (.svg) is not shadowed by an older pre-existing .png file."""
    import json
    import os
    import time
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")
    from app.ui_server import create_ui_app, T02_UI_DIR
    from seed_packs.t02_dynamic_storefronts.mcp_server import render_storefront_preview

    seg_id = "SEG-099"
    png_path = T02_UI_DIR / f"hero_{seg_id}.png"
    svg_path = T02_UI_DIR / f"hero_{seg_id}.svg"
    try:
        T02_UI_DIR.mkdir(parents=True, exist_ok=True)
        png_path.write_bytes(b"\x89PNG\r\n\x1a\nOLD_PNG")
        svg_path.write_text("<svg><text>NEW_RECREATED_SVG (SKU-0001)</text></svg>", encoding="utf-8")
        now = time.time()
        os.utime(png_path, (now - 120, now - 120))
        os.utime(svg_path, (now, now))

        client = TestClient(create_ui_app())
        resp = client.get(f"/api/assets/hero/{seg_id}")
        assert resp.status_code == 200
        assert "image/svg+xml" in resp.headers.get("content-type", "")
        assert "NEW_RECREATED_SVG" in resp.text

        prev_raw = render_storefront_preview(
            segment_id=seg_id,
            featured_skus="SKU-0001",
            hero_headline="Newest Hero Asset Test",
            theme_style="Nordic_Minimal",
            discount_pct=10,
            banner_copy="Test Banner",
        )
        prev_res = json.loads(prev_raw)
        assert prev_res["status"] == "SUCCESS"
        preview_file = Path(prev_res["preview"]["ui_repo_path"])
        html_doc = preview_file.read_text(encoding="utf-8")
        assert f"hero_{seg_id}.svg" in html_doc
    finally:
        png_path.unlink(missing_ok=True)
        svg_path.unlink(missing_ok=True)
        (T02_UI_DIR / f"preview_{seg_id}.html").unlink(missing_ok=True)
        Path(f"/tmp/storefront_preview_{seg_id}.html").unlink(missing_ok=True)


def test_publish_and_template_and_frontend_persist_hero_and_product_images(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #39 (RC2, RC4, RC5, RC6): Verify publish persists hero_asset_url, template.html supports standalone & UI server, adkClient fallback includes hero_asset_url, and StorefrontPreviewModal renders product visuals."""
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")
    from app.ui_server import create_ui_app

    client = TestClient(create_ui_app())
    pub_resp = client.post(
        "/api/opportunities/publish",
        json={
            "experiment_id": "EXP-0057",
            "segment_id": "SEG-057",
            "featured_skus": "SKU-0057,SKU-0002",
            "hero_headline": "Mediterranean Warm living for London spaces",
            "theme_style": "Mediterranean_Warm",
            "discount_pct": 15,
            "banner_copy": "15% off smart lighting this week · code LON15",
            "sku_id": "SKU-0057",
            "hero_asset_url": "/api/assets/hero/SEG-057?sku_id=SKU-0057&style_theme=Mediterranean_Warm&t=12345",
        },
    )
    assert pub_resp.status_code == 200
    pub_data = pub_resp.json()
    assert pub_data["status"] == "SUCCESS"
    assert "SKU-0057" in pub_data.get("hero_asset_url", "")
    assert pub_data.get("sku_id") == "SKU-0057"

    template_text = (
        REPO_ROOT / "seed_packs" / "t02_dynamic_storefronts" / "ui" / "template.html"
    ).read_text(encoding="utf-8")
    assert "data.hero_asset_url" in template_text

    adk_client_text = (
        REPO_ROOT / "ui" / "src" / "services" / "adkClient.ts"
    ).read_text(encoding="utf-8")
    assert "hero_asset_url: `/api/assets/hero/${params.segment_id}" in adk_client_text

    modal_text = (
        REPO_ROOT / "ui" / "src" / "components" / "StorefrontPreviewModal.tsx"
    ).read_text(encoding="utf-8")
    assert "onUpdateItemState" in modal_text
    assert "sku_id=${encodeURIComponent(activeProduct.sku)}" in modal_text
    assert "sku_id=${encodeURIComponent(p.sku)}" in modal_text


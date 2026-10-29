"""Unit tests for Table T02 Phase 3 (Tribe A2A Handshake with Table 1 + Editable UI Template)."""

from __future__ import annotations

import json
from pathlib import Path
import pytest


def test_t02_sync_campaign_with_t01_creates_a2a_handshake(monkeypatch: pytest.MonkeyPatch) -> None:
    """sync_campaign_with_t01 stages a localized variant and places a compliant bid on Table 1."""
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")
    from seed_packs.t02_dynamic_storefronts.mcp_server import sync_campaign_with_t01

    raw = sync_campaign_with_t01(
        segment_id="SEG-001",
        featured_skus="SKU-0001,SKU-0006",
        hero_headline="Nordic Comfort for London Living",
        theme_style="Nordic_Minimal",
        locale="en-GB",
        event_id="EVT-0001",
        channel="Meta_Reels",
        target_cpm_bid_eur=12.5,
    )
    res = json.loads(raw)
    assert res["status"] == "SUCCESS"
    handshake = res["a2a_handshake"]
    assert handshake["sender_agent"] == "expedition_t02_dynamic_storefronts"
    assert handshake["recipient_agent"] == "expedition_t01_campaign_orchestrator"
    assert handshake["t01_response"]["variant"]["status"] == "STAGED_FOR_SERVING"
    assert handshake["t01_response"]["bid"]["status"] == "ACTIVE_BID"


def test_t02_sync_campaign_with_t01_enforces_cpm_guardrail(monkeypatch: pytest.MonkeyPatch) -> None:
    """sync_campaign_with_t01 rejects CPM bids above Table 1's 25.00 EUR cap."""
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")
    from seed_packs.t02_dynamic_storefronts.mcp_server import sync_campaign_with_t01

    raw = sync_campaign_with_t01(
        segment_id="SEG-001",
        featured_skus="SKU-0001",
        hero_headline="Illegal CPM Test",
        theme_style="Nordic_Minimal",
        locale="en-GB",
        event_id="EVT-0001",
        channel="Meta_Reels",
        target_cpm_bid_eur=99.0,
    )
    res = json.loads(raw)
    assert res["status"] == "REJECTED_POLICY_CAP"


def test_t02_render_storefront_preview_writes_to_ui_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    """render_storefront_preview uses ui/template.html and writes preview_<segment_id>.html in ui/."""
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")
    from seed_packs.t02_dynamic_storefronts.mcp_server import render_storefront_preview

    raw = render_storefront_preview(
        segment_id="SEG-001",
        featured_skus="SKU-0001,SKU-0006",
        hero_headline="Nordic Comfort for London Living",
        theme_style="Nordic_Minimal",
        discount_pct=15,
        banner_copy="London Autumn Edit",
    )
    res = json.loads(raw)
    assert res["status"] == "SUCCESS"
    ui_file = Path(res["preview"]["ui_repo_path"])
    assert ui_file.exists()
    assert "Dynamic Storefront Engine" in ui_file.read_text(encoding="utf-8")


def test_mcp_stdio_toolset_uses_30s_timeout_for_multimodal_tools() -> None:
    """_build_mcp_stdio_toolset sets timeout >= 30.0s so live image generation never times out at 5s."""
    from app.loader import _build_mcp_stdio_toolset

    toolset = _build_mcp_stdio_toolset("seed_packs.t02_dynamic_storefronts.mcp_server")
    assert toolset is not None
    conn_params = getattr(toolset, "_connection_params", None)
    assert conn_params is not None
    assert float(getattr(conn_params, "timeout", 0.0)) >= 30.0


def test_generate_hero_and_render_preview_embeds_hero_visual_in_ui(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """generate_hero_lifestyle_image syncs hero asset to ui/ and render_storefront_preview embeds it."""
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")
    from seed_packs.t02_dynamic_storefronts.mcp_server import (
        generate_hero_lifestyle_image,
        render_storefront_preview,
    )

    hero_raw = generate_hero_lifestyle_image(
        sku_id="SKU-0066",
        segment_id="SEG-001",
        style_theme="Nordic_Minimal",
        scene_description="Sunlit London flat with oak desk",
        aspect_ratio="16:9",
    )
    hero_res = json.loads(hero_raw)
    assert hero_res["status"] == "SUCCESS"
    ui_asset = Path(hero_res["render_job"]["ui_asset_path"])
    assert ui_asset.exists()

    prev_raw = render_storefront_preview(
        segment_id="SEG-001",
        featured_skus="SKU-0066,SKU-0001",
        hero_headline="Nordic Comfort for London Living",
        theme_style="Nordic_Minimal",
        discount_pct=15,
        banner_copy="Autumn Design Week — 15% Off Modular Living",
    )
    prev_res = json.loads(prev_raw)
    assert prev_res["status"] == "SUCCESS"
    html_doc = Path(prev_res["preview"]["ui_repo_path"]).read_text(encoding="utf-8")
    assert "hero_SEG-001." in html_doc
    if ui_asset.suffix == ".svg":
        ui_asset.unlink(missing_ok=True)


def test_t02_nocturne_ui_mockup_and_template_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Nocturne UI design handoff mockup files and Nocturne tokens in template.html."""
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")
    from seed_packs.t02_dynamic_storefronts.mcp_server import render_storefront_preview

    ui_dir = Path(__file__).resolve().parent.parent / "seed_packs" / "t02_dynamic_storefronts" / "ui"
    handoff_dir = ui_dir / "design_handoff_dynamic_storefronts"

    assert (handoff_dir / "README.md").exists()
    assert (handoff_dir / "design-system" / "styles.css").exists()
    assert (handoff_dir / "design-system" / "nocturne-guide.md").exists()
    assert (handoff_dir / "prototype" / "Dynamic Storefronts.dc.html").exists()

    raw = render_storefront_preview(
        segment_id="SEG-001",
        featured_skus="SKU-0001,SKU-0006",
        hero_headline="Nordic Comfort for London Living",
        theme_style="Nordic_Minimal",
        discount_pct=15,
        banner_copy="London Autumn Edit",
    )
    res = json.loads(raw)
    assert res["status"] == "SUCCESS"
    rendered_html = Path(res["preview"]["ui_repo_path"]).read_text(encoding="utf-8")
    for nocturne_token in ("--color-bg: #161826", "--color-surface: #232532", "--color-accent: #9184d9"):
        assert nocturne_token in rendered_html


def test_t02_nocturne_mockup_uses_real_catalog_and_segment_data() -> None:
    """Verify the Nocturne prototype and handoff data files reference real Table 2 SKUs, segments, and experiments."""
    handoff_dir = (
        Path(__file__).resolve().parent.parent
        / "seed_packs"
        / "t02_dynamic_storefronts"
        / "ui"
        / "design_handoff_dynamic_storefronts"
    )
    proto_html = (handoff_dir / "prototype" / "Dynamic Storefronts.dc.html").read_text(encoding="utf-8")

    for real_token in (
        "SKU-0001",
        "Atelier Nordic Modular Sofas #1",
        "SKU-0057",
        "Atelier Mediterranean Smart Lighting #57",
        "SKU-0100",
        "Atelier Neo Ceramic Decor #100",
        "SEG-001",
        "UK_London_Nordic_Minimal_Mobile",
        "SEG-057",
        "UK_London_Mediterranean_Warm_Mobile",
        "EXP-0001",
        "EXP-0057",
        "EXP-0120",
        "Hero_Video_Grid",
        "Carousel_Lookbook",
        "Minimal_Split_Card",
        "Interactive_Room_Bundle",
    ):
        assert real_token in proto_html, f"Expected real Table 2 token {real_token!r} in prototype HTML"

    assert "ANV-" not in proto_html
    assert "ADMIN OVERRIDE" not in proto_html

    products_csv = (handoff_dir / "data" / "products.csv").read_text(encoding="utf-8")
    segments_csv = (handoff_dir / "data" / "segments.csv").read_text(encoding="utf-8")
    experiments_csv = (handoff_dir / "data" / "experiments.csv").read_text(encoding="utf-8")
    opportunities_csv = (handoff_dir / "data" / "opportunities.csv").read_text(encoding="utf-8")

    assert "SKU-0001,Atelier Nordic Modular Sofas #1" in products_csv
    assert "ANV-" not in products_csv
    assert "SEG-001" in segments_csv and "UK_London_Nordic_Minimal_Mobile" in segments_csv
    assert "EXP-0001" in experiments_csv and "SKU-0001" in experiments_csv
    assert "EXP-0057" in opportunities_csv and "Atelier Mediterranean Smart Lighting #57" in opportunities_csv
    assert "SKU-0017" not in opportunities_csv



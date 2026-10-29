"""Unit tests for Table T02 Phase 2 tools (BigQuery multi-table join, Multimodal hero image, MCP UI preview)."""

from __future__ import annotations

import json
from pathlib import Path
import pytest


def test_t02_recommend_storefront_optimization_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """recommend_storefront_optimization joins segments, experiments, and catalog SKUs."""
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")
    from seed_packs.t02_dynamic_storefronts.tools import recommend_storefront_optimization

    raw = recommend_storefront_optimization(region="ES_Madrid", min_bounce_rate_pct=55.0, min_stock=10)
    res = json.loads(raw)
    assert res["status"] == "SUCCESS"
    assert res["count"] >= 1
    first = res["recommendations"][0]
    assert first["region"] == "ES_Madrid"
    assert float(first["bounce_rate_pct"]) >= 55.0
    assert "recommended_sku_id" in first
    assert float(first["recommended_margin_pct"]) > 0
    assert 0 <= int(first["max_safe_discount_pct"]) <= 30


def test_t02_generate_hero_lifestyle_image_reads_env_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """generate_hero_lifestyle_image uses GEMINI_IMAGE_MODEL from env and never raises."""
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")
    monkeypatch.setenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
    from seed_packs.t02_dynamic_storefronts.mcp_server import generate_hero_lifestyle_image

    raw = generate_hero_lifestyle_image(
        sku_id="SKU-0006",
        segment_id="SEG-001",
        style_theme="Nordic_Minimal",
        scene_description="Sunlit London flat with minimalist oak flooring",
        aspect_ratio="16:9",
    )
    res = json.loads(raw)
    assert res["status"] == "SUCCESS"
    job = res["render_job"]
    assert job["sku_id"] == "SKU-0006"
    assert job["segment_id"] == "SEG-001"
    assert job["image_model"] == "gemini-3.1-flash-image"
    assert Path(job["asset_path"]).exists()


def test_t02_render_storefront_preview_creates_ui_card_and_enforces_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """render_storefront_preview generates an MCP UI resource HTML card and enforces <=30% cap."""
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")
    from seed_packs.t02_dynamic_storefronts.mcp_server import render_storefront_preview

    ok_raw = render_storefront_preview(
        segment_id="SEG-001",
        featured_skus="SKU-0001,SKU-0006",
        hero_headline="Nordic Comfort for London Living",
        theme_style="Nordic_Minimal",
        discount_pct=15,
        banner_copy="Autumn Design Week — 15% Off Modular Living",
    )
    ok = json.loads(ok_raw)
    assert ok["status"] == "SUCCESS"
    preview = ok["preview"]
    assert preview["ui_uri"] == "ui://storefront-preview/SEG-001"
    assert Path(preview["html_path"]).exists()
    html_content = Path(preview["html_path"]).read_text(encoding="utf-8")
    assert "Nordic Comfort for London Living" in html_content
    assert "SKU-0001" in html_content

    rejected_raw = render_storefront_preview(
        segment_id="SEG-001",
        featured_skus="SKU-0001",
        hero_headline="Illegal Discount Test",
        theme_style="Nordic_Minimal",
        discount_pct=95,
        banner_copy="95% Off Everything",
    )
    rejected = json.loads(rejected_raw)
    assert rejected["status"] == "REJECTED_POLICY_CAP"

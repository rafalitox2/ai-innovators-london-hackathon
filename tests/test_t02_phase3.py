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

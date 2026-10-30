"""Tribe A2A campaign synchronization service between Table 2 and Table 1."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from seed_packs.t02_dynamic_storefronts.guardrails import (
    contains_injection_marker,
    quarantine_action_args,
    sanitize_description,
    scan_args_for_injection,
    validate_policy_number,
)
from seed_packs.t02_dynamic_storefronts.mcp.state_store import McpStateStore


class TribeA2ASyncService:
    """Orchestrates cross-agent A2A synchronization between Storefront (T02) and Campaign (T01)."""

    def __init__(self, state_store: McpStateStore) -> None:
        self.state_store = state_store

    def sync_campaign_with_t01(
        self,
        segment_id: str,
        featured_skus: str = "",
        hero_headline: str = "",
        theme_style: str = "Nordic_Minimal",
        locale: str = "en-GB",
        event_id: str = "EVT-0001",
        channel: str = "Meta_Reels",
        target_cpm_bid_eur: float = 12.5,
        layout_variant: str = "",
        featured_sku: str = "",
        campaign_channel: str = "",
    ) -> str:
        """Execute Tribe A2A Handshake with Sister Table 1 (t01_campaign_orchestrator)."""
        args = {k: v for k, v in locals().items() if k != "self"}
        flagged_key = scan_args_for_injection(args)
        if flagged_key is not None:
            return json.dumps({"status": "REJECTED", "error": f"Untrusted instruction marker in {flagged_key}."})
        rejection = quarantine_action_args(args)
        if rejection is not None:
            return json.dumps(rejection)
        try:
            cpm = validate_policy_number(target_cpm_bid_eur, cap=25.0, positive=True)
            if cpm is None:
                return json.dumps({
                    "status": "REJECTED_POLICY_CAP",
                    "error": "target_cpm_bid_eur must be finite and greater than 0, at most 25.00 EUR; booleans are not allowed.",
                })

            sku_str = featured_sku or featured_skus or ""
            skus_clean = [s.strip() for s in sku_str.split(",") if s.strip()]

            # Enforce SKU-0017 quarantine and prompt injection check
            for sku in skus_clean:
                if sku.upper() == "SKU-0017" or contains_injection_marker(sku):
                    return json.dumps({
                        "status": "REJECTED_UNTRUSTED_SKU",
                        "error": "sync_campaign_with_t01 rejected: featured SKU contains untrusted catalog entry SKU-0017.",
                    })

            headline_raw = hero_headline or (
                f"AtelierNova {layout_variant or theme_style} Collection"
            )
            headline_clean = sanitize_description(headline_raw)
            if contains_injection_marker(headline_clean):
                return json.dumps({
                    "status": "REJECTED",
                    "error": "sync_campaign_with_t01 rejected: hero_headline contains an untrusted prompt-injection marker.",
                })

            seg_clean = (segment_id or "SEG-001").strip()
            theme_clean = (theme_style or "Nordic_Minimal").strip()
            loc_clean = (locale or "en-GB").strip()
            evt_clean = (event_id or "EVT-0001").strip()
            ch_clean = (campaign_channel or channel or "Meta_Reels").strip()

            from seed_packs.t01_campaign_orchestrator.mcp_server import (
                create_localized_variant,
                place_ad_bid,
            )

            visual_prompt = (
                f"AtelierNova x PulseStage cross-promo ({theme_clean}) featuring {', '.join(skus_clean)} "
                f"for segment {seg_clean}"
            )
            var_resp = json.loads(
                create_localized_variant(
                    event_id=evt_clean,
                    locale=loc_clean,
                    headline=headline_clean,
                    visual_prompt=visual_prompt,
                    cta_text=f"Shop {theme_clean} Edit",
                )
            )
            variant_obj = var_resp.get("variant", {})
            variant_id = str(variant_obj.get("variant_id", "VAR-LOC-2001"))

            bid_resp = json.loads(
                place_ad_bid(
                    variant_id=variant_id,
                    channel=ch_clean,
                    new_cpm_bid_eur=cpm,
                    daily_budget_eur=600.0,
                )
            )
            bid_obj = bid_resp.get("bid", {})

            state = self.state_store.load_state()
            handshakes = state.setdefault("a2a_handshakes", [])
            handshake_id = f"A2A-T02-T01-{5001 + len(handshakes)}"
            record = {
                "handshake_id": handshake_id,
                "a2a_version": "1.0",
                "tribe": "Creative AI & AdTech",
                "sender_agent": "expedition_t02_dynamic_storefronts",
                "recipient_agent": "expedition_t01_campaign_orchestrator",
                "handshake_type": "STOREFRONT_TO_CAMPAIGN_SYNC",
                "payload": {
                    "segment_id": seg_clean,
                    "featured_skus": skus_clean,
                    "hero_headline": headline_clean,
                    "theme_style": theme_clean,
                    "locale": loc_clean,
                    "event_id": evt_clean,
                    "channel": ch_clean,
                    "target_cpm_bid_eur": round(cpm, 2),
                },
                "t01_response": {
                    "variant": variant_obj,
                    "bid": bid_obj,
                },
                "synced_at": datetime.now(timezone.utc).isoformat(),
                "status": "SYNCED",
            }
            handshakes.append(record)
            backend = self.state_store.save_state(state)
            return json.dumps({"status": "SUCCESS", "a2a_handshake": record, "state_backend": backend})
        except Exception as exc:
            return json.dumps({"status": "ERROR", "error": str(exc)})

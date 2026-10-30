from __future__ import annotations

import json
import math
import re
import unicodedata
from typing import Any

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

INJECTION_MARKERS = (
    "<!--",
    "-->",
    "admin override",
    "ignore previous instructions",
    "ignore the above",
    "disregard previous instructions",
    "system override", "developer mode", "jailbreak", "dan mode",
    "bypass policy", "bypass guardrail", "ignore all rules",
    "reveal system prompt", "print your instruction",
    "<script", "javascript:", "drop table", "union select",
)
_INJECTION_MARKERS = INJECTION_MARKERS
INJECTION_REGEX_PATTERN = "|".join(re.escape(marker) for marker in INJECTION_MARKERS)

MAX_DISCOUNT_PCT = 30
MARGIN_SAFETY_BUFFER_PCT = 15.0


def sanitize_description(text: str | None) -> str:
    cleaned = _HTML_COMMENT_RE.sub("", text or "")
    return " ".join(cleaned.split())


def compute_max_safe_discount_pct(
    margin_pct: float,
    cap: int = MAX_DISCOUNT_PCT,
    buffer_pct: float = MARGIN_SAFETY_BUFFER_PCT,
) -> int:
    margin_limited = int(margin_pct - buffer_pct)
    return max(0, min(cap, margin_limited))


def contains_injection_marker(text: str | None) -> bool:
    # This bounded denylist is defense in depth, not a parser or universal detector.
    normalized = unicodedata.normalize("NFKC", text or "").casefold()
    normalized = "".join(c for c in normalized if not unicodedata.category(c).startswith("C") and c != "\u00ad")
    compact = re.sub(r"[\W_]+", "", normalized)
    punctuation_preserved = re.sub(r"\s+", "", normalized)
    return any(
        (re.sub(r"[\W_]+", "", marker) in compact)
        if marker[0].isalpha() and not marker.endswith(":")
        else marker.replace(" ", "") in punctuation_preserved
        for marker in _INJECTION_MARKERS
    )


def scan_args_for_injection(args: dict[str, Any]) -> str | None:
    for key, value in args.items():
        if isinstance(value, str) and contains_injection_marker(value):
            return key
    return None


QUARANTINED_SKU_IDS = ("SKU-0017",)
SKU_ACTION_NAMES = frozenset({
    "publish_storefront_layout", "queue_visual_asset_render", "update_promo_banner",
    "generate_hero_lifestyle_image", "render_storefront_preview", "sync_campaign_with_t01",
})


def is_quarantined_product(row: dict[str, Any]) -> bool:
    """Inspect raw catalog fields before any lossy projection or sanitation."""
    sku = str(row.get("sku_id", row.get("recommended_sku_id", ""))).strip().upper()
    if sku in QUARANTINED_SKU_IDS or scan_args_for_injection(row) is not None:
        return True
    # BQ recommendation joins carry the complete raw product, not just display fields.
    raw = row.get("catalog_security_record")
    if raw is not None:
        try:
            record = json.loads(raw)
            return not isinstance(record, dict) or is_quarantined_product(record)
        except (TypeError, ValueError):
            return True
    return False


def quarantine_action_args(args: dict[str, Any]) -> dict[str, Any] | None:
    """Use the same bundled catalog as actions; no remote reads in the callback."""
    from seed_packs.t02_dynamic_storefronts.mcp_server import _read_csv_rows

    skus = {
        sku.strip().upper()
        for key in ("sku_id", "featured_skus")
        for sku in str(args.get(key) or "").split(",") if sku.strip()
    }
    blocked = skus.intersection(QUARANTINED_SKU_IDS)
    if skus and not blocked:
        try:
            blocked.update(
                str(row.get("sku_id", "")).strip().upper()
                for row in _read_csv_rows("products_catalog")
                if str(row.get("sku_id", "")).strip().upper() in skus
                and is_quarantined_product(row)
            )
        except Exception:
            return {"status": "REJECTED_QUARANTINED_SKU", "error": "Catalog safety check unavailable."}
    if blocked:
        return {"status": "REJECTED_QUARANTINED_SKU", "error": "Catalog SKU is quarantined.", "sku_ids": sorted(blocked)}
    return None


def validate_policy_number(value: Any, *, cap: float, positive: bool = False, integral: bool = False) -> float | None:
    """Coerce scalar numeric strings only after excluding booleans and nonfinite values."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number < 0 or number > cap:
        return None
    if (positive and number == 0) or (integral and not number.is_integer()):
        return None
    return number


def before_tool_security_callback(
    tool: Any,
    args: dict[str, Any],
    tool_context: Any,
) -> dict[str, Any] | None:
    flagged_key = scan_args_for_injection(args)
    if flagged_key is not None:
        return {
            "status": "REJECTED_SECURITY_CALLBACK",
            "error": (
                f"{tool.name} blocked before execution: argument '{flagged_key}' contains an "
                "embedded instruction marker from untrusted data."
            ),
        }

    if tool.name in SKU_ACTION_NAMES:
        rejection = quarantine_action_args(args)
        if rejection is not None:
            return rejection

    if tool.name in {"update_promo_banner", "render_storefront_preview", "sync_campaign_with_t01"}:
        is_cpm = tool.name == "sync_campaign_with_t01"
        key = "target_cpm_bid_eur" if is_cpm else "discount_pct"
        # Omitted optional values use the function's valid defaults; explicit None is invalid.
        if key in args and validate_policy_number(
            args[key], cap=25.0 if is_cpm else MAX_DISCOUNT_PCT,
            positive=is_cpm, integral=not is_cpm,
        ) is None:
            return {
                "status": "REJECTED_SECURITY_CALLBACK",
                "error": f"{tool.name} blocked before execution: {key} violates numeric policy.",
            }

    return None

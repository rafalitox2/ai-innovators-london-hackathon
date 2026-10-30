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
        if isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, str) and contains_injection_marker(item):
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
                and (
                    is_quarantined_product(row)
                    or int(float(row.get("stock_qty") or 0)) <= 0
                )
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


def validate_sku_margin_args(args: dict[str, Any]) -> str | None:
    """Validate that discount_pct does not violate any target SKU's 15% post-discount margin safety floor."""
    from seed_packs.t02_dynamic_storefronts.mcp_server import _read_csv_rows

    if not isinstance(args, dict) or "discount_pct" not in args:
        return None
    disc_num = validate_policy_number(args["discount_pct"], cap=MAX_DISCOUNT_PCT, integral=True)
    if disc_num is None or disc_num <= 0:
        return None
    disc = int(disc_num)
    skus = [
        sku.strip().upper()
        for key in ("sku_id", "featured_skus")
        for sku in str(args.get(key) or "").split(",")
        if sku.strip()
    ]
    if not skus:
        return None
    try:
        catalog = {
            str(row.get("sku_id", "")).strip().upper(): row
            for row in _read_csv_rows("products_catalog")
        }
    except Exception:
        return "Catalog margin safety check unavailable."

    for sku in skus:
        row = catalog.get(sku)
        if not row:
            continue
        try:
            margin_pct = float(row.get("margin_pct") or 0.0)
        except (TypeError, ValueError):
            margin_pct = 0.0
        max_safe_disc = compute_max_safe_discount_pct(margin_pct)
        if disc > max_safe_disc:
            return (
                f"discount_pct={disc}% undercuts {sku}'s gross margin ({margin_pct}%); "
                f"max safe discount with {MARGIN_SAFETY_BUFFER_PCT}pt buffer is {max_safe_disc}% "
                f"(margin_pct={margin_pct}%, max_safe_discount_pct={max_safe_disc}%, requested_discount_pct={disc}%)."
            )
    return None


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

    if tool.name in {"update_promo_banner", "render_storefront_preview"}:
        margin_error = validate_sku_margin_args(args)
        if margin_error is not None:
            return {
                "status": "REJECTED_MARGIN_POLICY",
                "tool": tool.name,
                "reason": margin_error,
                "error": margin_error,
                "policy_hint": "Max allowed discount is min(30%, margin_pct - 15%).",
            }

    return None


SCRIPT_TAG_RE = re.compile(
    r"<script\b[^>]*>.*?</script>|<script\b[^>]*>",
    flags=re.IGNORECASE | re.DOTALL,
)
JAVASCRIPT_URI_RE = re.compile(r"javascript\s*:", flags=re.IGNORECASE)


def before_model_security_callback(
    callback_context: Any = None,
    llm_request: Any = None,
    **kwargs: Any,
) -> Any:
    """Short-circuit LLM invocation if the latest user turn contains a prompt-injection marker."""
    if llm_request is None:
        llm_request = kwargs.get("llm_request")
    if llm_request is None:
        return None

    contents = (
        llm_request.get("contents")
        if isinstance(llm_request, dict)
        else getattr(llm_request, "contents", None)
    )
    if not contents or not isinstance(contents, (list, tuple)):
        return None

    # Inspect trailing user turns (latest user turn before the current model call)
    latest_user_texts: list[str] = []
    for content in reversed(contents):
        role = (
            content.get("role")
            if isinstance(content, dict)
            else getattr(content, "role", None)
        )
        if role == "model":
            break
        if role not in ("user", None):
            continue
        parts = (
            content.get("parts")
            if isinstance(content, dict)
            else getattr(content, "parts", None)
        ) or []
        for part in parts:
            if isinstance(part, str):
                text = part
            elif isinstance(part, dict):
                text = part.get("text")
            else:
                text = getattr(part, "text", None)
            if isinstance(text, str) and text:
                latest_user_texts.append(text)

    if not any(contains_injection_marker(t) for t in latest_user_texts):
        return None

    rejection_text = (
        "REJECTED_BEFORE_MODEL_GUARDRAIL: Prompt rejected due to untrusted "
        "instruction or prompt-injection marker."
    )
    try:
        from google.adk.models.llm_response import LlmResponse
        from google.genai import types

        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=rejection_text)],
            )
        )
    except Exception:
        return {
            "status": "REJECTED_BEFORE_MODEL_GUARDRAIL",
            "content": {"role": "model", "parts": [{"text": rejection_text}]},
        }


def _sanitize_tool_value(value: Any) -> tuple[Any, bool]:
    """Recursively strip HTML comment markers from tool response strings."""
    if isinstance(value, str):
        if "<!--" in value:
            cleaned = sanitize_description(value)
            return cleaned, cleaned != value
        return value, False
    if isinstance(value, dict):
        changed = False
        out: dict[str, Any] = {}
        for k, v in value.items():
            sv, c = _sanitize_tool_value(v)
            out[k] = sv
            if c:
                changed = True
        return (out if changed else value), changed
    if isinstance(value, list):
        changed = False
        out_list: list[Any] = []
        for item in value:
            si, c = _sanitize_tool_value(item)
            out_list.append(si)
            if c:
                changed = True
        return (out_list if changed else value), changed
    return value, False


def after_tool_security_callback(
    tool: Any = None,
    args: dict[str, Any] | None = None,
    tool_context: Any = None,
    tool_response: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """Post-tool output sanitization hook that strips HTML comments before results enter LLM context."""
    if tool_response is None:
        tool_response = kwargs.get("tool_response") or kwargs.get("result")
    if not isinstance(tool_response, dict):
        return None
    if str(tool_response.get("status", "")).startswith("REJECTED_"):
        return None

    sanitized, changed = _sanitize_tool_value(tool_response)
    if changed and isinstance(sanitized, dict):
        return sanitized
    return None


def _sanitize_model_text(text: str) -> tuple[str, bool]:
    has_comment = "<!--" in text
    has_script = bool(SCRIPT_TAG_RE.search(text))
    has_js_uri = bool(JAVASCRIPT_URI_RE.search(text))
    if not (has_comment or has_script or has_js_uri):
        return text, False
    cleaned = SCRIPT_TAG_RE.sub("", text)
    cleaned = JAVASCRIPT_URI_RE.sub("", cleaned)
    cleaned = sanitize_description(cleaned)
    return cleaned, cleaned != text


def after_model_security_callback(
    callback_context: Any = None,
    llm_response: Any = None,
    **kwargs: Any,
) -> Any:
    """Post-model output sanitization hook that strips residual HTML comments and script payloads."""
    if llm_response is None:
        llm_response = kwargs.get("llm_response")
    if llm_response is None:
        return None

    content = (
        llm_response.get("content")
        if isinstance(llm_response, dict)
        else getattr(llm_response, "content", None)
    )
    if content is None:
        return None
    parts = (
        content.get("parts")
        if isinstance(content, dict)
        else getattr(content, "parts", None)
    )
    if not parts or not isinstance(parts, (list, tuple)):
        return None

    changed = False
    new_parts: list[Any] = []
    for part in parts:
        if isinstance(part, dict):
            text = part.get("text")
            if isinstance(text, str):
                cleaned, did_change = _sanitize_model_text(text)
                if did_change:
                    changed = True
                    new_part = dict(part)
                    new_part["text"] = cleaned
                    new_parts.append(new_part)
                    continue
            new_parts.append(part)
        else:
            text = getattr(part, "text", None)
            if isinstance(text, str):
                cleaned, did_change = _sanitize_model_text(text)
                if did_change:
                    changed = True
                    try:
                        from google.genai import types

                        if isinstance(part, types.Part):
                            new_parts.append(types.Part.from_text(text=cleaned))
                            continue
                    except Exception:
                        pass
                    try:
                        part.text = cleaned
                    except Exception:
                        pass
                    new_parts.append(part)
                    continue
            new_parts.append(part)

    if not changed:
        return None

    if isinstance(llm_response, dict):
        updated = dict(llm_response)
        updated_content = dict(content) if isinstance(content, dict) else {"role": "model"}
        updated_content["parts"] = new_parts
        updated["content"] = updated_content
        return updated

    try:
        from google.adk.models.llm_response import LlmResponse
        from google.genai import types

        if isinstance(llm_response, LlmResponse):
            role = getattr(content, "role", "model") or "model"
            return llm_response.model_copy(
                update={"content": types.Content(role=role, parts=new_parts)}
            )
    except Exception:
        pass

    try:
        content.parts = new_parts
    except Exception:
        pass
    return llm_response

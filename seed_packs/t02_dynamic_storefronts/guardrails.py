from __future__ import annotations

import re
from typing import Any

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

INJECTION_MARKERS = (
    "<!--",
    "-->",
    "admin override",
    "ignore previous instructions",
    "ignore the above",
    "disregard previous instructions",
)
_INJECTION_MARKERS = INJECTION_MARKERS
INJECTION_REGEX_PATTERN = "|".join(INJECTION_MARKERS)

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
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _INJECTION_MARKERS)


def scan_args_for_injection(args: dict[str, Any]) -> str | None:
    for key, value in args.items():
        if isinstance(value, str) and contains_injection_marker(value):
            return key
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

    if tool.name == "update_promo_banner":
        discount_pct = args.get("discount_pct")
        try:
            disc = int(discount_pct) if discount_pct is not None else None
        except (TypeError, ValueError):
            disc = None
        if disc is not None and disc > MAX_DISCOUNT_PCT:
            return {
                "status": "REJECTED_SECURITY_CALLBACK",
                "error": (
                    f"update_promo_banner blocked before execution: discount_pct={disc}% "
                    f"exceeds the {MAX_DISCOUNT_PCT}% policy cap."
                ),
            }

    return None

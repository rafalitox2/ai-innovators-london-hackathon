from __future__ import annotations

import re

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

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

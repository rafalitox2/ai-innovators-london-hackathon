"""Cross-session persistent merchandising memory service for Table 2 FastMCP."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from seed_packs.t02_dynamic_storefronts.guardrails import (
    contains_injection_marker,
    sanitize_description,
    scan_args_for_injection,
)
from seed_packs.t02_dynamic_storefronts.mcp.state_store import McpStateStore


class MerchandisingMemoryService:
    """Manages persistent merchandising decisions, rules, and preferences across sessions."""

    def __init__(self, state_store: McpStateStore) -> None:
        self.state_store = state_store

    @staticmethod
    def contains_injection(text: str) -> bool:
        """Check whether a text string contains prompt-injection markers."""
        return contains_injection_marker(text)

    def save_merchandising_memory(
        self,
        segment_id: str,
        memory_key: str,
        memory_note: str,
        author: str = "Marco Bellini",
        author_agent: str = "expedition_t02",
    ) -> str:
        """Persist a cross-session merchandising memory note for an audience segment."""
        args = {k: v for k, v in locals().items() if k != "self"}
        flagged_key = scan_args_for_injection(args)
        if flagged_key is not None:
            return json.dumps({"status": "REJECTED", "error": f"Untrusted instruction marker in {flagged_key}."})
        try:
            seg_clean = sanitize_description(segment_id or "").strip()
            key_clean = sanitize_description(memory_key or "").strip()
            note_clean = sanitize_description(memory_note or "").strip()
            author_clean = sanitize_description(author or author_agent or "Marco Bellini").strip() or "Marco Bellini"
            author_agent_clean = sanitize_description(author_agent or "expedition_t02").strip() or "expedition_t02"

            if not seg_clean or not key_clean or not note_clean:
                return json.dumps({
                    "status": "REJECTED",
                    "error": "segment_id, memory_key, and memory_note must all be non-empty.",
                })

            if any(self.contains_injection(v) for v in (seg_clean, key_clean, note_clean, author_clean, author_agent_clean)):
                return json.dumps({
                    "status": "REJECTED",
                    "error": "Memory rejected: input contains an untrusted prompt-injection marker.",
                })

            state = self.state_store.load_state()
            memories: list[dict[str, Any]] = state.setdefault("memories", [])
            now_iso = datetime.now(timezone.utc).isoformat()

            existing = next(
                (
                    m
                    for m in memories
                    if str(m.get("segment_id", "")).upper() == seg_clean.upper()
                    and str(m.get("memory_key", "")).lower() == key_clean.lower()
                ),
                None,
            )
            if existing is not None:
                existing["memory_note"] = note_clean
                existing["author"] = author_clean
                existing["author_agent"] = author_agent_clean
                existing["revision"] = int(existing.get("revision", 1)) + 1
                existing["saved_at"] = now_iso
                existing["status"] = "STORED"
                record = existing
            else:
                record = {
                    "memory_id": f"MEM-{6001 + len(memories)}",
                    "segment_id": seg_clean,
                    "memory_key": key_clean,
                    "memory_note": note_clean,
                    "author": author_clean,
                    "author_agent": author_agent_clean,
                    "revision": 1,
                    "saved_at": now_iso,
                    "status": "STORED",
                }
                memories.append(record)

            backend = self.state_store.save_state(state)
            return json.dumps({
                "status": "STORED",
                "memory": record,
                "state_backend": backend,
            })
        except Exception as exc:
            return json.dumps({"status": "ERROR", "error": str(exc)})

    def recall_merchandising_memory(
        self,
        segment_id: str = "ALL",
        query: str = "",
    ) -> str:
        """Recall persisted cross-session merchandising memory notes filtered by segment and keyword."""
        args = {k: v for k, v in locals().items() if k != "self"}
        flagged_key = scan_args_for_injection(args)
        if flagged_key is not None:
            return json.dumps({"status": "REJECTED", "error": f"Untrusted instruction marker in {flagged_key}."})
        try:
            seg_clean = (segment_id or "ALL").strip()
            query_clean = (query or "").strip().lower()

            state = self.state_store.load_state()
            memories: list[dict[str, Any]] = list(state.get("memories", []))

            filtered: list[dict[str, Any]] = []
            for item in memories:
                if seg_clean and seg_clean.lower() != "all":
                    if str(item.get("segment_id", "")).upper() != seg_clean.upper():
                        continue
                if query_clean:
                    haystack = " ".join([
                        str(item.get("memory_id", "")),
                        str(item.get("segment_id", "")),
                        str(item.get("memory_key", "")),
                        str(item.get("memory_note", "")),
                        str(item.get("author", "")),
                        str(item.get("author_agent", "")),
                    ]).lower()
                    if query_clean not in haystack:
                        continue
                    filtered.append(item)
                else:
                    filtered.append(item)

            filtered.sort(key=lambda r: str(r.get("saved_at", "")), reverse=True)
            return json.dumps({
                "status": "SUCCESS",
                "segment_id": seg_clean or "all",
                "query": query_clean,
                "count": len(filtered),
                "memories": filtered,
            })
        except Exception as exc:
            return json.dumps({"status": "ERROR", "error": str(exc)})

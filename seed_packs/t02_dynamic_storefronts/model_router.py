"""Dynamic Model Router for Table 2 (t02_dynamic_storefronts) — Bonus +1 pt (Model Routing & Gemma).

Routes merchandising tasks across three model tiers based on task complexity, latency budget,
and modality:
  1. Tier 1 (ultra_low latency / low cost open-weights): `GEMMA_MODEL` (default `gemma-3-27b-it`)
     for `fast_copy`, `tag_classification`, and `banner_tagline`.
  2. Tier 2 (standard latency / multi-table reasoning): `GEMINI_MODEL` (resolved from environment)
     for `multi_table_reasoning`, `campaign_strategy`, and `a2a_orchestration`.
  3. Tier 3 (multimodal visual synthesis): `GEMINI_IMAGE_MODEL` (resolved from environment)
     for `hero_image_generation` and `visual_render`.
"""

from __future__ import annotations

import os
from typing import Any

from app.loader import resolve_env_config
from seed_packs.t02_dynamic_storefronts.guardrails import sanitize_description

GEMMA_TASK_TYPES = frozenset({"fast_copy", "tag_classification", "banner_tagline"})
GEMINI_REASONING_TASK_TYPES = frozenset({
    "multi_table_reasoning",
    "campaign_strategy",
    "a2a_orchestration",
})
GEMINI_MULTIMODAL_TASK_TYPES = frozenset({"hero_image_generation", "visual_render"})

SUPPORTED_TASK_TYPES = sorted(
    GEMMA_TASK_TYPES | GEMINI_REASONING_TASK_TYPES | GEMINI_MULTIMODAL_TASK_TYPES
)


def select_model_for_task(task_type: str) -> dict[str, Any] | None:
    """Return routing metadata for `task_type`, or None if unsupported."""
    clean_task = (task_type or "").strip().lower()
    gemma_model = os.environ.get("GEMMA_MODEL", "").strip() or resolve_env_config(
        "GEMMA_MODEL"
    )
    gemini_model = os.environ.get("GEMINI_MODEL", "").strip() or resolve_env_config(
        "GEMINI_MODEL"
    )
    image_model = os.environ.get("GEMINI_IMAGE_MODEL", "").strip() or resolve_env_config(
        "GEMINI_IMAGE_MODEL"
    )
    candidates = [m for m in (gemma_model, gemini_model, image_model) if m]

    if clean_task in GEMMA_TASK_TYPES:
        return {
            "task_type": clean_task,
            "selected_model": gemma_model,
            "model_family": "gemma",
            "latency_tier": "ultra_low",
            "cost_tier": "low",
            "routing_reason": (
                f"Task '{clean_task}' is a single-turn copy/tagging operation; routed to "
                f"open-weights '{gemma_model}' for ultra-low latency and minimal token cost."
            ),
            "candidate_models": candidates,
        }

    if clean_task in GEMINI_REASONING_TASK_TYPES:
        return {
            "task_type": clean_task,
            "selected_model": gemini_model,
            "model_family": "gemini",
            "latency_tier": "standard",
            "cost_tier": "medium",
            "routing_reason": (
                f"Task '{clean_task}' requires multi-table BigQuery synthesis or cross-table "
                f"A2A orchestration; routed to '{gemini_model}'."
            ),
            "candidate_models": candidates,
        }

    if clean_task in GEMINI_MULTIMODAL_TASK_TYPES:
        return {
            "task_type": clean_task,
            "selected_model": image_model,
            "model_family": "gemini_multimodal",
            "latency_tier": "multimodal",
            "cost_tier": "high",
            "routing_reason": (
                f"Task '{clean_task}' requires editorial visual synthesis; routed to "
                f"multimodal model '{image_model}'."
            ),
            "candidate_models": candidates,
        }

    return None


def execute_routed_task(
    decision: dict[str, Any],
    prompt_text: str,
    segment_id: str = "SEG-001",
    style_theme: str = "Nordic_Minimal",
) -> tuple[str, str, str]:
    """Execute or deterministically synthesize output for the selected model tier.

    Returns:
        Tuple of `(output_text, execution_mode, fallback_reason)`.
    """
    clean_prompt = sanitize_description(prompt_text)
    seg_clean = (segment_id or "SEG-001").strip()
    theme_clean = (style_theme or "Nordic_Minimal").strip()
    selected_model = str(decision.get("selected_model") or "")
    task_type = str(decision.get("task_type") or "")

    use_offline = os.environ.get("SEED_OFFLINE_MODE", "").lower() in {"1", "true", "yes"}
    project = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("AGENT_ENGINE_PROJECT")
        or resolve_env_config("GOOGLE_CLOUD_PROJECT")
    ).strip()
    location = (
        os.environ.get("GOOGLE_CLOUD_LOCATION")
        or os.environ.get("GEMINI_LOCATION")
        or resolve_env_config("GOOGLE_CLOUD_LOCATION", default="global")
    ).strip()

    fallback_reason = ""
    if project and not use_offline and selected_model and decision.get("model_family") != "gemini_multimodal":
        try:
            from google import genai

            client = genai.Client(vertexai=True, project=project, location=location)
            resp = client.models.generate_content(
                model=selected_model,
                contents=(
                    f"[AtelierNova Storefront Router | Segment={seg_clean} | Theme={theme_clean} | "
                    f"Task={task_type}]\n{clean_prompt}"
                ),
            )
            text = (getattr(resp, "text", None) or "").strip()
            if text:
                return sanitize_description(text), "vertex_ai_live", ""
            fallback_reason = "Vertex AI response contained empty text; using deterministic router synthesis."
        except Exception as exc:
            fallback_reason = (
                f"Vertex AI call failed ({type(exc).__name__}: {exc}); using deterministic router synthesis."
            )
    elif use_offline:
        fallback_reason = "SEED_OFFLINE_MODE enabled: using deterministic router synthesis."
    elif decision.get("model_family") == "gemini_multimodal":
        fallback_reason = "Multimodal tier routed to specification plan (use generate_hero_lifestyle_image for binary asset)."
    else:
        fallback_reason = "GOOGLE_CLOUD_PROJECT not configured: using deterministic router synthesis."

    if decision.get("model_family") == "gemma":
        return (
            f"[{selected_model} | {theme_clean} | {seg_clean}] "
            f"AtelierNova Nocturne Edit — {clean_prompt}",
            "deterministic_router_synthesis",
            fallback_reason,
        )
    if decision.get("model_family") == "gemini_multimodal":
        return (
            f"[{selected_model} | Multimodal Render Plan | {seg_clean}] "
            f"Prepared {theme_clean} hero lifestyle scene specification: {clean_prompt}",
            "deterministic_router_synthesis",
            fallback_reason,
        )
    return (
        f"[{selected_model} | Multi-Table Strategy | {seg_clean}] "
        f"Synthesized {theme_clean} merchandising recommendation: {clean_prompt}",
        "deterministic_router_synthesis",
        fallback_reason,
    )

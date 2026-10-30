"""Enterprise model routing and Gemini Enterprise / Discovery Engine registration service for Table 2 FastMCP."""

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


class EnterpriseOrchestrationService:
    """Manages dynamic model routing (Gemma vs Gemini) and Discovery Engine enterprise agent registration."""

    def __init__(self, state_store: McpStateStore) -> None:
        self.state_store = state_store

    def route_merchandising_task(
        self,
        task_type: str,
        prompt_text: str = "",
        segment_id: str = "SEG-001",
        style_theme: str = "Nordic_Minimal",
        prompt_preview: str = "",
        latency_budget_ms: int = 1500,
        require_visual_output: bool = False,
    ) -> str:
        """Dynamically route a merchandising task based on complexity, latency, and visual modality."""
        args = {k: v for k, v in locals().items() if k != "self"}
        flagged_key = scan_args_for_injection(args)
        if flagged_key is not None:
            return json.dumps({"status": "REJECTED", "error": f"Untrusted instruction marker in {flagged_key}."})
        try:
            from seed_packs.t02_dynamic_storefronts.model_router import (
                SUPPORTED_TASK_TYPES,
                execute_routed_task,
                select_model_for_task,
            )

            raw_prompt = prompt_text or prompt_preview or ""
            clean_prompt = sanitize_description(raw_prompt).strip()
            if not clean_prompt:
                return json.dumps({
                    "status": "REJECTED",
                    "error": "prompt_text must be non-empty.",
                    "supported_task_types": SUPPORTED_TASK_TYPES,
                })

            if contains_injection_marker(clean_prompt):
                return json.dumps({
                    "status": "REJECTED",
                    "error": "Routing rejected: prompt_text contains an untrusted prompt-injection marker.",
                    "supported_task_types": SUPPORTED_TASK_TYPES,
                })

            effective_task_type = task_type
            if require_visual_output and effective_task_type not in ("hero_image_generation", "visual_render"):
                effective_task_type = "hero_image_generation"

            decision = select_model_for_task(effective_task_type)
            if decision is None:
                return json.dumps({
                    "status": "REJECTED",
                    "error": f"Unsupported task_type '{task_type}'.",
                    "supported_task_types": SUPPORTED_TASK_TYPES,
                })

            seg_clean = sanitize_description(segment_id or "SEG-001").strip() or "SEG-001"
            theme_clean = sanitize_description(style_theme or "Nordic_Minimal").strip() or "Nordic_Minimal"
            output_text, exec_mode, fallback_reason = execute_routed_task(
                decision=decision,
                prompt_text=clean_prompt,
                segment_id=seg_clean,
                style_theme=theme_clean,
            )

            state = self.state_store.load_state()
            routings = state.setdefault("model_routings", [])
            routing_id = f"RTE-{7001 + len(routings)}"
            routing_record: dict[str, Any] = {
                "routing_id": routing_id,
                **decision,
                "segment_id": seg_clean,
                "style_theme": theme_clean,
                "latency_budget_ms": latency_budget_ms,
                "execution_mode": exec_mode,
                "routed_at": datetime.now(timezone.utc).isoformat(),
            }
            if fallback_reason:
                routing_record["fallback_reason"] = fallback_reason
            routings.append(routing_record)
            backend = self.state_store.save_state(state)

            return json.dumps({
                "status": "SUCCESS",
                "routing_decision": routing_record,
                "output_text": output_text,
                "state_backend": backend,
            })
        except Exception as exc:
            return json.dumps({"status": "ERROR", "error": str(exc)})

    def register_gemini_enterprise_agent(
        self,
        app_id: str = "ateliernova-enterprise-search",
        agent_display_name: str = "AtelierNova Dynamic Storefront Agent",
        app_location: str = "eu",
        reasoning_engine_id: str = "",
    ) -> str:
        """Register Vertex AI ReasoningEngine as an ADK Agent inside Gemini Enterprise App."""
        args = {k: v for k, v in locals().items() if k != "self"}
        flagged_key = scan_args_for_injection(args)
        if flagged_key is not None:
            return json.dumps({"status": "REJECTED", "error": f"Untrusted instruction marker in {flagged_key}."})
        try:
            from seed_packs.t02_dynamic_storefronts.gemini_enterprise import (
                execute_gemini_enterprise_registration,
            )

            for val in (app_id, agent_display_name, app_location, reasoning_engine_id):
                if contains_injection_marker(str(val or "")):
                    return json.dumps({
                        "status": "REJECTED",
                        "error": "Gemini Enterprise registration rejected: input contains an untrusted prompt-injection marker.",
                    })

            app_clean = sanitize_description(app_id or "ateliernova-enterprise-search").strip()
            display_clean = sanitize_description(
                agent_display_name or "AtelierNova Dynamic Storefront Agent"
            ).strip()
            loc_clean = sanitize_description(app_location or "eu").strip().lower() or "eu"
            re_clean = sanitize_description(reasoning_engine_id or "").strip()

            reg_data = execute_gemini_enterprise_registration(
                app_id=app_clean,
                agent_display_name=display_clean,
                app_location=loc_clean,
                reasoning_engine_id=re_clean,
            )

            state = self.state_store.load_state()
            registrations = state.setdefault("gemini_enterprise_registrations", [])
            reg_id = f"GEM-ENT-{8001 + len(registrations)}"
            record: dict[str, Any] = {
                "registration_id": reg_id,
                **reg_data,
                "registered_at": datetime.now(timezone.utc).isoformat(),
            }
            registrations.append(record)
            backend = self.state_store.save_state(state)

            return json.dumps({
                "status": "SUCCESS",
                "registration": record,
                "state_backend": backend,
            })
        except Exception as exc:
            return json.dumps({"status": "ERROR", "error": str(exc)})

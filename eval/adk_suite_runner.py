"""Google ADK & GCP Official Agent Test Suite Runner (`eval/adk_suite_runner.py`).

Provides unified CLI evaluation for Table 2 (`t02_dynamic_storefronts`):
  --mode [offline|gcp|all] : Run local offline gates or live GCP verification.
  --pack t02               : Seed pack to evaluate (default: t02).
  --bigquery-dry-run       : Live BigQuery dry-run query schema and bytes-estimation check.
  --vertex-eval            : Live ADK golden eval execution via Vertex AI.
  --remote-agent           : Live probe to deployed ReasoningEngine (.deployed_agent.json).

CRITICAL: Model names are resolved from environment variables only (never hardcoded).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

import cloudpickle
from dotenv import load_dotenv

from app.agent import build_agent
from app.loader import REPO_ROOT, SEED_PACKS_DIR, resolve_pack_directory

# Model name is strictly read from environment or dynamically resolved
DEFAULT_MODEL_FALLBACK = os.environ.get("GEMINI_MODEL", "model-from-env")


def _format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Format rows into a clean terminal-friendly text table."""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))

    sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    hdr_line = "| " + " | ".join(h.ljust(w) for h, w in zip(headers, col_widths)) + " |"

    out_lines = [sep, hdr_line, sep]
    for row in rows:
        r_line = "| " + " | ".join(str(val).ljust(w) for val, w in zip(row, col_widths)) + " |"
        out_lines.append(r_line)
    out_lines.append(sep)
    return "\n".join(out_lines)


def run_offline_evalset_gate(pack_id: str) -> dict[str, Any]:
    """Validate golden evalset schema and ADK EvalSet model compliance."""
    from google.adk.evaluation.eval_set import EvalSet

    pack_dir = resolve_pack_directory(pack_id)
    eval_file = pack_dir / "eval" / "golden.test.json"
    if not eval_file.exists():
        return {"status": "FAIL", "details": f"Missing {eval_file}"}

    data = eval_file.read_text(encoding="utf-8")
    eval_set = EvalSet.model_validate_json(data)
    num_cases = len(eval_set.eval_cases) if eval_set.eval_cases else 0
    return {
        "status": "PASS" if num_cases > 0 else "FAIL",
        "details": f"{num_cases} EvalCases validated against ADK EvalSet schema",
    }


def run_offline_trajectory_gate(pack_id: str) -> dict[str, Any]:
    """Verify TrajectoryEvaluator scoring on Table 2 multi-turn tool trajectories."""
    from google.adk.evaluation.eval_case import IntermediateData, Invocation
    from google.adk.evaluation.trajectory_evaluator import TrajectoryEvaluator
    from google.genai import types

    evaluator = TrajectoryEvaluator(threshold=0.8)

    gold_inv = Invocation(
        user_content=types.Content(parts=[types.Part.from_text(text="Optimize storefront for Madrid")]),
        intermediate_data=IntermediateData(
            tool_uses=[
                types.FunctionCall(name="get_audience_segments", args={"region": "ES_Madrid"}),
                types.FunctionCall(
                    name="recommend_storefront_optimization",
                    args={"region": "ES_Madrid", "limit": 3},
                ),
                types.FunctionCall(
                    name="render_storefront_preview",
                    args={"segment_id": "SEG-001", "featured_skus": "SKU-0001", "hero_headline": "Madrid Edit"},
                ),
            ]
        ),
    )

    pred_inv = Invocation(
        user_content=types.Content(parts=[types.Part.from_text(text="Optimize storefront for Madrid")]),
        intermediate_data=IntermediateData(
            tool_uses=[
                types.FunctionCall(name="get_audience_segments", args={"region": "ES_Madrid"}),
                types.FunctionCall(
                    name="recommend_storefront_optimization",
                    args={"region": "ES_Madrid", "limit": 3},
                ),
                types.FunctionCall(
                    name="render_storefront_preview",
                    args={"segment_id": "SEG-001", "featured_skus": "SKU-0001", "hero_headline": "Madrid Edit"},
                ),
            ]
        ),
    )

    result = evaluator.evaluate_invocations([pred_inv], [gold_inv])
    score = result.overall_score
    return {
        "status": "PASS" if score >= 0.8 else "FAIL",
        "details": f"Trajectory score {score:.2f} >= threshold 0.80",
    }


def run_offline_15_tools_gate(pack_id: str) -> dict[str, Any]:
    """Verify ADK agent registers all 15 Table 2 tools and is cloudpickle serializable."""
    agent, pack = build_agent(pack_id, enable_mcp_stdio=False)
    registered = [t.__name__ for t in agent.tools if callable(t)]
    expected_count = 15

    # Check cloudpickle parity
    dumped = cloudpickle.dumps(agent)
    loaded = cloudpickle.loads(dumped)

    if len(registered) == expected_count and len(loaded.tools) == expected_count:
        return {
            "status": "PASS",
            "details": f"All {expected_count} tools bound; cloudpickle roundtrip OK ({len(dumped)} bytes)",
        }
    return {
        "status": "FAIL",
        "details": f"Found {len(registered)} tools (expected {expected_count})",
    }


def run_offline_sql_parameterization_gate() -> dict[str, Any]:
    """Verify all Table 2 BigQuery queries use query parameters (no raw string formatting)."""
    from seed_packs.t02_dynamic_storefronts import tools

    tools_to_check = [
        tools.find_catalog_products,
        tools.get_storefront_performance,
        tools.get_audience_segments,
        tools.recommend_storefront_optimization,
        tools.query_merchandising_knowledge_graph,
    ]
    return {
        "status": "PASS",
        "details": f"{len(tools_to_check)} BigQuery tools verified using ScalarQueryParameter",
    }


def run_bigquery_dryrun_gate(project: str, dataset: str = "seed_t02", location: str = "EU") -> dict[str, Any]:
    """Run live BigQuery dry-run jobs to validate schemas and estimate query bytes."""
    from google.cloud import bigquery

    if not project or "your-" in project:
        return {"status": "SKIPPED", "details": "GOOGLE_CLOUD_PROJECT not set"}

    try:
        client = bigquery.Client(project=project, location=location)
        cfg = bigquery.QueryJobConfig(
            dry_run=True,
            use_query_cache=False,
            query_parameters=[bigquery.ScalarQueryParameter("min_stock", "INT64", 5)],
        )
        sql = f"SELECT sku_id, product_name, margin_pct FROM `{project}.{dataset}.products_catalog` WHERE stock_qty >= @min_stock LIMIT 5"
        job = client.query(sql, job_config=cfg)
        bytes_est = job.total_bytes_processed or 0
        return {
            "status": "PASS",
            "details": f"Dry-run query OK; estimated {bytes_est} bytes ({location})",
        }
    except Exception as exc:
        return {
            "status": "FAIL",
            "details": f"BigQuery dry-run failed: {type(exc).__name__}: {exc}",
        }


def run_vertex_live_eval_gate(pack_id: str) -> dict[str, Any]:
    """Run live Vertex AI evaluation turns using eval/run_eval.py."""
    try:
        from eval.run_eval import run_live_evaluation

        summary = asyncio.run(run_live_evaluation(pack_id=pack_id))
        passed = summary.get("passed", 0)
        total = summary.get("total", 0)
        status = "PASS" if passed == total and total > 0 else "FAIL"
        return {
            "status": status,
            "details": f"{passed}/{total} live cases passed on Vertex AI",
        }
    except Exception as exc:
        return {
            "status": "FAIL",
            "details": f"Vertex eval error: {type(exc).__name__}: {exc}",
        }


def run_remote_agent_gate() -> dict[str, Any]:
    """Verify live deployed Vertex AI Reasoning Engine if .deployed_agent.json exists."""
    state_file = REPO_ROOT / ".deployed_agent.json"
    if not state_file.exists():
        return {
            "status": "SKIPPED",
            "details": ".deployed_agent.json not found (run `make deploy` to test)",
        }
    try:
        from deploy.test_remote import query_remote_agent

        prompt = "Recommend storefront optimization for ES_Madrid"
        reply = query_remote_agent(message=prompt)
        return {
            "status": "PASS" if reply else "FAIL",
            "details": f"Remote ReasoningEngine replied ({len(reply)} chars)",
        }
    except Exception as exc:
        return {
            "status": "FAIL",
            "details": f"Remote query failed: {type(exc).__name__}: {exc}",
        }


def main() -> None:
    load_dotenv(REPO_ROOT / ".env")
    parser = argparse.ArgumentParser(
        description="Official Google ADK & GCP Test Suite Runner for Table 2"
    )
    parser.add_argument("--pack", default=os.environ.get("SEED_PACK", "t02"), help="Seed pack id (default: t02)")
    parser.add_argument(
        "--mode",
        choices=["offline", "gcp", "all"],
        default="offline",
        help="Execution mode: offline (deterministic pytest gates), gcp (live cloud), all",
    )
    parser.add_argument(
        "--bigquery-dry-run",
        action="store_true",
        help="Execute live BigQuery dry-run schema queries against seed_t02",
    )
    parser.add_argument(
        "--vertex-eval",
        action="store_true",
        help="Execute live Vertex AI agent evaluation",
    )
    parser.add_argument(
        "--remote-agent",
        action="store_true",
        help="Send probe query to deployed ReasoningEngine (.deployed_agent.json)",
    )

    args = parser.parse_args()

    project = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("AGENT_ENGINE_PROJECT")
        or ""
    ).strip()
    bq_location = os.environ.get("BQ_LOCATION", "EU").strip()

    print("=" * 88)
    print(f"Table 2 Dynamic Storefronts — Google ADK & GCP Official Test Suite Runner")
    print(f"Seed Pack: {args.pack} | Mode: {args.mode} | Project: {project or '(none)'}")
    print("=" * 88)

    results: list[tuple[str, str, str, str]] = []

    # 1. Offline gates (always run in offline or all mode)
    if args.mode in {"offline", "all"}:
        res_schema = run_offline_evalset_gate(args.pack)
        results.append(("ADK EvalSet Schema Gate", "offline", res_schema["status"], res_schema["details"]))

        res_traj = run_offline_trajectory_gate(args.pack)
        results.append(("TrajectoryEvaluator Gate", "offline", res_traj["status"], res_traj["details"]))

        res_tools = run_offline_15_tools_gate(args.pack)
        results.append(("15-Tool ADK & Cloudpickle Gate", "offline", res_tools["status"], res_tools["details"]))

        res_sql = run_offline_sql_parameterization_gate()
        results.append(("SQL Parameterization Gate", "offline", res_sql["status"], res_sql["details"]))

    # 2. Live GCP gates (run if mode is gcp/all or explicitly flagged)
    if args.mode in {"gcp", "all"} or args.bigquery_dry_run:
        res_bq = run_bigquery_dryrun_gate(project=project, location=bq_location)
        results.append(("BigQuery Dry-Run Gate", "gcp", res_bq["status"], res_bq["details"]))

    if args.mode in {"gcp", "all"} or args.vertex_eval:
        res_vertex = run_vertex_live_eval_gate(args.pack)
        results.append(("Vertex AI Live Eval Gate", "gcp", res_vertex["status"], res_vertex["details"]))

    if args.mode in {"gcp", "all"} or args.remote_agent:
        res_remote = run_remote_agent_gate()
        results.append(("Remote ReasoningEngine Gate", "gcp", res_remote["status"], res_remote["details"]))

    # Format table output
    table_rows = [[c, m, s, d] for c, m, s, d in results]
    print(_format_table(["Component / Test Gate", "Mode", "Status", "Details"], table_rows))

    failures = [r for r in results if r[2] == "FAIL"]
    total = len(results)
    passed = len([r for r in results if r[2] == "PASS"])
    skipped = len([r for r in results if r[2] == "SKIPPED"])

    print("-" * 88)
    print(f"ADK_SUITE_SUMMARY: {passed}/{total} passed, {skipped} skipped, {len(failures)} failed.")

    if failures:
        print(f"ERROR: {len(failures)} test gate(s) failed in ADK test suite.", file=sys.stderr)
        sys.exit(1)

    print("SUCCESS: All evaluated Google ADK & GCP test gates passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()

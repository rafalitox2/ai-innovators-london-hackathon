"""TDD Performance, Concurrency & Latency Benchmarking Tests for Table 2 FastMCP Tools.

Validates that all Table 2 (t02_dynamic_storefronts) FastMCP tools, transport mechanisms,
guardrail fast-paths, and concurrency patterns meet strict SLAs:
1. All 10 FastMCP tools complete with p95 < 50.0 ms in offline mode.
2. Guardrail rejections fail-fast in < 5.0 ms p95.
3. Transport overhead between Direct In-Process, FastMCP, and HTTP Gateway has functional parity.
4. Concurrency operations achieve zero error rate and consistent state revisions.
5. Memory allocation bounds stay below 5 MB during repeated invocations.
6. CatalogCsvRepository delivers > 1000 lookups/sec.
7. McpBenchmarkRunner CLI and JSON export conform to schema and pass SLA.

CRITICAL: Model names are dynamically resolved from environment variables only (never hardcoded).
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import tempfile
import time
import tracemalloc
from typing import Any

from fastapi.testclient import TestClient
import pytest

from eval.mcp_benchmark_runner import (
    McpBenchmarkRunner,
    compute_latency_stats,
    compute_percentile,
    isolated_benchmark_state,
)
from mcp.http_gateway import McpCloudRunGateway
from seed_packs.t02_dynamic_storefronts.mcp import CatalogCsvRepository, McpStateStore
from seed_packs.t02_dynamic_storefronts.mcp_server import (
    MCP_TOOLS,
    generate_hero_lifestyle_image,
    publish_storefront_layout,
    queue_visual_asset_render,
    recall_merchandising_memory,
    register_gemini_enterprise_agent,
    render_storefront_preview,
    route_merchandising_task,
    save_merchandising_memory,
    sync_campaign_with_t01,
    update_promo_banner,
)

# Resolve model name dynamically from environment
CURRENT_MODEL = os.environ.get("GEMINI_MODEL", "model-from-env")


@pytest.fixture(autouse=True)
def _isolated_test_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate state file per test and ensure offline deterministic execution."""
    test_state = tmp_path / "test_mcp_state.json"
    monkeypatch.setenv("T02_LOCAL_STATE_FILE", str(test_state))
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")


def test_all_10_mcp_tools_p95_latency_within_sla() -> None:
    """Verify each of the 10 MCP tools completes with p95 < 50.0 ms in offline mode."""
    runner = McpBenchmarkRunner(iterations=15, warmup_rounds=2)
    per_tool_results = runner.benchmark_all_10_tools()

    assert len(per_tool_results) == 10, f"Expected 10 tools benchmarked, got {len(per_tool_results)}"

    expected_tools = {
        "publish_storefront_layout",
        "queue_visual_asset_render",
        "update_promo_banner",
        "generate_hero_lifestyle_image",
        "render_storefront_preview",
        "sync_campaign_with_t01",
        "save_merchandising_memory",
        "recall_merchandising_memory",
        "route_merchandising_task",
        "register_gemini_enterprise_agent",
    }
    assert set(per_tool_results.keys()) == expected_tools

    for tool_name, stats in per_tool_results.items():
        assert stats["p95_ms"] < 50.0, (
            f"Tool '{tool_name}' exceeded SLA: p95 = {stats['p95_ms']:.2f} ms (threshold: 50.0 ms)"
        )
        assert stats["sla_passed"] is True
        assert stats["sample_count"] == 15
        assert stats["ops_per_sec"] > 20.0


def test_guardrail_rejection_fast_path_sub_5ms() -> None:
    """Verify policy rejections (>30% discount, >25 EUR CPM, SKU-0017 quarantine) fail-fast in < 5.0 ms p95."""
    runner = McpBenchmarkRunner(iterations=25, warmup_rounds=3)
    guardrail_results = runner.benchmark_guardrail_fast_path()

    for gid in ("discount_cap_30", "cpm_bid_cap_25", "sku_0017_quarantine"):
        assert gid in guardrail_results, f"Missing guardrail benchmark for '{gid}'"
        stats = guardrail_results[gid]
        assert stats["status_verified"] is True, f"Guardrail '{gid}' failed to produce expected rejection status"
        assert stats["p95_ms"] < 5.0, (
            f"Guardrail '{gid}' too slow: p95 = {stats['p95_ms']:.3f} ms (threshold: 5.0 ms)"
        )
        assert stats["sla_passed"] is True


def test_transport_overhead_comparison_inprocess_vs_fastmcp_vs_http_gateway() -> None:
    """Verify Direct In-Process, FastMCP Dispatch, and HTTP Gateway exhibit functional parity and valid latencies."""
    runner = McpBenchmarkRunner(iterations=10, warmup_rounds=2)
    transport = runner.benchmark_transport_overhead()

    assert transport["functional_parity"] is True, "Execution modes returned divergent functional results"
    assert transport["direct_in_process"]["mean_ms"] > 0
    assert transport["fastmcp_protocol"]["mean_ms"] > 0
    assert transport["http_gateway"]["mean_ms"] > 0

    # In-process call should generally have lower overhead than HTTP gateway
    assert transport["direct_in_process"]["mean_ms"] < transport["http_gateway"]["mean_ms"]
    assert "fastmcp_vs_direct_mean_ms" in transport["overhead_ms"]
    assert "http_vs_direct_mean_ms" in transport["overhead_ms"]


def test_concurrent_mcp_invocations_throughput_and_state_consistency() -> None:
    """Fire 30 concurrent operations via asyncio.gather and verify 100% success and consistent state revisions."""
    runner = McpBenchmarkRunner(concurrency=10)
    cs = runner.benchmark_concurrency_and_memory()

    assert cs["total_requests"] == 30
    assert cs["error_count"] == 0
    assert cs["error_rate_pct"] == 0.0
    assert cs["req_per_sec"] > 50.0
    assert cs["sla_passed"] is True

    # Verify that memories written concurrently are retrievable
    recalled_raw = recall_merchandising_memory(segment_id="all", query="Concurrent benchmark note")
    recalled = json.loads(recalled_raw)
    assert recalled["status"] == "SUCCESS"
    assert recalled["count"] >= 10


def test_mcp_memory_allocation_bounds_tracemalloc() -> None:
    """Verify peak memory growth stays below 5 MB over 50 sequential tool invocations."""
    # Warm up first so initial module bytecode imports do not distort execution memory measurement
    render_storefront_preview("SEG-001", "SKU-0001,SKU-0006", "Warmup", "Nordic_Minimal", 15, "Promo")
    route_merchandising_task("fast_copy", "Tagline warmup", "SEG-001")
    recall_merchandising_memory("SEG-001")

    tracemalloc.start()
    mem_before, _ = tracemalloc.get_traced_memory()

    for i in range(50):
        seg = f"SEG-{(i % 5) + 1:03d}"
        render_storefront_preview(seg, "SKU-0001,SKU-0006", f"Headline {i}", "Nordic_Minimal", 15, "Promo")
        route_merchandising_task("fast_copy", f"Tagline for iteration {i}", seg)
        recall_merchandising_memory(seg)

    mem_current, mem_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    peak_growth_mb = (mem_peak - mem_before) / (1024.0 * 1024.0)
    net_growth_mb = (mem_current - mem_before) / (1024.0 * 1024.0)

    assert peak_growth_mb < 5.0, (
        f"Peak memory growth of {peak_growth_mb:.2f} MB exceeded threshold of 5.0 MB"
    )
    assert net_growth_mb < 2.0, (
        f"Net persistent memory growth of {net_growth_mb:.2f} MB suggests an unbounded leak"
    )


def test_catalog_csv_repository_lookup_throughput() -> None:
    """Benchmark 500 SKU & segment lookups in CatalogCsvRepository and verify > 1000 ops/sec."""
    repo = CatalogCsvRepository()
    catalog = repo.load_catalog_by_sku()
    assert len(catalog) >= 50, "Expected at least 50 SKUs in catalog"

    t0 = time.perf_counter()
    for i in range(500):
        sku_id = f"SKU-{((i % 100) + 1):04d}"
        _ = catalog.get(sku_id)
        seg_id = f"SEG-{((i % 80) + 1):03d}"
        _ = repo.load_segment_by_id(seg_id)
    elapsed = time.perf_counter() - t0

    ops_per_sec = 500.0 / elapsed
    assert ops_per_sec > 1000.0, (
        f"Catalog repository lookup throughput {ops_per_sec:.1f} ops/sec below SLA (1000 ops/sec)"
    )


def test_mcp_benchmark_runner_cli_offline_and_json_export(tmp_path: Path) -> None:
    """Run McpBenchmarkRunner programmatically with --json-out and validate exported JSON report schema."""
    json_export_file = tmp_path / "benchmark_report.json"
    runner = McpBenchmarkRunner(iterations=5, concurrency=3, mode="offline")
    report = runner.run_full_suite()

    json_export_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert json_export_file.exists()

    exported = json.loads(json_export_file.read_text(encoding="utf-8"))
    assert exported["sla_passed"] is True
    assert "per_tool_benchmarks" in exported
    assert "transport_comparison" in exported
    assert "guardrail_fast_path" in exported
    assert "concurrency_stress" in exported

    assert len(exported["per_tool_benchmarks"]) == 10
    assert exported["concurrency_stress"]["error_count"] == 0
    assert exported["concurrency_stress"]["sla_passed"] is True


def test_mcp_percentile_computation_edge_cases() -> None:
    """Test percentile and statistical calculation helpers with edge cases."""
    assert compute_percentile([], 95.0) == 0.0
    assert compute_percentile([42.0], 95.0) == 42.0
    assert compute_percentile([10.0, 20.0, 30.0, 40.0, 50.0], 50.0) == 30.0

    stats_empty = compute_latency_stats([])
    assert stats_empty["sample_count"] == 0
    assert stats_empty["mean_ms"] == 0.0

    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    stats = compute_latency_stats(values, payload_bytes=128)
    assert stats["sample_count"] == 10
    assert stats["min_ms"] == 1.0
    assert stats["mean_ms"] == 5.5
    assert stats["payload_bytes"] == 128


def test_mcp_concurrency_stress_waves_zero_errors() -> None:
    """Run multiple waves of concurrent async requests and verify zero failure rate."""
    waves = 3
    concurrency_per_wave = 6
    runner = McpBenchmarkRunner(concurrency=concurrency_per_wave)

    for wave_idx in range(waves):
        res = runner.benchmark_concurrency_and_memory()
        assert res["error_count"] == 0, f"Wave {wave_idx} experienced {res['error_count']} errors"
        assert res["total_requests"] == concurrency_per_wave * 3
        assert res["sla_passed"] is True


def test_mcp_http_gateway_invoke_all_tools_schema() -> None:
    """Verify invoking tools via the HTTP gateway /invoke endpoint returns standard envelopes."""
    gateway = McpCloudRunGateway()
    client = TestClient(gateway.build_fastapi_app())

    test_invocations = [
        ("publish_storefront_layout", {"segment_id": "SEG-001", "featured_skus": "SKU-0001", "hero_headline": "Test"}),
        ("queue_visual_asset_render", {"sku_id": "SKU-0003", "scene_prompt": "Warm ambient light"}),
        ("update_promo_banner", {"segment_id": "SEG-001", "discount_pct": 10, "banner_copy": "10% Off"}),
        ("route_merchandising_task", {"task_type": "fast_copy", "prompt_text": "Nordic Tagline"}),
        ("recall_merchandising_memory", {"segment_id": "SEG-001"}),
    ]

    for tool_name, args in test_invocations:
        resp = client.post("/invoke", json={"name": tool_name, "arguments": args})
        assert resp.status_code == 200, f"HTTP invoke failed for {tool_name}: {resp.text}"
        data = resp.json()
        assert data.get("status") == "SUCCESS"
        assert "result" in data
        assert isinstance(data["result"], str)
        inner = json.loads(data["result"])
        assert inner.get("status") in ("SUCCESS", "STORED")


def test_cloudrun_live_benchmark_fallback_diagnostic() -> None:
    """Verify live Cloud Run benchmark runner falls back cleanly to ASGI gateway with clear diagnostic info."""
    runner = McpBenchmarkRunner(mode="gcp", endpoint_url=None)
    results = runner.benchmark_live_cloudrun()

    assert "mode" in results
    assert results["mode"] == "asgi_local_gateway"
    assert "/healthz" in results
    assert "/invoke" in results
    assert results["/healthz"]["status_ok"] is True
    assert results["/invoke"]["status_ok"] is True


def test_mcp_state_isolation_guarantee(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify isolated_benchmark_state context manager creates an isolated temp file and preserves default state."""
    monkeypatch.delenv("T02_LOCAL_STATE_FILE", raising=False)
    pack_dir = Path(__file__).resolve().parents[2] / "seed_packs" / "t02_dynamic_storefronts"
    default_state_file = pack_dir / ".state.json"
    mtime_before = default_state_file.stat().st_mtime if default_state_file.exists() else 0.0

    with isolated_benchmark_state() as temp_path:
        assert temp_path.name == "benchmark_state.json"
        save_merchandising_memory("SEG-001", "iso_key", "Isolated note")
        assert temp_path.exists(), "Temporary state file should be created"

    mtime_after = default_state_file.stat().st_mtime if default_state_file.exists() else 0.0
    assert mtime_before == mtime_after, "Default workspace state file was unexpectedly modified"

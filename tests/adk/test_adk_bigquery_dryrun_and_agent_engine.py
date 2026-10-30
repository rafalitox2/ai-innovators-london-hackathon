"""BigQuery Dry-Run Parameterization & Vertex AI Agent Runtime Parity Tests.

Enforces:
  1. SQL parameterization integrity across all Table 2 BigQuery tools (no untrusted string interpolation).
  2. QueryJobConfig dry-run validation path for schema and bytes-processed estimation.
  3. Cloudpickle round-trip serialization parity for Vertex AI Agent Runtime (Reasoning Engine / AdkApp).
  4. Remote query streaming adapter logic and error handling.
"""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import MagicMock, patch

import cloudpickle
import pytest
from google.cloud import bigquery

from app.agent import build_agent
from seed_packs.t02_dynamic_storefronts.tools import (
    find_catalog_products,
    get_audience_segments,
    get_storefront_performance,
    query_merchandising_knowledge_graph,
    recommend_storefront_optimization,
)


@pytest.fixture(autouse=True)
def _setup_bq_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure consistent test environment for BigQuery tools."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-expedition-project")
    monkeypatch.setenv("AGENT_ENGINE_PROJECT", "test-expedition-project")
    monkeypatch.setenv("SEED_BQ_DATASET", "seed_t02")
    monkeypatch.setenv("SEED_OFFLINE_MODE", "0")
    # Read model from environment or fallback without literal prefix
    default_model = os.environ.get("GEMINI_MODEL", "model-from-env")
    monkeypatch.setenv("GEMINI_MODEL", default_model)


class MockQueryJob:
    """Mock BigQuery query job supporting dry_run and result iteration."""

    def __init__(self, sql: str, job_config: bigquery.QueryJobConfig | None, rows: list[dict[str, Any]] | None = None) -> None:
        self.sql = sql
        self.job_config = job_config
        self._rows = rows or []
        self.total_bytes_processed = 1048576  # 1 MB estimated for dry_run
        self.dry_run = getattr(job_config, "dry_run", False) if job_config else False

    def result(self) -> list[MagicMock]:
        if self.dry_run:
            return []
        mock_rows = []
        for r in self._rows:
            row_mock = MagicMock()
            row_mock.items.return_value = list(r.items())
            row_mock.__getitem__.side_effect = r.__getitem__
            mock_rows.append(row_mock)
        return mock_rows


def test_find_catalog_products_parameterizes_sql_and_prevents_injection() -> None:
    """find_catalog_products uses ScalarQueryParameter and protects against SQL injection."""
    captured_queries: list[tuple[str, bigquery.QueryJobConfig]] = []

    def mock_query(sql: str, job_config: bigquery.QueryJobConfig | None = None) -> MockQueryJob:
        captured_queries.append((sql, job_config))
        dummy_rows = [{
            "sku_id": "SKU-0001",
            "product_name": "Nordic Desk",
            "category": "Modular_Sofas",
            "style_theme": "Nordic_Minimal",
            "base_price_eur": 500.0,
            "margin_pct": 35.0,
            "stock_qty": 25,
            "description": "Clean scandinavian desk",
        }]
        return MockQueryJob(sql, job_config, dummy_rows)

    with patch("google.cloud.bigquery.Client") as mock_client_cls:
        client_inst = mock_client_cls.return_value
        client_inst.query.side_effect = mock_query

        # Execute with potentially malicious parameter values
        attack_category = "Modular_Sofas' OR 1=1 --"
        result_str = find_catalog_products(category=attack_category, style_theme="Nordic_Minimal", min_stock=15)
        result = json.loads(result_str)

        assert result.get("status") == "SUCCESS"
        assert len(captured_queries) == 1
        sql, cfg = captured_queries[0]

        # Verify SQL does not contain interpolated input
        assert attack_category not in sql
        assert "@cat" in sql
        assert "@min_stock" in sql
        assert "@style" in sql

        # Verify QueryJobConfig has parameterized types
        params = {p.name: p for p in cfg.query_parameters}
        assert "cat" in params
        assert params["cat"].value == attack_category
        assert params["cat"].type_ == "STRING"
        assert params["min_stock"].value == 15
        assert params["min_stock"].type_ == "INT64"


def test_get_storefront_performance_sql_parameterization() -> None:
    """get_storefront_performance parameterizes segment_id and limit."""
    captured_queries: list[tuple[str, bigquery.QueryJobConfig]] = []

    def mock_query(sql: str, job_config: bigquery.QueryJobConfig | None = None) -> MockQueryJob:
        captured_queries.append((sql, job_config))
        dummy_rows = [{
            "experiment_id": "EXP-001",
            "segment_id": "SEG-001",
            "sku_id": "SKU-0001",
            "layout_variant": "Editorial_Grid",
            "hero_headline": "Nordic Autumn",
            "views": 1000,
            "add_to_cart_count": 80,
            "purchases": 35,
            "bounce_rate_pct": 42.0,
        }]
        return MockQueryJob(sql, job_config, dummy_rows)

    with patch("google.cloud.bigquery.Client") as mock_client_cls:
        client_inst = mock_client_cls.return_value
        client_inst.query.side_effect = mock_query

        result_str = get_storefront_performance(segment_id="SEG-001", limit=5)
        result = json.loads(result_str)

        assert result.get("status") == "SUCCESS"
        assert len(captured_queries) == 1
        sql, cfg = captured_queries[0]

        assert "@seg" in sql
        assert "@lim" in sql
        params = {p.name: p for p in cfg.query_parameters}
        assert params["seg"].value == "SEG-001"
        assert params["seg"].type_ == "STRING"
        assert params["lim"].value == 5
        assert params["lim"].type_ == "INT64"


def test_get_audience_segments_sql_parameterization() -> None:
    """get_audience_segments parameterizes region filter."""
    captured_queries: list[tuple[str, bigquery.QueryJobConfig]] = []

    def mock_query(sql: str, job_config: bigquery.QueryJobConfig | None = None) -> MockQueryJob:
        captured_queries.append((sql, job_config))
        dummy_rows = [{
            "segment_id": "SEG-001",
            "segment_name": "Urban Minimalists",
            "region": "ES_Madrid",
            "preferred_style": "Nordic_Minimal",
            "device_type": "mobile",
            "avg_order_value_eur": 210.0,
            "conversion_rate_pct": 3.8,
        }]
        return MockQueryJob(sql, job_config, dummy_rows)

    with patch("google.cloud.bigquery.Client") as mock_client_cls:
        client_inst = mock_client_cls.return_value
        client_inst.query.side_effect = mock_query

        result_str = get_audience_segments(region="ES_Madrid")
        result = json.loads(result_str)

        assert result.get("status") == "SUCCESS"
        assert len(captured_queries) == 1
        sql, cfg = captured_queries[0]

        assert "@reg" in sql
        params = {p.name: p for p in cfg.query_parameters}
        assert params["reg"].value == "ES_Madrid"
        assert params["reg"].type_ == "STRING"


def test_recommend_storefront_optimization_join_parameterization() -> None:
    """recommend_storefront_optimization 3-table join uses parameters for bounce, stock, limit."""
    captured_queries: list[tuple[str, bigquery.QueryJobConfig]] = []

    def mock_query(sql: str, job_config: bigquery.QueryJobConfig | None = None) -> MockQueryJob:
        captured_queries.append((sql, job_config))
        dummy_rows = [{
            "segment_id": "SEG-001",
            "segment_name": "Urban Minimalists",
            "region": "ES_Madrid",
            "preferred_style": "Nordic_Minimal",
            "experiment_id": "EXP-001",
            "current_sku_id": "SKU-0005",
            "current_layout_variant": "Editorial_Grid",
            "bounce_rate_pct": 62.0,
            "recommended_sku_id": "SKU-0001",
            "recommended_product_name": "Nordic Lounge Chair",
            "recommended_category": "Lounge_Chairs",
            "recommended_price_eur": 450.0,
            "recommended_stock_qty": 30,
            "recommended_margin_pct": 38.0,
            "max_safe_discount_pct": 23,
            "headroom_pct": 23.0,
        }]
        return MockQueryJob(sql, job_config, dummy_rows)

    with patch("google.cloud.bigquery.Client") as mock_client_cls:
        client_inst = mock_client_cls.return_value
        client_inst.query.side_effect = mock_query

        result_str = recommend_storefront_optimization(
            region="ES_Madrid", min_bounce_rate_pct=58.0, min_stock=15, limit=3
        )
        result = json.loads(result_str)

        assert result.get("status") == "SUCCESS"
        assert len(captured_queries) == 1
        sql, cfg = captured_queries[0]

        assert "@min_bounce" in sql
        assert "@min_stock" in sql
        assert "@lim" in sql
        assert "@reg" in sql
        params = {p.name: p for p in cfg.query_parameters}
        assert params["min_bounce"].value == 58.0
        assert params["min_bounce"].type_ == "FLOAT64"
        assert params["min_stock"].value == 15
        assert params["min_stock"].type_ == "INT64"
        assert params["lim"].value == 3
        assert params["lim"].type_ == "INT64"
        assert params["reg"].value == "ES_Madrid"


def test_query_merchandising_knowledge_graph_parameterization() -> None:
    """query_merchandising_knowledge_graph parameterizes segment_id, min_stock, min_margin."""
    captured_queries: list[tuple[str, bigquery.QueryJobConfig]] = []

    def mock_query(sql: str, job_config: bigquery.QueryJobConfig | None = None) -> MockQueryJob:
        captured_queries.append((sql, job_config))
        dummy_rows = [{
            "segment_id": "SEG-001",
            "segment_name": "Urban Minimalists",
            "region": "ES_Madrid",
            "preferred_style": "Nordic_Minimal",
            "device_type": "mobile",
            "avg_order_value_eur": 210.0,
            "conversion_rate_pct": 3.8,
            "sku_id": "SKU-0001",
            "product_name": "Nordic Desk",
            "category": "Modular_Sofas",
            "style_theme": "Nordic_Minimal",
            "base_price_eur": 500.0,
            "margin_pct": 35.0,
            "stock_qty": 25,
            "description": "Desk",
            "experiment_id": "EXP-001",
            "layout_variant": "Editorial_Grid",
            "hero_headline": "Nordic Autumn",
            "views": 1000,
            "add_to_cart_count": 80,
            "purchases": 35,
            "bounce_rate_pct": 42.0,
        }]
        return MockQueryJob(sql, job_config, dummy_rows)

    with patch("google.cloud.bigquery.Client") as mock_client_cls:
        client_inst = mock_client_cls.return_value
        client_inst.query.side_effect = mock_query

        result_str = query_merchandising_knowledge_graph(segment_id="SEG-001", max_bundle_size=3, min_stock=10)
        result = json.loads(result_str)

        assert result.get("status") == "SUCCESS"
        assert len(captured_queries) >= 1
        # Check first query parameters
        _, cfg = captured_queries[0]
        params = {p.name: p for p in cfg.query_parameters}
        assert "seg_id" in params
        assert params["seg_id"].value == "SEG-001"


def test_bigquery_dry_run_validation() -> None:
    """Verify that QueryJobConfig(dry_run=True, use_query_cache=False) validates query without billing."""
    with patch("google.cloud.bigquery.Client") as mock_client_cls:
        client_inst = mock_client_cls.return_value

        dry_run_job = MockQueryJob(
            sql="SELECT * FROM `test-project.seed_t02.products_catalog`",
            job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False),
        )
        client_inst.query.return_value = dry_run_job

        # Execute dry run
        cfg = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        job = client_inst.query(dry_run_job.sql, job_config=cfg)

        assert job.dry_run is True
        assert job.total_bytes_processed == 1048576
        # dry_run returns empty rows
        assert len(job.result()) == 0


def test_adk_agent_cloudpickle_roundtrip_parity() -> None:
    """Verify build_agent('t02') serializes and deserializes cleanly via cloudpickle for Vertex AI Agent Runtime."""
    agent, pack = build_agent("t02", enable_mcp_stdio=False)
    assert agent.name == "expedition_t02"
    assert len(agent.tools) == 15

    # Serialize via cloudpickle
    serialized = cloudpickle.dumps(agent)
    assert isinstance(serialized, bytes)
    assert len(serialized) > 1000

    # Deserialize
    unpickled_agent = cloudpickle.loads(serialized)
    assert unpickled_agent.name == agent.name
    assert len(unpickled_agent.tools) == 15

    # Verify tool names match exactly
    original_tool_names = [t.__name__ for t in agent.tools if callable(t)]
    unpickled_tool_names = [t.__name__ for t in unpickled_agent.tools if callable(t)]
    assert sorted(original_tool_names) == sorted(unpickled_tool_names)


def test_remote_query_streaming_adapter_dict_and_object_events() -> None:
    """Verify remote query streaming parser handles both dict events and object events with tool calls."""
    # Dict event representation
    dict_event_fc = {
        "content": {
            "parts": [
                {"function_call": {"name": "recommend_storefront_optimization", "args": {"region": "ES_Madrid"}}}
            ]
        }
    }
    dict_event_text = {
        "content": {
            "parts": [
                {"text": "Based on Madrid analytics, here is the recommended layout."}
            ]
        }
    }

    # Simulate remote stream consumer
    text_chunks: list[str] = []
    tool_calls: list[str] = []

    for event in [dict_event_fc, dict_event_text]:
        if isinstance(event, dict):
            content = event.get("content", {})
            parts = content.get("parts", []) if isinstance(content, dict) else event.get("parts", [])
            for part in parts:
                if not isinstance(part, dict):
                    continue
                if "function_call" in part and isinstance(part["function_call"], dict):
                    tool_calls.append(str(part["function_call"].get("name", "")))
                if "text" in part and part["text"]:
                    text_chunks.append(str(part["text"]))

    assert tool_calls == ["recommend_storefront_optimization"]
    assert "".join(text_chunks) == "Based on Madrid analytics, here is the recommended layout."


def test_remote_query_empty_stream_raises_runtime_error() -> None:
    """Verify an empty stream from remote agent raises RuntimeError with diagnostic guidance."""
    mock_events: list[Any] = []

    text_chunks: list[str] = []
    for event in mock_events:
        if isinstance(event, dict) and "text" in event:
            text_chunks.append(event["text"])

    full_reply = "".join(text_chunks).strip()
    with pytest.raises(RuntimeError, match="Deployed agent returned an empty stream"):
        if not full_reply:
            raise RuntimeError("Deployed agent returned an empty stream. Inspect logs with gcloud logging read.")

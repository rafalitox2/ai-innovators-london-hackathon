"""Offline ADK evaluator, metric registry, and trajectory evaluation tests for Table 2."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from google.adk.evaluation.agent_evaluator import AgentEvaluator
from google.adk.evaluation.eval_case import IntermediateData, Invocation
from google.adk.evaluation.eval_metrics import (
    EvalMetric,
    EvalStatus,
    HallucinationsCriterion,
    JudgeModelOptions,
    Rubric,
    RubricScore,
    RubricsBasedCriterion,
)
from google.adk.evaluation.eval_set import EvalSet
from google.adk.evaluation.gcs_eval_set_results_manager import GcsEvalSetResultsManager
from google.adk.evaluation.gcs_eval_sets_manager import GcsEvalSetsManager
from google.adk.evaluation.hallucinations_v1 import HallucinationsV1Evaluator
from google.adk.evaluation.in_memory_eval_sets_manager import InMemoryEvalSetsManager
from google.adk.evaluation.local_eval_sets_manager import LocalEvalSetsManager
from google.adk.evaluation.metric_evaluator_registry import MetricEvaluatorRegistry
from google.adk.evaluation.response_evaluator import ResponseEvaluator
from google.adk.evaluation.rubric_based_evaluator import AutoRaterScore, RubricBasedEvaluator
from google.adk.evaluation.rubric_based_final_response_quality_v1 import (
    RubricBasedFinalResponseQualityV1Evaluator,
)
from google.adk.evaluation.rubric_based_tool_use_quality_v1 import (
    RubricBasedToolUseV1Evaluator,
)
from google.adk.evaluation.safety_evaluator import SafetyEvaluatorV1
from google.adk.evaluation.trajectory_evaluator import TrajectoryEvaluator
from google.adk.evaluation.vertex_ai_eval_facade import _SingleTurnVertexAiEvalFacade
import google.genai.types as types

APP_NAME = "expedition_t02_app"
MODEL_ID_FROM_ENV = os.environ.get("GEMINI_MODEL", "model-from-env")
GOLDEN_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "seed_packs"
    / "t02_dynamic_storefronts"
    / "eval"
    / "golden.test.json"
)


def test_golden_eval_set_schema_and_config_discovery() -> None:
    """Validate Table 2 golden evaluation dataset against ADK EvalSet schema and config lookup."""
    assert GOLDEN_PATH.is_file(), f"Expected golden file at {GOLDEN_PATH}"
    content = GOLDEN_PATH.read_text(encoding="utf-8")

    eval_set = EvalSet.model_validate_json(content)
    assert eval_set.eval_set_id == "t02_dynamic_storefronts_golden_eval_set"
    assert len(eval_set.eval_cases) == 13

    # Verify each case has valid ID and conversation invocations
    for case in eval_set.eval_cases:
        assert case.eval_id.startswith("case_")
        assert len(case.conversation) >= 1
        for inv in case.conversation:
            assert inv.user_content is not None
            assert len(inv.user_content.parts) >= 1

    # Verify AgentEvaluator config discovery
    cfg = AgentEvaluator.find_config_for_test_file(GOLDEN_PATH)
    assert cfg is not None
    assert "tool_trajectory_avg_score" in cfg.criteria
    assert cfg.criteria["tool_trajectory_avg_score"] >= 0.8
    assert "response_match_score" in cfg.criteria


def test_trajectory_evaluator_exact_match_score() -> None:
    """TrajectoryEvaluator scores 1.0 PASSED when actual matches expected tool calls."""
    evaluator = TrajectoryEvaluator(threshold=0.8)

    inv_act = Invocation(
        user_content=types.Content(parts=[types.Part.from_text(text="Show products")]),
        intermediate_data=IntermediateData(
            tool_uses=[
                types.FunctionCall(
                    name="find_catalog_products",
                    args={"category": "Modular_Sofas", "min_stock": 10},
                )
            ]
        ),
    )
    inv_exp = Invocation(
        user_content=types.Content(parts=[types.Part.from_text(text="Show products")]),
        intermediate_data=IntermediateData(
            tool_uses=[
                types.FunctionCall(
                    name="find_catalog_products",
                    args={"category": "Modular_Sofas", "min_stock": 10},
                )
            ]
        ),
    )

    result = evaluator.evaluate_invocations([inv_act], [inv_exp])
    assert result.overall_score == 1.0
    assert result.overall_eval_status == EvalStatus.PASSED
    assert len(result.per_invocation_results) == 1
    assert result.per_invocation_results[0].score == 1.0


def test_trajectory_evaluator_mismatch_fails_threshold() -> None:
    """TrajectoryEvaluator scores 0.0 FAILED when tool trajectory mismatches."""
    evaluator = TrajectoryEvaluator(threshold=0.8)

    inv_act = Invocation(
        user_content=types.Content(parts=[types.Part.from_text(text="Check bounce")]),
        intermediate_data=IntermediateData(
            tool_uses=[
                types.FunctionCall(
                    name="get_audience_segments",
                    args={"region": "ES_Madrid"},
                )
            ]
        ),
    )
    inv_exp = Invocation(
        user_content=types.Content(parts=[types.Part.from_text(text="Check bounce")]),
        intermediate_data=IntermediateData(
            tool_uses=[
                types.FunctionCall(
                    name="get_storefront_performance",
                    args={"segment_id": "SEG-001"},
                )
            ]
        ),
    )

    result = evaluator.evaluate_invocations([inv_act], [inv_exp])
    assert result.overall_score == 0.0
    assert result.overall_eval_status == EvalStatus.FAILED


def test_trajectory_evaluator_multi_tool_chain() -> None:
    """TrajectoryEvaluator handles multi-step tool call sequences for Table 2 workflows."""
    evaluator = TrajectoryEvaluator(threshold=0.8)

    chain_calls = [
        types.FunctionCall(name="get_audience_segments", args={"region": "ES_Madrid"}),
        types.FunctionCall(
            name="recommend_storefront_optimization",
            args={"region": "ES_Madrid", "min_bounce_rate_pct": 55.0},
        ),
        types.FunctionCall(
            name="render_storefront_preview",
            args={"segment_id": "SEG-001", "discount_pct": 20},
        ),
    ]

    inv_act = Invocation(
        user_content=types.Content(parts=[types.Part.from_text(text="Run storefront pipeline")]),
        intermediate_data=IntermediateData(tool_uses=chain_calls),
    )
    inv_exp = Invocation(
        user_content=types.Content(parts=[types.Part.from_text(text="Run storefront pipeline")]),
        intermediate_data=IntermediateData(tool_uses=chain_calls),
    )

    res_perfect = evaluator.evaluate_invocations([inv_act], [inv_exp])
    assert res_perfect.overall_score == 1.0
    assert res_perfect.overall_eval_status == EvalStatus.PASSED

    # Partial/mismatched trajectory: one tool omitted or replaced
    partial_calls = chain_calls[:2] + [
        types.FunctionCall(name="unrelated_tool", args={})
    ]
    inv_act_partial = Invocation(
        user_content=types.Content(parts=[types.Part.from_text(text="Run storefront pipeline")]),
        intermediate_data=IntermediateData(tool_uses=partial_calls),
    )
    res_partial = evaluator.evaluate_invocations([inv_act_partial], [inv_exp])
    assert res_partial.overall_score == 0.0
    assert res_partial.overall_eval_status == EvalStatus.FAILED


def test_response_evaluator_rouge_matching() -> None:
    """ResponseEvaluator computes token match score against expected golden response."""
    evaluator = ResponseEvaluator(threshold=0.75, metric_name="response_match_score")

    inv_act = Invocation(
        user_content=types.Content(parts=[types.Part.from_text(text="Status")]),
        final_response=types.Content(
            parts=[types.Part.from_text(text="AtelierNova storefront preview for SEG-001 generated with 20% discount.")]
        ),
    )
    inv_exp = Invocation(
        user_content=types.Content(parts=[types.Part.from_text(text="Status")]),
        final_response=types.Content(
            parts=[types.Part.from_text(text="AtelierNova storefront preview for SEG-001 generated with 20% discount.")]
        ),
    )

    res = evaluator.evaluate_invocations([inv_act], [inv_exp])
    assert res.overall_score == 1.0
    assert res.overall_eval_status == EvalStatus.PASSED

    # Mismatched response fails threshold
    inv_mismatch = Invocation(
        user_content=types.Content(parts=[types.Part.from_text(text="Status")]),
        final_response=types.Content(
            parts=[types.Part.from_text(text="Completely unrelated error text.")]
        ),
    )
    res_mismatch = evaluator.evaluate_invocations([inv_mismatch], [inv_exp])
    assert res_mismatch.overall_score is not None
    assert res_mismatch.overall_score < 0.75
    assert res_mismatch.overall_eval_status == EvalStatus.FAILED


def test_safety_evaluator_v1_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """SafetyEvaluatorV1 evaluates invocation harmlessness via mocked Vertex AI facade."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "t02-eval-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "europe-west1")

    metric = EvalMetric(metric_name="safety_v1", threshold=0.8)
    
    with patch("vertexai.Client"):
        safety_eval = SafetyEvaluatorV1(eval_metric=metric)

    inv = Invocation(
        user_content=types.Content(parts=[types.Part.from_text(text="Evaluate SKU-0017 safety")]),
        final_response=types.Content(
            parts=[types.Part.from_text(text="Security alert: injection marker blocked and quarantined.")]
        ),
    )

    with patch.object(_SingleTurnVertexAiEvalFacade, "_perform_eval", return_value={"mock_key": 1}), \
         patch.object(_SingleTurnVertexAiEvalFacade, "_get_score", return_value=0.98):
        result = safety_eval.evaluate_invocations([inv], [inv])
        assert result.overall_score == 0.98
        assert result.overall_eval_status == EvalStatus.PASSED


@pytest.mark.asyncio
async def test_hallucinations_v1_evaluator_offline() -> None:
    """HallucinationsV1Evaluator checks factual consistency using mocked NL judge rater."""
    criterion = HallucinationsCriterion(
        threshold=0.8,
        judge_model_options=JudgeModelOptions(judge_model=MODEL_ID_FROM_ENV),
    )
    metric = EvalMetric(metric_name="hallucinations_v1", criterion=criterion)
    mock_judge = MagicMock()

    with patch.object(HallucinationsV1Evaluator, "_setup_auto_rater", return_value=mock_judge):
        evaluator = HallucinationsV1Evaluator(eval_metric=metric)

    inv = Invocation(
        user_content=types.Content(parts=[types.Part.from_text(text="Recommend stock")]),
        final_response=types.Content(
            parts=[types.Part.from_text(text="SKU-0012 stock is verified at 42 units.")]
        ),
    )

    async def _mock_nl_response(nl_response: str, context: Any) -> tuple[float, dict[str, Any]]:
        return 0.95, {"claims_checked": 1}

    evaluator._evaluate_nl_response = _mock_nl_response  # type: ignore[assignment]
    result = await evaluator.evaluate_invocations([inv])
    assert result.overall_score == 0.95
    assert result.overall_eval_status == EvalStatus.PASSED


@pytest.mark.asyncio
async def test_rubric_based_tool_and_final_response_evaluators() -> None:
    """RubricBasedToolUseV1Evaluator and RubricBasedFinalResponseQualityV1Evaluator offline execution."""
    criterion = RubricsBasedCriterion(
        rubrics=[
            Rubric(
                rubric_id="tool_accuracy",
                rubric_content={"text_property": "The agent selects the appropriate tool with valid arguments."},
            )
        ],
        threshold=0.8,
        judge_model_options=JudgeModelOptions(judge_model=MODEL_ID_FROM_ENV),
    )

    mock_judge = MagicMock()
    with patch.object(RubricBasedEvaluator, "_setup_auto_rater", return_value=mock_judge):
        tool_metric = EvalMetric(metric_name="rubric_based_tool_use_quality_v1", criterion=criterion)
        tool_evaluator = RubricBasedToolUseV1Evaluator(eval_metric=tool_metric)

        response_metric = EvalMetric(metric_name="rubric_based_final_response_quality_v1", criterion=criterion)
        response_evaluator = RubricBasedFinalResponseQualityV1Evaluator(eval_metric=response_metric)

    inv = Invocation(
        user_content=types.Content(parts=[types.Part.from_text(text="Optimize storefront")]),
        final_response=types.Content(parts=[types.Part.from_text(text="Optimized layout rendered.")]),
        intermediate_data=IntermediateData(
            tool_uses=[types.FunctionCall(name="recommend_storefront_optimization", args={"region": "all"})]
        ),
    )

    mock_sample_result = AutoRaterScore(
        score=1.0,
        rubric_scores=[RubricScore(rubric_id="tool_accuracy", score=1.0, rationale="Valid tool selection")],
    )

    with patch.object(tool_evaluator, "convert_auto_rater_response_to_score", return_value=mock_sample_result):
        async def _mock_stream_tool(req: Any) -> Any:
            yield types.GenerateContentResponse()
        tool_evaluator._judge_model.generate_content_async = _mock_stream_tool  # type: ignore[assignment]

        res_tool = await tool_evaluator.evaluate_invocations([inv], [inv])
        assert res_tool.overall_score == 1.0
        assert res_tool.overall_eval_status == EvalStatus.PASSED

    with patch.object(response_evaluator, "convert_auto_rater_response_to_score", return_value=mock_sample_result):
        async def _mock_stream_resp(req: Any) -> Any:
            yield types.GenerateContentResponse()
        response_evaluator._judge_model.generate_content_async = _mock_stream_resp  # type: ignore[assignment]

        res_resp = await response_evaluator.evaluate_invocations([inv], [inv])
        assert res_resp.overall_score == 1.0
        assert res_resp.overall_eval_status == EvalStatus.PASSED


def test_metric_evaluator_registry_catalog() -> None:
    """MetricEvaluatorRegistry contains all official ADK evaluators used in Table 2."""
    registry = MetricEvaluatorRegistry()
    registered_names = {m.metric_name for m in registry.get_registered_metrics()}

    expected_metrics = {
        "tool_trajectory_avg_score",
        "response_match_score",
        "safety_v1",
        "hallucinations_v1",
        "rubric_based_tool_use_quality_v1",
        "rubric_based_final_response_quality_v1",
    }
    for m in expected_metrics:
        assert m in registered_names, f"Missing registered metric: {m}"


def test_in_memory_and_local_eval_sets_managers(tmp_path: Path) -> None:
    """InMemoryEvalSetsManager and LocalEvalSetsManager support CRUD lifecycle for eval sets."""
    from google.adk.evaluation.eval_case import EvalCase

    case_1 = EvalCase(
        eval_id="case_001",
        conversation=[
            Invocation(user_content=types.Content(parts=[types.Part.from_text(text="Hello")]))
        ],
    )

    # 1. InMemoryEvalSetsManager
    in_mem = InMemoryEvalSetsManager()
    eval_set_id = "mem_set_t02"
    in_mem.create_eval_set(app_name=APP_NAME, eval_set_id=eval_set_id)
    assert eval_set_id in in_mem.list_eval_sets(app_name=APP_NAME)

    in_mem.add_eval_case(app_name=APP_NAME, eval_set_id=eval_set_id, eval_case=case_1)
    retrieved_case = in_mem.get_eval_case(app_name=APP_NAME, eval_set_id=eval_set_id, eval_case_id="case_001")
    assert retrieved_case.eval_id == "case_001"

    # Update case
    case_1_updated = EvalCase(
        eval_id="case_001",
        conversation=[
            Invocation(user_content=types.Content(parts=[types.Part.from_text(text="Updated Hello")]))
        ],
    )
    in_mem.update_eval_case(app_name=APP_NAME, eval_set_id=eval_set_id, updated_eval_case=case_1_updated)
    read_updated = in_mem.get_eval_case(app_name=APP_NAME, eval_set_id=eval_set_id, eval_case_id="case_001")
    assert read_updated.conversation[0].user_content.parts[0].text == "Updated Hello"

    # Delete case
    in_mem.delete_eval_case(app_name=APP_NAME, eval_set_id=eval_set_id, eval_case_id="case_001")
    assert len(in_mem.get_eval_set(app_name=APP_NAME, eval_set_id=eval_set_id).eval_cases) == 0

    # 2. LocalEvalSetsManager
    local_mgr = LocalEvalSetsManager(agents_dir=str(tmp_path))
    local_set_id = "local_set_t02"
    local_mgr.create_eval_set(app_name=APP_NAME, eval_set_id=local_set_id)
    assert local_set_id in local_mgr.list_eval_sets(app_name=APP_NAME)
    local_mgr.add_eval_case(app_name=APP_NAME, eval_set_id=local_set_id, eval_case=case_1)
    read_local = local_mgr.get_eval_set(app_name=APP_NAME, eval_set_id=local_set_id)
    assert len(read_local.eval_cases) == 1


def test_gcs_eval_sets_and_results_managers_mocked() -> None:
    """GcsEvalSetsManager and GcsEvalSetResultsManager interact with Cloud Storage API."""
    mock_storage_client = MagicMock()
    mock_bucket = MagicMock()
    mock_bucket.exists.return_value = True
    mock_storage_client.bucket.return_value = mock_bucket

    mock_blob = MagicMock()
    mock_blob.exists.return_value = True
    mock_blob.download_as_text.return_value = json.dumps({
        "eval_set_id": "gcs_t02",
        "eval_cases": [],
    })
    mock_bucket.blob.return_value = mock_blob

    with patch("google.cloud.storage.Client", return_value=mock_storage_client):
        # GcsEvalSetsManager
        gcs_mgr = GcsEvalSetsManager(bucket_name="test-t02-eval-bucket")
        assert gcs_mgr.bucket_name == "test-t02-eval-bucket"

        # GcsEvalSetResultsManager
        results_mgr = GcsEvalSetResultsManager(bucket_name="test-t02-eval-bucket")
        assert results_mgr.bucket_name == "test-t02-eval-bucket"
        mock_blob.download_as_text.return_value = json.dumps({
            "eval_set_result_id": "res_001",
            "eval_set_id": "gcs_t02",
            "eval_case_results": [],
        })
        res = results_mgr.get_eval_set_result(app_name=APP_NAME, eval_set_result_id="res_001")
        assert res.eval_set_result_id == "res_001"

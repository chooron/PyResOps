"""Lightweight tests for Stage 3 MCP tools and scenario builder."""

from __future__ import annotations

import pytest
import yaml


# ---------------------------------------------------------------------------
# Import smoke tests
# ---------------------------------------------------------------------------

def test_stage3_imports():
    from experiments.stage3 import __doc__ as doc
    assert doc is not None

    from experiments.stage3.tool_registry import (
        STATIC_TOOL_CHAIN,
        DYNAMIC_REPLAN_CHAIN,
        DYNAMIC_RETAIN_CHAIN,
        ROLLING_REPLAN_CHAIN,
        ROLLING_RETAIN_CHAIN,
        REQUIRED_TOOLS,
        WORKFLOW_CHAINS,
    )
    from experiments.stage3.mcp_tools import build_stage3_scenario, list_static_events, list_dynamic_events, list_rolling_events
    from experiments.stage3.payload_schema import ReservoirDecisionPayload, validate_structured_payload, payload_to_stage3_row
    from experiments.stage3.fail_closed_validator import ValidationResult, validate_stage3_decision
    from experiments.stage3.session_trace import SessionTraceLogger
    from experiments.stage3.llm_runner import Stage3LlmRunner
    from experiments.stage3.comparator import Stage3Comparator
    from experiments.stage3.reporting import (
        generate_stage3_outputs,
        generate_stage3_comparison,
        generate_stage3_summary,
    )


def test_tool_registry_chains():
    from experiments.stage3.tool_registry import (
        STATIC_TOOL_CHAIN,
        DYNAMIC_REPLAN_CHAIN,
        DYNAMIC_RETAIN_CHAIN,
        ROLLING_REPLAN_CHAIN,
        ROLLING_RETAIN_CHAIN,
        WORKFLOW_CHAINS,
    )

    assert STATIC_TOOL_CHAIN == [
        "prepare_event",
        "optimize_release_plan",
        "simulate_release_plan",
        "evaluate_release_plan",
    ]
    assert DYNAMIC_RETAIN_CHAIN == ["simulate_release_plan", "evaluate_release_plan"]
    assert ROLLING_RETAIN_CHAIN == []
    assert "static" in WORKFLOW_CHAINS
    assert "dynamic_replan" in WORKFLOW_CHAINS
    assert "dynamic_retain" in WORKFLOW_CHAINS
    assert "rolling_replan" in WORKFLOW_CHAINS
    assert "rolling_retain" in WORKFLOW_CHAINS


def test_config_loads():
    with open("experiments/config/stage3_llm_mcp.yml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert cfg["model_profile"] in ("mimo_v25", "deepseek_v4_pro")
    assert "dynamic_events" in cfg
    assert "rolling_events" in cfg
    assert len(cfg["dynamic_events"]) == 10
    assert len(cfg["rolling_events"]) == 10
    assert "mcp" in cfg


def test_scenario_builder():
    """build_stage3_scenario returns a valid scenario dict from a real event."""
    from unittest.mock import MagicMock
    from pathlib import Path
    from datetime import datetime
    from experiments.data_adapters.real_events import FloodEventData, FloodEventRecord
    from experiments.stage3.mcp_tools import build_stage3_scenario

    records = [
        FloodEventRecord(
            time=datetime(2024, 7, 1 + (i * 3) // 24, (i * 3) % 24, 0),
            prcp=0.0,
            level=156.0 + i * 0.1,
            inflow=1000.0 + i * 50,
            outflow=800.0,
            predict=950.0 + i * 50,
        )
        for i in range(8)
    ]
    event = FloodEventData(
        event_id="test_event",
        source_path=Path("data/flood_event/test_event.csv"),
        records=records,
        time_step_hours=3,
        has_prediction=True,
    )

    # adapter.to_payload returns the canonical MCP-compatible payload
    expected_payload = {
        "id": "test_event_static",
        "workflow_type": "static",
        "benchmark_inflow_series_m3s": [1000.0 + i * 50 for i in range(8)],
        "start_time": datetime(2024, 7, 1, 0, 0),
        "current_level": 156.0,
        "initial_storage": 1e8,
        "initial_inflow": 1000.0,
        "time_step_hours": 3,
        "target_level": 160.0,
        "target_level_tolerance": 0.5,
        "data_source": {"event_id": "test_event", "path": "data/flood_event/test_event.csv"},
    }

    adapter = MagicMock()
    adapter.load_event.return_value = event
    adapter.data_root = Path("data")
    adapter.to_payload.return_value = dict(expected_payload)

    scenario = build_stage3_scenario(
        event_id="test_event",
        workflow_type="static",
        adapter=adapter,
        workflow_stage="static",
        offset_hours=0,
        use_predict=False,
        operator_instruction="",
        replan_reason="initial",
    )

    assert scenario["workflow_type"] == "static"
    assert scenario["stage_id"] == "static"
    assert "benchmark_inflow_series_m3s" in scenario
    assert len(scenario["benchmark_inflow_series_m3s"]) > 0
    assert "flood_limit_level" in scenario
    assert scenario["replan_reason"] == "initial"
    assert "start_time" in scenario

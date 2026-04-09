"""Tests for decision trace persistence."""

from pyresops.storage import Repository


def test_save_and_load_decision_trace() -> None:
    repo = Repository(":memory:")
    trace_data = {
        "program_id": "prog_1",
        "steps": [{"step_index": 0, "resolved_outflow": 8000.0}],
    }

    repo.save_decision_trace(trace_id="trace_1", program_id="prog_1", trace_data=trace_data)
    loaded = repo.load_decision_trace("trace_1")

    assert loaded is not None
    assert loaded["program_id"] == "prog_1"
    assert len(loaded["steps"]) == 1


def test_list_decision_traces() -> None:
    repo = Repository(":memory:")
    repo.save_decision_trace(
        trace_id="trace_a",
        program_id="prog_a",
        trace_data={"program_id": "prog_a", "steps": []},
    )
    repo.save_decision_trace(
        trace_id="trace_b",
        program_id="prog_b",
        trace_data={"program_id": "prog_b", "steps": []},
    )

    all_rows = repo.list_decision_traces(limit=10)
    assert len(all_rows) == 2

    filtered = repo.list_decision_traces(program_id="prog_a", limit=10)
    assert len(filtered) == 1
    assert filtered[0]["program_id"] == "prog_a"

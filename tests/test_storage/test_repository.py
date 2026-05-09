"""Tests for SQLite repository persistence."""

import pytest

from pyresops.storage import Repository


@pytest.fixture
def repo():
    """创建内存数据库仓库."""
    return Repository(db_path=":memory:")


class TestProgramPersistence:
    """方案持久化测试."""

    def test_save_and_load(self, repo):
        data = {"program_id": "p1", "name": "测试方案", "modules": ["constant_release"]}
        repo.save_program("p1", data)

        loaded = repo.load_program("p1")
        assert loaded is not None
        assert loaded["name"] == "测试方案"

    def test_load_nonexistent(self, repo):
        assert repo.load_program("nonexistent") is None

    def test_list_programs(self, repo):
        repo.save_program("p1", {"name": "方案1", "created_at": "2024-01-01"})
        repo.save_program("p2", {"name": "方案2", "created_at": "2024-01-02"})

        programs = repo.list_programs()
        assert len(programs) == 2


class TestSimulationResultPersistence:
    """仿真结果持久化测试."""

    def test_save_and_load(self, repo):
        data = {
            "program_id": "p1",
            "max_level": 170.0,
            "min_level": 160.0,
            "avg_outflow": 8000.0,
            "snapshot_count": 24,
        }
        repo.save_simulation_result("p1", data)

        loaded = repo.load_simulation_result("p1")
        assert loaded is not None
        assert loaded["max_level"] == 170.0


class TestEvaluationResultPersistence:
    """评估结果持久化测试."""

    def test_save_and_load(self, repo):
        data = {
            "program_id": "p1",
            "overall_score": 88.0,
            "flood_control_score": 90.0,
            "water_supply_score": 86.0,
            "violations_count": 0,
        }
        repo.save_evaluation_result("p1", data)

        loaded = repo.load_evaluation_result("p1")
        assert loaded is not None
        assert loaded["overall_score"] == 88.0


class TestSnapshotPersistence:
    """快照持久化测试."""

    def test_save_snapshot(self, repo):
        state = {
            "timestamp": "2024-07-01T00:00:00",
            "level": 165.0,
            "storage": 30.0,
            "inflow": 8000.0,
            "outflow": 8000.0,
        }
        repo.save_snapshot("res1", state)
        # 不报错即通过


class TestEventLogging:
    """事件记录测试."""

    def test_log_and_list(self, repo):
        repo.log_event("simulation", reservoir_id="res1", program_id="p1", description="仿真完成")
        repo.log_event("evaluation", reservoir_id="res1", program_id="p1", description="评估完成")

        events = repo.list_events()
        assert len(events) == 2

    def test_filter_by_type(self, repo):
        repo.log_event("simulation", description="仿真")
        repo.log_event("evaluation", description="评估")

        events = repo.list_events(event_type="simulation")
        assert len(events) == 1

    def test_filter_by_reservoir(self, repo):
        repo.log_event("simulation", reservoir_id="res1")
        repo.log_event("simulation", reservoir_id="res2")

        events = repo.list_events(reservoir_id="res1")
        assert len(events) == 1


class TestContextManager:
    """上下文管理器测试."""

    def test_with_statement(self):
        with Repository(db_path=":memory:") as repo:
            repo.save_program("p1", {"name": "test"})
            assert repo.load_program("p1") is not None


class TestFinalizedRecordPersistence:
    """最终方案历史记录测试."""

    def test_append_only_records(self, repo):
        repo.save_finalized_record(
            finalized_id="f1",
            reservoir_id="res1",
            context_id="ctx1",
            program_id="p1_final",
            source_program_id="p1",
            supersedes_id=None,
            version=1,
            record_data={"overall_score": 80.0},
        )
        repo.save_finalized_record(
            finalized_id="f2",
            reservoir_id="res1",
            context_id="ctx1",
            program_id="p2_final",
            source_program_id="p2",
            supersedes_id="f1",
            version=2,
            record_data={"overall_score": 82.0},
        )

        records = repo.list_finalized_records(reservoir_id="res1", context_id="ctx1")
        assert len(records) == 2
        ids = {item["finalized_id"] for item in records}
        assert "f1" in ids and "f2" in ids

    def test_finalized_unique_version_guard(self, repo):
        repo.save_finalized_record(
            finalized_id="f1",
            reservoir_id="res1",
            context_id="ctx1",
            program_id="p1_final",
            source_program_id="p1",
            supersedes_id=None,
            version=1,
            record_data={},
        )

        with pytest.raises(Exception):
            repo.save_finalized_record(
                finalized_id="f2",
                reservoir_id="res1",
                context_id="ctx1",
                program_id="p2_final",
                source_program_id="p2",
                supersedes_id="f1",
                version=1,
                record_data={},
            )

"""Storage layer: duplicate writes, evaluation_result, edge cases."""

import pytest

from res_ops.storage import Repository


@pytest.fixture
def repo():
    return Repository(db_path=":memory:")


class TestDuplicateWrites:
    """重复写入覆盖"""

    def test_program_overwrite(self, repo):
        repo.save_program("p1", {"name": "v1"})
        repo.save_program("p1", {"name": "v2"})
        loaded = repo.load_program("p1")
        assert loaded["name"] == "v2"

    def test_simulation_result_overwrite(self, repo):
        repo.save_simulation_result("p1", {"max_level": 100})
        repo.save_simulation_result("p1", {"max_level": 200})
        loaded = repo.load_simulation_result("p1")
        assert loaded["max_level"] == 200

    def test_snapshot_overwrite(self, repo):
        repo.save_snapshot("r1", {"timestamp": "2024-07-01T00:00:00", "level": 100})
        repo.save_snapshot("r1", {"timestamp": "2024-07-01T00:00:00", "level": 200})
        # 不报错即通过 (INSERT OR REPLACE)

    def test_finalized_records_do_not_overwrite(self, repo):
        repo.save_finalized_record(
            finalized_id="fin_1",
            reservoir_id="r1",
            context_id="ctx",
            program_id="p1_final",
            source_program_id="p1",
            supersedes_id=None,
            version=1,
            record_data={"score": 70},
        )
        repo.save_finalized_record(
            finalized_id="fin_2",
            reservoir_id="r1",
            context_id="ctx",
            program_id="p2_final",
            source_program_id="p2",
            supersedes_id="fin_1",
            version=2,
            record_data={"score": 80},
        )
        records = repo.list_finalized_records(reservoir_id="r1", context_id="ctx")
        assert len(records) == 2


class TestEvaluationResultSave:
    def test_save_evaluation_result(self, repo):
        repo.save_evaluation_result(
            "p1",
            {
                "overall_score": 85.5,
                "flood_control_score": 90.0,
                "water_supply_score": 80.0,
                "violations_count": 1,
            },
        )
        # 不报错即通过


class TestEventLogging:
    def test_event_with_data(self, repo):
        repo.log_event(
            "simulation",
            reservoir_id="r1",
            program_id="p1",
            description="洪水调度",
            data={"peak": 15000, "duration": 48},
        )
        events = repo.list_events()
        assert len(events) == 1

    def test_event_without_data(self, repo):
        repo.log_event("manual_override", description="人工接管")
        events = repo.list_events()
        assert len(events) == 1
        assert events[0]["data"] is None

    def test_event_limit(self, repo):
        for i in range(20):
            repo.log_event("test", description=f"event_{i}")
        events = repo.list_events(limit=5)
        assert len(events) == 5

    def test_combined_filters(self, repo):
        repo.log_event("sim", reservoir_id="r1", description="a")
        repo.log_event("sim", reservoir_id="r2", description="b")
        repo.log_event("eval", reservoir_id="r1", description="c")
        events = repo.list_events(event_type="sim", reservoir_id="r1")
        assert len(events) == 1


class TestProgramListOrder:
    """方案列表按时间倒序"""

    def test_list_order(self, repo):
        repo.save_program("p1", {"name": "first", "created_at": "2024-01-01"})
        repo.save_program("p2", {"name": "second", "created_at": "2024-06-01"})
        programs = repo.list_programs()
        assert len(programs) == 2
        assert programs[0]["program_id"] == "p2"  # 倒序


class TestRepositoryClose:
    def test_close_and_reopen(self, repo):
        repo.save_program("p1", {"name": "test"})
        repo.close()
        # 关闭后再操作应报错
        with pytest.raises(Exception):
            repo.save_program("p2", {"name": "fail"})

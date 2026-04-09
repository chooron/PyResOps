"""Repository for storing programs, simulation results, and cases."""

import json
import sqlite3
from datetime import datetime
from typing import Any


class Repository:
    """数据仓库 (Repository) - SQLite 持久化."""

    def __init__(self, db_path: str = ":memory:"):
        """初始化仓库并建表."""
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        """创建表结构."""
        cur = self._conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS programs (
                program_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                data TEXT NOT NULL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS simulation_results (
                program_id TEXT PRIMARY KEY,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                max_level REAL,
                min_level REAL,
                avg_outflow REAL,
                snapshot_count INTEGER,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS evaluation_results (
                program_id TEXT PRIMARY KEY,
                overall_score REAL,
                flood_control_score REAL,
                water_supply_score REAL,
                violations_count INTEGER,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                reservoir_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                level REAL,
                storage REAL,
                inflow REAL,
                outflow REAL,
                data TEXT,
                PRIMARY KEY (reservoir_id, timestamp)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                reservoir_id TEXT,
                program_id TEXT,
                description TEXT,
                data TEXT,
                created_at TEXT NOT NULL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS finalized_plans (
                finalized_id TEXT PRIMARY KEY,
                reservoir_id TEXT NOT NULL,
                context_id TEXT NOT NULL,
                program_id TEXT NOT NULL,
                source_program_id TEXT NOT NULL,
                supersedes_id TEXT,
                version INTEGER NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (reservoir_id, context_id, version)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS decision_traces (
                trace_id TEXT PRIMARY KEY,
                program_id TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        self._conn.commit()

    # ── Programs ──────────────────────────────────────────────

    def save_program(self, program_id: str, program_data: dict[str, Any]) -> None:
        """保存调度方案."""
        cur = self._conn.cursor()
        cur.execute(
            """INSERT OR REPLACE INTO programs (program_id, name, created_at, data)
               VALUES (?, ?, ?, ?)""",
            (
                program_id,
                program_data.get("name", ""),
                program_data.get("created_at", datetime.now().isoformat()),
                json.dumps(program_data, default=str),
            ),
        )
        self._conn.commit()

    def load_program(self, program_id: str) -> dict[str, Any] | None:
        """加载调度方案."""
        cur = self._conn.cursor()
        cur.execute("SELECT data FROM programs WHERE program_id = ?", (program_id,))
        row = cur.fetchone()
        if row:
            return json.loads(row["data"])
        return None

    def list_programs(self) -> list[dict[str, Any]]:
        """列出所有方案摘要."""
        cur = self._conn.cursor()
        cur.execute("SELECT program_id, name, created_at FROM programs ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    # ── Simulation Results ────────────────────────────────────

    def save_simulation_result(self, program_id: str, result_data: dict[str, Any]) -> None:
        """保存仿真结果."""
        cur = self._conn.cursor()
        cur.execute(
            """INSERT OR REPLACE INTO simulation_results
               (program_id, start_time, end_time, max_level, min_level,
                avg_outflow, snapshot_count, data, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                program_id,
                result_data.get("start_time", ""),
                result_data.get("end_time", ""),
                result_data.get("max_level", 0.0),
                result_data.get("min_level", 0.0),
                result_data.get("avg_outflow", 0.0),
                result_data.get("snapshot_count", 0),
                json.dumps(result_data, default=str),
                datetime.now().isoformat(),
            ),
        )
        self._conn.commit()

    def load_simulation_result(self, program_id: str) -> dict[str, Any] | None:
        """加载仿真结果."""
        cur = self._conn.cursor()
        cur.execute("SELECT data FROM simulation_results WHERE program_id = ?", (program_id,))
        row = cur.fetchone()
        if row:
            return json.loads(row["data"])
        return None

    # ── Evaluation Results ────────────────────────────────────

    def save_evaluation_result(self, program_id: str, eval_data: dict[str, Any]) -> None:
        """保存评估结果."""
        cur = self._conn.cursor()
        cur.execute(
            """INSERT OR REPLACE INTO evaluation_results
               (program_id, overall_score, flood_control_score, water_supply_score,
                violations_count, data, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                program_id,
                eval_data.get("overall_score", 0.0),
                eval_data.get("flood_control_score", 0.0),
                eval_data.get("water_supply_score", 0.0),
                eval_data.get("violations_count", 0),
                json.dumps(eval_data, default=str),
                datetime.now().isoformat(),
            ),
        )
        self._conn.commit()

    def load_evaluation_result(self, program_id: str) -> dict[str, Any] | None:
        """加载评估结果."""
        cur = self._conn.cursor()
        cur.execute("SELECT data FROM evaluation_results WHERE program_id = ?", (program_id,))
        row = cur.fetchone()
        if row:
            return json.loads(row["data"])
        return None

    # ── Snapshots ─────────────────────────────────────────────

    def save_snapshot(self, reservoir_id: str, state_data: dict[str, Any]) -> None:
        """保存水库状态快照."""
        cur = self._conn.cursor()
        cur.execute(
            """INSERT OR REPLACE INTO snapshots
               (reservoir_id, timestamp, level, storage, inflow, outflow, data)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                reservoir_id,
                state_data.get("timestamp", datetime.now().isoformat()),
                state_data.get("level", 0.0),
                state_data.get("storage", 0.0),
                state_data.get("inflow", 0.0),
                state_data.get("outflow", 0.0),
                json.dumps(state_data, default=str),
            ),
        )
        self._conn.commit()

    # ── Events (for case retrieval) ───────────────────────────

    def log_event(
        self,
        event_type: str,
        reservoir_id: str | None = None,
        program_id: str | None = None,
        description: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        """记录事件 (供未来案例检索)."""
        cur = self._conn.cursor()
        cur.execute(
            """INSERT INTO events (event_type, reservoir_id, program_id, description, data, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                event_type,
                reservoir_id,
                program_id,
                description,
                json.dumps(data, default=str) if data else None,
                datetime.now().isoformat(),
            ),
        )
        self._conn.commit()

    def list_events(
        self,
        event_type: str | None = None,
        reservoir_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """查询事件记录."""
        cur = self._conn.cursor()
        query = "SELECT * FROM events WHERE 1=1"
        params: list[Any] = []
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        if reservoir_id:
            query += " AND reservoir_id = ?"
            params.append(reservoir_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]

    # ── Finalized Plans (append-only) ─────────────────────────

    def save_finalized_record(
        self,
        *,
        finalized_id: str,
        reservoir_id: str,
        context_id: str,
        program_id: str,
        source_program_id: str,
        supersedes_id: str | None,
        version: int,
        record_data: dict[str, Any],
    ) -> None:
        """Save append-only finalized plan record."""
        cur = self._conn.cursor()
        cur.execute(
            """INSERT INTO finalized_plans
               (finalized_id, reservoir_id, context_id, program_id, source_program_id,
                supersedes_id, version, data, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                finalized_id,
                reservoir_id,
                context_id,
                program_id,
                source_program_id,
                supersedes_id,
                version,
                json.dumps(record_data, default=str),
                datetime.now().isoformat(),
            ),
        )
        self._conn.commit()

    def list_finalized_records(
        self,
        *,
        reservoir_id: str | None = None,
        context_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List finalized plan records in append-only history order."""
        cur = self._conn.cursor()
        query = "SELECT * FROM finalized_plans WHERE 1=1"
        params: list[Any] = []

        if reservoir_id:
            query += " AND reservoir_id = ?"
            params.append(reservoir_id)
        if context_id:
            query += " AND context_id = ?"
            params.append(context_id)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cur.execute(query, params)
        rows = [dict(row) for row in cur.fetchall()]

        for row in rows:
            row["data"] = json.loads(row["data"])

        return rows

    # ── Decision Traces ────────────────────────────────────────

    def save_decision_trace(
        self, *, trace_id: str, program_id: str, trace_data: dict[str, Any]
    ) -> None:
        """Save decision trace payload."""
        cur = self._conn.cursor()
        cur.execute(
            """INSERT OR REPLACE INTO decision_traces
               (trace_id, program_id, data, created_at)
               VALUES (?, ?, ?, ?)""",
            (
                trace_id,
                program_id,
                json.dumps(trace_data, default=str),
                datetime.now().isoformat(),
            ),
        )
        self._conn.commit()

    def load_decision_trace(self, trace_id: str) -> dict[str, Any] | None:
        """Load decision trace by trace id."""
        cur = self._conn.cursor()
        cur.execute("SELECT data FROM decision_traces WHERE trace_id = ?", (trace_id,))
        row = cur.fetchone()
        if row:
            return json.loads(row["data"])
        return None

    def list_decision_traces(
        self,
        *,
        program_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List decision traces."""
        cur = self._conn.cursor()
        query = "SELECT * FROM decision_traces WHERE 1=1"
        params: list[Any] = []
        if program_id:
            query += " AND program_id = ?"
            params.append(program_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cur.execute(query, params)
        rows = [dict(row) for row in cur.fetchall()]
        for row in rows:
            row["data"] = json.loads(row["data"])
        return rows

    # ── Cleanup ───────────────────────────────────────────────

    def close(self) -> None:
        """关闭数据库连接."""
        self._conn.close()

    def __enter__(self) -> "Repository":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

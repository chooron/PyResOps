"""Stage 2 vs Stage 1 oracle comparator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


_TOL_MAX_LEVEL = 0.5
_TOL_TERMINAL_DEV = 0.5
_TOL_PEAK_REDUCTION = 0.05

# Align on event_id + workflow_stage only: stage1 derives scenario_type from
# workflow_stage (e.g. "T0" → scenario_type="T0"), while stage2 uses canonical
# names ("dynamic", "rolling"). workflow_stage values are unique across types.
_ALIGN_KEYS = ["event_id", "workflow_stage"]


class Stage2Comparator:
    """Aligns Stage 2 results against Stage 1 oracle and reports discrepancies."""

    def __init__(self) -> None:
        self._s1: pd.DataFrame | None = None
        self._s2: pd.DataFrame | None = None

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------

    def load_stage1(self, stage1_dir: str | Path) -> "Stage2Comparator":
        d = Path(stage1_dir)
        frames = []
        static_csv = d / "static" / "all_events_metrics.csv"
        dynamic_csv = d / "dynamic" / "stage_results.csv"
        rolling_csv = d / "rolling" / "stage_results.csv"
        for csv in (static_csv, dynamic_csv, rolling_csv):
            if csv.exists():
                frames.append(pd.read_csv(csv))
        self._s1 = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        return self

    def load_stage2(self, stage2_dir: str | Path) -> "Stage2Comparator":
        d = Path(stage2_dir)
        frames = []
        static_csv = d / "static" / "all_events_metrics.csv"
        dynamic_csv = d / "dynamic" / "stage_results.csv"
        rolling_csv = d / "rolling" / "stage_results.csv"
        for csv in (static_csv, dynamic_csv, rolling_csv):
            if csv.exists():
                frames.append(pd.read_csv(csv))
        self._s2 = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        return self

    def load_stage2_from_metrics(
        self,
        static: list[dict],
        dynamic: list[dict],
        rolling: list[dict],
    ) -> "Stage2Comparator":
        all_rows = static + dynamic + rolling
        self._s2 = pd.DataFrame(all_rows) if all_rows else pd.DataFrame()
        return self

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    def compare(self) -> dict[str, Any]:
        if self._s1 is None or self._s2 is None:
            raise RuntimeError("Load both stage1 and stage2 before comparing.")

        s1 = self._s1.copy()
        s2 = self._s2.copy()

        # Normalise scenario_type for rolling rows (stage1 uses "rolling_Xh" prefix)
        for df in (s1, s2):
            if "scenario_type" not in df.columns and "workflow_stage" in df.columns:
                df["scenario_type"] = df["workflow_stage"].apply(
                    lambda x: "rolling" if str(x).startswith("rolling") else x
                )

        # Build align keys; fill missing with empty string
        for df in (s1, s2):
            for k in _ALIGN_KEYS:
                if k not in df.columns:
                    df[k] = ""

        def _make_key(df: pd.DataFrame) -> pd.Series:
            if df.empty:
                return pd.Series(dtype=str)
            return df[_ALIGN_KEYS].astype(str).agg("__".join, axis=1)

        s1_key = _make_key(s1)
        s2_key = _make_key(s2)

        s1_set = set(s1_key)
        s2_set = set(s2_key)

        matched_keys = s1_set & s2_set
        missing_in_s2 = s1_set - s2_set
        extra_in_s2 = s2_set - s1_set

        s1_idx = s1.copy()
        if not s1_idx.empty:
            s1_idx["_key"] = s1_key
        else:
            s1_idx["_key"] = pd.Series(dtype=str)
        s2_idx = s2.copy()
        if not s2_idx.empty:
            s2_idx["_key"] = s2_key
        else:
            s2_idx["_key"] = pd.Series(dtype=str)

        merged = s1_idx[s1_idx["_key"].isin(matched_keys)].merge(
            s2_idx[s2_idx["_key"].isin(matched_keys)],
            on="_key",
            suffixes=("_s1", "_s2"),
        )

        def _col(name: str, suffix: str) -> str:
            return f"{name}_{suffix}" if f"{name}_{suffix}" in merged.columns else name

        # accepted mismatch
        accepted_mismatch = 0
        if "accepted_s1" in merged.columns and "accepted_s2" in merged.columns:
            accepted_mismatch = int((merged["accepted_s1"] != merged["accepted_s2"]).sum())

        # tolerance failures
        def _tol_failures(col: str, tol: float) -> int:
            c1, c2 = _col(col, "s1"), _col(col, "s2")
            if c1 in merged.columns and c2 in merged.columns:
                return int((abs(merged[c1] - merged[c2]) > tol).sum())
            return 0

        max_level_failures = _tol_failures("max_level", _TOL_MAX_LEVEL)
        terminal_dev_failures = _tol_failures("terminal_deviation", _TOL_TERMINAL_DEV)
        peak_reduction_failures = _tol_failures("peak_reduction_rate", _TOL_PEAK_REDUCTION)

        # per-workflow summary
        # Stage 1 dynamic rows have scenario_type="T0"/"T1"/... (derived from workflow_stage),
        # so classify by workflow_stage prefix rather than scenario_type.
        def _wf_rows(df: pd.DataFrame, wf_type: str) -> int:
            if df.empty or "workflow_stage" not in df.columns:
                return 0
            if wf_type == "static":
                return int((df["workflow_stage"] == "static").sum())
            if wf_type == "dynamic":
                return int(df["workflow_stage"].str.match(r"^T\d+$", na=False).sum())
            if wf_type == "rolling":
                return int(df["workflow_stage"].str.startswith("rolling_", na=False).sum())
            return 0

        workflow_summary: dict[str, dict] = {}
        for wf_type in ("static", "dynamic", "rolling"):
            workflow_summary[wf_type] = {
                "s1_rows": _wf_rows(s1, wf_type),
                "s2_rows": _wf_rows(s2, wf_type),
            }

        passes_oracle = (
            accepted_mismatch == 0
            and max_level_failures == 0
            and terminal_dev_failures == 0
            and peak_reduction_failures == 0
            and len(missing_in_s2) == 0
        )

        return {
            "s1_total": len(s1),
            "s2_total": len(s2),
            "matched_rows": len(matched_keys),
            "missing_in_s2": len(missing_in_s2),
            "extra_in_s2": len(extra_in_s2),
            "missing_keys": sorted(missing_in_s2)[:20],
            "extra_keys": sorted(extra_in_s2)[:20],
            "accepted_mismatch": accepted_mismatch,
            "max_level_failures": max_level_failures,
            "terminal_deviation_failures": terminal_dev_failures,
            "peak_reduction_failures": peak_reduction_failures,
            "workflow_summary": workflow_summary,
            "passes_oracle": passes_oracle,
        }

    def to_report(self) -> dict[str, Any]:
        return self.compare()

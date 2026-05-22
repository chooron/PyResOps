"""Stage 3 vs Stage 2 oracle comparator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


_TOL_MAX_LEVEL = 0.5
_TOL_TERMINAL_DEV = 0.5
_TOL_PEAK_REDUCTION = 0.05

_ALIGN_KEYS = ["event_id", "workflow_stage"]


class Stage3Comparator:
    """Aligns Stage 3 accepted results against Stage 2 oracle."""

    def __init__(self) -> None:
        self._s2: pd.DataFrame | None = None
        self._s3: pd.DataFrame | None = None

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------

    def load_stage2(self, stage2_dir: str | Path) -> "Stage3Comparator":
        d = Path(stage2_dir)
        frames = []
        for csv in (
            d / "static" / "all_events_metrics.csv",
            d / "dynamic" / "stage_results.csv",
            d / "rolling" / "stage_results.csv",
        ):
            if csv.exists():
                frames.append(pd.read_csv(csv))
        self._s2 = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        return self

    def load_stage3(self, stage3_dir: str | Path) -> "Stage3Comparator":
        d = Path(stage3_dir)
        frames = []
        for csv in (
            d / "static" / "results.csv",
            d / "dynamic" / "results.csv",
            d / "rolling" / "results.csv",
        ):
            if csv.exists():
                frames.append(pd.read_csv(csv))
        self._s3 = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        return self

    def load_stage3_from_metrics(
        self,
        static: list[dict],
        dynamic: list[dict],
        rolling: list[dict],
    ) -> "Stage3Comparator":
        all_rows = static + dynamic + rolling
        self._s3 = pd.DataFrame(all_rows) if all_rows else pd.DataFrame()
        return self

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    def compare(self) -> dict[str, Any]:
        if self._s2 is None or self._s3 is None:
            raise RuntimeError("Load both stage2 and stage3 before comparing.")

        s2 = self._s2.copy()
        s3 = self._s3.copy()

        for df in (s2, s3):
            for k in _ALIGN_KEYS:
                if k not in df.columns:
                    df[k] = ""

        def _make_key(df: pd.DataFrame) -> pd.Series:
            if df.empty:
                return pd.Series(dtype=str)
            return df[_ALIGN_KEYS].astype(str).agg("__".join, axis=1)

        s2_key = _make_key(s2)
        s3_key = _make_key(s3)

        s2_set = set(s2_key)
        s3_set = set(s3_key)

        matched_keys = s2_set & s3_set
        missing_in_s3 = s2_set - s3_set
        extra_in_s3 = s3_set - s2_set

        s2_idx = s2.copy()
        if not s2_idx.empty:
            s2_idx["_key"] = s2_key
        else:
            s2_idx["_key"] = pd.Series(dtype=str)

        s3_idx = s3.copy()
        if not s3_idx.empty:
            s3_idx["_key"] = s3_key
        else:
            s3_idx["_key"] = pd.Series(dtype=str)

        merged = s2_idx[s2_idx["_key"].isin(matched_keys)].merge(
            s3_idx[s3_idx["_key"].isin(matched_keys)],
            on="_key",
            suffixes=("_s2", "_s3"),
        )

        def _tol_failures(col: str, tol: float) -> int:
            c2 = f"{col}_s2" if f"{col}_s2" in merged.columns else col
            c3 = f"{col}_s3" if f"{col}_s3" in merged.columns else col
            if c2 in merged.columns and c3 in merged.columns:
                return int((abs(pd.to_numeric(merged[c2], errors="coerce") - pd.to_numeric(merged[c3], errors="coerce")) > tol).sum())
            return 0

        max_level_failures = _tol_failures("max_level", _TOL_MAX_LEVEL)
        terminal_dev_failures = _tol_failures("terminal_deviation", _TOL_TERMINAL_DEV)
        peak_reduction_failures = _tol_failures("peak_reduction_rate", _TOL_PEAK_REDUCTION)

        # Stage 3 specific: acceptance stats
        s3_accepted = 0
        s3_total = len(s3)
        if not s3.empty and "accepted" in s3.columns:
            s3_accepted = int(s3["accepted"].sum())

        # Failure taxonomy
        failure_taxonomy: dict[str, int] = {}
        if not s3.empty and "failure_reason" in s3.columns:
            counts = s3[~s3["accepted"].astype(bool)]["failure_reason"].value_counts()
            failure_taxonomy = {str(k): int(v) for k, v in counts.items()}

        # Tool-order / eval-ref / schema failures
        def _flag_count(col: str) -> int:
            if not s3.empty and col in s3.columns:
                return int(s3[col].astype(bool).sum())
            return 0

        # Per-workflow summary
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
                "s2_rows": _wf_rows(s2, wf_type),
                "s3_rows": _wf_rows(s3, wf_type),
                "s3_accepted": _wf_rows(
                    s3[s3["accepted"].astype(bool)] if "accepted" in s3.columns else pd.DataFrame(),
                    wf_type,
                ),
            }

        passes_oracle = (
            len(missing_in_s3) == 0
            and max_level_failures == 0
            and terminal_dev_failures == 0
            and peak_reduction_failures == 0
        )

        return {
            "s2_total": len(s2),
            "s3_total": s3_total,
            "s3_accepted": s3_accepted,
            "s3_rejected": s3_total - s3_accepted,
            "matched_rows": len(matched_keys),
            "missing_in_s3": len(missing_in_s3),
            "extra_in_s3": len(extra_in_s3),
            "missing_keys": sorted(missing_in_s3)[:20],
            "extra_keys": sorted(extra_in_s3)[:20],
            "max_level_failures": max_level_failures,
            "terminal_deviation_failures": terminal_dev_failures,
            "peak_reduction_failures": peak_reduction_failures,
            "tool_order_failures": _flag_count("wrong_tool_order"),
            "eval_ref_failures": _flag_count("missing_eval_ref") + _flag_count("stale_eval_ref"),
            "schema_failures": _flag_count("llm_output_parse_error"),
            "hard_violations": _flag_count("hard_violation"),
            "downstream_violations": _flag_count("downstream_violation"),
            "failure_taxonomy": failure_taxonomy,
            "workflow_summary": workflow_summary,
            "passes_oracle": passes_oracle,
        }

    def to_report(self) -> dict[str, Any]:
        return self.compare()

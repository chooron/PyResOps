"""Real flood-event CSV loading for workflow experiments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd

from experiments.data_adapters.preprocessing import (
    DEFAULT_EXPECTED_TIME_STEP_HOURS,
    REQUIRED_COLUMNS,
    inspect_time_axis,
)
from pyresops.agents.specs import load_default_experiment_spec


PREDICT_COLUMN = "predict"


@dataclass(frozen=True)
class FloodEventRecord:
    time: datetime
    prcp: float | None
    level: float | None
    inflow: float | None
    outflow: float | None
    predict: float | None = None


@dataclass(frozen=True)
class DataQualitySummary:
    event_id: str
    raw_path: str
    processed_path: str | None
    raw_row_count: int
    processed_row_count: int
    inflow_missing_count_raw: int
    outflow_missing_count_raw: int
    rows_dropped_due_to_missing_inflow: int
    outflow_filled_by_inflow_count: int
    outflow_fallback_applied: bool
    inflow_drop_applied: bool
    valid_time_axis: bool
    non_increasing_time_count: int
    irregular_time_step_count: int
    expected_time_step_hours: int
    strict_clean_eligible: bool
    repaired_executable_eligible: bool
    diagnostic_only: bool
    event_class: str
    notes: str = ""
    time_axis_anomalies: tuple[str, ...] = ()
    data_quality_status: str = "diagnostic_only"
    reason: str = ""

    @property
    def missing_inflow_count(self) -> int:
        return self.inflow_missing_count_raw

    @property
    def missing_outflow_count(self) -> int:
        return self.outflow_missing_count_raw

    @property
    def time_axis_invalid(self) -> bool:
        return not self.valid_time_axis


@dataclass(frozen=True)
class FloodEventData:
    event_id: str
    source_path: Path
    records: list[FloodEventRecord]
    time_step_hours: int
    has_prediction: bool
    time_step_anomalies: tuple[str, ...] = ()
    forecast_error_pattern: str | None = None
    raw_source_path: Path | None = None
    quality_summary: DataQualitySummary | None = None

    @property
    def duration_hours(self) -> int:
        return self.time_step_hours * max(len(self.records) - 1, 0)

    def first_valid_index(self) -> int:
        for index, record in enumerate(self.records):
            if record.level is not None and record.inflow is not None:
                return index
        raise ValueError(f"{self.event_id}: no row has level and inflow")

    def slice_from_hour(self, offset_hours: int) -> "FloodEventData":
        if offset_hours < 0:
            raise ValueError("offset_hours must be non-negative")
        if offset_hours % self.time_step_hours != 0:
            raise ValueError(
                f"{self.event_id}: offset {offset_hours}h is not aligned to "
                f"{self.time_step_hours}h time step"
            )
        start_index = offset_hours // self.time_step_hours
        if start_index >= len(self.records):
            raise ValueError(f"{self.event_id}: offset {offset_hours}h exceeds event length")
        return FloodEventData(
            event_id=self.event_id,
            source_path=self.source_path,
            records=self.records[start_index:],
            time_step_hours=self.time_step_hours,
            has_prediction=self.has_prediction,
            time_step_anomalies=self.time_step_anomalies,
            forecast_error_pattern=self.forecast_error_pattern,
            raw_source_path=self.raw_source_path,
            quality_summary=self.quality_summary,
        )


class RealEventDataAdapter:
    """Load real CSVs and derive workflow payloads without synthetic data."""

    def __init__(
        self,
        data_root: Path | str = "data",
        *,
        quality_manifest_path: Path | str = (
            "experiments/results/data_quality/event_quality_manifest.csv"
        ),
    ):
        self.data_root = Path(data_root)
        self.flood_event_dir = self.data_root / "flood_event"
        self.processed_flood_event_dir = self.data_root / "processed" / "flood_event"
        self.quality_manifest_path = Path(quality_manifest_path)
        self.spec = load_default_experiment_spec()
        self.flood_limit_level = float(self.spec.flood_limit_level)
        self._quality_manifest_cache: dict[str, DataQualitySummary] | None = None

    def list_raw_flood_event_files(self) -> list[Path]:
        if not self.flood_event_dir.exists():
            raise FileNotFoundError(f"Missing flood event directory: {self.flood_event_dir}")
        return sorted(self.flood_event_dir.glob("*.csv"))

    def list_flood_event_files(self) -> list[Path]:
        return self.list_raw_flood_event_files()

    def load_all_flood_events(self, *, use_processed: bool = True) -> list[FloodEventData]:
        return [
            self.load_event(path.stem, prefer_processed=use_processed)
            for path in self.list_raw_flood_event_files()
        ]

    def load_event(
        self,
        event: str | Path,
        *,
        prefer_processed: bool = True,
    ) -> FloodEventData:
        path = self._resolve_event_path(event, prefer_processed=prefer_processed)
        frame = self._read_csv(path)
        self._validate_columns(path, frame, required=REQUIRED_COLUMNS)
        records = self._records_from_frame(frame, include_predict=PREDICT_COLUMN in frame.columns)
        step, anomalies = self._resolve_time_step(path, records)
        raw_source = self._resolve_raw_source_path(event, fallback=path)
        quality = self._quality_for_event(
            event_id=path.stem,
            raw_path=raw_source,
            loaded_path=path,
            records=records,
            expected_time_step_hours=step,
            anomalies=tuple(anomalies),
        )
        return FloodEventData(
            event_id=path.stem,
            source_path=path,
            records=records,
            time_step_hours=step,
            has_prediction=PREDICT_COLUMN in frame.columns,
            time_step_anomalies=tuple(anomalies),
            raw_source_path=raw_source,
            quality_summary=quality,
        )

    def load_predicted_event(self, path: str | Path | None = None) -> FloodEventData:
        resolved = Path(path) if path is not None else self.data_root / "withpred" / "2024072617.csv"
        if not resolved.exists() and resolved.name == "2024072617_with_pred.csv":
            fallback = self.data_root / "withpred" / "2024072617.csv"
            if fallback.exists():
                resolved = fallback
        frame = self._read_csv(resolved)
        self._validate_columns(resolved, frame, required=(*REQUIRED_COLUMNS, PREDICT_COLUMN))
        records = self._records_from_frame(frame, include_predict=True)
        step, anomalies = self._resolve_time_step(resolved, records)
        if anomalies:
            raise ValueError(f"{resolved}: invalid predicted-event time step: {anomalies}")
        quality = self._legacy_quality_summary(
            event_id=resolved.stem,
            raw_path=resolved,
            loaded_path=resolved,
            records=records,
            expected_time_step_hours=step,
            anomalies=(),
        )
        return FloodEventData(
            event_id=resolved.stem,
            source_path=resolved,
            records=records,
            time_step_hours=step,
            has_prediction=True,
            time_step_anomalies=(),
            raw_source_path=resolved,
            quality_summary=quality,
        )

    def load_forecast_error_event(self, event: str | Path, pattern: str) -> FloodEventData:
        """Derive a rolling forecast-stress case from a real observed flood event."""

        loaded = self.load_event(event)
        inflows = [record.inflow for record in loaded.records]
        if any(value is None for value in inflows):
            raise ValueError(f"{loaded.event_id}: forecast stress requires complete inflow")
        predictions = self._forecast_error_predictions(
            [float(value) for value in inflows if value is not None],
            pattern,
        )
        records = [
            FloodEventRecord(
                time=record.time,
                prcp=record.prcp,
                level=record.level,
                inflow=record.inflow,
                outflow=record.outflow,
                predict=predictions[index],
            )
            for index, record in enumerate(loaded.records)
        ]
        quality = loaded.quality_summary or self.quality_summary(loaded)
        return FloodEventData(
            event_id=f"{loaded.event_id}_with_pred_{pattern}",
            source_path=loaded.source_path,
            records=records,
            time_step_hours=loaded.time_step_hours,
            has_prediction=True,
            time_step_anomalies=loaded.time_step_anomalies,
            forecast_error_pattern=pattern,
            raw_source_path=loaded.raw_source_path,
            quality_summary=quality,
        )

    def to_payload(
        self,
        event: FloodEventData,
        *,
        workflow_type: str,
        scenario_id: str | None = None,
        stage_offset_hours: int = 0,
        operator_instruction: str | None = None,
        carry_over_plan: dict[str, Any] | None = None,
        target_level: float | None = None,
        target_level_tolerance: float | None = None,
        agent_workflow_profile: str | None = None,
    ) -> dict[str, Any]:
        sliced = event.slice_from_hour(stage_offset_hours) if stage_offset_hours else event
        quality = self.quality_summary(sliced)
        if quality.time_axis_invalid:
            raise ValueError(
                f"{event.event_id}: invalid time step inside workflow horizon: "
                f"{list(sliced.time_step_anomalies)}"
            )
        first_index = sliced.first_valid_index()
        first = sliced.records[first_index]
        usable_records = sliced.records[first_index:]
        inflows = self._required_series(usable_records, "inflow")
        outflows = self._outflow_series_with_fallback(
            usable_records,
            allow_fallback=not self._should_block_runtime_outflow_fallback(quality),
        )
        prcp = [0.0 if record.prcp is None else float(record.prcp) for record in usable_records]
        level = float(first.level)
        mean_inflow = sum(inflows) / len(inflows)
        resolved_target = (
            float(target_level)
            if target_level is not None
            else min(self.flood_limit_level, max(self.spec.dead_level, level))
        )
        payload: dict[str, Any] = {
            "id": scenario_id or f"{workflow_type}_{event.event_id}_{stage_offset_hours}h",
            "name": f"{workflow_type} real-data workflow for {event.event_id}",
            "description": (
                f"Real CSV event {event.source_path.as_posix()} with observed inflow/outflow; "
                "no synthetic flood generation."
            ),
            "workflow_type": workflow_type,
            "data_source": {
                "path": event.source_path.as_posix(),
                "raw_path": (
                    event.raw_source_path.as_posix()
                    if event.raw_source_path is not None
                    else event.source_path.as_posix()
                ),
                "processed_path": quality.processed_path,
                "event_id": event.event_id,
                "uses_real_observed_inflow": True,
                "uses_synthetic_data": False,
                "uses_processed_data": (
                    quality.processed_path is not None
                    and event.source_path.as_posix() == quality.processed_path
                ),
                "forecast_error_pattern": event.forecast_error_pattern,
                "missing_inflow_count": quality.missing_inflow_count,
                "missing_outflow_count": quality.missing_outflow_count,
                "inflow_missing_count_raw": quality.inflow_missing_count_raw,
                "outflow_missing_count_raw": quality.outflow_missing_count_raw,
                "rows_dropped_due_to_missing_inflow": quality.rows_dropped_due_to_missing_inflow,
                "outflow_filled_by_inflow_count": quality.outflow_filled_by_inflow_count,
                "outflow_fallback_applied": quality.outflow_fallback_applied,
                "inflow_drop_applied": quality.inflow_drop_applied,
                "time_axis_invalid": quality.time_axis_invalid,
                "time_axis_anomalies": list(quality.time_axis_anomalies),
                "valid_time_axis": quality.valid_time_axis,
                "non_increasing_time_count": quality.non_increasing_time_count,
                "irregular_time_step_count": quality.irregular_time_step_count,
                "expected_time_step_hours": quality.expected_time_step_hours,
                "strict_clean_eligible": quality.strict_clean_eligible,
                "repaired_executable_eligible": quality.repaired_executable_eligible,
                "diagnostic_only": quality.diagnostic_only,
                "event_class": quality.event_class,
                "data_quality_status": quality.data_quality_status,
                "data_quality_reason": quality.reason,
                "notes": quality.notes,
            },
            "start_time": first.time,
            "flood_limit_level": self.flood_limit_level,
            "current_level": level,
            "initial_storage": float(self.spec.level_storage_curve.get_storage(level)),
            "initial_inflow": float(first.inflow),
            "initial_outflow": outflows[0],
            "inflow": float(mean_inflow),
            "target_level": resolved_target,
            "target_level_tolerance": (
                0.5 if target_level_tolerance is None else float(target_level_tolerance)
            ),
            "season": self._infer_season(first.time),
            "flood_risk": self._infer_risk(level, max(inflows)),
            "duration_hours": sliced.time_step_hours * len(usable_records),
            "time_step_hours": sliced.time_step_hours,
            "benchmark_inflow_series_m3s": inflows,
            "benchmark_observed_outflow_series_m3s": outflows,
            "benchmark_precipitation_series_mm": prcp,
            "stage_offset_hours": int(stage_offset_hours),
            "operator_instruction": operator_instruction or "",
            "temperature_override": 0.0,
            "reproducibility": {"data_event_id": event.event_id},
        }
        if agent_workflow_profile:
            payload["agent_workflow_profile"] = agent_workflow_profile
        if carry_over_plan is not None:
            payload["carry_over_plan"] = dict(carry_over_plan)
        if event.has_prediction:
            predictions = self._required_series(usable_records, "predict")
            payload["benchmark_predicted_inflow_series_m3s"] = predictions
            payload["observed_mean_inflow"] = float(mean_inflow)
            payload["predicted_mean_inflow"] = float(sum(predictions) / len(predictions))
        return payload

    def quality_summary(self, event: FloodEventData) -> DataQualitySummary:
        """Summarize data quality for one event or stage slice."""

        if event.quality_summary is not None:
            return event.quality_summary
        manifest_quality = self._quality_manifest().get(event.event_id)
        if manifest_quality is not None:
            return manifest_quality
        return self._legacy_quality_summary(
            event_id=event.event_id,
            raw_path=event.raw_source_path or event.source_path,
            loaded_path=event.source_path,
            records=event.records,
            expected_time_step_hours=event.time_step_hours,
            anomalies=event.time_step_anomalies,
        )

    def inspect_quality(
        self,
        event: str | Path,
        *,
        stage_offset_hours: int = 0,
        predicted: bool = False,
    ) -> DataQualitySummary:
        loaded = self.load_predicted_event(event) if predicted else self.load_event(event)
        if predicted:
            sliced = loaded.slice_from_hour(stage_offset_hours) if stage_offset_hours else loaded
            return self.quality_summary(sliced)
        manifest_quality = self._quality_manifest().get(loaded.event_id)
        if manifest_quality is not None:
            return manifest_quality
        sliced = loaded.slice_from_hour(stage_offset_hours) if stage_offset_hours else loaded
        return self.quality_summary(sliced)

    def _resolve_event_path(self, event: str | Path, *, prefer_processed: bool) -> Path:
        path = Path(event)
        if path.exists():
            return path
        if path.suffix != ".csv":
            path = path.with_suffix(".csv")
        processed_candidate = self.processed_flood_event_dir / path.name
        raw_candidate = self.flood_event_dir / path.name
        if prefer_processed and processed_candidate.exists():
            return processed_candidate
        if raw_candidate.exists():
            return raw_candidate
        if processed_candidate.exists():
            return processed_candidate
        raise FileNotFoundError(f"Missing real flood event CSV: {raw_candidate}")

    def _resolve_raw_source_path(self, event: str | Path, *, fallback: Path) -> Path:
        path = Path(event)
        if path.exists() and path.parent == self.flood_event_dir:
            return path
        candidate = self.flood_event_dir / (path.name if path.name else fallback.name)
        if candidate.exists():
            return candidate
        return fallback

    @staticmethod
    def _read_csv(path: Path) -> pd.DataFrame:
        read_kwargs = {
            "na_values": ["", " ", "  ", "\u3000", "\u3000\u3000"],
            "keep_default_na": True,
        }
        try:
            return pd.read_csv(path, encoding="utf-8-sig", **read_kwargs)
        except UnicodeDecodeError:
            return pd.read_csv(path, encoding="gb18030", **read_kwargs)

    @staticmethod
    def _validate_columns(path: Path, frame: pd.DataFrame, *, required: tuple[str, ...]) -> None:
        missing = [column for column in required if column not in frame.columns]
        if missing:
            raise ValueError(f"{path}: missing required columns {missing}")

    @staticmethod
    def _records_from_frame(frame: pd.DataFrame, *, include_predict: bool) -> list[FloodEventRecord]:
        records: list[FloodEventRecord] = []
        for row in frame.to_dict(orient="records"):
            records.append(
                FloodEventRecord(
                    time=pd.to_datetime(row["time"]).to_pydatetime(),
                    prcp=RealEventDataAdapter._none_or_float(row.get("prcp")),
                    level=RealEventDataAdapter._none_or_float(row.get("level")),
                    inflow=RealEventDataAdapter._none_or_float(row.get("inflow")),
                    outflow=RealEventDataAdapter._none_or_float(row.get("outflow")),
                    predict=(
                        RealEventDataAdapter._none_or_float(row.get(PREDICT_COLUMN))
                        if include_predict
                        else None
                    ),
                )
            )
        if len(records) < 2:
            raise ValueError("A real event must contain at least two time rows")
        return records

    @staticmethod
    def _resolve_time_step(path: Path, records: list[FloodEventRecord]) -> tuple[int, list[str]]:
        deltas = [
            (records[index + 1].time - records[index].time).total_seconds() / 3600.0
            for index in range(len(records) - 1)
        ]
        positive_deltas = [delta for delta in deltas if delta > 0]
        if not positive_deltas:
            raise ValueError(f"{path}: no positive time step")
        resolved = float(median(positive_deltas))
        anomalies: list[str] = []
        for index, delta in enumerate(deltas):
            if delta <= 0:
                anomalies.append(f"row {index}->{index + 1} non-increasing delta {delta:g}h")
            elif abs(delta - resolved) > 1e-6:
                anomalies.append(f"row {index}->{index + 1} non-uniform delta {delta:g}h")
        if abs(resolved - round(resolved)) > 1e-6:
            anomalies.append(f"median time step is not whole hours: {resolved:g}h")
        return int(round(resolved)), anomalies

    @staticmethod
    def _none_or_float(value: Any) -> float | None:
        if pd.isna(value):
            return None
        return float(value)

    @staticmethod
    def _required_series(records: list[FloodEventRecord], field_name: str) -> list[float]:
        values: list[float] = []
        for record in records:
            value = getattr(record, field_name)
            if value is None:
                raise ValueError(f"Real event has missing {field_name} value inside workflow horizon")
            values.append(float(value))
        if not values:
            raise ValueError(f"Real event has no {field_name} values")
        return values

    @staticmethod
    def _outflow_series_with_fallback(
        records: list[FloodEventRecord],
        *,
        allow_fallback: bool,
    ) -> list[float]:
        values: list[float] = []
        for record in records:
            if record.outflow is not None:
                values.append(float(record.outflow))
                continue
            if record.inflow is None:
                raise ValueError("Real event has missing inflow value inside workflow horizon")
            if not allow_fallback:
                raise ValueError("unexpected_missing_outflow_after_preprocessing")
            values.append(float(record.inflow))
        if not values:
            raise ValueError("Real event has no outflow values")
        return values

    @staticmethod
    def _forecast_error_predictions(inflows: list[float], pattern: str) -> list[float]:
        if not inflows:
            raise ValueError("forecast stress requires non-empty inflow series")
        normalized = pattern.strip().lower().replace("_", "-")
        if normalized == "perfect":
            return list(inflows)
        if normalized in {"under-peak", "underpeak"}:
            return [round(value * 0.8, 3) for value in inflows]
        if normalized in {"over-peak", "overpeak"}:
            return [round(value * 1.2, 3) for value in inflows]
        if normalized == "lag":
            return [inflows[0], *[round(value, 3) for value in inflows[:-1]]]
        if normalized == "lead":
            return [*[round(value, 3) for value in inflows[1:]], inflows[-1]]
        if normalized == "mixed":
            peak_index = max(range(len(inflows)), key=lambda index: inflows[index])
            predictions: list[float] = []
            for index, value in enumerate(inflows):
                factor = 0.85 if index <= peak_index else 1.15
                if index % 3 == 0:
                    factor = 1.0
                predictions.append(round(value * factor, 3))
            return predictions
        raise ValueError(
            f"Unsupported forecast-error pattern {pattern!r}; expected perfect, "
            "under-peak, over-peak, lag, lead, or mixed"
        )

    def _quality_for_event(
        self,
        *,
        event_id: str,
        raw_path: Path,
        loaded_path: Path,
        records: list[FloodEventRecord],
        expected_time_step_hours: int,
        anomalies: tuple[str, ...],
    ) -> DataQualitySummary:
        manifest_quality = self._quality_manifest().get(event_id)
        if manifest_quality is not None:
            return manifest_quality
        return self._legacy_quality_summary(
            event_id=event_id,
            raw_path=raw_path,
            loaded_path=loaded_path,
            records=records,
            expected_time_step_hours=expected_time_step_hours,
            anomalies=anomalies,
        )

    def _legacy_quality_summary(
        self,
        *,
        event_id: str,
        raw_path: Path,
        loaded_path: Path,
        records: list[FloodEventRecord],
        expected_time_step_hours: int,
        anomalies: tuple[str, ...],
    ) -> DataQualitySummary:
        frame = pd.DataFrame(
            {
                "time": [record.time for record in records],
                "level": [record.level for record in records],
                "inflow": [record.inflow for record in records],
                "outflow": [record.outflow for record in records],
            }
        )
        time_check = inspect_time_axis(
            frame,
            expected_time_step_hours=expected_time_step_hours or DEFAULT_EXPECTED_TIME_STEP_HOURS,
        )
        missing_inflow_count = sum(1 for record in records if record.inflow is None)
        missing_outflow_count = sum(1 for record in records if record.outflow is None)
        strict_clean_eligible = (
            missing_inflow_count == 0
            and missing_outflow_count == 0
            and bool(time_check["valid_time_axis"])
        )
        repaired_executable_eligible = missing_inflow_count == 0 and bool(
            time_check["valid_time_axis"]
        )
        event_class = (
            "strict_clean"
            if strict_clean_eligible
            else "repaired_executable"
            if repaired_executable_eligible
            else "diagnostic_only"
        )
        notes = _legacy_notes(
            missing_inflow_count=missing_inflow_count,
            missing_outflow_count=missing_outflow_count,
            valid_time_axis=bool(time_check["valid_time_axis"]),
        )
        return DataQualitySummary(
            event_id=event_id,
            raw_path=raw_path.as_posix(),
            processed_path=(
                loaded_path.as_posix()
                if loaded_path.parent == self.processed_flood_event_dir
                else None
            ),
            raw_row_count=len(records),
            processed_row_count=len(records),
            inflow_missing_count_raw=missing_inflow_count,
            outflow_missing_count_raw=missing_outflow_count,
            rows_dropped_due_to_missing_inflow=0,
            outflow_filled_by_inflow_count=0,
            outflow_fallback_applied=repaired_executable_eligible and missing_outflow_count > 0,
            inflow_drop_applied=False,
            valid_time_axis=bool(time_check["valid_time_axis"]) and not anomalies,
            non_increasing_time_count=int(time_check["non_increasing_time_count"]),
            irregular_time_step_count=int(time_check["irregular_time_step_count"]) + len(anomalies),
            expected_time_step_hours=int(
                expected_time_step_hours or DEFAULT_EXPECTED_TIME_STEP_HOURS
            ),
            strict_clean_eligible=strict_clean_eligible and not anomalies,
            repaired_executable_eligible=repaired_executable_eligible and not anomalies,
            diagnostic_only=event_class == "diagnostic_only" or bool(anomalies),
            event_class=(
                event_class
                if not anomalies
                else "diagnostic_only"
            ),
            notes=notes,
            time_axis_anomalies=anomalies,
            data_quality_status=(
                "strict_clean"
                if strict_clean_eligible and not anomalies
                else "repaired_executable"
                if repaired_executable_eligible and not anomalies
                else "diagnostic_only"
            ),
            reason=notes,
        )

    def _quality_manifest(self) -> dict[str, DataQualitySummary]:
        if self._quality_manifest_cache is not None:
            return self._quality_manifest_cache
        if not self.quality_manifest_path.exists():
            self._quality_manifest_cache = {}
            return self._quality_manifest_cache
        frame = pd.read_csv(self.quality_manifest_path, encoding="utf-8-sig")
        manifest: dict[str, DataQualitySummary] = {}
        for row in frame.to_dict(orient="records"):
            event_id = str(row.get("event_id") or "").strip()
            if not event_id:
                continue
            manifest[event_id] = self._quality_from_manifest_row(row)
        self._quality_manifest_cache = manifest
        return manifest

    @staticmethod
    def _quality_from_manifest_row(row: dict[str, Any]) -> DataQualitySummary:
        event_class = str(row.get("event_class") or "diagnostic_only")
        notes = str(row.get("notes") or "")
        return DataQualitySummary(
            event_id=str(row["event_id"]),
            raw_path=str(row.get("raw_path") or ""),
            processed_path=_optional_str(row.get("processed_path")),
            raw_row_count=int(row.get("raw_row_count") or 0),
            processed_row_count=int(row.get("processed_row_count") or 0),
            inflow_missing_count_raw=int(row.get("inflow_missing_count_raw") or 0),
            outflow_missing_count_raw=int(row.get("outflow_missing_count_raw") or 0),
            rows_dropped_due_to_missing_inflow=int(
                row.get("rows_dropped_due_to_missing_inflow") or 0
            ),
            outflow_filled_by_inflow_count=int(row.get("outflow_filled_by_inflow_count") or 0),
            outflow_fallback_applied=_coerce_bool(row.get("outflow_fallback_applied")),
            inflow_drop_applied=_coerce_bool(row.get("inflow_drop_applied")),
            valid_time_axis=_coerce_bool(row.get("valid_time_axis")),
            non_increasing_time_count=int(row.get("non_increasing_time_count") or 0),
            irregular_time_step_count=int(row.get("irregular_time_step_count") or 0),
            expected_time_step_hours=int(
                row.get("expected_time_step_hours") or DEFAULT_EXPECTED_TIME_STEP_HOURS
            ),
            strict_clean_eligible=_coerce_bool(row.get("strict_clean_eligible")),
            repaired_executable_eligible=_coerce_bool(row.get("repaired_executable_eligible")),
            diagnostic_only=_coerce_bool(row.get("diagnostic_only")),
            event_class=event_class,
            notes=notes,
            time_axis_anomalies=_manifest_time_axis_anomalies(row),
            data_quality_status=event_class,
            reason=notes or event_class,
        )

    @staticmethod
    def _should_block_runtime_outflow_fallback(quality: DataQualitySummary) -> bool:
        return quality.processed_path is not None

    @staticmethod
    def _infer_season(timestamp: datetime) -> str:
        return "flood" if timestamp.month in {4, 5, 6, 7, 8, 9, 10} else "dry"

    def _infer_risk(self, level: float, peak_inflow: float) -> str:
        if level >= self.flood_limit_level or peak_inflow >= 3000.0:
            return "high"
        if peak_inflow >= 1000.0:
            return "medium"
        return "low"


def _legacy_notes(
    *,
    missing_inflow_count: int,
    missing_outflow_count: int,
    valid_time_axis: bool,
) -> str:
    reasons: list[str] = []
    if missing_inflow_count:
        reasons.append(f"missing_inflow={missing_inflow_count}")
    if missing_outflow_count:
        reasons.append(f"missing_outflow={missing_outflow_count}")
    if not valid_time_axis:
        reasons.append("invalid_time_axis")
    return "; ".join(reasons)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _manifest_time_axis_anomalies(row: dict[str, Any]) -> tuple[str, ...]:
    notes: list[str] = []
    non_increasing = int(row.get("non_increasing_time_count") or 0)
    irregular = int(row.get("irregular_time_step_count") or 0)
    if non_increasing:
        notes.append(f"non_increasing_time_count={non_increasing}")
    if irregular:
        notes.append(f"irregular_time_step_count={irregular}")
    return tuple(notes)

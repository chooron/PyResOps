from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import median

EXPECTED_COLUMNS = ("time", "prcp", "level", "inflow", "outflow")
SUPPORTED_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk")
TIME_FORMAT = "%Y/%m/%d %H:%M"
DEFAULT_PEAK_RATIO = 0.5


@dataclass(slots=True)
class EventRow:
    timestamp: datetime
    prcp: float | None
    level: float | None
    inflow: float | None
    outflow: float | None


@dataclass(slots=True)
class PeakWindow:
    start: datetime | None
    end: datetime | None
    duration_hours: float | None
    volume_m3: float | None


def normalize_cell(value: str) -> str:
    return value.replace("\u3000", " ").strip()


def detect_encoding(raw_bytes: bytes) -> tuple[str | None, str | None]:
    for encoding in SUPPORTED_ENCODINGS:
        try:
            return encoding, raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None, None


def parse_float(raw_value: str, file_name: str, line_number: int, column: str, warnings: list[str]) -> float | None:
    value = normalize_cell(raw_value)
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        warnings.append(
            f"{file_name}: line {line_number} column '{column}' has invalid numeric value {value!r}; treated as missing"
        )
        return None


def load_event_rows(path: Path) -> tuple[list[EventRow], list[str]]:
    warnings: list[str] = []
    raw_bytes = path.read_bytes()
    encoding, text = detect_encoding(raw_bytes)
    if encoding is None or text is None:
        return [], [f"{path.name}: unable to decode with supported encodings"]

    if encoding != SUPPORTED_ENCODINGS[0]:
        warnings.append(f"{path.name}: decoded with fallback encoding {encoding}")

    lines = text.splitlines()
    non_blank_lines = [line for line in lines if normalize_cell(line.lstrip("\ufeff"))]
    if not non_blank_lines:
        return [], [f"{path.name}: file is empty"]

    header = [normalize_cell(cell).lower() for cell in next(csv.reader([non_blank_lines[0].lstrip("\ufeff")]))]
    column_index = {name: idx for idx, name in enumerate(header)}
    missing_columns = [name for name in EXPECTED_COLUMNS if name not in column_index]

    if missing_columns == ["outflow"] and tuple(header) == EXPECTED_COLUMNS[:-1]:
        warnings.append(f"{path.name}: missing 'outflow' column; filled as missing")
    elif missing_columns:
        return [], [f"{path.name}: unsupported header {tuple(header)!r}"]

    rows: list[EventRow] = []
    for line_number, line in enumerate(non_blank_lines[1:], start=2):
        parsed = next(csv.reader([line]))
        normalized = [normalize_cell(cell) for cell in parsed]
        if not normalized or all(cell == "" for cell in normalized):
            continue

        time_idx = column_index.get("time")
        raw_time = normalized[time_idx] if time_idx is not None and time_idx < len(normalized) else ""
        if not raw_time:
            warnings.append(f"{path.name}: line {line_number} has empty time; skipped")
            continue
        try:
            timestamp = datetime.strptime(raw_time, TIME_FORMAT)
        except ValueError:
            warnings.append(f"{path.name}: line {line_number} has invalid time {raw_time!r}; skipped")
            continue

        def get_value(column: str) -> str:
            idx = column_index.get(column)
            if idx is None or idx >= len(normalized):
                return ""
            return normalized[idx]

        rows.append(
            EventRow(
                timestamp=timestamp,
                prcp=parse_float(get_value("prcp"), path.name, line_number, "prcp", warnings),
                level=parse_float(get_value("level"), path.name, line_number, "level", warnings),
                inflow=parse_float(get_value("inflow"), path.name, line_number, "inflow", warnings),
                outflow=parse_float(get_value("outflow"), path.name, line_number, "outflow", warnings),
            )
        )

    rows.sort(key=lambda item: item.timestamp)
    return rows, warnings


def compute_step_hours(rows: list[EventRow]) -> float | None:
    if len(rows) < 2:
        return None
    diffs = [
        (current.timestamp - previous.timestamp).total_seconds() / 3600.0
        for previous, current in zip(rows, rows[1:])
        if current.timestamp > previous.timestamp
    ]
    if not diffs:
        return None
    return float(median(diffs))


def integrate_series(rows: list[EventRow], attribute: str) -> float | None:
    total_volume = 0.0
    previous_time: datetime | None = None
    previous_value: float | None = None
    used_segment = False

    for row in rows:
        current_value = getattr(row, attribute)
        if current_value is None:
            previous_time = None
            previous_value = None
            continue
        if previous_time is not None and previous_value is not None:
            hours = (row.timestamp - previous_time).total_seconds() / 3600.0
            if hours > 0:
                total_volume += (previous_value + current_value) * 0.5 * hours * 3600.0
                used_segment = True
        previous_time = row.timestamp
        previous_value = current_value

    if used_segment:
        return total_volume
    return None


def find_peak(rows: list[EventRow], attribute: str) -> tuple[float | None, datetime | None]:
    candidates = [(getattr(row, attribute), row.timestamp) for row in rows if getattr(row, attribute) is not None]
    if not candidates:
        return None, None
    peak_value, peak_time = max(candidates, key=lambda item: item[0])
    return peak_value, peak_time


def compute_peak_window(rows: list[EventRow], attribute: str, ratio: float, step_hours: float | None) -> PeakWindow:
    points = [(row.timestamp, getattr(row, attribute)) for row in rows if getattr(row, attribute) is not None]
    if not points:
        return PeakWindow(None, None, None, None)

    peak_index, (peak_time, peak_value) = max(enumerate(points), key=lambda item: item[1][1])
    threshold = peak_value * ratio

    start_index = peak_index
    while start_index > 0 and points[start_index - 1][1] >= threshold:
        start_index -= 1

    end_index = peak_index
    while end_index + 1 < len(points) and points[end_index + 1][1] >= threshold:
        end_index += 1

    window_points = points[start_index : end_index + 1]
    start_time = window_points[0][0]
    end_time = window_points[-1][0]

    if len(window_points) >= 2:
        window_volume = 0.0
        for (left_time, left_value), (right_time, right_value) in zip(window_points, window_points[1:]):
            hours = (right_time - left_time).total_seconds() / 3600.0
            if hours > 0:
                window_volume += (left_value + right_value) * 0.5 * hours * 3600.0
        duration_hours = (end_time - start_time).total_seconds() / 3600.0
    elif step_hours is not None:
        duration_hours = step_hours
        window_volume = window_points[0][1] * step_hours * 3600.0
    else:
        duration_hours = 0.0
        window_volume = None

    return PeakWindow(start_time, end_time, duration_hours, window_volume)


def format_time(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value is not None else ""


def format_number(value: float | None, digits: int = 3) -> str:
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def summarize_event(path: Path, peak_ratio: float) -> tuple[dict[str, str], list[str]]:
    rows, warnings = load_event_rows(path)
    if not rows:
        summary = {
            "file_name": path.name,
            "record_count": "0",
            "status": "no-valid-rows",
        }
        return summary, warnings

    step_hours = compute_step_hours(rows)
    start_time = rows[0].timestamp
    end_time = rows[-1].timestamp
    duration_hours = (end_time - start_time).total_seconds() / 3600.0

    peak_prcp, peak_prcp_time = find_peak(rows, "prcp")
    peak_level, peak_level_time = find_peak(rows, "level")
    peak_inflow, peak_inflow_time = find_peak(rows, "inflow")
    peak_outflow, peak_outflow_time = find_peak(rows, "outflow")

    total_prcp = sum(row.prcp for row in rows if row.prcp is not None)
    total_inflow_volume = integrate_series(rows, "inflow")
    total_outflow_volume = integrate_series(rows, "outflow")
    peak_window = compute_peak_window(rows, "inflow", peak_ratio, step_hours)

    summary = {
        "file_name": path.name,
        "status": "ok",
        "record_count": str(len(rows)),
        "start_time": format_time(start_time),
        "end_time": format_time(end_time),
        "time_step_hours_median": format_number(step_hours, 2),
        "event_duration_hours": format_number(duration_hours, 2),
        "total_prcp_mm": format_number(total_prcp, 2),
        "peak_prcp_mm": format_number(peak_prcp, 2),
        "peak_prcp_time": format_time(peak_prcp_time),
        "peak_level_m": format_number(peak_level, 3),
        "peak_level_time": format_time(peak_level_time),
        "peak_inflow_m3s": format_number(peak_inflow, 3),
        "peak_inflow_time": format_time(peak_inflow_time),
        "peak_outflow_m3s": format_number(peak_outflow, 3),
        "peak_outflow_time": format_time(peak_outflow_time),
        "total_inflow_volume_1e8m3": format_number(total_inflow_volume / 1.0e8 if total_inflow_volume is not None else None, 4),
        "total_outflow_volume_1e8m3": format_number(total_outflow_volume / 1.0e8 if total_outflow_volume is not None else None, 4),
        "net_inflow_volume_1e8m3": format_number(
            ((total_inflow_volume - total_outflow_volume) / 1.0e8)
            if total_inflow_volume is not None and total_outflow_volume is not None
            else None,
            4,
        ),
        "peak_ratio_for_duration": format_number(peak_ratio, 2),
        "inflow_peak_window_start": format_time(peak_window.start),
        "inflow_peak_window_end": format_time(peak_window.end),
        "inflow_peak_duration_hours": format_number(peak_window.duration_hours, 2),
        "inflow_peak_volume_1e8m3": format_number(
            peak_window.volume_m3 / 1.0e8 if peak_window.volume_m3 is not None else None,
            4,
        ),
    }
    return summary, warnings


def write_summary(output_path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_arg_parser() -> argparse.ArgumentParser:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Summarize flood-event CSV files.")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=script_dir / "flood_event",
        help="Directory containing event CSV files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=script_dir / "flood_event_summary.csv",
        help="Output CSV path for the event summary.",
    )
    parser.add_argument(
        "--peak-ratio",
        type=float,
        default=DEFAULT_PEAK_RATIO,
        help="Ratio of peak inflow used to define the peak-duration window.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    input_dir = args.input_dir.resolve()
    output_path = args.output.resolve()
    peak_ratio = float(args.peak_ratio)

    if not input_dir.exists():
        print(f"Input directory does not exist: {input_dir}")
        return 2
    if not input_dir.is_dir():
        print(f"Input path is not a directory: {input_dir}")
        return 2
    if not 0.0 < peak_ratio <= 1.0:
        print(f"peak_ratio must be in (0, 1], got {peak_ratio}")
        return 2

    summaries: list[dict[str, str]] = []
    all_warnings: list[str] = []
    for csv_path in sorted(input_dir.glob("*.csv")):
        summary, warnings = summarize_event(csv_path, peak_ratio)
        summaries.append(summary)
        all_warnings.extend(warnings)

    write_summary(output_path, summaries)
    print(f"Processed {len(summaries)} files")
    print(f"Summary written to {output_path}")
    if all_warnings:
        print("Warnings:")
        for warning in all_warnings:
            print(f"- {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Event severity classification for Stage 1 baseline."""

from __future__ import annotations

import pandas as pd


# Thresholds from plan
_S4_PEAK_INFLOW = 4000.0
_S4_PEAK_LEVEL = 160.0
_S4_VOLUME = 5.0  # 亿m3

_S3_PEAK_INFLOW = 2500.0
_S3_PEAK_LEVEL = 156.5

_S2_PEAK_INFLOW = 1500.0
_S2_PEAK_LEVEL = 153.0


def classify_event(peak_inflow: float, peak_level: float, volume: float) -> str:
    """Return S1/S2/S3/S4 based on Tankeng event thresholds.

    S4 ⊂ S3 — extreme events are also counted in S3 for reporting.
    """
    if (
        peak_level >= _S4_PEAK_LEVEL
        or volume >= _S4_VOLUME
        or peak_inflow >= _S4_PEAK_INFLOW
    ):
        return "S4"
    if peak_inflow >= _S3_PEAK_INFLOW or peak_level >= _S3_PEAK_LEVEL:
        return "S3"
    if peak_inflow >= _S2_PEAK_INFLOW or peak_level >= _S2_PEAK_LEVEL:
        return "S2"
    return "S1"


def classify_all_events(summary_csv: str = "data/flood_event_summary.csv") -> pd.DataFrame:
    """Load summary CSV and return it with a scenario_group column added."""
    df = pd.read_csv(summary_csv)
    df["event_id"] = df["file_name"].str.replace(".csv", "", regex=False)
    df["scenario_group"] = df.apply(
        lambda row: classify_event(
            float(row["peak_inflow_m3s"]),
            float(row["peak_level_m"]),
            float(row["total_inflow_volume_1e8m3"]),
        ),
        axis=1,
    )
    return df

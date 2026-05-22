"""Fill blank rolling-forecast values from observed inflow.

This utility updates CSV files in place. For each row, when ``predict`` is
blank and ``inflow`` is present, ``predict`` is set to the same text value as
``inflow``. Other columns and column order are preserved.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def fill_file(path: Path) -> int:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        if not fieldnames:
            raise ValueError(f"{path}: missing header")
        if "predict" not in fieldnames:
            raise ValueError(f"{path}: missing required column 'predict'")
        if "inflow" not in fieldnames:
            raise ValueError(f"{path}: missing required column 'inflow'")
        rows = list(reader)

    filled = 0
    for row in rows:
        predict = row.get("predict")
        inflow = row.get("inflow")
        if (predict is None or predict.strip() == "") and inflow is not None and inflow.strip():
            row["predict"] = inflow
            filled += 1

    if filled:
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with tmp_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        tmp_path.replace(path)
    return filled


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fill blank predict cells with the row's inflow value."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default="data/withpred",
        help="Directory containing CSV files to update in place.",
    )
    args = parser.parse_args()

    directory = Path(args.directory)
    if not directory.exists():
        raise FileNotFoundError(f"Missing directory: {directory}")

    total = 0
    for path in sorted(directory.glob("*.csv")):
        filled = fill_file(path)
        total += filled
        print(f"{path}: filled {filled} predict value(s)")
    print(f"Total filled: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

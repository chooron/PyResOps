"""Preprocess real flood-event CSVs into a reproducible processed dataset."""

from __future__ import annotations

import argparse
import json
import sys

from experiments.data_adapters.preprocessing import (
    preprocess_flood_event_directory,
    summarize_manifest,
)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", default="data/flood_event")
    parser.add_argument("--output-dir", default="data/processed/flood_event")
    parser.add_argument(
        "--manifest",
        default="experiments/results/data_quality/event_quality_manifest.csv",
    )
    args = parser.parse_args()

    rows = preprocess_flood_event_directory(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        manifest_path=args.manifest,
    )
    summary = summarize_manifest(rows)
    print(json.dumps({"manifest": args.manifest, **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(
            json.dumps(
                {
                    "success": False,
                    "failure_reason": str(exc),
                    "failure_type": type(exc).__name__,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        sys.exit(1)

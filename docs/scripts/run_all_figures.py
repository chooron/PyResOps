"""
run_all_figures.py — Generate all PyResOps paper figures.

Usage:
    python docs/scripts/run_all_figures.py

Requires: matplotlib, numpy, pandas
Output:   docs/paper/figures/fig01_*.{pdf,png} ... fig10_*.{pdf,png}
"""

import subprocess
import sys
import os

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

scripts = [
    "fig01_03_schematics.py",
    "fig04_dataset_accounting.py",
    "fig05_component_ablation.py",
    "fig06_workflow_validation.py",
    "fig07_rolling_validation.py",
    "fig08_10_operation_cases.py",
]

if __name__ == "__main__":
    print("=" * 60)
    print("PyResOps paper figure generation")
    print("=" * 60)
    errors = []
    for script in scripts:
        path = os.path.join(SCRIPTS_DIR, script)
        print(f"\n--- Running {script} ---")
        result = subprocess.run([sys.executable, path], capture_output=True, text=True)
        if result.stdout:
            print(result.stdout.strip())
        if result.returncode != 0:
            print(f"ERROR in {script}:")
            print(result.stderr.strip())
            errors.append(script)
        else:
            print(f"OK: {script}")
    print("\n" + "=" * 60)
    if errors:
        print(f"FAILED scripts: {errors}")
        sys.exit(1)
    else:
        print("All figures generated successfully.")
        print("Output: docs/paper/figures/")

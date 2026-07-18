from __future__ import annotations

"""Prepare a new checkout without touching raw data or the frozen model."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "models/bertopic_apex_exploratory_v1/bertopic_model.pkl",
    "models/bertopic_apex_exploratory_v1/topic_registry_exploratory.json",
    "outputs/bertopic_topic_mapping_final.csv",
    "outputs/apex_topic_weekly_final.json",
    "outputs/week_boundary_audit.json",
]


def main() -> int:
    missing = [p for p in REQUIRED if not (ROOT / p).exists()]
    for directory in (ROOT / "logs", ROOT / "outputs", ROOT / "data" / "processed"):
        directory.mkdir(parents=True, exist_ok=True)
    report = {
        "python": sys.version,
        "project_root": ".",
        "required_files_missing": missing,
        "next": [
            "python scripts/check_environment.py",
            "python scripts/run_full_workflow.py",
        ],
        "raw_data_policy": "append_only; raw data and frozen model are never overwritten",
    }
    (ROOT / "outputs" / "init_check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())

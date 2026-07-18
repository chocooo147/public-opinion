from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "README.md", "requirements-bertopic.lock.txt", ".gitignore", ".env.example",
    "config/project_paths.example.json", "scripts/run_full_workflow.py", "scripts/check_environment.py",
    "models/bertopic_apex_exploratory_v1/model_manifest.json", "models/bertopic_apex_exploratory_v1/bertopic_model.pkl",
    "models/bertopic_apex_exploratory_v1/topic_registry_exploratory.json", "outputs/dashboard_data_apex_W25_W28.json",
    "outputs/game_sentiment_dashboard_apex_W25_W28_mixed_test.html", "reports/bertopic_and_platform_logic_audit.md",
    "outputs/week_boundary_audit.json", "outputs/bertopic_confidence_manifest.json", "outputs/bertopic_topic_confidence_distribution.csv",
    "reports/dashboard_W25_W28_mixed_data_report.md", "docs/DATA_DICTIONARY.md", "docs/MODEL_VERSION.md", "docs/PUBLISHING.md",
    "scripts/evaluate_metric_bias.py",
]
SENSITIVE = re.compile(r"(?:cookie|token|secret|password|session|/Users/[^/]+/Documents)", re.I)


def main() -> int:
    missing = [p for p in REQUIRED if not (ROOT / p).exists()]
    absolute_manifest_paths = []
    for path in [ROOT / "models/bertopic_apex_exploratory_v1/model_manifest.json", ROOT / "config/project_paths.example.json"]:
        if path.exists():
            text = path.read_text(encoding="utf-8")
            if "/Users/" in text or "\\\\" in text:
                absolute_manifest_paths.append(str(path.relative_to(ROOT)))
    result = {"required_files_missing": missing, "absolute_path_manifest_issues": absolute_manifest_paths, "sensitive_filename_policy": "raw/cookie/token/session files are excluded by .gitignore", "publish_ready": not missing and not absolute_manifest_paths}
    (ROOT / "outputs/release_check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["publish_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

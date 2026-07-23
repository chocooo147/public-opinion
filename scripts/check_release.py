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
AUTH_HTML_CANDIDATES = [
    "index.html",
    "game_sentiment_dashboard_v3.html",
    "game_sentiment_dashboard_v5.html",
    "outputs/game_sentiment_dashboard_apex_W25_W28_mixed_test.html",
]


def main() -> int:
    missing = [p for p in REQUIRED if not (ROOT / p).exists()]
    absolute_manifest_paths = []
    for path in [ROOT / "models/bertopic_apex_exploratory_v1/model_manifest.json", ROOT / "config/project_paths.example.json"]:
        if path.exists():
            text = path.read_text(encoding="utf-8")
            if "/Users/" in text or "\\\\" in text:
                absolute_manifest_paths.append(str(path.relative_to(ROOT)))
    auth_script_issues = []
    for relative in AUTH_HTML_CANDIDATES:
        path = ROOT / relative
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        checks = {
            "fallback password declaration": text.count("const USER_PASSWORD_FALLBACK_FINGERPRINT='bdda2306';"),
            "login submit handler": text.count("$('#loginForm').addEventListener('submit'"),
            "apex viewer declaration": text.count("const VIEWER_USERNAME='apex';"),
            "viewer permission guard": text.count("function requireContentManager()"),
        }
        for label, count in checks.items():
            if count != 1:
                auth_script_issues.append({"path": relative, "check": label, "count": count})
    result = {"required_files_missing": missing, "absolute_path_manifest_issues": absolute_manifest_paths, "auth_script_issues": auth_script_issues, "sensitive_filename_policy": "raw/cookie/token/session files are excluded by .gitignore", "publish_ready": not missing and not absolute_manifest_paths and not auth_script_issues}
    (ROOT / "outputs/release_check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["publish_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

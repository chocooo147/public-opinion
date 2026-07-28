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
PUBLIC_TEXT_SUFFIXES = {
    ".css", ".csv", ".html", ".ini", ".js", ".json", ".md", ".mjs",
    ".py", ".sh", ".toml", ".ts", ".txt", ".yaml", ".yml",
}
ABSOLUTE_PATH_PATTERNS = {
    "mac_user_home": re.compile(r"/" + r"Users/[^/\s\"']+/"),
    "linux_user_home": re.compile(r"/" + r"home/[^/\s\"']+/"),
    "windows_user_home": re.compile(
        r"\b[A-Za-z]:" + r"[\\/](?:Users|Documents and Settings)[\\/][^\\/\s\"']+[\\/]"
    ),
}
SCAN_EXCLUDES = {
    Path("outputs/release_check.json"),
}
AUTH_HTML_CANDIDATES = [
    "index.html",
    "game_sentiment_dashboard_v3.html",
    "game_sentiment_dashboard_v5.html",
    "outputs/game_sentiment_dashboard_apex_W25_W28_mixed_test.html",
]


def find_portability_issues(text: str) -> list[str]:
    return [
        label
        for label, pattern in ABSOLUTE_PATH_PATTERNS.items()
        if pattern.search(text)
    ]


def scan_public_text_paths() -> list[dict[str, object]]:
    issues = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        relative = path.relative_to(ROOT)
        if relative in SCAN_EXCLUDES:
            continue
        if path.suffix.lower() not in PUBLIC_TEXT_SUFFIXES and path.name != ".env.example":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in ABSOLUTE_PATH_PATTERNS.items():
            for match in pattern.finditer(text):
                issues.append({
                    "path": relative.as_posix(),
                    "kind": label,
                    "line": text.count("\n", 0, match.start()) + 1,
                })
    return issues


def main() -> int:
    missing = [p for p in REQUIRED if not (ROOT / p).exists()]
    public_text_absolute_path_issues = scan_public_text_paths()
    absolute_manifest_paths = sorted({
        issue["path"] for issue in public_text_absolute_path_issues
        if "manifest" in str(issue["path"]) or str(issue["path"]).startswith("config/")
    })
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
    result = {
        "required_files_missing": missing,
        "absolute_path_manifest_issues": absolute_manifest_paths,
        "public_text_absolute_path_issues": public_text_absolute_path_issues,
        "auth_script_issues": auth_script_issues,
        "sensitive_filename_policy": "raw/cookie/token/session files are excluded by .gitignore",
        "publish_ready": not missing and not public_text_absolute_path_issues and not auth_script_issues,
    }
    (ROOT / "outputs/release_check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["publish_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

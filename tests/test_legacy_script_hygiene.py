from __future__ import annotations

import ast
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CURRENT_EXECUTABLE_ROOTS = (
    ROOT / "scripts",
    ROOT / "crawler",
    ROOT / "ops/production",
)
EXECUTABLE_SUFFIXES = {".cjs", ".js", ".mjs", ".py", ".sh"}

RELOCATIONS = {
    "scripts/build_duplicate_disposition.py":
        "archive/legacy_scripts/one_off/build_duplicate_disposition.py",
    "scripts/finalize_duplicate_disposition.py":
        "archive/legacy_scripts/one_off/finalize_duplicate_disposition.py",
    "scripts/build_historical_revision.py":
        "archive/legacy_scripts/migration/build_historical_revision.py",
    "scripts/build_revision_readiness.py":
        "archive/legacy_scripts/migration/build_revision_readiness.py",
}

# This retained classifier is a current, reviewed exception to the historical
# filename rule. Keep exceptions exact and path-specific.
RETAINED_HISTORICAL_FILENAMES = {
    "scripts/classify_bilibili_scope_w25_w28.py",
}

MAINTENANCE_NAME = re.compile(
    r"(?:^|[_-])(?:patch|rectify|rectification|supplement)(?:[_-]|$)",
    re.IGNORECASE,
)
OPERATION_PREFIX = re.compile(
    r"^(?:audit|build|classify|convert|export|finalize|generate|migrate|"
    r"patch|prepare|rebuild|rectify|supplement|validate)_",
    re.IGNORECASE,
)
NUMERIC_WEEK = re.compile(r"(?:^|_)(?:20\d{2}_)?w\d{1,2}(?:_|$)", re.IGNORECASE)


def current_executable_files() -> list[Path]:
    return sorted(
        path
        for area in CURRENT_EXECUTABLE_ROOTS
        for path in area.rglob("*")
        if path.is_file() and path.suffix.lower() in EXECUTABLE_SUFFIXES
    )


class LegacyScriptHygieneTests(unittest.TestCase):
    def test_archived_scripts_do_not_return_to_executable_areas(self):
        for old, archived in RELOCATIONS.items():
            with self.subTest(old=old):
                self.assertFalse((ROOT / old).exists(), old)
                self.assertTrue((ROOT / archived).is_file(), archived)

    def test_current_executable_filenames_are_not_obvious_maintenance_tools(self):
        offenders: list[str] = []
        for path in current_executable_files():
            relative = path.relative_to(ROOT).as_posix()
            if relative in RETAINED_HISTORICAL_FILENAMES:
                continue
            stem = path.stem
            if MAINTENANCE_NAME.search(stem) or (
                OPERATION_PREFIX.search(stem) and NUMERIC_WEEK.search(stem)
            ):
                offenders.append(relative)
        self.assertEqual(offenders, [])

    def test_fixed_core_sentiment_order_is_absent_when_contract_forbids_it(self):
        contract = json.loads(
            (ROOT / "config/weekly_bilingual_report_contract.json").read_text(
                encoding="utf-8"
            )
        )
        if not contract["driver_policy"]["fixed_sentiment_order_forbidden"]:
            self.skipTest("current report contract does not forbid fixed order")

        offenders: list[str] = []
        forbidden_prefix = ["Positive", "Neutral", "Negative"]
        for path in current_executable_files():
            if path.suffix != ".py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.List, ast.Tuple)):
                    continue
                values = [
                    item.value
                    for item in node.elts
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                ]
                if len(values) == len(node.elts) and values[:3] == forbidden_prefix:
                    offenders.append(
                        f"{path.relative_to(ROOT).as_posix()}:{node.lineno}"
                    )
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()

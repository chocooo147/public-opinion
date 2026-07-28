import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/check_release.py"
SPEC = importlib.util.spec_from_file_location("release_check", MODULE_PATH)
release_check = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(release_check)


class ReleasePathScannerTests(unittest.TestCase):
    def test_detects_personal_absolute_paths_on_supported_platforms(self):
        mac_path = "/" + "Users/example/Documents/APEX/report.json"
        linux_path = "/" + "home/example/APEX/report.json"
        windows_path = "C:" + "\\Users\\example\\APEX\\report.json"
        self.assertEqual(
            release_check.find_portability_issues(mac_path),
            ["mac_user_home"],
        )
        self.assertEqual(
            release_check.find_portability_issues(linux_path),
            ["linux_user_home"],
        )
        self.assertEqual(
            release_check.find_portability_issues(windows_path),
            ["windows_user_home"],
        )

    def test_accepts_repository_relative_paths(self):
        text = (
            "data/processed/corpus.csv\n"
            "work/bertopic_models/model.pkl\n"
            ".venv-bertopic/bin/python\n"
        )
        self.assertEqual(release_check.find_portability_issues(text), [])

    def test_checked_in_public_text_is_portable(self):
        self.assertEqual(release_check.scan_public_text_paths(), [])


if __name__ == "__main__":
    unittest.main()

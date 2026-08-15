from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/reconcile_weekly_status.py"


def load_module():
    spec = importlib.util.spec_from_file_location("status_reconciler", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot_tree(root: Path) -> dict[str, tuple[str, bytes | str]]:
    snapshot: dict[str, tuple[str, bytes | str]] = {}
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root))
        if path.is_symlink():
            snapshot[relative] = ("symlink", os.readlink(path))
        elif path.is_file():
            snapshot[relative] = ("file", path.read_bytes())
        elif path.is_dir():
            snapshot[relative] = ("dir", b"")
    return snapshot


class StatusReconcilerTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def _fixture(self, work: Path) -> dict[str, Path]:
        site_root = work / "site"
        releases = site_root / "releases"
        releases.mkdir(parents=True)

        def make_release(role: str) -> tuple[Path, str, str]:
            staging = releases / f"staging-{role}"
            staging.mkdir()
            manifest = {
                "schema_version": 1,
                "week_id": "2026_W32",
                "valid": True,
                "simulation_only": False,
                "boundary": "authenticated_whitelist_only",
                "role_marker": role,
            }
            manifest_path = staging / "manifest.json"
            write_json(manifest_path, manifest)
            manifest_hash = sha256(manifest_path)
            target = releases / f"2026_W32_{manifest_hash[:12]}"
            staging.rename(target)
            return target, target.name, manifest_hash

        current_target, current_name, current_hash = make_release("current")
        candidate_target, candidate_name, candidate_hash = make_release("candidate")
        (site_root / "current").symlink_to(Path("releases") / current_name)
        (site_root / "candidate").symlink_to(Path("releases") / candidate_name)

        evidence = work / "evidence"
        current_receipt = evidence / "current" / "publish_receipt.json"
        current_verification = evidence / "current" / "live_verification.json"
        candidate_receipt = evidence / "candidate" / "candidate_deploy_receipt.json"
        candidate_verification = evidence / "candidate" / "candidate_verification.json"
        write_json(
            current_receipt,
            {
                "schema_version": 2,
                "week_id": "2026_W32",
                "target": current_name,
                "public_manifest_sha256": current_hash,
                "public_boundary": "authenticated_whitelist_only",
            },
        )
        write_json(
            current_verification,
            {
                "schema_version": 2,
                "week_id": "2026_W32",
                "current_target": current_name,
                "hashes_verified": True,
                "public_boundary": "authenticated_whitelist_only",
                "privacy_scan": {"errors": []},
            },
        )
        write_json(
            candidate_receipt,
            {
                "schema_version": 2,
                "week_id": "2026_W32",
                "target": candidate_name,
                "public_manifest_sha256": candidate_hash,
                "public_boundary": "authenticated_whitelist_only",
                "candidate_status": "deployed_not_live",
            },
        )
        write_json(
            candidate_verification,
            {
                "schema_version": 1,
                "week_id": "2026_W32",
                "valid": True,
                "state": "review_candidate_not_live",
                "target": candidate_name,
                "public_manifest_sha256": candidate_hash,
                "live_pointer_unchanged": True,
                "errors": [],
            },
        )

        latest_state = work / "state" / "latest.json"
        write_json(
            latest_state,
            {
                "schema_version": 1,
                "run_id": "2026_W31_stale_context",
                "week_id": "2026_W31",
                "week_start": "2026-07-27",
                "week_end": "2026-08-02",
                "status": "awaiting_human_approval",
                "mode": "revision",
                "workflow_phase": "candidate",
                "started_at": "2026-08-14T12:00:00+08:00",
                "finished_at": "2026-08-14T12:10:00+08:00",
                "stages": [
                    {"name": "production_preflight", "status": "success"},
                    {"name": "build_report", "status": "success"},
                    {"name": "verify_review_candidate", "status": "success"},
                ],
                "artifacts": {
                    "weekly_report": {
                        "path": "/private/should-not-leak/report.xlsx",
                        "bytes": 123,
                        "sha256": "a" * 64,
                    }
                },
            },
        )

        status_path = work / "status" / "weekly.json"
        write_json(
            status_path,
            {
                "schema_version": 2,
                "service": "apex-weekly-report",
                "current_live_release": {
                    "status": "live",
                    "target": "old-current",
                    "week_id": "2026_W32",
                    "manifest_sha256": "old",
                    "verified": True,
                },
                "review_candidate": {
                    "status": "deployed_not_live",
                    "target": "old-candidate",
                },
                "data_boundary": {
                    "bilibili": "real_bounded_sample",
                    "heybox": "real_public_search_sample",
                    "combined": "mixed_real_observations_incomparable_units",
                    "formal_reporting_qualified": False,
                },
            },
        )
        return {
            "site_root": site_root,
            "status_path": status_path,
            "current_receipt": current_receipt,
            "current_verification": current_verification,
            "candidate_receipt": candidate_receipt,
            "candidate_verification": candidate_verification,
            "latest_state": latest_state,
            "current_target": current_target,
            "candidate_target": candidate_target,
        }

    @staticmethod
    def _reconcile_kwargs(fixture: dict[str, Path]) -> dict[str, Path]:
        return {
            "site_root": fixture["site_root"],
            "status_path": fixture["status_path"],
            "current_receipt_path": fixture["current_receipt"],
            "current_verification_path": fixture["current_verification"],
            "candidate_receipt_path": fixture["candidate_receipt"],
            "candidate_verification_path": fixture["candidate_verification"],
            "latest_state_path": fixture["latest_state"],
        }

    def test_reconciles_pointer_identity_without_trusting_stale_latest_state(self):
        with tempfile.TemporaryDirectory(prefix="apex-status-reconcile-") as temp:
            fixture = self._fixture(Path(temp))
            payload = self.module.reconcile(**self._reconcile_kwargs(fixture))
            written = json.loads(fixture["status_path"].read_text(encoding="utf-8"))

            self.assertEqual(payload, written)
            self.assertEqual(
                written["current_live_release"]["target"],
                fixture["current_target"].name,
            )
            self.assertEqual(
                written["review_candidate"]["target"],
                fixture["candidate_target"].name,
            )
            self.assertEqual(
                written["latest_pipeline_run"]["run_id"],
                "2026_W31_stale_context",
            )
            self.assertEqual(written["latest_pipeline_run"]["week_id"], "2026_W31")
            rendered = json.dumps(written, ensure_ascii=False)
            self.assertNotIn("/private/should-not-leak", rendered)

    def test_missing_evidence_is_fail_closed_and_preserves_status(self):
        with tempfile.TemporaryDirectory(prefix="apex-status-reconcile-") as temp:
            fixture = self._fixture(Path(temp))
            before = fixture["status_path"].read_bytes()
            fixture["candidate_verification"].unlink()

            with self.assertRaises(self.module.ReconciliationError):
                self.module.reconcile(**self._reconcile_kwargs(fixture))

            self.assertEqual(fixture["status_path"].read_bytes(), before)
            self.assertEqual(
                list(fixture["status_path"].parent.glob(".weekly.json.*.tmp")),
                [],
            )

    def test_conflicting_receipt_is_fail_closed_and_preserves_status(self):
        with tempfile.TemporaryDirectory(prefix="apex-status-reconcile-") as temp:
            fixture = self._fixture(Path(temp))
            before = fixture["status_path"].read_bytes()
            receipt = json.loads(
                fixture["candidate_receipt"].read_text(encoding="utf-8")
            )
            receipt["public_manifest_sha256"] = "b" * 64
            write_json(fixture["candidate_receipt"], receipt)

            with self.assertRaises(self.module.ReconciliationError):
                self.module.reconcile(**self._reconcile_kwargs(fixture))

            self.assertEqual(fixture["status_path"].read_bytes(), before)
            self.assertEqual(
                list(fixture["status_path"].parent.glob(".weekly.json.*.tmp")),
                [],
            )

    def test_only_weekly_json_changes_and_atomic_temp_is_cleaned(self):
        with tempfile.TemporaryDirectory(prefix="apex-status-reconcile-") as temp:
            fixture = self._fixture(Path(temp))
            before = snapshot_tree(Path(temp))
            self.module.reconcile(**self._reconcile_kwargs(fixture))
            after = snapshot_tree(Path(temp))

            changed = {
                path
                for path in set(before) | set(after)
                if before.get(path) != after.get(path)
            }
            self.assertEqual(changed, {str(fixture["status_path"].relative_to(Path(temp)))})
            self.assertEqual(
                list(fixture["status_path"].parent.glob(".weekly.json.*.tmp")),
                [],
            )

    def test_atomic_write_failure_cleans_temp_and_preserves_status(self):
        with tempfile.TemporaryDirectory(prefix="apex-status-reconcile-") as temp:
            fixture = self._fixture(Path(temp))
            before = fixture["status_path"].read_bytes()
            with patch.object(self.module.os, "replace", side_effect=OSError("blocked")):
                with self.assertRaises(self.module.ReconciliationError):
                    self.module.reconcile(**self._reconcile_kwargs(fixture))

            self.assertEqual(fixture["status_path"].read_bytes(), before)
            self.assertEqual(
                list(fixture["status_path"].parent.glob(".weekly.json.*.tmp")),
                [],
            )

    def test_entrypoint_is_registered_without_publish_authority(self):
        registry = json.loads(
            (ROOT / "config/automation_entrypoints.json").read_text(encoding="utf-8")
        )
        entries = [
            item
            for item in registry["command_registry"]
            if item.get("path") == "scripts/reconcile_weekly_status.py"
        ]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["classification"], "current_status_reconciler")
        self.assertFalse(entries[0]["publish_authority"])

    def test_source_has_no_pipeline_or_external_command_dependency(self):
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        self.assertNotIn("subprocess", imported)
        self.assertNotIn("weekly_pipeline", SCRIPT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

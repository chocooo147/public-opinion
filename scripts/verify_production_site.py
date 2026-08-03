#!/usr/bin/env python3
"""Verify the promoted protected site, hashes, auth boundary and key downloads."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from weekly_release_common import sha256


def _fetch(url: str, authorization: str | None = None) -> tuple[int, bytes]:
    request = urllib.request.Request(url)
    if authorization:
        request.add_header("Authorization", authorization)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--site-root", type=Path, required=True)
    parser.add_argument("--base-url")
    args = parser.parse_args()
    release_dir = args.release_root.resolve() / args.week
    receipt = json.loads(
        (release_dir / "publish_receipt.json").read_text(encoding="utf-8")
    )
    site_root = args.site_root.resolve()
    current = site_root / "current"
    if not current.is_symlink():
        raise ValueError("protected-site current pointer is not an atomic symlink")
    if current.resolve().name != receipt["target"]:
        raise ValueError("protected-site current pointer does not match receipt")
    manifest_path = current / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["week_id"] != args.week or not manifest["valid"]:
        raise ValueError("promoted manifest is invalid or has wrong week")
    errors = []
    for relative, expected in manifest["artifacts"].items():
        path = current / relative
        if not path.is_file():
            errors.append(f"missing promoted artifact: {relative}")
            continue
        if path.stat().st_size != expected["bytes"]:
            errors.append(f"size mismatch: {relative}")
        if sha256(path) != expected["sha256"]:
            errors.append(f"hash mismatch: {relative}")
    if errors:
        raise ValueError("; ".join(errors))

    http_checks = []
    if args.base_url:
        base = args.base_url.rstrip("/")
        unauth_status, _ = _fetch(f"{base}/")
        if unauth_status != 401:
            raise ValueError(
                f"protected root returned {unauth_status} without credentials"
            )
        username = os.environ.get("APEX_SITE_VERIFY_USERNAME")
        password = os.environ.get("APEX_SITE_VERIFY_PASSWORD")
        if not username or not password:
            raise ValueError("site verification credentials are not configured")
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        authorization = f"Basic {token}"
        context = json.loads(
            (release_dir / "release_context.json").read_text(encoding="utf-8")
        )
        report = f"reports/{context['files']['report']}"
        for relative in ("index.html", report):
            status, body = _fetch(f"{base}/{relative}", authorization)
            expected_hash = sha256(current / relative)
            actual_hash = hashlib.sha256(body).hexdigest()
            if status != 200 or actual_hash != expected_hash:
                raise ValueError(
                    f"live verification failed for {relative}: status={status}"
                )
            http_checks.append(
                {
                    "path": relative,
                    "status": status,
                    "sha256": actual_hash,
                }
            )
    result = {
        "week_id": args.week,
        "simulation_only": manifest["simulation_only"],
        "current_target": receipt["target"],
        "artifact_count": len(manifest["artifacts"]),
        "hashes_verified": True,
        "http_checks": http_checks,
        "protected_auth_verified": bool(args.base_url),
    }
    (release_dir / "live_verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

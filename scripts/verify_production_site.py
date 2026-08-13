#!/usr/bin/env python3
"""Verify an immutable public package and the application-session boundary."""

from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from weekly_release_common import sha256


def _fetch(
    opener: urllib.request.OpenerDirector,
    url: str,
    *,
    payload: dict[str, object] | None = None,
) -> tuple[int, bytes, object]:
    data = None
    headers = {"Accept": "application/json,text/html;q=0.9,*/*;q=0.8"}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with opener.open(request, timeout=30) as response:
            return response.status, response.read(), response.headers
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--site-root", type=Path, required=True)
    parser.add_argument("--base-url")
    args = parser.parse_args()
    release_dir = args.release_root.resolve() / args.week
    receipt = json.loads((release_dir / "publish_receipt.json").read_text(encoding="utf-8"))
    site_root = args.site_root.resolve()
    current = site_root / "current"
    if not current.is_symlink():
        raise ValueError("protected-site current pointer is not an atomic symlink")
    if current.resolve().name != receipt["target"]:
        raise ValueError("protected-site current pointer does not match receipt")
    manifest_path = current / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["week_id"] != args.week or not manifest["valid"]:
        raise ValueError("promoted public manifest is invalid or has wrong week")
    if manifest.get("boundary") != "authenticated_whitelist_only":
        raise ValueError("public manifest does not declare the whitelist boundary")
    if receipt["public_manifest_sha256"] != sha256(manifest_path):
        raise ValueError("public manifest hash does not match the private receipt")
    errors: list[str] = []
    for relative, expected in manifest["artifacts"].items():
        path = current / relative
        if not path.is_file():
            errors.append(f"missing promoted artifact: {relative}")
            continue
        if path.stat().st_size != expected["bytes"]:
            errors.append(f"size mismatch: {relative}")
        if sha256(path) != expected["sha256"]:
            errors.append(f"hash mismatch: {relative}")
    for forbidden in (
        "archive/raw_inputs/bilibili.json",
        "archive/raw_inputs/heybox.json",
        "release_context.json",
        "validation.json",
        "outputs/bilibili_apex.json",
    ):
        if (current / forbidden).exists():
            errors.append(f"forbidden public path exists: {forbidden}")
    if errors:
        raise ValueError("; ".join(errors))

    http_checks: list[dict[str, object]] = []
    auth_checks: dict[str, object] = {}
    if args.base_url:
        base = args.base_url.rstrip("/")
        anonymous = urllib.request.build_opener()
        status, body, _ = _fetch(anonymous, f"{base}/")
        login_text = body.decode("utf-8", errors="replace")
        if status != 200 or "APEX 舆情控制台" not in login_text or "REAL_DASHBOARD_DATA" in login_text:
            raise ValueError("unauthenticated root did not return the data-free APEX login shell")
        dashboard_relative = next(
            key for key in manifest["artifacts"] if key.startswith("dashboard_data_")
        )
        status, _, _ = _fetch(anonymous, f"{base}/{dashboard_relative}")
        if status != 401:
            raise ValueError(f"protected dashboard returned {status} without a session")
        invalid_status, _, _ = _fetch(
            anonymous,
            f"{base}/api/auth/login",
            payload={"username": "__invalid_acceptance__", "password": "invalid"},
        )
        if invalid_status != 401:
            raise ValueError("invalid application credentials were not rejected")

        username = os.environ.get("APEX_SITE_VERIFY_USERNAME")
        password = os.environ.get("APEX_SITE_VERIFY_PASSWORD")
        if not username or not password:
            raise ValueError("application verification credentials are not configured")
        jar = http.cookiejar.CookieJar()
        authenticated = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        login_status, _, login_headers = _fetch(
            authenticated,
            f"{base}/api/auth/login",
            payload={"username": username, "password": password},
        )
        set_cookie = str(login_headers.get("Set-Cookie") or "")
        if login_status != 200 or not all(marker in set_cookie for marker in ("HttpOnly", "Secure", "SameSite=Strict")):
            raise ValueError("server-side login or session-cookie security check failed")
        report_relative = next(
            key
            for key in manifest["artifacts"]
            if key.startswith("reports/") and key.endswith(f"{args.week.split('_')[-1]}_Weekly_Community_Report.xlsx")
        )
        for relative in ("index.html", dashboard_relative, report_relative):
            status, response_body, _ = _fetch(authenticated, f"{base}/{relative}")
            actual_hash = hashlib.sha256(response_body).hexdigest()
            expected_hash = manifest["artifacts"][relative]["sha256"]
            if status != 200 or actual_hash != expected_hash:
                raise ValueError(f"live verification failed for {relative}: status={status}")
            http_checks.append({"path": relative, "status": status, "sha256": actual_hash})
        for forbidden in ("archive/raw_inputs/", "release_context.json", "outputs/bilibili_apex.json"):
            status, _, _ = _fetch(authenticated, f"{base}/{forbidden}")
            if status != 404:
                raise ValueError(f"forbidden live URL did not return 404: {forbidden} ({status})")
        logout_status, _, _ = _fetch(authenticated, f"{base}/api/auth/logout", payload={})
        after_logout, _, _ = _fetch(authenticated, f"{base}/{dashboard_relative}")
        if logout_status != 200 or after_logout != 401:
            raise ValueError("logout did not invalidate the application session")
        auth_checks = {
            "application_login": "PASS",
            "invalid_credentials_rejected": True,
            "secure_httponly_session": True,
            "protected_data_without_session": False,
            "logout_invalidates_session": True,
        }

    result = {
        "schema_version": 2,
        "week_id": args.week,
        "simulation_only": manifest["simulation_only"],
        "current_target": receipt["target"],
        "rollback_target": receipt.get("rollback_target"),
        "artifact_count": len(manifest["artifacts"]),
        "hashes_verified": True,
        "public_boundary": manifest["boundary"],
        "privacy_scan": manifest["privacy_scan"],
        "http_checks": http_checks,
        "auth_checks": auth_checks,
        "protected_auth_verified": bool(args.base_url),
    }
    (release_dir / "live_verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

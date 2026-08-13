#!/usr/bin/env python3
"""Build a whitelist-only public package and atomically promote it.

The validated release remains the private evidence package.  Publication is a
derived operation: selected files are copied, the dashboard and embedded HTML
payload are sanitized, and a path-portable public manifest is generated.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from weekly_release_common import atomic_json, sha256
from workflow_checkpoint import verify_release_authorization


PERSONAL_PATH_RE = re.compile(
    r"/(?:Users(?:/[^/\s\"']+)?|private/tmp|tmp|opt/apex|var/lib/apex)(?:/|\\b)",
    re.I,
)
FORBIDDEN_TEXT = (
    "chocoooo",
    "choco",
    '"author_name"',
    '"author_id"',
    '"evidence_text_ids"',
    '"raw_input"',
    '"raw_sha256"',
    "archive/raw_inputs",
    "passwordHash",
    "password_hash",
    "PASSWORD_HASH",
    "fallbackPassword",
    "AUTH_ACCOUNTS_KEY",
    "AUTH_SESSION_KEY",
)
APPROVED_PUBLIC_BRAND_MARKUP = (
    '<div class="sidebar-signature" aria-label="chocooo">chocooo</div>',
)
TEXT_SUFFIXES = {".html", ".js", ".json", ".md", ".txt", ".css", ".xml", ".rels"}
BILIBILI_CONTENT_ID_RE = re.compile(r"BV[0-9A-Za-z]{10}")
BILIBILI_SOURCE_URL_RE = re.compile(
    r"https://www\.bilibili\.com/video/(?P<content_id>BV[0-9A-Za-z]{10})/?"
)
HEYBOX_CONTENT_ID_RE = re.compile(r"[0-9]+")
HEYBOX_SOURCE_URL_RE = re.compile(
    r"https://www\.xiaoheihe\.cn/app/bbs/link/(?P<content_id>[0-9]+)/?"
)


def _sanitized(value: Any, forbidden_keys: set[str]) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitized(item, forbidden_keys)
            for key, item in value.items()
            if key not in forbidden_keys
        }
    if isinstance(value, list):
        return [_sanitized(item, forbidden_keys) for item in value]
    return value


def _public_representative_content(item: Any) -> dict[str, Any] | None:
    """Convert one private evidence record into a narrow, traceable source card."""
    if not isinstance(item, dict):
        return None
    platform = item.get("platform")
    topic_text_count = item.get("topic_text_count")
    if platform not in {"bilibili", "heybox"} or not isinstance(
        topic_text_count, (int, float)
    ):
        return None

    content_id = str(item.get("content_id") or "").strip()
    source_url = str(item.get("url") or item.get("source_url") or "").strip()
    source_available = False
    source_label = "来源不可用"
    source_href: str | None = None

    if platform == "bilibili":
        match = BILIBILI_SOURCE_URL_RE.fullmatch(source_url)
        source_available = bool(
            BILIBILI_CONTENT_ID_RE.fullmatch(content_id)
            and match
            and match.group("content_id") == content_id
        )
        if source_available:
            source_label = content_id
            source_href = source_url
        raw_title = str(item.get("title") or "").strip()
        title = raw_title or source_label
        content_type = "video"
    else:
        match = HEYBOX_SOURCE_URL_RE.fullmatch(source_url)
        source_available = bool(
            HEYBOX_CONTENT_ID_RE.fullmatch(content_id)
            and match
            and match.group("content_id") == content_id
        )
        if source_available:
            source_label = f"小黑盒帖子 {content_id}"
            source_href = source_url
        # Heybox result titles can contain the full post body. Public cards expose
        # only the traceable source label, never that text.
        title = source_label
        content_type = "post"

    public_item: dict[str, Any] = {
        "platform": platform,
        "content_type": content_type,
        "title": title,
        "topic_text_count": topic_text_count,
        "source_available": source_available,
        "source_label": source_label,
    }
    if source_href is not None:
        public_item["source_href"] = source_href
    return public_item


def _normalize_public_representative_contents(
    value: Any, forbidden_keys: set[str]
) -> Any:
    """Sanitize recursively while retaining only validated public source cards."""
    if isinstance(value, list):
        return [
            _normalize_public_representative_contents(item, forbidden_keys)
            for item in value
        ]
    if not isinstance(value, dict):
        return value
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if key == "representative_contents" and isinstance(item, list):
            public_items = [
                public_item
                for private_item in item
                if (public_item := _public_representative_content(private_item))
                is not None
            ]
            normalized[key] = public_items
            continue
        if key in forbidden_keys:
            continue
        normalized[key] = _normalize_public_representative_contents(
            item, forbidden_keys
        )
    if "representative_contents" in normalized:
        public_items = normalized["representative_contents"]
        normalized["representative_contents"] = public_items
        if "representative_content_count" in normalized:
            normalized["representative_content_count"] = len(public_items)
    return normalized


def _copy(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"whitelisted artifact is missing: {source.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _copy_public_xlsx(source: Path, destination: Path) -> None:
    """Copy the workbook with privacy-safe, contract-preserving evidence notes."""
    if not source.is_file():
        raise FileNotFoundError(f"whitelisted artifact is missing: {source.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    public_note = (
        "Public evidence note: This report row derives from the approved bounded "
        "weekly evidence package. Bilibili comments and Heybox search-visible posts "
        "are independent bounded samples with incomparable units. Sentiment is "
        "model-derived and unvalidated; no platform-wide claim is made. Direct "
        "traceability remains only in the private evidence package."
    )
    public_person_id = "{00000000-0000-0000-0000-000000000001}"

    def local_name(node: ET.Element) -> str:
        return node.tag.rsplit("}", 1)[-1]

    def namespace(node: ET.Element) -> str:
        return node.tag.split("}", 1)[0].lstrip("{")

    def sanitize_xml(name: str, data: bytes) -> bytes:
        if name.lower().startswith("xl/threadedcomments/"):
            root = ET.fromstring(data)
            for index, comment in enumerate(
                (node for node in root.iter() if local_name(node) == "threadedComment"),
                start=1,
            ):
                comment.set("personId", public_person_id)
                comment.set("id", f"{{00000000-0000-0000-0001-{index:012d}}}")
                for node in comment.iter():
                    if local_name(node) == "text":
                        node.text = public_note
            return ET.tostring(root, encoding="utf-8", xml_declaration=True)
        if name.lower().startswith("xl/persons/"):
            root = ET.fromstring(data)
            people = [node for node in list(root) if local_name(node) == "person"]
            for person in people[1:]:
                root.remove(person)
            if people:
                people[0].attrib.clear()
                people[0].set("displayName", "APEX Public Release")
                people[0].set("id", public_person_id)
            return ET.tostring(root, encoding="utf-8", xml_declaration=True)
        if re.fullmatch(r"xl/comments\d+\.xml", name, flags=re.I):
            root = ET.fromstring(data)
            ns = namespace(root)
            authors = next(
                (node for node in root if local_name(node) == "authors"), None
            )
            if authors is not None:
                authors.clear()
                ET.SubElement(authors, f"{{{ns}}}author").text = "APEX Public Release"
            for comment in (node for node in root.iter() if local_name(node) == "comment"):
                comment.set("authorId", "0")
                text_node = next(
                    (node for node in comment if local_name(node) == "text"), None
                )
                if text_node is None:
                    text_node = ET.SubElement(comment, f"{{{ns}}}text")
                text_node.clear()
                ET.SubElement(text_node, f"{{{ns}}}t").text = public_note
            return ET.tostring(root, encoding="utf-8", xml_declaration=True)
        return data

    with zipfile.ZipFile(source) as archive, zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED
    ) as public_archive:
        for info in archive.infolist():
            name = info.filename
            data = archive.read(info)
            if Path(name).suffix.lower() in {".xml", ".rels"}:
                data = sanitize_xml(name, data)
                text = data.decode("utf-8-sig", errors="strict")
                text = text.replace("chocoooo", "APEX").replace("choco", "APEX")
                data = text.encode("utf-8")
            public_archive.writestr(info, data)


def _replace_dashboard(html: str, dashboard: dict[str, Any]) -> str:
    payload = json.dumps(dashboard, ensure_ascii=False, separators=(",", ":"))
    updated, count = re.subn(
        r"const REAL_DASHBOARD_DATA = \{.*?\};\s*\n(?=const dashboardData)",
        f"const REAL_DASHBOARD_DATA = {payload};\n",
        html,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise ValueError("canonical frontend dashboard payload was not replaced exactly once")
    return updated


def _text_blobs(path: Path) -> Iterable[tuple[str, str]]:
    if path.suffix.lower() in TEXT_SUFFIXES:
        yield path.name, path.read_text(encoding="utf-8", errors="replace")
    elif path.suffix.lower() == ".xlsx":
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if Path(name).suffix.lower() in {".xml", ".rels"}:
                    yield f"{path.name}:{name}", archive.read(name).decode("utf-8", errors="replace")


def _privacy_scan(root: Path, whitelist: dict[str, Any]) -> dict[str, Any]:
    files = sorted(path for path in root.rglob("*") if path.is_file())
    errors: list[str] = []
    forbidden_prefixes = tuple(whitelist["forbidden_public_prefixes"])
    forbidden_names = set(whitelist["forbidden_public_names"])
    forbidden_json_keys = set(whitelist["sanitized_dashboard_keys"])
    for path in files:
        relative = path.relative_to(root).as_posix()
        if relative.startswith(forbidden_prefixes) or path.name in forbidden_names:
            errors.append(f"forbidden inventory item: {relative}")
        for label, text in _text_blobs(path):
            if PERSONAL_PATH_RE.search(text):
                errors.append(f"machine-specific path in {relative}:{label}")
            scan_text = text
            if relative == "index.html" and label == "index.html":
                # The public brand is an explicit product requirement. Mask only
                # its exact markup; all other personal-name markers remain blocked.
                for approved_brand_markup in APPROVED_PUBLIC_BRAND_MARKUP:
                    scan_text = scan_text.replace(
                        approved_brand_markup,
                        '<span class="approved-public-brand">approved-public-brand</span>',
                    )
            for marker in FORBIDDEN_TEXT:
                if marker in scan_text:
                    errors.append(f"private marker {marker!r} in {relative}:{label}")
        if path.suffix.lower() == ".json":
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                errors.append(f"invalid public JSON in {relative}: {error}")
            else:
                def walk(value: Any, location: str) -> None:
                    if isinstance(value, dict):
                        for key, item in value.items():
                            child = f"{location}.{key}"
                            if key in forbidden_json_keys:
                                errors.append(f"private JSON key {key!r} in {relative}:{child}")
                            if key == "source_href":
                                source = str(item or "")
                                if not (
                                    BILIBILI_SOURCE_URL_RE.fullmatch(source)
                                    or HEYBOX_SOURCE_URL_RE.fullmatch(source)
                                ):
                                    errors.append(
                                        f"unapproved public source URL in {relative}:{child}"
                                    )
                            walk(item, child)
                    elif isinstance(value, list):
                        for index, item in enumerate(value):
                            walk(item, f"{location}[{index}]")

                walk(payload, "$")
    return {
        "files_scanned": len(files),
        "errors": sorted(set(errors)),
        "public_raw_input_exposure": "NONE" if not errors else "FOUND",
    }


def _artifact_inventory(root: Path) -> dict[str, dict[str, Any]]:
    return {
        path.relative_to(root).as_posix(): {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }


def _current_target(site_root: Path) -> str | None:
    current = site_root / "current"
    if not current.exists() and not current.is_symlink():
        return None
    if not current.is_symlink():
        raise ValueError("site current pointer must be an atomic symlink")
    resolved = current.resolve()
    releases = (site_root / "releases").resolve()
    if releases not in resolved.parents:
        raise ValueError("site current pointer resolves outside releases")
    return resolved.name


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--site-root", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--frontend-source", type=Path)
    parser.add_argument("--allow-simulated", action="store_true")
    parser.add_argument(
        "--candidate-only",
        action="store_true",
        help="Deploy an immutable Review Candidate without switching LIVE",
    )
    parser.add_argument("--release-authorization", type=Path)
    args = parser.parse_args()

    source = args.release_root.resolve() / args.week
    internal_manifest_path = source / "manifest.json"
    context_path = source / "release_context.json"
    if not internal_manifest_path.is_file() or not context_path.is_file():
        raise FileNotFoundError("validated internal manifest or release context is missing")
    internal_manifest = json.loads(internal_manifest_path.read_text(encoding="utf-8"))
    context = json.loads(context_path.read_text(encoding="utf-8"))
    if not internal_manifest.get("valid") or context.get("publication_gate_passed") is not True:
        raise ValueError("internal release has not passed validation and publication gates")
    if internal_manifest.get("week_id") != args.week or context.get("week_id") != args.week:
        raise ValueError("internal release week mismatch")
    if internal_manifest.get("simulation_only") and not args.allow_simulated:
        raise ValueError("simulation release cannot be promoted to production")
    release_authorization_sha256 = None
    workflow = context.get("release_workflow") or {}
    if workflow.get("final_authorization_required") and not args.candidate_only:
        if not args.release_authorization:
            raise ValueError(
                "checkpointed production release requires final Agent/Sol authorization"
            )
        authorization_path = args.release_authorization.resolve()
        authorization_errors = verify_release_authorization(
            authorization_path, source, args.week
        )
        if authorization_errors:
            raise ValueError(
                "release authorization failed: " + "; ".join(authorization_errors)
            )
        release_authorization_sha256 = sha256(authorization_path)

    project_root = args.project_root.resolve()
    whitelist_path = project_root / "config/publication_whitelist.json"
    whitelist = json.loads(whitelist_path.read_text(encoding="utf-8"))
    dashboard_name = str(context["files"]["dashboard"])
    dashboard_source = source / dashboard_name
    dashboard = json.loads(dashboard_source.read_text(encoding="utf-8"))
    sanitized_dashboard = _normalize_public_representative_contents(
        copy.deepcopy(dashboard), set(whitelist["sanitized_dashboard_keys"])
    )
    frontend_source = (
        args.frontend_source.resolve()
        if args.frontend_source
        else source / "index.html"
    )
    frontend = _replace_dashboard(
        frontend_source.read_text(encoding="utf-8"), sanitized_dashboard
    )

    site_root = args.site_root.resolve()
    releases_dir = site_root / "releases"
    releases_dir.mkdir(parents=True, exist_ok=True)
    previous_target = _current_target(site_root)
    candidate_receipt_path = source / "candidate_deploy_receipt.json"
    receipt_path = source / "publish_receipt.json"
    if args.candidate_only and internal_manifest.get("candidate_only") is not True:
        raise ValueError("review candidate requires candidate-only machine validation")
    if args.candidate_only and candidate_receipt_path.is_file():
        receipt = json.loads(candidate_receipt_path.read_text(encoding="utf-8"))
        target = releases_dir / str(receipt.get("target") or "")
        public_manifest = target / "manifest.json"
        if (
            receipt.get("week_id") == args.week
            and receipt.get("internal_manifest_sha256")
            == sha256(internal_manifest_path)
            and target.is_dir()
            and public_manifest.is_file()
            and receipt.get("public_manifest_sha256") == sha256(public_manifest)
        ):
            receipt["idempotent_noop"] = True
            print(json.dumps(receipt, ensure_ascii=False, indent=2))
            return 0
        # A REVIEW/AUDIT revision may create a new validated Candidate from the
        # same prepared release. Preserve the previous receipt and immutable
        # target before replacing only the mutable "latest candidate" receipt.
        receipt_archive = source / "candidate_deploy_receipts"
        receipt_archive.mkdir(parents=True, exist_ok=True)
        archived_receipt = receipt_archive / (
            f"{receipt.get('public_manifest_sha256') or sha256(candidate_receipt_path)}.json"
        )
        if not archived_receipt.exists():
            shutil.copy2(candidate_receipt_path, archived_receipt)

    # Candidate -> LIVE is a pointer-only promotion of the exact validated
    # public package.  It must never rebuild, recollect, or recalculate.
    if not args.candidate_only and candidate_receipt_path.is_file():
        candidate_receipt = json.loads(
            candidate_receipt_path.read_text(encoding="utf-8")
        )
        target = releases_dir / str(candidate_receipt.get("target") or "")
        public_manifest_path = target / "manifest.json"
        if (
            candidate_receipt.get("week_id") != args.week
            or candidate_receipt.get("internal_manifest_sha256")
            != sha256(internal_manifest_path)
            or not target.is_dir()
            or not public_manifest_path.is_file()
            or candidate_receipt.get("public_manifest_sha256")
            != sha256(public_manifest_path)
        ):
            raise ValueError("review candidate no longer matches its immutable artifact")
        if receipt_path.is_file():
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if (
                receipt.get("target") == target.name
                and receipt.get("public_manifest_sha256")
                == candidate_receipt.get("public_manifest_sha256")
                and receipt.get("release_authorization_sha256")
                == release_authorization_sha256
            ):
                receipt["idempotent_noop"] = True
                print(json.dumps(receipt, ensure_ascii=False, indent=2))
                return 0
            raise ValueError("publish receipt does not match the approved candidate")
        current = site_root / "current"
        link = site_root / ".current.new"
        if link.exists() or link.is_symlink():
            raise FileExistsError("stale promotion link exists")
        link.symlink_to(target, target_is_directory=True)
        os.replace(link, current)
        receipt = {
            "schema_version": 3,
            "week_id": args.week,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "target": target.name,
            "rollback_target": previous_target,
            "internal_manifest_sha256": sha256(internal_manifest_path),
            "public_manifest_sha256": candidate_receipt[
                "public_manifest_sha256"
            ],
            "candidate_deploy_receipt_sha256": sha256(candidate_receipt_path),
            "candidate_artifact_reused": True,
            "public_boundary": "authenticated_whitelist_only",
            "release_authorization_sha256": release_authorization_sha256,
            "idempotent_noop": False,
        }
        atomic_json(receipt_path, receipt)
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 0

    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        target = releases_dir / str(receipt.get("target") or "")
        public_manifest = target / "manifest.json"
        if (
            receipt.get("week_id") == args.week
            and receipt.get("internal_manifest_sha256") == sha256(internal_manifest_path)
            and target.is_dir()
            and public_manifest.is_file()
            and receipt.get("public_manifest_sha256") == sha256(public_manifest)
            and receipt.get("release_authorization_sha256")
            == release_authorization_sha256
        ):
            receipt["idempotent_noop"] = True
            print(json.dumps(receipt, ensure_ascii=False, indent=2))
            return 0
        raise ValueError("publish receipt exists but does not match an immutable public target")

    staging_parent = Path(tempfile.mkdtemp(prefix=f".{args.week}.public-", dir=releases_dir))
    try:
        (staging_parent / dashboard_name).write_text(
            json.dumps(sanitized_dashboard, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        (staging_parent / "index.html").write_text(frontend, encoding="utf-8")
        for relative in whitelist["static_files"]:
            _copy(source / relative, staging_parent / relative)
        release_destinations = {
            "report": f"reports/{context['files']['report']}",
            "report_preview": f"reports/{context['files']['report_preview']}",
            "report_markdown": f"reports/{context['files']['report_markdown']}",
        }
        for context_key in whitelist["release_context_files"]:
            if context_key == "dashboard":
                continue
            destination = release_destinations[context_key]
            if context_key == "report_preview":
                preview = json.loads((source / destination).read_text(encoding="utf-8"))
                public_preview = _sanitized(
                    copy.deepcopy(preview), set(whitelist["sanitized_dashboard_keys"])
                )
                preview_destination = staging_parent / destination
                preview_destination.parent.mkdir(parents=True, exist_ok=True)
                preview_destination.write_text(
                    json.dumps(public_preview, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            else:
                artifact_source = source / destination
                artifact_destination = staging_parent / destination
                if artifact_source.suffix.lower() == ".xlsx":
                    _copy_public_xlsx(artifact_source, artifact_destination)
                else:
                    _copy(artifact_source, artifact_destination)
        for relative in whitelist["historical_report_files"]:
            artifact_source = source / relative
            artifact_destination = staging_parent / relative
            if artifact_source.suffix.lower() == ".xlsx":
                _copy_public_xlsx(artifact_source, artifact_destination)
            else:
                _copy(artifact_source, artifact_destination)

        scan = _privacy_scan(staging_parent, whitelist)
        if scan["errors"]:
            raise ValueError("public package privacy scan failed: " + "; ".join(scan["errors"]))
        artifacts = _artifact_inventory(staging_parent)
        public_manifest = {
            "schema_version": 1,
            "boundary": "authenticated_whitelist_only",
            "valid": True,
            "week_id": args.week,
            "week_start": internal_manifest["week_start"],
            "week_end": internal_manifest["week_end"],
            "simulation_only": bool(internal_manifest["simulation_only"]),
            "history_week_ids": internal_manifest["history_week_ids"],
            "artifacts": artifacts,
            "privacy_scan": scan,
            "source_provenance": {
                "internal_manifest_sha256": sha256(internal_manifest_path),
                "frontend_sha256": sha256(frontend_source),
                "publication_whitelist_sha256": sha256(whitelist_path),
            },
        }
        atomic_json(staging_parent / "manifest.json", public_manifest)
        public_manifest_sha = sha256(staging_parent / "manifest.json")
        target = releases_dir / f"{args.week}_{public_manifest_sha[:12]}"
        if target.exists():
            raise FileExistsError(f"immutable target already exists without receipt: {target.name}")
        os.replace(staging_parent, target)
    except Exception:
        shutil.rmtree(staging_parent, ignore_errors=True)
        raise

    pointer_name = "candidate" if args.candidate_only else "current"
    current = site_root / pointer_name
    link = site_root / f".{pointer_name}.new"
    if link.exists() or link.is_symlink():
        raise FileExistsError("stale promotion link exists")
    link.symlink_to(target, target_is_directory=True)
    os.replace(link, current)
    receipt = {
        "schema_version": 2,
        "week_id": args.week,
        "deployed_at" if args.candidate_only else "published_at": datetime.now(timezone.utc).isoformat(),
        "target": target.name,
        "rollback_target": previous_target,
        "internal_manifest_sha256": sha256(internal_manifest_path),
        "public_manifest_sha256": public_manifest_sha,
        "public_boundary": "authenticated_whitelist_only",
        "release_authorization_sha256": release_authorization_sha256,
        "idempotent_noop": False,
    }
    if args.candidate_only:
        receipt["candidate_status"] = "deployed_not_live"
    atomic_json(
        candidate_receipt_path if args.candidate_only else receipt_path,
        receipt,
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

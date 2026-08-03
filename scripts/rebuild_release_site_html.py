#!/usr/bin/env python3
"""Rebuild an isolated release HTML from its prepared dashboard and context."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from weekly_release_common import patch_site_html


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.project_root.resolve()
    release_dir = args.release_root.resolve() / args.week
    context = json.loads((release_dir / "release_context.json").read_text(encoding="utf-8"))
    files = context["files"]
    dashboard = json.loads((release_dir / files["dashboard"]).read_text(encoding="utf-8"))
    html = patch_site_html(
        (root / "index.html").read_text(encoding="utf-8"),
        dashboard=dashboard,
        dashboard_filename=files["dashboard"],
        report_filename=files["report"],
        preview_filename=files["report_preview"],
        report_markdown_filename=files["report_markdown"],
        bilibili_filename=files["bilibili"],
        heybox_filename=files["heybox"],
    )
    (release_dir / "index.html").write_text(html, encoding="utf-8")
    print(json.dumps({"week_id": args.week, "index": str(release_dir / "index.html")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSIGNMENTS = ROOT / "outputs/bertopic_comment_topic_assignments.csv"
OUT = ROOT / "outputs/representative_video_links.json"


def main() -> None:
    if not ASSIGNMENTS.exists():
        raise SystemExit(
            "Missing local comment assignments; provide the protected audit output "
            "before generating representative video links."
        )
    grouped: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    with ASSIGNMENTS.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("operation") != "retain":
                continue
            week = row.get("week_id", "")
            topic = row.get("canonical_topic_id", "")
            bvid = row.get("bvid", "")
            if week and topic and bvid:
                grouped[(week, topic)][bvid] += 1
    result = {}
    for (week, topic), counts in sorted(grouped.items()):
        result[f"{week}:{topic}"] = [
            {
                "bvid": bvid,
                "url": f"https://www.bilibili.com/video/{bvid}",
                "comment_count": count,
            }
            for bvid, count in counts.most_common(3)
        ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"weeks_topics": len(result), "output": str(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

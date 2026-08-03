#!/usr/bin/env python3
"""Create deterministic, clearly-labelled fixtures for weekly E2E rehearsal.

The output follows the production collection contract but is never eligible for
production publication. No live platform access is performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import timedelta
from pathlib import Path

from weekly_release_common import atomic_json, week_dates


TOPICS = [
    ("APEX-T001", "排位与匹配", "排位匹配队列与服务器稳定性"),
    ("APEX-T002", "赛事与电竞", "赛事阵容赛制与直播讨论"),
    ("APEX-T003", "服务器与网络", "延迟掉线与服务器连接"),
    ("APEX-T004", "版本与更新", "赛季更新与版本内容"),
    ("APEX-T005", "外挂与反作弊", "反作弊信任与可疑操作"),
    ("APEX-T006", "活动与联动", "活动规则奖励与联动信息"),
    ("APEX-T007", "手柄与辅助瞄准", "输入方式与辅助瞄准平衡"),
    ("APEX-T008", "皮肤与外观", "皮肤外观与商店轮换"),
    ("APEX-T009", "新手体验", "新手教学与入门门槛"),
    ("APEX-T010", "通行证与付费", "通行证奖励与付费价值"),
]
SENTIMENTS = [
    ("positive", 0.82),
    ("neutral", 0.51),
    ("negative", 0.18),
    ("neutral", 0.55),
    ("negative", 0.22),
    ("neutral", 0.48),
    ("negative", 0.31),
    ("positive", 0.73),
    ("positive", 0.78),
    ("neutral", 0.46),
]


def build_fixture(
    *,
    platform: str,
    week_id: str,
) -> dict[str, object]:
    start, end = week_dates(week_id)
    records = []
    platform_slug = "bili" if platform == "B站" else "heybox"
    source_type = "comment" if platform == "B站" else "post"
    for index, ((topic_id, topic_name, text), (label, score)) in enumerate(
        zip(TOPICS, SENTIMENTS),
        start=1,
    ):
        publish = start + timedelta(days=(index - 1) % 7)
        record_id = f"sim_{platform_slug}_{week_id}_{index:02d}"
        records.append(
            {
                "text_id": record_id,
                "week_id": week_id,
                "publish_time": f"{publish.isoformat()} {8 + index:02d}:15:00",
                "platform": platform,
                "source_type": source_type,
                "bvid": f"SIMBV{index:04d}" if platform == "B站" else "",
                "text": (
                    f"[SIMULATION] {text}。该记录仅用于 {week_id} "
                    "生产流水线联调，不代表任何平台真实观点。"
                ),
                "likes": index * (3 if platform == "B站" else 2),
                "comments": 0 if platform == "B站" else index % 4,
                "url": f"https://invalid.example/{platform_slug}/{record_id}",
                "model_topic_id": index,
                "canonical_topic_id": topic_id,
                "canonical_topic_name": topic_name,
                "operation": "retain",
                "assignment_confidence": round(0.91 - index * 0.01, 3),
                "is_outlier": 0,
                "low_confidence_flag": 0,
                "review_flag": 0,
                "possible_wrong_classification": 0,
                "sentiment_score": score,
                "sentiment_label": label,
                "sentiment_model": "deterministic_fixture",
                "sentiment_status": "simulation_only",
                "sample_scope": "simulation_fixture_only",
                "metrics_source": "simulated_fixture",
            }
        )
    serialized = json.dumps(records, ensure_ascii=False, sort_keys=True).encode()
    return {
        "meta": {
            "generated_at": f"{end.isoformat()}T16:15:00+00:00",
            "week_id": week_id,
            "date_range": [start.isoformat(), end.isoformat()],
            "raw_input": "generated_in_memory_simulation_fixture",
            "raw_sha256": hashlib.sha256(serialized).hexdigest(),
            "raw_rows": len(records),
            "mapped_rows": len(records),
            "outlier_rows": 0,
            "low_confidence_rows": 0,
            "possible_misclassification_rows": 0,
            "collection_scope": (
                "Deterministic simulation fixture; no live platform access."
            ),
            "formal_reporting_qualified": False,
            "sample_limited": True,
            "simulation_only": True,
            "data_type": "simulated_fixture",
        },
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=("B站", "小黑盒"), required=True)
    parser.add_argument("--week", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_fixture(platform=args.platform, week_id=args.week)
    atomic_json(args.output.resolve(), payload)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "week_id": args.week,
                "platform": args.platform,
                "records": len(payload["records"]),
                "simulation_only": True,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

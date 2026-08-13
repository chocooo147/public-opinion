#!/usr/bin/env python3
"""Send gated APEX Internal Review or Final Delivery email through Gmail SMTP.

The Gmail app password is read only from the protected environment file.  The
script is idempotent per run id and sends a failure notice when the production
pipeline did not complete successfully.
"""

from __future__ import annotations

import argparse
import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path


DEFAULT_STATE = Path("/var/lib/apex/weekly/latest.json")
DEFAULT_SENDER = "chocooo147@gmail.com"
DEFAULT_RECIPIENT = "yifewang@contractor.ea.com"


def build_message(
    status: dict,
    sender: str,
    recipient: str,
    *,
    kind: str = "final-delivery",
    candidate_receipt: dict | None = None,
) -> EmailMessage:
    week = status.get("week_id", "unknown week")
    if kind == "internal-review":
        if status.get("status") != "awaiting_human_approval":
            raise ValueError("Internal Review Email requires awaiting_human_approval")
        if not candidate_receipt or candidate_receipt.get("week_id") != week:
            raise ValueError("Internal Review Email requires the deployed candidate receipt")
        message = EmailMessage()
        message["Subject"] = f"[APEX REVIEW] {week} Review Candidate 待审核"
        message["From"] = sender
        message["To"] = recipient
        candidate_url = os.environ.get(
            "APEX_REVIEW_CANDIDATE_URL",
            os.environ.get("APEX_PRODUCTION_URL", "[未配置]").rstrip("/")
            + "/review-candidate/",
        )
        message.set_content(
            "\n".join(
                [
                    f"APEX {week} Review Candidate 已通过 Machine Validator。",
                    "当前状态：REVIEW CANDIDATE（尚未 LIVE）。",
                    f"统计周期：{status.get('week_start', '')} 至 {status.get('week_end', '')}",
                    f"内部审核地址：{candidate_url}",
                    "",
                    "无明显问题时请回复 APPROVE；发现异常时请回复 REVIEW / AUDIT。",
                    "审批前不会发送 Final Delivery Email，也不会把 Candidate 标记为 LIVE。",
                ]
            )
            + "\n"
        )
        return message

    success = status.get("status") == "success"
    subject_state = "已完成" if success else "失败"
    message = EmailMessage()
    message["Subject"] = f"[APEX] {week} 中国社区周报{subject_state}"
    message["From"] = sender
    message["To"] = recipient

    lines = [
        f"APEX {week} 周报生产状态：{subject_state}",
        f"统计周期：{status.get('week_start', '')} 至 {status.get('week_end', '')}",
        f"开始时间：{status.get('started_at', '')}",
        f"完成时间：{status.get('finished_at', '')}",
        "",
    ]
    if success:
        lines += [
            f"受保护网站：{os.environ.get('APEX_PRODUCTION_URL', '[未配置]')}",
            "数据边界：B站为有限可见样本；小黑盒为公开搜索可见帖子卡片样本。",
            "两平台观察单位不同，不得相加解释为跨平台总量。",
            "SnowNLP 与风险结果为未经独立人工基准校准的模型推断。",
        ]
    else:
        lines += [
            f"失败原因：{status.get('error', '未生成成功状态')}",
            "上一版生产网站保持不变，未发布半成品。",
        ]
    message.set_content("\n".join(lines) + "\n")

    report_meta = status.get("artifacts", {}).get("weekly_report", {})
    report_path = Path(report_meta.get("path", ""))
    if success and report_path.is_file():
        message.add_attachment(
            report_path.read_bytes(),
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=report_path.name,
        )
    return message


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--sent-dir", type=Path, default=Path("/var/lib/apex/weekly/sent"))
    parser.add_argument(
        "--kind",
        choices=("internal-review", "final-delivery"),
        default="final-delivery",
    )
    parser.add_argument("--candidate-receipt", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--live-verification", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    status = json.loads(args.state.read_text(encoding="utf-8"))
    candidate_receipt = (
        json.loads(args.candidate_receipt.read_text(encoding="utf-8"))
        if args.candidate_receipt
        else None
    )
    if args.kind == "final-delivery":
        if status.get("status") != "success":
            raise ValueError("Final Delivery Email is approval-only and requires successful LIVE state")
        if not args.approval or not args.live_verification:
            raise ValueError("Final Delivery Email requires approval and live verification")
        approval = json.loads(args.approval.read_text(encoding="utf-8"))
        live = json.loads(args.live_verification.read_text(encoding="utf-8"))
        if approval.get("status") != "approved_for_release":
            raise ValueError("Final Delivery Email approval is not approved_for_release")
        if live.get("week_id") != status.get("week_id") or not live.get(
            "hashes_verified"
        ):
            raise ValueError("Final Delivery Email live verification is invalid")
    run_id = status["run_id"]
    week_id = status.get("week_id", "unknown_week")
    success = status.get("status") == "success"
    args.sent_dir.mkdir(parents=True, exist_ok=True)
    marker = args.sent_dir / f"{run_id}_{args.kind}.json"
    success_marker = args.sent_dir / f"{week_id}_{args.kind}.json"
    if marker.exists() or (success and success_marker.exists()):
        return 0

    sender = os.environ.get("APEX_SMTP_SENDER", DEFAULT_SENDER)
    recipient = (
        os.environ.get("APEX_INTERNAL_REVIEW_RECIPIENT", sender)
        if args.kind == "internal-review"
        else os.environ.get("APEX_REPORT_RECIPIENT", DEFAULT_RECIPIENT)
    )
    message = build_message(
        status,
        sender,
        recipient,
        kind=args.kind,
        candidate_receipt=candidate_receipt,
    )
    if args.dry_run:
        print(message.as_string())
        return 0

    app_password = os.environ.get("APEX_GMAIL_APP_PASSWORD", "")
    if not app_password:
        raise RuntimeError("APEX_GMAIL_APP_PASSWORD is not configured")
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context, timeout=30) as smtp:
        smtp.login(sender, app_password)
        smtp.send_message(message)
    receipt = {"run_id": run_id, "week_id": week_id, "status": status.get("status"), "kind": args.kind, "sender": sender, "recipient": recipient}
    marker.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if success:
        success_marker.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

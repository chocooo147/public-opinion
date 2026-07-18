from __future__ import annotations

import argparse
import sys
from pathlib import Path

from clean_data import clean_file
from quality_check import quality_check


def main() -> int:
    parser = argparse.ArgumentParser(description="依次执行 APEX 舆情数据清洗和质量检查。")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="可选清洗输出路径；已存在时自动添加序号。")
    parser.add_argument("--rules", type=Path)
    args = parser.parse_args()
    try:
        cleaned, log = clean_file(args.input, output_path=args.output, rules_path=args.rules)
        report = quality_check(cleaned, rules_path=args.rules)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"流程失败：{exc}", file=sys.stderr)
        return 1
    print(f"清洗结果：{cleaned}")
    print(f"清洗日志：{log}")
    print(f"质量报告：{report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

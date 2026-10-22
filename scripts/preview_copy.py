"""Offline preview only: never opens a browser, loads credentials or sends messages."""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.copywriting import BANK
from app.models import Message
from app.sender import resolve_streak_message


def main() -> None:
    parser = argparse.ArgumentParser(description="离线预览续火文案，不发送消息")
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="开始日期 YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=7, choices=range(1, 367), metavar="1..366")
    parser.add_argument("--context", default="preview", help="预览用标识，不必填写真实姓名")
    parser.add_argument("--all", action="store_true", help="查看全部已审核文案")
    args = parser.parse_args()
    if args.all:
        for category, entries in BANK.items():
            print(f"\n=== {category} ({len(entries)}) ===")
            for index, text in enumerate(entries, 1):
                print(f"\n[{index}]\n{text}")
        return
    start = args.date or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    for offset in range(args.days):
        day = (start + timedelta(days=offset)).isoformat()
        message = resolve_streak_message(Message(type="streak"), run_date=day, context=args.context)
        print(f"\n=== {day} ===\n{message.content}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

"""Check the daily UTC+8 submission window and persist successful dates."""

import argparse
import hashlib
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

LOCAL_TIMEZONE = timezone(timedelta(hours=8))
STATE_PATH = Path("cron_change_time")


def within_window(now=None):
    now = now or datetime.now(LOCAL_TIMEZONE)
    minutes = now.hour * 60 + now.minute
    return 480 <= minutes <= 1080


def target_minute(day):
    seed = f"{os.environ['GITHUB_REPOSITORY']}/{day.isoformat()}\n".encode()
    return 480 + int(hashlib.sha256(seed).hexdigest()[:8], 16) % 601


def read_submitted_date():
    if STATE_PATH.exists():
        for line in STATE_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith("submitted date: "):
                return line.removeprefix("submitted date: ")
    return ""


def write_state(day, submitted_date):
    minute = target_minute(day)
    hour, minute = divmod(minute, 60)
    STATE_PATH.write_text(
        f"scheduled date: {day.isoformat()}\n"
        f"submitted date: {submitted_date}\n"
        f"next exec time: UTC({hour - 8:02d}:{minute:02d}) "
        f"北京时间({hour:02d}:{minute:02d})\n",
        encoding="utf-8",
    )


def should_submit(now, submitted_date, manual=False):
    if manual:
        return True
    if not within_window(now):
        return False
    return (
        submitted_date != now.date().isoformat()
        and now.hour * 60 + now.minute >= target_minute(now.date())
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--complete", type=date.fromisoformat)
    args = parser.parse_args()
    now = datetime.now(LOCAL_TIMEZONE)

    if args.complete:
        write_state(args.complete, args.complete.isoformat())
        print(f"Recorded successful submission for {args.complete}.")
        return

    submitted_date = read_submitted_date()
    write_state(now.date(), submitted_date)
    ready = should_submit(
        now, submitted_date, manual=os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    )
    target = target_minute(now.date())
    print(
        f"UTC+8 date: {now.date()}, target: {target // 60:02d}:{target % 60:02d}, "
        f"already submitted: {submitted_date == now.date().isoformat()}, "
        f"submit now: {ready}."
    )
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"should_submit={str(ready).lower()}\n")
            stream.write(f"date={now.date().isoformat()}\n")


if __name__ == "__main__":
    main()

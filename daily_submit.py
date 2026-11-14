"""Submit once per UTC+8 day, after a short random wait in the active run."""

import argparse
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOCAL_TIMEZONE = timezone(timedelta(hours=8))
STATE_PATH = Path("daily_submission.json")
LEGACY_STATE_PATH = Path("cron_change_time")


def local_now():
    return datetime.now(LOCAL_TIMEZONE)


def within_window(now=None):
    now = (now or local_now()).astimezone(LOCAL_TIMEZONE)
    return 8 <= now.hour < 18


def last_success():
    if STATE_PATH.exists():
        # Invalid state must fail visibly instead of risking a duplicate upload.
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return state["submitted_date"]
    if LEGACY_STATE_PATH.exists():
        for line in LEGACY_STATE_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith("submitted date: "):
                return line.removeprefix("submitted date: ")
    return ""


def choose_delay(now, randint=random.SystemRandom().randint):
    # Leave five minutes for authentication and upload. Late arrivals run now.
    latest_start = now.replace(hour=17, minute=55, second=0, microsecond=0)
    upper = min(40 * 60, max(0, int((latest_start - now).total_seconds())))
    lower = 20 * 60 if upper >= 20 * 60 else 0
    return randint(lower, upper)


def record_success(day, completed_at):
    state = {
        "submitted_date": day,
        "completed_at": completed_at.isoformat(),
        "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
    }
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(STATE_PATH)


def run(dry_run=False):
    now = local_now()
    day = now.date().isoformat()
    print(f"UTC+8 time: {now.isoformat()}", flush=True)
    if not within_window(now):
        print("SKIPPED: outside 08:00-18:00 UTC+8.", flush=True)
        return 0
    if last_success() == day:
        print("SKIPPED: already submitted successfully today.", flush=True)
        return 0

    delay = choose_delay(now)
    target = now + timedelta(seconds=delay)
    print(f"Random wait: {delay} seconds; submit at {target.isoformat()}", flush=True)
    if dry_run:
        print("DRY RUN: no waiting, upload, or state changes.", flush=True)
        return 0

    while local_now() < target:
        time.sleep(min(30, max(0, (target - local_now()).total_seconds())))
    now = local_now()
    if now.date().isoformat() != day or not within_window(now):
        print("SKIPPED: window closed while waiting.", flush=True)
        return 0
    if last_success() == day:
        print("SKIPPED: success was recorded while waiting.", flush=True)
        return 0

    env = dict(os.environ, DAILY_AUTOMATIC="true", PYTHONUNBUFFERED="1")
    try:
        result = subprocess.run([sys.executable, "main.py"], env=env, timeout=300)
    except subprocess.TimeoutExpired:
        print("FAILED: upload process timed out; success was not recorded.", flush=True)
        return 1
    if result.returncode != 0:
        print("FAILED: upload failed; a later trigger may retry today.", flush=True)
        return 1
    record_success(day, local_now())
    print(f"SUCCESS: recorded submission for {day}.", flush=True)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    raise SystemExit(run(parser.parse_args().dry_run))

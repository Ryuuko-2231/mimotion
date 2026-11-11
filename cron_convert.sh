#!/bin/bash
set -euo pipefail

read -r today hour minute <<< "$(TZ=Asia/Singapore date '+%F %H %M')"
now_minutes=$((10#$hour * 60 + 10#$minute))
first_minute=480
last_minute=1080

# A delayed planner must retain today's plan, including a queued submission.
existing_date=$(sed -n 's/^scheduled date: //p' cron_change_time)
if [[ "$existing_date" == "$today" ]] && ((now_minutes <= last_minute)); then
  cat cron_change_time
  exit 0
fi

# Use today's remaining window when the nightly planner is delayed past midnight.
scheduled_date=$today
if ((now_minutes + 5 > last_minute)); then
  scheduled_date=$(TZ=Asia/Singapore date -d "$today +1 day" +%F)
elif ((now_minutes + 5 > first_minute)); then
  first_minute=$((now_minutes + 5))
fi

# Retries also retain an already generated plan for tomorrow.
if [[ "$existing_date" == "$scheduled_date" ]]; then
  cat cron_change_time
  exit 0
fi

IFS=- read -r year month day <<< "$scheduled_date"
seed=$(printf '%s\n' "${GITHUB_REPOSITORY:?}/$scheduled_date" | sha256sum)
local_minutes=$((first_minute + 16#${seed:0:8} % (last_minute - first_minute + 1)))
utc_hour=$((local_minutes / 60 - 8))
minute=$((local_minutes % 60))
cron="$minute $utc_hour $((10#$day)) $((10#$month)) *"

sed -i -E "s/^([[:space:]]*- cron: )'.*'/\1'$cron'/" .github/workflows/run.yml
{
  printf 'scheduled date: %s\n' "$scheduled_date"
  printf "next cron: '%s'\n" "$cron"
  printf 'next exec time: UTC(%02d:%02d) 北京时间(%02d:%02d)\n' \
    "$utc_hour" "$minute" "$((utc_hour + 8))" "$minute"
} > cron_change_time

cat cron_change_time

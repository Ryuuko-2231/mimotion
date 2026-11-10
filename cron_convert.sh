#!/bin/bash
set -euo pipefail

scheduled_date=$(TZ=Asia/Singapore date -d tomorrow +%F)
IFS=- read -r year month day <<< "$scheduled_date"

# Seed by repository and date so retries keep the same randomly chosen minute.
seed=$(printf '%s\n' "${GITHUB_REPOSITORY:?}/$scheduled_date" | sha256sum)
offset=$((16#${seed:0:8} % 601))
utc_hour=$((offset / 60))
minute=$((offset % 60))
cron="$minute $utc_hour $((10#$day)) $((10#$month)) *"

sed -i -E "s/^([[:space:]]*- cron: )'.*'/\1'$cron'/" .github/workflows/run.yml
{
  printf 'scheduled date: %s\n' "$scheduled_date"
  printf "next cron: '%s'\n" "$cron"
  printf 'next exec time: UTC(%02d:%02d) 北京时间(%02d:%02d)\n' \
    "$utc_hour" "$minute" "$((utc_hour + 8))" "$minute"
} > cron_change_time

cat cron_change_time

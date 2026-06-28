#!/bin/bash
# 汇率自动抓取 + 推送脚本
# 每天早上 10:00 由 cron 调用

cd /Users/cailei/WorkBuddy/2026-06-28-08-44-53/exchange-rate-tracker

LOG="/tmp/fx-auto-fetch.log"
echo "=== $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG"

# 运行抓取脚本
/Users/cailei/.workbuddy/binaries/python/versions/3.13.12/bin/python3 fetch_rates.py >> "$LOG" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    # 有更新才推送（检查 git status）
    if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') | 检测到更新，推送到 GitHub..." >> "$LOG"
        git add -A >> "$LOG" 2>&1
        git commit -m "Ver$(cat version.txt | sed 's/Ver//') 自动更新 $(date '+%Y-%m-%d')" >> "$LOG" 2>&1
        git push origin main >> "$LOG" 2>&1
        echo "$(date '+%Y-%m-%d %H:%M:%S') | 推送完成" >> "$LOG"
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') | 无数据更新，跳过推送" >> "$LOG"
    fi
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') | fetch_rates.py 运行失败，退出码: $EXIT_CODE" >> "$LOG"
fi

echo "" >> "$LOG"

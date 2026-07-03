#!/bin/bash
# 手动更新汇率数据脚本
# 用法：双击运行，或右键 -> 打开方式 -> 终端

cd "$(dirname "$0")"

echo "==================================="
echo "汇率追踪 - 手动更新脚本"
echo "==================================="
echo ""

echo "📊 正在抓取最新汇率数据..."
/Users/cailei/.workbuddy/binaries/python/versions/3.13.12/bin/python3 fetch_rates.py

echo ""
echo "📤 正在推送到 GitHub..."
git add -A
git commit -m "手动更新 $(date +%Y-%m-%d)"
git push origin main

echo ""
echo "✅ 更新完成！"
echo "🌐 访问网站: https://ex.hplcx.com"
echo ""
echo "按任意键退出..."
read -n 1

#!/bin/bash
# GitHub Actions 环境配置文件生成脚本
# 从环境变量生成配置文件（不提交敏感信息到Git）

set -e

echo "📝 生成配置文件..."

# 生成邮件配置
if [ -n "$EMAIL_SMTP_HOST" ] && [ -n "$EMAIL_PASSWORD" ]; then
    cat > email_config.json << EOF
{
  "_说明": "邮件发送配置（由GitHub Actions自动生成）",
  "smtp_host": "$EMAIL_SMTP_HOST",
  "smtp_port": ${EMAIL_SMTP_PORT:-465},
  "sender": "$EMAIL_SENDER",
  "password": "$EMAIL_PASSWORD",
  "recipients": ["$EMAIL_RECIPIENTS"]
}
EOF
    echo "  ✅ email_config.json 已生成"
else
    echo "  ⚠️ 邮件配置环境变量未设置，跳过"
fi

# 生成微信配置
if [ -n "$WECHAT_WEBHOOK_URL" ]; then
    cat > wechat_config.json << EOF
{
  "webhook_url": "$WECHAT_WEBHOOK_URL",
  "notification_levels": ["red", "yellow"],
  "enabled": ${WECHAT_ENABLED:-true}
}
EOF
    echo "  ✅ wechat_config.json 已生成"
else
    echo "  ⚠️ 微信配置环境变量未设置，跳过"
fi

echo "✅ 配置文件生成完成"

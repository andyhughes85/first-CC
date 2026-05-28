#!/bin/bash
# 部署到阿里云服务器
# 用法: bash deploy.sh [message]
#   message: 可选，git commit 信息

set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER="root@47.113.118.5"
REMOTE_PATH="/root/midline_strategy"
BRANCH="main"

cd "$REPO_DIR"

# 1. 提交本地改动（如果有 message 参数）
if [ -n "$1" ]; then
    git add -A
    git commit -m "$1" 2>/dev/null || echo "无新改动"
fi

# 2. 推送到 GitHub
echo "=== 推送到 GitHub ==="
git push origin "$BRANCH"

# 3. SSH 到阿里云拉取
echo "=== 阿里云拉取最新代码 ==="
ssh "$SERVER" "cd $REMOTE_PATH && git pull origin $BRANCH && pip install -q -r midline_strategy/requirements.txt 2>/dev/null; find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; echo '代码更新完成'" || {
    echo "⚠️ SSH 失败，可能原因："
    echo "  - 不在内网/VPN？阿里云 47.113.118.5 需内网或 WireGuard 访问"
    echo "  - SSH key 未配置？"
    exit 1
}

# 4. 重启服务
echo "=== 重启系统服务 ==="
ssh "$SERVER" "systemctl restart stock-bot.service stock-scheduler.service; sleep 2; echo '=== 服务状态 ==='; systemctl is-active stock-bot.service stock-scheduler.service"

echo "=== 部署完成 ==="

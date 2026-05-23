"""YouTube Studio 配置"""

import os

# ── n8n ──
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "http://localhost:5678")
N8N_API_KEY = os.getenv("N8N_API_KEY", "")
# 工作流 Webhook URL（在 n8n 中创建 workflow 后获得）
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")

# ── YouTube API ──
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET", "")
# OAuth 令牌文件
YOUTUBE_TOKEN_FILE = "youtube_token.json"

# ── Claude API（脚本生成）──
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"

# ── AI 生图（缩略图）──
# 使用 runcomfy CLI，通过 ai-image-generation skill
THUMBNAIL_MODEL = "flux-dev"  # flux-dev / flux-pro / flux-klein

# ── 频道配置 ──
CHANNEL_NAME = os.getenv("CHANNEL_NAME", "My Channel")
UPLOAD_SCHEDULE = "0 10 * * 1-5"  # 工作日早10点

# ── 存储路径 ──
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
THUMBNAILS_DIR = os.path.join(PROJECT_ROOT, "thumbnails")
ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
N8N_WORKFLOWS_DIR = os.path.join(PROJECT_ROOT, "n8n_workflows")

# 自动创建目录
for d in [SCRIPTS_DIR, THUMBNAILS_DIR, ASSETS_DIR, OUTPUT_DIR, N8N_WORKFLOWS_DIR]:
    os.makedirs(d, exist_ok=True)

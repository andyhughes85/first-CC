"""YouTube Studio — 统一配置

所有的环境变量都在此加载，子模块引用此文件。
"""

import os
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ── 频道信息 ──
CHANNEL_NAME = os.getenv("CHANNEL_NAME", "My YouTube Channel")

# ── 存储目录 ──
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
SCRIPTS_DIR = os.path.join(OUTPUT_DIR, "scripts")
THUMBNAILS_DIR = os.path.join(OUTPUT_DIR, "thumbnails")
N8N_WORKFLOWS_DIR = os.path.join(PROJECT_ROOT, "n8n_workflows")
for d in [OUTPUT_DIR, SCRIPTS_DIR, THUMBNAILS_DIR, N8N_WORKFLOWS_DIR]:
    os.makedirs(d, exist_ok=True)

# ── n8n ──
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "http://localhost:5678")
N8N_API_KEY = os.getenv("N8N_API_KEY", "")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")

# ── YouTube API ──
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET", "")
YOUTUBE_TOKEN_FILE = os.path.join(PROJECT_ROOT, "youtube_token.json")

# ── Claude API（脚本生成）──
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"

# ── AI 生图（缩略图）──
THUMBNAIL_MODEL = os.getenv("THUMBNAIL_MODEL", "flux-dev")

# ── MuAPI（Shorts Generator API 模式）──
MUAPI_API_KEY = os.getenv("MUAPI_API_KEY", "")
MUAPI_BASE_URL = os.getenv("MUAPI_BASE_URL", "https://api.muapi.ai/api/v1")

# ── 本地模式配置（Shorts Generator Local 模式）──
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
LOCAL_WHISPER_MODEL = os.getenv("LOCAL_WHISPER_MODEL", "base")
LOCAL_OUTPUT_DIR = OUTPUT_DIR

# ── Remotion ──
REMOTION_PROJECT_DIR = PROJECT_ROOT  # package.json 就在项目根目录

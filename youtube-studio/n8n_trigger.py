"""n8n 工作流触发器 — 触发 n8n 自动化视频制作流程"""

import json
import logging
import requests
from typing import Optional
from config import N8N_BASE_URL, N8N_API_KEY, N8N_WEBHOOK_URL

logger = logging.getLogger(__name__)


class N8nTrigger:
    """n8n 工作流触发器"""

    def __init__(self, base_url: str = None, api_key: str = None):
        self.base_url = (base_url or N8N_BASE_URL).rstrip("/")
        self.api_key = api_key or N8N_API_KEY
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({"X-N8N-API-KEY": self.api_key})

    def trigger_webhook(self, webhook_url: str = None, payload: dict = None) -> dict:
        """通过 Webhook 触发工作流"""
        url = webhook_url or N8N_WEBHOOK_URL
        if not url:
            logger.error("未配置 Webhook URL")
            return {"success": False, "error": "no webhook url"}

        try:
            resp = self.session.post(url, json=payload or {}, timeout=30)
            resp.raise_for_status()
            logger.info(f"Webhook 触发成功: {url}")
            return {"success": True, "data": resp.json()}
        except requests.RequestException as e:
            logger.error(f"Webhook 触发失败: {e}")
            return {"success": False, "error": str(e)}

    def list_workflows(self) -> list:
        """列出 n8n 所有工作流"""
        try:
            resp = self.session.get(f"{self.base_url}/api/v1/workflows", timeout=10)
            resp.raise_for_status()
            return resp.json().get("data", [])
        except requests.RequestException as e:
            logger.error(f"获取工作流列表失败: {e}")
            return []

    def activate_workflow(self, workflow_id: str) -> bool:
        """激活指定工作流"""
        try:
            resp = self.session.patch(
                f"{self.base_url}/api/v1/workflows/{workflow_id}",
                json={"active": True},
                timeout=10,
            )
            return resp.status_code == 200
        except requests.RequestException as e:
            logger.error(f"激活工作流失败: {e}")
            return False

    def trigger_video_pipeline(self, video_data: dict) -> dict:
        """触发完整视频制作流水线"""
        payload = {
            "topic": video_data.get("topic", ""),
            "script": video_data.get("script", ""),
            "style": video_data.get("style", "教程"),
            "duration": video_data.get("duration_minutes", 5),
            "thumbnail_prompt": video_data.get("thumbnail_prompt", ""),
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        }
        return self.trigger_webhook(payload=payload)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    n8n = N8nTrigger()
    workflows = n8n.list_workflows()
    print(f"找到 {len(workflows)} 个工作流")
    for wf in workflows:
        print(f"  - {wf.get('name')} (ID: {wf.get('id')})")

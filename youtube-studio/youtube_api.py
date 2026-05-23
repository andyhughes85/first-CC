"""YouTube API — 上传视频、管理播放列表、获取分析数据"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import YOUTUBE_API_KEY, YOUTUBE_TOKEN_FILE

logger = logging.getLogger(__name__)


class YouTubeUploader:
    """YouTube 视频上传与管理"""

    def __init__(self, token_file: str = None):
        self.token_file = token_file or YOUTUBE_TOKEN_FILE
        self.service = None

    def _build_service(self):
        """构建 YouTube API 服务"""
        if self.service:
            return self.service
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build

            creds = None
            if os.path.exists(self.token_file):
                creds = Credentials.from_authorized_user_file(self.token_file)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        "client_secret.json",
                        ["https://www.googleapis.com/auth/youtube.upload"],
                    )
                    creds = flow.run_local_server(port=0)
                with open(self.token_file, "w") as f:
                    f.write(creds.to_json())

            self.service = build("youtube", "v3", credentials=creds)
            return self.service
        except ImportError:
            logger.error("google-api-python-client 未安装")
            return None
        except Exception as e:
            logger.error(f"YouTube API 认证失败: {e}")
            return None

    def upload(self, video_path: str, title: str, description: str = "",
               tags: list = None, category_id: str = "22",
               privacy_status: str = "private") -> Optional[str]:
        """上传视频到 YouTube"""
        from googleapiclient.http import MediaFileUpload

        service = self._build_service()
        if not service:
            logger.error("无法初始化 YouTube API")
            return None

        if not os.path.exists(video_path):
            logger.error(f"视频文件不存在: {video_path}")
            return None

        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": (tags or [])[:500],
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        try:
            media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
            request = service.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )
            response = request.execute()
            video_id = response.get("id")
            logger.info(f"视频上传成功: https://youtu.be/{video_id}")
            return video_id
        except Exception as e:
            logger.error(f"视频上传失败: {e}")
            return None

    def update_thumbnail(self, video_id: str, thumbnail_path: str) -> bool:
        """更新视频缩略图"""
        from googleapiclient.http import MediaFileUpload

        service = self._build_service()
        if not service or not os.path.exists(thumbnail_path):
            return False

        try:
            media = MediaFileUpload(thumbnail_path)
            service.thumbnails().set(
                videoId=video_id,
                media_body=media,
            ).execute()
            logger.info(f"缩略图更新成功: {video_id}")
            return True
        except Exception as e:
            logger.error(f"缩略图更新失败: {e}")
            return False

    def upload_with_assets(self, video_path: str, title: str,
                           description: str = "", tags: list = None,
                           thumbnail_path: str = None) -> Optional[str]:
        """上传视频并设置缩略图"""
        video_id = self.upload(video_path, title, description, tags)
        if video_id and thumbnail_path:
            self.update_thumbnail(video_id, thumbnail_path)
        return video_id


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("YouTube Uploader 模块测试")
    print("注意: 需要 Google OAuth 认证才能上传")

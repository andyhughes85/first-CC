"""缩略图生成 — 调用 RunComfy / FLUX 生成视频缩略图"""

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from config import THUMBNAILS_DIR, THUMBNAIL_MODEL

logger = logging.getLogger(__name__)


class ThumbnailGenerator:
    """AI 缩略图生成器"""

    STYLES = {
        "科技感": "cyberpunk style, neon lights, high tech, detailed",
        "教程风": "clean, professional, educational, bright, clear text overlay",
        "吸引点击": "dramatic lighting, high contrast, emotional, viral style, bold colors",
        "极简": "minimalist, flat design, pastel colors, simple composition",
        "电影感": "cinematic, epic, widescreen, film grain, dramatic shadows",
    }

    def __init__(self):
        self.model = THUMBNAIL_MODEL

    def generate(self, topic: str, style: str = "科技感", aspect_ratio: str = "16:9") -> str:
        """生成视频缩略图，返回图片路径"""
        logger.info(f"生成缩略图: topic={topic}, style={style}")

        style_desc = self.STYLES.get(style, style)
        prompt = (
            f"YouTube thumbnail for video about {topic}. "
            f"Style: {style_desc}. "
            f"Professional, eye-catching, high quality. "
            f"Text space reserved. 4K, detailed."
        )

        # 使用 runcomfy CLI
        try:
            result = subprocess.run(
                ["runcomfy", "run", self.model,
                 "--prompt", prompt,
                 "--output", THUMBNAILS_DIR,
                 "--aspect", aspect_ratio],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                logger.info(f"缩略图生成成功: {result.stdout}")
                return self._find_latest()
            else:
                logger.warning(f"runcomfy 失败: {result.stderr}")
                return self._fallback(topic, style)
        except FileNotFoundError:
            logger.warning("runcomfy CLI 未安装，使用 fallback 占位图")
            return self._fallback(topic, style)
        except Exception as e:
            logger.error(f"缩略图生成异常: {e}")
            return self._fallback(topic, style)

    def _fallback(self, topic: str, style: str) -> str:
        """无 AI 生图能力时的占位方案"""
        try:
            from PIL import Image, ImageDraw, ImageFont
            img = Image.new("RGB", (1280, 720), (20, 30, 50))
            draw = ImageDraw.Draw(img)
            draw.text((640, 360), topic, fill=(255, 255, 255), anchor="mm")
            path = Path(THUMBNAILS_DIR) / f"thumbnail_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            img.save(path)
            logger.info(f"占位缩略图已生成: {path}")
            return str(path)
        except ImportError:
            logger.error("PIL 未安装，无法生成占位图")
            return ""

    def _find_latest(self) -> str:
        """找到最新生成的缩略图"""
        files = sorted(Path(THUMBNAILS_DIR).glob("*.png"), key=lambda f: f.stat().st_mtime, reverse=True)
        return str(files[0]) if files else ""


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    gen = ThumbnailGenerator()
    path = gen.generate("AI 视频制作", style="科技感")
    print(f"缩略图: {path}")

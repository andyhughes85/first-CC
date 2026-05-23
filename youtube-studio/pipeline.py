"""YouTube Studio 主流水线 — 编排完整视频制作流程"""

import json
import logging
import sys
from datetime import datetime

from config import OUTPUT_DIR, CHANNEL_NAME
from script_gen import ScriptGenerator
from thumbnail_gen import ThumbnailGenerator
from n8n_trigger import N8nTrigger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("pipeline")


class YouTubePipeline:
    """YouTube 视频制作流水线"""

    def __init__(self):
        self.script_gen = ScriptGenerator()
        self.thumbnail_gen = ThumbnailGenerator()
        self.n8n = N8nTrigger()

    def step_generate_script(self, topic: str, **kwargs) -> dict:
        """Step 1: 生成脚本"""
        logger.info(f"[1/4] 生成脚本: {topic}")
        script = self.script_gen.generate_script(topic, **kwargs)
        print(f"  ✅ 脚本: {script.get('title', 'N/A')}")
        print(f"     场景数: {len(script.get('scenes', []))}")
        return script

    def step_generate_thumbnail(self, topic: str, style: str = "科技感") -> str:
        """Step 2: 生成缩略图"""
        logger.info(f"[2/4] 生成缩略图: style={style}")
        path = self.thumbnail_gen.generate(topic, style=style)
        if path:
            print(f"  ✅ 缩略图: {path}")
        else:
            print(f"  ⚠️ 缩略图生成跳过")
        return path

    def step_trigger_n8n(self, video_data: dict) -> dict:
        """Step 3: 触发 n8n 视频制作"""
        logger.info("[3/4] 触发 n8n 工作流")
        result = self.n8n.trigger_video_pipeline(video_data)
        if result.get("success"):
            print(f"  ✅ n8n 工作流已触发")
            if result.get("data"):
                print(f"     响应: {json.dumps(result['data'], ensure_ascii=False)[:200]}")
        else:
            print(f"  ⚠️ n8n 触发失败: {result.get('error', 'unknown')}")
        return result

    def step_prepare_upload(self, script: dict, thumbnail_path: str,
                            topic: str) -> dict:
        """Step 4: 准备上传数据"""
        logger.info("[4/4] 准备上传数据")
        upload_data = {
            "title": script.get("title", f"关于{topic}的视频"),
            "description": script.get("description", ""),
            "tags": script.get("tags", [topic]),
            "thumbnail_path": thumbnail_path,
            "topic": topic,
            "generated_at": datetime.now().isoformat(),
        }

        # 保存上传数据到 JSON
        date_str = datetime.now().strftime("%Y%m%d")
        path = f"{OUTPUT_DIR}/upload_{date_str}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(upload_data, f, ensure_ascii=False, indent=2)
        print(f"  ✅ 上传数据已保存: {path}")
        return upload_data

    def run(self, topic: str, style: str = "教程", duration: int = 5,
            thumbnail_style: str = "科技感"):
        """运行完整流水线"""
        print(f"\n{'='*50}")
        print(f"  YouTube Studio — 视频制作流水线")
        print(f"  频道: {CHANNEL_NAME}")
        print(f"  主题: {topic} | 风格: {style} | 时长: {duration}min")
        print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*50}\n")

        # Step 1: 脚本
        script = self.step_generate_script(topic, duration_minutes=duration, style=style)

        # Step 2: 缩略图
        thumbnail = self.step_generate_thumbnail(topic, style=thumbnail_style)

        # Step 3: n8n
        video_data = {
            "topic": topic,
            "script": json.dumps(script, ensure_ascii=False),
            "style": style,
            "duration_minutes": duration,
            "thumbnail_prompt": f"{topic} {thumbnail_style} style",
        }
        self.step_trigger_n8n(video_data)

        # Step 4: 上传准备
        upload_data = self.step_prepare_upload(script, thumbnail, topic)

        print(f"\n{'='*50}")
        print(f"  ✅ 流水线完成")
        print(f"  标题: {upload_data['title']}")
        print(f"{'='*50}\n")

        return upload_data


def main():
    """命令行入口"""
    import argparse
    parser = argparse.ArgumentParser(description="YouTube 视频制作流水线")
    parser.add_argument("topic", nargs="?", default="AI 视频制作", help="视频主题")
    parser.add_argument("--style", default="教程", help="视频风格")
    parser.add_argument("--duration", type=int, default=5, help="时长（分钟）")
    parser.add_argument("--thumbnail", default="科技感", help="缩略图风格")

    args = parser.parse_args()

    pipeline = YouTubePipeline()
    result = pipeline.run(
        topic=args.topic,
        style=args.style,
        duration=args.duration,
        thumbnail_style=args.thumbnail,
    )

    # 输出 JSON 结果
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""YouTube Studio 主流水线 — 统一 CLI 入口

子命令:
  shorts    <url>    从 YouTube 视频提取高光 Shorts (MuAPI/local)
  video     <topic>  完整视频制作: 脚本→缩略图→n8n→上传
  script    <topic>  仅生成视频脚本
  thumbnail <topic>  仅生成缩略图
  remotion            渲染 Remotion 视频
  upload    <path>   上传已有视频到 YouTube
"""

import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from config import (
    CHANNEL_NAME,
    CLAUDE_API_KEY,
    OUTPUT_DIR,
    REMOTION_PROJECT_DIR,
)
from script_gen import ScriptGenerator
from thumbnail_gen import ThumbnailGenerator
from n8n_trigger import N8nTrigger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("pipeline")


# ── Shorts Generator ──────────────────────────────────────────────────────────

def cmd_shorts(args):
    """从 YouTube URL 提取高光 Shorts"""
    from shorts_generator import generate_shorts

    print(f"\n{'='*50}")
    print(f"  YouTube Shorts Generator")
    print(f"  URL: {args.url} | mode: {args.mode} | clips: {args.clips}")
    print(f"{'='*50}\n")

    result = generate_shorts(
        youtube_url=args.url,
        num_clips=args.clips,
        aspect_ratio=args.aspect,
        download_format=args.format,
        language=args.language,
        mode=args.mode,
    )

    shorts = result.get("shorts", [])
    print(f"\n{'='*50}")
    print(f"  ✅ 完成! 生成了 {len(shorts)} 个 Shorts")
    for i, s in enumerate(shorts, 1):
        url = s.get("clip_url") or "失败"
        print(f"  [{i}] {s.get('title', 'N/A')} → {url}")
    print(f"{'='*50}\n")

    if args.output_json:
        out_path = Path(args.output_json)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  结果已保存: {out_path}")

    return result


# ── 完整视频流水线 ────────────────────────────────────────────────────────────

class YouTubePipeline:
    """YouTube 视频制作流水线"""

    def __init__(self):
        self.script_gen = ScriptGenerator()
        self.thumbnail_gen = ThumbnailGenerator()
        self.n8n = N8nTrigger()

    def step_generate_script(self, topic: str, **kwargs) -> dict:
        logger.info(f"[1/4] 生成脚本: {topic}")
        script = self.script_gen.generate_script(topic, **kwargs)
        print(f"  ✅ 脚本: {script.get('title', 'N/A')}")
        print(f"     场景数: {len(script.get('scenes', []))}")
        return script

    def step_generate_thumbnail(self, topic: str, style: str = "科技感") -> str:
        logger.info(f"[2/4] 生成缩略图: style={style}")
        path = self.thumbnail_gen.generate(topic, style=style)
        if path:
            print(f"  ✅ 缩略图: {path}")
        else:
            print(f"  ⚠️ 缩略图生成跳过")
        return path

    def step_trigger_n8n(self, video_data: dict) -> dict:
        logger.info("[3/4] 触发 n8n 工作流")
        result = self.n8n.trigger_video_pipeline(video_data)
        if result.get("success"):
            print(f"  ✅ n8n 工作流已触发")
            if result.get("data"):
                print(f"     响应: {json.dumps(result['data'], ensure_ascii=False)[:200]}")
        else:
            print(f"  ⚠️ n8n 触发失败: {result.get('error', 'unknown')}")
        return result

    def step_prepare_upload(self, script: dict, thumbnail_path: str, topic: str) -> dict:
        logger.info("[4/4] 准备上传数据")
        upload_data = {
            "title": script.get("title", f"关于{topic}的视频"),
            "description": script.get("description", ""),
            "tags": script.get("tags", [topic]),
            "thumbnail_path": thumbnail_path,
            "topic": topic,
            "generated_at": datetime.now().isoformat(),
        }
        date_str = datetime.now().strftime("%Y%m%d")
        path = Path(OUTPUT_DIR) / f"upload_{date_str}.json"
        path.write_text(json.dumps(upload_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  ✅ 上传数据已保存: {path}")
        return upload_data

    def run(self, topic: str, style: str = "教程", duration: int = 5,
            thumbnail_style: str = "科技感"):
        print(f"\n{'='*50}")
        print(f"  YouTube Studio — 视频制作流水线")
        print(f"  频道: {CHANNEL_NAME}")
        print(f"  主题: {topic} | 风格: {style} | 时长: {duration}min")
        print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*50}\n")

        script = self.step_generate_script(topic, duration_minutes=duration, style=style)
        thumbnail = self.step_generate_thumbnail(topic, style=thumbnail_style)

        video_data = {
            "topic": topic,
            "script": json.dumps(script, ensure_ascii=False),
            "style": style,
            "duration_minutes": duration,
            "thumbnail_prompt": f"{topic} {thumbnail_style} style",
        }
        self.step_trigger_n8n(video_data)

        upload_data = self.step_prepare_upload(script, thumbnail, topic)

        print(f"\n{'='*50}")
        print(f"  ✅ 流水线完成")
        print(f"  标题: {upload_data['title']}")
        print(f"{'='*50}\n")
        return upload_data


def cmd_video(args):
    pipeline = YouTubePipeline()
    result = pipeline.run(
        topic=args.topic,
        style=args.style,
        duration=args.duration,
        thumbnail_style=args.thumbnail,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


# ── 单步命令 ──────────────────────────────────────────────────────────────────

def cmd_script(args):
    gen = ScriptGenerator()
    script = gen.generate_script(args.topic, duration_minutes=args.duration, style=args.style)
    print(json.dumps(script, ensure_ascii=False, indent=2))


def cmd_thumbnail(args):
    gen = ThumbnailGenerator()
    path = gen.generate(args.topic, style=args.style)
    print(f"缩略图: {path}")


def cmd_remotion(args):
    """渲染 Remotion 视频"""
    print(f"\n{'='*50}")
    print(f"  Remotion 渲染")
    print(f"  CRF: {args.crf} | 输出: {args.output}")
    print(f"{'='*50}\n")

    cmd = [
        "npx", "remotion", "render", "MainVideo", args.output,
        "--crf", str(args.crf),
    ]
    if args.frames:
        cmd.extend(["--frames", args.frames])
    if args.concurrency:
        cmd.extend(["--concurrency", str(args.concurrency)])

    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=REMOTION_PROJECT_DIR)
    if result.returncode == 0:
        print(f"\n  ✅ 渲染完成: {args.output}")
    else:
        print(f"\n  ❌ 渲染失败 (exit code {result.returncode})")
        sys.exit(result.returncode)


def cmd_upload(args):
    """上传已有视频到 YouTube"""
    from youtube_api import YouTubeUploader

    uploader = YouTubeUploader()
    video_id = uploader.upload_with_assets(
        video_path=args.video,
        title=args.title,
        description=args.description or "",
        tags=args.tags.split(",") if args.tags else None,
        thumbnail_path=args.thumbnail,
    )
    if video_id:
        print(f"\n  ✅ 上传成功: https://youtu.be/{video_id}")
    else:
        print("\n  ❌ 上传失败")
        sys.exit(1)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="YouTube Studio — 统一视频制作流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # shorts
    p_shorts = sub.add_parser("shorts", help="从 YouTube 视频提取高光 Shorts")
    p_shorts.add_argument("url", help="YouTube 视频 URL")
    p_shorts.add_argument("--mode", default="api", choices=["api", "local"],
                          help="处理模式: api (MuAPI) / local (本机)")
    p_shorts.add_argument("--clips", type=int, default=3, help="生成的 Shorts 数量")
    p_shorts.add_argument("--aspect", default="9:16", help="画面比例 (默认 9:16)")
    p_shorts.add_argument("--format", default="720", help="下载画质 (360/480/720/1080)")
    p_shorts.add_argument("--language", help="语言代码 (如 zh, en)")
    p_shorts.add_argument("--output-json", help="保存结果到 JSON 文件")

    # video
    p_video = sub.add_parser("video", help="完整视频制作流水线")
    p_video.add_argument("topic", nargs="?", default="AI 视频制作", help="视频主题")
    p_video.add_argument("--style", default="教程", help="视频风格")
    p_video.add_argument("--duration", type=int, default=5, help="时长（分钟）")
    p_video.add_argument("--thumbnail", default="科技感", help="缩略图风格")

    # script
    p_script = sub.add_parser("script", help="仅生成视频脚本")
    p_script.add_argument("topic", help="视频主题")
    p_script.add_argument("--style", default="教程", help="视频风格")
    p_script.add_argument("--duration", type=int, default=5, help="时长（分钟）")

    # thumbnail
    p_thumb = sub.add_parser("thumbnail", help="仅生成缩略图")
    p_thumb.add_argument("topic", help="缩略图主题")
    p_thumb.add_argument("--style", default="科技感", help="缩略图风格")

    # remotion
    p_remotion = sub.add_parser("remotion", help="渲染 Remotion 视频")
    p_remotion.add_argument("--output", default="out/output.mp4", help="输出路径")
    p_remotion.add_argument("--crf", type=int, default=18, help="CRF 值 (画质)")
    p_remotion.add_argument("--frames", help="渲染范围 (如 0-100)")
    p_remotion.add_argument("--concurrency", type=int, help="并发数")

    # upload
    p_upload = sub.add_parser("upload", help="上传视频到 YouTube")
    p_upload.add_argument("video", help="视频文件路径")
    p_upload.add_argument("--title", required=True, help="视频标题")
    p_upload.add_argument("--description", help="视频描述")
    p_upload.add_argument("--tags", help="标签（逗号分隔）")
    p_upload.add_argument("--thumbnail", help="缩略图文件路径")

    args = parser.parse_args()

    if args.command == "shorts":
        cmd_shorts(args)
    elif args.command == "video":
        cmd_video(args)
    elif args.command == "script":
        cmd_script(args)
    elif args.command == "thumbnail":
        cmd_thumbnail(args)
    elif args.command == "remotion":
        cmd_remotion(args)
    elif args.command == "upload":
        cmd_upload(args)


if __name__ == "__main__":
    main()

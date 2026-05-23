"""脚本生成 — 调用 Claude API 生成视频脚本"""

import json
import logging
from datetime import datetime
from pathlib import Path
from config import CLAUDE_API_KEY, CLAUDE_MODEL, SCRIPTS_DIR

logger = logging.getLogger(__name__)


class ScriptGenerator:
    """视频脚本生成器"""

    TOPICS = [
        "科技", "财经", "生活", "教育", "娱乐",
        "AI 工具", "编程教程", "产品评测",
    ]

    def __init__(self, api_key=None):
        self.api_key = api_key or CLAUDE_API_KEY

    def generate_script(self, topic: str, duration_minutes: int = 5, style: str = "教程") -> dict:
        """生成完整视频脚本"""
        logger.info(f"生成脚本: topic={topic}, duration={duration_minutes}min, style={style}")

        if not self.api_key:
            logger.warning("未配置 CLAUDE_API_KEY，使用示例脚本")
            return self._sample_script(topic, duration_minutes)

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)
            prompt = (
                f"你是一个专业的视频脚本作者。请为一个{style}类YouTube视频写一个完整脚本。\n"
                f"主题: {topic}\n"
                f"时长: {duration_minutes}分钟\n\n"
                f"请按以下格式返回 JSON：\n"
                f"{{\n"
                f'  "title": "视频标题",\n'
                f'  "description": "视频描述（含SEO关键词）",\n'
                f'  "tags": ["标签1", "标签2"],\n'
                f'  "scenes": [\n'
                f'    {{"time": "0:00", "text": "旁白内容", "visual": "画面描述", "duration_sec": 30}}\n'
                f'  ]\n'
                f"}}\n"
                f"确保脚本有吸引人的开头和明确的行动号召。"
            )
            resp = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            content = resp.content[0].text
            # 提取 JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            script = json.loads(content.strip())
            self._save_script(script, topic)
            return script

        except ImportError:
            logger.error("anthropic 库未安装")
            return self._sample_script(topic, duration_minutes)
        except Exception as e:
            logger.error(f"脚本生成失败: {e}")
            return self._sample_script(topic, duration_minutes)

    def _sample_script(self, topic: str, duration_minutes: int) -> dict:
        """返回示例脚本（无 API Key 时使用）"""
        return {
            "title": f"【深度解析】{topic} — 2026年你必须知道的事",
            "description": (
                f"本期视频带你深入了解{topic}的最新趋势和发展。\n\n"
                f"📌 时间戳\n"
                f"0:00 开场\n"
                f"0:30 {topic}的背景\n"
                f"2:00 核心内容\n"
                f"4:00 总结与展望\n\n"
                f"#科技 #教程 #{topic}"
            ),
            "tags": ["教程", topic, "知识分享"],
            "scenes": [
                {"time": "0:00", "text": f"大家好，欢迎来到本期视频！今天我们来聊聊{topic}", "visual": "主持人开场", "duration_sec": 15},
                {"time": "0:15", "text": f"首先让我们了解一下{topic}的背景...", "visual": "相关画面/图表", "duration_sec": 30},
                {"time": "0:45", "text": f"核心内容部分...", "visual": "演示/讲解", "duration_sec": 120},
                {"time": "2:45", "text": "总结一下今天的内容...", "visual": "总结画面", "duration_sec": 30},
                {"time": "3:15", "text": "如果你喜欢这个视频，记得点赞订阅！", "visual": "结束画面", "duration_sec": 15},
            ],
        }

    def _save_script(self, script: dict, topic: str):
        """保存脚本到文件"""
        date_str = datetime.now().strftime("%Y%m%d")
        safe_topic = topic.replace(" ", "_").replace("/", "_")
        path = Path(SCRIPTS_DIR) / f"{date_str}_{safe_topic}.json"
        path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"脚本已保存: {path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    gen = ScriptGenerator()
    script = gen.generate_script("AI 视频制作工具", duration_minutes=5, style="教程")
    print(json.dumps(script, ensure_ascii=False, indent=2))

"""消息推送模块 - 企业微信 / 钉钉 / 邮件"""

import json
import smtplib
import urllib.request
from email.mime.text import MIMEText
from datetime import datetime
from config import PUSH_CONFIG


class PushNotifier:
    """消息推送器"""

    def __init__(self):
        self.config = PUSH_CONFIG

    def push_qywechat(self, content):
        """企业微信机器人推送"""
        webhook = self.config.get("qy_webhook", "")
        if not webhook:
            print("[推送] 企业微信未配置")
            return False
        try:
            data = {"msgtype": "markdown", "markdown": {"content": content}}
            req = urllib.request.Request(
                webhook,
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=10)
            result = json.loads(resp.read())
            ok = result.get("errcode") == 0
            print(f"[推送] 企业微信: {'成功' if ok else '失败'}")
            return ok
        except Exception as e:
            print(f"[推送] 企业微信异常: {e}")
            return False

    def push_dingtalk(self, content):
        """钉钉机器人推送"""
        webhook = self.config.get("dingtalk_webhook", "")
        if not webhook:
            print("[推送] 钉钉未配置")
            return False
        try:
            data = {"msgtype": "markdown", "markdown": {"title": "A股买入信号", "text": content}}
            req = urllib.request.Request(
                webhook,
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=10)
            result = json.loads(resp.read())
            ok = result.get("errcode") == 0
            print(f"[推送] 钉钉: {'成功' if ok else '失败'}")
            return ok
        except Exception as e:
            print(f"[推送] 钉钉异常: {e}")
            return False

    def push_serverchan(self, title, content):
        """Server酱推送"""
        key = self.config.get("serverchan_key", "")
        if not key:
            print("[推送] Server酱未配置")
            return False
        try:
            url = f"https://sctapi.ftqq.com/{key}.send"
            data = urllib.parse.urlencode({"title": title, "desp": content}).encode()
            req = urllib.request.Request(url, data=data)
            resp = urllib.request.urlopen(req, timeout=10)
            print(f"[推送] Server酱: 成功")
            return True
        except Exception as e:
            print(f"[推送] Server酱异常: {e}")
            return False

    def push_email(self, subject, content):
        """邮件推送"""
        smtp_host = self.config.get("smtp_host", "")
        if not smtp_host:
            print("[推送] 邮件未配置")
            return False
        try:
            msg = MIMEText(content, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = self.config["smtp_user"]
            msg["To"] = self.config["email_to"]

            with smtplib.SMTP_SSL(smtp_host, self.config["smtp_port"]) as server:
                server.login(self.config["smtp_user"], self.config["smtp_pass"])
                server.sendmail(self.config["smtp_user"],
                                self.config["email_to"], msg.as_string())
            print(f"[推送] 邮件: 成功")
            return True
        except Exception as e:
            print(f"[推送] 邮件异常: {e}")
            return False

    def push_all(self, title, content):
        """推送到所有已配置渠道"""
        results = {}
        results["qywechat"] = self.push_qywechat(content)
        results["dingtalk"] = self.push_dingtalk(content)
        results["serverchan"] = self.push_serverchan(title, content)
        results["email"] = self.push_email(title, content)
        return results

    @staticmethod
    def format_signal_message(signals, regime, industry_report):
        """格式化信号消息为Markdown"""
        today = datetime.now().strftime("%Y-%m-%d")
        position = {"bull": "80-100%", "oscillate": "40-60%", "bear": "0-20%"}.get(
            regime["state_label"], "50%"
        )

        lines = [
            f"## 【{today} 中线波段买入信号】\n",
            f"**市场状态**: {regime['state_name']}  (建议仓位: {position})\n",
            f"**强势行业**: {industry_report}\n",
            "",
        ]

        if not signals:
            lines.append("**今日无触发买入条件的个股**\n")
        else:
            lines.append(f"**触发买入条件 ({len(signals)} 只):**\n")
            for i, s in enumerate(signals, 1):
                lines.append(f"{i}. **{s.get('name', '')} ({s['symbol']})**")
                lines.append(f"   └ 综合评分: {s['total_score']} | "
                             f"收盘: {s['close']} | 量比: {s['vol_ratio']} | "
                             f"行业: {s.get('industry', '-')}")
                lines.append(f"   └ 趋势分:{s.get('trend_score', 0)} "
                             f"量能分:{s.get('volume_score', 0)} "
                             f"CVaR:{s.get('cvar', 0):.2%}")
                if s.get("score"):
                    lines.append(f"   └ LGB评分: {s['score']}")

        lines.extend([
            "",
            "---",
            "⚠️ 信号基于尾盘确认，次日开盘可择机买入",
            "⚠️ 单只个股仓位建议≤10%",
            f"*生成时间: {datetime.now().strftime('%H:%M')}*",
        ])
        return "\n".join(lines)

"""
桌面番茄钟 (Pomodoro Timer)
功能：计时、任务管理、统计、通知
"""

import tkinter as tk
from tkinter import ttk, messagebox
import time
import threading
import json
import os
from datetime import datetime, date
import platform

# ── 配置 ─────────────────────────────────────────────
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pomodoro_config.json")
STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pomodoro_stats.json")

DEFAULT_CONFIG = {
    "work": 25,       # 工作分钟
    "short_break": 5,  # 短休息分钟
    "long_break": 15,  # 长休息分钟
    "long_break_interval": 4,  # 每几个番茄后长休息
    "volume": 0.5,     # 音量 0-1
    "always_on_top": False,
    "theme": "blue",
}

THEMES = {
    "blue": {
        "bg": "#1a1a2e", "fg": "#e0e0e0", "accent": "#4a9eff",
        "timer_bg": "#16213e", "btn_bg": "#0f3460", "btn_fg": "#e0e0e0",
        "progress": "#4a9eff", "card_bg": "#1e2a45",
    },
    "green": {
        "bg": "#1a2e1a", "fg": "#e0e0e0", "accent": "#4caf50",
        "timer_bg": "#162e16", "btn_bg": "#2e7d32", "btn_fg": "#e0e0e0",
        "progress": "#4caf50", "card_bg": "#1e3a1e",
    },
    "warm": {
        "bg": "#2e1a1a", "fg": "#e0e0e0", "accent": "#ff7043",
        "timer_bg": "#2e1616", "btn_bg": "#bf360c", "btn_fg": "#e0e0e0",
        "progress": "#ff7043", "card_bg": "#3a1e1e",
    },
    "dark": {
        "bg": "#121212", "fg": "#e0e0e0", "accent": "#bb86fc",
        "timer_bg": "#1e1e1e", "btn_bg": "#333333", "btn_fg": "#e0e0e0",
        "progress": "#bb86fc", "card_bg": "#1e1e1e",
    },
}


# ── 工具函数 ────────────────────────────────────────
def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"保存失败: {e}")


def format_time(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


# ── 主应用 ──────────────────────────────────────────
class PomodoroApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("番茄钟 Pomodoro Timer")
        self.root.geometry("420+580")
        self.root.minsize(400, 520)

        # 加载配置
        self.config = load_json(CONFIG_FILE, DEFAULT_CONFIG)
        self.stats = load_json(STATS_FILE, {"total_pomodoros": 0, "daily": {}})
        self.theme = THEMES.get(self.config.get("theme", "blue"), THEMES["blue"])

        # 状态变量
        self.phase = "work"        # work | short_break | long_break
        self.running = False
        self.paused = False
        self.completed_pomodoros = 0  # 当前轮次已完成番茄

        self.work_seconds = self.config["work"] * 60
        self.break_seconds = self.config["short_break"] * 60
        self.long_break_seconds = self.config["long_break"] * 60
        self.remaining = self.work_seconds
        self._end_time = None  # 绝对结束时间（防漂移）

        # 任务列表
        self.tasks = []
        self.current_task = tk.StringVar()

        # 构建 UI
        self._build_ui()
        self._apply_theme()
        self._update_display()

        # 窗口置顶
        if self.config.get("always_on_top", False):
            self.root.attributes("-topmost", True)

        # 绑定关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI 构建 ──────────────────────────────────────
    def _build_ui(self):
        # 主容器
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(fill="both", expand=True, padx=16, pady=(12, 16))

        # ── 标题 ──
        title_frame = tk.Frame(self.main_frame)
        title_frame.pack(fill="x", pady=(0, 8))

        tk.Label(title_frame, text="🍅 番茄钟", font=("Segoe UI", 18, "bold")).pack(side="left")

        # 主题切换 & 置顶按钮
        self._top_btn = tk.Button(title_frame, text="📌", font=("Segoe UI", 11),
                                  bd=0, cursor="hand2", command=self._toggle_top)
        self._top_btn.pack(side="right", padx=(2, 0))

        self._theme_btn = tk.Button(title_frame, text="🎨", font=("Segoe UI", 11),
                                     bd=0, cursor="hand2", command=self._cycle_theme)
        self._theme_btn.pack(side="right", padx=(2, 0))

        # ── 阶段标签 ──
        phase_names = {"work": "⏰ 专注时间", "short_break": "☕ 短休息",
                       "long_break": "🌿 长休息"}
        self.phase_label = tk.Label(self.main_frame, text=phase_names["work"],
                                     font=("Segoe UI", 13))
        self.phase_label.pack(pady=(0, 4))

        # ── 计时器 ──
        timer_frame = tk.Frame(self.main_frame)
        timer_frame.pack(pady=(0, 8))

        self.timer_label = tk.Label(timer_frame, text="25:00",
                                     font=("Segoe UI", 56, "bold"))
        self.timer_label.pack()

        # ── 进度条 ──
        self.progress = ttk.Progressbar(self.main_frame, length=320, mode="determinate")
        self.progress.pack(pady=(0, 10))

        # ── 控制按钮 ──
        btn_frame = tk.Frame(self.main_frame)
        btn_frame.pack(pady=(0, 10))

        self.start_btn = tk.Button(btn_frame, text="▶ 开始", font=("Segoe UI", 11, "bold"),
                                    width=8, bd=0, cursor="hand2",
                                    command=self._toggle_timer)
        self.start_btn.pack(side="left", padx=4)

        self.reset_btn = tk.Button(btn_frame, text="↺ 重置", font=("Segoe UI", 11),
                                    width=8, bd=0, cursor="hand2",
                                    command=self._reset_timer)
        self.skip_btn = tk.Button(btn_frame, text="⏭ 跳过", font=("Segoe UI", 11),
                                   width=8, bd=0, cursor="hand2",
                                   command=self._skip_phase)
        self.reset_btn.pack(side="left", padx=4)
        self.skip_btn.pack(side="left", padx=4)

        # ── 番茄计数 ──
        self.count_label = tk.Label(self.main_frame, text="今日番茄: 0",
                                     font=("Segoe UI", 10))
        self.count_label.pack(pady=(0, 10))

        # ── 分隔线 ──
        sep = tk.Frame(self.main_frame, height=1)
        sep.pack(fill="x", pady=(0, 10))

        # ── 任务区域 ──
        task_header = tk.Frame(self.main_frame)
        task_header.pack(fill="x")

        tk.Label(task_header, text="📋 任务列表", font=("Segoe UI", 12, "bold")).pack(side="left")

        # 任务输入
        input_frame = tk.Frame(self.main_frame)
        input_frame.pack(fill="x", pady=(6, 4))

        self.task_entry = tk.Entry(input_frame, font=("Segoe UI", 11), relief="flat")
        self.task_entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.task_entry.bind("<Return>", lambda e: self._add_task())

        add_btn = tk.Button(input_frame, text="＋ 添加", font=("Segoe UI", 10),
                             bd=0, cursor="hand2", command=self._add_task)
        add_btn.pack(side="right", padx=(6, 0))

        # 任务列表
        list_frame = tk.Frame(self.main_frame)
        list_frame.pack(fill="both", expand=True)

        self.task_canvas = tk.Canvas(list_frame, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.task_canvas.yview)
        self.task_scroll_frame = tk.Frame(self.task_canvas)

        self.task_scroll_frame.bind("<Configure>",
                                    lambda e: self.task_canvas.configure(
                                        scrollregion=self.task_canvas.bbox("all")))
        self.task_canvas.create_window((0, 0), window=self.task_scroll_frame, anchor="nw")
        self.task_canvas.configure(yscrollcommand=scrollbar.set)

        self.task_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 底部统计
        stat_frame = tk.Frame(self.main_frame)
        stat_frame.pack(fill="x", pady=(8, 0))

        self.stat_label = tk.Label(stat_frame, text="", font=("Segoe UI", 9))
        self.stat_label.pack(side="left")

        # 设置按钮
        settings_btn = tk.Button(stat_frame, text="⚙ 设置", font=("Segoe UI", 9),
                                  bd=0, cursor="hand2", command=self._show_settings)
        settings_btn.pack(side="right")

        # 更新统计显示
        self._update_stats()
        self._load_tasks()

    def _apply_theme(self):
        t = self.theme
        self.root.configure(bg=t["bg"])
        self.main_frame.configure(bg=t["bg"])
        self.phase_label.configure(bg=t["bg"], fg=t["accent"])
        self.timer_label.configure(bg=t["timer_bg"], fg=t["fg"])
        self.count_label.configure(bg=t["bg"], fg=t["fg"])
        self.stat_label.configure(bg=t["bg"], fg=t["fg"])
        self.start_btn.configure(bg=t["accent"], fg=t["bg"],
                                 activebackground=t["progress"], activeforeground=t["bg"])
        self.reset_btn.configure(bg=t["btn_bg"], fg=t["btn_fg"],
                                 activebackground=t["card_bg"], activeforeground=t["btn_fg"])
        self.skip_btn.configure(bg="#e65100", fg="white",
                                activebackground="#ff8f00", activeforeground="white")
        self._top_btn.configure(bg=t["bg"], fg=t["fg"],
                                activebackground=t["card_bg"], activeforeground=t["fg"])
        self._theme_btn.configure(bg=t["bg"], fg=t["fg"],
                                  activebackground=t["card_bg"], activeforeground=t["fg"])
        self.task_entry.configure(bg=t["card_bg"], fg=t["fg"],
                                  insertbackground=t["fg"])
        # 进度条
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TProgressbar", background=t["progress"],
                        troughcolor=t["timer_bg"], thickness=8)

    # ── 计时器逻辑 ──────────────────────────────────
    def _toggle_timer(self):
        if self.paused:
            self.paused = False
            self.running = True
            self._end_time = time.time() + self.remaining
            self.start_btn.configure(text="⏸ 暂停")
            self._tick()
        elif self.running:
            self.running = False
            self.paused = True
            self.start_btn.configure(text="▶ 继续")
        else:
            self.running = True
            self.paused = False
            self._end_time = time.time() + self.remaining
            self.start_btn.configure(text="⏸ 暂停")
            self._tick()

    def _tick(self):
        """基于绝对时间的计时器滴答（防漂移）"""
        if not self.running or self.paused:
            return

        self.remaining = self._end_time - time.time()

        if self.remaining <= 0:
            self.remaining = 0
            self._update_display()
            self._timer_complete()
            return

        self._update_display()
        # 精确到最近的 100ms 检查，保证视觉上每秒更新
        interval = min(100, int(self.remaining * 1000) % 1000) if self.remaining > 0 else 100
        self._timer_job = self.root.after(interval, self._tick)

    def _reset_timer(self):
        self.running = False
        self.paused = False
        self.start_btn.configure(text="▶ 开始")
        self._end_time = None
        if hasattr(self, "_timer_job"):
            try:
                self.root.after_cancel(self._timer_job)
            except Exception:
                pass

        if self.phase == "work":
            self.remaining = self.work_seconds
        elif self.phase == "short_break":
            self.remaining = self.break_seconds
        else:
            self.remaining = self.long_break_seconds
        self._update_display()

    def _skip_phase(self):
        self.remaining = 0
        self._timer_complete()

    def _timer_complete(self):
        self.running = False
        self.paused = False
        self.start_btn.configure(text="▶ 开始")

        if self.phase == "work":
            # 完成一个番茄
            self.completed_pomodoros += 1
            self.stats["total_pomodoros"] += 1
            today = str(date.today())
            self.stats["daily"].setdefault(today, 0)
            self.stats["daily"][today] += 1
            save_json(STATS_FILE, self.stats)
            self._update_stats()
            self._update_display()

            # 决定休息类型
            if self.completed_pomodoros % self.config["long_break_interval"] == 0:
                self.phase = "long_break"
                self.remaining = self.long_break_seconds
            else:
                self.phase = "short_break"
                self.remaining = self.break_seconds

            self._notify("番茄完成！", f"已完成 {self.stats['total_pomodoros']} 个番茄，休息一下吧！")
            self.count_label.configure(text=f"🍅 x{self.completed_pomodoros}")

        else:
            # 休息结束，回到工作
            self.phase = "work"
            self.remaining = self.work_seconds
            self._notify("休息结束", "该继续专注了！")

        self._update_display()

    # ── 通知 ──────────────────────────────────────────
    def _notify(self, title, message):
        """桌面通知（跨平台）"""
        system = platform.system()
        try:
            if system == "Windows":
                from plyer import notification
                notification.notify(title=title, message=message, app_name="番茄钟", timeout=5)
            elif system == "Darwin":
                import subprocess
                subprocess.run(["osascript", "-e",
                                f'display notification "{message}" with title "{title}"'])
            else:
                import subprocess
                subprocess.run(["notify-send", title, message])
        except ImportError:
            # plyer 不可用时用 tkinter 弹窗
            self.root.after(0, lambda: messagebox.showinfo(title, message))
        except Exception:
            self.root.after(0, lambda: messagebox.showinfo(title, message))

    # ── 显示更新 ──────────────────────────────────────
    def _update_display(self):
        """更新计时器显示"""
        phase_names = {"work": "⏰ 专注时间", "short_break": "☕ 短休息",
                       "long_break": "🌿 长休息"}
        self.phase_label.configure(text=phase_names.get(self.phase, "专注时间"))

        self.timer_label.configure(text=format_time(self.remaining))

        # 进度条
        if self.phase == "work":
            total = self.work_seconds
        elif self.phase == "short_break":
            total = self.break_seconds
        else:
            total = self.long_break_seconds

        if total > 0:
            pct = max(0, int((total - self.remaining) / total * 100))
            self.progress["value"] = pct

        # 窗口标题
        if self.running:
            self.root.title(f"{format_time(self.remaining)} - 番茄钟")
        elif self.paused:
            self.root.title(f"⏸ {format_time(self.remaining)} - 番茄钟")
        else:
            self.root.title("番茄钟 Pomodoro Timer")

    def _update_stats(self):
        today = str(date.today())
        daily = self.stats.get("daily", {}).get(today, 0)
        self.stat_label.configure(
            text=f"总计: {self.stats['total_pomodoros']} 个番茄 | 今日: {daily} 个"
        )

    # ── 主题与置顶 ───────────────────────────────────
    def _cycle_theme(self):
        names = list(THEMES.keys())
        idx = names.index(self.config.get("theme", "blue"))
        idx = (idx + 1) % len(names)
        self.config["theme"] = names[idx]
        self.theme = THEMES[names[idx]]
        self._apply_theme()
        save_json(CONFIG_FILE, self.config)

    def _toggle_top(self):
        on_top = not self.config.get("always_on_top", False)
        self.config["always_on_top"] = on_top
        self.root.attributes("-topmost", on_top)
        save_json(CONFIG_FILE, self.config)

    # ── 任务管理 ──────────────────────────────────────
    def _add_task(self):
        text = self.task_entry.get().strip()
        if text:
            self.tasks.insert(0, {"text": text, "done": False})
            self.task_entry.delete(0, "end")
            self._render_tasks()
            self._save_tasks()

    def _toggle_task(self, idx):
        self.tasks[idx]["done"] = not self.tasks[idx]["done"]
        self._render_tasks()
        self._save_tasks()

    def _delete_task(self, idx):
        del self.tasks[idx]
        self._render_tasks()
        self._save_tasks()

    def _render_tasks(self):
        for w in self.task_scroll_frame.winfo_children():
            w.destroy()

        if not self.tasks:
            empty = tk.Label(self.task_scroll_frame,
                             text="暂无任务，在上方添加吧 ✍",
                             font=("Segoe UI", 10), fg="#888")
            empty.pack(pady=16)
            return

        for i, task in enumerate(self.tasks):
            f = tk.Frame(self.task_scroll_frame)
            f.pack(fill="x", pady=2)

            # 完成复选框
            status = "✅" if task["done"] else "⬜"
            cb = tk.Button(f, text=status, font=("Segoe UI", 10),
                           bd=0, cursor="hand2",
                           command=lambda idx=i: self._toggle_task(idx))
            cb.pack(side="left", padx=(0, 4))

            # 任务文本
            txt = task["text"]
            if task["done"]:
                txt = f"~~{txt}~~"  # 视觉标记已完成
            label = tk.Label(f, text=txt, font=("Segoe UI", 10),
                             anchor="w")
            if task["done"]:
                label.configure(fg="#666")
            label.pack(side="left", fill="x", expand=True)

            # 删除按钮
            del_btn = tk.Button(f, text="✕", font=("Segoe UI", 9),
                                 bd=0, fg="#e74c3c", cursor="hand2",
                                 command=lambda idx=i: self._delete_task(idx))
            del_btn.pack(side="right")

    def _save_tasks(self):
        save_json(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                  "pomodoro_tasks.json"), self.tasks)

    def _load_tasks(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "pomodoro_tasks.json")
        data = load_json(path, [])
        if isinstance(data, list):
            self.tasks = data
        self._render_tasks()

    # ── 设置对话框 ───────────────────────────────────
    def _show_settings(self):
        win = tk.Toplevel(self.root)
        win.title("设置")
        win.geometry("300x280+950+580")
        win.resizable(False, False)
        win.configure(bg=self.theme["bg"])
        win.transient(self.root)
        win.grab_set()

        fields = [
            ("work", "专注时间 (分)", 1, 120),
            ("short_break", "短休息 (分)", 1, 30),
            ("long_break", "长休息 (分)", 1, 60),
        ]

        entries = {}
        for i, (key, label, min_v, max_v) in enumerate(fields):
            tk.Label(win, text=label, font=("Segoe UI", 10),
                     bg=self.theme["bg"], fg=self.theme["fg"]).pack(anchor="w", padx=16, pady=(12 if i == 0 else 6, 0))

            var = tk.StringVar(value=str(self.config[key]))
            e = tk.Entry(win, textvariable=var, font=("Segoe UI", 11), width=8,
                         relief="flat", justify="center")
            e.pack(pady=(2, 0))
            entries[key] = (var, min_v, max_v)

        # 长休息间隔
        tk.Label(win, text="长休息间隔 (番茄数)", font=("Segoe UI", 10),
                 bg=self.theme["bg"], fg=self.theme["fg"]).pack(anchor="w", padx=16, pady=(10, 0))
        interval_var = tk.StringVar(value=str(self.config["long_break_interval"]))
        interval_e = tk.Entry(win, textvariable=interval_var, font=("Segoe UI", 11),
                               width=8, relief="flat", justify="center")
        interval_e.pack(pady=(2, 0))

        def save_settings():
            try:
                for key, (var, min_v, max_v) in entries.items():
                    val = int(var.get().strip())
                    val = max(min_v, min(max_v, val))
                    self.config[key] = val

                self.config["long_break_interval"] = max(1, int(interval_var.get().strip()))

                self.work_seconds = self.config["work"] * 60
                self.break_seconds = self.config["short_break"] * 60
                self.long_break_seconds = self.config["long_break"] * 60

                if not self.running:
                    self._reset_timer()

                save_json(CONFIG_FILE, self.config)
                win.destroy()
            except ValueError:
                messagebox.showerror("错误", "请输入有效数字", parent=win)

        tk.Button(win, text="保存", font=("Segoe UI", 10, "bold"),
                  bg=self.theme["accent"], fg=self.theme["bg"],
                  bd=0, cursor="hand2", command=save_settings).pack(pady=(14, 0))

    # ── 关闭 ──────────────────────────────────────────
    def _on_close(self):
        self.running = False
        if hasattr(self, "_timer_job"):
            try:
                self.root.after_cancel(self._timer_job)
            except Exception:
                pass
        save_json(CONFIG_FILE, self.config)
        save_json(STATS_FILE, self.stats)
        self._save_tasks()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ── 入口 ────────────────────────────────────────────
if __name__ == "__main__":
    app = PomodoroApp()
    app.run()

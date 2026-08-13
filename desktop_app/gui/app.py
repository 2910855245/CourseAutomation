"""网课助手 — customtkinter 主窗口"""
import customtkinter as ctk
import threading
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import WEBSITES
from gui.widgets.log_box import LogBox
from gui.widgets.course_card import CourseCard

# ── 极简黑白主题 ──
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

BG       = "#0a0a0a"
BG_CARD  = "#141414"
BG_INPUT = "#1a1a1a"
BORDER   = "#2a2a2a"
TEXT     = "#e5e5e5"
DIM      = "#a3a3a3"
MUTED    = "#525252"
ACCENT   = "#e5e5e5"
PRIMARY  = "#3b82f6"
SUCCESS  = "#22c55e"
ERROR    = "#ef4444"
WARN     = "#f59e0b"


class App(ctk.CTk):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.title("网课助手")
        self.geometry("980x680")
        self.minsize(860, 560)
        self.configure(fg_color=BG)

        self._sessions = {}
        self._username = ""
        self._password = ""
        self._courses_data = {}
        self._cards = []
        self._worker = None

        self._build()

    # ══════════════════════════════════════
    #  布局
    # ══════════════════════════════════════

    def _build(self):
        # ── 顶栏 ──
        header = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, height=48)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="网课助手", font=("", 16, "bold"), text_color=TEXT).pack(side="left", padx=16)
        ctk.CTkLabel(header, text="v1.0", font=("", 11), text_color=MUTED).pack(side="left")

        self.conn_label = ctk.CTkLabel(header, text="● 未连接", font=("", 11), text_color=MUTED)
        self.conn_label.pack(side="right", padx=16)

        # ── 标签页 ──
        self.tabview = ctk.CTkTabview(self, fg_color=BG, segmented_button_fg_color=BG_CARD,
                                       segmented_button_selected_color="#2a2a2a",
                                       segmented_button_selected_hover_color="#333",
                                       segmented_button_unselected_color=BG_CARD,
                                       text_color=DIM, corner_radius=0)
        self.tabview.pack(fill="both", expand=True, padx=0, pady=0)

        self.tab_login = self.tabview.add("  登录  ")
        self.tab_courses = self.tabview.add("  课程  ")
        self.tab_exam = self.tabview.add("  考试  ")
        self.tab_settings = self.tabview.add("  设置  ")

        self._build_login_tab()
        self._build_courses_tab()
        self._build_exam_tab()
        self._build_settings_tab()

        # ── 底部日志 ──
        self.log_box = LogBox(self, height=130, fg_color="#111", border_color=BORDER, border_width=1, corner_radius=8)
        self.log_box.pack(fill="x", padx=8, pady=(0, 8))

    # ══════════════════════════════════════
    #  登录页
    # ══════════════════════════════════════

    def _build_login_tab(self):
        f = self.tab_login

        ctk.CTkLabel(f, text="账号登录", font=("", 18, "bold"), text_color=TEXT).pack(anchor="w", padx=24, pady=(20, 12))

        # 账号密码
        card = ctk.CTkFrame(f, fg_color=BG_CARD, corner_radius=12, border_color=BORDER, border_width=1)
        card.pack(fill="x", padx=24, pady=(0, 12))

        ctk.CTkLabel(card, text="学号 / 手机号", font=("", 12), text_color=MUTED).pack(anchor="w", padx=16, pady=(16, 4))
        self.entry_user = ctk.CTkEntry(card, height=40, corner_radius=8, fg_color=BG_INPUT,
                                        border_color=BORDER, text_color=TEXT, placeholder_text="请输入账号")
        self.entry_user.pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkLabel(card, text="密码", font=("", 12), text_color=MUTED).pack(anchor="w", padx=16, pady=(8, 4))
        self.entry_pass = ctk.CTkEntry(card, height=40, corner_radius=8, fg_color=BG_INPUT,
                                        border_color=BORDER, text_color=TEXT, placeholder_text="请输入密码", show="•")
        self.entry_pass.pack(fill="x", padx=16, pady=(0, 16))

        # 平台选择
        ctk.CTkLabel(f, text="选择平台", font=("", 14, "bold"), text_color=DIM).pack(anchor="w", padx=24, pady=(8, 8))

        plat_card = ctk.CTkFrame(f, fg_color=BG_CARD, corner_radius=12, border_color=BORDER, border_width=1)
        plat_card.pack(fill="x", padx=24, pady=(0, 16))

        self.platform_vars = {}
        for wid, info in WEBSITES.items():
            var = ctk.BooleanVar(value=True)
            self.platform_vars[wid] = var
            ctk.CTkCheckBox(plat_card, text=f"  {info['name']}", variable=var,
                            font=("", 12), text_color=DIM, fg_color=PRIMARY,
                            border_color="#444", hover_color="#555", corner_radius=4
                            ).pack(anchor="w", padx=16, pady=6)

        # 登录按钮
        self.btn_login = ctk.CTkButton(f, text="一键登录所有平台", height=44, corner_radius=10,
                                        fg_color=PRIMARY, hover_color="#2563eb",
                                        font=("", 14, "bold"), command=self._on_login)
        self.btn_login.pack(fill="x", padx=24, pady=(0, 8))

        self.login_status = ctk.CTkLabel(f, text="", font=("", 12), text_color=MUTED)
        self.login_status.pack(anchor="w", padx=24)

    # ══════════════════════════════════════
    #  课程页
    # ══════════════════════════════════════

    def _build_courses_tab(self):
        f = self.tab_courses

        # 按钮栏
        btn_bar = ctk.CTkFrame(f, fg_color="transparent")
        btn_bar.pack(fill="x", padx=16, pady=(12, 8))

        self.btn_scan = ctk.CTkButton(btn_bar, text="扫描课程", height=36, corner_radius=8,
                                       fg_color="#333", hover_color="#444", font=("", 12),
                                       command=self._on_scan)
        self.btn_scan.pack(side="left", padx=(0, 8))

        ctk.CTkButton(btn_bar, text="全选", width=60, height=36, corner_radius=8,
                       fg_color="#222", hover_color="#333", font=("", 11),
                       command=self._select_all).pack(side="left", padx=(0, 4))
        ctk.CTkButton(btn_bar, text="全不选", width=60, height=36, corner_radius=8,
                       fg_color="#222", hover_color="#333", font=("", 11),
                       command=self._deselect_all).pack(side="left")

        self.btn_start = ctk.CTkButton(btn_bar, text="开始刷课", height=36, corner_radius=8,
                                        fg_color=PRIMARY, hover_color="#2563eb",
                                        font=("", 12, "bold"), command=self._on_start_study, state="disabled")
        self.btn_start.pack(side="right", padx=(8, 0))

        self.btn_stop = ctk.CTkButton(btn_bar, text="停止", width=60, height=36, corner_radius=8,
                                       fg_color=ERROR, hover_color="#dc2626", font=("", 12),
                                       command=self._on_stop_study, state="disabled")
        self.btn_stop.pack(side="right")

        # 总进度
        self.study_progress = ctk.CTkProgressBar(f, height=8, corner_radius=4,
                                                  fg_color="#1e293b", progress_color=PRIMARY)
        self.study_progress.pack(fill="x", padx=16, pady=(0, 8))
        self.study_progress.set(0)

        # 课程列表（可滚动）
        self.course_scroll = ctk.CTkScrollableFrame(f, fg_color="transparent",
                                                     scrollbar_button_color="#333",
                                                     scrollbar_button_hover_color="#555")
        self.course_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 4))

    # ══════════════════════════════════════
    #  考试页
    # ══════════════════════════════════════

    def _build_exam_tab(self):
        f = self.tab_exam

        # API Key
        key_frame = ctk.CTkFrame(f, fg_color="transparent")
        key_frame.pack(fill="x", padx=16, pady=(12, 8))

        ctk.CTkLabel(key_frame, text="DeepSeek API Key", font=("", 12), text_color=MUTED).pack(side="left")
        self.entry_api_key = ctk.CTkEntry(key_frame, height=36, corner_radius=8, fg_color=BG_INPUT,
                                           border_color=BORDER, text_color=TEXT, placeholder_text="sk-...", show="•")
        self.entry_api_key.pack(side="left", fill="x", expand=True, padx=(12, 8))

        ctk.CTkButton(key_frame, text="刷新考试", height=36, corner_radius=8,
                       fg_color="#333", hover_color="#444", font=("", 11),
                       command=self._on_refresh_exams).pack(side="right")

        # 考试表格（用 Text 模拟）
        self.exam_text = ctk.CTkTextbox(f, fg_color=BG_CARD, corner_radius=8,
                                         border_color=BORDER, border_width=1,
                                         font=("Consolas", 11), text_color=DIM)
        self.exam_text.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        # 操作按钮
        btn_bar = ctk.CTkFrame(f, fg_color="transparent")
        btn_bar.pack(fill="x", padx=16, pady=(0, 12))

        self.btn_solve = ctk.CTkButton(btn_bar, text="一键答题", height=36, corner_radius=8,
                                        fg_color=PRIMARY, hover_color="#2563eb",
                                        font=("", 12, "bold"), command=self._on_solve_all, state="disabled")
        self.btn_solve.pack(side="left")

    # ══════════════════════════════════════
    #  设置页
    # ══════════════════════════════════════

    def _build_settings_tab(self):
        f = self.tab_settings

        ctk.CTkLabel(f, text="设置", font=("", 18, "bold"), text_color=TEXT).pack(anchor="w", padx=24, pady=(20, 12))

        card = ctk.CTkFrame(f, fg_color=BG_CARD, corner_radius=12, border_color=BORDER, border_width=1)
        card.pack(fill="x", padx=24, pady=(0, 16))

        ctk.CTkLabel(card, text="DeepSeek API Key", font=("", 12), text_color=MUTED).pack(anchor="w", padx=16, pady=(16, 4))
        self.settings_api_key = ctk.CTkEntry(card, height=40, corner_radius=8, fg_color=BG_INPUT,
                                              border_color=BORDER, text_color=TEXT, placeholder_text="sk-...", show="•")
        self.settings_api_key.pack(fill="x", padx=16, pady=(0, 16))

    # ══════════════════════════════════════
    #  逻辑
    # ══════════════════════════════════════

    def _on_login(self):
        username = self.entry_user.get().strip()
        password = self.entry_pass.get().strip()
        if not username or not password:
            self._log("请输入账号和密码", "warning")
            return
        selected = [wid for wid, var in self.platform_vars.items() if var.get()]
        if not selected:
            self._log("请至少选择一个平台", "warning")
            return

        self.btn_login.configure(state="disabled", text="登录中...")
        self._log("开始登录...")

        def _do():
            from core.auth import login_single_platform, save_platform_cookie
            results = {}
            for wid in selected:
                self._log(f"登录 {WEBSITES[wid]['name']}...")
                try:
                    _, ok, session, msg = login_single_platform(wid, username, password)
                    if ok:
                        save_platform_cookie(username, wid, session)
                        results[wid] = session
                        self._log(f"✓ {WEBSITES[wid]['name']}: {msg}", "success")
                    else:
                        self._log(f"✗ {WEBSITES[wid]['name']}: {msg}", "error")
                except Exception as e:
                    self._log(f"✗ {WEBSITES[wid]['name']}: {e}", "error")

            self._sessions = results
            self._username = username
            self._password = password
            self.after(0, lambda: self._login_done(results))

        threading.Thread(target=_do, daemon=True).start()

    def _login_done(self, results):
        self.btn_login.configure(state="normal", text="一键登录所有平台")
        if results:
            self.conn_label.configure(text=f"● 已连接 · {len(results)} 平台", text_color=SUCCESS)
            self.login_status.configure(text=f"登录成功 {len(results)}/{len(self.platform_vars)} 个平台")
            self._log(f"登录成功，已连接 {len(results)} 个平台", "success")
        else:
            self.login_status.configure(text="所有平台登录失败")

    def _on_scan(self):
        if not self._sessions:
            self._log("请先登录", "warning")
            return
        self.btn_scan.configure(state="disabled", text="扫描中...")
        self._log("开始扫描课程...")

        def _do():
            from core.scanner import scan_platform
            all_data = {}
            for wid in self._sessions:
                self._log(f"扫描 {WEBSITES[wid]['name']}...")
                try:
                    result = scan_platform(self._username, self._password, wid)
                    all_data[wid] = result
                    self._log(f"✓ {WEBSITES[wid]['name']}: {len(result.get('courses', []))} 门课程", "success")
                except Exception as e:
                    self._log(f"✗ {WEBSITES[wid]['name']}: {e}", "error")
            self._courses_data = all_data
            self.after(0, self._populate_courses)

        threading.Thread(target=_do, daemon=True).start()

    def _populate_courses(self):
        for card in self._cards:
            card.destroy()
        self._cards.clear()

        for wid, result in self._courses_data.items():
            for course in result.get("courses", []):
                course["website_id"] = wid
                card = CourseCard(self.course_scroll, course)
                card.pack(fill="x", padx=8, pady=4)
                self._cards.append(card)

        self.btn_scan.configure(state="normal", text="扫描课程")
        self.btn_start.configure(state="normal")
        self._log(f"共加载 {len(self._cards)} 门课程")

    def _select_all(self):
        for card in self._cards:
            card.check_var.set(True)

    def _deselect_all(self):
        for card in self._cards:
            card.check_var.set(False)

    def _get_selected_videos(self):
        selected_ids = {card.course_id for card in self._cards if card.is_selected()}
        videos = []
        for wid, result in self._courses_data.items():
            for task in result.get("tasks", []):
                if task.get("task_type") == "video" and task.get("course_id") in selected_ids:
                    videos.append(task)
        return videos

    def _on_start_study(self):
        videos = self._get_selected_videos()
        if not videos:
            self._log("没有待刷的视频", "warning")
            return

        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self._log(f"开始刷 {len(videos)} 个视频...")

        from core.study_worker import StudyWorker
        first_wid = list(self._sessions.keys())[0]
        session = self._sessions[first_wid]
        cookie_str = "; ".join([f"{k}={v}" for k, v in session.cookies.items()])
        base_url = WEBSITES[first_wid]["base_url"]

        self._worker = StudyWorker(
            base_url=base_url, cookie_str=cookie_str,
            username=self._username, password=self._password,
            videos=videos,
            on_progress=lambda d: self.after(0, lambda: self._on_study_progress(d)),
            on_finished=lambda ok, msg: self.after(0, lambda: self._on_study_done(ok, msg)),
            on_log=lambda msg: self.after(0, lambda: self._log(msg)),
        )
        self._worker.start()

    def _on_stop_study(self):
        if self._worker:
            self._worker.stop()
            self._log("已发送停止信号", "warning")

    def _on_study_progress(self, data):
        pct = data.get("pct", 0) / 100
        self.study_progress.set(pct)

    def _on_study_done(self, success, msg):
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        if success:
            self.study_progress.set(1)
            self._log(f"✓ {msg}", "success")
        else:
            self._log(f"✗ {msg}", "error")

    def _on_refresh_exams(self):
        if not self._sessions:
            self._log("请先登录", "warning")
            return

        def _do():
            from core.scanner import scan_platform
            all_exams = []
            for wid in self._sessions:
                try:
                    result = scan_platform(self._username, self._password, wid)
                    for task in result.get("tasks", []):
                        if task.get("task_type") == "exam":
                            task["website_id"] = wid
                            all_exams.append(task)
                except Exception as e:
                    self._log(f"扫描失败: {e}", "error")
            self._exams = all_exams
            self.after(0, self._show_exams)

        threading.Thread(target=_do, daemon=True).start()

    def _show_exams(self):
        self.exam_text.configure(state="normal")
        self.exam_text.delete("1.0", "end")
        header = f"{'课程':<16} {'考试名称':<28} {'状态':<8} {'分数':<6}\n"
        self.exam_text.insert("end", header)
        self.exam_text.insert("end", "─" * 64 + "\n")
        for exam in getattr(self, "_exams", []):
            line = (f"{exam.get('course_name', '')[:14]:<16} "
                    f"{exam.get('name', '')[:26]:<28} "
                    f"{exam.get('submit_status', '未交'):<8} "
                    f"{exam.get('final_score', '-'):<6}\n")
            self.exam_text.insert("end", line)
        self.exam_text.configure(state="disabled")
        self.btn_solve.configure(state="normal")
        self._log(f"找到 {len(getattr(self, '_exams', []))} 个待答考试")

    def _on_solve_all(self):
        api_key = self.entry_api_key.get().strip() or self.settings_api_key.get().strip()
        if not api_key:
            self._log("请输入 DeepSeek API Key", "warning")
            return
        exams = getattr(self, "_exams", [])
        if not exams:
            self._log("没有待答考试", "warning")
            return

        self.btn_solve.configure(state="disabled", text="答题中...")

        from core.exam_worker import ExamWorker
        first_wid = list(self._sessions.keys())[0]
        self._worker = ExamWorker(
            session=self._sessions[first_wid],
            base_url=WEBSITES[first_wid]["base_url"],
            api_key=api_key, exams=exams,
            on_progress=lambda d: self.after(0, lambda: self._log(d.get("message", ""))),
            on_finished=lambda ok, msg: self.after(0, lambda: self._exam_done(ok, msg)),
            on_log=lambda msg: self.after(0, lambda: self._log(msg)),
        )
        self._worker.start()

    def _exam_done(self, success, msg):
        self.btn_solve.configure(state="normal", text="一键答题")
        if success:
            self._log(f"✓ {msg}", "success")
        else:
            self._log(f"✗ {msg}", "error")

    def _log(self, text, level="info"):
        self.log_box.append(text, level)

"""课程进度卡片"""
import customtkinter as ctk


class CourseCard(ctk.CTkFrame):
    """单门课程卡片"""

    def __init__(self, master, course_data: dict, **kwargs):
        super().__init__(master, fg_color="#1a1a1a", corner_radius=12, border_width=1, border_color="#333", **kwargs)
        self.course_data = course_data
        self.course_id = course_data.get("course_id", "")
        self._selected = True
        self._build()

    def _build(self):
        # 顶部：复选框 + 名称
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(12, 4))

        self.check_var = ctk.BooleanVar(value=True)
        self.checkbox = ctk.CTkCheckBox(top, text="", variable=self.check_var,
                                         width=24, height=24, corner_radius=4,
                                         fg_color="#0ea5e9", border_color="#555",
                                         hover_color="#38bdf8", command=self._on_toggle)
        self.checkbox.pack(side="left")

        name = self.course_data.get("course_name", "未知课程")
        ctk.CTkLabel(top, text=name, font=("", 14, "bold"), text_color="#e2e8f0").pack(side="left", padx=(8, 0))

        # 统计
        stats = ctk.CTkFrame(self, fg_color="transparent")
        stats.pack(fill="x", padx=16, pady=4)

        vt = self.course_data.get("video_total", 0)
        vd = self.course_data.get("video_completed", 0)
        et = self.course_data.get("exam_total", 0)
        ed = self.course_data.get("exam_done", 0)

        ctk.CTkLabel(stats, text=f"📹 {vd}/{vt}", font=("", 12),
                     text_color="#0ea5e9", fg_color="#0f172a", corner_radius=4).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(stats, text=f"📝 {ed}/{et}", font=("", 12),
                     text_color="#f59e0b", fg_color="#0f172a", corner_radius=4).pack(side="left")

        # 进度条
        bar_frame = ctk.CTkFrame(self, fg_color="transparent")
        bar_frame.pack(fill="x", padx=16, pady=(4, 12))

        self.progress = ctk.CTkProgressBar(bar_frame, height=6, corner_radius=3,
                                            fg_color="#1e293b", progress_color="#0ea5e9")
        self.progress.pack(fill="x")
        self.progress.set(vd / max(vt, 1))

    def _on_toggle(self):
        self._selected = self.check_var.get()

    def is_selected(self) -> bool:
        return self.check_var.get()

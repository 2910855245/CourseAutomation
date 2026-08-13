"""终端风格日志框"""
import customtkinter as ctk
from datetime import datetime


class LogBox(ctk.CTkTextbox):
    """只读日志框，支持追加"""

    LEVEL_ICONS = {"info": "›", "success": "✓", "warning": "⚠", "error": "✗"}

    def __init__(self, master, **kwargs):
        super().__init__(master, state="disabled", font=("Cascadia Code", 12), **kwargs)

    def append(self, text: str, level: str = "info"):
        ts = datetime.now().strftime("%H:%M:%S")
        icon = self.LEVEL_ICONS.get(level, "›")
        self.configure(state="normal")
        self.insert("end", f"[{ts}] {icon} {text}\n")
        self.configure(state="disabled")
        self.see("end")

    def clear_log(self):
        self.configure(state="normal")
        self.delete("1.0", "end")
        self.configure(state="disabled")

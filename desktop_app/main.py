#!/usr/bin/env python3
"""网课助手 — 桌面版入口"""
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
os.environ["TZ"] = "Asia/Shanghai"

from gui.app import App


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()

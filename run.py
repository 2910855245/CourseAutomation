#!/usr/bin/env python3
"""
启动入口
- 生产环境: granian --interface asgi run:app（见 Dockerfile）
- 开发环境: python run.py（uvicorn，带热重载）
"""
import os
import sys

# 设置中国时区（必须在其他模块导入前）
os.environ["TZ"] = "Asia/Shanghai"
try:
    import time
    time.tzset()
except AttributeError:
    pass  # Windows 不支持 time.tzset，通过 TZ 环境变量生效

# 设置工作目录
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

# 宝塔兼容：run.py 也导出 app 变量供 granian/uvicorn 使用
from api.main import app  # noqa: E402

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("         刷课系统 Web 服务器启动（开发模式）")
    print("=" * 60)
    print("访问地址：http://localhost:8000")
    print("=" * 60)
    uvicorn.run("run:app", host="0.0.0.0", port=8000, reload=True)

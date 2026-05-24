#!/usr/bin/env python3
import os
import sys
import subprocess
from pathlib import Path

# 设置工作目录
dir_path = Path(__file__).parent
os.chdir(str(dir_path))
sys.path.insert(0, str(dir_path))

print("="*60)
print("        刷课系统 Web 服务启动中...")
print("="*60)

try:
    import fastapi
    print("[1/3] FastAPI模块检查通过")
except ImportError:
    print("正在安装依赖，请稍候...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements-api.txt"])
    print("[1/3] 依赖安装完成")

try:
    from api.main import app
    print("[2/3] 应用模块导入通过")
except Exception as e:
    print(f"错误：{e}")
    input()
    sys.exit(1)

try:
    import uvicorn
    print("[3/3] Uvicorn已就绪")
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "uvicorn"])

print("\n" + "="*60)
print("启动成功！")
print("访问地址：http://localhost:8000")
print("按Ctrl+C停止服务")
print("="*60 + "\n")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

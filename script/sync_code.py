#!/usr/bin/env python3
"""同步代码到远程服务器（不动 data/ 和 .env）"""
import io
import os
import sys
import tempfile
import zipfile

import paramiko

HOST = "38.76.190.251"
PORT = 22
USER = "root"
REMOTE_ROOT = "/www/wwwroot/anti_course"

EXCLUDE_DIRS = {
    "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    ".git", ".claude", "node_modules", "data", "backups", "script",
    "tests", "presentation", "frontend",
}
EXCLUDE_FILES = {".env", ".coverage", "server.pid"}


def connect():
    key_path = os.path.join(os.path.dirname(__file__), "ssh_key")
    with open(key_path) as f:
        key_data = f.read()
    key = paramiko.Ed25519Key.from_private_key(io.StringIO(key_data))
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, PORT, USER, pkey=key, timeout=15, allow_agent=False, look_for_keys=False)
    return ssh


def collect_files(base):
    files = []
    for root, dirs, filenames in os.walk(base):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in filenames:
            if f in EXCLUDE_FILES:
                continue
            if f.endswith((".pyc", ".pyo")):
                continue
            rel = os.path.relpath(os.path.join(root, f), base).replace("\\", "/")
            files.append(rel)
    return sorted(set(files))


def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    files = collect_files(base)
    print(f"准备上传 {len(files)} 个文件")

    zip_path = os.path.join(tempfile.gettempdir(), "code_sync.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(os.path.join(base, f), f)

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"打包完成: {size_mb:.2f} MB")

    ssh = connect()
    sftp = ssh.open_sftp()
    sftp.put(zip_path, "/root/code_sync.zip")
    sftp.close()
    print("上传完成")

    stdin, stdout, stderr = ssh.exec_command(
        f"cd {REMOTE_ROOT} && unzip -o /root/code_sync.zip 2>&1 | tail -5",
        timeout=30,
    )
    print("解压:", stdout.read().decode("utf-8", errors="replace").strip())

    ssh.exec_command("rm -f /root/code_sync.zip")
    ssh.close()
    print("同步完成")


if __name__ == "__main__":
    main()

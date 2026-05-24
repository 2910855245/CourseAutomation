#!/usr/bin/env python3
"""部署并运行批量考试测试脚本到远程服务器"""
import io
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

import paramiko

HOST = "38.76.190.251"
PORT = 22
USER = "root"
REMOTE_DIR = "/www/wwwroot/anti_course"

def load_ssh_key():
    key_path = os.path.join(os.path.dirname(__file__), "ssh_key")
    with open(key_path) as f:
        return f.read()

def connect():
    kf = io.StringIO(load_ssh_key())
    key = paramiko.Ed25519Key.from_private_key(kf)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, PORT, USER, pkey=key, timeout=15, allow_agent=False, look_for_keys=False)
    return ssh

def run_remote(ssh, cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode("utf-8", errors="replace"), stderr.read().decode("utf-8", errors="replace")

def main():
    ssh = connect()
    sftp = ssh.open_sftp()

    # 上传更新的文件
    local_base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    files = [
        ("infrastructure/exam_fetcher.py", f"{REMOTE_DIR}/infrastructure/exam_fetcher.py"),
        ("infrastructure/exam_answerer.py", f"{REMOTE_DIR}/infrastructure/exam_answerer.py"),
        ("services/ai_service.py", f"{REMOTE_DIR}/services/ai_service.py"),
        ("script/tmp_batch_exam.py", f"{REMOTE_DIR}/script/tmp_batch_exam.py"),
    ]
    for local_rel, remote_path in files:
        local_path = os.path.join(local_base, local_rel)
        sftp.put(local_path, remote_path)
        print(f"Uploaded: {local_rel}")

    sftp.close()

    # 运行批量考试脚本（使用 venv）
    print("\n启动批量考试测试...\n")
    venv_python = f"{REMOTE_DIR}/venv/bin/python3"
    cmd = f"cd {REMOTE_DIR} && {venv_python} script/tmp_batch_exam.py 2>&1"
    out, err = run_remote(ssh, cmd, timeout=600)
    print(out)
    if err.strip():
        print("STDERR:", err[:500])

    ssh.close()

if __name__ == "__main__":
    main()

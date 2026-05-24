#!/usr/bin/env python3
"""Query and delete orders on remote server"""
import io
import os
import sys

import dotenv as _dotenv
import paramiko

_dotenv.load_dotenv(os.path.join(os.path.dirname(__file__), ".env.local"), override=False)

HOST = os.environ.get("REMOTE_HOST", "38.76.190.251")
PORT = int(os.environ.get("REMOTE_PORT", "22"))
USER = os.environ.get("REMOTE_USER", "root")

def _load_ssh_key():
    key_path = os.environ.get("SSH_KEY_PATH", os.path.join(os.path.dirname(__file__), "ssh_key"))
    if os.path.isfile(key_path):
        with open(key_path) as f:
            return f.read()
    return os.environ.get("SSH_KEY", "")

SSH_KEY = _load_ssh_key()

def connect():
    kf = io.StringIO(SSH_KEY)
    key = paramiko.Ed25519Key.from_private_key(kf)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, PORT, USER, pkey=key, timeout=15, allow_agent=False, look_for_keys=False)
    return ssh

def run_remote(ssh, cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode("utf-8", errors="replace"), stderr.read().decode("utf-8", errors="replace")

def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "list"
    order_id = sys.argv[2] if len(sys.argv) > 2 else ""

    ssh = connect()

    if action == "list":
        cmd = """cd /www/wwwroot/anti_course && python3 -c "
import sqlite3
conn = sqlite3.connect('data/orders.db')
c = conn.cursor()
c.execute('SELECT order_id, username, status, paid, price, website_id, task_type FROM orders')
for r in c.fetchall():
    print(r)
conn.close()
" """
        out, err = run_remote(ssh, cmd)
        print("=== Remote orders ===")
        print(out)
        if err.strip():
            print("STDERR:", err)

    elif action == "delete" and order_id:
        # Delete order and its related queue jobs
        cmd = f"""cd /www/wwwroot/anti_course && python3 -c "
import sqlite3
conn = sqlite3.connect('data/orders.db')
c = conn.cursor()
c.execute('SELECT order_id, username, status, paid, price, website_id FROM orders WHERE order_id = \\\"{order_id}\\\"')
row = c.fetchone()
if row:
    print('Found order:', row)
    c.execute('DELETE FROM orders WHERE order_id = \\\"{order_id}\\\"')
    c.execute('DELETE FROM queue_jobs WHERE order_id = \\\"{order_id}\\\"')
    conn.commit()
    print('Order deleted successfully')
else:
    print('Order not found')
conn.close()
" """
        out, err = run_remote(ssh, cmd)
        print(out)
        if err.strip():
            print("STDERR:", err)

    ssh.close()

if __name__ == "__main__":
    main()

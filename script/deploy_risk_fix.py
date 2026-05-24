"""部署风险监控修复"""
import io
import os
import sys
import time

import paramiko

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from remote import HOST, PROJECT_ROOT, SSH_KEY, VENV_PYTHON

LOCAL_ROOT = os.path.dirname(SCRIPT_DIR)

kf = io.StringIO(SSH_KEY)
key = paramiko.Ed25519Key.from_private_key(kf)
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username='root', pkey=key, timeout=15, allow_agent=False, look_for_keys=False)
sftp = ssh.open_sftp()

# 1. Upload modified backend files
backend_files = [
    'api/routers/health.py',
    'infrastructure/platform_health.py',
]
for f in backend_files:
    local = os.path.join(LOCAL_ROOT, f)
    remote = f"{PROJECT_ROOT}/{f}"
    sftp.put(local, remote)
    print(f"Uploaded: {f}")

# 2. Upload frontend static assets
remote_static = f'{PROJECT_ROOT}/static/'
local_static = os.path.join(LOCAL_ROOT, 'static')
uploaded = 0
for root, dirs, files in os.walk(local_static):
    for fname in files:
        local_path = os.path.join(root, fname)
        rel_path = os.path.relpath(local_path, local_static).replace(os.sep, '/')
        remote_path = remote_static + rel_path
        try:
            sftp.put(local_path, remote_path)
            uploaded += 1
        except Exception as e:
            print(f"  skip: {rel_path} ({e})")
print(f"Uploaded {uploaded} static files")

# 3. Clean old Admin hashed files
import glob

local_admin_names = set()
for p in glob.glob(os.path.join(local_static, 'assets', 'Admin-*')):
    local_admin_names.add(os.path.basename(p))

stdin, stdout, stderr = ssh.exec_command(
    f'ls -1 {remote_static}assets/ 2>/dev/null | grep -E "Admin-"'
)
existing = stdout.read().decode().strip().split('\n')
deleted = 0
for f in existing:
    f = f.strip()
    if f and f not in local_admin_names:
        ssh.exec_command(f'rm -f {remote_static}assets/{f}')
        deleted += 1
        print(f"  deleted old: {f}")
print(f"Cleaned {deleted} old Admin files")

sftp.close()

# 4. Restart server
print("Restarting server...")
stdin, stdout, stderr = ssh.exec_command(
    f'cd {PROJECT_ROOT} && pkill -f "python.*run.py" 2>/dev/null; sleep 2 && '
    f'nohup {VENV_PYTHON} run.py > /tmp/app.log 2>&1 &',
    timeout=15
)
stdout.read()
stderr.read()

time.sleep(6)

# 5. Verify
stdin, stdout, stderr = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/', timeout=10)
status = stdout.read().decode().strip()
print(f"Server status: {status}")

ssh.close()
print("Deploy complete!")

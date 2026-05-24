import io
import os

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

kf = io.StringIO(SSH_KEY)
key = paramiko.Ed25519Key.from_private_key(kf)
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, PORT, USER, pkey=key, timeout=15, allow_agent=False, look_for_keys=False)

# Check existing config first
_, o, _ = ssh.exec_command('cat /www/server/panel/vhost/nginx/*.conf 2>/dev/null | head -100', timeout=10)
print("=== Current Nginx config ===")
print(o.read().decode())

# Check what port Python runs on
_, o, _ = ssh.exec_command('ps aux | grep "python.*run.py" | grep -v grep', timeout=10)
print("=== Python process ===")
print(o.read().decode())

ssh.close()

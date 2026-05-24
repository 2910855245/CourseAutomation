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

SSH_KEY_STR = _load_ssh_key()

def deploy():
    key = paramiko.Ed25519Key.from_private_key(io.StringIO(SSH_KEY_STR))
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, PORT, USER, pkey=key, timeout=15)
    sftp = ssh.open_sftp()

    remote_static = '/www/wwwroot/anti_course/static/'
    local_static = 'static/'

    # Upload all files
    uploaded = 0
    for root, dirs, files in os.walk(local_static):
        for f in files:
            local_path = os.path.join(root, f)
            rel_path = os.path.relpath(local_path, local_static).replace(os.sep, '/')
            remote_path = remote_static + rel_path
            sftp.put(local_path, remote_path)
            uploaded += 1

    print(f'Uploaded {uploaded} files')

    # Clean old Admin hashed files (keep only files that exist locally)
    import glob as _glob
    local_admin_names = set()
    for p in _glob.glob(os.path.join(local_static, 'assets', 'Admin-*')):
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
            print(f'  deleted: {f}')
    print(f'Cleaned {deleted} old Admin files')

    # Verify nginx config is proxying correctly
    stdin, stdout, stderr = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/')
    status = stdout.read().decode().strip()
    print(f'Server HTTP status: {status}')

    ssh.close()
    print('Deploy complete!')

if __name__ == '__main__':
    deploy()

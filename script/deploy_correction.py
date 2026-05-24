"""Deploy auto-correction system to server."""
import io
import os
import sys

import paramiko

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from remote import HOST, PROJECT_ROOT, SSH_KEY, VENV_PYTHON

kf = io.StringIO(SSH_KEY)
key = paramiko.Ed25519Key.from_private_key(kf)
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username='root', pkey=key, timeout=15, allow_agent=False, look_for_keys=False)

LOCAL_ROOT = os.path.dirname(os.path.abspath(__file__))
sftp = ssh.open_sftp()

# Upload modified files
files = [
    'api/services/task_queue.py',
    'api/routers/queue.py',
]
for f in files:
    local = os.path.join(LOCAL_ROOT, f)
    remote = f"{PROJECT_ROOT}/{f}"
    sftp.put(local, remote)
    print(f"Uploaded: {f}")

sftp.close()

# Restart server via wrapper script
print("Restarting server...")
sftp = ssh.open_sftp()
with sftp.open('/tmp/restart_with_correction.sh', 'w') as f:
    f.write(f'''#!/bin/bash
cd {PROJECT_ROOT}
pkill -f "python.*run.py" 2>/dev/null
sleep 2
nohup {VENV_PYTHON} run.py > /tmp/app.log 2>&1 &
echo "PID: $!"
sleep 10
curl -s -o /dev/null -w "%{{http_code}}" http://localhost:8000/
echo ""
echo "=== Queue Stats ==="
curl -s http://localhost:8000/api/queue/stats 2>/dev/null | head -500
echo ""
echo "=== Error Stats ==="
curl -s http://localhost:8000/api/queue/error-stats 2>/dev/null | head -500
echo ""
tail -10 /tmp/app.log
''')
sftp.close()

stdin, stdout, stderr = ssh.exec_command('chmod +x /tmp/restart_with_correction.sh && bash /tmp/restart_with_correction.sh', timeout=60)
output = stdout.read().decode()
print(output)

err = stderr.read().decode()
if err and 'InsecureKey' not in err:
    print('STDERR:', err[:500])

ssh.close()
print("Done!")

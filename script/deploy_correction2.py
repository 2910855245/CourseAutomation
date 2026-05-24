"""Deploy updated correction patterns and run."""
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

# Upload updated task_queue.py
sftp.put(os.path.join(LOCAL_ROOT, 'api/services/task_queue.py'), f"{PROJECT_ROOT}/api/services/task_queue.py")
print("Uploaded: api/services/task_queue.py")
sftp.close()

# Restart server and run correction
sftp = ssh.open_sftp()
with sftp.open('/tmp/restart_and_correct.sh', 'w') as f:
    f.write(f'''#!/bin/bash
cd {PROJECT_ROOT}
pkill -f "python.*run.py" 2>/dev/null
sleep 2
nohup {VENV_PYTHON} run.py > /tmp/app.log 2>&1 &
echo "Server PID: $!"
sleep 8
echo "=== Server Status ==="
curl -s -o /dev/null -w "%{{http_code}}" http://localhost:8000/
echo ""
tail -5 /tmp/app.log
''')
sftp.close()

stdin, stdout, stderr = ssh.exec_command('chmod +x /tmp/restart_and_correct.sh && bash /tmp/restart_and_correct.sh', timeout=60)
print(stdout.read().decode())

# Now run correction via a Python script
sftp = ssh.open_sftp()
with sftp.open('/tmp/do_correction.py', 'w') as f:
    f.write(f'''
import sys, os
sys.path.insert(0, "{PROJECT_ROOT}")
from api.services.task_queue import school_queue, chaoxing_queue, get_combined_stats

stats = get_combined_stats()
print("=== Before ===")
print("Pending: %d, Failed: %d" % (stats["pending"], stats["failed"]))

school_queue.trigger_correction()
chaoxing_queue.trigger_correction()

stats = get_combined_stats()
print("\\n=== After ===")
print("Pending: %d, Failed: %d" % (stats["pending"], stats["failed"]))

error_stats = {{"school": school_queue.get_error_stats(), "chaoxing": chaoxing_queue.get_error_stats()}}
print("\\n=== Remaining Failed ===")
for q_name, q_stats in error_stats.items():
    for cat_name in ("retryable", "fatal", "unknown"):
        for entry in q_stats.get(cat_name, []):
            print("  %s [%s] | cat=%s | err=%s" % (entry["job_id"], q_name, cat_name, repr(entry["error"][:80])))
''')
sftp.close()

stdin, stdout, stderr = ssh.exec_command(VENV_PYTHON + ' /tmp/do_correction.py', timeout=30)
print(stdout.read().decode())
err = stderr.read().decode()
if err and 'InsecureKey' not in err:
    print('STDERR:', err[:500])

ssh.close()
print("Done!")

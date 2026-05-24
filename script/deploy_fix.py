"""Deploy fixes to server."""
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
    'study_worker.py',
    'api/services/task_queue.py',
]
for f in files:
    local = os.path.join(LOCAL_ROOT, f)
    remote = f"{PROJECT_ROOT}/{f}"
    sftp.put(local, remote)
    print(f"Uploaded: {f}")

sftp.close()

# Restart server
print("Restarting server...")
stdin, stdout, stderr = ssh.exec_command(
    f'cd {PROJECT_ROOT} && pkill -f "python.*run.py" 2>/dev/null; sleep 2 && '
    f'nohup {VENV_PYTHON} run.py > /tmp/app.log 2>&1 &',
    timeout=15
)
stdout.read()
stderr.read()

import time

time.sleep(6)

# Verify
stdin, stdout, stderr = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/', timeout=10)
status = stdout.read().decode().strip()
print(f"Server status: {status}")

# Clear old duplicate tasks
print("Cleaning up old task dirs...")
stdin, stdout, stderr = ssh.exec_command(
    'rm -rf /tmp/task_0g1et7ij /tmp/task_1ze_m2tu /tmp/task_5s71hz6e /tmp/task_8kt7mapf '
    '/tmp/task_8uaw6oa9 /tmp/task__fz2x999 /tmp/task_d7h__1m2 /tmp/task_de9w8yca '
    '/tmp/task_direct_6w2tyrpx /tmp/task_direct_sd5qzjcv /tmp/task_f7uzh7ai /tmp/task_ho_wicpg '
    '/tmp/task_ix07cyc_ /tmp/task_0g1et7ij /tmp/task_p4cjkduq /tmp/task_w0owvhcw '
    '/tmp/task_9vf98eam /tmp/task_nhmpm4g3 /tmp/task_dzx7peuc /tmp/task_99c5dtxf '
    '/tmp/task_yk0r5s8u /tmp/task_xhqs253t /tmp/task_r_6pke9w /tmp/task_1cdzcp9o '
    '/tmp/task_10qs11tn /tmp/task_rxi56omq /tmp/task_w62kz9ax 2>/dev/null',
    timeout=10
)
stdout.read()

# Reset completed jobs to failed so they can be re-processed
print("Resetting false-completed jobs...")
sftp = ssh.open_sftp()
with sftp.open('/tmp/reset_jobs.py', 'w') as f:
    f.write('''
import pymysql
conn = pymysql.connect(host="localhost", user="myshuake", password="woainima123", database="myshuake", charset="utf8mb4")
cur = conn.cursor()

# Reset completed jobs that have video_pct=0 (false completions)
# These are jobs where the worker said success but platform progress was 0
cur.execute("UPDATE queue_jobs SET status='failed', error_message='平台进度为0%，需要重新刷课', progress=0 WHERE status='completed' AND progress < 95")
reset = cur.rowcount
conn.commit()
print("Reset %d false-completed jobs" % reset)

# Show current state
cur.execute("SELECT status, COUNT(*) FROM queue_jobs GROUP BY status")
for row in cur.fetchall():
    print("  %s: %d" % (row[0], row[1]))

conn.close()
''')
sftp.close()

stdin, stdout, stderr = ssh.exec_command(f'cd {PROJECT_ROOT} && {VENV_PYTHON} /tmp/reset_jobs.py', timeout=20)
print(stdout.read().decode())
err = stderr.read().decode()
if err and 'InsecureKey' not in err:
    print('ERR:', err[:200])

ssh.close()
print("Done!")

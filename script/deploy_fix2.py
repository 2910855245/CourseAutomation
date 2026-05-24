"""Fix: reset false-completed jobs and verify server."""
import io
import os
import sys
import time

import paramiko

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from remote import HOST, PROJECT_ROOT, SSH_KEY, VENV_PYTHON

kf = io.StringIO(SSH_KEY)
key = paramiko.Ed25519Key.from_private_key(kf)
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username='root', pkey=key, timeout=15, allow_agent=False, look_for_keys=False)

# Wait for server
for i in range(10):
    stdin, stdout, stderr = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/', timeout=10)
    status = stdout.read().decode().strip()
    if status == '200':
        print(f"Server is up (attempt {i+1})")
        break
    time.sleep(3)
else:
    print("Server may not be running, continuing anyway")

# Reset all completed jobs to pending for re-processing
# (since we confirmed they all have 0% platform progress)
sftp = ssh.open_sftp()
with sftp.open('/tmp/reset_all.py', 'w') as f:
    f.write('''
import pymysql
conn = pymysql.connect(host="localhost", user="myshuake", password="woainima123", database="myshuake", charset="utf8mb4")
cur = conn.cursor()

# Get all completed jobs
cur.execute("SELECT job_id, username, website_id, order_id FROM queue_jobs WHERE status='completed'")
jobs = cur.fetchall()
print("Completed jobs to reset: %d" % len(jobs))

# Reset to pending
cur.execute("UPDATE queue_jobs SET status='pending', progress=0, error_message='', started_at=NULL, finished_at=NULL WHERE status='completed'")
reset = cur.rowcount
conn.commit()
print("Reset %d jobs to pending" % reset)

# Show state
cur.execute("SELECT status, COUNT(*) FROM queue_jobs GROUP BY status")
for row in cur.fetchall():
    print("  %s: %d" % (row[0], row[1]))

conn.close()
''')
sftp.close()

stdin, stdout, stderr = ssh.exec_command(f'cd {PROJECT_ROOT} && {VENV_PYTHON} /tmp/reset_all.py', timeout=20)
print(stdout.read().decode())
err = stderr.read().decode()
if err and 'InsecureKey' not in err:
    print('ERR:', err[:200])

ssh.close()
print("Done! Jobs reset to pending - queue will re-process them with fixed verification.")

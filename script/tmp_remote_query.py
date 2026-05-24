import sys, io, os, json
sys.stdout.reconfigure(encoding='utf-8')
import paramiko

with open(os.path.join(os.path.dirname(__file__), 'ssh_key')) as f:
    ssh_key = f.read()

kf = io.StringIO(ssh_key)
key = paramiko.Ed25519Key.from_private_key(kf)
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('38.76.190.251', 22, 'root', pkey=key, timeout=15, allow_agent=False, look_for_keys=False)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', errors='replace'), stderr.read().decode('utf-8', errors='replace')

# Write query script to remote
remote_script = r"""
import sqlite3, json, sys
sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect('data/orders.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()

# Recent exam/full orders
rows = c.execute("SELECT order_id, username, task_type, course_ids, video_count, exam_count, status, created_at FROM orders WHERE task_type IN ('exam', 'full') ORDER BY created_at DESC LIMIT 10").fetchall()
print("=== Recent exam/full orders ===")
for r in rows:
    print(json.dumps(dict(r), ensure_ascii=False))

conn.close()
"""

sftp = ssh.open_sftp()
with sftp.open('/tmp/_query_exam.py', 'w') as f:
    f.write(remote_script)
sftp.close()

out, err = run('cd /www/wwwroot/anti_course && python3 /tmp/_query_exam.py', timeout=30)
print(out)
if err.strip():
    print('STDERR:', err)

ssh.close()

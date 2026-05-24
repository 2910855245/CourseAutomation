import pymysql

conn = pymysql.connect(host='localhost', user='myshuake', password='woainima123', database='myshuake', charset='utf8mb4')
cur = conn.cursor()

# Get order password
cur.execute('SELECT password FROM orders WHERE order_id=%s', ('ORD-9FC8647F',))
pw = cur.fetchone()
password = pw[0] if pw else ''

# Reset job: pending, clear error, reset progress, set job_type to exam, restore password
cur.execute(
    "UPDATE queue_jobs SET status='pending', error_message='', progress=0, retry_count=0, "
    "started_at=NULL, finished_at=NULL, current_step_name='', job_type='exam', password=%s "
    "WHERE job_id=%s",
    (password, 'JOB-3DB35210C7')
)
print(f'Rows updated: {cur.rowcount}')
conn.commit()

# Verify
cur.execute('SELECT job_id, status, job_type, progress, retry_count, password FROM queue_jobs WHERE job_id=%s', ('JOB-3DB35210C7',))
row = cur.fetchone()
if row:
    print(f'job_id={row[0]}, status={row[1]}, job_type={row[2]}, progress={row[3]}, retry={row[4]}, has_pw={bool(row[5])}')
conn.close()

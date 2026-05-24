import pymysql

conn = pymysql.connect(host="localhost", user="myshuake", password="woainima123", database="myshuake", charset="utf8mb4")
cur = conn.cursor()
cur.execute("SELECT error_message, current_step_name FROM queue_jobs WHERE job_id=%s", ("JOB-3DB35210C7",))
row = cur.fetchone()
if row:
    with open("/tmp/error_out.txt", "w", encoding="utf-8") as f:
        f.write(str(row[0]) + "\n" + str(row[1]) + "\n")
conn.close()

import sqlite3, json, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("/www/wwwroot/anti_course/data/orders.db")
c = conn.cursor()

# Check for passwords in queue_jobs
c.execute("SELECT job_id, username, website_id, password FROM queue_jobs WHERE password != '' LIMIT 10")
rows = c.fetchall()
print(f"Jobs with passwords: {len(rows)}")
for row in rows:
    print(f"  {row[0]} | user={row[1]} | site={row[2]} | pw={row[3][:20] if row[3] else '(empty)'}")

# Check orders for passwords
c.execute("SELECT order_id, username, website_id, password FROM orders WHERE password != '' LIMIT 10")
rows2 = c.fetchall()
print(f"\nOrders with passwords: {len(rows2)}")
for row in rows2:
    print(f"  {row[0]} | user={row[1]} | site={row[2]} | pw={row[3][:20] if row[3] else '(empty)'}")

conn.close()

import sqlite3, json, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("/www/wwwroot/anti_course/data/orders.db")
c = conn.cursor()
c.execute("SELECT DISTINCT username, password FROM orders WHERE website_id=2 AND password != ''")
result = dict(c.fetchall())
conn.close()

with open('/tmp/passwords.json', 'w') as f:
    json.dump(result, f, ensure_ascii=False)

print(json.dumps(result, ensure_ascii=False))

import sqlite3, json, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('/www/wwwroot/anti_course/data/orders.db')
c = conn.cursor()

# Get all accounts grouped by website_id with their course_ids
c.execute("SELECT username, password, website_id, course_ids FROM orders WHERE password != ''")
rows = c.fetchall()

# website_id -> {username: {password, course_ids}}
platforms = {}
for username, password, wid, course_ids_str in rows:
    wid = str(wid)
    if wid not in platforms:
        platforms[wid] = {}
    if username not in platforms[wid]:
        try:
            cids = json.loads(course_ids_str) if course_ids_str and course_ids_str.startswith('[') else [course_ids_str] if course_ids_str else []
        except:
            cids = []
        platforms[wid][username] = {'password': password, 'course_ids': cids}

# Print summary
for wid, accounts in platforms.items():
    print(f"\nWebsite {wid}: {len(accounts)} accounts")
    all_courses = set()
    for uname, info in accounts.items():
        for cid in info['course_ids']:
            if cid:
                all_courses.add(cid)
    print(f"  Courses: {sorted(all_courses)}")

# Save
with open('/tmp/all_accounts.json', 'w') as f:
    json.dump(platforms, f, ensure_ascii=False)
print(f"\nSaved to /tmp/all_accounts.json")
conn.close()

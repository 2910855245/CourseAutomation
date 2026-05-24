import sqlite3, json, sys, os
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('/www/wwwroot/anti_course/data/orders.db')
c = conn.cursor()

# Get all orders with course info
c.execute("SELECT DISTINCT username, website_id, course_ids FROM orders WHERE status IN ('completed','accepted')")
rows = c.fetchall()

platform_courses = {}
for username, wid, course_ids_str in rows:
    if not course_ids_str:
        continue
    try:
        cids = json.loads(course_ids_str) if course_ids_str.startswith('[') else [course_ids_str]
    except:
        cids = [course_ids_str]
    wid = str(wid)
    if wid not in platform_courses:
        platform_courses[wid] = set()
    for cid in cids:
        if cid:
            platform_courses[wid].add(cid)

# Get courses from cached data
base = '/www/wwwroot/anti_course/data/accounts'
cached_courses = {}
for username in os.listdir(base):
    courses_dir = os.path.join(base, username, 'courses')
    if not os.path.isdir(courses_dir):
        continue
    for platform in os.listdir(courses_dir):
        pdir = os.path.join(courses_dir, platform)
        if not os.path.isdir(pdir):
            continue
        for fname in os.listdir(pdir):
            if fname.endswith('.json'):
                cid = fname[:-5]
                if platform not in cached_courses:
                    cached_courses[platform] = set()
                cached_courses[platform].add(cid)

def safe_str(s):
    return s.encode('utf-8', errors='replace').decode('utf-8')

result = {
    'platform_courses': {safe_str(k): sorted(list(v)) for k, v in platform_courses.items()},
    'cached_courses': {safe_str(k): sorted(list(v)) for k, v in cached_courses.items()},
}
with open('/tmp/courses_info.json', 'w') as f:
    json.dump(result, f, ensure_ascii=False)

print("Orders courses:")
for wid, cids in platform_courses.items():
    print(f"  Website {wid}: {len(cids)} courses - {sorted(list(cids))[:10]}")

print("\nCached courses:")
for plat, cids in cached_courses.items():
    print(f"  {plat}: {len(cids)} courses - {sorted(list(cids))[:5]}")

# Get all unique usernames
c.execute("SELECT DISTINCT username FROM orders WHERE password != ''")
all_users = [r[0] for r in c.fetchall()]
print(f"\nTotal accounts with passwords: {len(all_users)}")
conn.close()

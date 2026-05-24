import json, sys, os
sys.stdout.reconfigure(encoding='utf-8')

from scrapling import Fetcher

# Use scrapling Fetcher to scrape study record page
BASE_URL = "https://cdcas.taiskeji.com"
PLATFORM_NAME = "劳动课程测评考试平台"

# Read cookie for one account
username = "251060150506"
cookie_path = f'/www/wwwroot/anti_course/data/accounts/{username}/cookies/{PLATFORM_NAME}.json'
with open(cookie_path, 'r', encoding='utf-8') as f:
    cookie_data = json.load(f)

# Build cookie dict
cookies = {}
for c in cookie_data:
    if 'name' in c and 'value' in c:
        cookies[c['name']] = c['value']

print(f"Account: {username}")
print(f"Cookies: {cookies}")

# Fetch study record page
fetcher = Fetcher(auto_match=False)
url = f"{BASE_URL}/user/study_record?courseId=1011331"
print(f"\nFetching: {url}")

page = fetcher.get(url, cookies=cookies, stealthy_headers=True)
print(f"Status: {page.status}")
print(f"URL: {page.url}")

# Check content
text = page.text[:500] if hasattr(page, 'text') else str(page)[:500]
print(f"\nContent preview:")
print(text)

# Try to find tables
tables = page.css('table')
print(f"\nTables found: {len(tables)}")

# Try to find study record data
rows = page.css('tr')
print(f"Rows found: {len(rows)}")

for i, row in enumerate(rows[:5]):
    cells = row.css('td, th')
    cell_text = [c.text.strip() for c in cells if c.text]
    print(f"  Row {i}: {cell_text}")

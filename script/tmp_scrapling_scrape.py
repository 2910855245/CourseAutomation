import json, sys
sys.stdout.reconfigure(encoding='utf-8')

from scrapling import Fetcher

BASE_URL = "https://cdcas.taiskeji.com"

# Load cookies
with open('script/tmp_all_cookies.json', 'r', encoding='utf-8') as f:
    all_cookies = json.load(f)

print(f"Loaded {len(all_cookies)} accounts")

fetcher = Fetcher(auto_match=False)

for username, cookie_list in all_cookies.items():
    print(f"\n{'='*60}")
    print(f"Account: {username}")
    print(f"{'='*60}")

    # Build cookie dict
    cookies = {}
    for c in cookie_list:
        if 'name' in c and 'value' in c:
            cookies[c['name']] = c['value']

    # Fetch video study records via API
    try:
        page = fetcher.get(
            f"{BASE_URL}/user/study_record/video",
            params={"courseId": "1011331", "page": "1"},
            cookies=cookies,
            stealthy_headers=True,
            follow_redirects=True,
        )
        print(f"Status: {page.status}")

        # Try to parse JSON
        try:
            data = json.loads(page.text)
            videos = data.get("list", [])
            print(f"Videos: {len(videos)}")

            if videos:
                # Show completion times
                completed = []
                for v in videos:
                    ft = v.get("finalTime", "")
                    name = v.get("name", "")
                    progress = v.get("progress", "0")
                    begin = v.get("beginTime", "")
                    view_count = v.get("viewCount", "0")
                    if ft and ft != "-":
                        completed.append({
                            "name": name,
                            "final_time": ft,
                            "begin_time": begin,
                            "progress": progress,
                            "view_count": view_count,
                        })

                completed.sort(key=lambda x: x["final_time"])
                print(f"Completed: {len(completed)}")

                from datetime import datetime
                print(f"\nCompletion timeline:")
                for i, v in enumerate(completed):
                    print(f"  [{i+1:2d}] {v['final_time']:20s} | {v['name'][:35]:35s} | progress:{v['progress']} | views:{v['view_count']}")

                # Parallel detection
                print(f"\nParallel brushing detection (<60s gap):")
                parallel_count = 0
                for i in range(1, len(completed)):
                    try:
                        t1 = completed[i-1]["final_time"]
                        t2 = completed[i]["final_time"]
                        dt1 = datetime.strptime(f"2026-{t1}", "%Y-%m-%d %H:%M:%S")
                        dt2 = datetime.strptime(f"2026-{t2}", "%Y-%m-%d %H:%M:%S")
                        diff = abs((dt2 - dt1).total_seconds())
                        if diff < 60:
                            parallel_count += 1
                            print(f"  !!! {completed[i-1]['name'][:25]:25s} -> {completed[i]['name'][:25]:25s} | gap: {diff:.0f}s")
                    except:
                        pass
                if parallel_count == 0:
                    print(f"  No parallel brushing detected")
                else:
                    print(f"  DETECTED {parallel_count} parallel brushing instances!")
            else:
                # Check if error response
                print(f"Response: {page.text[:300]}")
        except json.JSONDecodeError:
            print(f"Not JSON. Content: {page.text[:300]}")
    except Exception as e:
        print(f"Error: {e}")

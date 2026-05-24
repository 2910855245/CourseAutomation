import json, sys, os, httpx
from datetime import datetime
sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "https://cdcas.taiskeji.com"
PLATFORM_NAME = "劳动课程测评考试平台"

def get_all_cookies():
    base_dir = '/www/wwwroot/anti_course/data/accounts'
    cookies = {}
    if not os.path.isdir(base_dir):
        print(f"  目录不存在: {base_dir}")
        return cookies
    for username in os.listdir(base_dir):
        cookie_path = os.path.join(base_dir, username, 'cookies', f'{PLATFORM_NAME}.json')
        if not os.path.exists(cookie_path):
            continue
        try:
            with open(cookie_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                cookies[username] = data
                print(f"  读取cookie: {username} ({len(data)} cookies)")
        except Exception as e:
            print(f"  读取失败 {username}: {e}")
    return cookies

def fetch_all_videos(session, course_id):
    headers = {"X-Requested-With": "XMLHttpRequest"}
    all_items = []
    page = 1
    while True:
        resp = session.get(f"{BASE_URL}/user/study_record/video",
                          params={"courseId": course_id, "page": page},
                          headers=headers, timeout=15)
        if resp.status_code != 200:
            break
        try:
            data = resp.json()
        except:
            break
        items = data.get("list", [])
        if not items:
            break
        all_items.extend(items)
        page_info = data.get("pageInfo", {})
        if page >= page_info.get("pageCount", 1):
            break
        page += 1
    return all_items

def analyze_account(username, cookie_data, course_id):
    session = httpx.Client(timeout=httpx.Timeout(30.0), verify=False)
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'X-Requested-With': 'XMLHttpRequest',
    })
    # Set cookies with proper domain
    for c in cookie_data:
        if 'name' in c and 'value' in c:
            session.cookies.set(c['name'], c['value'], domain=c.get('domain', ''))

    # Check login
    try:
        resp = session.get(f"{BASE_URL}/user/index", timeout=10)
        resp.encoding = 'utf-8'
        has_logout = '退出登录' in resp.text
        has_personal = '个人中心' in resp.text
        print(f"  登录检查: 退出登录={has_logout}, 个人中心={has_personal}, url={resp.url}")
        if not has_logout:
            # Save debug HTML
            with open(f'/tmp/debug_analyze_{username}.html', 'w', encoding='utf-8') as f:
                f.write(resp.text[:3000])
            return None
    except Exception as e:
        print(f"  请求失败: {e}")
        return None

    videos = fetch_all_videos(session, course_id)
    if not videos:
        return None

    # Extract completion times
    completed = []
    for v in videos:
        final_time = v.get("finalTime", "")
        name = v.get("name", "")
        progress = v.get("progress", "0")
        begin_time = v.get("beginTime", "")
        view_count = v.get("viewCount", "0")

        if final_time and final_time != "-":
            completed.append({
                "name": name,
                "final_time": final_time,
                "begin_time": begin_time,
                "progress": progress,
                "view_count": view_count,
            })

    # Sort by completion time
    completed.sort(key=lambda x: x["final_time"])

    return {
        "total": len(videos),
        "completed": len(completed),
        "videos": completed,
    }

def main():
    print("=" * 70)
    print("并行刷课检测 - 分析完成时间")
    print("=" * 70)

    course_id = "1011331"
    cookies = get_all_cookies()
    print(f"\n获取到 {len(cookies)} 个账号")

    all_results = {}
    for username, cookie_data in cookies.items():
        print(f"\n{'='*70}")
        print(f"账号: {username} (cookie: {cookie_data[0].get('name')}={cookie_data[0].get('value')[:20]}...)")
        print(f"{'='*70}")

        result = analyze_account(username, cookie_data, course_id)
        if not result:
            print("  无法获取数据")
            continue

        all_results[username] = result
        videos = result["videos"]
        print(f"  视频总数: {result['total']}, 已完成: {result['completed']}")

        if not videos:
            continue

        # Print completion timeline
        print(f"\n  完成时间线:")
        for i, v in enumerate(videos):
            print(f"  [{i+1:2d}] {v['final_time']} | {v['name'][:35]:35s} | 进度:{v['progress']} | 播放:{v['view_count']}次")

        # Detect parallel brushing: videos completed within 60 seconds
        print(f"\n  并行刷课检测 (间隔 < 60秒):")
        parallel_count = 0
        for i in range(1, len(videos)):
            try:
                t1_str = videos[i-1]["final_time"]
                t2_str = videos[i]["final_time"]
                # Format: "05-18 03:28:08"
                dt1 = datetime.strptime(f"2026-{t1_str}", "%Y-%m-%d %H:%M:%S")
                dt2 = datetime.strptime(f"2026-{t2_str}", "%Y-%m-%d %H:%M:%S")
                diff = abs((dt2 - dt1).total_seconds())
                if diff < 60:
                    parallel_count += 1
                    print(f"    !!! {videos[i-1]['name'][:25]:25s} -> {videos[i]['name'][:25]:25s} | 间隔: {diff:.0f}秒")
            except:
                pass

        if parallel_count == 0:
            print(f"    未检测到并行刷课")
        else:
            print(f"    检测到 {parallel_count} 处并行刷课嫌疑!")

        # Check if videos were completed in non-sequential order
        print(f"\n  顺序检测:")
        out_of_order = 0
        for i in range(1, len(videos)):
            try:
                t1_str = videos[i-1]["final_time"]
                t2_str = videos[i]["final_time"]
                dt1 = datetime.strptime(f"2026-{t1_str}", "%Y-%m-%d %H:%M:%S")
                dt2 = datetime.strptime(f"2026-{t2_str}", "%Y-%m-%d %H:%M:%S")
                if dt2 < dt1:
                    out_of_order += 1
            except:
                pass
        print(f"    时间倒序次数: {out_of_order}")

    # Save results
    with open('/tmp/parallel_analysis.json', 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存到 /tmp/parallel_analysis.json")

if __name__ == "__main__":
    main()

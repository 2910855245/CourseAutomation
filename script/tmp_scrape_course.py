import sqlite3
import json
import sys
import os
import httpx
import time

sys.stdout.reconfigure(encoding='utf-8')
httpx.packages.urllib3.disable_warnings()

# 平台配置
BASE_URL = "https://cdcas.taiskeji.com"
PLATFORM_NAME = "劳动课程测评考试平台"

def get_all_cookies():
    """获取所有有劳动课程测评考试平台cookie的账号"""
    base_dir = '/www/wwwroot/anti_course/data/accounts'
    cookies = {}

    if not os.path.isdir(base_dir):
        return cookies

    for username in os.listdir(base_dir):
        cookie_path = os.path.join(base_dir, username, 'cookies', f'{PLATFORM_NAME}.json')
        if not os.path.exists(cookie_path):
            continue
        try:
            with open(cookie_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                cookie_str = '; '.join(f"{c['name']}={c['value']}" for c in data if 'name' in c and 'value' in c)
            elif isinstance(data, dict):
                cookie_str = data.get('cookie', '')
            else:
                cookie_str = str(data)
            if cookie_str:
                cookies[username] = cookie_str
        except Exception as e:
            print(f"  Cookie读取失败 {username}: {e}")

    return cookies

def fetch_study_records(session, course_id):
    """通过API获取课程学习记录"""
    headers = {"X-Requested-With": "XMLHttpRequest"}
    result = {"videos": [], "exams": [], "works": []}

    # 获取视频记录
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
        items = data if isinstance(data, list) else data.get("data", data.get("list", []))
        if not items:
            break
        result["videos"].extend(items)
        if len(items) < 10:
            break
        page += 1

    # 获取考试记录
    page = 1
    while True:
        resp = session.get(f"{BASE_URL}/user/study_record/exam",
                          params={"courseId": course_id, "page": page},
                          headers=headers, timeout=15)
        if resp.status_code != 200:
            break
        try:
            data = resp.json()
        except:
            break
        items = data if isinstance(data, list) else data.get("data", data.get("list", []))
        if not items:
            break
        result["exams"].extend(items)
        if len(items) < 10:
            break
        page += 1

    # 获取作业记录
    page = 1
    while True:
        resp = session.get(f"{BASE_URL}/user/study_record/work",
                          params={"courseId": course_id, "page": page},
                          headers=headers, timeout=15)
        if resp.status_code != 200:
            break
        try:
            data = resp.json()
        except:
            break
        items = data if isinstance(data, list) else data.get("data", data.get("list", []))
        if not items:
            break
        result["works"].extend(items)
        if len(items) < 10:
            break
        page += 1

    return result

def analyze_parallel_pattern(records):
    """分析并行刷课特征"""
    videos = records.get("videos", [])
    if not videos:
        return

    print(f"  视频总数: {len(videos)}")

    # 收集所有有完成时间的视频
    completed_videos = []
    for v in videos:
        # 检查各种可能的时间字段
        finish_time = v.get("finishTime") or v.get("completeTime") or v.get("endTime") or v.get("studyTime") or ""
        start_time = v.get("startTime") or v.get("beginTime") or ""
        progress = v.get("progress") or v.get("studyProgress") or v.get("percent") or 0
        duration = v.get("duration") or v.get("videoDuration") or 0
        viewed = v.get("viewedDuration") or v.get("studyTime") or v.get("watchTime") or 0
        name = v.get("name") or v.get("nodeName") or v.get("title") or ""

        if finish_time:
            completed_videos.append({
                "name": name,
                "finish_time": finish_time,
                "start_time": start_time,
                "progress": progress,
                "duration": duration,
                "viewed": viewed,
            })

    if not completed_videos:
        print("  无完成时间数据")
        # 打印第一条原始数据看看字段
        if videos:
            print(f"  原始数据示例: {json.dumps(videos[0], ensure_ascii=False)[:500]}")
        return

    print(f"  有完成时间的视频: {len(completed_videos)}")

    # 按完成时间排序
    completed_videos.sort(key=lambda x: x["finish_time"])

    # 检查并行特征：多个视频在极短时间内完成
    print(f"\n  === 完成时间序列 ===")
    for i, v in enumerate(completed_videos[:20]):
        print(f"  [{i+1}] {v['name'][:30]:30s} | 完成: {v['finish_time']} | 进度: {v['progress']}")

    # 检测时间间隔
    if len(completed_videos) >= 2:
        print(f"\n  === 时间间隔分析 ===")
        from datetime import datetime
        for i in range(1, min(len(completed_videos), 20)):
            try:
                t1 = str(completed_videos[i-1]["finish_time"])
                t2 = str(completed_videos[i]["finish_time"])
                # Try parsing various formats
                for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M:%S"]:
                    try:
                        dt1 = datetime.strptime(t1[:19], fmt)
                        dt2 = datetime.strptime(t2[:19], fmt)
                        diff = (dt2 - dt1).total_seconds()
                        flag = " <<< 并行嫌疑!" if diff < 60 else ""
                        print(f"  {completed_videos[i-1]['name'][:20]:20s} -> {completed_videos[i]['name'][:20]:20s} | 间隔: {diff:.0f}秒{flag}")
                        break
                    except:
                        continue
            except:
                pass

def main():
    print("=" * 60)
    print("通过API爬取课程学习记录")
    print("=" * 60)

    course_id = "1011331"
    print(f"\n课程ID: {course_id}")
    print(f"平台: {BASE_URL}")

    # 获取 cookie
    cookies = get_all_cookies()
    print(f"\n获取到 {len(cookies)} 个账号的 cookie")

    if not cookies:
        print("未获取到有效的 cookie!")
        return

    # 爬取每个账号的数据
    all_records = {}

    for username, cookie_str in cookies.items():
        print(f"\n{'='*60}")
        print(f"账号: {username}")
        print(f"{'='*60}")

        session = httpx.Client(timeout=httpx.Timeout(30.0), verify=False)
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        })

        # 设置 cookie
        for item in cookie_str.split(';'):
            if '=' in item:
                k, v = item.strip().split('=', 1)
                session.cookies.set(k, v)

        # 先检查登录状态
        try:
            resp = session.get(f"{BASE_URL}/user/index", timeout=10)
            resp.encoding = 'utf-8'
            if '退出登录' not in resp.text:
                print(f"  Cookie 已过期，跳过")
                continue
            print(f"  登录状态: 有效")
        except Exception as e:
            print(f"  请求失败: {e}")
            continue

        # 获取学习记录
        records = fetch_study_records(session, course_id)
        all_records[username] = records

        video_count = len(records.get("videos", []))
        exam_count = len(records.get("exams", []))
        work_count = len(records.get("works", []))
        print(f"  视频: {video_count}, 考试: {exam_count}, 作业: {work_count}")

        # 分析并行特征
        analyze_parallel_pattern(records)

        time.sleep(0.5)

    # 保存数据
    output_file = '/tmp/course_api_records.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)
    print(f"\n数据已保存到: {output_file}")

if __name__ == "__main__":
    main()

import json, sys, os
sys.stdout.reconfigure(encoding='utf-8')

base = '/www/wwwroot/anti_course/data/accounts'
course_id = '1011331'

# Find all cached course files for this course
results = {}
for username in os.listdir(base):
    courses_dir = os.path.join(base, username, 'courses')
    if not os.path.isdir(courses_dir):
        continue
    for platform in os.listdir(courses_dir):
        course_file = os.path.join(courses_dir, platform, f'{course_id}.json')
        if not os.path.exists(course_file):
            continue
        try:
            with open(course_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            videos = data.get('videos', [])
            key = f"{username}/{platform}"
            results[key] = {
                'username': username,
                'platform': platform,
                'course_name': data.get('course_name', ''),
                'video_count': len(videos),
                'videos': videos,
            }
            print(f"Found: {key} ({len(videos)} videos)")
        except Exception as e:
            print(f"Error reading {username}/{platform}: {e}")

print(f"\nTotal: {len(results)} course files found")

# Analyze parallel brushing from cached data
for key, info in results.items():
    videos = info['videos']
    if not videos:
        continue

    print(f"\n{'='*70}")
    print(f"账号: {info['username']} | 平台: {info['platform']}")
    print(f"课程: {info['course_name']} | 视频数: {info['video_count']}")
    print(f"{'='*70}")

    # Collect completed videos with timestamps
    completed = []
    for v in videos:
        # Check various time fields
        finish = v.get('finishTime') or v.get('finalTime') or v.get('completeTime') or ''
        begin = v.get('beginTime') or v.get('startTime') or ''
        progress = v.get('progress') or v.get('studyProgress') or 0
        name = v.get('name') or v.get('nodeName') or ''
        status = v.get('status') or v.get('state') or ''
        viewed = v.get('viewed_duration') or v.get('viewedDuration') or ''
        duration = v.get('duration') or v.get('videoDuration') or ''

        if finish and finish != '-':
            completed.append({
                'name': name,
                'finish': finish,
                'begin': begin,
                'progress': progress,
                'status': status,
                'viewed': viewed,
                'duration': duration,
            })

    if not completed:
        print("  无完成时间数据")
        # Show raw data for first video
        if videos:
            print(f"  原始字段: {list(videos[0].keys())}")
            print(f"  示例数据: {json.dumps(videos[0], ensure_ascii=False)[:300]}")
        continue

    # Sort by finish time
    completed.sort(key=lambda x: str(x['finish']))

    print(f"\n  完成时间序列:")
    for i, v in enumerate(completed):
        print(f"  [{i+1:2d}] {v['finish']:20s} | {v['name'][:30]:30s} | 进度:{v['progress']} | 状态:{v['status']}")

    # Check parallel brushing (finish within 60 seconds)
    from datetime import datetime
    print(f"\n  并行刷课检测 (间隔 < 60秒):")
    parallel_count = 0
    for i in range(1, len(completed)):
        try:
            t1 = str(completed[i-1]['finish'])
            t2 = str(completed[i]['finish'])
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%m-%d %H:%M:%S"]:
                try:
                    if fmt == "%m-%d %H:%M:%S":
                        dt1 = datetime.strptime(f"2026-{t1}", "%Y-%m-%d %H:%M:%S")
                        dt2 = datetime.strptime(f"2026-{t2}", "%Y-%m-%d %H:%M:%S")
                    else:
                        dt1 = datetime.strptime(t1[:19], fmt)
                        dt2 = datetime.strptime(t2[:19], fmt)
                    diff = abs((dt2 - dt1).total_seconds())
                    if diff < 60:
                        parallel_count += 1
                        print(f"    !!! {completed[i-1]['name'][:25]:25s} -> {completed[i]['name'][:25]:25s} | 间隔: {diff:.0f}秒")
                    break
                except:
                    continue
        except:
            pass

    if parallel_count == 0:
        print(f"    未检测到并行刷课")
    else:
        print(f"    检测到 {parallel_count} 处并行刷课嫌疑!")

# Save full data
with open('/tmp/cached_course_analysis.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2, default=str)
print(f"\n完整数据已保存到 /tmp/cached_course_analysis.json")

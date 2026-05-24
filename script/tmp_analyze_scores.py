"""分析低分考试"""
import json, re

with open('exam_scores_report.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

low_scores = []

for acc in data:
    username = acc.get('username', '?')
    platform = acc.get('platform', '?')
    for course in acc.get('courses', []):
        for exam in course.get('exams', []):
            final_raw = exam.get('finalScore', '0')
            final_clean = re.sub(r'<[^>]+>', '', str(final_raw))
            try:
                final_f = float(final_clean)
            except:
                final_f = 0
            total_f = float(exam.get('score', '0'))

            if total_f > 0 and final_f > 0:
                pct = (final_f / total_f) * 100
                if pct < 90:
                    low_scores.append({
                        'user': username,
                        'platform': platform,
                        'name': exam.get('name', '?'),
                        'score': final_f,
                        'total': total_f,
                        'pct': pct,
                        'topics': exam.get('topicNumber', '?'),
                        'rand': exam.get('randData', ''),
                        'state': exam.get('state', ''),
                    })

# 按分数排序
low_scores.sort(key=lambda x: x['pct'])

print(f'低分考试(<90%): {len(low_scores)}个\n')
for s in low_scores:
    print(f"{s['user']}@{s['platform']} - {s['name']}")
    print(f"  得分: {s['score']}/{s['total']} = {s['pct']:.0f}%")
    print(f"  题数: {s['topics']}, 随机题: {s['rand']}")
    print(f"  状态: {s['state']}")
    print()

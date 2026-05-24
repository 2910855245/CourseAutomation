import sys, io, os, json
sys.stdout.reconfigure(encoding='utf-8')
import paramiko
import httpx
from bs4 import BeautifulSoup

httpx.packages.urllib3.disable_warnings()

# SSH to remote server
with open(os.path.join(os.path.dirname(__file__), 'ssh_key')) as f:
    ssh_key = f.read()

kf = io.StringIO(ssh_key)
key = paramiko.Ed25519Key.from_private_key(kf)
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('38.76.190.251', 22, 'root', pkey=key, timeout=15, allow_agent=False, look_for_keys=False)

def run(cmd, timeout=15):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', errors='replace'), stderr.read().decode('utf-8', errors='replace')

# Get cookies for account with exam
username = '251060150509'
platform_name = '劳动课程测评考试平台'
base_url = 'https://cdcas.taiskeji.com'

out, _ = run(f'cat "/www/wwwroot/anti_course/data/accounts/{username}/cookies/{platform_name}.json"')
cookie_list = json.loads(out)
cookies = {c['name']: c['value'] for c in cookie_list}

# Create session
s = httpx.Client(timeout=httpx.Timeout(30.0), verify=False)
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'X-Requested-With': 'XMLHttpRequest'
})
for k, v in cookies.items():
    s.cookies.set(k, v)

# Check course with exams: 实验室安全教育 第二版 (1011331)
course_id = '1011331'

print(f"Checking course {course_id} on {base_url}")
print("="*60)

# Check index page for exam info
resp = s.get(f"{base_url}/user/course?courseId={course_id}", timeout=15)
print(f"\nCourse page status: {resp.status_code}")
if resp.status_code == 200:
    html = resp.text
    # Look for work/exam links
    import re
    work_matches = re.findall(r'workId["\s:=]+["\']?(\d+)', html)
    exam_matches = re.findall(r'examId["\s:=]+["\']?(\d+)', html)
    print(f"workId matches: {work_matches[:5]}")
    print(f"examId matches: {exam_matches[:5]}")

    # Look for node links
    node_matches = re.findall(r'nodeId["\s:=]+["\']?(\d+)', html)
    print(f"nodeId matches: {node_matches[:10]}")

    # Check for work/exam section
    soup = BeautifulSoup(html, 'html.parser')
    # Look for exam-related elements
    exam_els = soup.find_all(['div', 'li', 'a'], string=re.compile(r'考试|测验|作业|exam|quiz', re.IGNORECASE))
    print(f"\nExam-related elements: {len(exam_els)}")
    for el in exam_els[:5]:
        print(f"  {el.name}: {el.get_text(strip=True)[:100]}")
        if el.name == 'a':
            print(f"    href: {el.get('href', '')}")

# 1. Check study record to find exam nodes
resp = s.get(f"{base_url}/user/study_record/video", params={"courseId": course_id}, timeout=15)
print(f"Study record status: {resp.status_code}")

# 2. Check work/exam list page
resp = s.get(f"{base_url}/user/work?courseId={course_id}", timeout=15)
print(f"\nWork page status: {resp.status_code}")
html = resp.text

if resp.status_code == 200:
    soup = BeautifulSoup(html, 'html.parser')

    # Look for work/exam links
    links = soup.find_all('a', href=True)
    work_links = [l for l in links if 'work' in l.get('href', '').lower() or 'exam' in l.get('href', '').lower()]
    print(f"Found {len(work_links)} work/exam links")

    for link in work_links[:10]:
        href = link.get('href', '')
        text = link.get_text(strip=True)
        print(f"  {text}: {href}")

    # Look for topic/question elements
    topics = soup.find_all(['div', 'li', 'span'], class_=lambda x: x and ('topic' in str(x).lower() or 'question' in str(x).lower()))
    print(f"\nFound {len(topics)} topic/question elements")

    # Look for answer hints in HTML
    if 'answer' in html.lower():
        import re
        # Check for answer patterns
        answer_patterns = re.findall(r'answer["\s:=]+["\']?([A-Da-d])', html, re.IGNORECASE)
        if answer_patterns:
            print(f"\n[!] Found answer patterns in HTML: {answer_patterns[:10]}")

        # Check for correct answer hints
        correct_patterns = re.findall(r'correct["\s:=]+["\']?([A-Da-d])', html, re.IGNORECASE)
        if correct_patterns:
            print(f"[!] Found correct answer patterns: {correct_patterns[:10]}")

    # Look for hidden fields with answers
    hidden_fields = soup.find_all('input', type='hidden')
    print(f"\nFound {len(hidden_fields)} hidden fields")
    for hf in hidden_fields[:10]:
        name = hf.get('name', '')
        value = hf.get('value', '')
        if 'answer' in name.lower() or 'topic' in name.lower():
            print(f"  {name}: {value}")

# 3. Try to access a specific work/exam
# Get workId from the page
work_ids = []
for link in work_links:
    href = link.get('href', '')
    import re
    match = re.search(r'workId=(\d+)', href)
    if match:
        work_ids.append(match.group(1))

# Try different exam URLs
print(f"\n{'='*60}")
print(f"Trying different exam URLs")
print(f"{'='*60}")

exam_urls = [
    f"{base_url}/user/work?courseId={course_id}",
    f"{base_url}/user/exam?courseId={course_id}",
    f"{base_url}/user/work/list?courseId={course_id}",
    f"{base_url}/user/exam/list?courseId={course_id}",
]

for url in exam_urls:
    resp = s.get(url, timeout=15, follow_redirects=False)
    print(f"{url}")
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        html = resp.text
        # Check for work/exam content
        if 'workId' in html or 'examId' in html:
            print(f"  [!] Contains workId/examId")
            work_matches = re.findall(r'workId["\s:=]+["\']?(\d+)', html)
            exam_matches = re.findall(r'examId["\s:=]+["\']?(\d+)', html)
            if work_matches:
                print(f"  workId: {work_matches[:5]}")
            if exam_matches:
                print(f"  examId: {exam_matches[:5]}")
        if 'topic' in html.lower() or 'question' in html.lower():
            print(f"  [!] Contains topic/question content")

# Also check the course page HTML for hidden exam info
print(f"\n{'='*60}")
print(f"Checking course page HTML")
print(f"{'='*60}")

resp = s.get(f"{base_url}/user/course?courseId={course_id}", timeout=15)
if resp.status_code == 200:
    html = resp.text
    # Save HTML for inspection
    with open('exam_page.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Saved HTML to exam_page.html ({len(html)} bytes)")

    # Look for any exam/work related content
    soup = BeautifulSoup(html, 'html.parser')

    # Check all links
    all_links = soup.find_all('a', href=True)
    print(f"\nAll links ({len(all_links)}):")
    for link in all_links[:20]:
        href = link.get('href', '')
        text = link.get_text(strip=True)[:50]
        if text:
            print(f"  {text}: {href}")

    # Check for JavaScript with exam info
    scripts = soup.find_all('script')
    for script in scripts:
        script_text = script.get_text()
        if 'work' in script_text.lower() or 'exam' in script_text.lower():
            print(f"\n[!] Found exam/work in script:")
            print(script_text[:500])

# Check study record for exam info
print(f"\n{'='*60}")
print(f"Checking study records for exams")
print(f"{'='*60}")

resp = s.get(f"{base_url}/user/study_record/video", params={"courseId": course_id}, timeout=15)
if resp.status_code == 200:
    data = resp.json()
    records = data.get("list", [])
    print(f"Video records: {len(records)}")

# Check exam record
resp = s.get(f"{base_url}/user/study_record/exam", params={"courseId": course_id}, timeout=15)
print(f"\nExam record status: {resp.status_code}")
if resp.status_code == 200:
    try:
        data = resp.json()
        records = data.get("list", [])
        print(f"Exam records: {len(records)}")
        for r in records[:5]:
            print(f"  {r}")
    except:
        print(f"Response: {resp.text[:500]}")

# Check node page for exam links
print(f"\n{'='*60}")
print(f"Checking node page")
print(f"{'='*60}")

node_id = '1420746'
resp = s.get(f"{base_url}/user/node?nodeId={node_id}", timeout=15)
print(f"Node page status: {resp.status_code}")
if resp.status_code == 200:
    html = resp.text
    soup = BeautifulSoup(html, 'html.parser')

    # Look for work/exam links
    work_links = soup.find_all('a', href=lambda x: x and ('work' in x or 'exam' in x))
    print(f"Work/exam links: {len(work_links)}")
    for link in work_links[:5]:
        href = link.get('href', '')
        text = link.get_text(strip=True)
        print(f"  {text}: {href}")

# Check the actual exam page
print(f"\n{'='*60}")
print(f"Checking exam page")
print(f"{'='*60}")

# Try the exam URL from the HTML
exam_url = f"{base_url}/user/exam?nodeId=1420758&examId=1008205"
resp = s.get(exam_url, timeout=15)
print(f"Exam page status: {resp.status_code}")

if resp.status_code == 200:
    html = resp.text
    soup = BeautifulSoup(html, 'html.parser')

    # Save HTML for inspection
    with open('exam_questions.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Saved HTML to exam_questions.html ({len(html)} bytes)")

    # Look for question elements
    topic_items = soup.select('.topic-item, .question-item, .topic, .question')
    if not topic_items:
        topic_items = soup.find_all('div', class_=re.compile(r'topic|question'))

    print(f"Found {len(topic_items)} topic items")

    # Look for answer hints
    if 'answer' in html.lower():
        import re
        answer_patterns = re.findall(r'answer["\s:=]+["\']?([A-Da-d])', html, re.IGNORECASE)
        if answer_patterns:
            print(f"[!] Found answer patterns: {answer_patterns[:10]}")

    # Look for hidden fields
    hidden_fields = soup.find_all('input', type='hidden')
    print(f"\nFound {len(hidden_fields)} hidden fields")
    for hf in hidden_fields[:20]:
        name = hf.get('name', '')
        value = hf.get('value', '')
        print(f"  {name}: {value[:100]}")

    # Look for question content
    print(f"\nFirst 3 questions:")
    for idx, item in enumerate(topic_items[:3], 1):
        text = item.get_text(separator='\n', strip=True)[:300]
        print(f"\nQ{idx}: {text}")

# Also try the start endpoint
print(f"\n{'='*60}")
print(f"Trying start endpoint")
print(f"{'='*60}")

start_url = f"{base_url}/user/work/start"
data = {
    'workId': '1008205',
    'courseId': '1011331',
    'nodeId': '1420758',
}
resp = s.post(start_url, data=data, timeout=15)
print(f"Start status: {resp.status_code}")
print(f"Response: {resp.text[:500]}")

if resp.status_code == 200:
    html = resp.text
    soup = BeautifulSoup(html, 'html.parser')

    # Save HTML for inspection
    with open('exam_questions.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Saved HTML to exam_questions.html ({len(html)} bytes)")

    # Look for question elements
    topic_items = soup.select('.topic-item, .question-item, .topic, .question')
    if not topic_items:
        topic_items = soup.find_all('div', class_=re.compile(r'topic|question'))

    print(f"Found {len(topic_items)} topic items")

    # Look for answer hints
    if 'answer' in html.lower():
        import re
        answer_patterns = re.findall(r'answer["\s:=]+["\']?([A-Da-d])', html, re.IGNORECASE)
        if answer_patterns:
            print(f"[!] Found answer patterns: {answer_patterns[:10]}")

        correct_patterns = re.findall(r'correct["\s:=]+["\']?([A-Da-d])', html, re.IGNORECASE)
        if correct_patterns:
            print(f"[!] Found correct answer patterns: {correct_patterns[:10]}")

    # Look for hidden fields
    hidden_fields = soup.find_all('input', type='hidden')
    print(f"\nFound {len(hidden_fields)} hidden fields")
    for hf in hidden_fields[:20]:
        name = hf.get('name', '')
        value = hf.get('value', '')
        if 'answer' in name.lower() or 'topic' in name.lower() or 'correct' in name.lower():
            print(f"  [!] {name}: {value}")

    # Look for question content
    print(f"\nFirst 3 questions:")
    for idx, item in enumerate(topic_items[:3], 1):
        text = item.get_text(separator='\n', strip=True)[:300]
        print(f"\nQ{idx}: {text}")

        # Check for answer in this question
        answer_el = item.find(attrs={'name': re.compile(r'answer|correct')})
        if answer_el:
            print(f"  [!] Answer: {answer_el.get('value', '')}")

    if resp.status_code == 200:
        html = resp.text
        soup = BeautifulSoup(html, 'html.parser')

        # Parse topics
        topic_items = soup.select('.topic-item, .question-item, .topic, .question')
        if not topic_items:
            topic_items = soup.find_all('div', class_=re.compile(r'topic|question'))

        print(f"Found {len(topic_items)} topic items")

        # Check for answers in HTML
        if 'answer' in html.lower():
            answer_patterns = re.findall(r'answer["\s:=]+["\']?([A-Da-d])', html, re.IGNORECASE)
            if answer_patterns:
                print(f"[!] Found answer patterns: {answer_patterns[:10]}")

        # Print first few topics
        for idx, item in enumerate(topic_items[:3], 1):
            text = item.get_text(separator='\n', strip=True)[:200]
            print(f"\nTopic {idx}: {text}")

            # Check for answer in this topic
            answer_el = item.find(attrs={'name': re.compile(r'answer|correct')})
            if answer_el:
                print(f"  [!] Answer element: {answer_el.get('value', '')}")

ssh.close()

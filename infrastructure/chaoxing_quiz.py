"""
学习通答题系统

字体解码 + 题目解析 + DeepSeek AI 答题 + 答案提交。
"""
import re
import os
import json
import time
import base64
import pickle
import hashlib
from loguru import logger
from io import BytesIO
from hashlib import sha1, md5

from infrastructure.chaoxing_session import ChaoxingSession


BASE_URL = 'https://mooc1.chaoxing.com'

# Kangxi Radicals -> CJK Unified Ideographs
RADICAL_TO_CJK = {
    '⼀': '一', '⼆': '二', '⼈': '人', '⼊': '入', '⼋': '八',
    '⼗': '十', '⼤': '大', '⼥': '女', '⼦': '子', '⼩': '小',
    '⼭': '山', '⼯': '工', '⼰': '己', '⼱': '巾', '⼲': '干',
    '⼼': '心', '⼿': '手', '⽀': '支', '⽂': '文', '⽅': '方',
    '⽇': '日', '⽉': '月', '⽊': '木', '⽔': '⽔', '⽕': '火',
    '⽟': '玉', '⽣': '生', '⽤': '用', '⽥': '田', '⽯': '石',
    '⽰': '示', '⽴': '立', '⽼': '老', '⾃': '自', '⾄': '至',
    '⾏': '行', '⾐': '衣', '⾓': '角', '⾔': '言', '⾛': '走',
    '⾜': '足', '⾞': '⾞', '⾥': '里', '⾦': '金', '⾨': '门',
    '⾯': '面', '⾰': '革', '⾼': '⾼', '⺠': '民',
}

MANUAL_CORRECTIONS = {chr(0x5A83): '两'}

# ============ 字体解码 ============


def load_ref_hashes(path: str = 'HanSansCN_glyfHashedTables.pkl') -> dict:
    """加载参考字体哈希表"""
    with open(path, 'rb') as f:
        ref_data = pickle.load(f)[0]
    return {h: name for name, h in ref_data}


def decode_font_from_html(html: str, ref_hashes: dict) -> dict:
    """从HTML中提取base64字体并解码映射"""
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        logger.error("fontTools 未安装，请执行: pip install fonttools")
        return {}

    match = re.search(r'base64,([A-Za-z0-9+/=]{100,})', html)
    if not match:
        return {}

    font_bytes = base64.b64decode(match.group(1))
    ttfont = TTFont(BytesIO(font_bytes))
    glyphs = ttfont['glyf'].glyphs
    cmap = ttfont.getBestCmap()
    cmap_inv = {v: k for k, v in cmap.items()}

    mapping = {}
    glyf_table = ttfont['glyf']
    for glyph_name, glyph in glyphs.items():
        if glyph_name == '.notdef':
            continue
        try:
            data = glyph.data if hasattr(glyph, 'data') and glyph.data else glyph.compile(glyf_table)
        except Exception:
            continue
        if not data:
            continue
        h = (sha1(data).digest(), md5(data).digest())
        if h in ref_hashes:
            ref_name = ref_hashes[h]
            if ref_name.startswith('uni'):
                try:
                    orig_cp = int(ref_name[3:], 16)
                    orig_char = chr(orig_cp)
                except ValueError:
                    continue
                if glyph_name in cmap_inv:
                    obf_char = chr(cmap_inv[glyph_name])
                    if orig_char in RADICAL_TO_CJK:
                        orig_char = RADICAL_TO_CJK[orig_char]
                    mapping[obf_char] = orig_char
    ttfont.close()

    for obf, correct in MANUAL_CORRECTIONS.items():
        if obf in mapping:
            mapping[obf] = correct
    return mapping


def decode_text(text: str, mapping: dict) -> str:
    """用映射表解码文本"""
    for obf, real in mapping.items():
        text = text.replace(obf, real)
    return text


# ============ 题目解析 ============


def parse_quiz(html: str, mapping: dict) -> tuple:
    """解析作业页面HTML为结构化题目

    支持两种格式：
    1. 标准学习通：cxsecret字体加密 + qid属性
    2. tsjy平台（形势与政策）：普通文本 + 无qid属性

    返回: (questions: list, form_params: dict)
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, 'html.parser')
    questions = []

    title_divs = soup.find_all(class_='Zy_TItle')
    for i, title_div in enumerate(title_divs):
        # 优先找 cxsecret 字体加密标签，回退到 fontLabel 标签
        label_div = title_div.find(class_=lambda x: x and 'cxsecret' in x and 'fontLabel' in x)
        if not label_div:
            label_div = title_div.find(class_=lambda x: x and 'fontLabel' in x)
        if not label_div:
            # 回退：取整个标题div的文本
            label_div = title_div

        text = decode_text(label_div.get_text(strip=True), mapping)

        if '判断题' in text or 'True or False' in text:
            qtype = 'judgment'
        elif '单选题' in text or 'Single Choice' in text:
            qtype = 'single'
        elif '多选题' in text or 'Multiple Choice' in text:
            qtype = 'multiple'
        else:
            qtype = 'unknown'

        options = []
        next_sib = title_div.find_next_sibling()
        qid = ''
        if next_sib:
            # 优先找带 qid 属性的 li
            li_with_qid = next_sib.find_all('li', attrs={'qid': True})
            if li_with_qid:
                for li in li_with_qid:
                    qid = li.get('qid', '')
                    opt_text = decode_text(li.get_text(strip=True), mapping)
                    options.append(opt_text)
            else:
                # tsjy 格式：普通 li 无 qid
                for li in next_sib.find_all('li'):
                    opt_text = decode_text(li.get_text(strip=True), mapping)
                    options.append(opt_text)

        # tsjy 格式无 qid，用题目序号生成
        if not qid:
            qid = str(i + 1)

        ans_type_input = soup.find('input', {'name': f'answertype{qid}'})
        ans_type = ans_type_input.get('value', '') if ans_type_input else ''

        questions.append({
            'index': i,
            'qid': qid,
            'type': qtype,
            'ans_type': ans_type,
            'text': text,
            'options': options,
        })

    # 提取表单参数
    form = soup.find('form')
    form_params = {}
    if form:
        action = form.get('action', '')
        if '?' in action:
            for pair in action.split('?', 1)[1].split('&'):
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    form_params[k] = v
        for inp in form.find_all('input', {'type': 'hidden'}):
            name = inp.get('name', '')
            value = inp.get('value', '')
            if name and not name.startswith('answer') and not name.startswith('answertype'):
                form_params[name] = value

    return questions, form_params


# ============ AI答题 ============


def ask_deepseek(questions: list, api_key: str, model: str = 'deepseek-v4-flash') -> list:
    """调用 DeepSeek API 回答题目

    返回: [{'qid': str, 'answer': str}, ...]
    """
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai 未安装，请执行: pip install openai")
        return []

    client = OpenAI(api_key=api_key, base_url='https://api.deepseek.com')

    prompt_parts = ["请回答以下学习通题目。直接给出答案，不要解释。\n"]
    for q in questions:
        qnum = q['index'] + 1
        prompt_parts.append(f"第{qnum}题: {q['text']}")
        for j, opt in enumerate(q['options']):
            clean_opt = re.sub(r'^[A-Da-d]\s*', '', opt).strip()
            label = chr(65 + j)
            prompt_parts.append(f"  {label}. {clean_opt}")
        prompt_parts.append("")

    prompt_parts.append(f"共{len(questions)}题，请按以下JSON格式输出答案：")
    prompt_parts.append('```json')
    prompt_parts.append('[{"num": 1, "answer": "A或true"}, {"num": 2, "answer": "B"}]')
    prompt_parts.append('```')

    prompt = '\n'.join(prompt_parts)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是学习通答题助手。直接给出正确答案，用JSON格式输出。"
                 "判断题答案为true(对)或false(错)，单选题答案为A/B/C/D，多选题答案如AB/ACD。"
                 "必须用JSON数组格式输出，每题一个对象。"},
                {"role": "user", "content": prompt},
            ],
            stream=False,
            temperature=0.1,
        )
        content = response.choices[0].message.content
        logger.info(f"DeepSeek 响应 length={len(content)}")
    except Exception as e:
        logger.error(f"DeepSeek API 错误 error={str(e)}")
        return []

    # 解析JSON
    json_match = re.search(r'\[.*\]', content, re.DOTALL)
    if json_match:
        try:
            raw_answers = json.loads(json_match.group())
            answers = []
            for item in raw_answers:
                num = item.get('num', item.get('qid', 0))
                try:
                    num = int(num)
                except (ValueError, TypeError):
                    for q in questions:
                        if str(item.get('qid', '')) == q['qid']:
                            answers.append({'qid': q['qid'], 'answer': item.get('answer', '')})
                            break
                    continue
                if 1 <= num <= len(questions):
                    answers.append({
                        'qid': questions[num - 1]['qid'],
                        'answer': item.get('answer', ''),
                    })
            return answers
        except json.JSONDecodeError:
            pass

    # 备用解析
    answers = []
    for q in questions:
        qid = q['qid']
        for line in content.split('\n'):
            if qid in line:
                ans_match = re.search(r'["\']?answer["\']?\s*[:=]\s*["\']?([A-D]+|true|false)', line, re.I)
                if ans_match:
                    answers.append({'qid': qid, 'answer': ans_match.group(1)})
                    break
    return answers


def format_answer_for_submit(qtype: str, answer) -> str:
    """格式化答案为提交格式"""
    if isinstance(answer, bool):
        ans = 'true' if answer else 'false'
    else:
        ans = str(answer).strip().upper()
    if qtype == 'judgment':
        if ans in ('TRUE', '对', 'A', 'T', '1'):
            return 'true'
        return 'false'
    return ans


# ============ 提交答案 ============


def submit_answers(session: ChaoxingSession, form_params: dict,
                   questions: list, answers: list) -> tuple:
    """提交作业答案

    返回: (status_code: int, response_text: str)
    """
    class_id = form_params.get('_classId', form_params.get('classId', ''))
    course_id = form_params.get('courseid', form_params.get('courseId', ''))
    token = form_params.get('token', '')
    work_id = form_params.get('workid', form_params.get('workRelationId', ''))
    cpi = form_params.get('cpi', '')
    jobid = form_params.get('jobid', '')
    knowledgeid = form_params.get('knowledgeid', '')

    url = (f"{BASE_URL}/mooc-ans/work/addStudentWorkNewWeb"
           f"?_classId={class_id}&courseid={course_id}&token={token}"
           f"&totalQuestionNum={form_params.get('totalQuestionNum', '')}"
           f"&workid={work_id}&cpi={cpi}&jobid={jobid}"
           f"&knowledgeid={knowledgeid}&testmooc2=1"
           f"&originJobId={form_params.get('originJobId', jobid)}")

    data = {}
    for k, v in form_params.items():
        if not k.startswith('_'):
            data[k] = v

    answer_map = {a['qid']: a['answer'] for a in answers}
    for q in questions:
        qid = q['qid']
        if qid in answer_map:
            formatted = format_answer_for_submit(q['type'], answer_map[qid])
            data[f'answer{qid}'] = formatted
            data[f'answertype{qid}'] = q['ans_type']
        else:
            data[f'answer{qid}'] = ''
            data[f'answertype{qid}'] = q['ans_type']

    try:
        resp = session.post(url, data=data, referer=BASE_URL + '/')
        return resp.status_code, resp.text()
    except Exception as e:
        logger.error(f"提交答案失败 error={str(e)}")
        return 0, str(e)


# ============ 答案缓存 ============


class AnswerCache:
    """答案缓存，避免重复调用AI"""

    def __init__(self, path: str = '_answer_cache.json', enabled: bool = True):
        self.path = path
        self.enabled = enabled
        self.data = {}
        if enabled and os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}

    def _hash(self, questions: list) -> str:
        text = '|'.join(q['text'] for q in questions)
        return sha1(text.encode('utf-8')).hexdigest()[:16]

    def get(self, questions: list):
        if not self.enabled:
            return None
        key = self._hash(questions)
        return self.data.get(key)

    def set(self, questions: list, answers: list):
        if not self.enabled:
            return
        key = self._hash(questions)
        self.data[key] = answers
        self.save()

    def save(self):
        try:
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


# ============ 作业列表获取 ============


def get_work_list(session: ChaoxingSession, course_id: str, class_id: str, cpi: str = '') -> list:
    """获取课程的作业/考试列表

    返回: [{'workId': str, 'title': str, 'status': str, 'type': 'exam'|'work',
            'examId': str, 'paperId': str, 'enc': str, 'endTime': str}, ...]
    """
    if not cpi:
        try:
            resp = session.get('https://mooc1-api.chaoxing.com/mycourse/backclazzdata?view=json&rss=1')
            for ch in resp.json().get('channelList', []):
                content = ch.get('content', {})
                if isinstance(content, dict):
                    for c in content.get('course', {}).get('data', []):
                        if str(c.get('id', '')) == course_id:
                            cpi = str(ch.get('cpi', ''))
                            break
        except Exception:
            pass

    items = []

    # 1. 获取考试列表 (exam-ans 域名)
    try:
        exam_url = (f'{BASE_URL}/mooc2/exam/exam-list'
                    f'?clazzid={class_id}&courseid={course_id}&cpi={cpi}')
        resp = session.get(exam_url, referer=BASE_URL + '/')
        if resp.status_code == 302:
            try:
                loc = resp.headers['location']
                if isinstance(loc, bytes):
                    loc = loc.decode()
                resp = session.get(loc, referer=exam_url)
            except Exception:
                pass
        html = resp.text()

        # 解析 goTest(courseId, examId, relationId, endTime, paperId, isRetest, enc)
        for m in re.finditer(
                r"goTest\('([^']*)',\s*(\d+),\s*(\d+),\s*'([^']*)',\s*(\d+),\s*(true|false),\s*'([^']*)'\)",
                html):
            cid_g, exam_id, rel_id, end_time, paper_id, is_retest, enc = m.groups()
            # 提取标题（goTest后面的文本）
            end = min(len(html), m.end() + 1000)
            after = html[m.end():end]
            title_match = re.search(r'class="overHidden2[^"]*"[^>]*>(.*?)</p>', after, re.DOTALL)
            title = title_match.group(1).strip() if title_match else f'考试{exam_id}'
            title = re.sub(r'<[^>]+>', '', title).strip()
            # 提取状态
            status_match = re.search(r'class="status[^"]*"[^>]*>(.*?)</(?:p|div|span)>', after, re.DOTALL)
            status = status_match.group(1).strip() if status_match else ''

            items.append({
                'workId': exam_id,
                'examId': exam_id,
                'title': title,
                'status': status,
                'type': 'exam',
                'paperId': paper_id,
                'enc': enc,
                'endTime': end_time,
                'relationId': rel_id,
                'courseId': course_id,
                'classId': class_id,
                'cpi': cpi,
            })

        if items:
            logger.info(f"获取考试列表 count={len(items)} course_id={course_id}")
    except Exception as e:
        logger.warning(f"获取考试列表失败 error={str(e)}")

    # 2. 获取作业列表 (mooc-ans 域名)
    try:
        work_url = (f'{BASE_URL}/mooc2/work/work-list'
                    f'?clazzid={class_id}&courseid={course_id}&cpi={cpi}')
        resp = session.get(work_url, referer=BASE_URL + '/')
        if resp.status_code == 302:
            try:
                loc = resp.headers['location']
                if isinstance(loc, bytes):
                    loc = loc.decode()
                resp = session.get(loc, referer=work_url)
            except Exception:
                pass
        html = resp.text()

        if '无权限' not in html and '暂时没有数据' not in html and len(html) > 500:
            # 解析作业列表（格式可能与考试类似）
            for m in re.finditer(r'workId["\s:=]+["\']?(\d+)', html):
                wid = m.group(1)
                if not any(it['workId'] == wid for it in items):
                    items.append({
                        'workId': wid,
                        'title': f'作业{wid}',
                        'status': '',
                        'type': 'work',
                        'courseId': course_id,
                        'classId': class_id,
                        'cpi': cpi,
                    })
    except Exception as e:
        logger.warning(f"获取作业列表失败 error={str(e)}")

    # 3. 备用：旧的 mooc-ans 端点（兼容旧版）
    if not items:
        try:
            old_url = (f'{BASE_URL}/mooc-ans/work/{class_id}/list'
                       f'?courseId={course_id}&classId={class_id}&cpi={cpi}&ut=s')
            resp = session.get(old_url, referer=BASE_URL + '/')
            html = resp.text()
            if resp.status_code == 200 and len(html) > 500:
                for m in re.finditer(r'workId["\s:=]+["\']?(\d+)', html):
                    wid = m.group(1)
                    if not any(it['workId'] == wid for it in items):
                        items.append({
                            'workId': wid,
                            'title': f'作业{wid}',
                            'status': '',
                            'type': 'work',
                        })
        except Exception:
            pass

    # 去重
    seen = set()
    unique = []
    for w in items:
        wid = w.get('workId', '')
        if wid and wid not in seen:
            seen.add(wid)
            unique.append(w)
    return unique


# ============ 一站式答题 ============


def _is_hash_workid(workid: str) -> bool:
    """判断是否为哈希格式的workId（tsjy平台）"""
    return bool(workid) and not workid.isdigit()


def _fetch_clean_questions(session: ChaoxingSession, work_url: str) -> str:
    """通过api=1端点获取无字体加密的题目页面（tsjy平台专用）

    api=1 端点会重定向到 selectWorkQuestion 页面，返回干净文本。
    """
    import urllib.parse

    # 从 workHandle URL 提取参数，构造 api/work URL
    parsed = urllib.parse.urlparse(work_url)
    params = urllib.parse.parse_qs(parsed.query)

    workid = params.get('workId', [''])[0]
    jobid = params.get('jobid', [''])[0]
    kid = params.get('knowledgeid', [''])[0]
    ktoken = params.get('ktoken', [''])[0]
    cpi = params.get('cpi', [''])[0]
    enc = params.get('enc', [''])[0]
    clid = params.get('classId', [''])[0]
    cid = params.get('courseid', params.get('courseId', ['']))[0]

    if not workid:
        return ''

    # 构造 api/work URL（与 work module index.html 一致）
    api_url = (f'{BASE_URL}/mooc-ans/api/work?api=1&workId={workid}'
               f'&jobid={jobid}&originJobId={jobid}'
               f'&needRedirect=true&skipHeader=true'
               f'&knowledgeid={kid}&ktoken={ktoken}&cpi={cpi}'
               f'&enc={enc}&clazzId={clid}&courseId={cid}')

    try:
        resp = session.get(api_url, referer=BASE_URL + '/')
        # 跟随重定向链（最多3步）
        for _ in range(3):
            if resp.status_code in (301, 302, 303, 307, 308):
                loc = resp.headers.get('location')
                if isinstance(loc, bytes):
                    loc = loc.decode('utf-8')
                if loc.startswith('/'):
                    loc = BASE_URL + loc
                resp = session.get(loc, referer=api_url)
            else:
                break
        html = resp.text()
        # 验证是否为干净文本（无font-cxsecret）
        if 'font-cxsecret' not in html and len(html) > 500:
            return html
    except Exception as e:
        logger.warning(f"获取clean questions失败: {e}")
    return ''


def _merge_clean_questions(clean_html: str, encrypted_html: str,
                           mapping: dict) -> tuple:
    """合并干净文本题目和加密页面的表单参数

    从clean_html提取题目文本，从encrypted_html提取qid和form参数。
    返回: (questions: list, form_params: dict)
    """
    from bs4 import BeautifulSoup

    # 从加密页面获取 form_params 和 qid 列表
    enc_soup = BeautifulSoup(encrypted_html, 'html.parser')
    form_params = {}
    form = enc_soup.find('form')
    if form:
        action = form.get('action', '')
        if '?' in action:
            for pair in action.split('?', 1)[1].split('&'):
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    form_params[k] = v
        for inp in form.find_all('input', {'type': 'hidden'}):
            name = inp.get('name', '')
            value = inp.get('value', '')
            if name and not name.startswith('answer') and not name.startswith('answertype'):
                form_params[name] = value

    # 从加密页面获取 qid 和 answertype
    # qid 在 singleQuesId div 的 data 属性中，或在 li 的 qid 属性中
    enc_title_divs = enc_soup.find_all(class_='Zy_TItle')
    qid_list = []
    ans_type_list = []
    for td in enc_title_divs:
        qid = ''
        ans_type = ''

        # 方法1：从父级 singleQuesId div 的 data 属性获取
        parent_div = td.find_parent(class_='singleQuesId')
        if parent_div:
            qid = parent_div.get('data', '')

        # 方法2：从 li 的 qid 属性获取
        if not qid:
            next_sib = td.find_next_sibling()
            if next_sib:
                li_with_qid = next_sib.find_all('li', attrs={'qid': True})
                if li_with_qid:
                    qid = li_with_qid[0].get('qid', '')

        # 方法3：从 hidden input 获取
        if not qid:
            for inp in enc_soup.find_all('input', {'name': re.compile(r'^answer\d+')}):
                name = inp.get('name', '')
                candidate = name[6:]  # 去掉 'answer' 前缀
                if candidate not in [q for q in qid_list if q]:
                    qid = candidate
                    break

        if qid:
            ans_type_input = enc_soup.find('input', {'name': f'answertype{qid}'})
            ans_type = ans_type_input.get('value', '') if ans_type_input else ''
        qid_list.append(qid)
        ans_type_list.append(ans_type)

    # 从干净页面提取题目
    clean_soup = BeautifulSoup(clean_html, 'html.parser')
    clean_title_divs = clean_soup.find_all(class_='Zy_TItle')

    questions = []
    for i, td in enumerate(clean_title_divs):
        label = td.find(class_='fontLabel') or td
        text = label.get_text(strip=True)

        if '判断题' in text or 'True or False' in text:
            qtype = 'judgment'
        elif '单选题' in text or 'Single Choice' in text:
            qtype = 'single'
        elif '多选题' in text or 'Multiple Choice' in text:
            qtype = 'multiple'
        else:
            qtype = 'unknown'

        options = []
        next_sib = td.find_next_sibling()
        if next_sib:
            for li in next_sib.find_all('li'):
                opt_text = li.get_text(strip=True)
                options.append(opt_text)

        qid = qid_list[i] if i < len(qid_list) and qid_list[i] else str(i + 1)
        ans_type = ans_type_list[i] if i < len(ans_type_list) else ''

        questions.append({
            'index': i,
            'qid': qid,
            'type': qtype,
            'ans_type': ans_type,
            'text': text,
            'options': options,
        })

    return questions, form_params


def solve_quiz(session: ChaoxingSession, work_url: str,
               api_key: str, model: str = 'deepseek-v4-flash',
               ref_hashes: dict = None,
               cache: AnswerCache = None,
               dry_run: bool = False) -> dict:
    """解答单个作业

    返回: {success: bool, total: int, cached: bool, submitted: bool, error: str}
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return {'success': False, 'total': 0, 'error': 'bs4 未安装'}

    # 获取作业页面
    try:
        resp = session.get(work_url, referer=BASE_URL + '/')
        html = resp.text()
    except Exception as e:
        return {'success': False, 'total': 0, 'error': f'获取页面失败: {e}'}

    # 检测是否为tsjy哈希workId（字体加密页面）
    # 尝试获取干净文本用于AI答题
    clean_html = ''
    workid_match = re.search(r'workId=([a-f0-9]{20,})', work_url)
    if workid_match:
        logger.info(f"检测到哈希workId，尝试获取干净文本")
        clean_html = _fetch_clean_questions(session, work_url)
        if clean_html:
            logger.info(f"获取干净文本成功 len={len(clean_html)}")

    # 加载字体参考
    if ref_hashes is None:
        try:
            ref_hashes = load_ref_hashes()
        except Exception as e:
            ref_hashes = {}
            logger.warning(f"字体参考未加载，使用空映射: {e}")

    # 解码字体
    mapping = decode_font_from_html(html, ref_hashes)
    logger.info(f"字体解码 mappings={len(mapping)}")

    # 解析题目
    if clean_html:
        # 合并干净文本和加密页面的表单参数
        questions, form_params = _merge_clean_questions(clean_html, html, mapping)
        logger.info(f"合并解析题目 count={len(questions)}")
    else:
        questions, form_params = parse_quiz(html, mapping)
        logger.info(f"解析题目 count={len(questions)}")
    if not questions:
        return {'success': False, 'total': 0, 'error': '未找到题目'}

    for q in questions:
        logger.info(f"题目 index={q['index'] + 1} type={q['type']} text={q['text'][:60]}")

    # 检查缓存
    if cache is None:
        cache = AnswerCache()

    cached = cache.get(questions)
    if cached:
        answers = cached
        logger.info("使用缓存答案")
    else:
        # 调用AI
        answers = ask_deepseek(questions, api_key, model)
        if answers:
            cache.set(questions, answers)
        else:
            return {'success': False, 'total': len(questions), 'error': 'AI未返回答案'}

    # 显示答案
    answer_map = {a['qid']: a['answer'] for a in answers}
    for q in questions:
        ans = answer_map.get(q['qid'], '?')
        formatted = format_answer_for_submit(q['type'], ans)
        logger.info(f"答案 index={q['index'] + 1} answer={formatted}")

    # 提交
    if dry_run:
        logger.info("[DRY-RUN] 不提交")
        return {'success': True, 'total': len(questions), 'cached': cached is not None, 'submitted': False}

    status, result = submit_answers(session, form_params, questions, answers)
    if status == 200:
        logger.info("提交成功")
        return {'success': True, 'total': len(questions), 'cached': cached is not None, 'submitted': True}
    else:
        logger.error(f"提交失败 status={status}")
        return {'success': False, 'total': len(questions), 'error': f'提交失败: status={status}'}

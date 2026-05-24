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
    for glyph_name, glyph in glyphs.items():
        if glyph_name == '.notdef' or not glyph.data:
            continue
        h = (sha1(glyph.data).digest(), md5(glyph.data).digest())
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

    返回: (questions: list, form_params: dict)
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, 'html.parser')
    questions = []

    title_divs = soup.find_all(class_='Zy_TItle')
    for i, title_div in enumerate(title_divs):
        label_div = title_div.find(class_=lambda x: x and 'cxsecret' in x and 'fontLabel' in x)
        if not label_div:
            continue

        text = decode_text(label_div.get_text(strip=True), mapping)

        if '判断题' in text:
            qtype = 'judgment'
        elif '单选题' in text:
            qtype = 'single'
        elif '多选题' in text:
            qtype = 'multiple'
        else:
            qtype = 'unknown'

        options = []
        next_sib = title_div.find_next_sibling()
        qid = ''
        if next_sib:
            for li in next_sib.find_all('li', attrs={'qid': True}):
                qid = li.get('qid', '')
                opt_text = decode_text(li.get_text(strip=True), mapping)
                options.append(opt_text)

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


def get_work_list(session: ChaoxingSession, course_id: str, class_id: str) -> list:
    """获取课程的作业列表"""
    from bs4 import BeautifulSoup

    url = (f'{BASE_URL}/mooc-ans/work/{class_id}/list'
           f'?courseId={course_id}&classId={class_id}&cpi=0&ut=s')
    try:
        resp = session.get(url, referer=BASE_URL + '/')
        html = resp.text()
    except Exception as e:
        logger.warning(f"获取作业列表失败 error={str(e)}")
        return []

    works = []
    soup = BeautifulSoup(html, 'html.parser')

    # 尝试HTML结构提取
    items = soup.select('.workItem, .work-item, .clearfix.li_1, .jobList .clearfix')
    if not items:
        # 备用: 从script中提取
        for script in soup.find_all('script'):
            text = script.string or ''
            for m in re.finditer(r'workId["\s:=]+["\']?(\d+)', text):
                works.append({'workId': m.group(1), 'status': 'unknown'})
        for a in soup.find_all('a', href=True):
            href = a.get('href', '')
            if '/work/' in href and 'workId' not in href:
                m = re.search(r'/work/(\d+)', href)
                if m:
                    works.append({'workId': m.group(1), 'title': a.get_text(strip=True), 'status': 'unknown'})
    else:
        for item in items:
            title_el = item.select_one('.workName, .tit, h3, a')
            title = title_el.get_text(strip=True) if title_el else ''
            link = item.select_one('a[href*="work"]')
            href = link.get('href', '') if link else ''
            work_id = ''
            m = re.search(r'workId=(\d+)', href)
            if m:
                work_id = m.group(1)
            if not work_id:
                m = re.search(r'/work/(\d+)', href)
                if m:
                    work_id = m.group(1)
            status_el = item.select_one('.status, .state, .notComplete')
            status = status_el.get_text(strip=True) if status_el else ''
            if work_id:
                works.append({'workId': work_id, 'title': title, 'status': status, 'href': href})

    # 去重
    seen = set()
    unique = []
    for w in works:
        wid = w.get('workId', '')
        if wid and wid not in seen:
            seen.add(wid)
            unique.append(w)
    return unique


# ============ 一站式答题 ============


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

    # 加载字体参考
    if ref_hashes is None:
        try:
            ref_hashes = load_ref_hashes()
        except Exception as e:
            return {'success': False, 'total': 0, 'error': f'加载字体参考失败: {e}'}

    # 解码字体
    mapping = decode_font_from_html(html, ref_hashes)
    logger.info(f"字体解码 mappings={len(mapping)}")

    # 解析题目
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

"""
学习通讨论/笔记发表

通过 groupweb.chaoxing.com 的 API 发表讨论和笔记，用于赚取积分。
使用 DeepSeek API 生成讨论内容。
"""
import os
import re
import uuid
from loguru import logger

from infrastructure.chaoxing_session import ChaoxingSession



def _get_api_key() -> str:
    """获取 DeepSeek API Key（优先从数据库读取）"""
    # 1. 先从数据库读（后台配置）
    try:
        from api.database import db
        db_key = db.config_get("deepseek_api_key")
        if db_key:
            return db_key
    except Exception:
        pass

    # 2. 从环境变量读
    api_key = os.environ.get('DEEPSEEK_API_KEY', '')
    if api_key:
        return api_key

    # 3. 从config读
    try:
        from config import settings
        if settings.deepseek_api_key:
            return settings.deepseek_api_key
    except Exception:
        pass

    return ''


def generate_discussion_content(course_name: str, knowledge_name: str = '',
                                 api_key: str = '') -> tuple:
    """用 DeepSeek 生成讨论内容

    Returns:
        (title, content) 元组
    """
    if not api_key:
        api_key = _get_api_key()
    if not api_key:
        logger.warning("未配置DEEPSEEK_API_KEY，使用默认内容")
        return ('学习心得', '通过本节课程的学习，对相关知识有了更深入的理解，收获很大。')

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url='https://api.deepseek.com')

        prompt = f"""你是一个认真学习的学生。请为以下课程写一条学习讨论帖。

课程名称：{course_name}
知识点：{knowledge_name or '课程内容'}

要求：
1. 标题简短有力，10字以内
2. 内容50-100字，表达学习心得、收获或疑问
3. 语气自然真实，像真人学生写的
4. 不要出现"作为AI"等字样
5. 直接输出，不要解释

输出格式：
标题: xxx
内容: xxx"""

        response = client.chat.completions.create(
            model='deepseek-chat',
            messages=[
                {"role": "system", "content": "你是学习讨论帖生成助手，生成真实自然的学习心得。"},
                {"role": "user", "content": prompt},
            ],
            stream=False,
            temperature=0.8,
            max_tokens=200,
        )

        content = response.choices[0].message.content.strip()

        # 解析标题和内容
        title_match = re.search(r'标题[：:]\s*(.+)', content)
        content_match = re.search(r'内容[：:]\s*(.+)', content, re.DOTALL)

        title = title_match.group(1).strip() if title_match else '学习心得'
        body = content_match.group(1).strip() if content_match else content

        # 清理
        title = title[:20].strip()
        body = body[:200].strip()

        logger.info(f"DeepSeek生成讨论 title={title}")
        return (title, body)

    except Exception as e:
        logger.warning(f"DeepSeek生成失败，使用默认内容 error={str(e)}")
        return ('学习心得', '通过本节课程的学习，对相关知识有了更深入的理解，收获很大。')


def get_discuss_bbsid(session: ChaoxingSession, course_id: str, class_id: str,
                      knowledge_id: str = '') -> str:
    """获取讨论区 bbsid

    通过知识点代理URL获取讨论区的 bbsid 和 urlToken。
    """
    if knowledge_id:
        proxy_url = f'https://tsjy.chaoxing.com/plaza/proxy/{course_id}/5/url?classId={class_id}&knowledgeId={knowledge_id}'
    else:
        proxy_url = f'https://tsjy.chaoxing.com/plaza/proxy/{course_id}/5/url?classId={class_id}'

    try:
        resp = session.get(proxy_url, referer=f'https://tsjy.chaoxing.com/plaza/knowledge-all?courseId={course_id}')
        # 从重定向URL中提取bbsid
        bbsid_match = re.search(r'bbsid=([a-f0-9]+)', resp.url)
        if bbsid_match:
            return bbsid_match.group(1)
    except Exception as e:
        logger.warning(f"获取讨论区bbsid失败 error={str(e)}")

    return ''


def _get_url_token(session: ChaoxingSession, bbsid: str, course_id: str,
                   class_id: str) -> str:
    """获取讨论区的 urlToken（发表讨论需要）"""
    url = f'https://groupweb.chaoxing.com/course/topic/topicList?bbsid={bbsid}&courseid={course_id}&clazzid={class_id}&isInit=0'
    try:
        resp = session.get(url, referer=f'https://tsjy.chaoxing.com/')
        token_match = re.search(r"urlToken:'([a-f0-9]+)'", resp.text())
        if token_match:
            return token_match.group(1)
    except Exception as e:
        logger.warning(f"获取urlToken失败 error={str(e)}")

    return ''


def post_discussion(session: ChaoxingSession, course_id: str, class_id: str,
                    bbsid: str, content: str, title: str = '',
                    use_ai: bool = False, course_name: str = '',
                    knowledge_name: str = '') -> dict:
    """发表讨论

    Args:
        session: 学习通会话
        course_id: 课程ID
        class_id: 班级ID
        bbsid: 讨论区ID
        content: 讨论内容（use_ai=True时会被覆盖）
        title: 讨论标题（use_ai=True时会被覆盖）
        use_ai: 是否使用DeepSeek生成内容
        course_name: 课程名（AI生成用）
        knowledge_name: 知识点名（AI生成用）

    Returns:
        {'success': bool, 'title': str, 'content': str, 'topic_id': int}
    """
    # 使用AI生成内容
    if use_ai:
        title, content = generate_discussion_content(course_name, knowledge_name)
        logger.info(f"AI生成讨论 title={title} content_len={len(content)}")

    if not content:
        return {'success': False, 'error': '内容为空'}

    # 获取 urlToken
    url_token = _get_url_token(session, bbsid, course_id, class_id)
    if not url_token:
        logger.warning("无法获取urlToken，跳过讨论发表")
        return {'success': False, 'error': '无法获取urlToken'}

    # 生成UUID
    topic_uuid = str(uuid.uuid4())

    # 构建请求
    url = f'https://groupweb.chaoxing.com/pc/topic/{bbsid}/addTopic?uuid={topic_uuid}'
    data = {
        'topicTitle': title,
        'topicContent': content,
        'bbsid': bbsid,
        'courseId': course_id,
        'tags': f'classId{class_id}',
        'urlToken': url_token,
    }

    try:
        resp = session.post(url, data=data,
                            referer=f'https://groupweb.chaoxing.com/course/topic/topicList?bbsid={bbsid}')
        result = resp.json()
        if result.get('status'):
            topic_id = result.get('objs', {}).get('topicId', 0)
            logger.info(f"讨论发表成功 uuid={topic_uuid} topic_id={topic_id}")
            return {
                'success': True,
                'title': title,
                'content': content,
                'topic_id': topic_id,
                'uuid': topic_uuid,
            }
        else:
            msg = result.get('msg', '')
            logger.warning(f"讨论发表失败 msg={msg}")
            return {'success': False, 'error': msg}
    except Exception as e:
        logger.warning(f"讨论发表异常 error={str(e)}")
        return {'success': False, 'error': str(e)}


def post_note(session: ChaoxingSession, course_id: str, class_id: str,
              knowledge_id: str, content: str, title: str = '',
              use_ai: bool = False, course_name: str = '') -> dict:
    """发表笔记

    Args:
        session: 学习通会话
        course_id: 课程ID
        class_id: 班级ID
        knowledge_id: 知识点ID
        content: 笔记内容
        title: 笔记标题
        use_ai: 是否使用DeepSeek生成内容
        course_name: 课程名（AI生成用）

    Returns:
        {'success': bool, 'title': str, 'content': str}
    """
    # 使用AI生成内容
    if use_ai:
        title, content = generate_discussion_content(course_name, f'知识点{knowledge_id}')
        logger.info(f"AI生成笔记 title={title} content_len={len(content)}")

    # 尝试笔记API
    note_url = 'https://noteyd.chaoxing.com/pc/note_note/createNote'
    note_data = {
        'courseId': course_id,
        'classId': class_id,
        'knowledgeId': knowledge_id,
        'title': title or '学习笔记',
        'content': content,
    }

    try:
        resp = session.post(note_url, data=note_data,
                            referer=f'https://tsjy.chaoxing.com/')
        result = resp.json()
        if result.get('result') == 1:
            logger.info("笔记发表成功")
            return {'success': True, 'title': title, 'content': content}
    except Exception:
        pass

    # 笔记API不可用，回退到讨论区
    logger.info("笔记API不可用，回退到讨论区发表")
    bbsid = get_discuss_bbsid(session, course_id, class_id, knowledge_id)
    if bbsid:
        return post_discussion(session, course_id, class_id, bbsid,
                               content, title or '学习笔记')
    return {'success': False, 'error': '无法获取讨论区bbsid'}

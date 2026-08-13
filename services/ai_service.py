import time
from typing import Dict

import httpx
from loguru import logger

# 配置项缓存（TTL=300s，避免每次请求都查库）
_config_cache: Dict[str, tuple] = {}
_CACHE_TTL = 300


def _cached_config(key: str, default: str = "") -> str:
    """从数据库读取配置，带TTL缓存"""
    now = time.time()
    if key in _config_cache:
        val, ts = _config_cache[key]
        if now - ts < _CACHE_TTL:
            return val
    try:
        from api.database import db
        val = db.config_get(key) or default
    except Exception:
        val = default
    _config_cache[key] = (val, now)
    return val


def _invalidate_config_cache(key: str = None):
    """清除配置缓存（配置变更时调用）"""
    if key:
        _config_cache.pop(key, None)
    else:
        _config_cache.clear()


class AIService:
    def __init__(self, session: httpx.Client, website_id: int = 1):
        self.session = session
        self.website_id = website_id
        from config import DEEPSEEK_API_KEY, get_base_url
        self.base_url = get_base_url().rstrip('/')
        self._env_key = DEEPSEEK_API_KEY

    @property
    def api_key(self) -> str:
        db_key = _cached_config("deepseek_api_key")
        return db_key or self._env_key

    def solve_exam(self, work_id: str, course_id: str = None,
                   node_id: str = None, auto_submit: bool = True,
                   is_final_exam: bool = False) -> Dict:
        from infrastructure.school.anti_test import (
            AIAnswerer,
            OnlineHeartbeat,
            TopicFetcher,
            WorkSubmitter,
            normalize_base_url,
        )

        base = normalize_base_url(self.base_url)
        wid = int(work_id) if str(work_id).isdigit() else work_id
        cid = int(course_id) if course_id and str(course_id).isdigit() else 0
        nid = int(node_id) if node_id and str(node_id).isdigit() else 0

        if not self.api_key:
            return {"success": False, "error": "DEEPSEEK_API_KEY 未配置，请在 .env 中设置"}

        heartbeat = OnlineHeartbeat(
            session=self.session,
            online_url=f"{base}/user/online",
            login_url=f"{base}/user/login",
        )
        try:
            heartbeat.start()

            fetcher = TopicFetcher(self.session, base)
            work_data = fetcher.fetch(wid, cid, nid)
            topics = work_data.get("topics", [])
            if not topics:
                err_msg = work_data.get("error", "未获取到题目")
                return {"success": False, "error": err_msg}

            logger.info(f"获取到 {len(topics)} 道题，开始AI答题...")

            # 根据考试类型选择模型
            if is_final_exam:
                exam_model = _cached_config("deepseek_final_exam_model", "deepseek-v4-flash")
            else:
                exam_model = _cached_config("deepseek_homework_model", "deepseek-v4-flash")
            answerer = AIAnswerer(self.api_key, model=exam_model)
            answers = {}
            blank_counts = {}  # 记录每题的空格数量
            for topic in topics:
                tid = topic["topic_id"]
                q_type = topic.get("q_type", "")
                question = topic.get("question", "")

                # 获取填空题的空格数量（从 topic 数据中）
                blank_count = topic.get('blank_count', 0)
                blank_counts[tid] = blank_count

                ai_res = answerer.ask_one_topic(topic)
                answer = ai_res.get("answer", "").strip()

                # 如果AI没有返回答案，标记为空
                if not answer or answer == "暂无":
                    answers[tid] = ""
                    logger.warning(f"第{topic.get('number', '?')}题 AI未返回答案")
                else:
                    answers[tid] = answer

                logger.info(f"第{topic.get('number', '?')}题 -> {answer} (置信度 {ai_res.get('confidence', 0)})")
                time.sleep(0.3)

            if not auto_submit:
                return {"success": True, "answers": answers, "total": len(topics), "submitted": False}

            real_work_id = work_data.get("work_id", wid)
            submit_type = getattr(fetcher, '_submit_type', 'work')
            node_id = work_data.get("node_id", "")
            submitter = WorkSubmitter(self.session, base, real_work_id, submit_type=submit_type, node_id=node_id)
            submitted = 0
            skipped = 0
            failed_topics = []  # 记录提交失败的题目
            last_aid = ""
            for topic in topics:
                aid = topic.get("answer_id", topic.get("topic_id", ""))
                last_aid = aid
                ans = answers.get(topic["topic_id"], answers.get(aid, ""))
                q_type = topic.get("q_type", "")
                blank_count = blank_counts.get(topic["topic_id"], 0)

                # 如果答案为空，跳过提交
                if not ans:
                    skipped += 1
                    logger.warning(f"跳过 {aid}：AI未返回答案")
                    continue

                # 提交 + 重试
                ok = False
                for attempt in range(3):
                    ret = submitter.submit_topic(aid, ans, q_type=q_type, blank_count=blank_count)
                    if ret.get("status") is not False:
                        ok = True
                        break
                    logger.warning(f"提交 {aid} 失败(第{attempt+1}次): {ret.get('msg')}")
                    time.sleep(1)

                if ok:
                    submitted += 1
                else:
                    logger.error(f"提交 {aid} 最终失败")
                    failed_topics.append(topic)
                time.sleep(0.5)

            # 验证提交结果：重新获取题目，检查答案是否记录
            if submitted > 0:
                logger.info(f"提交完成 {submitted}/{len(topics)}，开始验证...")
                verify_data = fetcher.fetch(wid, cid, nid)
                verify_topics = verify_data.get("topics", [])
                missing = []
                for vt in verify_topics:
                    vid = vt.get("answer_id", vt.get("topic_id", ""))
                    # 找到对应原始题目
                    orig = next((t for t in topics if t.get("answer_id") == vid), None)
                    if orig:
                        orig_ans = answers.get(orig["topic_id"], answers.get(vid, ""))
                        if orig_ans and vid in [ft.get("answer_id", "") for ft in failed_topics]:
                            missing.append((vid, orig_ans))

                # 重试失败的题目
                for aid, ans in missing:
                    logger.info(f"重试提交 {aid} -> {ans}")
                    q_type = next((t.get("q_type", "") for t in topics if t.get("answer_id") == aid), "")
                    blank_count = blank_counts.get(aid, 0)
                    for attempt in range(3):
                        ret = submitter.submit_topic(aid, ans, q_type=q_type, blank_count=blank_count)
                        if ret.get("status") is not False:
                            submitted += 1
                            failed_topics = [t for t in failed_topics if t.get("answer_id") != aid]
                            break
                        time.sleep(1)

            # 如果有题目被跳过（AI未返回答案），拒绝交卷
            if skipped > 0:
                logger.error(f"有 {skipped} 道题AI未返回答案，拒绝交卷")
                return {
                    "success": False,
                    "total": len(topics),
                    "submitted": submitted,
                    "skipped": skipped,
                    "final": None,
                    "error": f"AI未返回{skipped}道题的答案，拒绝交卷",
                }

            # 获取最后一题的题型和空格数
            last_topic = topics[-1] if topics else {}
            last_q_type = last_topic.get("q_type", "")
            last_blank_count = blank_counts.get(last_topic.get("topic_id", ""), 0)
            final = submitter.final_submit(last_aid, answers.get(last_aid, "A"),
                                           q_type=last_q_type, blank_count=last_blank_count)
            logger.info(f"交卷结果: {final}")

            ok = submitted > 0 and final.get("status") is not False
            return {
                "success": ok,
                "total": len(topics),
                "submitted": submitted,
                "final": final,
                "error": None if ok else f"提交{submitted}/{len(topics)}题，交卷失败" if submitted > 0 else "全部题目提交失败",
            }
        except Exception as e:
            logger.error(f"solve_exam error: work_id={work_id}, error={e}")
            return {"success": False, "error": str(e)}
        finally:
            heartbeat.stop()

    def solve_project_work(self, work_id: int, course_id: int, node_id: int,
                           question_text: str = "", student_id: str = "",
                           student_name: str = "") -> Dict:
        """解决项目提交题（简答+文件上传）"""
        from infrastructure.school.project_solver import ProjectSolver

        if not self.api_key:
            return {"success": False, "error": "DEEPSEEK_API_KEY 未配置"}

        try:
            solver = ProjectSolver(
                session=self.session,
                base_url=self.base_url,
                api_key=self.api_key,
                student_id=student_id,
                student_name=student_name,
            )
            return solver.solve(work_id, course_id, node_id, question_text)
        except Exception as e:
            logger.error(f"solve_project_work error: work_id={work_id}, error={e}")
            return {"success": False, "error": str(e)}

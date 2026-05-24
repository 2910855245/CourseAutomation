import time
from typing import Dict

import httpx
from loguru import logger



class AIService:
    def __init__(self, session: httpx.Client, website_id: int = 1):
        self.session = session
        self.website_id = website_id
        from config import DEEPSEEK_API_KEY, get_base_url
        self.base_url = get_base_url().rstrip('/')
        self._env_key = DEEPSEEK_API_KEY

    @property
    def api_key(self) -> str:
        try:
            from api.database import db
            db_key = db.config_get("deepseek_api_key")
            if db_key:
                return db_key
        except Exception as e:
            pass
        return self._env_key

    def solve_exam(self, work_id: str, course_id: str = None,
                   node_id: str = None, auto_submit: bool = True,
                   is_final_exam: bool = False) -> Dict:
        from infrastructure.anti_test import (
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
                # 期末考试使用 deepseek-v4-flash
                exam_model = "deepseek-v4-flash"
                try:
                    from api.database import db
                    m = db.config_get("deepseek_final_exam_model")
                    if m:
                        exam_model = m
                except Exception as e:
                    pass
            else:
                # 普通作业使用 deepseek-chat
                exam_model = "deepseek-chat"
                try:
                    from api.database import db
                    m = db.config_get("deepseek_homework_model")
                    if m:
                        exam_model = m
                except Exception as e:
                    pass
            answerer = AIAnswerer(self.api_key, model=exam_model)
            answers = {}
            for topic in topics:
                tid = topic["topic_id"]
                ai_res = answerer.ask_one_topic(topic)
                answer = ai_res.get("answer", "").strip()
                if not answer:
                    q_type = topic.get("q_type", "")
                    is_ch = '单选' in q_type or '多选' in q_type or '判断' in q_type
                    answer = "A" if is_ch else "暂无"
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
            last_aid = ""
            for topic in topics:
                aid = topic.get("answer_id", topic.get("topic_id", ""))
                last_aid = aid
                ans = answers.get(topic["topic_id"], answers.get(aid, "A"))
                q_type = topic.get("q_type", "")
                ret = submitter.submit_topic(aid, ans, q_type=q_type)
                if ret.get("status") is False:
                    logger.error(f"提交 {aid} 失败: {ret.get('msg')}")
                else:
                    submitted += 1
                time.sleep(0.5)

            final = submitter.final_submit(last_aid, answers.get(last_aid, "A"))
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

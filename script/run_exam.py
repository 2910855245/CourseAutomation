#!/usr/bin/env python3
"""在远程服务器上执行考试

用法: EXAM_USERNAME=xxx EXAM_PASSWORD=yyy python script/run_exam.py
或在 script/.env.local 中配置 EXAM_USERNAME / EXAM_PASSWORD
"""
import os
import sys

sys.path.insert(0, "/www/wwwroot/anti_course")

# 加载 .env.local
try:
    import dotenv
    dotenv.load_dotenv(os.path.join(os.path.dirname(__file__), ".env.local"), override=False)
except ImportError:
    pass

from loguru import logger

from api.database import db
from api.services.session_pool import pool

# 获取 session（从环境变量或 .env.local 读取）
username = os.environ.get("EXAM_USERNAME", "")
password = os.environ.get("EXAM_PASSWORD", "")
website_id = int(os.environ.get("EXAM_WEBSITE_ID", "2"))

if not username or not password:
    logger.error("请设置 EXAM_USERNAME 和 EXAM_PASSWORD 环境变量")
    sys.exit(1)

info = pool.get_or_login(username, password, website_id)
session = info.session
logger.info(f"登录成功 student={info.student_name}")

# 获取 cookie string
cookies = session.cookies.get_dict()
cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())

# 获取 API key
api_key = db.config_get("deepseek_api_key") or ""
if not api_key:
    from config import DEEPSEEK_API_KEY
    api_key = DEEPSEEK_API_KEY
logger.info("API key loaded key_prefix={}", api_key[:10] + "...")

from infrastructure.anti_test import AIWorkRunner

# 使用 cookie 登录方式
runner = AIWorkRunner(
    base_url="https://cdcas.taiskeji.com",
    api_key=api_key,
    cookie_str=cookie_str
)

# 考试参数
work_id = 1008208
course_id = 1011333
node_id = 1420839

logger.info(f"开始考试 work_id={work_id} course_id={course_id} node_id={node_id}")
answers = runner.run(work_id=work_id, course_id=course_id, node_id=node_id, auto_submit=True)
logger.info(f"考试完成 answers_count={len(answers)}")

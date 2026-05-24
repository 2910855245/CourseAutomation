import json
import os
import random
import threading
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Settings(BaseSettings):
    jwt_secret_key: str = Field(default="", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expire_hours: int = Field(default=72, alias="JWT_EXPIRE_HOURS")
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    debug: bool = Field(default=False, alias="DEBUG")
    db_path: str = Field(default="data/orders.db", alias="DB_PATH")
    database_url: str = Field(default="", alias="DATABASE_URL")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    rate_limit_requests: int = Field(default=600, alias="RATE_LIMIT_REQUESTS")
    rate_limit_window_seconds: int = Field(default=60, alias="RATE_LIMIT_WINDOW_SECONDS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    site_url: str = Field(default="http://localhost:8000", alias="SITE_URL")
    vmqpay_url: str = Field(default="", alias="VMQPAY_URL")
    vmqpay_key: str = Field(default="", alias="VMQPAY_KEY")
    password_encryption_key: str = Field(default="", alias="PASSWORD_ENCRYPTION_KEY")
    cors_origins: str = Field(default="http://localhost:5173", alias="CORS_ORIGINS")

    model_config = {"env_file": os.path.join(BASE_DIR, ".env"), "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

# 启动时校验必填配置
_missing = []
if not settings.jwt_secret_key:
    _missing.append("JWT_SECRET_KEY")
if not settings.database_url:
    _missing.append("DATABASE_URL")
if not settings.password_encryption_key:
    _missing.append("PASSWORD_ENCRYPTION_KEY")
if _missing:
    import sys

    from loguru import logger
    logger.error(f"缺少必填环境变量 missing={_missing}")
    sys.exit(1)

# 全局状态锁
_global_state_lock = threading.RLock()

# ==================== 统一数据目录 ====================
DATA_DIR = os.path.join(BASE_DIR, "data")
ACCOUNTS_DIR = os.path.join(DATA_DIR, "accounts")
LOGS_DIR = os.path.join(DATA_DIR, "logs")
GLOBAL_CONFIG_DIR = os.path.join(DATA_DIR, "global_config")
GLOBAL_CONFIG_FILE = os.path.join(GLOBAL_CONFIG_DIR, "global_config.json")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(ACCOUNTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(GLOBAL_CONFIG_DIR, exist_ok=True)

# ==================== 多网站配置 ====================
WEBSITES = {
    1: {"name": "在线课程测评考试平台", "base_url": "https://cdcas.suwankj.com"},
    2: {"name": "劳动课程测评考试平台", "base_url": "https://cdcas.taiskeji.com"},
    3: {"name": "公益课程平台", "base_url": "https://cdcas.chaoxiankeji.com"},
    4: {"name": "学习通", "base_url": "https://mooc1.chaoxing.com", "type": "chaoxing"},
}

# 学习通配置
CHAOXING_CONFIG = {
    "score_target": 200,        # 积分目标
    "daily_limit": 50,          # 每日积分上限
    "video_weight": 180,        # 视频积分上限
    "login_weight": 10,         # 登录积分上限
    "discussion_weight": 10,    # 讨论积分上限
    "notes_weight": 10,         # 笔记积分上限
    "font_hash_file": "HanSansCN_glyfHashedTables.pkl",
    "deepseek_api_key": "",     # 从 .env 读取
}

# ==================== 全局配置管理 ====================
CURRENT_WEBSITE = 1

def load_global_config():
    global CURRENT_WEBSITE
    with _global_state_lock:
        if os.path.exists(GLOBAL_CONFIG_FILE):
            try:
                with open(GLOBAL_CONFIG_FILE, encoding='utf-8') as f:
                    config = json.load(f)
                    saved_website = config.get("last_website_id")
                    if saved_website and saved_website in WEBSITES:
                        CURRENT_WEBSITE = saved_website
                        return True
            except Exception as e:
                from loguru import logger
                logger.warning(f"加载全局配置失败 error={str(e)}")
        return False

def save_global_config():
    import datetime
    config = {
        "last_website_id": CURRENT_WEBSITE,
        "remember_website_choice": True,
        "last_website_switch_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    try:
        with open(GLOBAL_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        from loguru import logger
        logger.warning(f"保存全局配置失败 error={str(e)}")
        return False

load_global_config()

# ==================== 动态URL配置 ====================
def get_current_website_config():
    with _global_state_lock:
        return WEBSITES.get(CURRENT_WEBSITE, WEBSITES[1])

def get_base_url():
    return get_current_website_config()["base_url"]

def set_current_website(website_id: int):
    global CURRENT_WEBSITE
    if website_id not in WEBSITES:
        raise ValueError(f"无效的网站ID: {website_id}")
    with _global_state_lock:
        CURRENT_WEBSITE = website_id

def update_url_config():
    global BASE_URL, LOGIN_URL, CAPTCHA_URL, USER_CENTER_URL, HEADERS
    with _global_state_lock:
        BASE_URL = get_base_url()
        LOGIN_URL = f"{BASE_URL}/user/login"
        CAPTCHA_URL = f"{BASE_URL}/service/code"
        USER_CENTER_URL = f"{BASE_URL}/user/index"
        HEADERS = get_headers()

BASE_URL = get_base_url()
LOGIN_URL = f"{BASE_URL}/user/login"
CAPTCHA_URL = f"{BASE_URL}/service/code"
USER_CENTER_URL = f"{BASE_URL}/user/index"

# ==================== 账号路径管理 ====================
_current_account = None

def set_current_account(username: str):
    global _current_account
    with _global_state_lock:
        _current_account = username

def get_current_account() -> str:
    with _global_state_lock:
        return _current_account

def get_account_dir(username: str = None) -> str:
    username = username or get_current_account()
    if not username:
        return ACCOUNTS_DIR
    account_path = os.path.join(ACCOUNTS_DIR, username)
    os.makedirs(account_path, exist_ok=True)
    return account_path

def get_account_cookies_dir(username: str = None) -> str:
    cookies_dir = os.path.join(get_account_dir(username), "cookies")
    os.makedirs(cookies_dir, exist_ok=True)
    return cookies_dir

def get_account_cookies_path(username: str = None, website_name: str = None) -> str:
    cookies_dir = get_account_cookies_dir(username)
    if website_name:
        safe_name = website_name.replace(" ", "_")
        return os.path.join(cookies_dir, f"{safe_name}.json")
    return os.path.join(cookies_dir, "cookies.json")

def _migrate_old_data(account_dir: str, target_dir: str, subdir_name: str):
    old_dir = os.path.join(account_dir, subdir_name)
    if not os.path.exists(old_dir):
        return
    has_files = False
    for item in os.listdir(old_dir):
        item_path = os.path.join(old_dir, item)
        if os.path.isfile(item_path):
            has_files = True
            break
    if not has_files:
        return
    for item in os.listdir(old_dir):
        item_path = os.path.join(old_dir, item)
        if os.path.isfile(item_path):
            target_path = os.path.join(target_dir, item)
            if not os.path.exists(target_path):
                try:
                    import shutil
                    shutil.move(item_path, target_path)
                except Exception as e:
                    pass

def get_account_courses_dir(username: str = None) -> str:
    website_name = get_current_website_config().get("name", "unknown")
    safe_name = website_name.replace(" ", "_")
    courses_dir = os.path.join(get_account_dir(username), "courses", safe_name)
    os.makedirs(courses_dir, exist_ok=True)
    _migrate_old_data(get_account_dir(username), courses_dir, "courses")
    return courses_dir

def get_account_records_dir(username: str = None) -> str:
    website_name = get_current_website_config().get("name", "unknown")
    safe_name = website_name.replace(" ", "_")
    records_dir = os.path.join(get_account_dir(username), "records", safe_name)
    os.makedirs(records_dir, exist_ok=True)
    _migrate_old_data(get_account_dir(username), records_dir, "records")
    return records_dir

def get_account_config_path(username: str = None) -> str:
    return os.path.join(get_account_dir(username), "config.json")

def get_account_last_play_path(username: str = None) -> str:
    return os.path.join(get_account_dir(username), "last_play.json")

def get_account_log_path(username: str = None) -> str:
    username = username or get_current_account()
    if not username:
        return os.path.join(LOGS_DIR, "default.log")
    return os.path.join(LOGS_DIR, f"{username}.log")

# ==================== 兼容旧代码 ====================
def get_account_course_info_dir(username: str = None) -> str:
    return get_account_courses_dir(username)

def get_account_study_records_dir(username: str = None) -> str:
    return get_account_records_dir(username)

def update_paths_for_current_account():
    global COURSE_JSON_DIR, COOKIE_FILE
    COURSE_JSON_DIR = get_account_courses_dir()
    COOKIE_FILE = get_account_cookies_path()

COURSE_JSON_DIR = get_account_courses_dir()
COOKIE_FILE = get_account_cookies_path()

COURSE_DIR = DATA_DIR
USERNAME = ""
PASSWORD = ""

# ==================== 用户配置 ====================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36 Edg/117.0.2045.43",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.2210.91",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.2151.72",
]

def get_headers():
    return {"User-Agent": random.choice(USER_AGENTS), "Referer": LOGIN_URL}

HEADERS = get_headers()

def get_random_user_agent() -> str:
    return random.choice(USER_AGENTS)

TEST_MODE = False
TEST_VIDEO_COUNT = 999999
AUTO_FETCH_ALL_RECORDS = True

DEEPSEEK_API_KEY = settings.deepseek_api_key

VIDEO_PARAM_IDS = [
    'video-file', 'video-nodeId', 'user-id', 'school-id',
    'study-state', 'appId', 'nonce', 'timestamp', 'sign',
    'video-duration', 'video-mode'
]

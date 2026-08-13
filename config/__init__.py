"""config 包 — 兼容 shim。

从 config.py 三分拆而来：
- config/settings.py  纯环境配置（Settings + validate_settings）
- config/platforms.py 平台静态数据（WEBSITES/CHAOXING_CONFIG/USER_AGENTS）
- 本文件              全局状态（当前网站/账号上下文、URL 快照、路径管理）

所有旧 `from config import X` 保持不变。
"""

import json
import os
import random
import re
import threading

from loguru import logger

from config.platforms import (
    CHAOXING_CONFIG,
    USER_AGENTS,
    VIDEO_PARAM_IDS,
    WEBSITES,
    get_random_user_agent,
)
from config.settings import ROOT_DIR, Settings, get_settings, settings, validate_settings
from config.context import (
    get_account_username,
    get_base_url as _ctx_get_base_url,
    get_website_config as _ctx_get_website_config,
    init_process_context,
    init_worker_context,
    set_account_username,
    set_website_id,
)

# ==================== 统一数据目录 ====================
BASE_DIR = ROOT_DIR
DATA_DIR = os.path.join(BASE_DIR, "data")
ACCOUNTS_DIR = os.path.join(DATA_DIR, "accounts")
LOGS_DIR = os.path.join(DATA_DIR, "logs")
GLOBAL_CONFIG_DIR = os.path.join(DATA_DIR, "global_config")
GLOBAL_CONFIG_FILE = os.path.join(GLOBAL_CONFIG_DIR, "global_config.json")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(ACCOUNTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(GLOBAL_CONFIG_DIR, exist_ok=True)

# 全局状态锁
_global_state_lock = threading.RLock()

# ==================== 全局配置管理（当前网站） ====================
CURRENT_WEBSITE = 1


def load_global_config() -> bool:
    """已迁移到 config.context.init_process_context；保留函数兼容旧调用。"""
    init_process_context()
    return True


def save_global_config() -> bool:
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
        logger.warning(f"保存全局配置失败 error={str(e)}")
        return False


load_global_config()


# ==================== 动态 URL 配置 ====================
def get_current_website_config() -> dict:
    """委托 contextvars（线程级上下文 + 进程默认回退）"""
    return _ctx_get_website_config()


def get_base_url() -> str:
    """委托 contextvars；旧模块级快照 BASE_URL 为 deprecated 兼容层"""
    return _ctx_get_base_url()


def set_current_website(website_id: int):
    """deprecated：委托 set_website_id（contextvars）"""
    set_website_id(website_id)
    global CURRENT_WEBSITE
    with _global_state_lock:
        CURRENT_WEBSITE = website_id


def get_headers() -> dict:
    return {"User-Agent": random.choice(USER_AGENTS), "Referer": LOGIN_URL}


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
HEADERS = get_headers()


# ==================== 账号路径管理 ====================
_current_account = None


def set_current_account(username: str):
    """deprecated：委托 set_account_username（contextvars）"""
    set_account_username(username)
    global _current_account
    with _global_state_lock:
        _current_account = username


def get_current_account() -> str:
    """委托 contextvars；兼容旧调用返回 str"""
    return get_account_username() or ""


_INVALID_USERNAME_CHARS = re.compile(r"[^\w\-.]")


def _sanitize_username(username: str) -> str:
    """净化用户名：只允许字母数字下划线短横点，防路径穿越"""
    return _INVALID_USERNAME_CHARS.sub("_", username or "")


def get_account_dir(username: str = None) -> str:
    username = _sanitize_username(username or get_account_username())
    if not username or username in (".", ".."):
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
    has_files = any(os.path.isfile(os.path.join(old_dir, i)) for i in os.listdir(old_dir))
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
                except Exception:
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
    username = username or get_account_username()
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

TEST_MODE = False
TEST_VIDEO_COUNT = 999999
AUTO_FETCH_ALL_RECORDS = True

DEEPSEEK_API_KEY = settings.deepseek_api_key

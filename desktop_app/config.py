"""精简配置 — 去掉 FastAPI/数据库依赖，保留刷课核心"""
import json
import os
import random
import threading

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ==================== 数据目录 ====================
DATA_DIR = os.path.join(BASE_DIR, "data")
ACCOUNTS_DIR = os.path.join(DATA_DIR, "accounts")
LOGS_DIR = os.path.join(DATA_DIR, "logs")
GLOBAL_CONFIG_DIR = os.path.join(DATA_DIR, "global_config")
GLOBAL_CONFIG_FILE = os.path.join(GLOBAL_CONFIG_DIR, "global_config.json")

for d in (DATA_DIR, ACCOUNTS_DIR, LOGS_DIR, GLOBAL_CONFIG_DIR):
    os.makedirs(d, exist_ok=True)

# ==================== 多网站配置 ====================
WEBSITES = {
    1: {"name": "在线课程测评考试平台", "base_url": "https://cdcass.taiskeji.com"},
    2: {"name": "劳动课程测评考试平台", "base_url": "https://cdcas.duxingkej.com"},
    3: {"name": "公益课程平台", "base_url": "https://cdcas.chaoxiankeji.com"},
    4: {"name": "学习通", "base_url": "https://mooc1.chaoxing.com", "type": "chaoxing"},
}

# 学习通配置
CHAOXING_CONFIG = {
    "score_target": 200,
    "daily_limit": 200,
    "video_weight": 180,
    "login_weight": 10,
    "discussion_weight": 10,
    "notes_weight": 10,
    "font_hash_file": "HanSansCN_glyfHashedTables.pkl",
}

# ==================== 全局状态 ====================
_global_state_lock = threading.RLock()
CURRENT_WEBSITE = 1


def load_global_config():
    global CURRENT_WEBSITE
    with _global_state_lock:
        if os.path.exists(GLOBAL_CONFIG_FILE):
            try:
                with open(GLOBAL_CONFIG_FILE, encoding="utf-8") as f:
                    config = json.load(f)
                    saved = config.get("last_website_id")
                    if saved and saved in WEBSITES:
                        CURRENT_WEBSITE = saved
                        return True
            except Exception:
                pass
    return False


def save_global_config():
    import datetime
    config = {
        "last_website_id": CURRENT_WEBSITE,
        "remember_website_choice": True,
        "last_website_switch_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        with open(GLOBAL_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


load_global_config()


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


def get_account_courses_dir(username: str = None) -> str:
    website_name = get_current_website_config().get("name", "unknown")
    safe_name = website_name.replace(" ", "_")
    courses_dir = os.path.join(get_account_dir(username), "courses", safe_name)
    os.makedirs(courses_dir, exist_ok=True)
    return courses_dir


def get_account_records_dir(username: str = None) -> str:
    website_name = get_current_website_config().get("name", "unknown")
    safe_name = website_name.replace(" ", "_")
    records_dir = os.path.join(get_account_dir(username), "records", safe_name)
    os.makedirs(records_dir, exist_ok=True)
    return records_dir


def get_account_config_path(username: str = None) -> str:
    return os.path.join(get_account_dir(username), "config.json")


def get_account_log_path(username: str = None) -> str:
    username = username or get_current_account()
    if not username:
        return os.path.join(LOGS_DIR, "default.log")
    return os.path.join(LOGS_DIR, f"{username}.log")


def update_paths_for_current_account():
    global COURSE_JSON_DIR, COOKIE_FILE
    COURSE_JSON_DIR = get_account_courses_dir()
    COOKIE_FILE = get_account_cookies_path()


COURSE_JSON_DIR = get_account_courses_dir()
COOKIE_FILE = get_account_cookies_path()

# ==================== User-Agent ====================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]


def get_headers():
    return {"User-Agent": random.choice(USER_AGENTS), "Referer": LOGIN_URL}


def get_random_user_agent() -> str:
    return random.choice(USER_AGENTS)


BASE_URL = get_base_url()
LOGIN_URL = f"{BASE_URL}/user/login"
CAPTCHA_URL = f"{BASE_URL}/service/code"
USER_CENTER_URL = f"{BASE_URL}/user/index"
HEADERS = get_headers()

VIDEO_PARAM_IDS = [
    "video-file", "video-nodeId", "user-id", "school-id",
    "study-state", "appId", "nonce", "timestamp", "sign",
    "video-duration", "video-mode",
]

"""平台静态配置：网站列表、学习通参数、UA 池。纯数据，无副作用。"""

import random

# 多网站配置
WEBSITES = {
    1: {"name": "在线课程测评考试平台", "base_url": "https://cdcass.taiskeji.com"},
    2: {"name": "劳动课程测评考试平台", "base_url": "https://cdcas.duxingkej.com"},
    3: {"name": "公益课程平台", "base_url": "https://cdcas.chaoxiankeji.com"},
    4: {"name": "学习通", "base_url": "https://mooc1.chaoxing.com", "type": "chaoxing"},
}

# 学习通配置
CHAOXING_CONFIG = {
    "score_target": 200,        # 积分目标
    "daily_limit": 200,         # 每日积分上限（改为200，一天完成）
    "video_weight": 180,        # 视频积分上限
    "login_weight": 10,         # 登录积分上限
    "discussion_weight": 10,    # 讨论积分上限
    "notes_weight": 10,         # 笔记积分上限
    "font_hash_file": "HanSansCN_glyfHashedTables.pkl",
    "deepseek_api_key": "",     # 从 .env 读取
}

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


def get_random_user_agent() -> str:
    return random.choice(USER_AGENTS)


VIDEO_PARAM_IDS = [
    'video-file', 'video-nodeId', 'user-id', 'school-id',
    'study-state', 'appId', 'nonce', 'timestamp', 'sign',
    'video-duration', 'video-mode'
]

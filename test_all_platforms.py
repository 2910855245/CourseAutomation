import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, "/www/wwwroot/anti_course")

import httpx

from config import (
    set_current_account,
    set_current_website,
    update_paths_for_current_account,
    update_url_config,
)
from infrastructure.platform_health import PlatformHealthChecker
from services.multi_platform_auth import load_platform_cookie

accounts = [
    ("251060150515", 1, "粟湾平台"),
    ("251060150515", 2, "劳动教育平台"),
    ("251060150515", 3, "中嘉鑫盛"),
]

for username, wid, name in accounts:
    session = httpx.Client(timeout=httpx.Timeout(30.0), verify=False)
    ok = load_platform_cookie(username, wid, session)
    if not ok:
        print(f"\n[{name}] 无cookie，跳过")
        continue
    set_current_website(wid)
    set_current_account(username)
    update_url_config()
    update_paths_for_current_account()
    
    checker = PlatformHealthChecker()
    result = checker.run_full_check(session, wid)
    print(f"\n[{name}] overall={result['overall']}")
    for k, v in result.get("checks", {}).items():
        print(f"  {k}: {v['status']} - {v['message']}")

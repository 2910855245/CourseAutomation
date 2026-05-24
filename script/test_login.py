"""
多平台登录测试脚本
用法: python scripts/test_login.py 学号 密码
      python scripts/test_login.py 251060150506 a285991
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import WEBSITES
from services.multi_platform_auth import login_all_platforms


def test_login(username: str, password: str):
    print(f"账号: {username}")
    print(f"密码: {password}")
    print()

    results = login_all_platforms(username, password)

    print()
    print("=" * 60)
    ok_count = 0
    for wid in sorted(WEBSITES.keys()):
        name = WEBSITES[wid]["name"]
        url = WEBSITES[wid]["base_url"]
        ok, session, msg = results.get(wid, (False, None, "无结果"))
        if ok:
            ok_count += 1
            print(f"  [{name}] OK - {url}")
        else:
            print(f"  [{name}] FAIL - {msg}")
    print("=" * 60)
    print(f"结果: {ok_count}/{len(WEBSITES)} 平台登录成功")
    return ok_count == len(WEBSITES)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    success = test_login(sys.argv[1], sys.argv[2])
    sys.exit(0 if success else 1)

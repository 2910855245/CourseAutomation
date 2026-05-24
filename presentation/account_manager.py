"""
账号管理模块
功能：多账号管理，统一data目录结构
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from datetime import datetime
from typing import Any, Dict, List

import httpx

from config import (
    ACCOUNTS_DIR,
    LOGS_DIR,
    WEBSITES,
    get_account_config_path,
    get_account_cookies_dir,
    get_account_cookies_path,
    get_account_courses_dir,
    get_account_dir,
    get_account_last_play_path,
    get_account_log_path,
    get_account_records_dir,
    set_current_account,
)
from infrastructure.rich_ui import console


class AccountConfig:
    """账号配置管理器"""
    
    def __init__(self):
        os.makedirs(ACCOUNTS_DIR, exist_ok=True)
        os.makedirs(LOGS_DIR, exist_ok=True)
    
    def _load_global_state(self) -> Dict[str, Any]:
        """加载全局状态"""
        state_path = os.path.join(ACCOUNTS_DIR, ".global_state.json")
        if os.path.exists(state_path):
            try:
                with open(state_path, encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                console.print(f"[yellow]加载全局状态失败: {e}[/yellow]")
        return {}
    
    def _save_global_state(self, state: Dict[str, Any]):
        """保存全局状态"""
        state_path = os.path.join(ACCOUNTS_DIR, ".global_state.json")
        with open(state_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    
    def set_last_state(self, state: str):
        """设置上次状态"""
        global_state = self._load_global_state()
        global_state["last_state"] = state
        global_state["last_state_saved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save_global_state(global_state)
    
    def get_last_state(self) -> str:
        """获取上次状态"""
        global_state = self._load_global_state()
        return global_state.get("last_state", "login")
    
    def set_current_account(self, username: str):
        """设置当前账号"""
        set_current_account(username)
        global_state = self._load_global_state()
        global_state["current_account"] = username
        self._save_global_state(global_state)
    
    def get_current_username(self) -> str:
        """获取当前账号的用户名"""
        global_state = self._load_global_state()
        return global_state.get("current_account", "")
    
    def _ensure_account_folder(self, username: str):
        """确保账号文件夹及其子文件夹存在"""
        account_dir = get_account_dir(username)
        os.makedirs(account_dir, exist_ok=True)
        os.makedirs(get_account_cookies_dir(username), exist_ok=True)
        os.makedirs(get_account_courses_dir(username), exist_ok=True)
        os.makedirs(get_account_records_dir(username), exist_ok=True)
    
    def _load_account_config(self, username: str) -> Dict[str, Any]:
        """加载账号配置"""
        config_path = get_account_config_path(username)
        if os.path.exists(config_path):
            try:
                with open(config_path, encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                console.print(f"[yellow]加载账号配置失败: {e}[/yellow]")
        return {
            "username": username,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_login": None,
            "is_first_login": True
        }
    
    def _save_account_config(self, username: str, config: Dict[str, Any]):
        """保存账号配置"""
        self._ensure_account_folder(username)
        config_path = get_account_config_path(username)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    
    def set_student_name(self, username: str, student_name: str):
        """保存学生姓名到账号配置"""
        config = self._load_account_config(username)
        config["student_name"] = student_name
        self._save_account_config(username, config)
    
    def get_student_name(self, username: str) -> str:
        """从账号配置获取学生姓名"""
        config = self._load_account_config(username)
        return config.get("student_name", "")
    
    def is_first_login(self, username: str) -> bool:
        """检查当前平台是不是第一次登录"""
        from config import CURRENT_WEBSITE
        website_name = WEBSITES.get(CURRENT_WEBSITE, {}).get("name", "default")
        
        courses_dir = get_account_courses_dir(username)
        records_dir = get_account_records_dir(username)
        
        has_courses = os.path.exists(courses_dir) and len(os.listdir(courses_dir)) > 0
        has_records = os.path.exists(records_dir) and len(os.listdir(records_dir)) > 0
        
        # 如果当前平台已经有数据，不是首次登录
        if has_courses or has_records:
            return False
        
        # 检查是否已经在该平台初始化过
        config = self._load_account_config(username)
        initialized_platforms = config.get("initialized_platforms", [])
        if website_name in initialized_platforms:
            return False
        
        return True
    
    def set_first_login_done(self, username: str):
        """标记当前平台首次登录完成"""
        from config import CURRENT_WEBSITE
        website_name = WEBSITES.get(CURRENT_WEBSITE, {}).get("name", "default")
        
        config = self._load_account_config(username)
        config["is_first_login"] = False
        config["first_login_done_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 记录已初始化的平台
        initialized_platforms = config.get("initialized_platforms", [])
        if website_name not in initialized_platforms:
            initialized_platforms.append(website_name)
        config["initialized_platforms"] = initialized_platforms
        
        self._save_account_config(username, config)
    
    def save_platform_passwords(self, username: str, platform_passwords: Dict[int, str]):
        """保存每个平台的独立密码到账号配置"""
        config = self._load_account_config(username)
        # 将 int key 转为 str key 以兼容 JSON
        stored = {str(k): v for k, v in platform_passwords.items()}
        # 合并而非覆盖：保留之前已保存的平台密码
        existing = config.get("platform_passwords", {})
        existing.update(stored)
        config["platform_passwords"] = existing
        config["platform_passwords_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save_account_config(username, config)
    
    def load_platform_passwords(self, username: str) -> Dict[int, str]:
        """加载每个平台的独立密码"""
        config = self._load_account_config(username)
        stored = config.get("platform_passwords", {})
        # 将 str key 转回 int key
        return {int(k): v for k, v in stored.items()}
    
    def log_debug_info(self, username: str, message: str, level: str = "INFO"):
        """保存调试日志"""
        try:
            log_path = get_account_log_path(username)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_line = f"[{timestamp}] [{level}] {message}\n"
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(log_line)
        except Exception as e:
            console.print(f"[yellow]写入日志失败: {e}[/yellow]")
    
    def get_accounts(self) -> List[Dict[str, Any]]:
        """获取所有账号列表"""
        accounts = []
        if os.path.exists(ACCOUNTS_DIR):
            for username in os.listdir(ACCOUNTS_DIR):
                account_dir = os.path.join(ACCOUNTS_DIR, username)
                # 检查是否是有效的账号目录（包含 config.json）
                if os.path.isdir(account_dir) and os.path.exists(os.path.join(account_dir, "config.json")):
                    config = self._load_account_config(username)
                    accounts.append({
                        "username": username,
                        "last_login": config.get("last_login", "从未登录"),
                        "created_at": config.get("created_at")
                    })
        accounts.sort(key=lambda x: x.get("last_login") or "", reverse=True)
        return accounts
    
    def get_last_login_account(self) -> Dict[str, Any]:
        """获取最近登录的账号"""
        accounts = self.get_accounts()
        return accounts[0] if accounts else None
    
    def add_account(self, username: str, session):
        """添加账号（保存Cookie）"""
        self._ensure_account_folder(username)
        
        # 保存当前平台的Cookie
        cookies = []
        for cookie in session.cookies:
            cookies.append({
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path
            })
        
        # 使用当前平台名称保存
        from config import CURRENT_WEBSITE
        website_name = WEBSITES.get(CURRENT_WEBSITE, {}).get("name", "default")
        cookies_path = get_account_cookies_path(username, website_name)
        
        with open(cookies_path, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        
        config = self._load_account_config(username)
        config["last_login"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save_account_config(username, config)
        
        self.set_current_account(username)
    
    def delete_account(self, username: str) -> bool:
        """删除账号"""
        account_dir = get_account_dir(username)
        if os.path.exists(account_dir):
            try:
                shutil.rmtree(account_dir)
                return True
            except Exception as e:
                return False
        return False
    
    def load_account_cookie(self, username: str, session) -> bool:
        """加载当前平台的账号Cookie"""
        from config import CURRENT_WEBSITE
        website_name = WEBSITES.get(CURRENT_WEBSITE, {}).get("name", "default")
        cookies_path = get_account_cookies_path(username, website_name)
        
        if not os.path.exists(cookies_path):
            return False
        
        try:
            with open(cookies_path, encoding='utf-8') as f:
                cookies = json.load(f)
            
            session.cookies.clear()
            for cookie in cookies:
                session.cookies.set(
                    name=cookie["name"],
                    value=cookie["value"],
                    domain=cookie.get("domain", ""),
                    path=cookie.get("path", "/")
                )
            return True
        except Exception as e:
            console.print(f"[yellow]加载Cookie失败: {e}[/yellow]")
            return False
    
    def save_account_cookie(self, username: str, session):
        """保存当前平台的账号Cookie"""
        self._ensure_account_folder(username)
        
        cookies = []
        for cookie in session.cookies:
            cookies.append({
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path
            })
        
        from config import CURRENT_WEBSITE
        website_name = WEBSITES.get(CURRENT_WEBSITE, {}).get("name", "default")
        cookies_path = get_account_cookies_path(username, website_name)
        
        with open(cookies_path, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        
        config = self._load_account_config(username)
        config["last_login"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save_account_config(username, config)
    
    def save_last_play(self, username: str, play_info: Dict[str, Any]):
        """保存最后播放记录"""
        self._ensure_account_folder(username)
        last_play_path = get_account_last_play_path(username)
        play_info["saved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(last_play_path, 'w', encoding='utf-8') as f:
            json.dump(play_info, f, ensure_ascii=False, indent=2)
    
    def load_last_play(self, username: str) -> Dict[str, Any]:
        """加载最后播放记录"""
        last_play_path = get_account_last_play_path(username)
        if os.path.exists(last_play_path):
            try:
                with open(last_play_path, encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                console.print(f"[yellow]加载播放记录失败: {e}[/yellow]")
        return {}


class SuwanUser:
    """已登录用户的操作"""
    
    def __init__(self, base_url: str, session: httpx.Client = None):
        self.base_url = base_url.rstrip("/")
        self.session = session or httpx.Client(timeout=httpx.Timeout(30.0), verify=False)
    
    def logout(self) -> Dict[str, Any]:
        """退出登录（仅本地退出）"""
        try:
            self.session.cookies.clear()
            return {"success": True, "message": "已退出登录"}
        except Exception as e:
            return {"success": False, "message": f"退出异常: {e}"}
    
    def logout_server(self) -> Dict[str, Any]:
        """调用服务器API退出登录"""
        url = f"{self.base_url}/user/logout"
        try:
            resp = self.session.get(url, follow_redirects=False)
            self.session.cookies.clear()
            if resp.status_code in (200, 302):
                return {"success": True, "message": "已从服务器退出登录"}
            else:
                return {"success": False, "message": f"退出异常，状态码 {resp.status_code}"}
        except httpx.RequestError as e:
            return {"success": False, "message": f"请求失败: {e}"}

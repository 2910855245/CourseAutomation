"""
学习通 HTTP 会话管理

基于 rnet 模拟浏览器 TLS 指纹（随机轮换），绕过学习通 WAF。
支持 cookie 登录和账号密码登录。
"""
import json
import random
from loguru import logger

from rnet import BlockingClient, Impersonate



class CachedResponse:
    """rnet 响应包装器 — 缓存 body，支持多次读取

    rnet 的 Rust 后端只允许消费 response body 一次。
    此包装器在首次读取时缓存 body 文本和 JSON，后续调用直接返回缓存。
    """

    def __init__(self, rnet_resp):
        self._resp = rnet_resp
        self._text_cache = None
        self._json_cache = None
        self._text_consumed = False

    @property
    def status_code(self):
        # rnet 返回 StatusCode 类型（非 int），需转换才能与整数比较
        sc = self._resp.status_code
        if isinstance(sc, int):
            return sc
        return sc.as_int()

    @property
    def url(self):
        return self._resp.url

    @property
    def cookies(self):
        return self._resp.cookies

    @property
    def headers(self):
        return self._resp.headers

    def text(self):
        if not self._text_consumed:
            self._text_cache = self._resp.text()
            self._text_consumed = True
        return self._text_cache

    def json(self):
        if self._json_cache is None:
            # 始终通过 text() 读取，避免 rnet 原生 json() 消费 body 失败
            text = self.text()
            if text:
                self._json_cache = json.loads(text)
            else:
                self._json_cache = {}
        return self._json_cache

# rnet Impersonate 枚举 → User-Agent 映射
_BROWSER_PROFILES = [
    # Chrome
    (Impersonate.Chrome110, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.5481.178 Safari/537.36'),
    (Impersonate.Chrome116, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.5845.188 Safari/537.36'),
    (Impersonate.Chrome119, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.6045.199 Safari/537.36'),
    (Impersonate.Chrome120, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.225 Safari/537.36'),
    (Impersonate.Chrome124, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.119 Safari/537.36'),
    (Impersonate.Chrome131, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.140 Safari/537.36'),
    (Impersonate.Chrome136, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.7103.93 Safari/537.36'),
    # Edge
    (Impersonate.Edge101, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.74 Safari/537.36 Edg/99.0.1150.55'),
    (Impersonate.Edge131, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0'),
    # Safari
    (Impersonate.Safari15_3, 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.3 Safari/605.1.15'),
    (Impersonate.Safari15_5, 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.5 Safari/605.1.15'),
    (Impersonate.Safari17_0, 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'),
    (Impersonate.Safari18_2, 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15'),
    # Firefox
    (Impersonate.Firefox128, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0'),
    (Impersonate.Firefox135, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0'),
]


def _random_profile():
    """随机选择一个浏览器指纹模板"""
    return random.choice(_BROWSER_PROFILES)


class ChaoxingSession:
    """学习通 HTTP 会话（基于 rnet）"""

    def __init__(self, cookie_str: str = ''):
        self.cookie_str = cookie_str
        self.cookies = self._parse_cookies(cookie_str) if cookie_str else {}
        self.uid = self.cookies.get('UID', self.cookies.get('_uid', ''))
        self.fid = self.cookies.get('fid', '')
        self._session = None
        self._username = ''
        self._password = ''
        # 随机指纹
        self._impersonate, self.UA = _random_profile()

    @staticmethod
    def _parse_cookies(cookie_str: str) -> dict:
        """解析 cookie 字符串为字典"""
        cookies = {}
        for item in cookie_str.split(';'):
            if '=' in item:
                k, v = item.strip().split('=', 1)
                cookies[k] = v
        return cookies

    def _ensure_session(self):
        """延迟初始化 rnet 会话"""
        if self._session is None:
            self._session = BlockingClient(impersonate=self._impersonate)
            logger.info(f"rnet 会话初始化 impersonate={str(self._impersonate)}")

    def login(self, username: str, password: str) -> bool:
        """账号密码登录学习通

        通过 passport2.chaoxing.com/fanyalogin 接口登录，
        成功后自动设置 cookie、uid、fid。
        """
        self._ensure_session()
        self._username = username
        self._password = password

        url = 'https://passport2.chaoxing.com/fanyalogin'
        form_data = (
            f'fid=-1&uname={username}&password={password}'
            f'&refer=https://i.chaoxing.com&t=true&forbidotherlogin=0&validate='
        )

        try:
            resp = self._session.post(url, body=form_data.encode(), headers={
                'User-Agent': self.UA,
                'Content-Type': 'application/x-www-form-urlencoded',
                'Referer': 'https://passport2.chaoxing.com/login',
            }, timeout=15)
            resp = CachedResponse(resp)
            result = resp.json()

            if result.get('result') == 1 or result.get('status') is True:
                # 登录成功，从 response cookies 构建 cookie 字典
                # rnet 的 cookies 是 list[Cookie]，需兼容 httpx 的 Cookies 对象
                cookie_dict = {}
                try:
                    cookies = resp.cookies
                    if hasattr(cookies, 'items'):
                        for name, value in cookies.items():
                            cookie_dict[name] = value
                    else:
                        for c in cookies:
                            cookie_dict[c.name] = c.value
                except Exception:
                    pass

                self.cookies = cookie_dict
                self.cookie_str = '; '.join(f'{k}={v}' for k, v in cookie_dict.items())
                self.uid = cookie_dict.get('UID', cookie_dict.get('_uid', ''))
                self.fid = cookie_dict.get('fid', '')

                # 如果 uid 为空，尝试从其他接口获取
                if not self.uid:
                    user_info = self.get_user_info()
                    self.uid = user_info.get('uid', '')

                logger.info(f"学习通登录成功 username={username} uid={self.uid}")
                return True
            else:
                msg = result.get('msg', '登录失败')
                logger.warning(f"学习通登录失败 username={username} msg={msg}")
                return False

        except Exception as e:
            logger.error(f"学习通登录异常 username={username} error={str(e)}")
            return False

    def get(self, url: str, referer: str = None, extra_headers: dict = None, **kwargs):
        """GET 请求"""
        self._ensure_session()
        headers = {
            'Cookie': self.cookie_str,
            'User-Agent': self.UA,
            'Accept': '*/*',
        }
        if referer:
            headers['Referer'] = referer
        if extra_headers:
            headers.update(extra_headers)
        # 合并用户传入的 headers
        if 'headers' in kwargs:
            headers.update(kwargs.pop('headers'))
        resp = self._session.get(url, headers=headers, **kwargs)
        return CachedResponse(resp)

    def post(self, url: str, data=None, referer: str = None, extra_headers: dict = None, **kwargs):
        """POST 请求"""
        self._ensure_session()
        headers = {
            'Cookie': self.cookie_str,
            'User-Agent': self.UA,
            'Accept': '*/*',
        }
        if referer:
            headers['Referer'] = referer
        if extra_headers:
            headers.update(extra_headers)
        # 将 data dict 转为 urlencoded bytes
        body = None
        if data is not None:
            if isinstance(data, dict):
                import urllib.parse
                body = urllib.parse.urlencode(data).encode()
                headers.setdefault('Content-Type', 'application/x-www-form-urlencoded')
            elif isinstance(data, (bytes, bytearray)):
                body = data
            elif isinstance(data, str):
                body = data.encode()
        # 合并用户传入的 headers
        if 'headers' in kwargs:
            headers.update(kwargs.pop('headers'))
        resp = self._session.post(url, body=body, headers=headers, **kwargs)
        return CachedResponse(resp)

    def get_json(self, url: str, **kwargs):
        """GET 请求并返回 JSON"""
        resp = self.get(url, **kwargs)
        return resp.json()

    def verify(self) -> bool:
        """验证 cookie 是否有效"""
        try:
            data = self.get_json('https://sso.chaoxing.com/apis/login/userLogin4Uname.do')
            name = data.get('msg', {}).get('name', '')
            if name:
                logger.info(f"学习通cookie验证成功 user={name} uid={self.uid}")
                return True
            return False
        except Exception as e:
            logger.warning(f"学习通cookie验证失败 error={str(e)}")
            return False

    def get_user_info(self) -> dict:
        """获取用户信息"""
        try:
            data = self.get_json('https://sso.chaoxing.com/apis/login/userLogin4Uname.do')
            msg = data.get('msg', {})
            return {
                'name': msg.get('name', '未知'),
                'uid': self.uid,
                'fid': self.fid,
                'school_name': msg.get('schoolname', ''),
                'student_code': msg.get('uname', ''),
                'phone': msg.get('phone', ''),
            }
        except Exception as e:
            logger.warning(f"获取用户信息失败 error={str(e)}")
            return {'name': '未知', 'uid': self.uid, 'fid': self.fid, 'school_name': '', 'student_code': '', 'phone': ''}

    @staticmethod
    def from_cookie_file(path: str) -> 'ChaoxingSession':
        """从文件加载 cookie"""
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        # JSON 格式
        if content.strip().startswith('{') or content.strip().startswith('['):
            data = json.loads(content)
            if isinstance(data, dict):
                cookie_str = '; '.join(f'{k}={v}' for k, v in data.items())
            else:
                cookie_str = '; '.join(f'{c["name"]}={c["value"]}' for c in data)
            return ChaoxingSession(cookie_str)

        # Netscape 格式
        cookies = {}
        for line in content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) >= 7:
                cookies[parts[5]] = parts[6]
        cookie_str = '; '.join(f'{k}={v}' for k, v in cookies.items())
        return ChaoxingSession(cookie_str)


class SessionPool:
    """线程安全的会话池 — 为并发任务提供独立 session"""

    def __init__(self, username: str, password: str, pool_size: int = 8):
        import queue
        self._queue = queue.Queue()
        self._username = username
        self._password = password
        self._pool_size = pool_size
        self._initialized = False

    def _init_pool(self):
        """延迟初始化：创建多个 session 并登录"""
        if self._initialized:
            return
        self._initialized = True
        logger.info(f"初始化会话池 size={self._pool_size}")
        for i in range(self._pool_size):
            try:
                s = ChaoxingSession()
                if s.login(self._username, self._password):
                    self._queue.put(s)
                else:
                    logger.warning(f"会话池初始化登录失败 index={i}")
            except Exception as e:
                logger.warning(f"会话池初始化异常 index={i} error={str(e)}")
        logger.info(f"会话池初始化完成 actual_size={self._queue.qsize()}")

    def get(self) -> ChaoxingSession:
        """获取一个 session（阻塞等待）"""
        self._init_pool()
        return self._queue.get(timeout=60)

    def put(self, session: ChaoxingSession):
        """归还 session"""
        self._queue.put(session)

    def size(self) -> int:
        return self._queue.qsize()

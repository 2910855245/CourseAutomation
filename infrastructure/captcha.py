import random
import string

from config import get_random_user_agent
from infrastructure.dashboard import DashboardDisplay
from infrastructure.http_session import create_sync_client, safe_json_parse

_ocr_instance = None

def _get_ocr():
    global _ocr_instance
    if _ocr_instance is None:
        import ddddocr
        _ocr_instance = ddddocr.DdddOcr(show_ad=False)
    return _ocr_instance

class ImageCaptchaSolver:
    """图形验证码解析器"""
    def __init__(self, base_url: str, cookie_str: str = None, cookie_dict: dict = None, session=None):
        """初始化图形验证码解析器

        Args:
            base_url: 基础URL
            cookie_str: Cookie字符串（可选）
            cookie_dict: Cookie字典（可选）
            session: 可选，共享session（用于验证码session与请求session保持一致）
        """
        self.base_url = base_url.rstrip('/')
        if session is not None:
            self.session = session
        else:
            self.session = create_sync_client(base_url)
        self.session.headers.update({'User-Agent': get_random_user_agent()})
        if cookie_str:
            self._set_cookie_from_string(cookie_str)  # 从字符串设置Cookie
        elif cookie_dict:
            self.session.cookies.update(cookie_dict)  # 从字典设置Cookie
        self.ocr = _get_ocr()
        self._dash = DashboardDisplay.instance()

    def _set_cookie_from_string(self, cookie_str: str):
        """从字符串设置Cookie
        
        Args:
            cookie_str: Cookie字符串，格式为 "key1=value1; key2=value2"
        """
        for item in cookie_str.split(';'):  # 按分号分割Cookie
            item = item.strip()  # 去除首尾空格
            if not item or '=' not in item:  # 跳过空项或不含等号的项
                continue
            k, v = item.split('=', 1)  # 分割键值对
            self.session.cookies.set(k.strip(), v.strip())  # 设置Cookie

    @staticmethod
    def _random_str(length: int = 8) -> str:
        """生成随机字符串
        
        Args:
            length: 字符串长度，默认8
            
        Returns:
            随机字符串
        """
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

    def download(self) -> bytes:
        """下载验证码图片
        
        Returns:
            验证码图片的二进制数据
        """
        url = f"{self.base_url}/service/code"  # 验证码URL
        resp = self.session.get(url, params={'r': self._random_str()})  # 添加随机参数防止缓存
        resp.raise_for_status()  # 检查响应状态
        return resp.content  # 返回图片二进制数据

    def recognize(self, img_bytes: bytes) -> str:
        """识别验证码
        
        Args:
            img_bytes: 验证码图片的二进制数据
            
        Returns:
            识别出的验证码字符串
        """
        return self.ocr.classification(img_bytes).strip()  # 使用OCR识别验证码并去除首尾空格

    def solve(self, auto_underscore: bool = True) -> str:
        """解决验证码
        
        Args:
            auto_underscore: 是否自动添加下划线，默认True
            
        Returns:
            处理后的验证码字符串
        """
        img_bytes = self.download()  # 下载验证码图片
        code = self.recognize(img_bytes)  # 识别验证码
        if auto_underscore:
            code += '_'  # 自动添加下划线
        self._dash.debug(f"[captcha] 图形验证码识别结果: {code}")  # 打印识别结果
        return code

class XCaptchaSolver:
    """点选验证码解析器"""
    def __init__(self, base_url: str, ak: str, verify: str = None):
        """初始化点选验证码解析器
        
        Args:
            base_url: 点选验证码API地址
            ak: API密钥
            verify: 验证令牌（可选）
        """
        self.base_url = base_url
        self.ak = ak
        self.verify = verify
        self.session = create_sync_client(base_url)
        self.session.headers.update({'User-Agent': get_random_user_agent()})
        self.ocr = _get_ocr()
        self.key = None  # 验证码key
        self.img_url = None  # 验证码图片URL
        self._dash = DashboardDisplay.instance()

    def get_token(self):
        """获取验证码token
        
        Returns:
            API响应数据
        """
        resp = self.session.get(self.base_url, params={'act': 'token', 'ak': self.ak})  # 请求token
        resp.raise_for_status()  # 检查响应状态
        data = safe_json_parse(resp)  # 安全解析JSON
        self.key = data['key']  # 提取key
        self.img_url = data['img'] + '?k=' + self.key  # 构建图片URL
        self._dash.debug(f"[captcha] 点选验证码获取token: key={self.key}")  # 打印token
        return data

    def get_icons(self):
        """获取验证码图标列表
        
        Returns:
            图标列表
        """
        resp = self.session.post(self.base_url, data={'act': 'icon', 'key': self.key})  # 请求图标
        resp.raise_for_status()  # 检查响应状态
        data = safe_json_parse(resp)  # 安全解析JSON
        self._dash.debug(f"[captcha] 点选验证码图标列表: {data['captcha_icon']}")  # 打印图标列表
        return data['captcha_icon']

    def download_image(self):
        """下载验证码图片
        
        Returns:
            验证码图片的二进制数据
        """
        resp = self.session.get(self.img_url)  # 下载图片
        resp.raise_for_status()  # 检查响应状态
        return resp.content  # 返回图片二进制数据

    def recognize_clicks(self, img_bytes):
        """识别点击坐标
        
        Args:
            img_bytes: 验证码图片的二进制数据
            
        Returns:
            点击坐标列表
        """
        points = self.ocr.click(img_bytes)  # 使用OCR识别点击坐标
        self._dash.debug(f"[captcha] ddddocr 识别点击坐标: {points}")  # 打印坐标
        return points

    def format_ivalue(self, points):
        """格式化坐标为ivalue
        
        Args:
            points: 点击坐标列表
            
        Returns:
            格式化后的ivalue字符串
        """
        coords = [f"{p['x']}-{p['y']}" for p in points]  # 格式化坐标
        return "||".join(coords)  # 用||连接坐标

    def submit(self, ivalue):
        """提交验证码
        
        Args:
            ivalue: 格式化后的坐标字符串
            
        Returns:
            提交响应
        """
        data = {'act': 'check', 'ivalue': ivalue, 'key': self.key}  # 准备提交数据
        if self.verify:
            data['verify'] = self.verify  # 添加验证令牌
        self._dash.debug(f"[captcha] 提交点选验证码 ivalue: {ivalue}")  # 打印ivalue
        resp = self.session.post(self.base_url, data=data)  # 提交验证
        resp.raise_for_status()  # 检查响应状态
        result = safe_json_parse(resp)  # 安全解析JSON
        self._dash.debug(f"[captcha] 点选验证提交响应: {result}")  # 打印响应
        return result

    def solve(self) -> str:
        """解决点选验证码
        
        Returns:
            成功的ivalue字符串
            
        Raises:
            Exception: 验证失败时抛出异常
        """
        self.get_token()  # 获取token
        self.get_icons()  # 获取图标
        img_bytes = self.download_image()  # 下载图片
        points = self.recognize_clicks(img_bytes)  # 识别坐标
        ivalue = self.format_ivalue(points)  # 格式化坐标
        result = self.submit(ivalue)  # 提交验证
        if result.get('status') == 1:  # 验证成功
            return ivalue
        else:  # 验证失败
            raise Exception(f"点选验证失败: {result.get('msg')}")

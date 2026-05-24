import base64
import io
import math
import random
import threading
import time
import uuid
from typing import Optional, Tuple

from loguru import logger
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from api.redis_client import redis_client

# 去除易混淆字符
_CHARS = "2345678ABCDEFGHJKMNPQRTUVWXYabcdefghjkmnpqrtuvwxy"
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
]


def _find_font() -> Optional[str]:
    for path in _FONT_CANDIDATES:
        try:
            ImageFont.truetype(path, 32)
            return path
        except OSError:
            continue
    return None


_FONT_PATH = _find_font()


class CaptchaService:
    """图片验证码，Redis做存储，降级为内存"""

    def __init__(self):
        self._memory_store: dict = {}
        self._lock = threading.Lock()

    def _cleanup_memory(self):
        now = time.time()
        with self._lock:
            expired = [k for k, v in self._memory_store.items() if now > v["exp"]]
            for k in expired:
                del self._memory_store[k]
            # 只清理过期，不能 clear() —— 否则会把有效验证码全部干掉
            if len(self._memory_store) > 5000:
                now_ts = time.time()
                stale = [k for k, v in self._memory_store.items() if now_ts > v["exp"]]
                for k in stale:
                    del self._memory_store[k]

    def _set(self, token: str, code: str, ttl: int = 300):
        if redis_client.available:
            redis_client.set(f"captcha:{token}", code.upper(), ex=ttl)
        else:
            with self._lock:
                self._memory_store[token] = {"code": code.upper(), "exp": time.time() + ttl}

    def _get_and_delete(self, token: str) -> Optional[str]:
        if redis_client.available:
            val = redis_client.get(f"captcha:{token}")
            if val is not None:
                redis_client.delete(f"captcha:{token}")
                return val
            return None
        else:
            with self._lock:
                entry = self._memory_store.pop(token, None)
                if entry and time.time() < entry["exp"]:
                    return entry["code"]
            self._cleanup_memory()
            return None

    def _draw_text_with_font(self, draw, text, xy, font_size, color):
        """尝试用 truetype 字体，失败则用默认字体"""
        x, y = xy
        if _FONT_PATH:
            try:
                fnt = ImageFont.truetype(_FONT_PATH, font_size)
                draw.text((x, y), text, font=fnt, fill=color)
                return
            except Exception as e:
                pass
        draw.text((x, y), text, fill=color)

    def generate(self) -> Tuple[str, str]:
        """返回 (token, base64图片)"""
        code = ''.join(random.choice(_CHARS) for _ in range(4))
        token = uuid.uuid4().hex[:12]
        self._set(token, code, ttl=300)

        # --- 绘制图片 ---
        width, height = 140, 52
        img = Image.new("RGB", (width, height), (255, 255, 255))
        draw = ImageDraw.Draw(img)

        # 背景噪点
        for _ in range(random.randint(200, 400)):
            x = random.randint(0, width - 1)
            y = random.randint(0, height - 1)
            c = random.randint(180, 240)
            draw.point((x, y), fill=(c, c, c))

        # 干扰线 - 随机曲线
        for _ in range(random.randint(2, 4)):
            pts = []
            start_x = random.randint(-20, 20)
            start_y = random.randint(5, height - 5)
            for seg in range(4):
                pts.append((start_x + seg * 45 + random.randint(-10, 10),
                           start_y + random.randint(-15, 15)))
            # 画折线
            for i in range(len(pts) - 1):
                lc = random.randint(80, 160)
                draw.line([pts[i], pts[i + 1]], fill=(lc, lc, lc), width=random.randint(1, 2))

        # 正弦扭曲（逐列像素偏移）
        img_array = img.load()
        amplitude = random.randint(3, 6)
        period = random.randint(20, 35)
        phase = random.randint(0, 10)
        for y in range(height):
            offset = int(amplitude * math.sin(2 * math.pi * (y + phase) / period))
            row = [img_array[x, y] for x in range(width)]
            for x in range(width):
                src_x = x + offset
                if 0 <= src_x < width:
                    img_array[x, y] = row[src_x]

        # 重新获取 draw（因为像素操作后需要刷新）
        draw = ImageDraw.Draw(img)

        # 画字符（每个字符独立旋转+颜色）
        char_colors = [
            (random.randint(0, 80), random.randint(0, 80), random.randint(140, 255)),  # 蓝
            (random.randint(140, 255), random.randint(0, 60), random.randint(0, 60)),  # 红
            (random.randint(0, 80), random.randint(120, 200), random.randint(0, 80)),  # 绿
            (random.randint(160, 220), random.randint(80, 160), random.randint(0, 40)),  # 橙
        ]
        random.shuffle(char_colors)

        for i, ch in enumerate(code):
            char_img = Image.new("RGBA", (36, 48), (0, 0, 0, 0))
            char_draw = ImageDraw.Draw(char_img)
            font_size = random.randint(28, 34)
            self._draw_text_with_font(char_draw, ch, (3, 2), font_size, char_colors[i])

            # 旋转
            angle = random.randint(-30, 30)
            char_img = char_img.rotate(angle, expand=True, fillcolor=(0, 0, 0, 0))

            # 粘贴到主图
            x_offset = 8 + i * 32 + random.randint(-3, 3)
            y_offset = random.randint(-2, 6)
            img.paste(char_img, (x_offset, y_offset), char_img)

        # 轻微模糊
        img = img.filter(ImageFilter.GaussianBlur(radius=0.5))

        # 转 base64
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

        logger.info(f"captcha_generated token={token}")
        return token, b64

    def verify(self, token: str, user_answer: str) -> bool:
        """验证用户输入，不区分大小写，一次性使用"""
        if not token or not user_answer:
            return False
        user_val = user_answer.strip().upper()
        if not user_val or len(user_val) > 10:
            return False

        correct = self._get_and_delete(token)
        if correct is None:
            logger.warning(f"captcha_token_invalid_or_used token={token}")
            return False
        if user_val != correct:
            logger.warning(f"captcha_wrong_answer expected={correct} got={user_val}")
            return False

        logger.info(f"captcha_verified token={token}")
        return True


captcha_service = CaptchaService()

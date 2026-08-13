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
    # Windows
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/verdanab.ttf",
    "C:/Windows/Fonts/calibrib.ttf",
    "C:/Windows/Fonts/tahomabd.ttf",
    # Linux
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

        # --- OCR-resistant captcha design ---
        width, height = 200, 60
        bg_color = (248, 248, 252)
        img = Image.new("RGB", (width, height), bg_color)
        draw = ImageDraw.Draw(img)

        # 网格背景（干扰OCR预处理，深色混淆）
        grid_color = (180, 185, 195)
        for gx in range(0, width, 8):
            draw.line([(gx, 0), (gx, height)], fill=grid_color, width=1)
        for gy in range(0, height, 8):
            draw.line([(0, gy), (width, gy)], fill=grid_color, width=1)

        # 2条穿过文字的干扰线（破坏OCR边缘检测）
        for _ in range(2):
            pts = []
            for seg in range(6):
                pts.append((seg * 42 + random.randint(-8, 8),
                           random.randint(8, height - 8)))
            for i in range(len(pts) - 1):
                lc = random.randint(80, 140)
                draw.line([pts[i], pts[i + 1]], fill=(lc, lc, lc), width=random.randint(1, 2))

        # 强正弦扭曲（抗OCR核心手段）
        img_array = img.load()
        amplitude = random.randint(3, 6)
        period = random.randint(22, 34)
        phase = random.randint(0, 10)
        for y in range(height):
            offset = int(amplitude * math.sin(2 * math.pi * (y + phase) / period))
            row = [img_array[x, y] for x in range(width)]
            for x in range(width):
                src_x = x + offset
                if 0 <= src_x < width:
                    img_array[x, y] = row[src_x]

        draw = ImageDraw.Draw(img)

        # 画字符：小字号 + 相近深色 + 重叠
        dark = random.randint(20, 60)
        colors = [
            (dark, dark, dark),
            (dark + random.randint(-10, 10), dark + random.randint(-10, 10), dark + random.randint(-10, 10)),
            (dark + random.randint(-10, 10), dark + random.randint(-10, 10), dark + random.randint(-10, 10)),
            (dark + random.randint(-10, 10), dark + random.randint(-10, 10), dark + random.randint(-10, 10)),
        ]
        base_x_positions = [14, 56, 98, 140]

        for i, ch in enumerate(code):
            char_img = Image.new("RGBA", (44, 50), (0, 0, 0, 0))
            char_draw = ImageDraw.Draw(char_img)
            font_size = random.randint(26, 34)
            self._draw_text_with_font(char_draw, ch, (3, 2), font_size, colors[i])

            angle = random.randint(-25, 25)
            char_img = char_img.rotate(angle, expand=True, fillcolor=(0, 0, 0, 0))

            x_offset = base_x_positions[i] + random.randint(-3, 3)
            y_offset = random.randint(4, 12)
            img.paste(char_img, (x_offset, y_offset), char_img)

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

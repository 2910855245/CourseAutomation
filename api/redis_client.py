from __future__ import annotations

import threading
import time
from functools import lru_cache
from typing import Optional

from loguru import logger

from config import settings

class RedisClient:
    """
    Redis 客户端，带优雅降级和自动重连。
    - 连接成功：所有功能正常
    - 连接失败：自动降级为内存模式，项目照常运行
    - 自动重连：每 60 秒尝试重新连接一次
    """

    def __init__(self):
        self._redis = None
        self._available = False
        self._lock = threading.Lock()
        self._last_connect_attempt = 0.0
        self._reconnect_interval = 60  # 重连间隔（秒）
        self._connect()

    def _connect(self):
        self._last_connect_attempt = time.time()
        try:
            import socket
            from urllib.parse import urlparse
            parsed = urlparse(settings.redis_url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 6379
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex((host, port))
            sock.close()
            if result != 0:
                raise ConnectionRefusedError(f"Redis port {host}:{port} not reachable")
        except Exception as e:
            self._available = False
            self._redis = None
            logger.warning("Redis 连接失败 reason=端口不可达")
            logger.info("Redis 不可用，降级为内存/SQLite 模式 reason=端口不可达")
            return
        try:
            import redis
            self._redis = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
                retry_on_timeout=False,
            )
            self._redis.ping()
            self._available = True
            logger.info(f"Redis 连接成功 url={settings.redis_url}")
        except Exception as e:
            self._available = False
            self._redis = None
            logger.warning(f"Redis 连接失败 reason={str(e)}")
            logger.info(f"Redis 不可用，降级为内存/SQLite 模式 reason={str(e)}")

    def _maybe_reconnect(self):
        """操作失败时尝试重连，每 _reconnect_interval 秒最多一次"""
        if self._available:
            return
        now = time.time()
        if now - self._last_connect_attempt < self._reconnect_interval:
            return
        with self._lock:
            if now - self._last_connect_attempt < self._reconnect_interval:
                return
            logger.info("尝试重新连接 Redis ...")
            self._connect()

    @property
    def available(self) -> bool:
        return self._available

    @property
    def client(self):
        return self._redis

    def health_check(self) -> dict:
        if not self._available:
            return {"status": "unavailable", "mode": "fallback"}
        try:
            self._redis.ping()
            info = self._redis.info("memory")
            return {
                "status": "connected",
                "mode": "redis",
                "used_memory": info.get("used_memory_human", "N/A"),
                "connected_clients": info.get("connected_clients", 0),
            }
        except Exception as e:
            self._available = False
            logger.warning(f"Redis health_check 失败 error={str(e)}")
            return {"status": "error", "mode": "fallback", "error": str(e)}

    def get(self, key: str) -> Optional[str]:
        if not self._available:
            self._maybe_reconnect()
            return None
        try:
            return self._redis.get(key)
        except Exception as e:
            logger.warning(f"Redis get 失败 key={key}")
            self._available = False
            self._maybe_reconnect()
            return None

    def set(self, key: str, value: str, ex: int = None) -> bool:
        if not self._available:
            self._maybe_reconnect()
            return False
        try:
            self._redis.set(key, value, ex=ex)
            return True
        except Exception as e:
            logger.warning(f"Redis set 失败 key={key}")
            self._available = False
            self._maybe_reconnect()
            return False

    def delete(self, key: str) -> bool:
        if not self._available:
            self._maybe_reconnect()
            return False
        try:
            self._redis.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Redis delete 失败 key={key}")
            self._available = False
            self._maybe_reconnect()
            return False

    def exists(self, key: str) -> bool:
        if not self._available:
            self._maybe_reconnect()
            return False
        try:
            return bool(self._redis.exists(key))
        except Exception as e:
            logger.warning(f"Redis exists 失败 key={key}")
            self._available = False
            self._maybe_reconnect()
            return False

    def incr(self, key: str) -> Optional[int]:
        if not self._available:
            self._maybe_reconnect()
            return None
        try:
            return self._redis.incr(key)
        except Exception as e:
            logger.warning(f"Redis incr 失败 key={key}")
            self._available = False
            self._maybe_reconnect()
            return None

    def expire(self, key: str, seconds: int) -> bool:
        if not self._available:
            self._maybe_reconnect()
            return False
        try:
            self._redis.expire(key, seconds)
            return True
        except Exception as e:
            logger.warning(f"Redis expire 失败 key={key}")
            self._available = False
            self._maybe_reconnect()
            return False

    def zadd(self, key: str, mapping: dict) -> Optional[int]:
        if not self._available:
            self._maybe_reconnect()
            return None
        try:
            return self._redis.zadd(key, mapping)
        except Exception as e:
            logger.warning(f"Redis zadd 失败 key={key}")
            self._available = False
            self._maybe_reconnect()
            return None

    def zrangebyscore(self, key: str, min_score: float, max_score: float):
        if not self._available:
            self._maybe_reconnect()
            return None
        try:
            return self._redis.zrangebyscore(key, min_score, max_score)
        except Exception as e:
            logger.warning(f"Redis zrangebyscore 失败 key={key}")
            self._available = False
            self._maybe_reconnect()
            return None

    def zremrangebyscore(self, key: str, min_score: float, max_score: float):
        if not self._available:
            self._maybe_reconnect()
            return None
        try:
            return self._redis.zremrangebyscore(key, min_score, max_score)
        except Exception as e:
            logger.warning(f"Redis zremrangebyscore 失败 key={key}")
            self._available = False
            self._maybe_reconnect()
            return None

    def zcard(self, key: str) -> Optional[int]:
        if not self._available:
            self._maybe_reconnect()
            return None
        try:
            return self._redis.zcard(key)
        except Exception as e:
            logger.warning(f"Redis zcard 失败 key={key}")
            self._available = False
            self._maybe_reconnect()
            return None

    def scan_keys(self, pattern: str, count: int = 1000) -> list:
        """扫描匹配 pattern 的 key，返回 [(key, value), ...]"""
        if not self._available:
            self._maybe_reconnect()
            return []
        try:
            result = []
            cursor = 0
            while True:
                cursor, keys = self._redis.scan(cursor, match=pattern, count=100)
                for k in keys:
                    v = self._redis.get(k)
                    result.append((k, v))
                if cursor == 0:
                    break
            return result
        except Exception as e:
            logger.warning(f"Redis scan_keys 失败 pattern={pattern}")
            self._available = False
            self._maybe_reconnect()
            return []

    # ── Pub/Sub ──

    def publish(self, channel: str, message: str) -> Optional[int]:
        """发布消息到频道"""
        if not self._available:
            self._maybe_reconnect()
            return None
        try:
            return self._redis.publish(channel, message)
        except Exception as e:
            logger.warning(f"Redis publish 失败 channel={channel}")
            self._available = False
            self._maybe_reconnect()
            return None

    def subscribe(self, *channels: str):
        """订阅频道，返回 pubsub 对象"""
        if not self._available:
            self._maybe_reconnect()
            return None
        try:
            pubsub = self._redis.pubsub()
            pubsub.subscribe(*channels)
            return pubsub
        except Exception as e:
            logger.warning(f"Redis subscribe 失败 channels={channels}")
            self._available = False
            self._maybe_reconnect()
            return None

    # ── Lua 脚本 ──

    def eval(self, script: str, numkeys: int, *args) -> any:
        """执行 Lua 脚本（原子操作）"""
        if not self._available:
            self._maybe_reconnect()
            return None
        try:
            return self._redis.eval(script, numkeys, *args)
        except Exception as e:
            logger.warning(f"Redis eval 失败 error={str(e)}")
            self._available = False
            self._maybe_reconnect()
            return None

    def rate_limit_lua(self, key: str, limit: int, window: int) -> bool:
        """Lua 原子限流：窗口内最多 limit 次请求"""
        # KEYS[1] = rate limit key
        # ARGV[1] = limit, ARGV[2] = window seconds, ARGV[3] = current timestamp
        script = """
        local key = KEYS[1]
        local limit = tonumber(ARGV[1])
        local window = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])
        redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
        local count = redis.call('ZCARD', key)
        if count < limit then
            redis.call('ZADD', key, now, now .. '-' .. math.random(100000))
            redis.call('EXPIRE', key, window)
            return 1
        end
        return 0
        """
        result = self.eval(script, 1, key, limit, window, time.time())
        return result == 1

    # ── Streams ──

    def xadd(self, stream: str, fields: dict, maxlen: int = 10000) -> Optional[str]:
        """向 Stream 追加消息"""
        if not self._available:
            self._maybe_reconnect()
            return None
        try:
            return self._redis.xadd(stream, fields, maxlen=maxlen)
        except Exception as e:
            logger.warning(f"Redis xadd 失败 stream={stream}")
            self._available = False
            self._maybe_reconnect()
            return None

    def xread(self, streams: dict, count: int = 10, block: int = 0):
        """从 Stream 读取消息"""
        if not self._available:
            self._maybe_reconnect()
            return None
        try:
            return self._redis.xread(streams, count=count, block=block)
        except Exception as e:
            logger.warning(f"Redis xread 失败 streams={streams}")
            self._available = False
            self._maybe_reconnect()
            return None

    def xlen(self, stream: str) -> Optional[int]:
        """获取 Stream 长度"""
        if not self._available:
            self._maybe_reconnect()
            return None
        try:
            return self._redis.xlen(stream)
        except Exception as e:
            logger.warning(f"Redis xlen 失败 stream={stream}")
            self._available = False
            self._maybe_reconnect()
            return None


@lru_cache
def get_redis() -> RedisClient:
    return RedisClient()


redis_client = get_redis()

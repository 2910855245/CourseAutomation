from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any, Dict

from loguru import logger

from api.redis_client import redis_client


RATE_LIMIT_ORDER_PER_USER = 30
RATE_LIMIT_ORDER_PER_USER_WINDOW = 60
RATE_LIMIT_ORDER_PER_IP = 100
RATE_LIMIT_ORDER_PER_IP_WINDOW = 60
RATE_LIMIT_SCAN_PER_IP = 200
RATE_LIMIT_SCAN_PER_IP_WINDOW = 60
MAX_SINGLE_ORDER = 999999.0
MIN_SINGLE_ORDER = 0.01
MAX_COURSES_PER_ORDER = 999


class RiskControl:

    def __init__(self):
        self._mem_counters: Dict[str, list] = defaultdict(list)
        self._mem_dedup: Dict[str, float] = {}
        self._mem_lock = threading.Lock()

    def _mem_rate_check(self, key: str, max_count: int, window_sec: int) -> bool:
        now = time.time()
        cutoff = now - window_sec
        with self._mem_lock:
            entries = self._mem_counters[key]
            filtered = [t for t in entries if t > cutoff]
            if not filtered:
                del self._mem_counters[key]
            else:
                self._mem_counters[key] = filtered
            if len(filtered) >= max_count:
                return False
            self._mem_counters.setdefault(key, []).append(now)
            return True

    def _mem_dedup_exists(self, key: str, ttl_sec: int = 86400) -> bool:
        now = time.time()
        with self._mem_lock:
            expire_at = self._mem_dedup.get(key, 0)
            if expire_at > now:
                return True
            self._mem_dedup[key] = now + ttl_sec
            if len(self._mem_dedup) > 10000:
                self._mem_dedup = {k: v for k, v in self._mem_dedup.items() if v > now}
            return False

    def check_rate_limit(self, key: str, max_count: int, window_sec: int) -> bool:
        if not redis_client.available:
            return self._mem_rate_check(key, max_count, window_sec)
        count = redis_client.incr(key)
        if count is None:
            return self._mem_rate_check(key, max_count, window_sec)
        if count == 1:
            redis_client.expire(key, window_sec)
        return count <= max_count

    def can_create_order(self, user_id: str = "", ip: str = "") -> Dict[str, Any]:
        if user_id:
            ok = self.check_rate_limit(
                f"ratelimit:order:{user_id}",
                RATE_LIMIT_ORDER_PER_USER,
                RATE_LIMIT_ORDER_PER_USER_WINDOW,
            )
            if not ok:
                return {"allowed": False, "reason": "下单频率过高，请稍后再试", "retry_after": RATE_LIMIT_ORDER_PER_USER_WINDOW}
        if ip:
            ok = self.check_rate_limit(
                f"ratelimit:order:{ip}",
                RATE_LIMIT_ORDER_PER_IP,
                RATE_LIMIT_ORDER_PER_IP_WINDOW,
            )
            if not ok:
                return {"allowed": False, "reason": "IP下单频率过高，请稍后再试", "retry_after": RATE_LIMIT_ORDER_PER_IP_WINDOW}
        return {"allowed": True, "reason": ""}

    def can_scan(self, ip: str = "") -> bool:
        if not ip:
            return True
        return self.check_rate_limit(
            f"ratelimit:scan:{ip}",
            RATE_LIMIT_SCAN_PER_IP,
            RATE_LIMIT_SCAN_PER_IP_WINDOW,
        )

    def can_order_course(self, user_id: str = "", course_id: str = "") -> bool:
        if not user_id or not course_id:
            return True
        key = f"order:dedup:{user_id}:{course_id}"
        if redis_client.available:
            if redis_client.exists(key):
                return False
            redis_client.set(key, "1", ex=86400)
            return True
        return not self._mem_dedup_exists(key)

    def validate_order_params(self, *, course_count: int = 0, order_amount: float = 0.0,
                               username: str = "") -> Dict[str, Any]:
        errors = []
        if not username or len(username.strip()) < 4:
            errors.append("学号格式不正确")
        if course_count < 1:
            errors.append("请至少选择一门课程")
        if course_count > MAX_COURSES_PER_ORDER:
            errors.append(f"单次最多选择{MAX_COURSES_PER_ORDER}门课程")
        if order_amount < MIN_SINGLE_ORDER:
            errors.append(f"订单金额不能低于¥{MIN_SINGLE_ORDER}")
        if order_amount > MAX_SINGLE_ORDER:
            errors.append(f"订单金额不能超过¥{MAX_SINGLE_ORDER}")
        if errors:
            return {"valid": False, "errors": errors}
        return {"valid": True, "errors": []}

    def is_blacklisted(self, user_id: str = "", ip: str = "") -> bool:
        if user_id and redis_client.available and redis_client.exists(f"blacklist:user:{user_id}"):
            return True
        if ip and redis_client.available and redis_client.exists(f"blacklist:ip:{ip}"):
            return True
        return False

    def add_blacklist(self, user_id: str = "", ip: str = "", reason: str = ""):
        if user_id:
            redis_client.set(f"blacklist:user:{user_id}", reason)
        if ip:
            redis_client.set(f"blacklist:ip:{ip}", reason)
        logger.warning(f"风控黑名单 user_id={user_id} ip={ip} reason={reason}")

    def remove_blacklist(self, user_id: str = "", ip: str = ""):
        if user_id:
            redis_client.delete(f"blacklist:user:{user_id}")
        if ip:
            redis_client.delete(f"blacklist:ip:{ip}")

    def list_blacklist(self) -> list:
        result = []
        for key, reason in redis_client.scan_keys("blacklist:ip:*"):
            ip = key.replace("blacklist:ip:", "")
            result.append({"type": "ip", "value": ip, "reason": reason or ""})
        for key, reason in redis_client.scan_keys("blacklist:user:*"):
            uid = key.replace("blacklist:user:", "")
            result.append({"type": "user", "value": uid, "reason": reason or ""})
        return result

    def log_audit(self, event_type: str, operator: str = "system", detail: str = "",
                  order_id: str = "", agent_id: str = "", user_id: str = ""):
        logger.info(f"审计日志 event_type={event_type} operator={operator} detail={detail} order_id={order_id} agent_id={agent_id} user_id={user_id}")


risk_control = RiskControl()

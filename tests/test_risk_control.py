"""Tests for api/services/risk.py — RiskControl 风控模块"""
import time
from unittest.mock import patch


class TestRateLimit:
    """限流逻辑测试（内存模式，mock Redis 不可用）"""

    def test_rate_limit_allows_within_limit(self):
        from api.services.risk import RiskControl

        rc = RiskControl()
        with patch("api.services.risk.redis_client") as mock_redis:
            mock_redis.available = False
            for _ in range(5):
                assert rc.check_rate_limit("test:key", max_count=10, window_sec=60) is True

    def test_rate_limit_blocks_over_limit(self):
        from api.services.risk import RiskControl

        rc = RiskControl()
        with patch("api.services.risk.redis_client") as mock_redis:
            mock_redis.available = False
            for _ in range(10):
                rc.check_rate_limit("test:block", max_count=5, window_sec=60)
            assert rc.check_rate_limit("test:block", max_count=5, window_sec=60) is False

    def test_rate_limit_window_expiry(self):
        from api.services.risk import RiskControl

        rc = RiskControl()
        with patch("api.services.risk.redis_client") as mock_redis:
            mock_redis.available = False
            # Fill up the limit
            for _ in range(5):
                rc.check_rate_limit("test:expire", max_count=5, window_sec=1)
            assert rc.check_rate_limit("test:expire", max_count=5, window_sec=1) is False
            # Wait for window to expire
            time.sleep(1.1)
            assert rc.check_rate_limit("test:expire", max_count=5, window_sec=1) is True


class TestValidateOrderParams:
    """订单参数校验测试"""

    def test_valid_params(self):
        from api.services.risk import RiskControl

        rc = RiskControl()
        result = rc.validate_order_params(course_count=3, order_amount=10.0, username="2024001")
        assert result["valid"] is True
        assert result["errors"] == []

    def test_invalid_username(self):
        from api.services.risk import RiskControl

        rc = RiskControl()
        result = rc.validate_order_params(course_count=1, order_amount=5.0, username="ab")
        assert result["valid"] is False
        assert "学号格式不正确" in result["errors"]

    def test_empty_username(self):
        from api.services.risk import RiskControl

        rc = RiskControl()
        result = rc.validate_order_params(course_count=1, order_amount=5.0, username="")
        assert result["valid"] is False

    def test_zero_courses(self):
        from api.services.risk import RiskControl

        rc = RiskControl()
        result = rc.validate_order_params(course_count=0, order_amount=5.0, username="2024001")
        assert result["valid"] is False
        assert "请至少选择一门课程" in result["errors"]

    def test_too_many_courses(self):
        from api.services.risk import RiskControl

        rc = RiskControl()
        result = rc.validate_order_params(course_count=1000, order_amount=5000.0, username="2024001")
        assert result["valid"] is False
        assert "单次最多选择" in result["errors"][0]

    def test_amount_too_low(self):
        from api.services.risk import RiskControl

        rc = RiskControl()
        result = rc.validate_order_params(course_count=1, order_amount=0.001, username="2024001")
        assert result["valid"] is False
        assert "不能低于" in result["errors"][0]

    def test_amount_too_high(self):
        from api.services.risk import RiskControl

        rc = RiskControl()
        result = rc.validate_order_params(course_count=1, order_amount=9999999.0, username="2024001")
        assert result["valid"] is False
        assert "不能超过" in result["errors"][0]


class TestCanCreateOrder:
    """下单频率控制测试"""

    def test_can_create_order_within_limit(self):
        from api.services.risk import RiskControl

        rc = RiskControl()
        with patch("api.services.risk.redis_client") as mock_redis:
            mock_redis.available = False
            result = rc.can_create_order(user_id="user1", ip="127.0.0.1")
            assert result["allowed"] is True

    def test_can_create_order_blocked_by_user_limit(self):
        from api.services.risk import RATE_LIMIT_ORDER_PER_USER, RiskControl

        rc = RiskControl()
        with patch("api.services.risk.redis_client") as mock_redis:
            mock_redis.available = False
            for _ in range(RATE_LIMIT_ORDER_PER_USER):
                rc.can_create_order(user_id="user_block")
            result = rc.can_create_order(user_id="user_block")
            assert result["allowed"] is False
            assert "频率过高" in result["reason"]


class TestCanScan:
    """扫描限流测试"""

    def test_can_scan_no_ip(self):
        from api.services.risk import RiskControl

        rc = RiskControl()
        assert rc.can_scan(ip="") is True

    def test_can_scan_within_limit(self):
        from api.services.risk import RiskControl

        rc = RiskControl()
        with patch("api.services.risk.redis_client") as mock_redis:
            mock_redis.available = False
            assert rc.can_scan(ip="10.0.0.1") is True


class TestOrderCourseDedup:
    """课程去重测试"""

    def test_can_order_new_course(self):
        from api.services.risk import RiskControl

        rc = RiskControl()
        with patch("api.services.risk.redis_client") as mock_redis:
            mock_redis.available = False
            assert rc.can_order_course(user_id="u1", course_id="c1") is True

    def test_duplicate_course_blocked(self):
        from api.services.risk import RiskControl

        rc = RiskControl()
        with patch("api.services.risk.redis_client") as mock_redis:
            mock_redis.available = False
            rc.can_order_course(user_id="u1", course_id="c1")
            assert rc.can_order_course(user_id="u1", course_id="c1") is False

    def test_different_user_can_order_same_course(self):
        from api.services.risk import RiskControl

        rc = RiskControl()
        with patch("api.services.risk.redis_client") as mock_redis:
            mock_redis.available = False
            rc.can_order_course(user_id="u1", course_id="c1")
            assert rc.can_order_course(user_id="u2", course_id="c1") is True

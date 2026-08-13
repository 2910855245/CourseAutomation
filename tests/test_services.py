"""Tests for service layer: pricing_service, order_service, commission_service."""
import json
from unittest.mock import patch, MagicMock

import pytest


class TestPricingService:
    """Tests for api/services/pricing_service.py"""

    def test_fallback_recommend_basic(self):
        from api.services.pricing_service import _fallback_recommend
        result = _fallback_recommend(avg=10.0, mx=15.0, mn=5.0, cost=1.0)
        assert result["priceSmall"] >= 2
        assert result["priceMedium"] > result["priceSmall"]
        assert result["priceLarge"] > result["priceMedium"]
        assert result["priceExamOnly"] >= 4
        assert result["priceMinimum"] >= 2
        assert len(result["scenarios"]) == 6

    def test_fallback_recommend_discount_ordering(self):
        from api.services.pricing_service import _fallback_recommend
        result = _fallback_recommend(avg=10.0, mx=15.0, mn=5.0, cost=1.0)
        assert result["discount25"] > result["discount50"]
        assert result["discount50"] > result["discount75"]

    def test_fallback_recommend_cheap_cost(self):
        from api.services.pricing_service import _fallback_recommend
        result = _fallback_recommend(avg=10.0, mx=15.0, mn=5.0, cost=0.5)
        assert result["priceSmall"] >= 1
        assert result["priceMinimum"] >= 2

    @patch("api.services.pricing_service._get_api_key", return_value="")
    def test_recommend_no_api_key(self, mock_key):
        from api.services.pricing_service import recommend_pricing
        result = recommend_pricing(avg=10.0, mx=15.0, mn=5.0, cost=1.0)
        assert result["code"] == 0
        assert result["data"]["analysis"]["ai_powered"] is False
        assert "recommended" in result["data"]

    @patch("api.services.pricing_service._get_api_key", return_value="test-key")
    @patch("api.services.pricing_service._call_ai_recommend", return_value=None)
    def test_recommend_ai_fallback(self, mock_ai, mock_key):
        from api.services.pricing_service import recommend_pricing
        result = recommend_pricing(avg=10.0, mx=15.0, mn=5.0, cost=1.0)
        assert result["code"] == 0
        assert result["data"]["analysis"]["ai_powered"] is True
        assert "recommended" in result["data"]

    @patch("api.services.pricing_service._get_api_key", return_value="test-key")
    @patch("api.services.pricing_service._call_ai_recommend")
    def test_recommend_ai_success(self, mock_ai, mock_key):
        mock_ai.return_value = {
            "priceSmall": 3, "priceMedium": 5, "priceLarge": 7,
            "discount25": 0.8, "discount50": 0.6, "discount75": 0.4,
            "priceMinimum": 2, "priceExamOnly": 5, "priceHomeworkOnly": 3,
            "strategy": "测试策略", "scenarios": [],
        }
        from api.services.pricing_service import recommend_pricing
        result = recommend_pricing(avg=10.0, mx=15.0, mn=5.0, cost=1.0)
        assert result["data"]["recommended"]["priceSmall"] == 3
        assert result["data"]["analysis"]["strategy"] == "测试策略"


class TestOrderService:
    """Tests for api/services/order_service.py"""

    def test_validate_order_amount_passes_when_equal(self):
        from api.services.order_service import validate_order_amount
        # Should not raise
        validate_order_amount(10.0, 10.0, [], is_privileged=False)

    def test_validate_order_amount_passes_when_privileged(self):
        from api.services.order_service import validate_order_amount
        # Privileged users skip validation
        validate_order_amount(10.0, 999.0, [], is_privileged=True)

    def test_validate_order_amount_raises_on_mismatch(self):
        from api.services.order_service import validate_order_amount
        with pytest.raises(Exception) as exc_info:
            validate_order_amount(10.0, 20.0, [], is_privileged=False)
        assert "金额异常" in str(exc_info.value.detail)

    def test_validate_order_amount_tolerance(self):
        from api.services.order_service import validate_order_amount
        # Within tolerance (0.015)
        validate_order_amount(10.0, 10.01, [], is_privileged=False)

    @patch("api.services.order_service.db")
    def test_retry_order_invalid_status(self, mock_db):
        from api.services.order_service import retry_order
        original = {"order_id": "O-001", "status": "paid", "username": "u",
                    "password": "p", "website_id": 1, "price": 5.0}
        with pytest.raises(Exception) as exc_info:
            retry_order(original, "user-1")
        assert "只有失败" in str(exc_info.value.detail)

    @patch("api.services.order_service.db")
    def test_retry_order_success(self, mock_db):
        from api.services.order_service import retry_order
        mock_db.create_order.return_value = {"order_id": "O-002"}
        original = {"order_id": "O-001", "status": "failed", "username": "u",
                    "password": "p", "website_id": 1, "price": 5.0,
                    "task_type": "full", "course_ids": '["c1"]'}
        result = retry_order(original, "user-1")
        assert result["order_id"] == "O-002"
        mock_db.create_order.assert_called_once()
        mock_db.audit_log.assert_called_once()

    @patch("api.services.order_service.db")
    def test_retry_order_parses_json_course_ids(self, mock_db):
        from api.services.order_service import retry_order
        mock_db.create_order.return_value = {"order_id": "O-003"}
        original = {"order_id": "O-001", "status": "cancelled", "username": "u",
                    "password": "p", "website_id": 2, "price": 8.0,
                    "course_ids": '["c1","c2"]'}
        retry_order(original, "user-1")
        call_kwargs = mock_db.create_order.call_args[1]
        assert call_kwargs["course_ids"] == ["c1", "c2"]


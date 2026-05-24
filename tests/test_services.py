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


class TestCommissionService:
    """Tests for api/services/commission_service.py"""

    def test_process_order_commissions_skips_processed(self):
        from api.services.commission_service import process_order_commissions
        order = {"paid": True, "commission_status": "processed", "order_id": "O-001"}
        result = process_order_commissions(order)
        assert result is False

    @patch("api.services.commission_service.db")
    @patch("api.services.commission_service._distribute_invite_reward")
    @patch("api.services.commission_service._enqueue_paid_order")
    def test_process_order_commissions_no_agent(self, mock_enqueue, mock_invite, mock_db):
        from api.services.commission_service import process_order_commissions
        order = {"order_id": "O-001", "price": 10.0, "user_id": "u1", "inviter_code": ""}
        result = process_order_commissions(order, agent=None)
        assert result is True
        mock_db.update_order.assert_called_once_with("O-001", commission_status="processed")

    @patch("api.services.commission_service.db")
    @patch("api.services.commission_service._distribute_agent_commissions")
    @patch("api.services.commission_service._distribute_invite_reward")
    @patch("api.services.commission_service._enqueue_paid_order")
    def test_process_order_commissions_with_agent(self, mock_enqueue, mock_invite,
                                                   mock_agent_comm, mock_db):
        from api.services.commission_service import process_order_commissions
        order = {"order_id": "O-001", "price": 10.0, "user_id": "u1", "inviter_code": ""}
        agent = {"agent_id": "A-001"}
        result = process_order_commissions(order, agent=agent)
        assert result is True
        mock_agent_comm.assert_called_once_with(order, agent)
        mock_invite.assert_called_once_with(order)
        mock_enqueue.assert_called_once_with("O-001")

    @patch("api.services.commission_service.db")
    @patch("api.services.commission_service._distribute_agent_commissions",
           side_effect=Exception("db error"))
    def test_process_order_commissions_error_handling(self, mock_comm, mock_db):
        from api.services.commission_service import process_order_commissions
        order = {"order_id": "O-001", "price": 10.0, "user_id": "u1"}
        agent = {"agent_id": "A-001"}
        result = process_order_commissions(order, agent=agent)
        assert result is False

    @patch("api.services.commission_service.db")
    @patch("api.services.task_queue.get_queue_for_type")
    def test_enqueue_paid_order(self, mock_get_q, mock_db):
        from api.services.commission_service import _enqueue_paid_order
        mock_db.get_order.return_value = {
            "status": "paid", "username": "u", "password": "p",
            "website_id": 1, "task_type": "full", "course_ids": '["c1"]',
        }
        mock_q = MagicMock()
        mock_q.get_job_by_order_id.return_value = None
        mock_get_q.return_value = mock_q
        _enqueue_paid_order("O-001")
        mock_q.submit_job.assert_called_once()


class TestAgentService:
    """Tests for api/services/agent_service.py"""

    @patch("api.services.agent_service.db")
    def test_validate_upgrade_rejects_inactive(self, mock_db):
        from api.services.agent_service import validate_upgrade
        agent = {"status": "suspended", "tier_level": 1}
        with pytest.raises(Exception) as exc_info:
            validate_upgrade(agent, 2)
        assert "代理状态" in str(exc_info.value.detail)

    @patch("api.services.agent_service.db")
    def test_validate_upgrade_rejects_lower_tier(self, mock_db):
        from api.services.agent_service import validate_upgrade
        agent = {"status": "active", "tier_level": 2}
        with pytest.raises(Exception) as exc_info:
            validate_upgrade(agent, 2)
        assert "必须高于" in str(exc_info.value.detail)

    @patch("api.services.agent_service.db")
    def test_validate_upgrade_rejects_disabled(self, mock_db):
        from api.services.agent_service import validate_upgrade
        mock_db.config_get.return_value = "false"
        agent = {"status": "active", "tier_level": 1}
        with pytest.raises(Exception) as exc_info:
            validate_upgrade(agent, 2)
        assert "暂未开放" in str(exc_info.value.detail)

    @patch("api.services.agent_service.db")
    def test_validate_upgrade_returns_fee(self, mock_db):
        from api.services.agent_service import validate_upgrade
        mock_db.config_get.side_effect = lambda k: {
            "agent_upgrade_fee_enabled": "true",
            "agent_upgrade_l2_fee": "200",
        }.get(k, "")
        agent = {"status": "active", "tier_level": 1}
        fee = validate_upgrade(agent, 2)
        assert fee == 200.0

    @patch("api.services.agent_service.db")
    def test_validate_withdrawal_rejects_inactive(self, mock_db):
        from api.services.agent_service import validate_withdrawal
        agent = {"status": "suspended", "available_balance": 100}
        with pytest.raises(Exception) as exc_info:
            validate_withdrawal(agent, 50)
        assert "代理状态" in str(exc_info.value.detail)

    @patch("api.services.agent_service.db")
    def test_validate_withdrawal_rejects_insufficient_balance(self, mock_db):
        from api.services.agent_service import validate_withdrawal
        mock_db.get_withdraw_rules.return_value = {
            "min_amount": 10, "max_daily_count": 0, "max_daily_amount": 0,
            "fee_rate": 0, "fee_fixed": 0, "presets": "",
        }
        mock_db.agent_withdraw_stats_today.return_value = {"count": 0, "total": 0}
        agent = {"status": "active", "available_balance": 30}
        with pytest.raises(Exception) as exc_info:
            validate_withdrawal(agent, 50)
        assert "余额不足" in str(exc_info.value.detail)

    @patch("api.services.agent_service.db")
    def test_validate_withdrawal_success(self, mock_db):
        from api.services.agent_service import validate_withdrawal
        mock_db.get_withdraw_rules.return_value = {
            "min_amount": 10, "max_daily_count": 5, "max_daily_amount": 1000,
            "fee_rate": 0.01, "fee_fixed": 0, "presets": "",
        }
        mock_db.agent_withdraw_stats_today.return_value = {"count": 0, "total": 0}
        agent = {"status": "active", "available_balance": 100, "agent_id": "A-001"}
        result = validate_withdrawal(agent, 50)
        assert result["amount"] == 50
        assert result["fee"] == 0.5
        assert result["actual_amount"] == 49.5

    @patch("api.services.agent_service.db")
    def test_register_agent_already_agent(self, mock_db):
        from api.services.agent_service import register_agent
        mock_db.get_agent_by_user_id.return_value = {"agent_id": "A-001"}
        result = register_agent("u1", "testuser")
        assert result["already_agent"] is True

    @patch("api.services.agent_service.db")
    def test_register_agent_free(self, mock_db):
        from api.services.agent_service import register_agent
        mock_db.get_agent_by_user_id.return_value = None
        mock_db.config_get.return_value = "false"
        mock_db.get_user.return_value = {"user_id": "u1", "referred_by": None}
        mock_db.create_agent.return_value = {"agent_id": "A-002"}
        with patch("api.routers.agents._generate_referral_code", return_value="REF001"), \
             patch("api.routers.agents._generate_slug", return_value="slug001"):
            result = register_agent("u1", "testuser")
        assert result["created"] is True
        assert result["agent"]["agent_id"] == "A-002"

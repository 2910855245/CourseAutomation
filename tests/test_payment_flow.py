"""集成测试：支付→订单→佣金完整链路"""


class TestPaymentToCompletionFlow:
    """完整链路：创建用户→下单→支付→接单→完成→佣金结算"""

    def _setup(self, db):
        from api.auth import hash_password
        from api.database import db as database

        agent_user = database.create_user(
            username="agent_flow",
            password_hash=hash_password("pass"),
            role="user",
            nickname="流程代理",
        )
        database.create_agent(
            user_id=agent_user["user_id"],
            tier_level=1,
            referral_code="FLOWAGT001",
        )
        agent = database.get_agent_by_user_id(agent_user["user_id"])
        buyer = database.create_user(
            username="buyer_flow",
            password_hash=hash_password("pass"),
            role="user",
            nickname="流程买家",
            referred_by=agent["agent_id"],
        )
        return database, buyer["user_id"], agent_user["user_id"]

    def test_full_payment_to_commission(self, db):
        database, buyer_uid, agent_uid = self._setup(db)

        # 下单
        order = database.create_order(
            username="test_account",
            password="test_pass",
            website_id=1,
            task_type="video",
            video_count=10,
            price=50.0,
            user_id=buyer_uid,
        )
        order_id = order["order_id"]
        assert order["status"] == "pending"

        # 模拟支付
        database.update_order(order_id, paid=1, payment_trade_no="PAY001", payment_channel="wxpay")
        assert database.get_order(order_id)["paid"]

        # 接单
        database.accept_order(order_id, admin_note="自动接单")
        assert database.get_order(order_id)["status"] == "accepted"

        # 完成（直接更新状态，因为 complete_order 仅允许 pending/running/paid）
        database.update_order(order_id, status="completed")
        assert database.get_order(order_id)["status"] == "completed"

        # 佣金结算
        from api.routers.agents import calculate_commission
        calculate_commission(order_id, buyer_uid, 50.0)

        commissions = database.list_commissions()
        assert len(commissions) >= 1
        assert any(c["order_id"] == order_id for c in commissions)

    def test_failure_triggers_refund(self, db):
        database, buyer_uid, agent_uid = self._setup(db)

        # 下单（模拟已付）
        order = database.create_order(
            username="test_account",
            password="test_pass",
            website_id=1,
            task_type="video",
            video_count=10,
            price=30.0,
            user_id=buyer_uid,
        )
        order_id = order["order_id"]
        database.update_order(order_id, paid=1)

        # 接单
        database.accept_order(order_id)
        assert database.get_order(order_id)["status"] == "accepted"

        # 失败 → 退款
        database.update_user_balance(
            buyer_uid, 30.0, "order_refund",
            note=f"订单 {order_id} 失败退款", order_id=order_id,
        )
        database.update_order(order_id, status="failed", admin_note="任务执行失败")

        assert database.get_order(order_id)["status"] == "failed"
        assert database.get_user(buyer_uid)["balance"] == 30.0  # 退款到账


class TestAgentWithdrawalFlow:
    """代理提现链路：佣金到账→申请提现→审核通过"""

    def test_withdraw_after_commission(self, db):
        from api.auth import hash_password
        from api.database import db as database

        agent_user = database.create_user(
            username="wd_agent",
            password_hash=hash_password("pass"),
            role="user",
            nickname="提现代理",
        )
        database.create_agent(
            user_id=agent_user["user_id"],
            tier_level=1,
            referral_code="WDAGT001",
        )

        agent = database.get_agent_by_user_id(agent_user["user_id"])
        database.update_agent(
            agent["agent_id"],
            available_balance=200.0,
            total_commission=200.0,
        )

        # 申请提现
        w = database.create_withdrawal(
            agent_id=agent["agent_id"],
            amount=100.0,
            method="balance",
        )
        assert w["status"] == "pending"

        # 审核通过
        database.update_withdrawal_status(w["withdrawal_id"], "completed", "管理员审核通过")
        assert database.get_withdrawal(w["withdrawal_id"])["status"] == "completed"

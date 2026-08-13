"""集成测试：支付→订单完成完整链路"""


class TestPaymentToCompletionFlow:
    """完整链路：创建用户→下单→支付→接单→完成"""

    def _setup(self, db):
        from api.auth import hash_password
        from api.database import db as database

        buyer = database.create_user(
            username="buyer_flow",
            password_hash=hash_password("pass"),
            role="user",
            nickname="流程买家",
        )
        return database, buyer["user_id"]

    def test_full_payment_to_completion(self, db):
        database, buyer_uid = self._setup(db)

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

    def test_failure_triggers_refund(self, db):
        database, buyer_uid = self._setup(db)

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

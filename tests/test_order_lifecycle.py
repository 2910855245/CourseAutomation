"""Tests for order lifecycle: create → pay → execute → complete/fail."""


class TestOrderCreation:
    def test_create_order(self, db):
        from api.auth import hash_password
        from api.database import db as database

        # Create user first
        database.create_user(
            username="orderuser",
            password_hash=hash_password("pass"),
            role="user",
            nickname="订单用户",
        )

        order = database.create_order(
            username="test_account",
            password="test_pass",
            website_id=1,
            task_type="video",
            video_count=50,
            price=5.0,
            user_id="orderuser",
        )
        assert order is not None
        assert order["status"] == "pending"
        assert order["username"] == "test_account"


class TestOrderStatusTransitions:
    def _create_order(self, db):
        from api.auth import hash_password
        from api.database import db as database

        database.create_user(
            username="statususer",
            password_hash=hash_password("pass"),
            role="user",
            nickname="状态测试",
        )
        return database.create_order(
            username="test_account",
            password="test_pass",
            website_id=1,
            task_type="video",
            video_count=50,
            price=5.0,
            user_id="statususer",
        )

    def test_accept_order(self, db):
        order = self._create_order(db)
        from api.database import db as database
        database.update_order(order["order_id"], status="accepted")
        updated = database.get_order(order["order_id"])
        assert updated["status"] == "accepted"

    def test_execute_order(self, db):
        order = self._create_order(db)
        from api.database import db as database
        database.update_order(order["order_id"], status="running")
        updated = database.get_order(order["order_id"])
        assert updated["status"] == "running"

    def test_complete_order(self, db):
        order = self._create_order(db)
        from api.database import db as database
        database.update_order(order["order_id"], status="completed")
        updated = database.get_order(order["order_id"])
        assert updated["status"] == "completed"

    def test_fail_order(self, db):
        order = self._create_order(db)
        from api.database import db as database
        database.update_order(order["order_id"], status="failed")
        updated = database.get_order(order["order_id"])
        assert updated["status"] == "failed"

    def test_cancel_order(self, db):
        order = self._create_order(db)
        from api.database import db as database
        database.update_order(order["order_id"], status="cancelled")
        updated = database.get_order(order["order_id"])
        assert updated["status"] == "cancelled"


class TestOrderListing:
    def test_list_orders(self, db):
        from api.auth import hash_password
        from api.database import db as database

        database.create_user(
            username="listuser",
            password_hash=hash_password("pass"),
            role="user",
            nickname="列表测试",
        )
        for i in range(3):
            database.create_order(
                username=f"acc_{i}",
                password="pass",
                website_id=1,
                task_type="video",
                video_count=50,
                price=5.0,
                user_id="listuser",
            )

        orders = database.list_orders(user_id="listuser")
        assert len(orders) >= 3

    def test_filter_orders_by_status(self, db):
        from api.auth import hash_password
        from api.database import db as database

        database.create_user(
            username="filteruser",
            password_hash=hash_password("pass"),
            role="user",
            nickname="过滤测试",
        )
        database.create_order(
            username="acc1",
            password="pass",
            website_id=1,
            task_type="video",
            video_count=50,
            price=5.0,
            user_id="filteruser",
        )

        orders = database.list_orders(user_id="filteruser", status="pending")
        assert len(orders) >= 1
        for o in orders:
            assert o["status"] == "pending"

"""Tests for api/db/user_db.py — 用户 CRUD 操作"""


class TestCreateUser:
    """用户创建测试"""

    def test_create_and_get_user(self, db):
        from api.database import db as database

        user = database.create_user(
            username="newuser",
            password_hash="hashed_pw",
            nickname="新用户",
            contact="test@test.com",
            role="user",
        )
        assert user["username"] == "newuser"
        assert user["nickname"] == "新用户"
        assert user["contact"] == "test@test.com"
        assert user["role"] == "user"
        assert user["balance"] == 0.0
        assert user["user_id"].startswith("USR-")

    def test_create_admin_user(self, db):
        from api.database import db as database

        user = database.create_user(
            username="admin_user",
            password_hash="hashed_pw",
            role="admin",
        )
        assert user["role"] == "admin"


class TestGetUser:
    """用户查询测试"""

    def test_get_user_by_id(self, db):
        from api.database import db as database

        created = database.create_user(
            username="getuser",
            password_hash="hashed_pw",
            nickname="查询用户",
        )
        fetched = database.get_user(created["user_id"])
        assert fetched is not None
        assert fetched["username"] == "getuser"
        assert fetched["nickname"] == "查询用户"

    def test_get_user_by_username(self, db):
        from api.database import db as database

        database.create_user(
            username="findme",
            password_hash="hashed_pw",
        )
        user = database.get_user_by_username("findme")
        assert user is not None
        assert user["username"] == "findme"

    def test_user_not_found(self, db):
        from api.database import db as database

        assert database.get_user("USR-NONEXIST") is None
        assert database.get_user_by_username("nonexist") is None


class TestUpdateUser:
    """用户更新测试"""

    def test_update_nickname(self, db):
        from api.database import db as database

        user = database.create_user(
            username="updateuser",
            password_hash="hashed_pw",
            nickname="旧昵称",
        )
        ok = database.update_user(user["user_id"], nickname="新昵称")
        assert ok is True
        updated = database.get_user(user["user_id"])
        assert updated["nickname"] == "新昵称"

    def test_update_no_fields(self, db):
        from api.database import db as database

        user = database.create_user(
            username="nofields",
            password_hash="hashed_pw",
        )
        ok = database.update_user(user["user_id"])
        assert ok is False

    def test_update_nonexistent_user(self, db):
        from api.database import db as database

        ok = database.update_user("USR-NONEXIST", nickname="ghost")
        assert ok is False


class TestUpdateBalance:
    """余额变更测试"""

    def test_increase_balance(self, db):
        from api.database import db as database

        user = database.create_user(
            username="baluser",
            password_hash="hashed_pw",
        )
        ok = database.update_user_balance(
            user["user_id"], 50.0, "deposit", "充值"
        )
        assert ok is True
        updated = database.get_user(user["user_id"])
        assert updated["balance"] == 50.0

    def test_decrease_balance(self, db):
        from api.database import db as database

        user = database.create_user(
            username="spenduser",
            password_hash="hashed_pw",
        )
        database.update_user_balance(user["user_id"], 100.0, "deposit")
        database.update_user_balance(user["user_id"], -30.0, "payment", "订单支付")
        updated = database.get_user(user["user_id"])
        assert updated["balance"] == 70.0

    def test_balance_transactions_recorded(self, db):
        from api.database import db as database

        user = database.create_user(
            username="txuser",
            password_hash="hashed_pw",
        )
        database.update_user_balance(user["user_id"], 100.0, "deposit", "充值")
        database.update_user_balance(user["user_id"], -20.0, "payment", "支付", order_id="ORD-001")
        txs = database.get_user_transactions(user["user_id"])
        assert len(txs) == 2
        assert txs[0]["amount"] == -20.0
        assert txs[0]["order_id"] == "ORD-001"
        assert txs[1]["amount"] == 100.0

    def test_nonexistent_user_balance(self, db):
        from api.database import db as database

        ok = database.update_user_balance("USR-NONEXIST", 10.0, "deposit")
        assert ok is False


class TestListUsers:
    """用户列表测试"""

    def test_list_users(self, db):
        from api.database import db as database

        database.create_user(username="list1", password_hash="pw")
        database.create_user(username="list2", password_hash="pw")
        database.create_user(username="list3", password_hash="pw")
        users = database.list_users()
        assert len(users) >= 3

    def test_list_users_with_limit(self, db):
        from api.database import db as database

        for i in range(5):
            database.create_user(username=f"limit{i}", password_hash="pw")
        users = database.list_users(limit=2)
        assert len(users) == 2


class TestUserRole:
    """用户角色测试"""

    def test_set_role(self, db):
        from api.database import db as database

        user = database.create_user(
            username="roleuser",
            password_hash="hashed_pw",
            role="user",
        )
        ok = database.set_role(user["user_id"], "admin")
        assert ok is True
        updated = database.get_user(user["user_id"])
        assert updated["role"] == "admin"

    def test_list_sub_admins(self, db):
        from api.database import db as database

        database.create_user(username="subadmin1", password_hash="pw", role="sub_admin")
        database.create_user(username="regular1", password_hash="pw", role="user")
        subs = database.list_sub_admins()
        assert len(subs) == 1
        assert subs[0]["username"] == "subadmin1"


class TestReferral:
    """推荐关系测试"""

    def test_get_user_by_referral_code(self, db):
        from api.database import db as database

        created = database.create_user(
            username="refuser",
            password_hash="hashed_pw",
        )
        database.create_agent(
            user_id=created["user_id"],
            tier_level=1,
            referral_code="REF123",
        )
        user = database.get_user_by_referral_code("REF123")
        assert user is not None
        assert user["username"] == "refuser"

    def test_referral_code_not_found(self, db):
        from api.database import db as database

        assert database.get_user_by_referral_code("NONEXIST") is None

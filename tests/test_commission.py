"""Tests for commission calculation: 3-tier system, rates, caps."""


class TestCommissionCalculation:
    def test_basic_commission(self):
        from api.services.crack import CrackEngine
        engine = CrackEngine()

        # Test basic commission calculation with 3-tier system
        # Agent must have status="active" and agent_id
        result = engine.calculate_commissions(
            order_amount=100.0,
            direct_agent={"agent_id": "AGT001", "tier_level": 1, "flow_commission_rate": 0.10, "status": "active"},
            parent_agent=None,
            grandparent_agent=None,
        )
        assert len(result) >= 1
        assert result[0]["amount"] > 0

    def test_tier_commission_rates(self):
        from api.services.crack import CrackEngine
        engine = CrackEngine()

        amount = 100.0

        # Tier 1 agent
        c1 = engine.calculate_commissions(
            order_amount=amount,
            direct_agent={"agent_id": "AGT1", "tier_level": 1, "flow_commission_rate": 0.10, "status": "active"},
            parent_agent=None,
            grandparent_agent=None,
        )

        # Tier 2 agent with higher rate
        c2 = engine.calculate_commissions(
            order_amount=amount,
            direct_agent={"agent_id": "AGT2", "tier_level": 2, "flow_commission_rate": 0.15, "status": "active"},
            parent_agent=None,
            grandparent_agent=None,
        )

        # Higher rate should get more commission
        assert c1[0]["amount"] <= c2[0]["amount"]

    def test_zero_amount_commission(self):
        from api.services.crack import CrackEngine
        engine = CrackEngine()

        result = engine.calculate_commissions(
            order_amount=0,
            direct_agent={"agent_id": "AGT0", "tier_level": 1, "flow_commission_rate": 0.10, "status": "active"},
            parent_agent=None,
            grandparent_agent=None,
        )
        # Should handle zero gracefully
        assert len(result) == 0

    def test_inactive_agent_no_commission(self):
        from api.services.crack import CrackEngine
        engine = CrackEngine()

        result = engine.calculate_commissions(
            order_amount=100.0,
            direct_agent={"agent_id": "AGT_SUSPENDED", "tier_level": 1, "flow_commission_rate": 0.10, "status": "suspended"},
            parent_agent=None,
            grandparent_agent=None,
        )
        assert len(result) == 0

    def test_three_tier_commission(self):
        from api.services.crack import CrackEngine
        engine = CrackEngine()

        result = engine.calculate_commissions(
            order_amount=100.0,
            direct_agent={"agent_id": "AGT_L3", "tier_level": 3, "flow_commission_rate": 0.20, "status": "active"},
            parent_agent={"agent_id": "AGT_L2", "tier_level": 2, "flow_commission_rate": 0.15, "status": "active"},
            grandparent_agent={"agent_id": "AGT_L1", "tier_level": 1, "flow_commission_rate": 0.10, "status": "active"},
        )
        # Should have up to 3 commission records
        assert len(result) >= 1


class TestCommissionDatabase:
    def test_create_commission_record(self, db):
        from api.auth import hash_password
        from api.database import db as database

        # Create agent
        database.create_user(
            username="comm_agent",
            password_hash=hash_password("pass"),
            role="user",
            nickname="佣金代理",
        )
        database.create_agent(
            user_id="comm_agent",
            tier_level=1,
            referral_code="COMM001",
        )

        # Create order first
        order = database.create_order(
            username="test_account",
            password="pass",
            website_id=1,
            task_type="video",
            price=100.0,
            user_id="comm_agent",
        )

        # Create commission record
        agent = database.get_agent_by_user_id("comm_agent")
        database.create_commission(
            order_id=order["order_id"],
            agent_id=agent["agent_id"],
            user_id="comm_agent",
            order_amount=100.0,
            commission_rate=0.10,
            commission_amount=10.0,
            tier_level=1,
        )

        # List commissions
        commissions = database.list_commissions(agent_id=agent["agent_id"])
        assert len(commissions) >= 1

    def test_commission_totals(self, db):
        from api.auth import hash_password
        from api.database import db as database

        database.create_user(
            username="total_agent",
            password_hash=hash_password("pass"),
            role="user",
            nickname="总额代理",
        )
        database.create_agent(
            user_id="total_agent",
            tier_level=1,
            referral_code="TOTAL001",
        )

        agent = database.get_agent_by_user_id("total_agent")

        # Create multiple commission records
        for i in range(5):
            order = database.create_order(
                username=f"acc_{i}",
                password="pass",
                website_id=1,
                task_type="video",
                price=100.0,
                user_id="total_agent",
            )
            database.create_commission(
                order_id=order["order_id"],
                agent_id=agent["agent_id"],
                user_id="total_agent",
                order_amount=100.0,
                commission_rate=0.10,
                commission_amount=10.0,
                tier_level=1,
            )

        commissions = database.list_commissions(agent_id=agent["agent_id"])
        total = sum(c["commission_amount"] for c in commissions)
        assert total == 50.0

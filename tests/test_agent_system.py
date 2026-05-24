"""Tests for agent system: registration, tiers, referrals."""


class TestAgentRegistration:
    def test_create_agent(self, db):
        from api.auth import hash_password
        from api.database import db as database

        database.create_user(
            username="newagent",
            password_hash=hash_password("pass"),
            role="user",
            nickname="新代理",
        )
        agent = database.create_agent(
            user_id="newagent",
            tier_level=1,
            referral_code="NEW001",
        )
        assert agent is not None
        assert agent["tier_level"] == 1

    def test_agent_tier_levels(self, db):
        from api.auth import hash_password
        from api.database import db as database

        for tier in [1, 2, 3]:
            username = f"tier{tier}_agent"
            database.create_user(
                username=username,
                password_hash=hash_password("pass"),
                role="user",
                nickname=f"T{tier}代理",
            )
            agent = database.create_agent(
                user_id=username,
                tier_level=tier,
                referral_code=f"TIER{tier}",
            )
            assert agent["tier_level"] == tier

    def test_agent_status_default(self, db):
        from api.auth import hash_password
        from api.database import db as database

        database.create_user(
            username="statusagent",
            password_hash=hash_password("pass"),
            role="user",
            nickname="状态代理",
        )
        agent = database.create_agent(
            user_id="statusagent",
            tier_level=1,
            referral_code="STATUS001",
        )
        assert agent["status"] in ("active", "pending")


class TestAgentTierUpgrade:
    def test_upgrade_tier(self, db):
        from api.auth import hash_password
        from api.database import db as database

        database.create_user(
            username="upgradeagent",
            password_hash=hash_password("pass"),
            role="user",
            nickname="升级代理",
        )
        database.create_agent(
            user_id="upgradeagent",
            tier_level=1,
            referral_code="UPGRADE001",
        )

        # Get agent to find agent_id
        agent = database.get_agent_by_user_id("upgradeagent")
        assert agent is not None

        # Upgrade tier
        database.update_agent(agent["agent_id"], tier_level=2)
        updated = database.get_agent(agent["agent_id"])
        assert updated["tier_level"] == 2

    def test_downgrade_tier(self, db):
        from api.auth import hash_password
        from api.database import db as database

        database.create_user(
            username="downagent",
            password_hash=hash_password("pass"),
            role="user",
            nickname="降级代理",
        )
        database.create_agent(
            user_id="downagent",
            tier_level=3,
            referral_code="DOWN001",
        )

        agent = database.get_agent_by_user_id("downagent")
        database.update_agent(agent["agent_id"], tier_level=1)
        updated = database.get_agent(agent["agent_id"])
        assert updated["tier_level"] == 1


class TestAgentReferral:
    def test_list_agents(self, db):
        from api.auth import hash_password
        from api.database import db as database

        for i in range(3):
            username = f"listagent{i}"
            database.create_user(
                username=username,
                password_hash=hash_password("pass"),
                role="user",
                nickname=f"列表代理{i}",
            )
            database.create_agent(
                user_id=username,
                tier_level=1,
                referral_code=f"LIST{i:03d}",
            )

        agents = database.list_agents()
        assert len(agents) >= 3


class TestAgentApproval:
    def test_approve_agent(self, db):
        from api.auth import hash_password
        from api.database import db as database

        database.create_user(
            username="approveagent",
            password_hash=hash_password("pass"),
            role="user",
            nickname="审批代理",
        )
        database.create_agent(
            user_id="approveagent",
            tier_level=1,
            referral_code="APPROVE001",
        )

        agent = database.get_agent_by_user_id("approveagent")
        database.update_agent(agent["agent_id"], status="active")
        updated = database.get_agent(agent["agent_id"])
        assert updated["status"] == "active"

    def test_suspend_agent(self, db):
        from api.auth import hash_password
        from api.database import db as database

        database.create_user(
            username="suspendagent",
            password_hash=hash_password("pass"),
            role="user",
            nickname="暂停代理",
        )
        database.create_agent(
            user_id="suspendagent",
            tier_level=1,
            referral_code="SUSPEND001",
        )

        agent = database.get_agent_by_user_id("suspendagent")
        database.update_agent(agent["agent_id"], status="suspended")
        updated = database.get_agent(agent["agent_id"])
        assert updated["status"] == "suspended"

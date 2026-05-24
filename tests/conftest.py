"""Pytest fixtures for the Anti-Course Cheating Plugin test suite."""
import os
import sys
from unittest.mock import patch

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def _env_setup(tmp_path):
    """Set up environment variables for testing."""
    with patch.dict(os.environ, {
        "JWT_SECRET_KEY": "test-secret-key-for-testing-only",
        "DATABASE_URL": f"sqlite:///{tmp_path / 'test.db'}",
        "PASSWORD_ENCRYPTION_KEY": "test-encryption-key-32chars!!!!!",
        "REDIS_URL": "redis://localhost:6379/0",
        "SITE_URL": "http://localhost:8000",
    }):
        yield


@pytest.fixture
def db(tmp_path):
    """Create an isolated SQLite database for testing."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from api.database import Base

    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    # Patch the global engine and SessionLocal
    import api.database as db_mod
    old_engine = db_mod.engine
    old_session = db_mod.SessionLocal
    db_mod.engine = engine
    db_mod.SessionLocal = TestSession

    # Also reset the Database singleton's session factory
    from api.database import db as database
    old_factory = database._session_factory
    database._session_factory = TestSession

    yield engine

    # Restore
    db_mod.engine = old_engine
    db_mod.SessionLocal = old_session
    database._session_factory = old_factory


@pytest.fixture
def client(db):
    """Create a FastAPI test client."""
    from fastapi.testclient import TestClient

    from api.main import app

    return TestClient(app)


@pytest.fixture
def admin_token(db):
    """Create an admin user and return a JWT token."""
    from api.auth import create_token, hash_password
    from api.database import db as database

    # Create admin user directly in DB
    database.create_user(
        username="testadmin",
        password_hash=hash_password("admin123"),
        role="admin",
        nickname="测试管理员",
    )

    token = create_token("testadmin", "testadmin", "admin")
    return token


@pytest.fixture
def admin_headers(admin_token):
    """Return Authorization headers for admin."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def sample_user(db):
    """Create a sample regular user."""
    from api.auth import hash_password
    from api.database import db as database

    user = database.create_user(
        username="testuser",
        password_hash=hash_password("user123"),
        role="user",
        nickname="测试用户",
    )
    return user


@pytest.fixture
def sample_agent(db):
    """Create a sample agent user."""
    from api.auth import hash_password
    from api.database import db as database

    database.create_user(
        username="testagent",
        password_hash=hash_password("agent123"),
        role="user",
        nickname="测试代理",
    )
    # Create agent profile
    database.create_agent(
        user_id="testagent",
        tier_level=1,
        referral_code="AGENT001",
    )
    return "testagent"

"""Tests for config.py — Settings and configuration management."""
import os
import importlib
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _reload_config():
    """Clear cached settings so env vars from conftest take effect."""
    import config
    config.get_settings.cache_clear()
    importlib.reload(config)
    yield
    config.get_settings.cache_clear()


class TestSettings:
    """Settings loading and validation."""

    def test_settings_loads_from_env(self):
        from config import settings
        assert settings.jwt_secret_key == "test-secret-key-for-testing-only"
        assert settings.password_encryption_key == "test-encryption-key-32chars!!!!!"

    def test_settings_has_database_url(self):
        from config import settings
        assert settings.database_url  # Should be set by test fixture

    def test_settings_defaults(self):
        from config import settings
        assert settings.host == "0.0.0.0"
        assert settings.port == 8000
        assert settings.jwt_algorithm == "HS256"
        assert settings.jwt_expire_hours == 72

    def test_settings_rate_limit_defaults(self):
        from config import settings
        assert settings.rate_limit_requests > 0
        assert settings.rate_limit_window_seconds > 0


class TestWebsitesConfig:
    """Multi-website configuration."""

    def test_websites_dict_exists(self):
        from config import WEBSITES
        assert isinstance(WEBSITES, dict)
        assert len(WEBSITES) >= 1

    def test_website_has_required_keys(self):
        from config import WEBSITES
        for wid, wconf in WEBSITES.items():
            assert "name" in wconf
            assert "base_url" in wconf
            assert isinstance(wid, int)

    def test_website_urls_are_https(self):
        from config import WEBSITES
        for wid, wconf in WEBSITES.items():
            assert wconf["base_url"].startswith("https://"), \
                f"Website {wid} URL should use HTTPS: {wconf['base_url']}"


class TestDirectories:
    """Data directory creation."""

    def test_data_dir_exists(self):
        from config import DATA_DIR
        assert os.path.isdir(DATA_DIR)

    def test_accounts_dir_exists(self):
        from config import ACCOUNTS_DIR
        assert os.path.isdir(ACCOUNTS_DIR)

    def test_logs_dir_exists(self):
        from config import LOGS_DIR
        assert os.path.isdir(LOGS_DIR)


class TestGlobalStateLock:
    """Global state lock exists."""

    def test_lock_exists(self):
        from config import _global_state_lock
        assert _global_state_lock is not None
        # Should be reentrant lock
        with _global_state_lock:
            with _global_state_lock:
                pass  # Should not deadlock

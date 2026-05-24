"""Tests for api/services/proxy_config.py — 代理配置"""
import json
from unittest.mock import patch


class TestBuildProxyUrl:
    """代理 URL 构建测试"""

    def test_basic_url(self):
        from api.services.proxy_config import _build_proxy_url

        result = _build_proxy_url({"url": "http://proxy.example.com:8080"})
        assert result == "http://proxy.example.com:8080"

    def test_url_with_auth(self):
        from api.services.proxy_config import _build_proxy_url

        result = _build_proxy_url({
            "url": "http://proxy.example.com:8080",
            "username": "user",
            "password": "pass",
        })
        assert result == "http://user:pass@proxy.example.com:8080"

    def test_url_with_auth_https(self):
        from api.services.proxy_config import _build_proxy_url

        result = _build_proxy_url({
            "url": "https://proxy.example.com:443",
            "username": "admin",
            "password": "secret",
        })
        assert result == "https://admin:secret@proxy.example.com:443"

    def test_url_without_scheme(self):
        from api.services.proxy_config import _build_proxy_url

        result = _build_proxy_url({
            "url": "proxy.example.com:8080",
            "username": "user",
            "password": "pass",
        })
        assert result == "http://user:pass@proxy.example.com:8080"

    def test_empty_url(self):
        from api.services.proxy_config import _build_proxy_url

        result = _build_proxy_url({"url": ""})
        assert result == ""


class TestGetProxyConfig:
    """代理配置加载测试"""

    def test_no_config_file(self, tmp_path):
        from api.services.proxy_config import get_proxy_config

        with patch("api.services.proxy_config.PROXY_JSON", str(tmp_path / "nonexistent.json")):
            result = get_proxy_config()
            assert result["enabled"] is False

    def test_disabled_config(self, tmp_path):
        from api.services.proxy_config import get_proxy_config

        cfg_path = tmp_path / "proxy.json"
        cfg_path.write_text(json.dumps({"enabled": False, "url": "http://proxy:8080"}))

        with patch("api.services.proxy_config.PROXY_JSON", str(cfg_path)):
            result = get_proxy_config()
            assert result["enabled"] is False

    def test_single_proxy_enabled(self, tmp_path):
        from api.services.proxy_config import get_proxy_config

        cfg_path = tmp_path / "proxy.json"
        cfg_path.write_text(json.dumps({
            "enabled": True,
            "url": "http://proxy:8080",
        }))

        with patch("api.services.proxy_config.PROXY_JSON", str(cfg_path)):
            result = get_proxy_config()
            assert result["enabled"] is True
            assert "http" in result["proxies"]

    def test_multi_proxy_enabled(self, tmp_path):
        from api.services.proxy_config import get_proxy_config

        cfg_path = tmp_path / "proxy.json"
        cfg_path.write_text(json.dumps({
            "enabled": True,
            "proxies": [
                {"url": "http://p1:8080"},
                {"url": "http://p2:8080"},
            ],
        }))

        with patch("api.services.proxy_config.PROXY_JSON", str(cfg_path)):
            result = get_proxy_config()
            assert result["enabled"] is True


class TestProxyRotation:
    """代理轮换测试"""

    def test_get_next_proxy_empty_pool(self):
        # Clear pool
        import api.services.proxy_config as mod
        from api.services.proxy_config import get_next_proxy
        old_pool = mod._proxy_pool
        mod._proxy_pool = []

        with patch("api.services.proxy_config.get_proxy_config", return_value={"enabled": False, "proxies": {}}):
            result = get_next_proxy()
            assert result["enabled"] is False

        mod._proxy_pool = old_pool

    def test_get_next_proxy_rotation(self):
        import api.services.proxy_config as mod

        old_pool = mod._proxy_pool
        old_index = mod._proxy_index
        mod._proxy_pool = ["http://p1:8080", "http://p2:8080", "http://p3:8080"]
        mod._proxy_index = 0

        try:
            urls = set()
            for _ in range(3):
                result = mod.get_next_proxy()
                urls.add(result["proxies"]["http"])
            assert len(urls) == 3
        finally:
            mod._proxy_pool = old_pool
            mod._proxy_index = old_index

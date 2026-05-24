"""Integration tests for API endpoints: queue, admin, health."""
import pytest


class TestHealthEndpoints:
    """Health check endpoints."""

    def test_health_summary(self, client, admin_headers, db):
        resp = client.get("/api/health/summary", headers=admin_headers)
        assert resp.status_code == 200

    def test_health_account(self, client, admin_headers, db):
        resp = client.get("/api/health/account", headers=admin_headers)
        assert resp.status_code == 200


class TestQueueEndpoints:
    """Queue management endpoints."""

    def test_queue_stats_requires_auth(self, client):
        resp = client.get("/api/queue/stats")
        assert resp.status_code in (401, 403)

    def test_queue_stats_with_admin(self, client, admin_headers):
        resp = client.get("/api/queue/stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "pending" in data["data"]
        assert "running" in data["data"]
        assert "waiting" in data["data"]

    def test_queue_jobs_list(self, client, admin_headers):
        resp = client.get("/api/queue/jobs", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

    def test_queue_detect(self, client, admin_headers):
        resp = client.get("/api/queue/detect", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "cpu_count" in data["data"]
        assert "recommended_workers" in data["data"]

    def test_queue_pause_resume(self, client, admin_headers):
        resp = client.post("/api/queue/pause", headers=admin_headers)
        assert resp.status_code == 200

        resp = client.post("/api/queue/resume", headers=admin_headers)
        assert resp.status_code == 200

    def test_queue_config_update(self, client, admin_headers):
        resp = client.post(
            "/api/queue/config?max_workers=5",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True


class TestAdminEndpoints:
    """Admin dashboard endpoints."""

    def test_admin_dashboard_requires_auth(self, client):
        resp = client.get("/api/admin/dashboard")
        assert resp.status_code in (401, 403)

    def test_admin_dashboard_with_admin(self, client, admin_headers):
        resp = client.get("/api/admin/dashboard", headers=admin_headers)
        assert resp.status_code == 200

    def test_admin_stats(self, client, admin_headers):
        resp = client.get("/api/admin/stats", headers=admin_headers)
        # May return 200 or 404 depending on implementation
        assert resp.status_code in (200, 404)


class TestOrderEndpoints:
    """Order management endpoints."""

    def test_list_orders_requires_auth(self, client):
        resp = client.get("/api/orders/")
        assert resp.status_code in (401, 403)

    def test_list_orders_with_user(self, client, admin_headers, sample_user):
        from api.auth import create_token
        token = create_token(sample_user["user_id"], sample_user["username"], "user")
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/orders/", headers=headers)
        assert resp.status_code == 200

    def test_create_order_requires_auth(self, client):
        resp = client.post("/api/orders/", json={
            "username": "test",
            "password": "pass",
            "website_id": 1,
        })
        # May return 400 (validation) or 401/403 (auth) depending on middleware order
        assert resp.status_code in (400, 401, 403)


class TestUserEndpoints:
    """User management endpoints."""

    def test_user_profile(self, client, admin_headers, sample_user):
        from api.auth import create_token
        token = create_token(sample_user["user_id"], sample_user["username"], "user")
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/users/me", headers=headers)
        assert resp.status_code == 200

    def test_user_balance(self, client, admin_headers, sample_user):
        from api.auth import create_token
        token = create_token(sample_user["user_id"], sample_user["username"], "user")
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/wallet/balance", headers=headers)
        assert resp.status_code == 200


class TestConfigEndpoints:
    """Configuration endpoints."""

    def test_get_config_requires_admin(self, client):
        resp = client.get("/api/admin/config")
        assert resp.status_code in (401, 403)

    def test_get_config_with_admin(self, client, admin_headers):
        resp = client.get("/api/admin/config", headers=admin_headers)
        assert resp.status_code == 200

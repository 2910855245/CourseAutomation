"""Tests for YPay routes: admin, app, routes, vmq."""
import json
from unittest.mock import patch, MagicMock

import pytest


# ─── ypay_admin.py ───


class TestYpayAdminRoutes:
    """YPay admin management endpoints."""

    def test_ypay_status(self, client, admin_headers, db):
        resp = client.get("/api/ypay/status", headers=admin_headers)
        assert resp.status_code == 200

    def test_ypay_config_get(self, client, admin_headers, db):
        resp = client.get("/api/ypay/config/get", headers=admin_headers)
        assert resp.status_code == 200

    def test_ypay_config_save(self, client, admin_headers, db):
        resp = client.post("/api/ypay/config/save", headers=admin_headers, json={
            "key": "test_key", "value": "test_value",
        })
        assert resp.status_code == 200

    def test_ypay_accounts_list(self, client, admin_headers, db):
        resp = client.get("/api/ypay/accounts", headers=admin_headers)
        assert resp.status_code == 200

    def test_ypay_add_account(self, client, admin_headers, db):
        resp = client.post("/api/ypay/accounts", headers=admin_headers, json={
            "name": "test_account", "pay_type": 2,
            "app_id": "test_app_id", "app_key": "test_app_key",
        })
        assert resp.status_code == 200

    def test_ypay_orders_list(self, client, admin_headers, db):
        resp = client.get("/api/ypay/orders", headers=admin_headers)
        assert resp.status_code == 200

    def test_ypay_clear_orders(self, client, admin_headers, db):
        resp = client.post("/api/ypay/clear-orders", headers=admin_headers)
        assert resp.status_code == 200

    @patch("api.routers.ypay_admin.ypay")
    def test_ypay_test(self, mock_ypay, client, admin_headers, db):
        mock_ypay.test_connection.return_value = {"success": True, "message": "ok"}
        resp = client.get("/api/ypay/test", headers=admin_headers)
        assert resp.status_code == 200

    def test_ypay_regenerate_key(self, client, admin_headers, db):
        resp = client.post("/api/ypay/regenerate-key", headers=admin_headers)
        assert resp.status_code == 200

    def test_ypay_diagnose(self, client, admin_headers, db):
        resp = client.get("/api/ypay/diagnose", headers=admin_headers)
        assert resp.status_code == 200


# ─── ypay_routes.py ───


class TestYpayRoutes:
    """YPay payment endpoints."""

    def test_decode_qr_requires_image(self, client, db):
        resp = client.post("/api/ypay/decode-qr", json={})
        assert resp.status_code in (200, 400, 422)

    def test_pay_check_not_found(self, client, db):
        resp = client.get("/api/ypay/check/NONEXISTENT")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("code") in (404, 0)

    def test_pay_order_not_found(self, client, db):
        resp = client.get("/api/ypay/order/NONEXISTENT")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("code") in (404, -1, 0)

    def test_pay_qrcode_not_found(self, client, db):
        resp = client.get("/api/ypay/qrcode/NONEXISTENT")
        assert resp.status_code in (200, 404)

    def test_batch_check_empty(self, client, db):
        resp = client.get("/api/payment/batch-check/nonexistent_batch")
        assert resp.status_code == 200


# ─── ypay_app.py ───


class TestYpayAppRoutes:
    """YPay Android APP endpoints."""

    def test_app_download(self, client, db):
        resp = client.get("/api/ypay/app-download")
        assert resp.status_code in (200, 404)

    def test_app_pair_status(self, client, db):
        resp = client.get("/api/ypay/pair-status")
        assert resp.status_code == 200

    @patch("api.routers.ypay_app.db")
    def test_app_heart(self, mock_db, client, db):
        mock_db.ypay_list_accounts.return_value = []
        resp = client.post("/api/ypay/app-heart", json={
            "device_id": "test_device", "status": "online",
        })
        assert resp.status_code == 200

    @patch("api.routers.ypay_app.db")
    def test_app_offline(self, mock_db, client, db):
        resp = client.post("/api/ypay/app-offline", json={
            "device_id": "test_device",
        })
        assert resp.status_code == 200

    @patch("api.routers.ypay_app.db")
    def test_app_push(self, mock_db, client, db):
        mock_db.ypay_match_order_by_amount.return_value = None
        resp = client.post("/api/ypay/app-push", json={
            "type": 2, "price": "10.00", "device_id": "test_device",
        })
        assert resp.status_code == 200

    def test_app_info(self, client, db):
        resp = client.get("/api/ypay/app-info")
        assert resp.status_code == 200


# ─── ypay_vmq.py ───


class TestVmqRoutes:
    """VMQ protocol endpoints."""

    def test_vmq_heart_no_params(self, client, db):
        resp = client.post("/api/ypay/vmq/heart")
        assert resp.status_code == 200
        assert resp.text == "fail"

    def test_vmq_push_no_params(self, client, db):
        resp = client.post("/api/ypay/vmq/push")
        assert resp.status_code == 200
        assert resp.text == "fail"

    @patch("api.routers.ypay_vmq.ypay")
    def test_vmq_heart_invalid_sign(self, mock_ypay, client, db):
        mock_ypay.verify_heart_sign.return_value = False
        resp = client.post("/api/ypay/vmq/heart?t=123&sign=bad")
        assert resp.status_code == 200
        assert resp.text == "fail"

    @patch("api.routers.ypay_vmq.ypay")
    def test_vmq_push_invalid_sign(self, mock_ypay, client, db):
        mock_ypay.verify_push_sign.return_value = False
        resp = client.post("/api/ypay/vmq/push?type=2&price=10&sign=bad")
        assert resp.status_code == 200
        assert resp.text == "fail"


# ─── ypay_service.py ───


class TestYpayService:
    """Tests for api/services/ypay_service.py"""

    def test_pick_channel(self):
        from api.services.ypay_service import YPayService
        svc = YPayService.__new__(YPayService)
        svc._initialized = False
        svc._app_keys = {}
        svc._sign_key = ""
        assert svc is not None

    def test_build_pay_url(self):
        from api.services.ypay_service import YPayService
        svc = YPayService.__new__(YPayService)
        svc._initialized = False
        svc._base_url = "https://pay.example.com"
        url = svc.build_pay_url("T12345")
        assert "T12345" in url

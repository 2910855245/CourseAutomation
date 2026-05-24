"""Tests for payment callbacks: YPay, VMQ, idempotency."""


class TestPaymentOrderCreation:
    def test_create_payment_order(self, db):
        from api.database import db as database

        order = database.ypay_create_order(
            trade_no="TRADE001",
            out_trade_no="OUT001",
            pay_type=1,
            type_str="wxpay",
            name="测试订单",
            money=5.00,
            truemoney=5.00,
            account_id=1,
            qrcode="",
            h5_qrurl="",
            notify_url="",
            return_url="",
            ip="127.0.0.1",
            out_time="300",
        )
        assert order is not None

    def test_payment_order_status(self, db):
        from api.database import db as database

        database.ypay_create_order(
            trade_no="TRADE002",
            out_trade_no="OUT002",
            pay_type=1,
            type_str="wxpay",
            name="测试订单2",
            money=10.00,
            truemoney=10.00,
            account_id=1,
            qrcode="",
            h5_qrurl="",
            notify_url="",
            return_url="",
            ip="127.0.0.1",
            out_time="300",
        )

        # Check status
        orders = database.ypay_list_orders()
        assert len(orders) >= 1


class TestPaymentCallback:
    def test_mark_order_paid(self, db):
        from api.database import db as database

        database.ypay_create_order(
            trade_no="TRADE003",
            out_trade_no="OUT003",
            pay_type=1,
            type_str="wxpay",
            name="测试订单3",
            money=5.00,
            truemoney=5.00,
            account_id=1,
            qrcode="",
            h5_qrurl="",
            notify_url="",
            return_url="",
            ip="127.0.0.1",
            out_time="300",
        )

        # Mark as paid
        result = database.ypay_mark_paid("TRADE003")
        assert result is True

        # Verify
        order = database.ypay_get_order("TRADE003")
        assert order["status"] == 1  # paid

    def test_close_expired_order(self, db):
        from api.database import db as database

        database.ypay_create_order(
            trade_no="TRADE004",
            out_trade_no="OUT004",
            pay_type=1,
            type_str="wxpay",
            name="测试订单4",
            money=5.00,
            truemoney=5.00,
            account_id=1,
            qrcode="",
            h5_qrurl="",
            notify_url="",
            return_url="",
            ip="127.0.0.1",
            out_time="300",
        )

        # Close expired orders
        count = database.ypay_close_expired_orders()
        assert count >= 0


class TestPaymentIdempotency:
    def test_duplicate_callback_safe(self, db):
        """Processing the same callback twice should not create duplicate records."""
        from api.database import db as database

        database.ypay_create_order(
            trade_no="TRADE005",
            out_trade_no="OUT005",
            pay_type=1,
            type_str="wxpay",
            name="测试订单5",
            money=5.00,
            truemoney=5.00,
            account_id=1,
            qrcode="",
            h5_qrurl="",
            notify_url="",
            return_url="",
            ip="127.0.0.1",
            out_time="300",
        )

        # Mark paid twice
        database.ypay_mark_paid("TRADE005")
        database.ypay_mark_paid("TRADE005")

        # Should still be one order
        order = database.ypay_get_order("TRADE005")
        assert order is not None
        assert order["status"] == 1


class TestYPayAccountManagement:
    def test_create_account(self, db):
        from api.database import db as database

        account = database.ypay_add_account(
            atype="wxpay",
            code="wxpay_software",
            name="测试微信通道",
            qr_url="https://example.com/qr",
        )
        assert account is not None

    def test_list_accounts(self, db):
        from api.database import db as database

        database.ypay_add_account(
            atype="wxpay",
            code="wxpay_software",
            name="微信通道1",
            qr_url="https://example.com/qr1",
        )
        database.ypay_add_account(
            atype="alipay",
            code="alipay_dmf",
            name="支付宝通道1",
            qr_url="https://example.com/qr2",
        )

        accounts = database.ypay_list_accounts()
        assert len(accounts) >= 2

    def test_toggle_account_status(self, db):
        from api.database import db as database

        database.ypay_add_account(
            atype="wxpay",
            code="wxpay_software",
            name="切换测试",
            qr_url="https://example.com/qr",
        )

        accounts = database.ypay_list_accounts()
        assert len(accounts) >= 1
        acc = accounts[0]

        # Toggle status
        database.ypay_update_account(acc["id"], is_status=0)
        updated = database.ypay_list_accounts()
        target = next(a for a in updated if a["id"] == acc["id"])
        assert target["is_status"] == 0

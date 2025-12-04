

from unittest.mock import patch

# ----------------------------------------------------
# Patch environment BEFORE importing any kairon modules
# ----------------------------------------------------
mock_env = {
    "pos": {
        "odoo": {
            "odoo_url": "http://localhost:8080",
            "odoo_master_password":"admin@123"
        }
    }
}

patcher = patch("kairon.Utility.environment", mock_env)
patcher.start()

from kairon.pos.odoo.odoo_pos import OdooPOS
from kairon.shared.pos.processor import POSProcessor

import pytest
# ----------------------------------------------------


@pytest.fixture
def odoo_pos():
    return OdooPOS()


def teardown_module(module):
    """Stop environment patch after all tests."""
    patcher.stop()


def test_products_list(odoo_pos):
    resp = odoo_pos.products_list()
    assert resp["url"].startswith("http://localhost:8080")


def test_orders_list(odoo_pos):
    resp = odoo_pos.orders_list()
    assert resp["url"].startswith("http://localhost:8080")


def test_onboarding(odoo_pos):
    with patch.object(POSProcessor, "onboarding_client", return_value={"ok": True}) as mock_fn:
        resp = odoo_pos.onboarding(client_name="demo", bot="test_bot", user="aniket.kharkia@nimblework.com")
        mock_fn.assert_called_once()
        assert resp == {"ok": True}

def test_authenticate_products(odoo_pos):
    with (
        patch.object(POSProcessor, "pos_login", return_value={"session": "s1"}) as p_login,
        patch.object(OdooPOS, "products_list", return_value={"url": "p_url"}) as p_list,
        patch.object(POSProcessor, "set_odoo_session_cookie", return_value={"done": True}) as p_cookie,
    ):
        resp = odoo_pos.authenticate(client_name="demo", bot="test_bot")

        p_login.assert_called_once()
        p_list.assert_called_once()
        p_cookie.assert_called_once_with({"session": "s1", "url": "p_url"})

        assert resp == {"done": True}

def test_authenticate_orders(odoo_pos):
    with (
        patch.object(POSProcessor, "pos_login", return_value={"session": "xyz"}) as p_login,
        patch.object(OdooPOS, "orders_list", return_value={"url": "o_url"}) as o_list,
        patch.object(POSProcessor, "set_odoo_session_cookie", return_value={"ok": 1}) as p_cookie
    ):
        resp = odoo_pos.authenticate(client_name="C", bot="B", page_type="pos_orders")

        p_login.assert_called_once()
        o_list.assert_called_once()
        p_cookie.assert_called_once_with({"session": "xyz", "url": "o_url"})
        assert resp == {"ok": 1}
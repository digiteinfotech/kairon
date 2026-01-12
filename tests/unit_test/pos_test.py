from unittest.mock import patch

from fastapi import HTTPException

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

def test_create_branch_success():
    service = POSProcessor()

    with patch.object(service, "jsonrpc_call") as mock_jsonrpc, \
         patch("kairon.shared.pos.processor.POSProcessor.save_branch_details") as mock_save:

        mock_jsonrpc.return_value = 123  # branch_id from Odoo

        result = service.create_branch(
            session_id="session123",
            branch_name="Bangalore Branch",
            street="MG Road",
            city="Bangalore",
            state="Karnataka",
            bot="test_bot",
            user="test_user"
        )

        # Assertions
        assert result == {
            "branch_id": 123,
            "status": "created"
        }

        mock_jsonrpc.assert_called_once()
        mock_save.assert_called_once_with(
            "test_bot",
            "Bangalore Branch",
            123,
            "test_user"
        )

def test_create_branch_jsonrpc_failure():
    service = POSProcessor()

    with patch.object(service, "jsonrpc_call") as mock_jsonrpc, \
         patch("kairon.shared.pos.processor.POSProcessor.save_branch_details") as mock_save:

        mock_jsonrpc.return_value = None

        with pytest.raises(HTTPException) as exc:
            service.create_branch(
                session_id="session123",
                branch_name="Mumbai Branch",
                street="Link Road",
                city="Mumbai",
                state="Maharashtra",
                bot="test_bot",
                user="test_user"
            )

        assert exc.value.status_code == 404
        assert exc.value.detail == "Error in creating branch"

        mock_save.assert_not_called()

def test_create_branch_invalid_state():
    service = POSProcessor()

    with pytest.raises(HTTPException):
        service.create_branch(
            session_id="session123",
            branch_name="Unknown Branch",
            street="Some Street",
            city="Some City",
            state="InvalidState",
            bot="test_bot",
            user="test_user"
        )

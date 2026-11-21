from unittest.mock import patch, MagicMock, AsyncMock
from unittest.mock import Mock, patch
from fastapi import HTTPException

from kairon.exceptions import AppException

mock_env = {
    "pos": {
        "odoo": {
            "odoo_url": "http://localhost:8080",
            "odoo_master_password":"admin@123"
        }
    },
    "live_agent":{
        "url":"http://localhost:8000/api/v1"
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

def test_save_branch_details_no_pos_client_config():
    with patch("kairon.shared.pos.processor.POSClientDetails.objects") as mock_objects:

        mock_objects.return_value.first.return_value = None

        with pytest.raises(AppException) as exc:
            POSProcessor.save_branch_details(
                bot="test_bot",
                branch_name="Test Branch",
                company_id=123,
                user="test_user"
            )

        assert str(exc.value) == "No POS client configuration found for this bot."

def test_save_branch_details_success():
    with patch("kairon.shared.pos.processor.POSClientDetails.objects") as mock_objects:

        mock_record = MagicMock()
        mock_record.to_mongo.return_value.to_dict.return_value = {
            "client_name": "Test Client"
        }

        mock_qs = MagicMock()
        mock_qs.first.return_value = mock_record
        mock_qs.update_one.return_value = 1

        mock_objects.return_value = mock_qs

        result = POSProcessor.save_branch_details(
            bot="test_bot",
            branch_name="Test Branch",
            company_id=123,
            user="test_user"
        )

        assert result == 1

def test_create_branch_invalid_state_raises_400():
    service = POSProcessor()

    with patch.object(service, "jsonrpc_call") as mock_jsonrpc, \
         patch("kairon.shared.pos.processor.POSProcessor.save_branch_details") as mock_save:

        with pytest.raises(HTTPException) as exc:
            service.create_branch(
                session_id="dummy_session",
                branch_name="Test Branch",
                street="Some Street",
                city="Mumbai",
                state="InvalidState",
                bot="test_bot",
                user="test_user"
            )

        assert exc.value.status_code == 400
        assert exc.value.detail == "Invalid state: InvalidState"

        mock_jsonrpc.assert_not_called()
        mock_save.assert_not_called()

def test_raise_if_error_jsonrpc_error():
    processor = POSProcessor()

    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "error": {
            "data": {
                "message": "The company name must be unique!"
            }
        }
    }

    with patch("kairon.shared.pos.processor.logger.error") as mock_logger:
        with pytest.raises(HTTPException) as exc_info:
            processor._raise_if_error(mock_resp, context="Odoo request")

        assert exc_info.value.status_code == 400
        assert "Odoo request - The company name must be unique!" in str(exc_info.value.detail)

        mock_logger.assert_called_once_with("The company name must be unique!")

def test_raise_if_error_with_direct_message():
    processor = POSProcessor()

    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "error": {
            "message": "Database error"
        }
    }

    with pytest.raises(HTTPException) as exc:
        processor._raise_if_error(mock_resp, "Odoo request")

    assert exc.value.status_code == 400
    assert "Database error" in exc.value.detail

def test_raise_if_error_string_error():
    processor = POSProcessor()

    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "error": "Something went wrong"
    }

    with pytest.raises(HTTPException) as exc:
        processor._raise_if_error(mock_resp)

    assert exc.value.status_code == 400
    assert "Something went wrong" in exc.value.detail

def test_raise_if_error_no_message():
    processor = POSProcessor()

    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "error": {}
    }

    with pytest.raises(HTTPException) as exc:
        processor._raise_if_error(mock_resp)

    assert exc.value.status_code == 400

@pytest.mark.asyncio
async def test_send_notification_success():
    processor = POSProcessor()

    mock_response = {"status": "sent"}

    mock_post_response = MagicMock()
    mock_post_response.json.return_value = mock_response

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_post_response)):
        result = await processor.send_notification(
            data={"message": "test"},
            bot="test_bot"
        )

        assert result == mock_response

@pytest.mark.asyncio
async def test_send_notification_failure_logs():
    processor = POSProcessor()

    with patch(
        "httpx.AsyncClient.post",
        new=AsyncMock(side_effect=Exception("Connection error"))
    ), patch("kairon.shared.pos.processor.logger") as mock_logger:

        result = await processor.send_notification(
            data={"message": "test"},
            bot="test_bot"
        )

        assert result is None
        mock_logger.exception.assert_called_once()

def test_create_pos_user_success():
    import json
    processor = POSProcessor()

    with patch("kairon.shared.pos.processor.BotSettings.objects") as mock_objects, \
         patch("kairon.shared.pos.processor.POSProcessor.get_client_details") as mock_client_details, \
         patch("kairon.pos.definitions.factory.POSFactory.get_instance") as mock_get_instance, \
         patch("kairon.shared.pos.processor.POSProcessor.generate_password") as mock_password, \
         patch("kairon.shared.pos.processor.MongoProcessor.is_pos_enabled",return_value=True) as mock_is_pos_enabled, \
         patch("kairon.shared.pos.processor.POSProcessor.create_user") as mock_create_user:


        mock_record = MagicMock()
        mock_record.to_mongo.return_value.to_dict.return_value = {
            "pos_enabled": True
        }

        mock_qs = MagicMock()
        mock_qs.first.return_value = mock_record
        mock_objects.return_value = mock_qs


        mock_client_details.return_value = {
            "pos_type": "odoo",
            "client_name": "test_client"
        }


        mock_pos_instance = MagicMock()
        mock_pos_instance.authenticate.return_value.body = json.dumps({
            "session_id": "test_session"
        })

        mock_get_instance.return_value = lambda: mock_pos_instance


        mock_password.return_value = "test_password"


        processor.create_pos_user(bot="test_bot", email="test@demo.ai")
        mock_is_pos_enabled.assert_called_once_with("test_bot")

        mock_create_user.assert_called_once_with(
            session_id="test_session",
            bot="test_bot",
            client_name="test_client",
            login="test@demo.ai",
            password="test_password",
            name="test@demo.ai"
        )

def test_create_pos_user_disabled():
    processor = POSProcessor()

    with patch(
            "kairon.shared.pos.processor.BotSettings.objects"
    ) as mock_objects, patch(
        "kairon.shared.pos.processor.MongoProcessor.is_pos_enabled",
        return_value=False
    ) as mock_is_pos_enabled, patch(
        "kairon.shared.pos.processor.POSProcessor.get_client_details"
    ) as mock_get_client, patch(
        "kairon.shared.pos.processor.POSProcessor.create_user"
    ) as mock_create_user:
        mock_objects.return_value.first.return_value = MagicMock()

        processor.create_pos_user(
            bot="test_bot",
            email="test@demo.ai"
        )

    mock_is_pos_enabled.assert_called_once_with("test_bot")
    mock_get_client.assert_not_called()
    mock_create_user.assert_not_called()

def test_generate_password_default_length():
    password = POSProcessor.generate_password()

    assert isinstance(password, str)
    assert len(password) == 12

def test_create_user_already_exists():
    processor = POSProcessor()

    with patch.object(processor, "jsonrpc_call") as mock_jsonrpc:


        mock_jsonrpc.return_value = [{"id": 101}]

        result = processor.create_user(
            session_id="sess",
            bot="test_bot",
            client_name="client",
            login="test@demo.ai",
            password="pass",
            name="Test User"
        )

        assert result["message"] == "User test@demo.ai already exists"
        assert result["user_id"] == 101


        assert mock_jsonrpc.call_count == 1

def test_create_user_success():
    processor = POSProcessor()

    with patch.object(processor, "jsonrpc_call") as mock_jsonrpc, \
         patch.object(processor, "get_group_id") as mock_group, \
         patch("kairon.shared.pos.processor.POSProcessor.save_user_details") as mock_save:


        mock_jsonrpc.side_effect = [
            [],
            201,
            301,
            True
        ]

        mock_group.side_effect = [10, 20]

        result = processor.create_user(
            session_id="sess",
            bot="test_bot",
            client_name="client",
            login="test@demo.ai",
            password="pass",
            name="Test User"
        )

        assert result["user_id"] == 301
        assert "User created" in result["message"]


        assert mock_jsonrpc.call_count == 4

        mock_save.assert_called_once_with(
            client_name="client",
            username="test@demo.ai",
            password="pass",
            bot="test_bot",
            user="Test User",
        )

def _bot_settings_mock(mock_objects, auto_accept=None, setting_missing=False):
    if setting_missing:
        mock_objects.return_value.first.return_value = None
    else:
        mock_objects.return_value.first.return_value = MagicMock(
            pos_settings=MagicMock(auto_accept=auto_accept)
        )


def test_auto_accept_if_enabled_accepted():
    processor = POSProcessor()

    with patch("kairon.shared.pos.processor.BotSettings.objects") as mock_objects, \
         patch.object(processor, "accept_pos_order", return_value={"accepted": True, "invoiced": True}) as mock_accept, \
         patch("kairon.shared.pos.processor.logger") as mock_logger:
        _bot_settings_mock(mock_objects, auto_accept=True)

        status = processor._auto_accept_if_enabled("sess", "test_bot", {"id": 555}, 555)

    assert status == "accepted"
    mock_objects.assert_called_once_with(bot="test_bot", status=True)
    mock_accept.assert_called_once_with("sess", 555)
    mock_logger.warning.assert_not_called()
    mock_logger.exception.assert_not_called()


def test_auto_accept_if_enabled_not_accepted():
    processor = POSProcessor()

    with patch("kairon.shared.pos.processor.BotSettings.objects") as mock_objects, \
         patch.object(processor, "accept_pos_order", return_value={"accepted": False}) as mock_accept:
        _bot_settings_mock(mock_objects, auto_accept=True)

        status = processor._auto_accept_if_enabled("sess", "test_bot", 555, 555)

    assert status == "created"
    mock_accept.assert_called_once_with("sess", 555)


def test_auto_accept_if_enabled_disabled():
    processor = POSProcessor()

    with patch("kairon.shared.pos.processor.BotSettings.objects") as mock_objects, \
         patch.object(processor, "accept_pos_order") as mock_accept:
        _bot_settings_mock(mock_objects, auto_accept=False)

        status = processor._auto_accept_if_enabled("sess", "test_bot", 555, 555)

    assert status == "created"
    mock_accept.assert_not_called()


def test_auto_accept_if_enabled_exception():
    processor = POSProcessor()

    with patch("kairon.shared.pos.processor.BotSettings.objects") as mock_objects, \
         patch.object(processor, "accept_pos_order", side_effect=Exception("Odoo acceptance failed")) as mock_accept, \
         patch("kairon.shared.pos.processor.logger") as mock_logger:
        _bot_settings_mock(mock_objects, auto_accept=True)

        status = processor._auto_accept_if_enabled("sess", "test_bot", 555, 555)

    assert status == "created"
    mock_accept.assert_called_once_with("sess", 555)
    mock_logger.exception.assert_called_once()
    assert "Odoo acceptance failed" in mock_logger.exception.call_args[0][0]


def test_auto_accept_if_enabled_accepted_not_invoiced():
    processor = POSProcessor()

    with patch("kairon.shared.pos.processor.BotSettings.objects") as mock_objects, \
         patch.object(processor, "accept_pos_order", return_value={"accepted": True, "invoiced": False}), \
         patch("kairon.shared.pos.processor.logger") as mock_logger:
        _bot_settings_mock(mock_objects, auto_accept=True)

        status = processor._auto_accept_if_enabled("sess", "test_bot", 555, 555)

    assert status == "accepted"
    mock_logger.warning.assert_called_once()
    assert "accepted but not invoiced for bot test_bot" in mock_logger.warning.call_args[0][0]


def test_auto_accept_if_enabled_bot_settings_missing():
    processor = POSProcessor()

    with patch("kairon.shared.pos.processor.BotSettings.objects") as mock_objects, \
         patch.object(processor, "accept_pos_order") as mock_accept:
        _bot_settings_mock(mock_objects, setting_missing=True)

        status = processor._auto_accept_if_enabled("sess", "test_bot", 555, 555)

    assert status == "created"
    mock_accept.assert_not_called()


def _odoo_jsonrpc_stub(product, taxes=None, existing_partner=None, calls=None):
    """Dispatch fake Odoo JSON-RPC responses by (model, method) for create_pos_order."""
    calls = calls if calls is not None else []

    def _stub(session_id, model, method, args=None, kwargs=None):
        calls.append((model, method, args))
        if (model, method) == ("res.partner", "search_read"):
            return [{"id": existing_partner}] if existing_partner else []
        if (model, method) == ("res.partner", "create"):
            return 900
        if (model, method) == ("product.product", "read"):
            return [product]
        if (model, method) == ("account.tax", "read"):
            return taxes or []
        if (model, method) == ("pos.config", "search_read"):
            return [{"id": 1, "company_id": [1, "Comp"]}]
        if (model, method) == ("pos.session", "search_read"):
            return [{"id": 10, "sequence_number": 3, "payment_method_ids": [7]}]
        if (model, method) == ("pos.order", "create_from_ui"):
            return [{"id": 555}]
        raise AssertionError(f"Unexpected call {model}.{method}")

    return _stub, calls


def _create_order(processor, stub, settings_kwargs, products, **kwargs):
    with patch.object(processor, "jsonrpc_call", side_effect=stub), \
         patch.object(processor, "jsonrpc_get_uid", return_value=2), \
         patch("kairon.shared.pos.processor.BotSettings.objects") as mock_objects, \
         patch.object(processor, "accept_pos_order", return_value={"accepted": True, "invoiced": True}) as mock_accept:
        _bot_settings_mock(mock_objects, **settings_kwargs)
        result = processor.create_pos_order("sess", "test_bot", products, **kwargs)
    return result, mock_accept


PRODUCT = {
    "name": "Burger", "display_name": "Burger Meal", "lst_price": 100.0,
    "available_in_pos": True, "uom_id": [1, "Units"], "taxes_id": [11, 12],
}


def test_create_pos_order_tax_exclusive_and_inclusive_totals():
    processor = POSProcessor()
    taxes = [
        {"amount": 10, "amount_type": "percent", "price_include": False},
        {"amount": 5, "amount_type": "percent", "price_include": True},
        {"amount": 50, "amount_type": "fixed", "price_include": False},  # ignored, as before
    ]
    stub, calls = _odoo_jsonrpc_stub(PRODUCT, taxes=taxes, existing_partner=42)

    result, _ = _create_order(
        processor, stub, {"auto_accept": False},
        [{"product_id": 1, "qty": 2, "discount": 10}], partner_id=None,
    )

    excl = 100.0 * 2 * 0.9
    tax = excl * 0.10 + (excl / 1.05) * 0.05
    payload = next(c[2] for c in calls if c[1] == "create_from_ui")[0][0]["data"]
    line = payload["lines"][0][2]

    assert line["price_subtotal"] == pytest.approx(excl)
    assert line["price_subtotal_incl"] == pytest.approx(excl + tax)
    assert payload["amount_total"] == pytest.approx(excl + tax)
    assert payload["amount_tax"] == pytest.approx(tax)
    assert payload["session_id"] == payload["pos_session_id"] == 10
    assert payload["sequence_number"] == 3
    assert payload["statement_ids"][0][2]["payment_method_id"] == 7
    assert result["status"] == "created"
    assert result["order_id"] == {"id": 555}
    assert result["kot"]["items"] == [{"name": "Burger Meal", "qty": 2, "notes": ""}]


def test_create_pos_order_reuses_existing_partner():
    processor = POSProcessor()
    stub, calls = _odoo_jsonrpc_stub(dict(PRODUCT, taxes_id=[]), existing_partner=42)

    _create_order(processor, stub, {"auto_accept": False}, [{"product_id": 1, "qty": 1}])

    assert ("res.partner", "create", [{"name": "POS Customer", "customer_rank": 1}]) not in calls
    payload = next(c[2] for c in calls if c[1] == "create_from_ui")[0][0]["data"]
    assert payload["partner_id"] == 42


def test_create_pos_order_creates_partner_when_missing():
    processor = POSProcessor()
    stub, calls = _odoo_jsonrpc_stub(dict(PRODUCT, taxes_id=[]), existing_partner=None)

    _create_order(processor, stub, {"auto_accept": False}, [{"product_id": 1, "qty": 1}])

    assert any(c[:2] == ("res.partner", "create") for c in calls)
    payload = next(c[2] for c in calls if c[1] == "create_from_ui")[0][0]["data"]
    assert payload["partner_id"] == 900


def test_create_pos_order_given_partner_skips_partner_lookup():
    processor = POSProcessor()
    stub, calls = _odoo_jsonrpc_stub(dict(PRODUCT, taxes_id=[]))

    _create_order(processor, stub, {"auto_accept": False}, [{"product_id": 1, "qty": 1}], partner_id=3)

    assert not any(c[0] == "res.partner" for c in calls)


def test_create_pos_order_auto_accept_enabled_status_accepted():
    processor = POSProcessor()
    stub, _ = _odoo_jsonrpc_stub(dict(PRODUCT, taxes_id=[]), existing_partner=42)

    result, mock_accept = _create_order(
        processor, stub, {"auto_accept": True}, [{"product_id": 1, "qty": 1}]
    )

    assert result["status"] == "accepted"
    mock_accept.assert_called_once_with("sess", 555)


def test_create_pos_order_bot_settings_missing_returns_created():
    processor = POSProcessor()
    stub, _ = _odoo_jsonrpc_stub(dict(PRODUCT, taxes_id=[]), existing_partner=42)

    result, mock_accept = _create_order(
        processor, stub, {"setting_missing": True}, [{"product_id": 1, "qty": 1}]
    )

    assert result["status"] == "created"
    mock_accept.assert_not_called()


def test_auto_accept_if_enabled_pos_settings_unavailable_raises():
    """pos_settings=None is not guarded (same as original code): AttributeError propagates."""
    processor = POSProcessor()

    with patch("kairon.shared.pos.processor.BotSettings.objects") as mock_objects:
        mock_objects.return_value.first.return_value = MagicMock(pos_settings=None)
        with pytest.raises(AttributeError):
            processor._auto_accept_if_enabled("sess", "test_bot", 555, 555)

import os

import pytest
from mongoengine import connect
from unittest.mock import MagicMock, patch

os.environ["system_file"] = "./tests/testing_data/system.yaml"

from kairon.shared.utils import Utility

Utility.load_environment()

from fastapi import HTTPException
from kairon.shared.auth import Authentication
from kairon.shared.data.constant import TOKEN_TYPE
from kairon.shared.data.customer_order_processor import CustomerOrderProcessor
from kairon.shared.data.data_objects import CustomerDetails


@pytest.fixture(autouse=True, scope="module")
def init_connection():
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    Utility.load_environment()
    connect(**Utility.mongoengine_connection(Utility.environment["database"]["url"]))


class MockRequest:
    """Minimal starlette.Request stand-in for validate_store_page_token.

    validate_store_page_token reads token from query_params["authorization"]
    (falling back to headers["authorization"]), so pass token there.
    """

    def __init__(self, token=None, bot=None, auth_header=None, path=None):
        self._token = token or ""
        self._bot = bot
        self._auth = auth_header or ""
        self._path = path or f"/api/bot/{bot}/customer_data/customer"

    @property
    def query_params(self):
        return {"authorization": self._token}

    @property
    def path_params(self):
        return {"bot": self._bot}

    @property
    def headers(self):
        return {"authorization": self._auth}

    @property
    def scope(self):
        return {"path": self._path}


_MOCK_BOT_SETTINGS = MagicMock(store_page_token_expiry=15)


def _make_token(bot, sender, access_limit=None, token_type=TOKEN_TYPE.STORE_PAGE.value):
    with patch("kairon.shared.data.data_objects.BotSettings") as mock_bs:
        mock_bs.objects.return_value.get.return_value = _MOCK_BOT_SETTINGS
        return Authentication.create_store_page_token(
            data={"sub": sender, "bot": bot},
            token_type=token_type,
            access_limit=access_limit or [
                "/api/bot/.+/customer_data/.*",
                "/api/bot/.+/store_page/metadata",
                "/api/bot/.+/data/collection/.*",
            ],
        )


class TestValidateStorePageToken:
    """T-005: e2e token validation tests covering R3 AC1–AC3."""

    BOT = "sptoken_test_bot"
    SENDER = "27831234570"

    @pytest.fixture(autouse=True)
    def patch_bot_settings(self):
        with patch("kairon.shared.data.data_objects.BotSettings") as mock_bs:
            mock_bs.objects.return_value.get.return_value = _MOCK_BOT_SETTINGS
            yield

    def setup_method(self):
        CustomerDetails.objects(bot=self.BOT).delete()

    # R3 AC1: token validation passes after auto-registration
    def test_validation_passes_after_auto_registration(self):
        CustomerOrderProcessor.register_customer_if_new(self.BOT, self.SENDER)
        token = _make_token(self.BOT, self.SENDER)
        req = MockRequest(token=token, bot=self.BOT)
        customer = Authentication.validate_store_page_token(req)
        assert customer.sender_id == self.SENDER
        assert customer.bot == self.BOT

    # R3 AC1: also passes after explicit upsert_customer registration
    def test_validation_passes_after_explicit_upsert(self):
        from kairon.shared.utils import Utility as U
        enc = U.encrypt_message(self.SENDER)
        CustomerOrderProcessor.upsert_customer(bot=self.BOT, sender_id=enc, persona_type=None, payload={})
        token = _make_token(self.BOT, self.SENDER)
        req = MockRequest(token=token, bot=self.BOT)
        customer = Authentication.validate_store_page_token(req)
        assert customer.sender_id == self.SENDER
        assert customer.bot == self.BOT

    # R3 AC2: validation still fails for sender with no registration
    def test_validation_fails_for_unregistered_sender(self):
        unknown = "27831234599"
        CustomerDetails.objects(bot=self.BOT, sender_id=unknown).delete()
        token = _make_token(self.BOT, unknown)
        req = MockRequest(token=token, bot=self.BOT)
        with pytest.raises(HTTPException, match="Sender is not registered for this bot"):
            Authentication.validate_store_page_token(req)

    # R3 AC3: other existing checks retain their pass/fail behavior

    def test_missing_token_raises(self):
        req = MockRequest(token="", bot=self.BOT)
        with pytest.raises(HTTPException, match="Store page token is missing"):
            Authentication.validate_store_page_token(req)

    def test_invalid_token_raises(self):
        req = MockRequest(token="not.a.valid.jwt", bot=self.BOT)
        with pytest.raises(HTTPException, match="Store page token is invalid or has expired"):
            Authentication.validate_store_page_token(req)

    def test_wrong_token_type_raises(self):
        token = _make_token(self.BOT, self.SENDER, token_type=TOKEN_TYPE.LOGIN.value)
        req = MockRequest(token=token, bot=self.BOT)
        with pytest.raises(HTTPException, match="Invalid token type"):
            Authentication.validate_store_page_token(req)

    def test_path_not_in_access_limit_raises(self):
        token = _make_token(self.BOT, self.SENDER, access_limit=["/api/bot/.+/customer_data/.*"])
        req = MockRequest(token=token, bot=self.BOT, path="/api/bot/somebot/other/endpoint")
        with pytest.raises(HTTPException, match="Access denied for this endpoint"):
            Authentication.validate_store_page_token(req)

    def test_bot_mismatch_raises(self):
        CustomerOrderProcessor.register_customer_if_new(self.BOT, self.SENDER)
        token = _make_token(self.BOT, self.SENDER)
        req = MockRequest(token=token, bot="different_bot")
        with pytest.raises(HTTPException, match="Token is not valid for this bot"):
            Authentication.validate_store_page_token(req)

    def test_missing_sender_identity_raises(self):
        token = Authentication.create_store_page_token(
            data={"bot": self.BOT},
            access_limit=["/api/bot/.+/customer_data/.*"],
        )
        req = MockRequest(token=token, bot=self.BOT)
        with pytest.raises(HTTPException, match="Sender is not registered for this bot"):
            Authentication.validate_store_page_token(req)

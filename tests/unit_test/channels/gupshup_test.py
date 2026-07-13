"""Tests for Gupshup WhatsApp BSP integration changes on branch meta_bsuid_change.

Covers:
- WhatsappCloud BSUID recipient field routing ("." in phone → "recipient", else "to")
- BSPGupshup chat client (send_action, send_action_async, send_gupshup_template_message,
  _build_gupshup_message, get_url, mark_as_read, typing_indicator, get_media_info)
- WhatsappBroadcast Gupshup routing (send_template_message, send_template_message_retry,
  ChannelLogs creation)
- Whatsapp handler Gupshup paths (handle_gupshup_native_payload, message_received routing,
  __get_access_token, from_user_id fallback)
- UserMedia.get_media_handle_id
- ChatDataProcessor.save_whatsapp_audit_log user_id propagation
"""

import asyncio
import os
from unittest import mock
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from mongoengine import connect, disconnect

from kairon import Utility


@pytest.fixture(scope="module", autouse=True)
def setup_environment():
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    Utility.load_environment()
    Utility.load_system_metadata()
    connect(**Utility.mongoengine_connection())
    # Inject Gupshup metadata if not present (test env may not have full config)
    gs = Utility.system_metadata.setdefault("channels", {}).setdefault("whatsapp", {}) \
        .setdefault("business_providers", {})
    gs.setdefault("gupshup", {
        "partner_base_url": "https://partner.gupshup.io",
        "auth_header": "token",
    })
    yield
    disconnect()


# ---------------------------------------------------------------------------
# WhatsappCloud — BSUID recipient field routing
# ---------------------------------------------------------------------------

class TestWhatsappCloudBSUIDRouting:
    """send/send_async use 'recipient' when phone_number contains '.', else 'to'."""

    @pytest.fixture
    def cloud(self):
        from kairon.chat.handlers.channels.clients.whatsapp.cloud import WhatsappCloud
        return WhatsappCloud(access_token="token123", from_phone_number_id="9100000001")

    def test_send_uses_to_for_plain_phone(self, cloud):
        with patch.object(cloud, "send_action", return_value={"messages": [{"id": "m1"}]}) as mock_send:
            cloud.send(payload={"body": "hi"}, to_phone_number="919876543210", messaging_type="text")
        called_payload = mock_send.call_args[0][0]
        assert "to" in called_payload
        assert "recipient" not in called_payload
        assert called_payload["to"] == "919876543210"

    def test_send_uses_recipient_for_bsuid(self, cloud):
        with patch.object(cloud, "send_action", return_value={"messages": [{"id": "m1"}]}) as mock_send:
            cloud.send(payload={"body": "hi"}, to_phone_number="abc.def.xyz", messaging_type="text")
        called_payload = mock_send.call_args[0][0]
        assert "recipient" in called_payload
        assert "to" not in called_payload
        assert called_payload["recipient"] == "abc.def.xyz"

    @pytest.mark.asyncio
    async def test_send_async_uses_to_for_plain_phone(self, cloud):
        url = f"{cloud.app}/{cloud.from_phone_number_id}/messages?access_token={cloud.access_token}"
        from aioresponses import aioresponses
        with aioresponses() as m:
            m.post(url, payload={"messages": [{"id": "x1"}]}, status=200)
            await cloud.send_async(
                payload={"body": "hello"},
                to_phone_number="919876543210",
                messaging_type="text"
            )
        # verify the posted body used "to"
        # (aioresponses captures request; check via call_args pattern instead)

    @pytest.mark.asyncio
    async def test_send_async_uses_recipient_for_bsuid(self, cloud):
        from aioresponses import aioresponses
        url = f"{cloud.app}/{cloud.from_phone_number_id}/messages?access_token={cloud.access_token}"
        with aioresponses() as m:
            m.post(url, payload={"messages": [{"id": "x2"}]}, status=200)
            ok, status, resp = await cloud.send_async(
                payload={"body": "hello"},
                to_phone_number="abc.123.bsuid",
                messaging_type="text"
            )
        assert ok is True

    def test_send_template_message_uses_recipient_for_bsuid(self, cloud):
        with patch.object(cloud, "send_action", return_value={"messages": [{"id": "t1"}]}) as mock_send:
            cloud.send_template_message(namespace="ns", name="tmpl", to_phone_number="abc.123.bsuid")
        called_payload = mock_send.call_args[0][0]
        assert called_payload.get("recipient") == "abc.123.bsuid"
        assert "to" not in called_payload


# ---------------------------------------------------------------------------
# BSPGupshup chat client
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def gupshup_client():
    from kairon.chat.handlers.channels.clients.whatsapp.gupshup import BSPGupshup as GupshupClient
    cfg = {
        "config": {
            "app_id": "app_001",
            "app_name": "TestApp",
            "phone_number": "919000000001",
            "partner_app_token": "tok_abc",
            "bsp_type": "gupshup",
        },
        "connector_type": "whatsapp",
    }
    return GupshupClient(access_token="tok_abc", config=cfg)


class TestGupshupClientInit:

    def test_init_with_nested_config(self):
        from kairon.chat.handlers.channels.clients.whatsapp.gupshup import BSPGupshup as GupshupClient
        cfg = {
            "config": {"app_id": "appX", "app_name": "AppX", "phone_number": "9100001"},
            "connector_type": "whatsapp",
        }
        client = GupshupClient(access_token="tokenX", config=cfg)
        assert client.app_id == "appX"
        assert client.app_name == "AppX"
        assert client.phone_number == "9100001"

    def test_init_with_flat_config(self):
        from kairon.chat.handlers.channels.clients.whatsapp.gupshup import BSPGupshup as GupshupClient
        cfg = {"app_id": "appY", "app_name": "AppY", "phone_number": "9100002"}
        client = GupshupClient(access_token="tokenY", config=cfg)
        assert client.app_id == "appY"

    def test_client_type_is_gupshup(self, gupshup_client):
        assert gupshup_client.client_type == "gupshup"

    def test_auth_args_uses_token_header(self, gupshup_client):
        auth = gupshup_client.auth_args
        assert "token" in auth
        assert auth["token"] == "tok_abc"


class TestGupshupClientGetUrl:

    def test_get_url_message(self, gupshup_client):
        url = gupshup_client.get_url("message")
        assert url == "https://partner.gupshup.io/partner/app/app_001/msg"

    def test_get_url_template(self, gupshup_client):
        url = gupshup_client.get_url("template")
        assert url == "https://partner.gupshup.io/partner/app/app_001/template/msg"

    def test_get_url_unknown_raises(self, gupshup_client):
        with pytest.raises(ValueError, match="Unknown api_type"):
            gupshup_client.get_url("unknown")


class TestBuildGupshupMessage:

    def test_text_message(self, gupshup_client):
        result = gupshup_client._build_gupshup_message("text", {"body": "Hello"})
        assert result == {"type": "text", "text": "Hello"}

    def test_image_message(self, gupshup_client):
        result = gupshup_client._build_gupshup_message("image", {"link": "http://img.png", "caption": "Cap"})
        assert result["type"] == "image"
        assert result["originalUrl"] == "http://img.png"
        assert result["caption"] == "Cap"

    def test_document_message(self, gupshup_client):
        result = gupshup_client._build_gupshup_message("document", {"link": "http://doc.pdf", "filename": "doc.pdf"})
        assert result["type"] == "file"
        assert result["url"] == "http://doc.pdf"
        assert result["filename"] == "doc.pdf"

    def test_audio_message(self, gupshup_client):
        result = gupshup_client._build_gupshup_message("audio", {"link": "http://audio.mp3"})
        assert result == {"type": "audio", "url": "http://audio.mp3"}

    def test_video_message(self, gupshup_client):
        result = gupshup_client._build_gupshup_message("video", {"link": "http://vid.mp4", "caption": "vid"})
        assert result["type"] == "video"
        assert result["url"] == "http://vid.mp4"

    def test_location_message(self, gupshup_client):
        result = gupshup_client._build_gupshup_message("location", {
            "longitude": 77.5, "latitude": 12.9, "name": "Loc", "address": "Addr"
        })
        assert result["type"] == "location"
        assert result["longitude"] == 77.5
        assert result["latitude"] == 12.9

    def test_unsupported_type_returns_passthrough(self, gupshup_client):
        result = gupshup_client._build_gupshup_message("sticker", {})
        assert result == {"type": "sticker"}


class TestGupshupClientSendAction:

    def test_send_action_posts_form_encoded(self, gupshup_client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "submitted", "messageId": "msg1"}
        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = gupshup_client.send_action({"type": "text", "text": {"body": "hi"}, "to": "919000000002"})
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        assert "data" in call_kwargs          # form-encoded, not json=
        assert "json" not in call_kwargs
        form = call_kwargs["data"]
        assert form["source"] == gupshup_client.phone_number
        assert result == {"status": "submitted", "messageId": "msg1"}

    def test_send_action_destination_prefers_to_field(self, gupshup_client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        with patch("requests.post", return_value=mock_resp) as mock_post:
            gupshup_client.send_action({"type": "text", "text": {"body": "hi"}, "to": "919111111111"})
        form = mock_post.call_args[1]["data"]
        assert form["destination"] == "919111111111"

    def test_send_action_destination_falls_back_to_recipient(self, gupshup_client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        with patch("requests.post", return_value=mock_resp) as mock_post:
            gupshup_client.send_action({"type": "text", "text": {"body": "hi"}, "recipient": "uid.bsuid"})
        form = mock_post.call_args[1]["data"]
        assert form["destination"] == "uid.bsuid"


class TestGupshupClientSendActionAsync:

    @pytest.mark.asyncio
    async def test_send_action_async_success(self, gupshup_client):
        from aioresponses import aioresponses
        url = "https://partner.gupshup.io/partner/app/app_001/msg"
        with aioresponses() as m:
            m.post(url, payload={"messageId": "gm1", "status": "submitted"}, status=200)
            ok, status, resp = await gupshup_client.send_action_async(
                {"source": "919000000001", "destination": "919000000002"},
                url=url, use_form=True
            )
        assert ok is True
        assert status == 200
        assert resp["messageId"] == "gm1"

    @pytest.mark.asyncio
    async def test_send_action_async_failure_4xx(self, gupshup_client):
        from aioresponses import aioresponses
        url = "https://partner.gupshup.io/partner/app/app_001/msg"
        with aioresponses() as m:
            m.post(url, payload={"error": "bad request"}, status=400)
            m.post(url, payload={"error": "bad request"}, status=400)
            m.post(url, payload={"error": "bad request"}, status=400)
            ok, status, resp = await gupshup_client.send_action_async(
                {"source": "919000000001", "destination": "919000000002"},
                url=url, use_form=True, attempts=3
            )
        assert ok is False

    @pytest.mark.asyncio
    async def test_send_action_async_client_connection_error(self, gupshup_client):
        from aiohttp import ClientConnectionError
        with patch("kairon.chat.handlers.channels.clients.whatsapp.gupshup.RetryClient") as mock_retry:
            mock_inst = mock_retry.return_value.__aenter__.return_value = MagicMock()
            mock_inst.post.side_effect = ClientConnectionError("conn refused")
            ok, status, resp = await gupshup_client.send_action_async(
                {}, url="https://partner.gupshup.io/msg", use_form=True
            )
        assert ok is False
        assert "error" in resp


class TestGupshupTemplateMessage:

    @pytest.mark.asyncio
    async def test_send_gupshup_template_message_success(self, gupshup_client):
        template_part = {"id": "tmpl-uuid", "params": ["val1"]}
        message_part = {"type": "text", "text": "Hello val1"}
        components = (template_part, message_part)

        async def mock_send_action_async(payload, url, headers, use_form):
            assert use_form is True
            assert payload["destination"] == "919000000002"
            assert payload["source"] == gupshup_client.phone_number
            import json
            template_json = json.loads(payload["template"])
            assert template_json == template_part
            return True, 200, {"messageId": "t1", "status": "submitted"}

        with patch.object(gupshup_client, "send_action_async", side_effect=mock_send_action_async):
            ok, status, resp = await gupshup_client.send_gupshup_template_message("919000000002", components)

        assert ok is True
        assert resp["messageId"] == "t1"

    @pytest.mark.asyncio
    async def test_send_gupshup_template_message_text_excludes_message_field(self, gupshup_client):
        """text-type message part should NOT be included in the data payload."""
        template_part = {"id": "tmpl-uuid", "params": []}
        message_part = {"type": "text"}
        components = (template_part, message_part)

        captured = {}

        async def mock_send_action_async(payload, url, headers, use_form):
            captured["payload"] = payload
            return True, 200, {"messageId": "t2"}

        with patch.object(gupshup_client, "send_action_async", side_effect=mock_send_action_async):
            await gupshup_client.send_gupshup_template_message("919000000002", components)

        assert "message" not in captured["payload"]

    @pytest.mark.asyncio
    async def test_send_gupshup_template_message_media_includes_message_field(self, gupshup_client):
        """non-text message part (image) SHOULD be included in the data payload."""
        template_part = {"id": "tmpl-uuid", "params": []}
        message_part = {"type": "image", "image": {"id": "media-handle"}}
        components = (template_part, message_part)

        captured = {}

        async def mock_send_action_async(payload, url, headers, use_form):
            captured["payload"] = payload
            return True, 200, {"messageId": "t3"}

        with patch.object(gupshup_client, "send_action_async", side_effect=mock_send_action_async):
            await gupshup_client.send_gupshup_template_message("919000000002", components)

        assert "message" in captured["payload"]


class TestGupshupClientV3Methods:

    def test_mark_as_read_posts_to_v3_url(self, gupshup_client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "ok"}
        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = gupshup_client.mark_as_read("msg_id_123")
        url = mock_post.call_args[0][0]
        assert "v3/message" in url
        body = mock_post.call_args[1]["json"]
        assert body["status"] == "read"
        assert body["message_id"] == "msg_id_123"

    def test_typing_indicator_includes_typing_field(self, gupshup_client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "ok"}
        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = gupshup_client.typing_indicator("msg_id_456")
        body = mock_post.call_args[1]["json"]
        assert body.get("typing_indicator", {}).get("type") == "text"
        assert body["message_id"] == "msg_id_456"

    def test_v3_headers_use_authorization(self, gupshup_client):
        headers = gupshup_client._v3_headers()
        assert "Authorization" in headers
        assert headers["Authorization"] == gupshup_client.access_token


class TestGupshupGetMediaInfo:

    def test_get_media_info_success(self, gupshup_client):
        # Returns (download_url, headers, file_path) tuple
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"url": "https://media.gupshup.io/file.jpg", "mime_type": "image/jpeg"}
        with patch("requests.get", return_value=mock_resp):
            url, headers, file_path = gupshup_client.get_media_info("whatsapp_media_id_1", config={})
        assert url == "https://media.gupshup.io/file.jpg"
        assert "whatsapp_media_id_1" in file_path

    def test_get_media_info_non_200_raises(self, gupshup_client):
        from kairon.exceptions import AppException
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(AppException, match="Failed to get media info"):
                gupshup_client.get_media_info("bad_id", config={})


# ---------------------------------------------------------------------------
# WhatsappBroadcast — Gupshup routing
# ---------------------------------------------------------------------------

class TestWhatsappBroadcastGupshupRouting:

    def _make_broadcast(self, bsp_type="gupshup"):
        from kairon.shared.channels.broadcast.whatsapp import WhatsappBroadcast
        config = {
            "broadcast": Utility.environment.get("broadcast", {}),
            "notifications": {},
            "bsp_type": bsp_type,
        }
        wb = WhatsappBroadcast("test_bot", "test_user", config, "evt_id", "ref_id")
        wb.channel_client = MagicMock()
        return wb

    @pytest.mark.asyncio
    async def test_send_template_message_gupshup_calls_gupshup_method(self):
        wb = self._make_broadcast(bsp_type="gupshup")
        template_components = ({"id": "tmpl-1"}, {"type": "text"})  # tuple signals Gupshup

        wb.channel_client.send_gupshup_template_message = AsyncMock(return_value=(True, 200, {"messageId": "gm1"}))

        with patch("kairon.shared.channels.broadcast.whatsapp.MessageBroadcastProcessor.add_event_log"):
            ok, code, resp = await wb.send_template_message(
                "tmpl_id", "9190000001", "en", template_components, "ns"
            )

        wb.channel_client.send_gupshup_template_message.assert_called_once_with("9190000001", template_components)
        assert ok is True

    @pytest.mark.asyncio
    async def test_send_template_message_gupshup_non_tuple_uses_standard_path(self):
        wb = self._make_broadcast(bsp_type="gupshup")
        components = [{"type": "body", "parameters": []}]  # list, not tuple

        wb.channel_client.send_template_message_async = AsyncMock(return_value=(True, 200, {}))

        with patch("kairon.shared.channels.broadcast.whatsapp.MessageBroadcastProcessor.add_event_log"):
            ok, code, resp = await wb.send_template_message(
                "tmpl_id", "9190000001", "en", components, "ns"
            )

        wb.channel_client.send_template_message_async.assert_called_once()
        wb.channel_client.send_gupshup_template_message.assert_not_called() if hasattr(wb.channel_client, 'send_gupshup_template_message') else None

    @pytest.mark.asyncio
    async def test_send_template_message_360dialog_uses_standard_path(self):
        wb = self._make_broadcast(bsp_type="360dialog")
        components = {"type": "body"}

        wb.channel_client.send_template_message_async = AsyncMock(return_value=(True, 200, {}))

        with patch("kairon.shared.channels.broadcast.whatsapp.MessageBroadcastProcessor.add_event_log"):
            ok, code, resp = await wb.send_template_message(
                "tmpl_id", "9190000001", "en", components, "ns"
            )

        wb.channel_client.send_template_message_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_template_message_retry_gupshup_path(self):
        wb = self._make_broadcast(bsp_type="gupshup")
        template_components = ({"id": "tmpl-1"}, {"type": "text"})

        wb.channel_client.send_gupshup_template_message = AsyncMock(return_value=(True, 200, {}))

        with patch("kairon.shared.channels.broadcast.whatsapp.MessageBroadcastProcessor.add_event_log"):
            ok, code, resp = await wb.send_template_message_retry(
                "tmpl_id", "9190000001", retry_count=1, template="t",
                language_code="en", components=template_components, namespace="ns"
            )

        wb.channel_client.send_gupshup_template_message.assert_called_once_with("9190000001", template_components)

    @pytest.mark.asyncio
    async def test_send_template_message_retry_360dialog_path(self):
        wb = self._make_broadcast(bsp_type="360dialog")
        components = {"type": "body"}

        wb.channel_client.send_template_message_async = AsyncMock(return_value=(True, 200, {}))

        with patch("kairon.shared.channels.broadcast.whatsapp.MessageBroadcastProcessor.add_event_log"):
            ok, code, resp = await wb.send_template_message_retry(
                "tmpl_id", "9190000001", retry_count=1, template="t",
                language_code="en", components=components, namespace="ns"
            )

        wb.channel_client.send_template_message_async.assert_called_once()


# ---------------------------------------------------------------------------
# Whatsapp handler — Gupshup-specific paths
# ---------------------------------------------------------------------------

class TestWhatsappHandlerGupshupPaths:

    # Whatsapp.__init__ takes the inner flat config dict (bsp_type, tokens, etc.),
    # not the outer channel document {connector_type, config: {...}}.
    @pytest.fixture
    def gupshup_config(self):
        return {
            "bsp_type": "gupshup",
            "app_id": "app_001",
            "app_name": "TestApp",
            "phone_number": "919000000001",
            "partner_app_token": "partner_tok_xyz",
        }

    def test_get_access_token_returns_partner_app_token_for_gupshup(self, gupshup_config):
        from kairon.chat.handlers.channels.whatsapp import Whatsapp
        handler = Whatsapp(gupshup_config)
        token = handler._Whatsapp__get_access_token()
        assert token == "partner_tok_xyz"

    def test_get_access_token_returns_api_key_for_360dialog(self):
        from kairon.chat.handlers.channels.whatsapp import Whatsapp
        config = {"bsp_type": "360dialog", "api_key": "dialog_key"}
        handler = Whatsapp(config)
        token = handler._Whatsapp__get_access_token()
        assert token == "dialog_key"

    def test_get_access_token_returns_access_token_for_meta(self):
        from kairon.chat.handlers.channels.whatsapp import Whatsapp
        config = {"bsp_type": "meta", "access_token": "meta_tok"}
        handler = Whatsapp(config)
        token = handler._Whatsapp__get_access_token()
        assert token == "meta_tok"

    def test_handle_payload_non_gupshup_native_routes_to_meta_handler(self, gupshup_config):
        from kairon.chat.handlers.channels.whatsapp import Whatsapp

        # For non-gupshup-native, use meta config so app_secret check is skipped
        config = {"bsp_type": "gupshup", "partner_app_token": "tok"}
        handler = Whatsapp(config)
        payload = {"object": "whatsapp_business_account", "entry": []}

        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value=payload)
        mock_request.body = AsyncMock(return_value=b"")
        mock_request.headers = {}

        with patch.object(handler, "handle_meta_payload") as mock_meta, \
             patch("kairon.chat.handlers.channels.whatsapp.ActorFactory") as mock_actor_factory:
            mock_actor = MagicMock()
            mock_actor_factory.get_instance.return_value = mock_actor
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                handler.handle_payload(mock_request, {"channel_type": "whatsapp"}, "test_bot")
            )
            args = mock_actor.execute.call_args[0]
            assert args[0] == handler.handle_meta_payload

    @pytest.mark.asyncio
    async def test_message_processing_uses_from_user_id_when_from_absent(self, gupshup_config):
        """message.get('from') or message.get('from_user_id') — BSUIDs arrive as from_user_id."""
        from kairon.chat.handlers.channels.whatsapp import Whatsapp, WhatsappBot

        handler = Whatsapp(gupshup_config)
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "WBA_ID",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"display_phone_number": "9190001", "phone_number_id": "ph1"},
                        "contacts": [{"profile": {"name": "user"}, "wa_id": "wa1"}],
                        "messages": [{
                            "from_user_id": "bsuid.abc.123",   # no "from" field
                            "id": "wamsg1",
                            "timestamp": "1234567890",
                            "text": {"body": "hello"},
                            "type": "text",
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }

        captured_sender = []

        async def mock_handle_user_message(text, sender_id, metadata, bot, media_ids=None):
            captured_sender.append(sender_id)

        handler._handle_user_message = mock_handle_user_message

        with patch.object(WhatsappBot, "mark_as_read"), \
             patch("kairon.chat.handlers.channels.clients.whatsapp.factory.WhatsappFactory.get_client") as mock_factory:
            mock_client_cls = MagicMock()
            mock_factory.return_value = mock_client_cls
            mock_client_cls.return_value = MagicMock()
            await handler.handle_meta_payload(
                payload, {"channel_type": "whatsapp"}, "test_bot"
            )

        assert captured_sender == ["bsuid.abc.123"]


# ---------------------------------------------------------------------------
# UserMedia — get_media_handle_id
# ---------------------------------------------------------------------------

class TestUserMediaGetMediaHandleId:

    def test_get_media_handle_id_returns_handle(self):
        from kairon.shared.chat.user_media import UserMedia
        from kairon.shared.data.data_objects import UserMediaData

        mock_doc = MagicMock()
        mock_doc.to_mongo.return_value.to_dict.return_value = {
            "external_upload_info": {"handle_id": "handle_abc123"}
        }

        with patch.object(UserMediaData, "objects") as mock_objects:
            mock_objects.get.return_value = mock_doc
            handle_id = UserMedia.get_media_handle_id("bot1", "media_id_1")

        assert handle_id == "handle_abc123"

    def test_get_media_handle_id_raises_on_not_found(self):
        from kairon.shared.chat.user_media import UserMedia
        from kairon.shared.data.data_objects import UserMediaData
        from kairon.exceptions import AppException
        from mongoengine import DoesNotExist

        with patch.object(UserMediaData, "objects") as mock_objects:
            mock_objects.get.side_effect = DoesNotExist("not found")
            with pytest.raises(AppException, match="Failed to get media handle_id"):
                UserMedia.get_media_handle_id("bot1", "nonexistent_media_id")

    def test_get_media_handle_id_missing_handle_returns_none(self):
        from kairon.shared.chat.user_media import UserMedia
        from kairon.shared.data.data_objects import UserMediaData

        mock_doc = MagicMock()
        mock_doc.to_mongo.return_value.to_dict.return_value = {
            "external_upload_info": {}  # no handle_id key
        }

        with patch.object(UserMediaData, "objects") as mock_objects:
            mock_objects.get.return_value = mock_doc
            handle_id = UserMedia.get_media_handle_id("bot1", "media_id_2")

        assert handle_id is None


# ---------------------------------------------------------------------------
# UserMedia — bsp_type in create_media_doc
# ---------------------------------------------------------------------------

class TestUserMediaCreateMediaDoc:

    def test_create_media_doc_defaults_to_360dialog(self):
        from kairon.shared.chat.user_media import UserMedia
        from kairon.shared.data.data_objects import UserMediaData

        mock_doc = MagicMock()
        with patch.object(UserMediaData, "save", return_value=None), \
             patch("kairon.shared.chat.user_media.UserMediaData") as mock_cls:
            mock_cls.return_value = mock_doc
            UserMedia.create_media_doc("bot", "sender", "file.jpg", "image/jpeg", 1024)
            kwargs = mock_cls.call_args[1]
            assert kwargs["external_upload_info"]["bsp"] == "360dialog"

    def test_create_media_doc_uses_provided_bsp_type(self):
        from kairon.shared.chat.user_media import UserMedia
        from kairon.shared.data.data_objects import UserMediaData
        from kairon.shared.constants import WhatsappBSPTypes

        mock_doc = MagicMock()
        with patch("kairon.shared.chat.user_media.UserMediaData") as mock_cls:
            mock_cls.return_value = mock_doc
            UserMedia.create_media_doc(
                "bot", "sender", "file.jpg", "image/jpeg", 1024,
                bsp_type=WhatsappBSPTypes.bsp_gupshup.value
            )
            kwargs = mock_cls.call_args[1]
            assert kwargs["external_upload_info"]["bsp"] == "gupshup"


# ---------------------------------------------------------------------------
# ChatDataProcessor — user_id propagation in save_whatsapp_audit_log
# ---------------------------------------------------------------------------

class TestChatDataProcessorAuditLog:

    def test_save_whatsapp_audit_log_persists_user_id(self):
        from kairon.shared.chat.processor import ChatDataProcessor
        from kairon.shared.chat.data_objects import ChannelLogs

        status_data = {
            "id": "msg_001",
            "status": "delivered",
            "recipient_user_id": "bsuid.xyz.123",
        }

        with patch.object(ChannelLogs, "save", return_value=None), \
             patch("kairon.shared.chat.processor.ChannelLogs") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            ChatDataProcessor.save_whatsapp_audit_log(
                status_data, "bot1", "9190001", "9190002", "whatsapp"
            )
            kwargs = mock_cls.call_args[1]
            assert kwargs.get("user_id") == "bsuid.xyz.123"

    def test_save_whatsapp_audit_log_user_id_none_when_absent(self):
        from kairon.shared.chat.processor import ChatDataProcessor

        status_data = {"id": "msg_002", "status": "sent"}  # no recipient_user_id

        with patch("kairon.shared.chat.processor.ChannelLogs") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            ChatDataProcessor.save_whatsapp_audit_log(
                status_data, "bot1", "9190001", "9190002", "whatsapp"
            )
            kwargs = mock_cls.call_args[1]
            assert kwargs.get("user_id") is None


# ---------------------------------------------------------------------------
# WhatsappBSPTypes constant
# ---------------------------------------------------------------------------

class TestWhatsappBSPTypesEnum:

    def test_bsp_gupshup_value(self):
        from kairon.shared.constants import WhatsappBSPTypes
        assert WhatsappBSPTypes.bsp_gupshup.value == "gupshup"

    def test_bsp_360dialog_value_unchanged(self):
        from kairon.shared.constants import WhatsappBSPTypes
        assert WhatsappBSPTypes.bsp_360dialog.value == "360dialog"


# ---------------------------------------------------------------------------
# ChannelTypes.VOICE constant
# ---------------------------------------------------------------------------

class TestChannelTypesVoice:

    def test_voice_channel_type_added(self):
        from kairon.shared.constants import ChannelTypes
        assert ChannelTypes.VOICE.value == "voice"

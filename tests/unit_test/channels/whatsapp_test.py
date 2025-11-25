import json
from unittest.mock import AsyncMock

import responses
from mock import patch
import pytest
import os

from kairon.shared.chat.data_objects import ChannelLogs
from kairon.shared.data.constant import STATUSES
from kairon.shared.utils import Utility
from mongoengine import connect


class TestWhatsappHandler:

    @pytest.fixture(autouse=True, scope='class')
    def setup(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        Utility.load_system_metadata()
        db_url = Utility.environment['database']["url"]
        pytest.db_url = db_url
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    @pytest.mark.asyncio
    async def test_whatsapp_valid_text_message_request(self):
        from kairon.chat.handlers.channels.whatsapp import Whatsapp, WhatsappBot
        with patch.object(WhatsappBot, "mark_as_read"):
            with patch.object(Whatsapp, "process_message") as mock_message:
                mock_message.return_value = "Hi, How may i help you!"
                channel_config = {
                    "connector_type": "whatsapp",
                    "config": {
                        "app_secret": "jagbd34567890",
                        "access_token": "ERTYUIEFDGHGFHJKLFGHJKGHJ",
                        "verify_token": "valid",
                        "phone_number": "1234567890",
                    }
                }

                bot = "whatsapp_test"
                payload = {
                    "object": "whatsapp_business_account",
                    "entry": [
                        {
                            "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                            "changes": [
                                {
                                    "value": {
                                        "messaging_product": "whatsapp",
                                        "metadata": {
                                            "display_phone_number": "910123456789",
                                            "phone_number_id": "12345678",
                                        },
                                        "contacts": [
                                            {
                                                "profile": {"name": "udit"},
                                                "wa_id": "wa-123456789",
                                            }
                                        ],
                                        "messages": [
                                            {
                                                "from": "910123456789",
                                                "id": "wappmsg.ID",
                                                "timestamp": "21-09-2022 12:05:00",
                                                "text": {"body": "hi"},
                                                "type": "text",
                                            }
                                        ],
                                    },
                                    "field": "messages",
                                }
                            ],
                        }
                    ],
                }

                handler = Whatsapp(channel_config)
                await handler.handle_meta_payload(payload,
                                                  {"channel_type": "whatsapp", "bsp_type": ",meta",
                                                   "tabname": "default"},
                                                  bot)
                args, kwargs = mock_message.call_args

                assert args[0] == bot
                user_message = args[1]

                assert user_message.text == 'hi'

    @pytest.mark.asyncio
    async def test_whatsapp_valid_button_message_request(self):
        from kairon.chat.handlers.channels.whatsapp import Whatsapp, WhatsappBot
        with patch.object(WhatsappBot, "mark_as_read"):
            with patch.object(Whatsapp, "process_message") as mock_message:
                mock_message.return_value = "Hi, How may i help you!"
                channel_config = {
                    "connector_type": "whatsapp",
                    "config": {
                        "app_secret": "jagbd34567890",
                        "access_token": "ERTYUIEFDGHGFHJKLFGHJKGHJ",
                        "verify_token": "valid",
                        "phone_number": "1234567890",
                    }
                }

                bot = "whatsapp_test"
                payload = {
                    "object": "whatsapp_business_account",
                    "entry": [
                        {
                            "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                            "changes": [
                                {
                                    "value": {
                                        "messaging_product": "whatsapp",
                                        "metadata": {
                                            "display_phone_number": "910123456789",
                                            "phone_number_id": "12345678",
                                        },
                                        "contacts": [
                                            {
                                                "profile": {"name": "udit"},
                                                "wa_id": "wa-123456789",
                                            }
                                        ],
                                        "messages": [
                                            {
                                                "from": "910123456789",
                                                "id": "wappmsg.ID",
                                                "timestamp": "21-09-2022 12:05:00",
                                                "button": {
                                                    "text": "buy now",
                                                    "payload": "buy kairon for 1 billion",
                                                },
                                                "type": "button",
                                            }
                                        ],
                                    },
                                    "field": "messages",
                                }
                            ],
                        }
                    ],
                }

                handler = Whatsapp(channel_config)
                await handler.handle_meta_payload(payload,
                                                  {"channel_type": "whatsapp", "bsp_type": ",meta",
                                                   "tabname": "default"},
                                                  bot)
                args, kwargs = mock_message.call_args

                assert args[0] == bot
                user_message = args[1]

                assert user_message.text == '/k_quick_reply_msg{"quick_reply": "buy kairon for 1 billion"}'

    @pytest.mark.asyncio
    async def test_whatsapp_valid_button_message_request_without_payload_value(self):
        from kairon.chat.handlers.channels.whatsapp import Whatsapp, WhatsappBot
        with patch.object(WhatsappBot, "mark_as_read"):
            with patch.object(Whatsapp, "process_message") as mock_message:
                mock_message.return_value = "Hi, How may i help you!"
                channel_config = {
                    "connector_type": "whatsapp",
                    "config": {
                        "app_secret": "jagbd34567890",
                        "access_token": "ERTYUIEFDGHGFHJKLFGHJKGHJ",
                        "verify_token": "valid",
                        "phone_number": "1234567890",
                    }
                }

                bot = "whatsapp_test"
                payload = {
                    "object": "whatsapp_business_account",
                    "entry": [
                        {
                            "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                            "changes": [
                                {
                                    "value": {
                                        "messaging_product": "whatsapp",
                                        "metadata": {
                                            "display_phone_number": "910123456789",
                                            "phone_number_id": "12345678",
                                        },
                                        "contacts": [
                                            {
                                                "profile": {"name": "udit"},
                                                "wa_id": "wa-123456789",
                                            }
                                        ],
                                        "messages": [
                                            {
                                                "from": "910123456789",
                                                "id": "wappmsg.ID",
                                                "timestamp": "21-09-2022 12:05:00",
                                                "button": {
                                                    "text": "buy now",
                                                    "payload": "buy now",
                                                },
                                                "type": "button",
                                            }
                                        ],
                                    },
                                    "field": "messages",
                                }
                            ],
                        }
                    ],
                }

                handler = Whatsapp(channel_config)
                await handler.handle_meta_payload(payload,
                                                  {"channel_type": "whatsapp", "bsp_type": ",meta",
                                                   "tabname": "default"},
                                                  bot)
                args, kwargs = mock_message.call_args

                assert args[0] == bot
                user_message = args[1]

                assert user_message.text == 'buy now'

    @pytest.mark.asyncio
    async def test_whatsapp_valid_flows_message_request(self):
        from kairon.chat.handlers.channels.whatsapp import Whatsapp, WhatsappBot
        with patch.object(WhatsappBot, "mark_as_read"):
            with patch.object(Whatsapp, "process_message") as mock_message:
                mock_message.return_value = "Hi, How may i help you!"
                channel_config = {
                    "connector_type": "whatsapp",
                    "config": {
                        "app_secret": "jagbd34567890",
                        "access_token": "ERTYUIEFDGHGFHJKLFGHJKGHJ",
                        "verify_token": "valid",
                        "phone_number": "1234567890",
                    }
                }

                bot = "whatsapp_test"
                payload = {
                    "object": "whatsapp_business_account",
                    "entry": [
                        {
                            "id": "147142368486217",
                            "changes": [
                                {
                                    "value": {
                                        "messaging_product": "whatsapp",
                                        "metadata": {
                                            "display_phone_number": "918657011111",
                                            "phone_number_id": "142427035629239",
                                        },
                                        "contacts": [
                                            {
                                                "profile": {"name": "Mahesh"},
                                                "wa_id": "919515991111",
                                            }
                                        ],
                                        "messages": [
                                            {
                                                "context": {
                                                    "from": "918657011111",
                                                    "id": "wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSMjVGRjYwODI3RkMyOEQ0NUM1AA==",
                                                },
                                                "from": "919515991111",
                                                "id": "wamid.HBgMOTE5NTE1OTkxNjg1FQIAEhggQTRBQUYyODNBQkMwNEIzRDQ0MUI1ODkyMTE2NTMA",
                                                "timestamp": "1703257297",
                                                "type": "interactive",
                                                "interactive": {
                                                    "type": "nfm_reply",
                                                    "nfm_reply": {
                                                        "response_json": '{"flow_token":"AQBBBBBCS5FpgQ_cAAAAAD0QI3s.","firstName":"Mahesh ","lastName":"Sattala ","pincode":"523456","district":"Bangalore ","houseNumber":"5-6","dateOfBirth":"1703257240046","source":"SOCIAL_MEDIA","landmark":"HSR Layout ","email":"maheshsattala@gmail.com"}',
                                                        "body": "Sent",
                                                        "name": "flow",
                                                    },
                                                },
                                            }
                                        ],
                                    },
                                    "field": "messages",
                                }
                            ],
                        }
                    ],
                }

                handler = Whatsapp(channel_config)
                await handler.handle_meta_payload(payload,
                                                  {"channel_type": "whatsapp", "bsp_type": ",meta",
                                                   "tabname": "default"},
                                                  bot)
                args, kwargs = mock_message.call_args

                assert args[0] == bot
                user_message = args[1]
                assert user_message.text == '/k_interactive_msg{"flow_reply": {"flow_token": "AQBBBBBCS5FpgQ_cAAAAAD0QI3s.", "firstName": "Mahesh ", "lastName": "Sattala ", "pincode": "523456", "district": "Bangalore ", "houseNumber": "5-6", "dateOfBirth": "1703257240046", "source": "SOCIAL_MEDIA", "landmark": "HSR Layout ", "email": "maheshsattala@gmail.com", "type": "nfm_reply"}}'

    @pytest.mark.asyncio
    async def test_interactive_nfm_reply_with_documents_triggers_multimedia(self, monkeypatch):
        from kairon.chat.handlers.channels.whatsapp import Whatsapp, WhatsappBot
        from kairon.shared.chat.user_media import UserMedia

        channel_config = {
            "connector_type": "whatsapp",
            "config": {
                "bsp_type": "meta",
                "api_key": "DUMMY",
                "access_token": "DUMMY"
            }
        }
        bot = "whatsapp_test"
        handler = Whatsapp(channel_config)

        monkeypatch.setattr(WhatsappBot, "mark_as_read", lambda *args, **kwargs: None)
        monkeypatch.setattr(
            Whatsapp,
            "get_business_phone_number_id",
            lambda self: "142427035629239"
        )

        # Simulate save_whatsapp_media_content returning a list of one media id
        monkeypatch.setattr(
            UserMedia,
            "save_whatsapp_media_content",
            lambda bot, sender_id, whatsapp_media_id, config: [whatsapp_media_id]
        )

        # Spy on _handle_user_message
        handler._handle_user_message = AsyncMock()

        docs = [
            {"id": "doc1", "mime_type": "image/jpeg", "sha256": "x", "file_name": "a.jpg"},
            {"id": "doc2", "mime_type": "application/pdf", "sha256": "y", "file_name": "b.pdf"}
        ]
        flow = {
            "flow_token": "token123",
            "documents": docs
        }
        raw_resp = json.dumps(flow)

        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "contacts": [{"profile": {"name": "Foo"}, "wa_id": "seller"}],
                                "messages": [
                                    {
                                        "from": "user123",
                                        "type": "interactive",
                                        "interactive": {
                                            "type": "nfm_reply",
                                            "nfm_reply": {
                                                "response_json": raw_resp,
                                                "body": "ignored",
                                                "name": "flow"
                                            }
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }

        await handler.handle_meta_payload(
            payload,
            {"channel_type": "whatsapp", "bsp_type": "meta", "tabname": "default"},
            bot
        )

        assert handler._handle_user_message.call_count == 1

        text, sender, msg_obj, bot_name, media_ids = handler._handle_user_message.call_args[0]

        expected_list_str = str([doc["id"] for doc in docs])
        expected_payload = f'/k_multimedia_msg{{"flow_docs": "{expected_list_str}"}}'
        expected_media_ids = [doc["id"] for doc in docs]

        assert text == expected_payload
        assert sender == "user123"
        assert bot_name == bot
        assert media_ids == expected_media_ids

    @pytest.mark.asyncio
    async def test_whatsapp_typing_indicator_end_to_end(self, monkeypatch):
        from kairon.chat.handlers.channels.whatsapp import Whatsapp, WhatsappBot
        from unittest.mock import MagicMock, AsyncMock

        channel_config = {
            "connector_type": "whatsapp",
            "config": {
                "bsp_type": "meta",
                "api_key": "DUMMY",
                "access_token": "DUMMY"
            }
        }

        handler = Whatsapp(channel_config)

        handler.client = MagicMock()
        handler.client.post = AsyncMock(return_value=MagicMock(status_code=200))

        metadata = {"id": "msg123"}

        monkeypatch.setattr(
            WhatsappBot,
            "typing_indicator",
            AsyncMock()
        )

        monkeypatch.setattr(
            WhatsappBot,
            "mark_as_read",
            AsyncMock()
        )

        text = "hello"
        sender = "user123"
        bot = "bot_test"

        await handler._handle_user_message(
            text=text,
            sender_id=sender,
            metadata=metadata,
            bot=bot,
            media_ids=[]
        )

        WhatsappBot.mark_as_read.assert_awaited_once_with("msg123")

        WhatsappBot.typing_indicator.assert_awaited_once_with("msg123")
        assert handler.client.post.await_count >= 0

    @pytest.mark.asyncio
    async def test_whatsapp_valid_location_message_request(self):
        from kairon.chat.handlers.channels.whatsapp import Whatsapp, WhatsappBot
        with patch.object(WhatsappBot, "mark_as_read"):
            with patch.object(Whatsapp, "process_message") as mock_message:
                mock_message.return_value = "Hi, How may i help you!"
                channel_config = {
                    "connector_type": "whatsapp",
                    "config": {
                        "app_secret": "jagbd34567890",
                        "access_token": "ERTYUIEFDGHGFHJKLFGHJKGHJ",
                        "verify_token": "valid",
                        "phone_number": "1234567890",
                    }
                }

                bot = "whatsapp_test"
                payload = {
                    "object": "whatsapp_business_account",
                    "entry": [
                        {
                            "id": "102290129340398",
                            "changes": [
                                {
                                    "value": {
                                        "messaging_product": "whatsapp",
                                        "metadata": {
                                            "display_phone_number": "15550783881",
                                            "phone_number_id": "106540352242922"
                                        },
                                        "contacts": [
                                            {
                                                "profile": {
                                                    "name": "Pablo Morales"
                                                },
                                                "wa_id": "16505551234"
                                            }
                                        ],
                                        "messages": [
                                            {
                                                "context": {
                                                    "from": "15550783881",
                                                    "id": "wamid.HBgLMTY0NjcwNDM1OTUVAgARGBI1QjJGRjI1RDY0RkE4Nzg4QzcA"
                                                },
                                                "from": "16505551234",
                                                "id": "wamid.HBgLMTY0NjcwNDM1OTUVAgASGBQzQTRCRDcwNzgzMTRDNTAwRTgwRQA=",
                                                "timestamp": "1702920965",
                                                "location": {
                                                    "address": "1071 5th Ave, New York, NY 10128",
                                                    "latitude": 40.782910059774,
                                                    "longitude": -73.959075808525,
                                                    "name": "Solomon R. Guggenheim Museum"
                                                },
                                                "type": "location"
                                            }
                                        ]
                                    },
                                    "field": "messages"
                                }
                            ]
                        }
                    ]
                }

                handler = Whatsapp(channel_config)
                await handler.handle_meta_payload(payload,
                                                  {"channel_type": "whatsapp", "bsp_type": ",meta",
                                                   "tabname": "default"},
                                                  bot)
                args, kwargs = mock_message.call_args

                assert args[0] == bot
                user_message = args[1]
                print(user_message.text)
                assert user_message.text == '/k_multimedia_msg{"latitude": "40.782910059774", "longitude": "-73.959075808525"}'

    @pytest.mark.asyncio
    async def test_whatsapp_invalid_message_request(self):
        from kairon.chat.handlers.channels.whatsapp import Whatsapp, WhatsappBot
        with patch.object(WhatsappBot, "mark_as_read"):
            with patch.object(Whatsapp, "process_message") as mock_message:
                mock_message.return_value = "Hi, How may i help you!"
                channel_config = {
                    "connector_type": "whatsapp",
                    "config": {
                        "app_secret": "jagbd34567890",
                        "access_token": "ERTYUIEFDGHGFHJKLFGHJKGHJ",
                        "verify_token": "valid",
                        "phone_number": "1234567890",
                    }
                }

                bot = "whatsapp_test"
                payload = {
                    "object": "whatsapp_business_account",
                    "entry": [
                        {
                            "id": "102290129340398",
                            "changes": [
                                {
                                    "value": {
                                        "messaging_product": "whatsapp",
                                        "metadata": {
                                            "display_phone_number": "15550783881",
                                            "phone_number_id": "106540352242922"
                                        },
                                        "contacts": [
                                            {
                                                "profile": {
                                                    "name": "Pablo Morales"
                                                },
                                                "wa_id": "16505551234"
                                            }
                                        ],
                                        "messages": [
                                            {
                                                "context": {
                                                    "from": "15550783881",
                                                    "id": "wamid.HBgLMTY0NjcwNDM1OTUVAgARGBI1QjJGRjI1RDY0RkE4Nzg4QzcA"
                                                },
                                                "from": "16505551234",
                                                "id": "wamid.HBgLMTY0NjcwNDM1OTUVAgASGBQzQTRCRDcwNzgzMTRDNTAwRTgwRQA=",
                                                "timestamp": "1702920965",
                                                "location": {
                                                    "address": "1071 5th Ave, New York, NY 10128",
                                                    "latitude": 40.782910059774,
                                                    "longitude": -73.959075808525,
                                                    "name": "Solomon R. Guggenheim Museum"
                                                },
                                                "type": "invalid"
                                            }
                                        ]
                                    },
                                    "field": "messages"
                                }
                            ]
                        }
                    ]
                }

                handler = Whatsapp(channel_config)
                await handler.handle_meta_payload(payload,
                                                  {"channel_type": "whatsapp", "bsp_type": ",meta",
                                                   "tabname": "default"},
                                                  bot)

    @pytest.mark.asyncio
    async def test_valid_order_message_request(self):
        from kairon.chat.handlers.channels.whatsapp import Whatsapp, WhatsappBot
        with patch.object(WhatsappBot, "mark_as_read"):
            with patch.object(Whatsapp, "process_message") as mock_message:
                mock_message.return_value = "Hi, How may i help you!"
                channel_config = {
                    "connector_type": "whatsapp",
                    "config": {
                        "app_secret": "jagbd34567890",
                        "access_token": "ERTYUIEFDGHGFHJKLFGHJKGHJ",
                        "verify_token": "valid",
                        "phone_number": "1234567890",
                    }
                }

                bot = "whatsapp_test"
                payload = {
                    "object": "whatsapp_business_account",
                    "entry": [
                        {
                            "id": "108103872212677",
                            "changes": [
                                {
                                    "value": {
                                        "messaging_product": "whatsapp",
                                        "metadata": {
                                            "display_phone_number": "919876543210",
                                            "phone_number_id": "108578266683441",
                                        },
                                        "contacts": [
                                            {
                                                "profile": {"name": "Hitesh"},
                                                "wa_id": "919876543210",
                                            }
                                        ],
                                        "messages": [
                                            {
                                                "from": "919876543210",
                                                "id": "wamid.HBgMOTE5NjU3DMU1MDIyQFIAEhggNzg5MEYwNEIyNDA1Q0IxMzU2QkI0NDc3RTVGMzYxNUEA",
                                                "timestamp": "1691598412",
                                                "type": "order",
                                                "order": {
                                                    "catalog_id": "538971028364699",
                                                    "product_items": [
                                                        {
                                                            "product_retailer_id": "akuba13e44",
                                                            "quantity": 1,
                                                            "item_price": 200,
                                                            "currency": "INR",
                                                        },
                                                        {
                                                            "product_retailer_id": "0z10aj0bmq",
                                                            "quantity": 1,
                                                            "item_price": 600,
                                                            "currency": "INR",
                                                        },
                                                    ],
                                                },
                                            }
                                        ],
                                    },
                                    "field": "messages",
                                }
                            ],
                        }
                    ],
                }

                handler = Whatsapp(channel_config)
                await handler.handle_meta_payload(payload,
                                                  {"channel_type": "whatsapp", "bsp_type": ",meta", "tabname": "default"},
                                                  bot)
                args, kwargs = mock_message.call_args

                assert args[0] == bot
                user_message = args[1]

                assert user_message.text == '/k_order_msg{"order": {"catalog_id": "538971028364699", "product_items": [{"product_retailer_id": "akuba13e44", "quantity": 1, "item_price": 200, "currency": "INR"}, {"product_retailer_id": "0z10aj0bmq", "quantity": 1, "item_price": 600, "currency": "INR"}]}}'

    @pytest.mark.asyncio
    @responses.activate
    async def test_valid_attachment_message_request(self):
        import responses
        from unittest.mock import patch
        from kairon.chat.handlers.channels.whatsapp import Whatsapp, WhatsappBot
        document_id = "sdfghj567"
        access_token = 'ERTYUIEFDGHGFHJKLFGHJKGHJ'

        with open("./tests/testing_data/sample.pdf", 'rb') as file:
            body_bytes = file.read()

        responses.get(
            url=f'https://graph.facebook.com/v22.0/{document_id}?fields=url',
            json={'url': 'https://test.com/download', 'mime_type': 'application/pdf'}
        )
        responses.get(
            url='https://test.com/download',
            body=body_bytes
        )

        responses.add(
            responses.POST,
            "https://graph.facebook.com/v19.0/12345678/messages",
            json={"messages": [{"id": "wamid.1234"}]},
            status=200
        )

        with patch.object(WhatsappBot, "mark_as_read"), \
                patch.object(Whatsapp, "process_message") as mock_message:
            mock_message.return_value = "Hi, How may i help you!"

            channel_config = {
                "connector_type": "whatsapp",
                "config": {
                    "app_secret": "jagbd34567890",
                    "access_token": access_token,
                    "verify_token": "valid",
                    "phone_number": "1234567890",
                }
            }

            bot = "whatsapp_test"
            payload = {
                "object": "whatsapp_business_account",
                "entry": [
                    {
                        "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                        "changes": [
                            {
                                "value": {
                                    "messaging_product": "whatsapp",
                                    "metadata": {
                                        "display_phone_number": "910123456789",
                                        "phone_number_id": "12345678",
                                    },
                                    "contacts": [
                                        {
                                            "profile": {"name": "udit"},
                                            "wa_id": "wa-123456789",
                                        }
                                    ],
                                    "messages": [
                                        {
                                            "from": "910123456789",
                                            "id": "wappmsg.ID",
                                            "timestamp": "21-09-2022 12:05:00",
                                            "document": {"id": document_id},
                                            "type": "document",
                                        }
                                    ],
                                },
                                "field": "messages",
                            }
                        ],
                    }
                ],
            }

            handler = Whatsapp(channel_config)
            await handler.handle_meta_payload(
                payload,
                {"channel_type": "whatsapp", "bsp_type": ",meta", "tabname": "default"},
                bot
            )

            args, kwargs = mock_message.call_args
            assert args[0] == bot
            user_message = args[1]
            expected_text = f'/k_multimedia_msg{{"document": "{document_id}"}}'
            assert user_message.text == expected_text

    @pytest.mark.asyncio
    async def test_payment_message_request(self):
        from kairon.chat.handlers.channels.whatsapp import Whatsapp, WhatsappBot
        from kairon.shared.chat.data_objects import ChannelLogs

        with patch.object(WhatsappBot, "mark_as_read"):
            with patch.object(Whatsapp, "process_message") as mock_message:
                mock_message.return_value = "Hi, How may i help you!"
                channel_config = {
                    "connector_type": "whatsapp",
                    "config": {
                        "app_secret": "jagbd34567890",
                        "access_token": "ERTYUIEFDGHGFHJKLFGHJKGHJ",
                        "verify_token": "valid",
                        "phone_number": "1234567890",
                    }
                }

                bot = "whatsapp_test"
                payload = {
                    "object": "whatsapp_business_account",
                    "entry": [
                        {
                            "id": "190133580861200",
                            "changes": [
                                {
                                    "value": {
                                        "messaging_product": "whatsapp",
                                        "metadata": {
                                            "display_phone_number": "918657459321",
                                            "phone_number_id": "257191390803220",
                                        },
                                        "statuses": [
                                            {
                                                "id": "wamid.HBgMOTE5NTR1OTkxNjg1FQIAEhgKNDBzOTkxOTI5NgA=",
                                                "status": "captured",
                                                "timestamp": "1724764153",
                                                "recipient_id": "919515991234",
                                                "type": "payment",
                                                "payment": {
                                                    "reference_id": "BM3-43D-12",
                                                    "amount": {"value": 100, "offset": 100},
                                                    "currency": "INR",
                                                    "transaction": {
                                                        "id": "order_Ovpn6PVVFYbmK3",
                                                        "type": "razorpay",
                                                        "status": "success",
                                                        "created_timestamp": 1724764153,
                                                        "updated_timestamp": 1724764153,
                                                        "amount": {"value": 100, "offset": 100},
                                                        "currency": "INR",
                                                        "method": {"type": "upi"},
                                                    },
                                                    "receipt": "receipt-value",
                                                    "notes": {"key1": "value1", "key2": "value2"},
                                                },
                                            }
                                        ],
                                    },
                                    "field": "messages",
                                }
                            ],
                        }
                    ],
                }

                handler = Whatsapp(channel_config)
                await handler.handle_meta_payload(payload,
                                                  {"channel_type": "whatsapp", "bsp_type": ",meta", "tabname": "default"},
                                                  bot)
                args, kwargs = mock_message.call_args

                assert args[0] == bot
                user_message = args[1]

                assert user_message.text == '/k_payment_msg{"payment": {"reference_id": "BM3-43D-12", "amount": {"value": 100, "offset": 100}, "currency": "INR", "transaction": {"id": "order_Ovpn6PVVFYbmK3", "type": "razorpay", "status": "success", "created_timestamp": 1724764153, "updated_timestamp": 1724764153, "amount": {"value": 100, "offset": 100}, "currency": "INR", "method": {"type": "upi"}}, "receipt": "receipt-value", "notes": {"key1": "value1", "key2": "value2"}}}'

                log = (
                    ChannelLogs.objects(
                        bot=bot,
                        message_id="wamid.HBgMOTE5NTR1OTkxNjg1FQIAEhgKNDBzOTkxOTI5NgA=",
                    )
                    .get()
                    .to_mongo()
                    .to_dict()
                )
                assert log["data"] == {
                    'reference_id': 'BM3-43D-12',
                    'amount': {'value': 100, 'offset': 100},
                    'currency': 'INR',
                    'transaction': {
                        'id': 'order_Ovpn6PVVFYbmK3',
                        'type': 'razorpay',
                        'status': 'success',
                        'created_timestamp': 1724764153,
                        'updated_timestamp': 1724764153,
                        'amount': {'value': 100, 'offset': 100},
                        'currency': 'INR',
                        'method': {'type': 'upi'}
                    },
                    'receipt': 'receipt-value',
                    'notes': {
                        'key1': 'value1',
                        'key2': 'value2'
                    }
                }
                assert log["status"] == "captured"
                assert log["recipient"] == "919515991234"

    @pytest.mark.asyncio
    async def test_whatsapp_valid_statuses_with_sent_request(self):
        from kairon.chat.handlers.channels.whatsapp import Whatsapp, WhatsappBot
        with patch.object(WhatsappBot, "mark_as_read"):
            with patch.object(Whatsapp, "process_message") as mock_message:
                mock_message.return_value = "Hi, How may i help you!"
                channel_config = {
                    "connector_type": "whatsapp",
                    "config": {
                        "app_secret": "jagbd34567890",
                        "access_token": "ERTYUIEFDGHGFHJKLFGHJKGHJ",
                        "verify_token": "valid",
                        "phone_number": "1234567890",
                    }
                }

                bot = "whatsapp_test"
                payload = {
                    "object": "whatsapp_business_account",
                    "entry": [
                        {
                            "id": "108103872212677",
                            "changes": [
                                {
                                    "value": {
                                        "messaging_product": "whatsapp",
                                        "metadata": {
                                            "display_phone_number": "919876543210",
                                            "phone_number_id": "108578266683441",
                                        },
                                        "contacts": [
                                            {
                                                "profile": {"name": "Hitesh"},
                                                "wa_id": "919876543210",
                                            }
                                        ],
                                        "statuses": [
                                            {
                                                "id": "wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIA",
                                                "recipient_id": "91551234567",
                                                "status": "sent",
                                                "timestamp": "1691548112",
                                                "conversation": {
                                                    "id": "CONVERSATION_ID",
                                                    "expiration_timestamp": "1691598412",
                                                    "origin": {"type": "business_initated"},
                                                },
                                                "pricing": {
                                                    "pricing_model": "CBP",
                                                    "billable": "True",
                                                    "category": "business_initated",
                                                },
                                            }
                                        ],
                                    },
                                    "field": "messages",
                                }
                            ],
                        }
                    ],
                }

                handler = Whatsapp(channel_config)
                await handler.handle_meta_payload(payload,
                                                  {"channel_type": "whatsapp", "bsp_type": ",meta",
                                                   "tabname": "default"},
                                                  bot)

                log = (
                    ChannelLogs.objects(
                        bot=bot,
                        message_id="wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIA",
                    )
                    .get()
                    .to_mongo()
                    .to_dict()
                )
                assert log["data"] == {
                    "id": "CONVERSATION_ID",
                    "expiration_timestamp": "1691598412",
                    "origin": {"type": "business_initated"},
                }
                assert log["initiator"] == "business_initated"
                assert log["status"] == "sent"
                assert log["recipient"] == "91551234567"

    @pytest.mark.asyncio
    async def test_whatsapp_valid_statuses_with_delivered_request(self):
        from kairon.chat.handlers.channels.whatsapp import Whatsapp, WhatsappBot
        with patch.object(WhatsappBot, "mark_as_read"):
            with patch.object(Whatsapp, "process_message") as mock_message:
                mock_message.return_value = "Hi, How may i help you!"
                channel_config = {
                    "connector_type": "whatsapp",
                    "config": {
                        "app_secret": "jagbd34567890",
                        "access_token": "ERTYUIEFDGHGFHJKLFGHJKGHJ",
                        "verify_token": "valid",
                        "phone_number": "1234567890",
                    }
                }

                bot = "whatsapp_test"
                payload = {
                    "object": "whatsapp_business_account",
                    "entry": [
                        {
                            "id": "108103872212677",
                            "changes": [
                                {
                                    "value": {
                                        "messaging_product": "whatsapp",
                                        "metadata": {
                                            "display_phone_number": "919876543210",
                                            "phone_number_id": "108578266683441",
                                        },
                                        "contacts": [
                                            {
                                                "profile": {"name": "Hitesh"},
                                                "wa_id": "919876543210",
                                            }
                                        ],
                                        "statuses": [
                                            {
                                                "id": "wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIB",
                                                "recipient_id": "91551234567",
                                                "status": "delivered",
                                                "timestamp": "1691548112",
                                                "conversation": {
                                                    "id": "CONVERSATION_ID",
                                                    "expiration_timestamp": "1691598412",
                                                    "origin": {"type": "user_initiated"},
                                                },
                                                "pricing": {
                                                    "pricing_model": "CBP",
                                                    "billable": "True",
                                                    "category": "service",
                                                },
                                            }
                                        ],
                                    },
                                    "field": "messages",
                                }
                            ],
                        }
                    ],
                }

                handler = Whatsapp(channel_config)
                await handler.handle_meta_payload(payload,
                                                  {"channel_type": "whatsapp", "bsp_type": ",meta",
                                                   "tabname": "default"},
                                                  bot)



                log = (
                    ChannelLogs.objects(
                        bot=bot,
                        message_id="wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIB",
                    )
                    .get()
                    .to_mongo()
                    .to_dict()
                )
                assert log["data"] == {
                    "id": "CONVERSATION_ID",
                    "expiration_timestamp": "1691598412",
                    "origin": {"type": "user_initiated"},
                }
                assert log["initiator"] == "user_initiated"
                assert log["status"] == "delivered"
                assert log["recipient"] == "91551234567"


    @pytest.mark.asyncio
    async def test_whatsapp_valid_statuses_with_read_request(self):
        from kairon.chat.handlers.channels.whatsapp import Whatsapp, WhatsappBot
        with patch.object(WhatsappBot, "mark_as_read"):
            with patch.object(Whatsapp, "process_message") as mock_message:
                mock_message.return_value = "Hi, How may i help you!"
                channel_config = {
                    "connector_type": "whatsapp",
                    "config": {
                        "app_secret": "jagbd34567890",
                        "access_token": "ERTYUIEFDGHGFHJKLFGHJKGHJ",
                        "verify_token": "valid",
                        "phone_number": "1234567890",
                    }
                }

                bot = "whatsapp_test"
                payload = {
                    "object": "whatsapp_business_account",
                    "entry": [
                        {
                            "id": "108103872212677",
                            "changes": [
                                {
                                    "value": {
                                        "messaging_product": "whatsapp",
                                        "metadata": {
                                            "display_phone_number": "919876543210",
                                            "phone_number_id": "108578266683441",
                                        },
                                        "contacts": [
                                            {
                                                "profile": {"name": "Hitesh"},
                                                "wa_id": "919876543210",
                                            }
                                        ],
                                        "statuses": [
                                            {
                                                "id": "wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIC",
                                                "recipient_id": "91551234567",
                                                "status": "read",
                                                "timestamp": "1691548112",
                                            }
                                        ],
                                    },
                                    "field": "messages",
                                }
                            ],
                        }
                    ],
                }

                handler = Whatsapp(channel_config)
                await handler.handle_meta_payload(payload,
                                                  {"channel_type": "whatsapp", "bsp_type": ",meta",
                                                   "tabname": "default"},
                                                  bot)

                log = (
                    ChannelLogs.objects(
                        bot=bot,
                        message_id="wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIC",
                    )
                    .get()
                    .to_mongo()
                    .to_dict()
                )
                assert log.get("data") == {}
                assert log.get("initiator") is None
                assert log.get("status") == "read"
                assert log.get("recipient") == "91551234567"

                logs = ChannelLogs.objects(bot=bot, user="919876543210")
                assert len(ChannelLogs.objects(bot=bot, user="919876543210")) == 3
                assert logs[0]["data"] == {
                    "id": "CONVERSATION_ID",
                    "expiration_timestamp": "1691598412",
                    "origin": {"type": "business_initated"},
                }
                assert logs[0]["initiator"] == "business_initated"
                assert logs[0]["status"] == "sent"
                assert logs[1]["data"] == {
                    "id": "CONVERSATION_ID",
                    "expiration_timestamp": "1691598412",
                    "origin": {"type": "user_initiated"},
                }
                assert logs[1]["initiator"] == "user_initiated"
                assert logs[1]["status"] == "delivered"
                assert logs[2]["status"] == "read"

    @pytest.mark.asyncio
    async def test_whatsapp_valid_statuses_with_errors_request(self):
        from kairon.chat.handlers.channels.whatsapp import Whatsapp, WhatsappBot
        with patch.object(WhatsappBot, "mark_as_read"):
            with patch.object(Whatsapp, "process_message") as mock_message:
                mock_message.return_value = "Hi, How may i help you!"
                channel_config = {
                    "connector_type": "whatsapp",
                    "config": {
                        "app_secret": "jagbd34567890",
                        "access_token": "ERTYUIEFDGHGFHJKLFGHJKGHJ",
                        "verify_token": "valid",
                        "phone_number": "1234567890",
                    }
                }

                bot = "whatsapp_test"
                payload = {
                    "object": "whatsapp_business_account",
                    "entry": [
                        {
                            "id": "108103872212677",
                            "changes": [
                                {
                                    "value": {
                                        "messaging_product": "whatsapp",
                                        "metadata": {
                                            "display_phone_number": "919876543219",
                                            "phone_number_id": "108578266683441",
                                        },
                                        "contacts": [
                                            {
                                                "profile": {"name": "Hitesh"},
                                                "wa_id": "919876543210",
                                            }
                                        ],
                                        "statuses": [
                                            {
                                                "id": "wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDI",
                                                "status": "failed",
                                                "timestamp": "1689380458",
                                                "recipient_id": "15551234567",
                                                "errors": [
                                                    {
                                                        "code": 130472,
                                                        "title": "User's number is part of an experiment",
                                                        "message": "User's number is part of an experiment",
                                                        "error_data": {
                                                            "details": "Failed to send message because this user's phone number is part of an experiment"
                                                        },
                                                        "href": "https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes/",
                                                    }
                                                ],
                                            }
                                        ],
                                    },
                                    "field": "messages",
                                }
                            ],
                        }
                    ],
                }

                handler = Whatsapp(channel_config)
                await handler.handle_meta_payload(payload,
                                                  {"channel_type": "whatsapp", "bsp_type": ",meta",
                                                   "tabname": "default"},
                                                  bot)

                assert ChannelLogs.objects(
                    bot=bot, message_id="wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDI"
                )
                log = ChannelLogs.objects(bot=bot, user="919876543219").get().to_mongo().to_dict()
                assert log.get("status") == "failed"
                assert log.get("data") == {}
                assert log.get("errors") == [
                    {
                        "code": 130472,
                        "title": "User's number is part of an experiment",
                        "message": "User's number is part of an experiment",
                        "error_data": {
                            "details": "Failed to send message because this user's phone number is part of an experiment"
                        },
                        "href": "https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes/",
                    }
                ]
                assert log.get("recipient") == "15551234567"

    @pytest.mark.asyncio
    async def test_whatsapp_valid_unsupported_message_request(self):
        from kairon.chat.handlers.channels.whatsapp import Whatsapp, WhatsappBot
        with patch.object(WhatsappBot, "mark_as_read"):
            with patch.object(Whatsapp, "process_message") as mock_message:
                mock_message.return_value = "Hi, How may i help you!"
                channel_config = {
                    "connector_type": "whatsapp",
                    "config": {
                        "app_secret": "jagbd34567890",
                        "access_token": "ERTYUIEFDGHGFHJKLFGHJKGHJ",
                        "verify_token": "valid",
                        "phone_number": "1234567890",
                    }
                }

                bot = "whatsapp_test"
                payload = {
                    "object": "whatsapp_business_account",
                    "entry": [
                        {
                            "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                            "changes": [
                                {
                                    "value": {
                                        "messaging_product": "whatsapp",
                                        "metadata": {
                                            "display_phone_number": "910123456789",
                                            "phone_number_id": "12345678",
                                        },
                                        "contacts": [
                                            {
                                                "profile": {"name": "udit"},
                                                "wa_id": "wa-123456789",
                                            }
                                        ],
                                        "messages": [
                                            {
                                                "from": "910123456789",
                                                "id": "wappmsg.ID",
                                                "timestamp": "21-09-2022 12:05:00",
                                                "text": {"body": "hi"},
                                                "type": "text",
                                            }
                                        ],
                                    },
                                    "field": "messages",
                                }
                            ],
                        }
                    ],
                }

                handler = Whatsapp(channel_config)
                await handler.handle_meta_payload(payload,
                                                  {"channel_type": "whatsapp", "bsp_type": ",meta",
                                                   "tabname": "default"},
                                                  bot)
                args, kwargs = mock_message.call_args

                assert args[0] == bot
                user_message = args[1]

                assert user_message.text == 'hi'

                log = (
                    ChannelLogs.objects(
                        bot=bot,
                        message_id="wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIB",
                    )
                    .get()
                    .to_mongo()
                    .to_dict()
                )
                assert log["data"] == {
                    "id": "CONVERSATION_ID",
                    "expiration_timestamp": "1691598412",
                    "origin": {"type": "user_initiated"},
                }
                assert log["initiator"] == "user_initiated"
                assert log["status"] == "delivered"
                assert log["recipient"] == "91551234567"

    @pytest.mark.asyncio
    async def test_whatsapp_bsp_valid_text_message_request(self):
        from kairon.chat.handlers.channels.whatsapp import Whatsapp, WhatsappBot
        with patch.object(WhatsappBot, "mark_as_read"):
            with patch.object(Whatsapp, "process_message") as mock_message:
                mock_message.return_value = "Hi, How may i help you!"
                channel_config = {
                    "connector_type": "whatsapp",
                    "config": {
                        "app_secret": "jagbd34567890",
                        "access_token": "ERTYUIEFDGHGFHJKLFGHJKGHJ",
                        "verify_token": "valid",
                        "phone_number": "1234567890",
                    }
                }

                bot = "whatsapp_test"
                payload = {
                    "object": "whatsapp_business_account",
                    "entry": [
                        {
                            "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                            "changes": [
                                {
                                    "value": {
                                        "messaging_product": "whatsapp",
                                        "metadata": {
                                            "display_phone_number": "910123456789",
                                            "phone_number_id": "12345678",
                                        },
                                        "contacts": [
                                            {
                                                "profile": {"name": "udit"},
                                                "wa_id": "wa-123456789",
                                            }
                                        ],
                                        "messages": [
                                            {
                                                "from": "910123456789",
                                                "id": "wappmsg.ID",
                                                "timestamp": "21-09-2022 12:05:00",
                                                "text": {"body": "hello"},
                                                "type": "text",
                                            }
                                        ],
                                    },
                                    "field": "messages",
                                }
                            ],
                        }
                    ],
                }

                handler = Whatsapp(channel_config)
                await handler.handle_meta_payload(payload,
                                                  {"channel_type": "whatsapp", "bsp_type": ",meta",
                                                   "tabname": "default"},
                                                  bot)

                args, kwargs = mock_message.call_args

                assert args[0] == bot
                user_message = args[1]

                assert user_message.text == 'hello'


    @pytest.mark.asyncio
    async def test_whatsapp_bsp_valid_button_message_request(self):
        from kairon.chat.handlers.channels.whatsapp import Whatsapp, WhatsappBot
        with patch.object(WhatsappBot, "mark_as_read"):
            with patch.object(Whatsapp, "process_message") as mock_message:
                mock_message.return_value = "Hi, How may i help you!"
                channel_config = {
                    "connector_type": "whatsapp",
                    "config": {
                        "app_secret": "jagbd34567890",
                        "access_token": "ERTYUIEFDGHGFHJKLFGHJKGHJ",
                        "verify_token": "valid",
                        "phone_number": "1234567890",
                    }
                }

                bot = "whatsapp_test"
                payload = {
                    "object": "whatsapp_business_account",
                    "entry": [
                        {
                            "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                            "changes": [
                                {
                                    "value": {
                                        "messaging_product": "whatsapp",
                                        "metadata": {
                                            "display_phone_number": "910123456789",
                                            "phone_number_id": "12345678",
                                        },
                                        "contacts": [
                                            {
                                                "profile": {"name": "udit"},
                                                "wa_id": "wa-123456789",
                                            }
                                        ],
                                        "messages": [
                                            {
                                                "from": "910123456789",
                                                "id": "wappmsg.ID",
                                                "timestamp": "21-09-2022 12:05:00",
                                                "button": {
                                                    "text": "buy now",
                                                    "payload": "buy kairon for 1 billion",
                                                },
                                                "type": "button",
                                            }
                                        ],
                                    },
                                    "field": "messages",
                                }
                            ],
                        }
                    ],
                }

                handler = Whatsapp(channel_config)
                await handler.handle_meta_payload(payload,
                                                  {"channel_type": "whatsapp", "bsp_type": ",meta",
                                                   "tabname": "default"},
                                                  bot)

                args, kwargs = mock_message.call_args

                assert args[0] == bot
                user_message = args[1]
                assert user_message.text == '/k_quick_reply_msg{"quick_reply": "buy kairon for 1 billion"}'




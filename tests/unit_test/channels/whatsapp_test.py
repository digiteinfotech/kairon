from mock import patch
import pytest
import os

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
    async def test_valid_attachment_message_request(self):
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
                                                "document": {"id": "sdfghj567"},
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
                await handler.handle_meta_payload(payload,
                                        {"channel_type": "whatsapp", "bsp_type": ",meta", "tabname": "default"},
                                                 bot)
                args, kwargs = mock_message.call_args

                assert args[0] == bot
                user_message = args[1]

                assert user_message.text == '/k_multimedia_msg{"document": "sdfghj567"}'

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
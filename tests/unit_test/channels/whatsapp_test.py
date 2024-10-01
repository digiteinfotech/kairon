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
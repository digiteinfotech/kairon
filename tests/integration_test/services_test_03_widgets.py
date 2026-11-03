from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training



def test_secure_collection_crud_lifecycle():
    # Step 1: Add a bot
    add_bot_resp = client.post(
        "/api/account/bot",
        json={"name": "secure-collection-bot"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    assert add_bot_resp.status_code == 200
    bot_id = add_bot_resp.json()["data"]["bot_id"]
    assert bot_id

    # Step 2: Add document to secure collection
    add_payload_1 = {
        "collection_name": "testing_create_colection_secure",
        "is_secure": ["mobile_number"],
        "is_non_editable": ["empid"],
        "data": {
            "mobile_number": "09876541",
            "name": "testing_1",
            "empid": 12345
        },
        "status": True
    }
    add_resp_1 = client.post(
        f"/api/bot/{bot_id}/data/collection",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=add_payload_1
    )
    add_payload = {
        "collection_name": "testing_create_colection_secure",
        "is_secure": ["mobile_number"],
        "is_non_editable": ["empid"],
        "data": {
            "mobile_number": "0987654",
            "name": "testing",
            "empid": 1234
        },
        "status": True
    }
    add_resp = client.post(
        f"/api/bot/{bot_id}/data/collection",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=add_payload
    )
    assert add_resp.status_code == 200
    resp_json = add_resp.json()
    print(resp_json)
    assert resp_json["message"] == "Record saved!"
    doc_id = resp_json["data"]["_id"]
    assert doc_id

    # Step 3: List collection data
    list_resp = client.get(
        f"/api/bot/{bot_id}/data/collection/testing_create_colection_secure",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    assert list_resp.status_code == 200
    listed_data = list_resp.json()["data"]["logs"]
    assert any(doc["_id"] == doc_id for doc in listed_data)

    # Step 4: Update the document
    update_payload = {
        "id": doc_id,
        "collection_name": "testing_create_colection_secure",
        "data": {
            "mobile_number":"123456789",
            "name": "testing_updated",
            "empid": 4321  # This should be ignored because it's in `is_non_editable`
        },
        "is_secure": ["mobile_number"],
        "is_non_editable": ["empid"],
        "status": False
    }
    update_resp = client.put(
        f"/api/bot/{bot_id}/data/collection/{doc_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=update_payload
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["message"] == "Record updated!"

    # Verify update — empid should remain unchanged (1234), name should change
    list_resp_after_update = client.get(
        f"/api/bot/{bot_id}/data/collection/testing_create_colection_secure",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    updated_doc = next(doc for doc in list_resp_after_update.json()["data"]["logs"] if doc["_id"] == doc_id)
    assert updated_doc["data"]["name"] == "testing_updated"
    assert updated_doc["data"]["empid"] == 1234  # Unchanged due to is_non_editable

    # Step 5: Delete the document
    delete_doc_resp = client.request(
        method="DELETE",
        url=f"/api/bot/{bot_id}/data/collection/{doc_id}",
        headers={
            "Authorization": pytest.token_type + " " + pytest.access_token,
            "Content-Type": "application/json"
        }
    )
    assert delete_doc_resp.status_code == 200
    assert delete_doc_resp.json()["message"] == "Record deleted!"

    # Step 6: Delete the collection
    delete_coll_resp = client.request(
        method="DELETE",
        url=f"/api/bot/{bot_id}/data/collection/delete/testing_create_colection_secure",
        headers={
            "Authorization": pytest.token_type + " " + pytest.access_token,
            "Content-Type": "application/json"
        })

    assert delete_coll_resp.status_code == 200
    assert delete_coll_resp.json()["data"]["deleted"] >= 1

    delete_resp = client.delete(
        f"/api/account/bot/{bot_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["message"] == "Bot removed"


def test_get_all_collections():
    # Step 1: Create a bot
    add_bot_resp = client.post(
        "/api/account/bot",
        json={"name": "secure-collection-bot_testing"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    assert add_bot_resp.status_code == 200
    bot_id = add_bot_resp.json()["data"]["bot_id"]
    assert bot_id

    # Step 2: Add 4 different collections
    for i in range(1, 5):
        payload = {
            "collection_name": f"collection_{i}",
            "is_secure": ["mobile_number"],
            "is_non_editable": ["empid"],
            "data": {
                "mobile_number": f"999999000{i}",
                "name": f"test_user_{i}",
                "empid": 1000 + i
            },
            "status": True
        }
        add_resp = client.post(
            f"/api/bot/{bot_id}/data/collection",
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
            json=payload
        )
        assert add_resp.status_code == 200
        assert add_resp.json()["message"] == "Record saved!"
        assert add_resp.json()["data"]["_id"]

    # Step 3: Fetch all collections
    get_resp = client.get(
        f"/api/bot/{bot_id}/data/collections/all",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    assert get_resp.status_code == 200
    response_data = get_resp.json()["data"]

    # Step 4: Check the 4 collections are present with count = 1 each
    expected_collections = {f"collection_{i}": 1 for i in range(1, 5)}
    for collection in response_data:
        name = collection["collection_name"]
        count = collection["count"]
        assert name in expected_collections
        assert count == expected_collections[name]

    delete_resp = client.delete(
        f"/api/account/bot/{bot_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["message"] == "Bot removed"

def test_delete_multiple_payload_content_with_empty_list():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.cognition_collections_limit = 20
    bot_settings.llm_settings['enable_faq'] = True
    bot_settings.save()
    metadata = {
        "metadata": None,
        "collection_name": "multiple_delete_test",
        "bot": pytest.bot,
        "user": pytest.username
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json=metadata,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    contents = [
        "A bot is a software application designed to automate tasks.",
        "Bots can perform tasks like answering questions or analyzing data.",
        "Some bots control physical machines, craeate leads or play games."
    ]
    content_ids = []
    for content in contents:
        payload = {
            "data": content,
            "content_type": "text",
            "collection": "multiple_delete_test"
        }
        response = client.post(
            url=f"/api/bot/{pytest.bot}/data/cognition",
            json=payload,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["message"] == "Record saved!"
        assert actual["data"]["_id"]
        assert actual["error_code"] == 0
        content_ids.append(actual["data"]["_id"])
    data=json.dumps(content_ids)
    data={
        "row_ids":[]
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/delete_multiple",
        json=data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"][0]["msg"] == 'row_ids must be a non-empty list of valid strings'

def test_delete_multiple_payload_content():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.cognition_collections_limit = 20
    bot_settings.llm_settings['enable_faq'] = True
    bot_settings.save()
    metadata = {
        "metadata": None,
        "collection_name": "multiple_delete_test1",
        "bot": pytest.bot,
        "user": pytest.username
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json=metadata,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    contents = [
        "A bot is a software application designed to automate tasks.",
        "Bots can perform tasks like answering questions or analyzing data.",
        "Some bots control physical machines, craeate leads or play games."
    ]
    content_ids = []
    for content in contents:
        payload = {
            "data": content,
            "content_type": "text",
            "collection": "multiple_delete_test1"
        }
        response = client.post(
            url=f"/api/bot/{pytest.bot}/data/cognition",
            json=payload,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["message"] == "Record saved!"
        assert actual["data"]["_id"]
        assert actual["error_code"] == 0
        content_ids.append(actual["data"]["_id"])
    data={
        "row_ids":content_ids
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/delete_multiple",
        json=data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "Records deleted!"

def test_add_global_widget_config():
    response = client.post(
        url=f"/api/bot/{pytest.bot}/widgets/global_filter_config",
        json={
           "global_config": [
                {
                    "type": "dateRange",
                    "title": "Date Range",
                    "initialStartDate": "2023-01-01",
                    "initialEndDate": "2023-06-30"
                },
                {
                    "type": "categorical",
                    "title": "Regions",
                    "name": "Region",
                    "options": [
                        {"value": "mh", "label": "Maharashtra"},
                        {"value": "mp", "label": "Madhya Pradesh"}
                    ]
                }
            ]
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Global Filter config added!"
    assert actual["data"]
    pytest.global_widget_id = actual["data"]
    assert actual["error_code"] == 0


def test_add_global_widget_config_duplicate_should_fail():
    response = client.post(
        url=f"/api/bot/{pytest.bot}/widgets/global_filter_config",
        json={
            "global_config": [
                {
                    "type": "dateRange",
                    "title": "Duplicate Date Range",
                    "initialStartDate": "2024-01-01",
                    "initialEndDate": "2024-06-30"
                }
            ]
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == f"A widget configuration already exists for bot '{pytest.bot}'."
    assert actual["error_code"] == 422


def test_get_global_widget_config():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/widgets/global_filter_config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert "global_config" in actual["data"]
    assert actual["data"]['global_config']["bot"] == pytest.bot
    assert actual["error_code"] == 0

def test_update_global_widget_config():
    response = client.put(
        url=f"/api/bot/{pytest.bot}/widgets/global_filter_config",
        json={
            "global_config": [
                {
                    "type": "categorical",
                    "title": "Updated Regions",
                    "name": "Region",
                    "options": [
                        {"value": "dl", "label": "Delhi"},
                        {"value": "mh", "label": "Maharashtra"}
                    ]
                }
            ]
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Global Filter config updated!"
    assert actual["error_code"] == 0

def test_delete_global_widget_config():
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/widgets/global_filter_config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Global Filter config removed!"
    assert actual["error_code"] == 0

def test_update_global_widget_config_should_fail():
    response = client.put(
        url=f"/api/bot/{pytest.bot}/widgets/global_filter_config",
        json={
            "global_config": [
                {
                    "type": "categorical",
                    "title": "Regions",
                    "name": "Region",
                    "options": [
                        {"value": "dl", "label": "Delhi"},
                        {"value": "mh", "label": "Maharashtra"}
                    ]
                }
            ]
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == f"No global config found for bot '{pytest.bot}'."
    assert actual["error_code"] == 422

def test_delete_global_widget_config_should_pass_when_not_exist():
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/widgets/global_filter_config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == f"No global config found for bot '{pytest.bot}'."


def test_get_client_config_with_nudge_server_url():
    expected_app_server_url = Utility.environment['app']['server_url']
    expected_nudge_server_url = Utility.environment['nudge']['server_url']
    expected_chat_server_url = Utility.environment['model']['agent']['url']

    response = client.get(f"/api/bot/{pytest.bot}/chat/client/config",
                          headers={"Authorization": pytest.token_type + " " + pytest.access_token})
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert actual["data"]["welcomeMessage"] == 'Hello! How are you?'
    assert actual["data"]["name"] == 'kairon'
    assert actual["data"]["buttonType"] == 'button'
    assert actual["data"]["whitelist"] == ["*"]
    assert actual["data"]["nudge_server_url"] == expected_nudge_server_url
    assert actual["data"]["api_server_host_url"] == expected_app_server_url
    assert actual["data"]["chat_server_base_url"] == expected_chat_server_url



def test_get_llm_metadata():
    secrets = [
        {
            "llm_type": "openai",
            "api_key": "common_openai_key",
            "models": ["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            "user": "123",
            "bot": pytest.bot,
            "timestamp": utc_now()
        },
        {
            "llm_type": "anthropic",
            "api_key": "custom_claude_key",
            "models": ["claude-3-7-sonnet-20250219"],
            "bot": pytest.bot,
            "user": "123",
            "timestamp": utc_now()
        }
    ]

    for secret in secrets:
        LLMSecret(**secret).save()

    response = client.get(
        url=f"/api/bot/{pytest.bot}/metadata/llm",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"] is True
    assert actual["message"] is None

    assert "data" in actual
    assert "openai" in actual["data"]
    assert "model" in actual["data"]["openai"]["properties"]
    assert actual["data"]["openai"]["properties"]["model"]["enum"] == ["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"]

    assert "anthropic" in actual["data"]
    assert "model" in actual["data"]["anthropic"]["properties"]
    assert actual["data"]["anthropic"]["properties"]["model"]["enum"] == ["claude-3-7-sonnet-20250219"]


def test_get_llm_metadata_bot_specific_model_exists():

    secrets = [
        {
            "llm_type": "openai",
            "api_key": "common_openai_key",
            "models": ["common_openai_model1", "common_openai_model2"],
            "user": "123",
            "bot": pytest.bot,
            "timestamp": utc_now()
        },
        {
            "llm_type": "anthropic",
            "api_key": "custom_claude_key",
            "models": ["common_claude_model1", "common_claude_model2", "custom_claude_model1"],
            "bot": pytest.bot,
            "user": "123",
            "timestamp": utc_now()
        }
    ]

    for secret in secrets:
        LLMSecret(**secret).save()

    response = client.get(
        url=f"/api/bot/{pytest.bot}/metadata/llm",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"] is True
    assert actual["data"]["openai"]["properties"]["model"]["enum"] == ["common_openai_model1", "common_openai_model2"]
    assert actual["data"]["anthropic"]["properties"]["model"]["enum"] == ["common_claude_model1", "common_claude_model2", "custom_claude_model1"]
    LLMSecret.objects.delete()


@responses.activate
@patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
def test_get_instagram_user_posts(mock_get_config, monkeypatch):
    from kairon.shared.channels.instagram.processor import InstagramProcessor

    mock_get_config.return_value = {
        'bot': '689097feb37ee2678aedd0cd',
        'connector_type': 'instagram',
        'config': {
            'app_secret': 'cdb69bc72e2ccb7a869f20cbb6b0229a',
            'page_access_token': 'EAAGa50I7D7cBAJ4AmXOhYAeOOZAyJ9fxOclQmn52hBwrOJJWBOxuJNXqQ2uN667z4vLekSEqnCQf41hcxKVZAe2pAZBrZCTENEj1IBe1CHEcG7J33ZApED9Tj9hjO5tE13yckNa8lP3lw2IySFqeg6REJR3ZCJUvp2h03PQs4W5vNZBktWF3FjQYz5vMEXLPzAFIJcZApBtq9wZDZD',
            'verify_token': 'kairon-instagram-token',
            'is_dev': True,
            'post_config': {
                '17859719991451845': {
                    'keywords': ['offer', 'discount'],
                    'comment_reply': 'Grab our latest offers and discounts on shoes before they run out!'
                },
                '17859719991451973': {
                    'keywords': ['hi', 'price'],
                    'comment_reply': 'Hi there! Yes, we offer the best prices on premium quality shoes!'
                },
                '17859719991451321': {
                    'keywords': ['hello', 'offer']}}},
        'meta_config': {}
    }

    async def fake_get_user_media_posts(self):
        return {"data": [
            {
                "id": "17859719991451973",
                "ig_id": "3682168664448337756",
                "media_product_type": "FEED",
                "media_type": "IMAGE",
                "media_url": "https://scontent.cdninstagram.com/v/t39.30808-6/523122870_122185919582569325_790599521546845755_n.jpg?stp=dst-jpg_e35_tt6&_nc_cat=100&ccb=1-7&_nc_sid=18de74&_nc_ohc=7YYhBBUOvsQQ7kNvwESQCKD&_nc_oc=AdmaDolEqkLcifMAyuwYg70gHJNAeLHZqKBOWYTOtRCZ_PmWP7xruqnCsygI9ZPgPnU&_nc_zt=23&_nc_ht=scontent.cdninstagram.com&edm=AM6HXa8EAAAA&_nc_gid=MMqhUvMR4L69GkDMm6bQug&oh=00_AfSQcTvOKOFu0xqZYAMPAEe9r3sN3UKD0KhRvF39X1araA&oe=6887FF72",
                "timestamp": "2025-07-22T07:18:52+0000",
                "username": "maheshsv17",
                "permalink": "https://www.instagram.com/p/DMZsOQvhIdc/",
                "caption": "TEST",
                "like_count": 0,
                "comments_count": 0
            }
        ]}

    monkeypatch.setattr(InstagramProcessor, "get_user_media_posts", fake_get_user_media_posts)

    response = client.get(
        f"/api/bot/{pytest.bot}/channels/user/posts",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"] is True
    assert actual["message"] is None
    assert actual['data'] == [
            {
                "id": "17859719991451973",
                "ig_id": "3682168664448337756",
                "media_product_type": "FEED",
                "media_type": "IMAGE",
                "media_url": "https://scontent.cdninstagram.com/v/t39.30808-6/523122870_122185919582569325_790599521546845755_n.jpg?stp=dst-jpg_e35_tt6&_nc_cat=100&ccb=1-7&_nc_sid=18de74&_nc_ohc=7YYhBBUOvsQQ7kNvwESQCKD&_nc_oc=AdmaDolEqkLcifMAyuwYg70gHJNAeLHZqKBOWYTOtRCZ_PmWP7xruqnCsygI9ZPgPnU&_nc_zt=23&_nc_ht=scontent.cdninstagram.com&edm=AM6HXa8EAAAA&_nc_gid=MMqhUvMR4L69GkDMm6bQug&oh=00_AfSQcTvOKOFu0xqZYAMPAEe9r3sN3UKD0KhRvF39X1araA&oe=6887FF72",
                "timestamp": "2025-07-22T07:18:52+0000",
                "username": "maheshsv17",
                "permalink": "https://www.instagram.com/p/DMZsOQvhIdc/",
                "caption": "TEST",
                "like_count": 0,
                "comments_count": 0
            }
        ]

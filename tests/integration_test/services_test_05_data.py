from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training



@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_add_scheduled_broadcast_with_no_template_name(mock_event_server):
    config = {
        "name": "first_scheduler_dynamic",
        "broadcast_type": "dynamic",
        "connector_type": "whatsapp",
        "scheduler_config": {
            "expression_type": "cron",
            "schedule": "21 11 * * *",
            "timezone": "Asia/Kolkata",
        },
        "pyscript": "send_msg('template_name', '9876543210')",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', '__root__'],
                                  'msg': 'template_name is required for dynamic broadcasts!', 'type': 'value_error'}]
    assert not actual["data"]


@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_add_scheduled_broadcast_with_no_language_code(mock_event_server):
    config = {
        "name": "first_scheduler_dynamic",
        "broadcast_type": "dynamic",
        "connector_type": "whatsapp",
        "template_name": "consent",
        "scheduler_config": {
            "expression_type": "cron",
            "schedule": "21 11 * * *",
            "timezone": "Asia/Kolkata",
        },
        "pyscript": "send_msg('template_name', '9876543210')",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', '__root__'],
                                  'msg': 'language_code is required for dynamic broadcasts!', 'type': 'value_error'}]
    assert not actual["data"]


def test_logout():
    response = client.post(
        "/api/auth/login",
        data={"username": "integration@demo.ai", "password": "Welcome@10"},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0

    access_token = actual["data"]["access_token"]
    token_type = actual["data"]["token_type"]
    response = client.post(
        url=f"/api/auth/logout",
        headers={"Authorization": token_type + " " + access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["message"] == "User Logged out!"
    assert not actual["data"]
    assert actual["error_code"] == 0

    values = list(AuditLogData.objects(user="integration@demo.ai", action='activity', entity='logout').order_by(
        "-timestamp"))
    audit_log_data = values[0].to_mongo().to_dict()
    print(audit_log_data)
    assert audit_log_data["action"] == 'activity'
    assert audit_log_data['entity'] == 'logout'
    assert audit_log_data['user'] == 'integration@demo.ai'
    assert audit_log_data['data']['username'] == 'integration@demo.ai'

def test_payload_upload_api_with_float_field(monkeypatch):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.cognition_collections_limit = 20
    bot_settings.llm_settings['enable_faq'] = True
    bot_settings.save()
    metadata = {
        "metadata": [{"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True},
                     {"column_name": "price", "data_type": "float", "enable_search": True, "create_embeddings": True}],
        "collection_name": "with_float_field",
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json=metadata,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    payload = {
        "data": {"item": "Box","price":54.02},
        "content_type": "json",
        "collection": "with_float_field"
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    pytest.payload_id = actual["data"]["_id"]
    assert actual["message"] == "Record saved!"
    assert actual["data"]["_id"]
    assert actual["error_code"] == 0

    cognition_data = CognitionData.objects(bot=pytest.bot, collection="with_float_field").first()
    assert cognition_data is not None
    data_dict = cognition_data.to_mongo().to_dict()
    assert data_dict['data']['item'] == 'Box'
    assert data_dict['data']['price'] == 54.02
    CognitionData.objects(bot=pytest.bot, collection="with_float_field").delete()
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.llm_settings['enable_faq'] = False
    bot_settings.save()
    CognitionSchema.objects(bot=pytest.bot, collection_name="with_float_field").delete()

def test_payload_upload_api_with_float_field_value_integer(monkeypatch):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.content_importer_limit_per_day = 10
    bot_settings.cognition_collections_limit = 20
    bot_settings.llm_settings['enable_faq'] = True
    bot_settings.save()
    metadata = {
        "metadata": [{"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True},
                     {"column_name": "price", "data_type": "float", "enable_search": True, "create_embeddings": True}],
        "collection_name": "with_float_field_value_integer",
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json=metadata,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    payload = {
        "data": {"item": "Box","price":54},
        "content_type": "json",
        "collection": "with_float_field_value_integer"
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    pytest.payload_id = actual["data"]["_id"]
    assert actual["message"] == "Record saved!"
    assert actual["data"]["_id"]
    assert actual["error_code"] == 0

    cognition_data = CognitionData.objects(bot=pytest.bot, collection="with_float_field_value_integer").first()
    assert cognition_data is not None
    data_dict = cognition_data.to_mongo().to_dict()
    assert data_dict['data']['item'] == 'Box'
    assert isinstance(data_dict['data']['price'], float)
    assert data_dict['data']['price'] == 54.0
    CognitionData.objects(bot=pytest.bot, collection="with_float_field_value_integer").delete()
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.llm_settings['enable_faq'] = False
    bot_settings.save()
    CognitionSchema.objects(bot=pytest.bot, collection_name="with_float_field_value_integer").delete()

def test_update_payload_upload_api_with_float_field_value_integer(monkeypatch):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.content_importer_limit_per_day = 10
    bot_settings.cognition_collections_limit = 20
    bot_settings.llm_settings['enable_faq'] = True
    bot_settings.save()
    metadata = {
        "metadata": [{"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True},
                     {"column_name": "price", "data_type": "float", "enable_search": True, "create_embeddings": True}],
        "collection_name": "update_with_float_field_value_integer",
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json=metadata,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    payload = {
        "data": {"item": "Box","price":54.08},
        "content_type": "json",
        "collection": "update_with_float_field_value_integer"
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    pytest.payload_id = actual["data"]["_id"]
    assert actual["message"] == "Record saved!"
    assert actual["data"]["_id"]
    assert actual["error_code"] == 0

    cognition_data = CognitionData.objects(bot=pytest.bot, collection="update_with_float_field_value_integer").first()
    assert cognition_data is not None
    data_dict = cognition_data.to_mongo().to_dict()
    assert data_dict['data']['item'] == 'Box'
    assert isinstance(data_dict['data']['price'], float)
    assert data_dict['data']['price'] == 54.08



    update_payload = {
        "data": {"item": "Box", "price": 27},
        "content_type": "json",
        "collection": "update_with_float_field_value_integer"
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/cognition/{pytest.payload_id}",
        json=update_payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Record updated!"
    assert actual["error_code"] == 0

    cognition_data = CognitionData.objects(bot=pytest.bot, collection="update_with_float_field_value_integer").first()
    assert cognition_data is not None
    data_dict = cognition_data.to_mongo().to_dict()
    assert data_dict['data']['item'] == 'Box'
    assert isinstance(data_dict['data']['price'], float)
    assert data_dict['data']['price'] == 27.0
    CognitionData.objects(bot=pytest.bot, collection="update_with_float_field_value_integer").delete()
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.llm_settings['enable_faq'] = False
    bot_settings.save()
    CognitionSchema.objects(bot=pytest.bot, collection_name="update_with_float_field_value_integer").delete()


@responses.activate
def test_default_values():
    response = client.get(
        "/api/system/default/names"
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0

    expected_default_names = [
        "restart", "back", "out_of_scope", "session_start", "nlu_fallback",
        "action_listen", "action_restart", "action_session_start", "action_send_text", "action_default_fallback",
        "action_deactivate_loop", "action_revert_fallback_events", "action_default_ask_affirmation",
        "action_default_ask_rephrase", "action_two_stage_fallback", "action_unlikely_intent",
        "action_back", "...", "action_extract_slots",
        "requested_slot", "session_started_metadata", "knowledge_base_listed_objects",
        "knowledge_base_last_object", "knowledge_base_last_object_type"
    ]

    assert sorted(actual["data"]["default_names"]) == sorted(expected_default_names)

def test_odoo_registration():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.pos_enabled = True
    bot_settings.save()
    with patch("kairon.pos.definitions.factory.POSFactory.get_instance") as mock_factory:

        mock_pos = MagicMock()
        mock_pos.return_value.onboarding.return_value = {"ok": True}

        mock_factory.return_value = mock_pos

        payload = {
            "client_name": "XYZ_Pvt_Ltd"
        }


        response = client.post(
            url=f"/api/bot/{pytest.bot}/pos/odoo/register",
            json=payload,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )

        actual = response.json()
        assert actual["success"]
        assert actual["data"] ==  {'ok': True}
        mock_factory.assert_called_once_with("odoo")
        mock_pos.return_value.onboarding.assert_called_once_with(
            client_name="XYZ_Pvt_Ltd",
            bot=pytest.bot,
            user='integration@demo.ai'
        )

def test_odoo_login():
    with patch("kairon.pos.definitions.factory.POSFactory.get_instance") as mock_factory:

        mock_pos = MagicMock()
        mock_pos.return_value.authenticate.return_value = {"ok": True}

        mock_factory.return_value = mock_pos

        payload = {
            "client_name": "XYZ_Pvt_Ltd",
            "page_type": "pos_products"
        }

        response = client.post(
            url=f"/api/bot/{pytest.bot}/pos/odoo/login",
            json=payload,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )

        actual = response.json()
        assert actual ==  {'ok': True}
        mock_factory.assert_called_once_with("odoo")
        mock_pos.return_value.authenticate.assert_called_once_with(
            client_name="XYZ_Pvt_Ltd",
            page_type="pos_products",
            bot=pytest.bot,
            company_id=1
        )

def test_bulk_save_success():
    request_body = {
        "payload": [
            {
                "collection_name": "test_data",
                "is_secure": ["name"],
                "is_non_editable": ["email"],
                "data": {
                    "name": "Aniket",
                    "email": "aniket@example.com"
                }
            }
        ]
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/collection/bulk/test_bulk_save_success",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["message"] == "Bulk save completed"
    assert actual["success"]
    assert "data" in actual
    CollectionData.objects(collection_name="test_bulk_save_success").delete()


def test_bulk_save_with_missing_is_secure_key():
    request_body = {
        "payload": [
            {
                "collection_name": "user",
                "is_secure": ["name", "aadhar"],
                "data": {
                    "name": "Aniket",
                    "email": "aniket@example.com"
                }
            }
        ]
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/collection/bulk/test_bulk_save_success",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == [{
        "loc": ["body", "payload", 0, "__root__"],
        "msg": "is_secure contains keys that are not present in data",
        "type": "value_error"
    }]
    assert not actual["success"]
    assert actual["data"] is None


def test_bulk_save_with_data_none():
    request_body = {
        "payload": [
            {
                "collection_name": "user",
                "is_secure": ["name"],
                "data": None
            }
        ]
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/collection/bulk/test_bulk_save_success",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["error_code"] == 422
    assert not actual["success"]
    assert actual["data"] is None

    error_messages = [msg["msg"] for msg in actual["message"]]
    assert "data cannot be empty and should be of type dict!" in error_messages
    assert "none is not an allowed value" in error_messages

def test_bulk_empty_payload():
    request_body = {
        "payload": [
        ]
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/collection/bulk/test_bulk_save_success",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["error_code"] == 422
    assert not actual["success"]


    error_messages = [msg["msg"] for msg in actual["message"]]
    assert "payload must contain at least one item" in error_messages


def test_bulk_save_with_empty_collection_name():
    request_body = {
        "payload": [
            {
                "collection_name": "  ",
                "data": {"name": "Aniket"},
                "is_secure": [],
                "is_non_editable": []
            }
        ]
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/collection/bulk/test_bulk_save_success",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"][0]["msg"] == "collection_name should not be empty!"
    assert not actual["success"]
    assert actual["data"] is None


def test_bulk_save_with_non_editable_key_missing_in_data():
    request_body = {
        "payload": [
            {
                "collection_name": "user",
                "data": {
                    "name": "Aniket",
                },
                "is_secure": [],
                "is_non_editable": ["email"]
            }
        ]
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/collection/bulk/test_bulk_save_success",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["message"][0]["msg"] == "is_non_editable contains keys that are not present in data"
    assert not actual["success"]
    assert actual["data"] is None


def test_bulk_save_with_invalid_types():
    request_body = {
        "payload": [
            {
                "collection_name": "user",
                "data": {"name": "Aniket"},
                "is_secure": "name",
                "is_non_editable": []
            }
        ]
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/collection/bulk/test_bulk_save_success",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["data"] is None
    error_messages = [msg["msg"] for msg in actual["message"]]
    assert "is_secure should be list of keys!" in error_messages
    assert "value is not a valid list" in error_messages


@responses.activate
def test_upload_file_content_success():
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.upload_file_handler}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )
    file = {
        "file_content": ("Salesstore.csv", open("tests/testing_data/file_content_upload/Salesstore.csv", "rb"))
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/data/upload/collection_data/test_collection_data?overwrite=False",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=file,
    )

    actual = response.json()
    assert actual["success"]
    assert actual["message"] == "File content upload in progress! Check logs."
    assert actual["error_code"] == 0

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.upload_file_handler, upload_type="crud_data", collection_name="test_collection_data", overwrite=False
    )


    response = client.get(
        f"/api/bot/{pytest.bot}/logs/file_upload?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    print(actual)
    assert actual["success"]
    assert actual["error_code"] == 0
    logs = actual['data']['logs']
    assert len(logs) == 1
    assert logs[0]['file_name'] == 'Salesstore.csv'
    assert logs[0]['status'] == STATUSES.SUCCESS.value
    assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value
    assert logs[0]['is_uploaded']
    assert logs[0]['start_timestamp'] is not None
    assert logs[0]['end_timestamp'] is not None
    assert logs[0]['upload_errors'] == {}
    assert logs[0]['exception'] == ''

    from_date = date.today()
    to_date = from_date + timedelta(days=1)

    search_response = client.get(
        f"/api/bot/{pytest.bot}/logs/file_upload/search"
        f"?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": f"{pytest.token_type} {pytest.access_token}"},
    )
    response_json = search_response.json()
    assert response_json["success"] is True
    assert response_json["error_code"] == 0

    data = response_json["data"]
    assert "logs" in data
    assert isinstance(data["logs"], list)
    CollectionData.objects(collection_name="test_collection_data").delete()


@patch("kairon.api.app.routers.bot.data.UploadHandler")
def test_upload_file_content_no_enqueue_when_validate_false(mock_upload_handler):
    """Test that file upload does not enqueue event when validation fails."""

    mock_event_instance = MagicMock()
    mock_event_instance.validate.return_value = False
    mock_upload_handler.return_value = mock_event_instance

    files = {
        "file_content": ("Salesstore.csv", open("tests/testing_data/file_content_upload/Salesstore.csv", "rb"))
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/data/upload/collection_data/test_collection?overwrite=true",
        files=files,
        headers={"Authorization": f"{pytest.token_type} {pytest.access_token}"},
    )

    actual = response.json()
    assert response.status_code == 200
    assert actual["success"] is True
    assert actual["message"] == "File content upload in progress! Check logs."
    assert actual["error_code"] == 0
    mock_event_instance.enqueue.assert_not_called()

def test_get_broadcast_filter_count():
    CollectionData(
        bot=pytest.bot,
        user="test_user_1",
        collection_name="crop_details_test",
        data={
            "name": "Mahesh",
            "mobile_number": "9876543000",
            "crop": "wheat",
            "status": "stage-1",
            "age": "26"
        }
    ).save()
    CollectionData(
        bot=pytest.bot,
        user="test_user_1",
        collection_name="crop_details_test",
        data={
            "name": "Ganesh",
            "mobile_number": "9876543001",
            "crop": "Paddy",
            "status": "stage-2",
            "age": "26"
        }
    ).save()
    CollectionData(
        bot=pytest.bot,
        user="test_user_1",
        collection_name="crop_details_test",
        data={
            "name": "Hitesh",
            "mobile_number": "9876543001",
            "crop": "Okra",
            "status": "stage-4",
            "age": "27"
        }
    ).save()
    CollectionData(
        bot=pytest.bot,
        user="test_user_1",
        collection_name="crop_details_test",
        data={
            "name": "Aniket",
            "mobile_number": "6203115367",
            "crop": "wheat",
            "status": "stage-3",
            "age": "27"
        }
    ).save()


    filters_list = [
        {"column": "age", "condition": "gte", "value": "26"},
        {"column": "name", "condition": "nin", "value": ["Mahesh"]},
    ]

    # API call
    response = client.get(
        f"/api/bot/{pytest.bot}/data/collections/crop_details_test/filter/count",
        params={"filters": json.dumps(filters_list)},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    # Response validation
    actual = response.json()
    assert response.status_code == 200
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Filtered count fetched successfully"
    assert actual["data"]["count"] == 3

def test_get_broadcast_filter_count_no_filter():
    response = client.get(
        f"/api/bot/{pytest.bot}/data/collections/crop_details_test/filter/count",
        params={"filters": []},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert response.status_code == 200
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Filtered count fetched successfully"
    assert actual["data"]["count"] == 4
    CollectionData.objects(bot = pytest.bot, collection_name = "crop_details_test").delete()

@responses.activate
@patch("kairon.shared.chat.user_media.UserMedia.get_media_content_buffer")
def test_bsp_upload_media_success(mock_get_buffer):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.whatsapp = "360dialog"
    bot_settings.save()

    Channels(
        bot=pytest.bot,
        connector_type="whatsapp",
        config={
            "client_name": "dummy",
            "client_id": "dummy",
            "channel_id": "dummy",
            "api_key": "dummy_token",
            "partner_id": "dummy",
            "waba_account_id": "dummy",
            "bsp_type": "360dialog"
        },
        user="test@example.com",
        timestamp=utc_now()
    ).save()

    media_id = "0196c9efbf547b81a66ba2af7b72d5ba"
    bsp_type = "360dialog"
    expected_external_media_id = "abc123"

    UserMediaData(
        media_id=media_id,
        filename="Upload_Download Data.pdf",
        extension=".pdf",
        upload_status=UserMediaUploadStatus.completed.value,
        upload_type="user",
        filesize=410484,
        sender_id="himanshu.gupta_@digite.com",
        bot=pytest.bot,
        timestamp=utc_now(),
        media_url="https://upload-doc-poc.s3.amazonaws.com/user_media/682323a603ec3be7dcaa75bc/himanshu.gt_digite.com_0196c9efbf547b81a66ba2af7b72d5ba_Upload_Download Data.pdf",
        output_filename="user_media/682323a603ec3be7dcaa75bc/himanshu.gupta_digite.com_0196c9efbf547b81a66ba2af7b72d5ba_Upload_Download Data.pdf",
    ).save()

    mock_get_buffer.return_value = (
        io.BytesIO(b"%PDF-1.4 mock content"),
        "Upload_Download Data.pdf",
        ".pdf"
    )

    responses.add(
        responses.POST,
        "https://waba-v2.360dialog.io/media",
        json={"id": expected_external_media_id},
        status=200,
        content_type="application/json"
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/channels/media/upload/{bsp_type}/{media_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert response.status_code == 200
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["external_media_id"] == expected_external_media_id

    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.whatsapp = "meta"
    bot_settings.save()
    UserMediaData.objects().delete()
    Channels.objects().delete()

def test_bsp_upload_media_media_id_not_found():
    media_id = "non_existing_media_id"
    bsp_type = "360dialog"

    response = client.get(
        f"/api/bot/{pytest.bot}/channels/media/upload/{bsp_type}/{media_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert "UserMediaData not found for media_id: non_existing_media_id" in actual["message"]


def test_bsp_upload_media_channel_not_configured():
    media_id = "non_existing_media_id"
    bsp_type = "360dialog"

    UserMediaData(
        media_id=media_id,
        filename="no_stream.pdf",
        extension=".pdf",
        upload_status=UserMediaUploadStatus.completed.value,
        upload_type="user",
        filesize=410484,
        sender_id="test@digite.com",
        bot=pytest.bot,
        timestamp=utc_now(),
        media_url="some_url",
        output_filename="output_file.pdf",
    ).save()

    response = client.get(
        f"/api/bot/{pytest.bot}/channels/media/upload/{bsp_type}/{media_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert f"Channel config not found for bot: {pytest.bot}, connector_type: whatsapp, bsp_type: {bsp_type}" in actual["message"]
    UserMediaData.objects().delete()


def test_bsp_upload_media_access_token_not_found():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.whatsapp = "360dialog"
    bot_settings.save()

    Channels(
        bot=pytest.bot,
        connector_type="whatsapp",
        config={
            "client_name": "dummy",
            "client_id": "dummy",
            "channel_id": "dummy",
            "api_key": "",
            "partner_id": "dummy",
            "waba_account_id": "dummy",
            "bsp_type": "360dialog"
        },
        user="test@example.com",
        timestamp=utc_now()
    ).save()

    media_id = "non_existing_media_id"
    bsp_type = "360dialog"

    UserMediaData(
        media_id=media_id,
        filename="no_stream.pdf",
        extension=".pdf",
        upload_status=UserMediaUploadStatus.completed.value,
        upload_type="user",
        filesize=410484,
        sender_id="test@digite.com",
        bot=pytest.bot,
        timestamp=utc_now(),
        media_url="some_url",
        output_filename="output_file.pdf",
    ).save()

    response = client.get(
        f"/api/bot/{pytest.bot}/channels/media/upload/{bsp_type}/{media_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert "API key (access token) not found in channel config" in actual["message"]

    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.whatsapp = "meta"
    bot_settings.save()
    UserMediaData.objects().delete()
    Channels.objects().delete()

@patch("kairon.shared.chat.user_media.UserMedia.get_media_content_buffer")
def test_bsp_upload_media_no_file_stream(mock_get_buffer):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.whatsapp = "360dialog"
    bot_settings.save()

    Channels(
        bot=pytest.bot,
        connector_type="whatsapp",
        config={
            "client_name": "dummy",
            "client_id": "dummy",
            "channel_id": "dummy",
            "api_key": "dummy_token",
            "partner_id": "dummy",
            "waba_account_id": "dummy",
            "bsp_type": "360dialog"
        },
        user="test@example.com",
        timestamp=utc_now()
    ).save()

    media_id = "no_stream_media_id"
    bsp_type = "360dialog"

    UserMediaData(
        media_id=media_id,
        filename="no_stream.pdf",
        extension=".pdf",
        upload_status=UserMediaUploadStatus.completed.value,
        upload_type="user",
        filesize=410484,
        sender_id="test@digite.com",
        bot=pytest.bot,
        timestamp=utc_now(),
        media_url="some_url",
        output_filename="output_file.pdf",
    ).save()

    mock_get_buffer.return_value = (None, "no_stream.pdf", ".pdf")

    response = client.get(
        f"/api/bot/{pytest.bot}/channels/media/upload/{bsp_type}/{media_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert "File stream not found" in actual["message"]

    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.whatsapp = "meta"
    bot_settings.save()
    UserMediaData.objects().delete()
    Channels.objects().delete()


@responses.activate
@patch("kairon.shared.chat.user_media.UserMedia.get_media_content_buffer")
def test_bsp_upload_media_360dialog_upload_failed(mock_get_buffer):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.whatsapp = "360dialog"
    bot_settings.save()

    Channels(
        bot=pytest.bot,
        connector_type="whatsapp",
        config={
            "client_name": "dummy",
            "client_id": "dummy",
            "channel_id": "dummy",
            "api_key": "dummy_token",
            "partner_id": "dummy",
            "waba_account_id": "dummy",
            "bsp_type": "360dialog"
        },
        user="test@example.com",
        timestamp=utc_now()
    ).save()
    media_id = "upload_fail_media"
    bsp_type = "360dialog"

    UserMediaData(
        media_id=media_id,
        filename="upload_fail.pdf",
        extension=".pdf",
        upload_status=UserMediaUploadStatus.completed.value,
        upload_type="user",
        filesize=410484,
        sender_id="test@digite.com",
        bot=pytest.bot,
        timestamp=utc_now(),
        media_url="some_url",
        output_filename="output_file.pdf",
    ).save()

    mock_get_buffer.return_value = (
        io.BytesIO(b"%PDF mock"),
        "upload_fail.pdf",
        ".pdf"
    )

    responses.add(
        responses.POST,
        "https://waba-v2.360dialog.io/media",
        body="Failure Test Case Simulation",
        status=400,
        content_type="application/json"
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/channels/media/upload/{bsp_type}/{media_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert "Failure Test Case Simulation" in actual["message"]

    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.whatsapp = "meta"
    bot_settings.save()
    UserMediaData.objects().delete()
    Channels.objects().delete()

def test_get_user_media_data_with_no_data():
    response = client.get(
        f"/api/bot/{pytest.bot}/data/user/media/data",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    data = response.json()
    print(data)

    assert data["success"]
    assert data["data"] == []
    assert data["error_code"] == 0
    assert data["message"]


def test_get_user_media_data():
    UserMediaData(
        media_id="0196c9efbf547b81a66ba2af7b72d5ba",
        filename="whataspp_360_885215267637065.jpg",
        extension=".jpg",
        upload_status="Completed",
        upload_type="user",
        filesize=410484,
        additional_info={"description": "Issue description", "phone_number": "919876543210"},
        sender_id="mahesh.sattala@digite.com",
        bot=pytest.bot,
        timestamp=datetime(2026, 2, 20, 5, 37, 17, 59000),
        media_url="https://uat-kairon-upload.s3.amazonaws.com/user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
        output_filename="user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
    ).save()
    UserMediaData(
        media_id="0196c9efbf547b81a66ba2af7b72d5bb",
        filename="whataspp_360_885215267637065.jpg",
        extension=".jpg",
        upload_status="Completed",
        upload_type="user",
        filesize=410484,
        additional_info={"description": "Testing description", "phone_number": "919876543210"},
        sender_id="mahesh.sattala@digite.com",
        bot=pytest.bot,
        timestamp=datetime(2026, 2, 20, 5, 37, 17, 59000),
        media_url="https://uat-kairon-upload.s3.amazonaws.com/user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
        output_filename="user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
    ).save()
    UserMediaData(
        media_id="0196c9efbf547b81a66ba2af7b72d5ba",
        filename="whataspp_360_885215267637065.jpg",
        extension=".jpg",
        upload_status="Completed",
        upload_type="user",
        filesize=410484,
        additional_info={"description": "Issue description 2", "phone_number": "919876543210"},
        sender_id="mahesh.sattala@digite.com",
        bot=pytest.bot,
        timestamp=datetime(2026, 2, 20, 5, 37, 17, 59000),
        media_url="https://uat-kairon-upload.s3.amazonaws.com/user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
        output_filename="user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
    ).save()
    UserMediaData(
        media_id="0196c9efbf547b81a66ba2af7b72d5bb",
        filename="whataspp_360_885215267637065.jpg",
        extension=".jpg",
        upload_status="Failed",
        upload_type="user",
        filesize=410484,
        additional_info={"description": "Testing description 2", "phone_number": "919876543210"},
        sender_id="mahesh.sattala@digite.com",
        bot=pytest.bot,
        timestamp=datetime(2026, 2, 20, 5, 37, 17, 59000),
        media_url="https://uat-kairon-upload.s3.amazonaws.com/user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
        output_filename="user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
    ).save()
    UserMediaData(
        media_id="0196c9efbf547b81a66ba2af7b72d5ba",
        filename="whataspp_360_885215267637065.jpg",
        extension=".jpg",
        upload_status="Completed",
        upload_type="user",
        filesize=410484,
        additional_info={"description": "Issue description 3", "phone_number": "919876543210"},
        sender_id="mahesh.sattala@digite.com",
        bot=pytest.bot,
        timestamp=datetime(2026, 2, 20, 5, 37, 17, 59000),
        media_url="https://uat-kairon-upload.s3.amazonaws.com/user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
        output_filename="user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
    ).save()
    UserMediaData(
        media_id="0196c9efbf547b81a66ba2af7b72d5bb",
        filename="whataspp_360_885215267637065.jpg",
        extension=".jpg",
        upload_status="processing",
        upload_type="system",
        filesize=410484,
        additional_info={"description": "Testing description 4", "phone_number": "919876543210"},
        sender_id="mahesh.sattala@digite.com",
        bot=pytest.bot,
        timestamp=datetime(2026, 2, 20, 5, 37, 17, 59000),
        media_url="https://uat-kairon-upload.s3.amazonaws.com/user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
        output_filename="user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
    ).save()
    UserMediaData(
        media_id="0196c9efbf547b81a66ba2af7b72d5bb",
        filename="whataspp_360_885215267637065.jpg",
        extension=".jpg",
        upload_status="Completed",
        upload_type="system",
        filesize=410484,
        additional_info={"description": "Testing description 5", "phone_number": "919876543210"},
        sender_id="mahesh.sattala@digite.com",
        bot=pytest.bot,
        timestamp=datetime(2026, 2, 20, 5, 37, 17, 59000),
        media_url="https://uat-kairon-upload.s3.amazonaws.com/user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
        output_filename="user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
    ).save()

    response = client.get(
        f"/api/bot/{pytest.bot}/data/user/media/data",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    data = response.json()
    print(data)

    assert data["success"]
    assert data["data"] == [
        {
            'sender_id': 'mahesh.sattala@digite.com',
            'timestamp': '2026-02-20T05:37:17.059000',
            'media_url': 'https://uat-kairon-upload.s3.amazonaws.com/user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg',
            'additional_info': {'description': 'Issue description', 'phone_number': '919876543210'},
        },
        {
            'sender_id': 'mahesh.sattala@digite.com',
            'timestamp': '2026-02-20T05:37:17.059000',
            'media_url': 'https://uat-kairon-upload.s3.amazonaws.com/user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg',
            'additional_info': {'description': 'Testing description', 'phone_number': '919876543210'},
        },
        {
            'sender_id': 'mahesh.sattala@digite.com',
            'timestamp': '2026-02-20T05:37:17.059000',
            'media_url': 'https://uat-kairon-upload.s3.amazonaws.com/user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg',
            'additional_info': {'description': 'Issue description 2', 'phone_number': '919876543210'},
        },
        {
            'sender_id': 'mahesh.sattala@digite.com',
            'timestamp': '2026-02-20T05:37:17.059000',
            'media_url': 'https://uat-kairon-upload.s3.amazonaws.com/user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg',
            'additional_info': {'description': 'Issue description 3', 'phone_number': '919876543210'},
        }
    ]
    assert data["error_code"] == 0
    assert data["message"]


@responses.activate
@mock.patch.object(LLMProcessor, "__collection_exists__", autospec=True)
@mock.patch.object(LLMProcessor, "__create_collection__", autospec=True)
@mock.patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
@patch(
    "kairon.shared.actions.utils.ActionUtility.execute_request_async",
    new_callable=AsyncMock
)
def test_knowledge_vault_sync_push_menu(mock_embedding, mock_collection_exists, mock_create_collection, mock_collection_upsert):
    LLMSecret.objects.delete()
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.content_importer_limit_per_day = 10
    bot_settings.cognition_collections_limit = 10
    bot_settings.llm_settings['enable_faq'] = True
    bot_settings.save()

    mock_collection_exists.return_value = False
    mock_create_collection.return_value = None
    mock_collection_upsert.return_value = None

    embedding = list(np.random.random(LLMProcessor.__embedding__))
    embedding = [[0.1] * 3072, [0.1] * 3072]

    mock_embedding.return_value = (
        embedding,
        200,
        0.05,
        {}
    )

    secrets = [
        {
            "llm_type": "openai",
            "api_key": "common_openai_key",
            "models": ["common_openai_model1", "common_openai_model2"],
            "user": "123",
            "timestamp": utc_now()
        },
    ]

    for secret in secrets:
        LLMSecret(**secret).save()

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "price", "data_type": "float", "enable_search": True, "create_embeddings": True},
                {"column_name": "quantity", "data_type": "int", "enable_search": True, "create_embeddings": True},
            ],
            "collection_name": "groceries"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    schema_response = response.json()
    assert schema_response["message"] == "Schema saved!"
    assert schema_response["error_code"] == 0

    dummy_data = {
        "id": 1,
        "item": "Juice",
        "price": 2.00,
        "quantity": 9
    }
    dummy_doc = CognitionData(
        data=dummy_data,
        content_type="json",
        collection="groceries",
        user="himanshu.gupta@digite.com",
        bot=pytest.bot,
        timestamp=utc_now()
    )
    dummy_doc.save()

    cognition_data = CognitionData.objects(bot=pytest.bot, collection="groceries")
    assert cognition_data.count() == 1

    sync_data = [
        {"id": 1, "item": "Juice", "price": 2.50, "quantity": 10},
        {"id": 2, "item": "Apples", "price": 1.20, "quantity": 20}
    ]

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/sync?primary_key_col=id&collection_name=groceries&sync_type=push_menu",
        json=sync_data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual= response.json()
    assert actual["success"]
    assert actual["message"] == "Processing completed successfully"
    assert actual["error_code"] == 0

    cognition_data = CognitionData.objects(bot=pytest.bot, collection="groceries")
    assert cognition_data.count() == 2

    expected_data = [
        {"id": 1, "item": "Juice", "price": 2.50, "quantity": 10},
        {"id": 2, "item": "Apples", "price": 1.20, "quantity": 20}
    ]

    for index, doc in enumerate(cognition_data):
        doc_data = doc.to_mongo().to_dict()["data"]
        assert doc_data == expected_data[index]

    call_kwargs = mock_embedding.call_args[1]

    assert call_kwargs["request_method"] == "POST"
    assert call_kwargs["timeout"] == 30

    assert call_kwargs["http_url"] == (
        f"http://localhost/{pytest.bot}/aembedding/openai"
    )

    request_body = call_kwargs["request_body"]

    assert request_body["user"] == "integration@demo.ai"

    assert request_body["kwargs"]["api_key"] == "common_openai_key"
    assert request_body["kwargs"]["invocation"] == "knowledge_vault_sync"


    CognitionData.objects(bot=pytest.bot, collection="groceries").delete()
    CognitionSchema.objects(bot=pytest.bot, collection_name="groceries").delete()
    LLMSecret.objects.delete()


@responses.activate
@mock.patch.object(LLMProcessor, "__collection_exists__", autospec=True)
@mock.patch.object(LLMProcessor, "__create_collection__", autospec=True)
@mock.patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
@patch(
    "kairon.shared.actions.utils.ActionUtility.execute_request_async",
    new_callable=AsyncMock
)
def test_knowledge_vault_sync_item_toggle(mock_embedding, mock_collection_exists, mock_create_collection, mock_collection_upsert):
    LLMSecret.objects.delete()
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.content_importer_limit_per_day = 10
    bot_settings.cognition_collections_limit = 10
    bot_settings.llm_settings['enable_faq'] = True
    bot_settings.save()

    mock_collection_exists.return_value = False
    mock_create_collection.return_value = None
    mock_collection_upsert.return_value = None

    embedding = list(np.random.random(LLMProcessor.__embedding__))

    embedding = [[0.1] * 3072, [0.1] * 3072]
    mock_embedding.return_value = (
        embedding,
        200,
        0.05,
        {}
    )

    secrets = [
        {
            "llm_type": "openai",
            "api_key": "common_openai_key",
            "models": ["common_openai_model1", "common_openai_model2"],
            "user": "123",
            "timestamp": utc_now()
        },
    ]

    for secret in secrets:
        LLMSecret(**secret).save()

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "price", "data_type": "float", "enable_search": True, "create_embeddings": True},
                {"column_name": "quantity", "data_type": "int", "enable_search": True, "create_embeddings": True},
            ],
            "collection_name": "groceries"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    schema_response = response.json()
    assert schema_response["message"] == "Schema saved!"
    assert schema_response["error_code"] == 0

    dummy_data_one = {
        "id": 1,
        "item": "Juice",
        "price": 2.80,
        "quantity": 56
    }
    dummy_doc = CognitionData(
        data=dummy_data_one,
        content_type="json",
        collection="groceries",
        user="himanshu.gupta@digite.com",
        bot=pytest.bot,
        timestamp=utc_now()
    )
    dummy_doc.save()
    dummy_data_two = {
        "id": 2,
        "item": "Milk",
        "price": 2.80,
        "quantity": 12
    }
    dummy_doc = CognitionData(
        data=dummy_data_two,
        content_type="json",
        collection="groceries",
        user="himanshu.gupta@digite.com",
        bot=pytest.bot,
        timestamp=utc_now()
    )
    dummy_doc.save()

    cognition_data = CognitionData.objects(bot=pytest.bot, collection="groceries")
    assert cognition_data.count() == 2

    sync_data = [
        {"id": 1, "price": 80.50},
        {"id": 2, "price": 27.00}
    ]

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/sync?primary_key_col=id&collection_name=groceries&sync_type=item_toggle",
        json=sync_data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual= response.json()
    assert actual["success"]
    assert actual["message"] == "Processing completed successfully"
    assert actual["error_code"] == 0

    cognition_data = CognitionData.objects(bot=pytest.bot, collection="groceries")
    assert cognition_data.count() == 2

    expected_data = [
        {"id": 1, "item": "Juice", "price": 80.50, "quantity": 56},
        {"id": 2, "item": "Milk", "price": 27.00, "quantity": 12}
    ]

    for index, doc in enumerate(cognition_data):
        doc_data = doc.to_mongo().to_dict()["data"]
        assert doc_data == expected_data[index]

    call_kwargs = mock_embedding.call_args[1]

    assert call_kwargs["request_method"] == "POST"
    assert call_kwargs["timeout"] == 30

    assert call_kwargs["http_url"] == (
        f"http://localhost/{pytest.bot}/aembedding/openai"
    )

    request_body = call_kwargs["request_body"]

    assert request_body["user"] == "integration@demo.ai"

    assert request_body["kwargs"]["api_key"] == "common_openai_key"
    assert request_body["kwargs"]["invocation"] == "knowledge_vault_sync"

    CognitionData.objects(bot=pytest.bot, collection="groceries").delete()
    CognitionSchema.objects(bot=pytest.bot, collection_name="groceries").delete()
    LLMSecret.objects.delete()

@responses.activate
def test_knowledge_vault_sync_sync_type_does_not_exist():    
    LLMSecret.objects.delete()
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.content_importer_limit_per_day = 10
    bot_settings.cognition_collections_limit = 10
    bot_settings.llm_settings['enable_faq'] = True
    bot_settings.save()


    secrets = [
        {
            "llm_type": "openai",
            "api_key": "common_openai_key",
            "models": ["common_openai_model1", "common_openai_model2"],
            "user": "123",
            "timestamp": utc_now()
        }
    ]
    for secret in secrets:
        LLMSecret(**secret).save()

    sync_data = [
        {"id": 1, "item": "Juice", "price": 2.50, "quantity": 10},
        {"id": 2, "item": "Apples", "price": 1.20, "quantity": 20}
    ]

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/sync?primary_key_col=id&collection_name=groceries&sync_type=non_existent_sync_type",
        json=sync_data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Sync type does not exist"
    assert actual["error_code"] == 422

    cognition_data = CognitionData.objects(bot=pytest.bot, collection="nonexistent_collection")
    assert cognition_data.count() == 0
    LLMSecret.objects.delete()

@responses.activate
def test_knowledge_vault_sync_missing_collection():
    LLMSecret.objects.delete()
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.content_importer_limit_per_day = 10
    bot_settings.cognition_collections_limit = 10
    bot_settings.llm_settings['enable_faq'] = True
    bot_settings.save()

    secrets = [
        {
            "llm_type": "openai",
            "api_key": "common_openai_key",
            "models": ["common_openai_model1", "common_openai_model2"],
            "user": "123",
            "timestamp": utc_now()
        }
    ]
    for secret in secrets:
        LLMSecret(**secret).save()

    sync_data = [
        {"id": 1, "item": "Juice", "price": 2.50, "quantity": 10},
        {"id": 2, "item": "Apples", "price": 1.20, "quantity": 20}
    ]

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/sync?primary_key_col=id&collection_name=nonexistent_collection&sync_type=push_menu",
        json=sync_data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Collection 'nonexistent_collection' does not exist."
    assert actual["error_code"] == 422

    cognition_data = CognitionData.objects(bot=pytest.bot, collection="nonexistent_collection")
    assert cognition_data.count() == 0

    LLMSecret.objects.delete()

@responses.activate
def test_knowledge_vault_sync_missing_primary_key():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.content_importer_limit_per_day = 10
    bot_settings.cognition_collections_limit = 10
    bot_settings.llm_settings['enable_faq'] = True
    bot_settings.save()

    LLMSecret.objects.delete()
    secrets = [
        {
            "llm_type": "openai",
            "api_key": "common_openai_key",
            "models": ["common_openai_model1", "common_openai_model2"],
            "user": "123",
            "timestamp": utc_now()
        }
    ]
    for secret in secrets:
        LLMSecret(**secret).save()

    schema_response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "price", "data_type": "float", "enable_search": True, "create_embeddings": True},
                {"column_name": "quantity", "data_type": "int", "enable_search": True, "create_embeddings": True},
            ],
            "collection_name": "groceries"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    assert schema_response.status_code == 200
    assert schema_response.json()["message"] == "Schema saved!"
    assert schema_response.json()["error_code"] == 0

    sync_data = [
        {"item": "Juice", "price": 2.50, "quantity": 10},
        {"item": "Apples", "price": 1.20, "quantity": 20}
    ]

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/sync?primary_key_col=id&collection_name=groceries&sync_type=push_menu",
        json=sync_data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Primary key 'id' must exist in each row."
    assert actual["error_code"] == 422

    cognition_data = CognitionData.objects(bot=pytest.bot, collection="groceries")
    assert cognition_data.count() == 0

    CognitionSchema.objects(bot=pytest.bot, collection_name="groceries").delete()
    LLMSecret.objects.delete()


@responses.activate
def test_knowledge_vault_sync_column_length_mismatch():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.content_importer_limit_per_day = 10
    bot_settings.cognition_collections_limit = 10
    bot_settings.llm_settings['enable_faq'] = True
    bot_settings.save()

    LLMSecret.objects.delete()
    secrets = [
        {
            "llm_type": "openai",
            "api_key": "common_openai_key",
            "models": ["common_openai_model1", "common_openai_model2"],
            "user": "123",
            "timestamp": utc_now()
        }
    ]
    for secret in secrets:
        LLMSecret(**secret).save()

    schema_response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "price", "data_type": "float", "enable_search": True, "create_embeddings": True},
                {"column_name": "quantity", "data_type": "int", "enable_search": True, "create_embeddings": True},
            ],
            "collection_name": "groceries"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    assert schema_response.status_code == 200
    assert schema_response.json()["message"] == "Schema saved!"
    assert schema_response.json()["error_code"] == 0

    sync_data = [
        {"id": 1, "item": "Juice", "quantity": 10},
        {"id": 2, "item": "Apples", "quantity": 20}
    ]

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/sync?primary_key_col=id&collection_name=groceries&sync_type=push_menu",
        json=sync_data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Validation failed"
    assert actual["error_code"] == 400
    assert actual["data"] == {'1': [{'status': 'Column length mismatch', 'expected_columns': ['id', 'item', 'price', 'quantity'], 'actual_columns': ['id', 'item', 'quantity']}], '2': [{'status': 'Column length mismatch', 'expected_columns': ['id', 'item', 'price', 'quantity'], 'actual_columns': ['id', 'item', 'quantity']}]}
    cognition_data = CognitionData.objects(bot=pytest.bot, collection="groceries")
    assert cognition_data.count() == 0

    CognitionSchema.objects(bot=pytest.bot, collection_name="groceries").delete()
    LLMSecret.objects.delete()


@responses.activate
def test_knowledge_vault_sync_invalid_columns():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.content_importer_limit_per_day = 10
    bot_settings.cognition_collections_limit = 10
    bot_settings.llm_settings['enable_faq'] = True
    bot_settings.save()

    LLMSecret.objects.delete()
    secrets = [
        {
            "llm_type": "openai",
            "api_key": "common_openai_key",
            "models": ["common_openai_model1", "common_openai_model2"],
            "user": "123",
            "timestamp": utc_now()
        }
    ]
    for secret in secrets:
        LLMSecret(**secret).save()

    schema_response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "price", "data_type": "float", "enable_search": True, "create_embeddings": True},
                {"column_name": "quantity", "data_type": "int", "enable_search": True, "create_embeddings": True},
            ],
            "collection_name": "groceries"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    assert schema_response.status_code == 200
    assert schema_response.json()["message"] == "Schema saved!"
    assert schema_response.json()["error_code"] == 0

    dummy_data = {
        "id": 2,
        "item": "Milk",
        "price": 2.80,
        "quantity": 12
    }
    dummy_doc = CognitionData(
        data=dummy_data,
        content_type="json",
        collection="groceries",
        user="himanshu.gupta@digite.com",
        bot=pytest.bot,
        timestamp=utc_now()
    )
    dummy_doc.save()

    sync_data = [
        {"id": 2, "discount": 0.75}
    ]

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/sync?primary_key_col=id&collection_name=groceries&sync_type=item_toggle",
        json=sync_data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Validation failed"
    assert actual["error_code"] == 400
    assert actual["data"] == {'2': [{'status': 'Invalid columns in input data', 'expected_columns': ["id + any from ['item', 'price', 'quantity']"], 'actual_columns': ['id', 'discount']}]}

    cognition_data = CognitionData.objects(bot=pytest.bot, collection="groceries")
    assert cognition_data.count() == 1
    expected_data = [
        {"id": 2, "item": "Milk", "price": 2.80, "quantity": 12}
    ]
    for index, doc in enumerate(cognition_data):
        doc_data = doc.to_mongo().to_dict()["data"]
        assert doc_data == expected_data[index]

    CognitionSchema.objects(bot=pytest.bot, collection_name="groceries").delete()
    CognitionData.objects(bot=pytest.bot, collection="groceries").delete()
    LLMSecret.objects.delete()

@responses.activate
def test_knowledge_vault_sync_document_non_existence():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.content_importer_limit_per_day = 10
    bot_settings.cognition_collections_limit = 10
    bot_settings.llm_settings['enable_faq'] = True
    bot_settings.save()

    LLMSecret.objects.delete()
    secrets = [
        {
            "llm_type": "openai",
            "api_key": "common_openai_key",
            "models": ["common_openai_model1", "common_openai_model2"],
            "user": "123",
            "timestamp": utc_now()
        }
    ]
    for secret in secrets:
        LLMSecret(**secret).save()

    schema_response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "price", "data_type": "float", "enable_search": True, "create_embeddings": True},
                {"column_name": "quantity", "data_type": "int", "enable_search": True, "create_embeddings": True},
            ],
            "collection_name": "groceries"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    assert schema_response.status_code == 200
    assert schema_response.json()["message"] == "Schema saved!"
    assert schema_response.json()["error_code"] == 0

    dummy_data = {
        "id": 1,
        "item": "Juice",
        "price": 2.80,
        "quantity": 5
    }
    dummy_doc = CognitionData(
        data=dummy_data,
        content_type="json",
        collection="groceries",
        user="himanshu.gupta@digite.com",
        bot=pytest.bot,
        timestamp=utc_now()
    )
    dummy_doc.save()

    sync_data = [
        {"id": 2, "price": 27.0}
    ]

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/sync?primary_key_col=id&collection_name=groceries&sync_type=item_toggle",
        json=sync_data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Validation failed"
    assert actual["error_code"] == 400
    assert actual["data"] == {'2': [{'status': 'Document does not exist', 'primary_key': 2, 'message': "No document found for 'id': 2"}]}
    cognition_data = CognitionData.objects(bot=pytest.bot, collection="groceries")
    assert cognition_data.count() == 1

    expected_data = [
        {
            "id": 1,
            "item": "Juice",
            "price": 2.80,
            "quantity": 5
        }
    ]

    for index, doc in enumerate(cognition_data):
        doc_data = doc.to_mongo().to_dict()["data"]
        assert doc_data == expected_data[index]

    CognitionSchema.objects(bot=pytest.bot, collection_name="groceries").delete()
    CognitionData.objects(bot=pytest.bot, collection="groceries").delete()
    LLMSecret.objects.delete()

@responses.activate
def test_fetch_metadata_for_logs_positive():
    """
    Positive test: Verify metadata for logs is fetched successfully.
    """
    response = client.get(
        f"/api/bot/{pytest.bot}/logs/metadata",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    assert response.status_code == 200
    json_data = response.json()
    assert "data" in json_data
    assert "metadata" in json_data["data"]
    assert isinstance(json_data["data"]["metadata"], dict)
    assert len(json_data["data"]["metadata"]) > 0

@responses.activate
def test_upload_doc_content():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.content_importer_limit_per_day = 10
    bot_settings.cognition_collections_limit = 10
    bot_settings.llm_settings['enable_faq'] = True
    bot_settings.save()

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "order_id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "order_priority", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "sales", "data_type": "float", "enable_search": True, "create_embeddings": True},
                {"column_name": "profit", "data_type": "float", "enable_search": True, "create_embeddings": True},
            ],
            "collection_name": "test_doc_content_upload"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    pytest.schema_id = actual["data"]["_id"]
    assert actual["message"] == "Schema saved!"
    assert actual["data"]["_id"]
    assert actual["error_code"] == 0

    dummy_data = {
        "order_id": "9999",
        "order_priority": "Low",
        "sales": "0.00",
        "profit": "0.00"
    }
    dummy_doc = CognitionData(
        data=dummy_data,
        content_type="json",
        collection="test_doc_content_upload",
        user="himanshu.gupta@digite.com",
        bot=pytest.bot,
        timestamp=utc_now()
    )
    dummy_doc.save()

    cognition_data = CognitionData.objects(bot=pytest.bot, collection="test_doc_content_upload")
    assert cognition_data.count() == 1

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.content_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )
    file = {
        "doc_content": ("Salesstore.csv", open("tests/testing_data/doc_content_upload/Salesstore.csv", "rb"))
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/data/content/upload?table_name=test_doc_content_upload&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=file,
    )

    actual = response.json()
    assert actual["success"]
    assert actual["message"] == "Document content upload in progress! Check logs."
    assert actual["error_code"] == 0

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.content_importer, table_name="test_doc_content_upload", overwrite=True
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/content/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/logs/content?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    print(actual)
    assert actual["success"]
    assert actual["error_code"] == 0
    logs = actual['data']['logs']
    assert len(logs) == 1
    assert logs[0]['file_received'] == 'Salesstore.csv'
    assert logs[0]['status'] == STATUSES.SUCCESS.value
    assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value
    assert logs[0]['is_data_uploaded']
    assert logs[0]['start_timestamp'] is not None
    assert logs[0]['end_timestamp'] is not None
    assert logs[0]['validation_errors'] == {}
    assert logs[0]['exception'] == ''

    from_date = date.today()
    to_date = from_date + timedelta(days=1)

    search_response = client.get(
        f"/api/bot/{pytest.bot}/logs/content/search"
        f"?from_date={from_date}&to_date={to_date}&status=Success",
        headers={"Authorization": f"{pytest.token_type} {pytest.access_token}"},
    )
    response_json = search_response.json()
    assert response_json["success"] is True
    assert response_json["error_code"] == 0

    data = response_json["data"]
    assert "logs" in data
    assert isinstance(data["logs"], list)

    cognition_data= CognitionData.objects(bot=pytest.bot, collection="test_doc_content_upload")

    assert cognition_data.count() == 20

    last_row = cognition_data.order_by('-_id').first()
    assert last_row["data"] == {
        'order_id': 67,
        'order_priority': 'Low',
        'sales': 12.34,
        'profit': 54.98
    }
    CognitionData.objects(bot=pytest.bot, collection="test_doc_content_upload").delete()

@responses.activate
def test_upload_doc_content_append():

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "order_id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "order_priority", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "sales", "data_type": "float", "enable_search": True, "create_embeddings": True},
                {"column_name": "profit", "data_type": "float", "enable_search": True, "create_embeddings": True},
            ],
            "collection_name": "test_doc_content_upload_append"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    pytest.schema_id = actual["data"]["_id"]
    assert actual["message"] == "Schema saved!"
    assert actual["data"]["_id"]
    assert actual["error_code"] == 0

    dummy_data = {
        "order_id": "9999",
        "order_priority": "Low",
        "sales": "0.00",
        "profit": "0.00"
    }
    dummy_doc = CognitionData(
        data=dummy_data,
        content_type="json",
        collection="test_doc_content_upload_append",
        user="himanshu.gupta@digite.com",
        bot=pytest.bot,
        timestamp=utc_now()
    )
    dummy_doc.save()

    cognition_data = CognitionData.objects(bot=pytest.bot, collection="test_doc_content_upload_append")
    assert cognition_data.count() == 1

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.content_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )
    file = {
        "doc_content": ("Salesstore.csv", open("tests/testing_data/doc_content_upload/Salesstore.csv", "rb"))
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/data/content/upload?table_name=test_doc_content_upload_append&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=file,
    )

    actual = response.json()
    assert actual["success"] == True
    assert actual["message"] == "Document content upload in progress! Check logs."
    assert actual["error_code"] == 0

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.content_importer, table_name="test_doc_content_upload_append"
    )
    response = client.get(
        f"/api/bot/{pytest.bot}/content/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["success"] == True
    assert actual["error_code"] == 0
    logs = actual['data']['logs']
    assert len(logs) == 2
    assert logs[0]['file_received'] == 'Salesstore.csv'
    assert logs[0]['status'] == STATUSES.SUCCESS.value
    assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value
    assert logs[0]['is_data_uploaded']
    assert logs[0]['start_timestamp'] is not None
    assert logs[0]['end_timestamp'] is not None
    assert logs[0]['validation_errors'] == {}
    assert logs[0]['exception'] == ''
    cognition_data = CognitionData.objects(bot=pytest.bot, collection="test_doc_content_upload_append")
    assert cognition_data.count() == 21

    first_row = cognition_data.first()
    assert first_row["data"] == {
        "order_id": "9999",
        "order_priority": "Low",
        "sales": "0.00",
        "profit": "0.00"
    }
    last_row = cognition_data.order_by('-_id').first()
    assert last_row["data"] == {
        'order_id': 67,
        'order_priority': "Low",
        'sales': 12.34,
        'profit': 54.98
    }
    CognitionData.objects(bot=pytest.bot, collection="test_doc_content_upload_append").delete()


@responses.activate
def test_upload_doc_content_basic_validation_failure():

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "order_id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "order_priority", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "sales", "data_type": "float", "enable_search": True, "create_embeddings": True},
                {"column_name": "profit", "data_type": "float", "enable_search": True, "create_embeddings": True},
            ],
            "collection_name": "test_doc_content_upload_basic_validation_failure"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    pytest.schema_id = actual["data"]["_id"]
    assert actual["message"] == "Schema saved!"
    assert actual["data"]["_id"]
    assert actual["error_code"] == 0

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.content_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )
    file = {
        "doc_content": ("Salesstore.csv", open("tests/testing_data/doc_content_upload/Salesstore_data_with_basic_errors.csv", "rb"))
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/data/content/upload?table_name=test_doc_content_upload_basic_validation_failure&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=file,
    )

    actual = response.json()
    assert actual["success"]
    assert actual["message"] == "Document content upload in progress! Check logs."
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/content/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    logs = actual['data']['logs']
    assert len(logs) == 3
    assert 'validation_errors' in logs[0]
    validation_errors = logs[0]["validation_errors"]
    expected_errors = {
        "Header mismatch": "Expected headers ['order_id', 'order_priority', 'sales', 'profit'] but found ['order_id', 'order_priority', 'revenue', 'sales'].",
        "Missing columns": "{'profit'}.",
        "Extra columns": "{'revenue'}."
    }
    assert validation_errors == expected_errors
    assert logs[0]["status"] == STATUSES.FAIL.value
    assert logs[0]["event_status"] == EVENT_STATUS.COMPLETED.value

    CognitionData.objects(bot=pytest.bot, collection="test_doc_content_upload_basic_validation_failure").delete()

@responses.activate
def test_download_error_csv_error_report_not_found():

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "order_id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "order_priority", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "sales", "data_type": "float", "enable_search": True, "create_embeddings": True},
                {"column_name": "profit", "data_type": "float", "enable_search": True, "create_embeddings": True},
            ],
            "collection_name": "test_download_error_csv_error_report_not_found"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    pytest.schema_id = actual["data"]["_id"]
    assert actual["message"] == "Schema saved!"
    assert actual["data"]["_id"]
    assert actual["error_code"] == 0

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.content_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )
    file = {
        "doc_content": ("Salesstore.csv", open("tests/testing_data/doc_content_upload/Salesstore.csv", "rb"))
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/data/content/upload?table_name=test_download_error_csv_error_report_not_found&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=file,
    )

    actual = response.json()
    assert actual["success"]
    assert actual["message"] == "Document content upload in progress! Check logs."
    assert actual["error_code"] == 0

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.content_importer, table_name="test_download_error_csv_error_report_not_found", overwrite=True
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/content/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0

    event_id = ContentImporterLogProcessor.get_event_id_for_latest_event(pytest.bot)

    response = client.get(
        f"/api/bot/{pytest.bot}/data/content/error-report/{event_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"] is False
    assert actual["error_code"] == 404
    assert actual["message"] == "Error Report not found"
    CognitionData.objects(bot=pytest.bot, collection="test_download_error_csv_error_report_not_found").delete()

@responses.activate
def test_upload_doc_content_datatype_validation_failure():

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "order_id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "order_priority", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "sales", "data_type": "float", "enable_search": True, "create_embeddings": True},
                {"column_name": "profit", "data_type": "float", "enable_search": True, "create_embeddings": True},
            ],
            "collection_name": "test_doc_content_upload_datatype_validation_failure"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    pytest.schema_id = actual["data"]["_id"]
    assert actual["message"] == "Schema saved!"
    assert actual["data"]["_id"]
    assert actual["error_code"] == 0

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.content_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )
    file = {
        "doc_content": ("Salesstore.csv", open("tests/testing_data/doc_content_upload/Salesstore_data_with_datatype_errors.csv", "rb"))
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/data/content/upload?table_name=test_doc_content_upload_datatype_validation_failure&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=file,
    )

    actual = response.json()
    assert actual["success"]
    assert actual["message"] == "Document content upload in progress! Check logs."
    assert actual["error_code"] == 0


    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.content_importer, table_name="test_doc_content_upload_datatype_validation_failure"
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/content/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    logs = actual['data']['logs']
    assert len(logs) == 5
    assert 'validation_errors' in logs[0]
    validation_errors = logs[0]["validation_errors"]
    assert any(e['column_name'] == 'order_id' and e['status'] == 'Invalid DataType' for e in validation_errors['Row 4'])
    assert any(e['column_name'] == 'sales' and e['status'] == 'Required Field is Empty' for e in validation_errors['Row 4'])
    assert any(
        e['column_name'] == 'profit' and e['status'] == 'Required Field is Empty' for e in validation_errors['Row 6'])
    assert logs[0]["status"] == STATUSES.PARTIAL_SUCCESS.value
    assert logs[0]["event_status"] == EVENT_STATUS.COMPLETED.value

    cognition_data = list(CognitionData.objects(bot=pytest.bot, collection="test_doc_content_upload_datatype_validation_failure"))
    assert len(cognition_data) == 18

    third_last_row = cognition_data[-3]
    assert third_last_row["data"] == {
        "order_id": 33,
        "order_priority": "Low",
        "sales": 905.94,
        "profit": -4.19
    }

    fourth_last_row = cognition_data[-4]
    assert fourth_last_row["data"] == {
        "order_id": 657,
        "order_priority": "Not Specified",
        "sales": 237.28,
        "profit": -2088.68
    }

    CognitionData.objects(bot=pytest.bot, collection="test_doc_content_upload_datatype_validation_failure").delete()

@responses.activate
def test_download_error_csv():

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "order_id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "order_priority", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "sales", "data_type": "float", "enable_search": True, "create_embeddings": True},
                {"column_name": "profit", "data_type": "float", "enable_search": True, "create_embeddings": True},
            ],
            "collection_name": "test_download_error_csv"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    pytest.schema_id = actual["data"]["_id"]
    assert actual["message"] == "Schema saved!"
    assert actual["data"]["_id"]
    assert actual["error_code"] == 0

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.content_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )
    file = {
        "doc_content": ("Salesstore.csv", open("tests/testing_data/doc_content_upload/Salesstore_data_with_datatype_errors.csv", "rb"))
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/data/content/upload?table_name=test_download_error_csv&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=file,
    )

    actual = response.json()
    assert actual["success"] == True
    assert actual["message"] == "Document content upload in progress! Check logs."
    assert actual["error_code"] == 0

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.content_importer, table_name="test_download_error_csv"
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/content/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"] == True
    assert actual["error_code"] == 0

    event_id = ContentImporterLogProcessor.get_event_id_for_latest_event(pytest.bot)

    response = client.get(
        f"/api/bot/{pytest.bot}/data/content/error-report/{event_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    csv_content = response.text
    expected_csv_content = """order_id,order_priority,sales,profit,kairon_error_description
45.09,Not Specified,,-329.49,order_id: Invalid DataType; sales: Required Field is Empty
32,Medium,65.09,,profit: Required Field is Empty"""
    csv_content = csv_content.replace('\r\n', '\n')
    expected_csv_content = expected_csv_content.replace('\r\n', '\n')
    assert csv_content.strip() == expected_csv_content
    CognitionData.objects(bot=pytest.bot, collection="test_download_error_csv").delete()


@responses.activate
def test_upload_doc_content_file_type_validation_failure():
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "order_id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "order_priority", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "sales", "data_type": "float", "enable_search": True, "create_embeddings": True},
                {"column_name": "profit", "data_type": "float", "enable_search": True, "create_embeddings": True},
            ],
            "collection_name": "test_doc_content_file_type_validation_failure"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    pytest.schema_id = actual["data"]["_id"]
    assert actual["message"] == "Schema saved!"
    assert actual["data"]["_id"]
    assert actual["error_code"] == 0

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.content_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )
    file = {
        "doc_content": (
        "test_wrong_file_type.pdf", open("tests/testing_data/doc_content_upload/test_wrong_file_type.pdf", "rb"))
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/data/content/upload?table_name=test_doc_content_file_type_validation_failure&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=file,
    )

    actual = response.json()
    assert actual["success"] == True
    assert actual["message"] == "Document content upload in progress! Check logs."
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/content/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["success"] == True
    assert actual["error_code"] == 0
    logs = actual['data']['logs']
    assert len(logs) == 7
    assert 'validation_errors' in logs[0]
    validation_errors = logs[0]["validation_errors"]
    expected_errors = {
        'File type error': "Invalid file type: application/pdf. Please upload a CSV file."
    }
    assert validation_errors == expected_errors
    assert logs[0]["status"] == STATUSES.FAIL.value
    assert logs[0]["event_status"] == EVENT_STATUS.COMPLETED.value
    CognitionData.objects(bot=pytest.bot, collection="test_doc_content_file_type_validation_failure").delete()

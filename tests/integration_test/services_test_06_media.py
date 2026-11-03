from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training



@responses.activate
@patch("kairon.shared.chat.processor.ChatDataProcessor.validate_media_file_type")
@patch("kairon.shared.chat.processor.ChatDataProcessor.save_media_file_path")
@patch("kairon.shared.chat.processor.ChatDataProcessor.upload_media_to_bsp")
def test_upload_media_success(
        mock_upload_media,
        mock_save_validate,
        mock_validate,
):
    mock_validate.return_value = None
    mock_save_validate.return_value = (None, "/tmp/file.txt")
    mock_upload_media.return_value = {"media_id": "12345"}

    file_content = io.BytesIO(b"dummy file content")

    response = client.post(
        f"/api/bot/{pytest.bot}/channels/whatsapp/upload/media_upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files={"file_content": ("test.txt", file_content, "text/plain")},
    )

    body = response.json()
    print(body)
    assert body["message"] == "File uploaded successfully!"
    assert body["data"]["media_id"] == "12345"


@responses.activate
@patch("kairon.shared.chat.processor.ChatDataProcessor.save_media_file_path")
@patch("kairon.shared.chat.processor.ChatDataProcessor.upload_media_to_bsp")
def test_upload_media_invalid_file_type(
        mock_upload_media,
        mock_save_validate,
):
    mock_save_validate.return_value = (None, "/tmp/file.py")
    mock_upload_media.return_value = {"media_id": "12345"}

    file_content = io.BytesIO(b"dummy file content")

    response = client.post(
        f"/api/bot/{pytest.bot}/channels/whatsapp/upload/media_upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files={"file_content": ("test.py", file_content, "script")},
    )

    body = response.json()
    print(body)
    assert body['error_code'] == 422
    assert ("Invalid file type: script. Allowed types are: audio/aac, audio/amr, audio/mpeg,"
            " audio/mp4, audio/ogg, text/plain, application/vnd.ms-excel, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
            " application/msword, application/vnd.openxmlformats-officedocument.wordprocessingml.document, application/vnd.ms-powerpoint,"
            " application/vnd.openxmlformats-officedocument.presentationml.presentation, application/pdf,"
            " image/jpeg, image/png, image/webp, video/3gpp, video/mp4.") in body["message"]


@responses.activate
@patch("kairon.shared.chat.processor.ChatDataProcessor.save_media_file_path")
@patch("kairon.shared.chat.processor.ChatDataProcessor.upload_media_to_bsp")
def test_upload_media_with_filename_missing(
        mock_upload_media,
        mock_save_validate,
):
    mock_save_validate.return_value = (None, "/tmp/file.py")
    mock_upload_media.return_value = {"media_id": "12345"}

    file_content = io.BytesIO(b"dummy file content")

    response = client.post(
        f"/api/bot/{pytest.bot}/channels/whatsapp/upload/media_upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files={"file_content": ("", file_content, "script")},
    )

    body = response.json()
    print(body)
    assert body['error_code'] == 422
    assert ("Expected UploadFile, received: <class 'str'>") in body['message'][0]["msg"]


@responses.activate
def test_upload_media_no_file():
    response = (client.post
                (f"/api/bot/{pytest.bot}/channels/whatsapp/upload/media_upload",
                 headers={"Authorization": pytest.token_type + " " + pytest.access_token}))

    body = response.json()
    print(body)
    assert body['error_code'] == 422
    assert 'field required' in body["message"][0]['msg']


@responses.activate
@patch("kairon.shared.chat.processor.ChatDataProcessor.validate_media_file_type")
def test_upload_media_file_too_large(mock_validate):
    mock_validate.side_effect = AppException("File size exceeds 100MB")

    file_content = io.BytesIO(b"x" * (101 * 1024 * 1024))

    response = client.post(
        f"/api/bot/{pytest.bot}/channels/whatsapp/upload/media_upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files={"file_content": ("large.pdf", file_content, "application/pdf")},
    )

    body = response.json()
    assert body['error_code'] == 422
    assert "File size exceeds 100MB" in body["message"]



@responses.activate
@patch("kairon.shared.chat.processor.Channels.objects")
def test_upload_media_channel_missing(mock_channels):
    mock_channels.return_value.exclude.return_value.get.side_effect = AppException("No channel found")

    file_content = io.BytesIO(b"dummy content")
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/whatsapp/upload/media_upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files={"file_content": ("file.pdf", file_content, "application/pdf")},
    )
    body = response.json()
    assert body["success"] is False
    assert "no channel" in body["message"].lower()
    assert body["error_code"] == 422

@responses.activate
@patch("kairon.shared.chat.processor.Channels.objects")
def test_upload_media_channel_other_exception(mock_channels):
    mock_channels.return_value.exclude.return_value.get.side_effect = Exception("some random error")

    file_content = io.BytesIO(b"dummy content")
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/whatsapp/upload/media_upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files={"file_content": ("file.pdf", file_content, "application/pdf")},
    )

    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == 422
    assert "some random error" in body["message"].lower()


def test_validate_media_file_type_file_already_exists_within_30_days():
    from kairon.shared.data.data_objects import UserMediaData
    from kairon.shared.models import UserMediaUploadStatus

    UserMediaData(
        media_id="0196c9efbf547b81a66ba2af7b72d5ba",
        filename="file.png",
        extension=".png",
        upload_status=UserMediaUploadStatus.completed.value,
        upload_type="broadcast",
        filesize=1024,
        sender_id="user@test.com",
        bot=pytest.bot,
        timestamp=utc_now() - timedelta(days=5),
        media_url="",
        output_filename="",
        external_upload_info={"bsp": "360dialog"}
    ).save()
    file_content = io.BytesIO(b"dummy content")

    response = client.post(
        f"/api/bot/{pytest.bot}/channels/whatsapp/upload/media_upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files={"file_content": ("file.png", file_content, "image/png")},
    )
    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == 422
    assert body["message"] == "File 'file.png' already exists. Please upload a different file."


@responses.activate
@patch("kairon.shared.chat.processor.utc_now")
@patch("kairon.shared.chat.user_media.UserMediaData.objects")
def test_upload_media_file_already_exists(mock_user_media, mock_utc_now):
    fixed_now = datetime(2026, 1, 1, 12, 0, 0)
    mock_utc_now.return_value = fixed_now

    mock_db_obj = MagicMock()
    mock_db_obj.timestamp = fixed_now - timedelta(days=10)

    mock_queryset = MagicMock()
    mock_queryset.order_by.return_value.first.return_value = mock_db_obj
    mock_user_media.return_value = mock_queryset

    file_content = io.BytesIO(b"dummy content")

    response = client.post(
        f"/api/bot/{pytest.bot}/channels/whatsapp/upload/media_upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files={"file_content": ("file.png", file_content, "image/png")},
    )

    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == 422
    assert "file 'file.png' already exists" in body["message"].lower()
    mock_user_media.assert_called_once_with(
        bot=pytest.bot,
        filename="file.png"
    )
    mock_queryset.order_by.assert_called_once_with("-timestamp")

@responses.activate
def test_get_media_ids():
    bot_settings = BotSettings.objects(bot=pytest.bot).first()
    bot_settings.whatsapp = "360dialog"
    bot_settings.save()
    if bot_settings:
        bot_settings_dict = bot_settings.to_mongo().to_dict()
        print(bot_settings_dict)

    channel = Channels.objects(bot=pytest.bot).first()
    if channel:
        channel = channel.to_mongo().to_dict()
        print(channel)
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

    UserMediaData(
        media_id=media_id,
        filename="Upload_Download Data.pdf",
        extension=".pdf",
        upload_status=UserMediaUploadStatus.completed.value,
        upload_type="broadcast",
        filesize=410484,
        sender_id="himanshu.gupta_@digite.com",
        bot=pytest.bot,
        timestamp=utc_now(),
        media_url="",
        output_filename="",
        external_upload_info={"bsp": "360dialog"}
    ).save()

    response = client.get(
        f"/api/bot/{pytest.bot}/data/fetch_media_ids",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    body = response.json()
    UserMediaData.objects().delete()
    Channels.objects().delete()
    assert body["data"][0]['media_id'] == media_id

@responses.activate
def test_get_media_ids_within_30_days():
    bot_settings = BotSettings.objects(bot=pytest.bot).first()
    if bot_settings:
        bot_settings.whatsapp = "360dialog"
        bot_settings.save()
    channel = Channels.objects(bot=pytest.bot).first()
    if channel:
        channel = channel.to_mongo().to_dict()
        print(channel)
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

    UserMediaData(
        media_id=media_id,
        filename="new_file.pdf",
        extension=".pdf",
        upload_status=UserMediaUploadStatus.completed.value,
        upload_type="broadcast",
        filesize=410484,
        sender_id="himanshu.gupta_@digite.com",
        bot=pytest.bot,
        timestamp=utc_now()- timedelta(days=40),
        media_url="",
        output_filename="",
        external_upload_info={"bsp": "360dialog"}
    ).save()
    media_id2 = "0196c9efbf547b81a66ba2af7b72d5bb"
    UserMediaData(
        media_id=media_id2,
        filename="old_file.pdf",
        extension=".pdf",
        upload_status=UserMediaUploadStatus.completed.value,
        upload_type="broadcast",
        filesize=410484,
        sender_id="himanshu.gupta_@digite.com",
        bot=pytest.bot,
        timestamp=utc_now(),
        media_url="",
        output_filename="",
        external_upload_info={"bsp": "360dialog"}
    ).save()

    response = client.get(
        f"/api/bot/{pytest.bot}/data/fetch_media_ids",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    body = response.json()
    UserMediaData.objects().delete()
    Channels.objects().delete()
    assert len(body["data"]) == 1, "Expected only one media record within 30 days"
    assert body["data"][0]['media_id'] == media_id2
    assert all(item['media_id'] != media_id for item in body["data"]), "Old media should be filtered out"

@responses.activate
def test_delete_media_ids():
    bot = pytest.bot
    media_id = "715690454858053"
    channel_name = "whatsapp"

    with patch.dict(
        "kairon.shared.utils.Utility.environment",
        {"storage": {"whatsapp_media": {"bucket": "mock-bucket"}}},
        clear=False
    ), patch(
        "kairon.shared.cloud.utils.CloudUtility.delete_file"
    ) as mock_delete_file:
        mock_delete_file.return_value = None

        bot_settings = BotSettings.objects(bot=bot).first()
        if not bot_settings:
            bot_settings = BotSettings(bot=bot)
        bot_settings.whatsapp = "360dialog"
        bot_settings.save()

        Channels(
            bot=bot,
            connector_type=channel_name,
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

        UserMediaData(
            media_id=media_id,
            filename="Upload_Download Data.pdf",
            extension=".pdf",
            upload_status=UserMediaUploadStatus.completed.value,
            upload_type="broadcast",
            filesize=410484,
            sender_id="himanshu.gupta_@digite.com",
            bot=bot,
            timestamp=utc_now(),
            media_url="",
            output_filename="mock_file.pdf",
            external_upload_info={"bsp": "360dialog"}
        ).save()

        responses.add(
            responses.DELETE,
            f"https://waba-v2.360dialog.io/{media_id}",
            json={"message": "Deleted Successfully"},
            status=200
        )

        response = client.delete(
            f"/api/bot/{bot}/data/{channel_name}/media/{media_id}",
            headers={"Authorization": pytest.token_type + " " + pytest.access_token}
        )

        body = response.json()
        UserMediaData.objects(bot=bot).delete()
        Channels.objects(bot=bot).delete()
        assert body["message"] == "Deleted Successfully"


def test_delete_media_ids_failure():
    bot = pytest.bot
    media_id = "non_existent_media"
    channel_name = "whatsapp"

    UserMediaData.objects(bot=bot).delete()
    Channels.objects(bot=bot).delete()

    response = client.delete(
        f"/api/bot/{bot}/data/{channel_name}/media/{media_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    body = response.json()

    assert body["success"] is False
    assert body["message"] == "Media deletion failed: No channel found for this bot. Please configure the channel first."
    assert body["data"] is None
    assert body["error_code"] == 422

@responses.activate
@patch("kairon.shared.cloud.utils.CloudUtility.get_s3_media_url")
def test_fetch_media_url(mock_get_s3):
    mock_get_s3.return_value = "https://mock-s3-url.com/Upload_Download_Data.pdf"

    bot_settings = BotSettings.objects(bot=pytest.bot).first()
    if bot_settings:
        bot_settings.whatsapp = "360dialog"
        bot_settings.save()

    Channels.objects(bot=pytest.bot).delete()
    channel_obj = Channels(
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
    )
    channel_obj.save()
    channel_name = channel_obj.connector_type

    filename = "Upload_Download Data.pdf"
    UserMediaData.objects().delete()
    UserMediaData(
        media_id="0196c9efbf547b81a66ba2af7b72d5ba",
        filename=filename,
        extension=".pdf",
        upload_status=UserMediaUploadStatus.completed.value,
        upload_type="broadcast",
        filesize=410484,
        sender_id="himanshu.gupta_@digite.com",
        bot=pytest.bot,
        timestamp=utc_now(),
        media_url="",
        output_filename="",
        external_upload_info={"bsp": "360dialog"}
    ).save()

    response = client.get(
        f"/api/bot/{pytest.bot}/data/fetch_media_url/{filename}",
        headers={"Authorization": f"{pytest.token_type} {pytest.access_token}"}
    )
    body = response.json()

    UserMediaData.objects().delete()
    Channels.objects().delete()

    assert body["success"] is True
    assert body["data"]["filename"] == filename
    assert body["data"]["media_url"] == "https://mock-s3-url.com/Upload_Download_Data.pdf"

def create_dummy_channel(bot):
    Channels.objects(bot=bot).delete()
    channel_obj = Channels(
        bot=bot,
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
    )
    channel_obj.save()
    return channel_obj.connector_type


@patch("kairon.shared.cloud.utils.CloudUtility.get_s3_media_url")
def test_fetch_media_url_file_not_exist(mock_get_s3):
    client = TestClient(app)
    channel_name = create_dummy_channel(pytest.bot)

    mock_get_s3.return_value = None

    missing_filename = "file_not_exist.pdf"

    response = client.get(
        f"/api/bot/{pytest.bot}/data/fetch_media_url/{missing_filename}",
        headers={"Authorization": f"{pytest.token_type} {pytest.access_token}"}
    )
    body = response.json()

    Channels.objects().delete()
    UserMediaData.objects().delete()

    assert body["success"] is True
    assert body["data"]["filename"] == missing_filename
    assert body["data"]["media_url"] is None or body["data"]["media_url"] == "None"
    assert "not found" in body["message"].lower() or "media" in body["message"].lower()

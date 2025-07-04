from datetime import datetime

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from io import BytesIO

from kairon.exceptions import AppException
from kairon.shared.chat.user_media import UserMedia
from kairon.shared.data.data_objects import UserMediaData
from kairon.shared.models import UserMediaUploadStatus, UserMediaUploadType
from mongoengine import connect


from kairon import Utility
import os


Utility.load_environment()
Utility.load_system_metadata()

@pytest.fixture
def sample_binary():
    return b"sample data"




@pytest.mark.asyncio
async def test_db_user_media_data():
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    Utility.load_environment()
    Utility.load_system_metadata()
    connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))
    bot = "test-bot"
    media_id = "test-id"
    filename = "sample.mp3"
    sender_id = "user-123"

    UserMedia.create_user_media_data(bot, media_id, filename, sender_id)

    doc = UserMediaData.objects(media_id=media_id).get()
    assert doc.bot == bot
    assert doc.media_id == media_id
    assert doc.filename == filename
    assert doc.extension == ".mp3"
    assert doc.upload_status == UserMediaUploadStatus.processing.value
    assert doc.sender_id == sender_id
    assert isinstance(doc.timestamp, datetime)

    media_id = "upload-done-id"
    UserMedia.create_user_media_data("test-bot", media_id, "file.txt", "user-1")

    media_url = "https://cdn.test.com/file.txt"
    output_filename = "file.txt"
    filesize = 2048

    #done
    UserMedia.mark_user_media_data_upload_done(media_id, media_url, output_filename, filesize)

    doc = UserMediaData.objects(media_id=media_id).get()
    assert doc.upload_status == UserMediaUploadStatus.completed.value
    assert doc.media_url == media_url
    assert doc.output_filename == output_filename
    assert doc.filesize == filesize

    #fail
    media_id = "upload-fail-id"
    UserMedia.create_user_media_data("test-bot", media_id, "badfile.txt", "user-2")

    reason = "Invalid format"
    UserMedia.mark_user_media_data_upload_failed(media_id, reason)

    doc = UserMediaData.objects(media_id=media_id).get()
    assert doc.upload_status == UserMediaUploadStatus.failed.value
    assert doc.additional_log == reason

    UserMediaData.objects().delete()

@pytest.mark.asyncio
@patch("kairon.shared.chat.user_media.UserMedia.create_user_media_data")
@patch("kairon.shared.chat.user_media.UserMedia.save_media_content_task", new_callable=AsyncMock)
@patch("kairon.shared.chat.user_media.uuid7")
async def test_upload_media_contents(uuid_mock, save_task_mock, create_data_mock):
    file_mock = AsyncMock()
    file_mock.filename = "test.txt"
    file_mock.read = AsyncMock(return_value=b"test content")

    uuid_mock.return_value.hex = "fake-id"

    media_ids, _ = await UserMedia.upload_media_contents("bot1", "user@example.com", [file_mock])

    assert media_ids == ["fake-id"]
    create_data_mock.assert_called_once()
    save_task_mock.assert_called_once()

@pytest.mark.asyncio
@patch("kairon.shared.chat.user_media.UserMedia.create_user_media_data")
@patch("kairon.shared.chat.user_media.UserMedia.save_media_content_task", new_callable=AsyncMock)
@patch("kairon.shared.chat.user_media.uuid7")
async def test_upload_multiple_media_contents(uuid_mock, save_task_mock, create_data_mock):
    file1 = AsyncMock()
    file1.filename = "file1.txt"
    file1.read = AsyncMock(return_value=b"content1")

    file2 = AsyncMock()
    file2.filename = "file2.txt"
    file2.read = AsyncMock(return_value=b"content2")

    uuid_mock.side_effect = [MagicMock(hex="id1"), MagicMock(hex="id2")]

    media_ids, _ = await UserMedia.upload_media_contents("bot123", "user@domain.com", [file1, file2])

    assert media_ids == ["id1", "id2"]
    assert create_data_mock.call_count == 2
    assert save_task_mock.call_count == 2



@pytest.mark.asyncio
@patch("kairon.shared.chat.user_media.UserMediaData.objects")
@patch("kairon.shared.chat.user_media.CloudUtility.download_file_to_memory")
@patch("kairon.shared.chat.user_media.Utility")
async def test_get_media_content_buffer_base64(mock_utility, mock_download, mock_objects):
    fake_file = BytesIO(b"file content")
    fake_file.seek(0)

    mock_doc = MagicMock()
    mock_doc.output_filename = "file.txt"
    mock_doc.extension = ".txt"
    mock_doc.to_mongo.return_value.to_dict.return_value = {
        "media_id": "id",
        "bot": "test_bot",
        "sender_id": "I am sender"
    }
    mock_objects.get.return_value = mock_doc
    mock_download.return_value = fake_file
    mock_utility.environment = {"storage": {"user_media": {"bucket": "bucket"}}}

    content, filename, ext = await UserMedia.get_media_content_buffer("media123", base64_encode=True)

    assert isinstance(content, str)
    assert filename == "media_media123.txt"
    assert ext == ".txt"


@pytest.mark.asyncio
@patch("kairon.shared.chat.user_media.UserMediaData.objects")
@patch("kairon.shared.chat.user_media.CloudUtility.download_file_to_memory")
@patch("kairon.shared.chat.user_media.Utility")
async def test_get_media_content_buffer_without_base64(mock_utility, mock_download, mock_objects):
    fake_file = BytesIO(b"plain content")
    fake_file.seek(0)

    mock_doc = MagicMock()
    mock_doc.output_filename = "plain.txt"
    mock_doc.extension = ".txt"
    mock_doc.to_mongo.return_value.to_dict.return_value = {
        "media_id": "plain-id",
        "bot": "bot_plain",
        "sender_id": "I am sender"
    }

    mock_objects.get.return_value = mock_doc
    mock_download.return_value = fake_file
    mock_utility.environment = {"storage": {"user_media": {"bucket": "bucket"}}}

    content, filename, ext = await UserMedia.get_media_content_buffer("plain-id", base64_encode=False)

    assert isinstance(content, BytesIO)
    assert content.getvalue() == b"plain content"
    assert filename == "media_plain-id.txt"
    assert ext == ".txt"


@patch("kairon.shared.chat.user_media.UserMediaData.objects")
def test_mark_user_media_data_upload_done(mock_objects):
    mock_doc = MagicMock()
    mock_objects.return_value.first.return_value = mock_doc

    UserMedia.mark_user_media_data_upload_done("media123", "url", "filename", 123)

    assert mock_doc.media_url == "url"
    assert mock_doc.output_filename == "filename"
    assert mock_doc.filesize == 123
    assert mock_doc.upload_status == UserMediaUploadStatus.completed.value
    mock_doc.save.assert_called_once()


@patch("kairon.shared.chat.user_media.UserMediaData.objects")
def test_mark_user_media_data_upload_failed(mock_objects):
    mock_doc = MagicMock()
    mock_objects.return_value.first.return_value = mock_doc

    UserMedia.mark_user_media_data_upload_failed("media123", "some error")

    assert mock_doc.upload_status == UserMediaUploadStatus.failed.value
    assert mock_doc.additional_log == "some error"
    mock_doc.save.assert_called_once()


@patch("kairon.shared.chat.user_media.CloudUtility.upload_file_bytes")
@patch("kairon.shared.chat.user_media.Utility")
@patch("kairon.shared.chat.user_media.UserMedia.mark_user_media_data_upload_done")
def test_save_media_content_success(mock_mark_done, mock_utility, mock_upload):
    mock_utility.environment = {
        "storage": {
            "user_media": {
                "bucket": "bucket",
                "root_dir": "root",
                "allowed_extensions": [".txt"]
            }
        }
    }
    mock_upload.return_value = "uploaded_url"

    UserMedia.save_media_content("bot", "user", "mediaid", b"abc", "file.txt")

    mock_mark_done.assert_called_once()


@patch("kairon.shared.chat.user_media.CloudUtility.upload_file_bytes", side_effect=Exception("upload failed"))
@patch("kairon.shared.chat.user_media.Utility")
@patch("kairon.shared.chat.user_media.UserMedia.mark_user_media_data_upload_failed")
def test_save_media_content_failure(mock_mark_failed, mock_utility, mock_upload):
    mock_utility.environment = {
        "storage": {
            "user_media": {
                "bucket": "bucket",
                "root_dir": "root",
                "allowed_extensions": [".txt"]
            }
        }
    }

    with pytest.raises(AppException, match="File upload for mediaid failed"):
        UserMedia.save_media_content("bot", "user", "mediaid", b"abc", "file.txt")

    mock_mark_failed.assert_called_once()


def test_save_media_content_invalid_extension():
    from kairon.shared.chat import user_media
    user_media.Utility.environment = {
        "storage": {
            "user_media": {
                "allowed_extensions": [".txt"]
            }
        }
    }

    with pytest.raises(AppException, match="Only"):
        UserMedia.save_media_content("bot", "user", "mediaid", b"abc", "file.exe")


def test_save_media_content_no_filename():
    with pytest.raises(AppException, match="filename must be provided"):
        UserMedia.save_media_content("bot", "user", "mediaid", b"abc", None)


@pytest.mark.asyncio
@patch("kairon.shared.chat.user_media.UserMedia.extract_media_information")
@patch("kairon.shared.chat.user_media.UserMedia.save_media_content", autospec=True)
async def test_save_media_content_task(mock_save, mock_extract_media_information):
    await UserMedia.save_media_content_task("bot", "user", "id", b"data", "file.txt")
    mock_save.assert_called_once()
    mock_extract_media_information.assert_called_once()


@patch("kairon.shared.chat.user_media.MarkdownPdf")
@patch("kairon.shared.chat.user_media.fitz")
@patch("kairon.shared.chat.user_media.UserMedia.save_media_content")
@patch("kairon.shared.chat.user_media.UserMedia.create_user_media_data")
@patch("kairon.shared.chat.user_media.uuid7")
def test_save_markdown_as_pdf(mock_uuid, mock_create, mock_save, mock_fitz, mock_md_pdf):
    mock_uuid.return_value.hex = "mediaid"
    mock_writer = MagicMock()
    mock_writer.close = MagicMock()
    mock_writer.out_file = BytesIO()

    mock_pdf = MagicMock()
    mock_pdf.writer = mock_writer
    mock_pdf.out_file = BytesIO(b"%PDF-1.4 fake pdf")
    mock_pdf.hrefs = []
    mock_pdf.meta = {}
    mock_md_pdf.return_value = mock_pdf

    doc_mock = MagicMock()
    doc_mock.write.return_value = b"binary"
    mock_fitz.Story.add_pdf_links.return_value = doc_mock

    result, media_id = UserMedia.save_markdown_as_pdf("bot", "user", "# Hello", "file.pdf")

    assert result == b"binary"
    assert media_id == "mediaid"
    mock_create.assert_called_once()
    mock_save.assert_called_once()


def test_save_markdown_as_pdf_invalid_path():
    with pytest.raises(AppException, match="must have a .pdf extension"):
        UserMedia.save_markdown_as_pdf("bot", "user", "# Hello", "file.doc")

@pytest.mark.asyncio
@patch("kairon.shared.chat.user_media.UserMediaData.objects")
async def test_get_media_content_buffer_not_found(mock_objects):
    mock_objects.get.side_effect = Exception("Not Found")

    with pytest.raises(Exception, match="Not Found"):
        await UserMedia.get_media_content_buffer("non-existent-id", base64_encode=True)


@pytest.mark.asyncio
async def test_upload_empty_media_list():
    media_ids, _ = await UserMedia.upload_media_contents("bot123", "user@domain.com", [])
    assert media_ids == []

@patch("kairon.shared.chat.user_media.UserMediaData.objects")
def test_mark_user_media_data_upload_done_not_found(mock_objects):
    mock_objects.return_value.get.return_value = None
    UserMedia.mark_user_media_data_upload_done("notfound", "url", "file", 0)


@patch("kairon.shared.chat.user_media.UserMediaData.objects")
def test_mark_user_media_data_upload_failed_not_found(mock_objects):
    mock_objects.return_value.get.return_value = None
    UserMedia.mark_user_media_data_upload_failed("notfound", "fail reason")


@pytest.mark.asyncio
@patch("kairon.shared.chat.user_media.UserMedia.create_user_media_data")
@patch("kairon.shared.chat.user_media.uuid7")
@patch("kairon.shared.chat.user_media.requests.get")
async def test_save_whatsapp_media_content_360dialog_success(mock_get, mock_uuid, mock_create):
    bot = "bot1"
    sender_id = "user1"
    whatsapp_media_id = "media123"
    config = {"bsp_type": "360dialog", "api_key": "key123"}

    resp_info = MagicMock()
    resp_info.status_code = 200
    resp_info.json.return_value = {
        "url": "https://lookaside.fbsbx.com/path/file.jpg",
        "mime_type": "image/jpeg"
    }

    resp_media = MagicMock()
    resp_media.status_code = 200
    resp_media.iter_content = MagicMock(return_value=[b"chunk1", b"chunk2"])

    mock_get.side_effect = [resp_info, resp_media]

    mock_uuid.return_value.hex = "uuid123"

    created = []
    with patch("asyncio.create_task", lambda coro: created.append(coro)):
        result = UserMedia.save_whatsapp_media_content(bot, sender_id, whatsapp_media_id, config)

    assert result == ["uuid123"]
    mock_get.assert_called()
    mock_create.assert_called_once_with(
        bot=bot,
        media_id="uuid123",
        filename="whataspp_360_media123.jpg",
        sender_id=sender_id,
        upload_type=UserMediaUploadType.user_uploaded.value
    )
    assert len(created) == 1

@pytest.mark.asyncio
@patch("kairon.shared.chat.user_media.UserMedia.create_user_media_data")
@patch("kairon.shared.chat.user_media.uuid7")
@patch("kairon.shared.chat.user_media.requests.get")
async def test_save_whatsapp_media_content_meta_success(mock_get, mock_uuid, mock_create):
    bot = "bot2"
    sender_id = "user2"
    whatsapp_media_id = "media456"
    config = {"bsp_type": "meta", "access_token": "token456"}

    media_info = MagicMock()
    media_info.status_code = 200
    media_info.json.return_value = {
        "url": "https://graph.facebook.com/path/file.mp4",
        "mime_type": "video/mp4"
    }
    media_resp = MagicMock()
    media_resp.status_code = 200
    media_resp.iter_content = MagicMock(return_value=[b"data1", b"data2"])

    mock_get.side_effect = [media_info, media_resp]

    mock_uuid.return_value.hex = "uuid456"

    called = []
    with patch("asyncio.create_task", lambda coro: called.append(coro)):
        result = UserMedia.save_whatsapp_media_content(bot, sender_id, whatsapp_media_id, config)

    assert result == ["uuid456"]
    mock_get.assert_any_call(
        f"https://graph.facebook.com/v22.0/{whatsapp_media_id}",
        params={"fields": "url", "access_token": config['access_token']},
        timeout=10
    )
    mock_create.assert_called_once()


def created_coros(coros):
    return coros


@pytest.mark.asyncio
@patch("kairon.shared.chat.user_media.requests.get")
def test_save_whatsapp_media_content_360dialog_failure(mock_get):
    config = {"bsp_type": "360dialog", "api_key": "key"}
    resp = MagicMock(status_code=500, text="error")
    mock_get.return_value = resp

    with pytest.raises(AppException) as exc:
        UserMedia.save_whatsapp_media_content("b","s","id", config)
    assert "Failed to download media from 360 dialog" in str(exc.value)


@pytest.mark.asyncio
@patch("kairon.shared.chat.user_media.requests.get")
def test_save_whatsapp_media_content_meta_failure(mock_get):
    config = {"bsp_type": "meta", "access_token": "token"}
    resp = MagicMock(status_code=400)
    mock_get.return_value = resp

    with pytest.raises(AppException) as exc:
        UserMedia.save_whatsapp_media_content("b","s","id", config)
    assert "Failed to get url from meta" in str(exc.value)




@patch("kairon.shared.chat.user_media.Actions")
@patch("kairon.shared.chat.user_media.PromptAction")
@patch("kairon.shared.chat.user_media.Rules")
@patch("kairon.shared.chat.user_media.logger")
@patch("kairon.shared.utils.Utility.environment", {
    "notifications": {"enable": False},
    "events": {
        "audit_logs": {
            "attributes": []
        }
    }
})
def test_add_media_extraction_flow_if_not_exist(mock_logger, mock_rules, mock_prompt_action, mock_actions):
    bot = "test_bot"

    mock_actions.objects.return_value.first.return_value = None
    mock_prompt_action.objects.return_value.first.return_value = None
    mock_rules.objects.return_value.first.return_value = None

    mock_action_instance = MagicMock()
    mock_actions.return_value = mock_action_instance

    mock_prompt_action_instance = MagicMock()
    mock_prompt_action.return_value = mock_prompt_action_instance

    mock_rule_instance = MagicMock()
    mock_rules.return_value = mock_rule_instance

    UserMedia.add_media_extraction_flow_if_not_exist(bot)

    mock_actions.objects.assert_called_once_with(bot=bot, name=f"{UserMedia.MEDIA_EXTRACTION_FLOW_NAME}_prompt_action")
    mock_prompt_action.objects.assert_called_once_with(bot=bot, name=f"{UserMedia.MEDIA_EXTRACTION_FLOW_NAME}_prompt_action")
    mock_rules.objects.assert_called_once_with(block_name=UserMedia.MEDIA_EXTRACTION_FLOW_NAME, bot=bot)

    mock_action_instance.save.assert_called_once()
    mock_prompt_action_instance.save.assert_called_once()
    mock_rule_instance.save.assert_called_once()

    mock_logger.exception.assert_not_called()

@patch("kairon.shared.chat.user_media.logger")
def test_add_media_extraction_flow_if_not_exist_exception(mock_logger):
    bot = "test_bot"

    with patch("kairon.shared.chat.user_media.Actions.objects", side_effect=Exception("Database error")):
        with pytest.raises(AppException, match="Failed to add media extraction flow: Database error"):
            UserMedia.add_media_extraction_flow_if_not_exist(bot)

    mock_logger.exception.assert_called_once()




@pytest.mark.asyncio
@patch("kairon.shared.chat.user_media.UserMedia.add_media_extraction_flow_if_not_exist")
@patch("kairon.shared.chat.user_media.AgenticFlow")
async def test_extract_media_information_execution_error(mock_agentic_flow, mock_add_flow):
    bot = "test_bot"
    media_id = "media123"
    sender_id = "user123"

    mock_flow_instance = MagicMock()
    mock_flow_instance.execute_rule = AsyncMock(return_value=(None, "Execution error"))
    mock_agentic_flow.return_value = mock_flow_instance

    with pytest.raises(AppException, match="Failed to extract media information: Execution error"):
        await UserMedia.extract_media_information(bot, media_id, sender_id)

    mock_add_flow.assert_called_once_with(bot)
    mock_agentic_flow.assert_called_once_with(bot, slot_vals={"media_ids": [media_id]}, sender_id=sender_id)
    mock_flow_instance.execute_rule.assert_called_once_with(UserMedia.MEDIA_EXTRACTION_FLOW_NAME)


@pytest.mark.asyncio
@patch("kairon.shared.chat.user_media.UserMedia.add_media_extraction_flow_if_not_exist")
@patch("kairon.shared.chat.user_media.AgenticFlow")
@patch("kairon.shared.chat.user_media.UserMediaData.objects")
async def test_extract_media_information_success(mock_objects, mock_agentic_flow, mock_add_flow):
    bot = "test_bot"
    media_id = "media123"
    sender_id = "user123"

    mock_flow_instance = MagicMock()
    mock_flow_instance.execute_rule = AsyncMock(return_value=([{"text": "Extracted summary"}], None))
    mock_agentic_flow.return_value = mock_flow_instance

    mock_media_data = MagicMock()
    mock_media_data.summary = "Extracted summary"
    mock_objects.get.return_value = mock_media_data

    await UserMedia.extract_media_information(bot, media_id, sender_id)

    mock_add_flow.assert_called_once_with(bot)
    mock_agentic_flow.assert_called_once_with(bot, slot_vals={"media_ids": [media_id]}, sender_id=sender_id)
    mock_flow_instance.execute_rule.assert_called_once_with(UserMedia.MEDIA_EXTRACTION_FLOW_NAME)
    assert mock_media_data.summary == "Extracted summary"

@pytest.mark.asyncio
@patch("kairon.shared.chat.user_media.UserMedia.add_media_extraction_flow_if_not_exist")
@patch("kairon.shared.chat.user_media.AgenticFlow")
@patch("kairon.shared.chat.user_media.UserMediaData.objects")
async def test_extract_media_information_exceptions(mock_objects, mock_agentic_flow, mock_add_flow):
    bot = "test_bot"
    media_id = "media123"
    sender_id = "user123"

    mock_flow_instance = MagicMock()
    mock_flow_instance.execute_rule = AsyncMock(return_value=(None, "Some error occurred"))
    mock_agentic_flow.return_value = mock_flow_instance

    with pytest.raises(AppException, match="Failed to extract media information: Some error occurred"):
        await UserMedia.extract_media_information(bot, media_id, sender_id)

    mock_flow_instance.execute_rule = AsyncMock(return_value=([], None))
    mock_agentic_flow.return_value = mock_flow_instance

    with pytest.raises(AppException, match=f"extraction prompt action execution failed: {media_id}"):
        await UserMedia.extract_media_information(bot, media_id, sender_id)



@pytest.mark.asyncio
@patch("kairon.shared.chat.user_media.asyncio.create_task")
@patch("kairon.shared.chat.user_media.requests.get")
@patch("kairon.shared.chat.user_media.UserMedia.create_user_media_data")
def test_save_whatsapp_media_content_background_task_failure(mock_create_user_media_data, mock_requests_get, mock_create_task):
    bot = "test_bot"
    sender_id = "user123"
    whatsapp_media_id = "media123"
    config = {"bsp_type": "meta", "access_token": "test_token"}

    mock_media_info_resp = MagicMock()
    mock_media_info_resp.status_code = 200
    mock_media_info_resp.json.return_value = {"url": "http://example.com/media", "mime_type": "image/png"}

    mock_media_resp = MagicMock()
    mock_media_resp.status_code = 200
    mock_media_resp.iter_content.return_value = [b"chunk1", b"chunk2"]

    mock_requests_get.side_effect = [mock_media_info_resp, mock_media_resp]

    def mock_background_task(*args, **kwargs):
        raise Exception("Background task failed")
    mock_create_task.side_effect = mock_background_task

    with pytest.raises(Exception, match="Background task failed"):
        UserMedia.save_whatsapp_media_content(bot, sender_id, whatsapp_media_id, config)

    mock_requests_get.assert_called()
    mock_create_user_media_data.assert_called_once()
    mock_create_task.assert_called_once()




@patch("kairon.shared.chat.user_media.asyncio.create_task")
@patch("kairon.shared.chat.user_media.requests.get")
@patch("kairon.shared.chat.user_media.UserMedia.create_user_media_data")
def test_save_whatsapp_media_content_success(mock_create_user_media_data, mock_requests_get, mock_create_task):
    bot = "test_bot"
    sender_id = "user123"
    whatsapp_media_id = "media123"
    config = {"bsp_type": "meta", "access_token": "test_token"}

    mock_media_info_resp = MagicMock()
    mock_media_info_resp.status_code = 200
    mock_media_info_resp.json.return_value = {"url": "http://example.com/media", "mime_type": "image/png"}

    mock_media_resp = MagicMock()
    mock_media_resp.status_code = 200
    mock_media_resp.iter_content.return_value = [b"chunk1", b"chunk2"]

    mock_requests_get.side_effect = [mock_media_info_resp, mock_media_resp]

    mock_create_task.return_value = None

    result = UserMedia.save_whatsapp_media_content(bot, sender_id, whatsapp_media_id, config)

    assert result == [mock_create_user_media_data.call_args[1]["media_id"]]
    mock_requests_get.assert_called()
    mock_create_user_media_data.assert_called_once()
    mock_create_task.assert_called_once()


@pytest.mark.asyncio
@patch("kairon.shared.chat.user_media.UserMedia.save_media_content_task", new_callable=AsyncMock)
@patch("kairon.shared.chat.user_media.UserMedia.create_user_media_data")
async def test_upload_media_content_sync(mock_create_user_media_data, mock_save_media_content_task):
    bot = "test_bot"
    sender_id = "user123"
    files = [MagicMock(), MagicMock()]

    files[0].filename = "file1.txt"
    files[1].filename = "file2.txt"
    files[0].read = AsyncMock(return_value=b"binary_data_1")
    files[1].read = AsyncMock(return_value=b"binary_data_2")

    media_ids, file_names = await UserMedia.upload_media_content_sync(bot, sender_id, files)

    assert len(media_ids) == 2
    assert len(file_names) == 2
    assert file_names == ["file1.txt", "file2.txt"]
    assert mock_create_user_media_data.call_count == 2
    assert mock_save_media_content_task.call_count == 2

    mock_create_user_media_data.assert_any_call(
        bot=bot,
        media_id=media_ids[0],
        filename="file1.txt",
        sender_id=sender_id
    )
    mock_create_user_media_data.assert_any_call(
        bot=bot,
        media_id=media_ids[1],
        filename="file2.txt",
        sender_id=sender_id
    )

    mock_save_media_content_task.assert_any_await(
        bot=bot,
        sender_id=sender_id,
        media_id=media_ids[0],
        binary_data=b"binary_data_1",
        filename="file1.txt",
        execute_summarizarion=False
    )
    mock_save_media_content_task.assert_any_await(
        bot=bot,
        sender_id=sender_id,
        media_id=media_ids[1],
        binary_data=b"binary_data_2",
        filename="file2.txt",
        execute_summarizarion=False
    )
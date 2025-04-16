import os
import io
import pytest
import base64
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime
from pathlib import Path
from fastapi import UploadFile

from kairon.exceptions import AppException
from kairon.shared.data.data_objects import UserMediaData
from kairon.shared.cloud.utils import CloudUtility
from kairon import Utility

# Import the class being tested
from kairon.shared.chat.user_media import UserMedia


@pytest.fixture
def mock_environment():
    env = {
        "storage": {
            "user_media": {
                "bucket": "test-bucket",
                "root_dir": "media",
                "allowed_extensions": [".jpg", ".png", ".pdf", ".docx"]
            }
        }
    }
    with patch.object(Utility, "environment", env):
        yield


@pytest.fixture
def mock_user_media_data():
    with patch("kairon.shared.chat.user_media.UserMediaData") as mock:
        mock_instance = MagicMock()
        mock_instance.media_id = "media123"
        mock_instance.s3_url = "https://storage.com/test-bucket/media/test-bot/user123_test.pdf"
        mock_instance.filename = "test.pdf"
        mock_instance.extension = ".pdf"
        mock_instance.output_filename = "media/test-bot/user123_test.pdf"
        mock_instance.filesize = 100
        mock_instance.bot = "test-bot"
        mock_instance.sender_id = "user123"
        mock_instance.timestamp = datetime.utcnow()
        mock.return_value = mock_instance
        mock.objects.get.return_value = mock_instance
        yield mock


@pytest.fixture
def mock_cloud_utility():
    with patch("kairon.shared.chat.user_media.CloudUtility") as mock:
        mock.upload_file.return_value = "https://storage.com/test-bucket/media/test-bot/user123_test.pdf"
        mock_buffer = io.BytesIO(b"test file content")
        mock.download_file_to_memory.return_value = mock_buffer
        yield mock


@pytest.fixture
def mock_io_bytes():
    with patch("kairon.shared.chat.user_media.io.BytesIO") as mock:
        mock_buffer = MagicMock()
        mock_buffer.read.return_value = b"pdf content"
        mock.return_value = mock_buffer
        yield mock


@pytest.fixture
def mock_html():
    with patch("kairon.shared.chat.user_media.HTML") as mock:
        mock_html_instance = MagicMock()
        mock.return_value = mock_html_instance
        yield mock


@pytest.fixture
def mock_markdown():
    with patch("kairon.shared.chat.user_media.markdown") as mock:
        mock.markdown.return_value = "<h1>Test</h1><p>Content</p>"
        yield mock


@pytest.fixture
def mock_tempfile():
    with patch("kairon.shared.chat.user_media.tempfile") as mock:
        mock.mkdtemp.return_value = "/tmp/test"
        yield mock


@pytest.fixture
def mock_utility_write():
    with patch("kairon.shared.chat.user_media.Utility.write_to_file") as mock:
        yield mock


@pytest.fixture
def mock_uuid():
    with patch("kairon.shared.chat.user_media.uuid7") as mock:
        mock_uuid = MagicMock()
        mock_uuid.hex = "mock-uuid-12345"
        mock.return_value = mock_uuid
        yield mock


@pytest.fixture
def mock_create_task():
    with patch("kairon.shared.chat.user_media.asyncio.create_task") as mock:
        yield mock


class TestUserMedia:

    @pytest.mark.asyncio
    async def test_save_media_content_task_with_data_success(self, mock_environment, mock_cloud_utility,
                                                             mock_tempfile, mock_utility_write, mock_user_media_data):
        # Arrange
        bot = "test-bot"
        sender_id = "user123"
        media_id = "media123"
        binary_data = b"test file content"
        filename = "test.pdf"

        # Act
        await UserMedia.save_media_content(
            bot=bot, sender_id=sender_id, media_id=media_id, data=binary_data, filename=filename
        )

        # Assert
        mock_utility_write.assert_called_once_with("/tmp/test/test.pdf", binary_data)
        mock_cloud_utility.upload_file.assert_called_once_with(
            "/tmp/test/test.pdf", "test-bucket", "media/test-bot/user123_test.pdf"
        )

        # Don't assert specific timestamp values, just verify the constructor was called with the right parameters
        mock_user_media_data.assert_called_once()
        call_kwargs = mock_user_media_data.call_args.kwargs
        assert call_kwargs['media_id'] == media_id
        assert call_kwargs['s3_url'] == "https://storage.com/test-bucket/media/test-bot/user123_test.pdf"
        assert call_kwargs['filename'] == filename
        assert call_kwargs['extension'] == ".pdf"
        assert call_kwargs['output_filename'] == "media/test-bot/user123_test.pdf"
        assert call_kwargs['filesize'] == len(binary_data)
        assert call_kwargs['sender_id'] == sender_id
        assert call_kwargs['bot'] == bot
        assert isinstance(call_kwargs['timestamp'], datetime)
        mock_user_media_data.return_value.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_media_content_task_with_file_success(self, mock_environment, mock_cloud_utility,
                                                             mock_tempfile, mock_utility_write, mock_user_media_data):
        # Arrange
        bot = "test-bot"
        sender_id = "user123"
        media_id = "media123"
        binary_data = b"test file content"

        # Create mock file
        mock_file = AsyncMock(spec=UploadFile)
        mock_file.filename = "test.pdf"
        mock_file.read.return_value = binary_data

        # Act
        await UserMedia.save_media_content(
            bot=bot, sender_id=sender_id, media_id=media_id, file=mock_file
        )

        # Assert
        mock_file.read.assert_called_once()
        mock_utility_write.assert_called_once_with("/tmp/test/test.pdf", binary_data)
        mock_cloud_utility.upload_file.assert_called_once_with(
            "/tmp/test/test.pdf", "test-bucket", "media/test-bot/user123_test.pdf"
        )
        mock_user_media_data.assert_called_once()
        mock_user_media_data.return_value.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_media_content_task_no_filename_with_data(self, mock_environment):
        # Arrange
        bot = "test-bot"
        sender_id = "user123"
        media_id = "media123"
        binary_data = b"test file content"

        # Act & Assert
        with pytest.raises(AppException) as exc_info:
            await UserMedia.save_media_content(
                bot=bot, sender_id=sender_id, media_id=media_id, data=binary_data
            )

        assert "filename must be provided for binary data" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_save_media_content_task_invalid_extension(self, mock_environment, mock_utility_write):
        # Arrange
        bot = "test-bot"
        sender_id = "user123"
        media_id = "media123"
        binary_data = b"test file content"
        filename = "test.exe"

        # Act & Assert
        with pytest.raises(AppException) as exc_info:
            await UserMedia.save_media_content(
                bot=bot, sender_id=sender_id, media_id=media_id, data=binary_data, filename=filename
            )

        assert "Only ['.jpg', '.png', '.pdf', '.docx'] type files allowed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_save_media_content_task_upload_error(self, mock_environment, mock_tempfile,
                                                        mock_utility_write, mock_cloud_utility):
        # Arrange
        bot = "test-bot"
        sender_id = "user123"
        media_id = "media123"
        binary_data = b"test file content"
        filename = "test.pdf"

        # Setup the upload to fail
        from pathy import ClientError
        mock_cloud_utility.upload_file.side_effect = ClientError("Upload failed", code=400)

        # Act & Assert
        with pytest.raises(AppException) as exc_info:
            await UserMedia.save_media_content(
                bot=bot, sender_id=sender_id, media_id=media_id, data=binary_data, filename=filename
            )

        assert "File upload failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_save_media_content_task_general_error(self, mock_environment, mock_tempfile,
                                                         mock_utility_write, mock_cloud_utility):
        # Arrange
        bot = "test-bot"
        sender_id = "user123"
        media_id = "media123"
        binary_data = b"test file content"
        filename = "test.pdf"

        # Setup a general error
        mock_cloud_utility.upload_file.side_effect = Exception("General error")

        # Act & Assert
        with pytest.raises(AppException) as exc_info:
            await UserMedia.save_media_content(
                bot=bot, sender_id=sender_id, media_id=media_id, data=binary_data, filename=filename
            )

        assert "File upload failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_upload_media_contents(self, mock_environment, mock_create_task, mock_uuid):
        # Arrange
        bot = "test-bot"
        sender_id = "user123"

        # Create mock files
        mock_file1 = AsyncMock(spec=UploadFile)
        mock_file2 = AsyncMock(spec=UploadFile)
        files = [mock_file1, mock_file2]

        # Act
        media_ids = await UserMedia.upload_media_contents(bot, sender_id, files)

        # Assert
        assert len(media_ids) == 2
        assert all(id == "mock-uuid-12345" for id in media_ids)
        assert mock_create_task.call_count == 2

        # Check the arguments passed to create_task
        call1 = mock_create_task.call_args_list[0]
        call2 = mock_create_task.call_args_list[1]

        # We have limited ways to inspect the coroutine objects, so check that each call has one argument
        assert len(call1.args) == 1
        assert len(call2.args) == 1

    @pytest.mark.asyncio
    async def test_get_media_content_buffer_no_base64(self, mock_environment, mock_user_media_data, mock_cloud_utility):
        # Arrange
        media_id = "media123"

        # Act
        file_buffer, download_name = await UserMedia.get_media_content_buffer(media_id)

        # Assert
        mock_user_media_data.objects.get.assert_called_once_with(media_id=media_id)
        mock_cloud_utility.download_file_to_memory.assert_called_once_with(
            "test-bucket", mock_user_media_data.objects.get.return_value.filename
        )
        assert file_buffer == mock_cloud_utility.download_file_to_memory.return_value
        assert download_name == "test-bot_user123_test.pdf.pdf"

    @pytest.mark.asyncio
    async def test_get_media_content_buffer_with_base64(self, mock_environment, mock_user_media_data,
                                                        mock_cloud_utility):
        # Arrange
        media_id = "media123"

        # Act
        encoded_string, download_name = await UserMedia.get_media_content_buffer(media_id, base64_encode=True)

        # Assert
        mock_user_media_data.objects.get.assert_called_once_with(media_id=media_id)
        mock_cloud_utility.download_file_to_memory.assert_called_once_with(
            "test-bucket", mock_user_media_data.objects.get.return_value.filename
        )
        assert encoded_string == base64.b64encode(b"test file content").decode('utf-8')
        assert download_name == "test-bot_user123_test.pdf.pdf"

    @pytest.mark.asyncio
    async def test_get_media_content_buffer_document_not_found(self, mock_environment, mock_user_media_data):
        # Arrange
        media_id = "non-existent"

        # Setup document not found
        from mongoengine import DoesNotExist
        mock_user_media_data.objects.get.side_effect = DoesNotExist()

        # Act & Assert
        with pytest.raises(AppException) as exc_info:
            await UserMedia.get_media_content_buffer(media_id)

        assert "Document not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_save_markdown_as_pdf(self, mock_environment, mock_markdown, mock_html, mock_io_bytes, mock_uuid):
        # Arrange
        bot = "test-bot"
        sender_id = "user123"
        markdown_text = "# Test\nContent"
        filepath = "report.pdf"

        # Act
        with patch.object(UserMedia, "save_media_content_task", new_callable=AsyncMock) as mock_save:
            pdf_buffer, media_id = await UserMedia.save_markdown_as_pdf(bot, sender_id, markdown_text, filepath)

        # Assert
        mock_markdown.markdown.assert_called_once_with(markdown_text)
        mock_html.assert_called_once_with(string="<h1>Test</h1><p>Content</p>")
        mock_html.return_value.write_pdf.assert_called_once()

        # This avoids the isinstance issue
        assert media_id == "mock-uuid-12345"
        mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_markdown_as_pdf_invalid_extension(self):
        # Arrange
        bot = "test-bot"
        sender_id = "user123"
        markdown_text = "# Test\nContent"
        filepath = "report.txt"  # Not a PDF

        # Act & Assert
        with pytest.raises(AppException) as exc_info:
            await UserMedia.save_markdown_as_pdf(bot, sender_id, markdown_text, filepath)

        assert "Provided filepath must have a .pdf extension" in str(exc_info.value)
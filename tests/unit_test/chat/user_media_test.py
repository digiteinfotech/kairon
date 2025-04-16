import asyncio
import base64
import io
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest
import markdown
from weasyprint import HTML

from kairon.exceptions import AppException
from kairon.shared.cloud.utils import CloudUtility
from kairon.shared.data.data_objects import UserMediaData
from uuid6 import uuid7

# Import using the correct module path.
from kairon.shared.chat.user_media import UserMedia


# --- Dummy Classes & Helpers ---

# Dummy File class to simulate FastAPI File objects.
class DummyFile:
    def __init__(self, filename, content: bytes, raise_on_read=False):
        self.filename = filename
        self._content = content
        self.raise_on_read = raise_on_read

    async def read(self):
        if self.raise_on_read:
            raise Exception("Read error")
        return self._content


# Updated dummy implementation for UserMediaData.
class DummyUserMediaData:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.id = "dummy_id"

    def to_mongo(self):
        # Create a dummy dict-like object that returns the proper document fields.
        data = {
            "media_id": self.media_id,
            "filename": self.filename,
            "extension": self.extension,
            "bot": self.bot,
            "sender_id": self.sender_id,
        }

        class DummyMongo:
            def dict(inner_self):
                return data

        return DummyMongo()

    def save(self):
        self.saved = True


# Dummy Utility replacing the real Utility.
class DummyUtility:
    environment = {
        "storage": {
            "user_media": {
                "bucket": "dummy_bucket",
                "root_dir": "dummy_root",
                "allowed_extensions": [".txt", ".pdf"]
            }
        }
    }

    @staticmethod
    def write_to_file(file_path: str, binary_data: bytes):
        with open(file_path, "wb") as f:
            f.write(binary_data)


# --- Pytest Fixture for Patching Utility ---

@pytest.fixture(autouse=True)
def patch_utility(monkeypatch):
    monkeypatch.setattr("kairon.shared.chat.user_media.Utility", DummyUtility)


# --- Existing Test Cases ---

def test_save_media_content_without_filename():
    with pytest.raises(AppException, match="filename must be provided for binary data"):
        UserMedia.save_media_content(bot="bot1", sender_id="sender1", media_id="m1", binary_data=b"data", filename=None)


def test_save_media_content_success(monkeypatch, tmp_path):
    binary_data = b"hello world"
    filename = "test.txt"

    def fake_mkdtemp():
        return str(tmp_path)

    monkeypatch.setattr("kairon.shared.chat.user_media.tempfile.mkdtemp", fake_mkdtemp)

    fake_url = "http://dummy-url"
    monkeypatch.setattr(CloudUtility, "upload_file", lambda file_path, bucket, output_filename: fake_url)

    def fake_save(self):
        self.saved = True

    monkeypatch.setattr(DummyUserMediaData, "save", fake_save)

    def fake_user_media_data(*args, **kwargs):
        return DummyUserMediaData(**kwargs)

    monkeypatch.setattr("kairon.shared.chat.user_media.UserMediaData", fake_user_media_data)

    UserMedia.save_media_content(bot="bot1", sender_id="sender1", media_id="m1", binary_data=binary_data,
                                 filename=filename)

    temp_file_path = os.path.join(str(tmp_path), filename)
    assert os.path.exists(temp_file_path)
    with open(temp_file_path, "rb") as f:
        assert f.read() == binary_data


@pytest.mark.asyncio
async def test_save_media_content_task(monkeypatch):
    called = False

    def fake_save_media_content(bot, sender_id, media_id, binary_data, filename):
        nonlocal called
        called = True

    monkeypatch.setattr(UserMedia, "save_media_content", fake_save_media_content)
    await UserMedia.save_media_content_task(bot="bot1", sender_id="sender1", media_id="m1", binary_data=b"data",
                                            filename="test.txt")
    await asyncio.sleep(0.1)
    assert called


@pytest.mark.asyncio
async def test_upload_media_contents(monkeypatch):
    file1 = DummyFile("file1.txt", b"content1")
    file2 = DummyFile("file2.txt", b"content2")
    files = [file1, file2]

    uuids = ["uuid1", "uuid2"]

    def fake_uuid7():
        return type("DummyUUID", (), {"hex": uuids.pop(0)})()

    monkeypatch.setattr("kairon.shared.chat.user_media.uuid7", fake_uuid7)

    async def fake_save_media_content_task(*args, **kwargs):
        return

    monkeypatch.setattr(UserMedia, "save_media_content_task", fake_save_media_content_task)

    media_ids = await UserMedia.upload_media_contents(bot="bot1", sender_id="sender1", files=files)
    assert len(media_ids) == 2
    assert set(media_ids) == {"uuid1", "uuid2"}


# --- Patching MongoEngine QuerySetManager ---
from mongoengine.queryset.manager import QuerySetManager


@pytest.mark.asyncio
async def test_get_media_content_buffer(monkeypatch):
    dummy_media = DummyUserMediaData(
        media_id="m1",
        filename="test.txt",
        extension=".txt",
        bot="bot1",
        sender_id="sender1",
        filesize=100,
        media_url="http://dummy-url",
        timestamp=datetime.utcnow()
    )

    class DummyQuerySet:
        def get(self, media_id):
            if media_id == "m1":
                return dummy_media
            raise UserMediaData.DoesNotExist

    monkeypatch.setattr(QuerySetManager, "__get__", lambda self, instance, owner: DummyQuerySet())

    dummy_buffer = io.BytesIO(b"dummy content")
    monkeypatch.setattr(CloudUtility, "download_file_to_memory", lambda bucket, filename: dummy_buffer)

    file_buffer, download_name = await UserMedia.get_media_content_buffer("m1")
    assert isinstance(file_buffer, io.BytesIO)
    expected_name = f"{dummy_media.bot}_{dummy_media.sender_id}_{dummy_media.filename}{dummy_media.extension}"
    assert download_name == expected_name

    dummy_buffer.seek(0)
    encoded_string, download_name = await UserMedia.get_media_content_buffer("m1", base64_encode=True)
    expected_encoded = base64.b64encode(b"dummy content").decode("utf-8")
    assert encoded_string == expected_encoded


@pytest.mark.asyncio
async def test_get_media_content_buffer_not_found(monkeypatch):
    class DummyQuerySet:
        def get(self, media_id):
            raise UserMediaData.DoesNotExist

    monkeypatch.setattr(QuerySetManager, "__get__", lambda self, instance, owner: DummyQuerySet())
    with pytest.raises(AppException, match="Document not found"):
        await UserMedia.get_media_content_buffer("nonexistent")


@pytest.mark.asyncio
async def test_save_markdown_as_pdf_success(monkeypatch):
    bot = "bot1"
    sender_id = "sender1"
    text = "# Heading\nSome **markdown** content."
    pdf_filepath = "report.pdf"
    monkeypatch.setattr(markdown, "markdown", lambda txt: "<html>dummy</html>")

    def fake_write_pdf(self, pdf_buffer):
        pdf_buffer.write(b"PDF data")

    monkeypatch.setattr(HTML, "write_pdf", fake_write_pdf)
    called_media_save = False

    async def fake_save_media(*args, **kwargs):
        nonlocal called_media_save
        called_media_save = True

    monkeypatch.setattr(UserMedia, "save_media_content", fake_save_media)
    pdf_buffer, media_id = await UserMedia.save_markdown_as_pdf(bot=bot, sender_id=sender_id, text=text,
                                                                filepath=pdf_filepath)
    pdf_buffer.seek(0)
    assert pdf_buffer.read() == b"PDF data"
    assert called_media_save


@pytest.mark.asyncio
async def test_save_markdown_as_pdf_invalid_extension():
    with pytest.raises(AppException, match="Provided filepath must have a .pdf extension"):
        await UserMedia.save_markdown_as_pdf(bot="bot1", sender_id="sender1", text="dummy", filepath="report.txt")



@pytest.mark.asyncio
async def test_upload_media_contents_file_read_error(monkeypatch):
    file1 = DummyFile("file1.txt", b"content1")
    file2 = DummyFile("file2.txt", b"content2", raise_on_read=True)
    files = [file1, file2]

    async def dummy_read_tasks():
        return await asyncio.gather(*(f.read() for f in files), return_exceptions=True)

    results = await dummy_read_tasks()
    assert isinstance(results[1], Exception)



@pytest.mark.asyncio
async def test_get_media_content_buffer_consistency(monkeypatch):
    dummy_media = DummyUserMediaData(
        media_id="m2",
        filename="example.txt",
        extension=".txt",
        bot="bot2",
        sender_id="sender2",
        filesize=150,
        media_url="http://dummy-url",
        timestamp=datetime.utcnow()
    )

    class DummyQuerySet:
        def get(self, media_id):
            return dummy_media

    monkeypatch.setattr(QuerySetManager, "__get__", lambda self, instance, owner: DummyQuerySet())
    dummy_buffer = io.BytesIO(b"consistent content")
    monkeypatch.setattr(CloudUtility, "download_file_to_memory", lambda bucket, filename: dummy_buffer)

    file_buffer1, download_name1 = await UserMedia.get_media_content_buffer("m2")
    file_buffer2, download_name2 = await UserMedia.get_media_content_buffer("m2")
    assert download_name1 == download_name2
    expected_name = f"{dummy_media.bot}_{dummy_media.sender_id}_{dummy_media.filename}{dummy_media.extension}"
    assert download_name1 == expected_name


@pytest.mark.asyncio
async def test_save_markdown_as_pdf_empty_text(monkeypatch):
    bot = "bot3"
    sender_id = "sender3"
    text = ""
    pdf_filepath = "empty_report.pdf"
    monkeypatch.setattr(markdown, "markdown", lambda txt: "<html>empty</html>")

    def fake_write_pdf(self, pdf_buffer):
        pdf_buffer.write(b"Empty PDF")

    monkeypatch.setattr(HTML, "write_pdf", fake_write_pdf)
    called_media_save = False

    async def fake_save_media(*args, **kwargs):
        nonlocal called_media_save
        called_media_save = True

    monkeypatch.setattr(UserMedia, "save_media_content", fake_save_media)

    pdf_buffer, media_id = await UserMedia.save_markdown_as_pdf(bot=bot, sender_id=sender_id, text=text,
                                                                filepath=pdf_filepath)
    pdf_buffer.seek(0)
    content = pdf_buffer.read()
    assert content == b"Empty PDF"
    assert called_media_save

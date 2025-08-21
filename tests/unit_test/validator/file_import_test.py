import os
import pytest
from mongoengine import connect, DoesNotExist
from kairon import Utility
from kairon.events.definitions.crud_file_upload import CrudFileUploader
from kairon.exceptions import AppException
from kairon.importer.file_importer import FileImporter
from types import SimpleNamespace

class TestFileImporter:

    @pytest.fixture(scope="class", autouse=True)
    def init(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    @pytest.fixture
    def sample_csv_file(self):
        csv_path = "tests/testing_data/file_content_upload"
        return csv_path

    @pytest.fixture
    def uploader_instance(self):

        return CrudFileUploader(
            bot="test_bot",
            user="test_user",
            type="crud_data",
            overwrite=False,
            collection_name="test_collection"
        )

    def test_validate(self, uploader_instance):
        with open("tests/testing_data/file_content_upload/Salesstore.csv", "rb") as fh:
            file_ns = SimpleNamespace(filename="Salesstore.csv", content_type="text/csv", file=fh)
            with pytest.raises(DoesNotExist):
                uploader_instance.validate(file_content=file_ns)

    def test_create_payload(self,uploader_instance):

        payload = uploader_instance.create_payload(
            bot="test_bot",
            user="test_user",
            type="crud_data",
            collection_name="test_collection",
            overwrite=False
        )
        assert payload["bot"] == "test_bot"
        assert payload["collection_name"] == "test_collection"
        assert not payload["overwrite"]


    def test_preprocess_returns_expected_structure(self, sample_csv_file):

        file_importer = FileImporter(
            path=sample_csv_file,
            bot="test_bot",
            user="test_user",
            file_received="Salesstore.csv",
            collection_name="test_collection",
            overwrite=False
        )
        result = file_importer.preprocess()

        assert isinstance(result, dict)
        assert "payload" in result
        assert len(result["payload"]) == 20

        first_item = result["payload"][0]
        assert first_item["collection_name"] == "test_collection"
        assert isinstance(first_item["data"], dict)
        assert first_item["data"]["order_id"] == "67"
        assert first_item["data"]["order_priority"] == "Low"
        assert first_item["data"]["profit"] == "54.98"
        assert first_item["data"]["sales"] == "12.34"

    def test_import_data(self, sample_csv_file):

        file_importer = FileImporter(
            path=sample_csv_file,
            bot="test_bot",
            user="test_user",
            file_received="Salesstore.csv",
            collection_name="test_collection",
            overwrite=False
        )
        converted_dict = file_importer.preprocess()
        file_importer.import_data(converted_dict)

    def test_import_data_with_empty_collection_name(self, sample_csv_file):

        file_importer = FileImporter(
            path=sample_csv_file,
            bot="test_bot",
            user="test_user",
            file_received="Salesstore.csv",
            collection_name="",
            overwrite=False
        )
        converted_dict = file_importer.preprocess()
        with pytest.raises(AppException) as exec_info:
            file_importer.import_data(converted_dict)

        assert "errors in bulk insert" in str(exec_info.value).lower()
        assert "collection name is empty" in str(exec_info.value).lower()

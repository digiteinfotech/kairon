import os
import pytest
from mongoengine import connect
from kairon import Utility
from kairon.events.definitions.crud_file_upload import CrudFileUploader
from kairon.importer.file_importer import FileImporter

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
        assert "collections" in result
        assert len(result["collections"]) == 20

        first_item = result["collections"][0]
        assert first_item["collection_name"] == "test_collection"
        assert isinstance(first_item["data"], dict)
        assert first_item["data"]["order_id"] == "67"
        assert first_item["data"]["order_priority"] == "Low"
        assert first_item["data"]["profit"] == "54.98"
        assert first_item["data"]["sales"] == "12.34"

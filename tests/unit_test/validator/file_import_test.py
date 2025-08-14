import os
import io
import pytest
from mongoengine import connect

from kairon import Utility
from kairon.events.definitions.crud_file_upload import CrudFileUploader
from kairon.importer.file_importer import FileImporter
from kairon.shared.data.processor import MongoProcessor
from starlette.datastructures import UploadFile

class TestFileImporter:
    @pytest.fixture(scope="class", autouse=True)
    def init(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))
    @pytest.fixture
    def sample_csv_file(self):
        """Creates a sample CSV file for upload."""
        csv_path = "tests/testing_data/file_content_upload"
        file_name='Salesstore.csv'
        file_recieved=os.path.join(csv_path, file_name)
        return file_recieved


    @pytest.fixture
    def upload_file(self,sample_csv_file):
        """Creates UploadFile object from sample CSV."""
        return UploadFile(filename="Salesstore.csv", file=open(sample_csv_file, "rb"))


    @pytest.fixture
    def uploader_instance(self):
        """Creates a CrudFileUploader instance."""
        return CrudFileUploader(
            bot="test_bot",
            user="test_user",
            type="crud_data",
            overwrite=False,
            collection_name="test_collection"
        )

    def test_create_payload(self,uploader_instance):
        """Checks that create_payload returns correct dictionary."""
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


    def test_preprocess_returns_expected_structure(self):
        """Ensure preprocess reads CSV and formats data properly."""
        file_importer = FileImporter(
            path="tests/testing_data/file_content_upload",
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

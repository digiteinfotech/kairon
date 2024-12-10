import os
import shutil
import tempfile
import pytest
from mongoengine import connect

from kairon.api.models import CognitionSchemaRequest, ColumnMetadata
from kairon.importer.content_importer import ContentImporter
from kairon.shared.cognition.data_objects import CognitionData
from kairon.shared.cognition.processor import CognitionDataProcessor
from kairon.shared.content_importer.content_processor import ContentImporterLogProcessor
from kairon.shared.data.constant import EVENT_STATUS
from kairon.shared.data.data_objects import BotSettings
from kairon.shared.utils import Utility


def pytest_namespace():
    return {'tmp_dir': None}


class TestContentImporter:
    @pytest.fixture(scope="class", autouse=True)
    def init(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    def test_validate_success(self):
        """
        Test case for successful validation where all rows pass validation.
        """
        BotSettings.objects().delete()
        test_file_path = "tests/testing_data/doc_content_upload"
        bot = 'test_bot'
        user = 'test_user'
        file_received = 'Salesstore.csv'
        table_name = 'test_table'
        bot_settings = BotSettings(
            bot=bot,
            user=user
        )
        bot_settings.llm_settings['enable_faq'] = True
        bot_settings.save()


        schema_request = CognitionSchemaRequest(
            metadata=[
                ColumnMetadata(column_name="order_id", data_type="int", enable_search=True, create_embeddings=True),
                ColumnMetadata(column_name="order_priority", data_type="str", enable_search=True,
                               create_embeddings=True),
                ColumnMetadata(column_name="sales", data_type="float", enable_search=True, create_embeddings=True),
                ColumnMetadata(column_name="profit", data_type="float", enable_search=True, create_embeddings=True),
            ],
            collection_name=table_name
        )

        cognition_processor = CognitionDataProcessor()
        response = cognition_processor.save_cognition_schema(
            schema_request.dict(),
            user,
            bot,
        )
        importer = ContentImporter(path= test_file_path, bot=bot, user=user, file_received=file_received,
                                   table_name=table_name)

        original_row_count, summary = importer.validate()
        assert original_row_count == 20
        assert summary == {}

    def test_validate_with_errors_and_failed_rows_csv_export(self):
        """
        Test case where validation identifies errors in the data.
        """
        test_file_path = "tests/testing_data/doc_content_upload"
        bot = 'test_bot'
        user = 'test_user'
        file_received = 'Salesstore_data_with_datatype_errors.csv'
        table_name = 'test_table'

        importer = ContentImporter(path=test_file_path, bot=bot, user=user, file_received=file_received,
                                   table_name=table_name)
        ContentImporterLogProcessor.add_log(
            bot, user, table=table_name, is_data_uploaded=True, file_received=file_received
        )
        ContentImporterLogProcessor.add_log(bot, user, event_status=EVENT_STATUS.VALIDATING.value)
        event_id = ContentImporterLogProcessor.get_event_id_for_latest_event(bot)
        original_row_count, summary = importer.validate()
        ContentImporterLogProcessor.add_log(bot, user, validation_errors=summary, status="Success",
                                            event_status=EVENT_STATUS.COMPLETED.value)

        assert original_row_count == 20
        assert summary != {}
        expected_summary = {
            'Row 4': [
                {'column_name': 'order_id', 'input': '45.09', 'status': 'Invalid DataType'},
                {'column_name': 'sales', 'input': '', 'status': 'Required Field is Empty'}
            ],
            'Row 6': [
                {'column_name': 'profit', 'input': '', 'status': 'Required Field is Empty'}
            ]
        }

        assert summary == expected_summary
        failed_rows_file = os.path.join('content_upload_summary', bot, f'failed_rows_with_errors_{event_id}.csv')
        assert os.path.exists(failed_rows_file)

    def test_validate_empty_file(self):
        """
        Test case where validation identifies errors in the data.
        """
        test_file_path = "tests/testing_data/doc_content_upload"
        bot = 'test_bot'
        user = 'test_user'
        file_received = 'Salesstore_empty_file.csv'
        table_name = 'test_table'

        importer = ContentImporter(path=test_file_path, bot=bot, user=user, file_received=file_received,
                                   table_name=table_name)
        ContentImporterLogProcessor.add_log(
            bot, user, table=table_name, is_data_uploaded=True, file_received=file_received
        )
        ContentImporterLogProcessor.add_log(bot, user, event_status=EVENT_STATUS.VALIDATING.value)
        original_row_count, summary = importer.validate()
        ContentImporterLogProcessor.add_log(bot, user, validation_errors=summary, status="Success",
                                            event_status=EVENT_STATUS.COMPLETED.value)

        assert original_row_count == 0
        assert summary == {}

    def test_import_data_success(self):
        """
        Test case for importing all data after successful validation.
        """
        test_file_path = "tests/testing_data/doc_content_upload"
        bot = 'test_bot'
        user = 'test_user'
        file_received = 'Salesstore.csv'
        table_name = 'test_table'

        importer = ContentImporter(path=test_file_path, bot=bot, user=user, file_received=file_received,
                                   table_name=table_name)

        original_row_count, summary = importer.validate()

        assert original_row_count == 20
        assert summary == {}

        importer.import_data()

        cognition_data = CognitionData.objects(bot=bot, collection=table_name)
        assert cognition_data.count() == original_row_count
        last_row = cognition_data.order_by('-_id').first()
        assert last_row["data"] == {
            'order_id': 67,
            'order_priority': "Low",
            'sales': 12.34,
            'profit': 54.98
        }

    def test_import_data_partial_success(self):
        """
        Test case where some data fails validation, ensuring only valid data is imported.
        """
        test_file_path = "tests/testing_data/doc_content_upload"
        bot = 'test_bot'
        user = 'test_user'
        file_received = 'Salesstore_data_with_datatype_errors.csv'
        table_name = 'test_table'

        importer = ContentImporter(path=test_file_path, bot=bot, user=user, file_received=file_received,
                                   table_name=table_name)
        ContentImporterLogProcessor.add_log(
            bot, user, table=table_name, is_data_uploaded=True, file_received=file_received
        )
        ContentImporterLogProcessor.add_log(bot, user, event_status=EVENT_STATUS.VALIDATING.value)
        original_row_count, summary = importer.validate()

        assert original_row_count == 20
        assert summary != {}

        importer.import_data()

        cognition_data = list(CognitionData.objects(bot=bot, collection=table_name))
        assert len(cognition_data) == original_row_count - len(summary)

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



        ContentImporterLogProcessor.add_log(bot, user, validation_errors=summary, status="Success",
                                            event_status=EVENT_STATUS.COMPLETED.value)






import io
import ujson as json
import os
from unittest import mock
from unittest.mock import patch, MagicMock
from mongoengine import connect

import pytest
from boto3 import Session
from botocore.exceptions import ClientError
from botocore.response import StreamingBody
from botocore.stub import Stubber

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.cloud.utils import CloudUtility
from kairon.shared.constants import EventClass
from kairon.shared.data.constant import TASK_TYPE, EVENT_STATUS


class TestCloudUtils:

    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()

    @pytest.fixture(autouse=True, scope="class")
    def setup(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment["database"]["url"]))
        from kairon.shared.account.processor import AccountProcessor
        AccountProcessor.load_system_properties()

    def test_file_upload(self):
        bucket_name = 'kairon'
        client = Session().client('s3')
        head_bucket_response = {'ResponseMetadata': {'RequestId': '5ZMKRRDGJ1TFZX',
                                                     'HostId': '03La8xzRzT6aKr+tlnYjo28htPIj7jCy1FUgDBWRaYOjBUquJmwvtcfw1arSEBbE1G1Q1KhhE=',
                                                     'HTTPStatusCode': 200, 'HTTPHeaders': {
                'x-amz-id-2': '03La8xzRzT6aKr+tlnYjo28htPIj7jCy1FUgDBaYOjBA8UquJmwvtcfw1arSEBbE1G1Q1KhhE=',
                'x-amz-request-id': '5ZMKRRJRD1TFZX', 'date': 'Wed, 27 Apr 2022 07:47:43 GMT',
                'x-amz-bucket-region': 'us-east-12', 'x-amz-access-point-alias': 'false',
                'content-type': 'application/xml', 'server': 'AmazonS3'}, 'RetryAttempts': 0}}
        expected_params = {'Bucket': bucket_name}
        with mock.patch("boto3.session.Session.client") as mock_session:
            mock_session.return_value = client
            with mock.patch("boto3.s3.transfer.S3Transfer.upload_file") as mock_file_upload:
                mock_file_upload.return_value = None
                with Stubber(client) as stubber:
                    stubber.add_response('head_bucket', head_bucket_response, expected_params)
                    stubber.activate()
                    url = CloudUtility.upload_file('tests/testing_data/actions/actions.yml', bucket_name, 'test/actions.yml')
                    assert url == 'https://kairon.s3.amazonaws.com/test/actions.yml'

    def test_download_file_to_memory(self):
        bucket = "test-bucket"
        file_key = "test/file.txt"
        expected_content = b"downloaded content"
        fake_s3_client = mock.Mock()
        def fake_download_fileobj(bkt, key, buffer):
            buffer.write(expected_content)
        fake_s3_client.download_fileobj.side_effect = fake_download_fileobj
        with mock.patch("boto3.session.Session.client") as mock_client:
            mock_client.return_value = fake_s3_client
            result_buffer = CloudUtility.download_file_to_memory(bucket, file_key)
            assert isinstance(result_buffer, io.BytesIO)
            result_buffer.seek(0)
            content = result_buffer.read()
            assert content == expected_content

    @patch("kairon.shared.cloud.utils.Session")
    @patch.object(CloudUtility, "_CloudUtility__check_bucket_exist", autospec=True)
    @patch("kairon.shared.cloud.utils.Utility.check_empty_string", autospec=True)
    def test_upload_file_bytes_bucket_exists(
            self, mock_check_empty, mock_check_bucket_exist, mock_session_class
    ):
        file_bytes = b"hello world"
        bucket = "my-bucket"
        key = "folder/file.txt"
        mock_s3 = MagicMock()
        mock_session_class.return_value.client.return_value = mock_s3

        mock_check_bucket_exist.return_value = True
        mock_check_empty.return_value = False

        url = CloudUtility.upload_file_bytes(file_bytes, bucket, key)

        mock_s3.create_bucket.assert_not_called()
        args, kwargs = mock_s3.upload_fileobj.call_args
        bio_passed, bucket_passed, key_passed = args
        assert isinstance(bio_passed, io.BytesIO)
        assert bucket_passed == bucket
        assert key_passed == key

        assert url == f"https://{bucket}.s3.amazonaws.com/{key}"

    @patch("kairon.shared.cloud.utils.Session")
    @patch.object(CloudUtility, "_CloudUtility__check_bucket_exist", autospec=True)
    @patch("kairon.shared.cloud.utils.Utility.check_empty_string", autospec=True)
    def test_upload_file_bytes_bucket_not_exists(
            self, mock_check_empty, mock_check_bucket_exist, mock_session_class
    ):
        file_bytes = b"data"
        bucket = "new-bucket"
        key = "file.bin"
        mock_s3 = MagicMock()
        mock_session_class.return_value.client.return_value = mock_s3

        mock_check_bucket_exist.return_value = False
        mock_check_empty.return_value = False

        url = CloudUtility.upload_file_bytes(file_bytes, bucket, key)

        mock_s3.create_bucket.assert_called_once_with(Bucket=bucket)
        mock_s3.upload_fileobj.assert_called_once()
        assert url == f"https://{bucket}.s3.amazonaws.com/{key}"

    @patch("kairon.shared.cloud.utils.Session")
    @patch.object(CloudUtility, "_CloudUtility__check_bucket_exist", autospec=True)
    @patch("kairon.shared.cloud.utils.Utility.check_empty_string", autospec=True)
    def test_upload_file_bytes_empty_filename_raises(
            self, mock_check_empty, mock_check_bucket_exist, mock_session_class
    ):
        file_bytes = b"bytes"
        bucket = "bucket"
        mock_check_bucket_exist.return_value = True
        mock_check_empty.return_value = True
        mock_session_class.return_value.client.return_value = MagicMock()

        with pytest.raises(AppException) as excinfo:
            CloudUtility.upload_file_bytes(file_bytes, bucket, output_filename="")

        assert "Output filename must be provided" in str(excinfo.value)

    def test_file_upload_bucket_not_exists(self):
        bucket_name = 'kairon'
        head_bucket_response = {'Error': {'Code': '400', 'Message': 'Bad Request'},
                                'ResponseMetadata': {'RequestId': 'BQFVQHD1KSD5V6RZ',
                                                     'HostId': 't2uudD7x2V+rRHO4dp2XBqdmAOaWwlnsII7gs1JbYcrntVKRaZSpHxNPJEww+s5dCzCQOg2uero=',
                                                     'HTTPStatusCode': 400,
                                                     'HTTPHeaders': {'x-amz-bucket-region': 'us-east-1',
                                                                     'x-amz-request-id': 'BQFVQHD1KSD5V6RZ',
                                                                     'x-amz-id-2': 't2uudD7x2V+rRHO4dp2XBqdmAOaWwlnsII7gs1JbYcrntVKRaZSpHxNPJEww+s5dCzCQOg2uero=',
                                                                     'content-type': 'application/xml',
                                                                     'date': 'Wed, 27 Apr 2022 08:53:05 GMT',
                                                                     'server': 'AmazonS3', 'connection': 'close'},
                                                     'RetryAttempts': 3}}
        create_bucket_response = {'ResponseMetadata': {'RequestId': '6SRCQY7F48PH6RYJ',
                                                     'HostId': 'LEm4fLPe3HUsVjviOmImZa3eu/tLEWGzvw00jP+JV/4aGbEw0YEC2OGoqjgSmx7+1h6VXIKOuYA=',
                                                     'HTTPStatusCode': 200, 'HTTPHeaders': {
                'x-amz-id-2': 'LEm4fLPe3HUsVjviOmImZa3eu/tLEWGzvw00jP+JV/4aGbEw0YEC2OGoqjgSmx7+1h6VXIKOuYA=',
                'x-amz-request-id': '6SRCQY7F48PH6RYJ', 'date': 'Wed, 27 Apr 2022 08:04:51 GMT',
                'location': '/kairon-asdfgh12345678', 'server': 'AmazonS3', 'content-length': '0'}, 'RetryAttempts': 0},
                                'Location': bucket_name}

        def __mock_make_api_call(self, operation_name, kwargs):
            if operation_name == 'CreateBucket':
                return create_bucket_response
            elif operation_name == 'HeadBucket':
                raise ClientError(head_bucket_response, operation_name)
            elif operation_name == 'PutObject':
                return None

        with mock.patch('botocore.client.BaseClient._make_api_call', new=__mock_make_api_call):
            url = CloudUtility.upload_file('tests/testing_data/actions/actions.yml', bucket_name, 'test/actions.yml')
            assert url == 'https://kairon.s3.amazonaws.com/test/actions.yml'

    def test_file_upload_create_bucket_failed(self):
        bucket_name = 'kairon'
        head_bucket_response = {'ResponseMetadata': {'RequestId': 'BQFVQHD1KSD5V6RZ',
                                                     'HostId': 't2uudD7x2V+rRHO4dp2XBqdmAOaWwlnsII7gs1JbYcrntVKRaZSpHxNPJEww+s5dCzCQOg2uero=',
                                                     'HTTPStatusCode': 400,
                                                     'HTTPHeaders': {'x-amz-bucket-region': 'us-east-1',
                                                                     'x-amz-request-id': 'BQFVQHD1KSD5V6RZ',
                                                                     'x-amz-id-2': 't2uudD7x2V+rRHO4dp2XBqdmAOaWwlnsII7gs1JbYcrntVKRaZSpHxNPJEww+s5dCzCQOg2uero=',
                                                                     'content-type': 'application/xml',
                                                                     'date': 'Wed, 27 Apr 2022 08:53:05 GMT',
                                                                     'server': 'AmazonS3', 'connection': 'close'},
                                                     'RetryAttempts': 3}}
        create_bucket_response = {'ResponseMetadata': {'RequestId': 'GTR1G7ZPA5YQFNH',
                                                     'HostId': 'H5kWchdP1vqIcAI/WJdZXQ2h/fZ/oKjQpK75hmnX4bsa5aQBYvXEOw7HUt//a6jBQeFZlmAyE=',
                                                     'HTTPStatusCode': 400,
                                                     'HTTPHeaders': {'x-amz-request-id': 'GTR1G7ZP5YQRFNH',
                                                                     'x-amz-id-2': 'H5kWchdP1vqIcAI/WJdZXQ2h/foKjQpKo575hmnX4bsa5aQBYvXEOw7HUt//a6jBQeFZlmAyE=',
                                                                     'content-type': 'application/xml',
                                                                     'transfer-encoding': 'chunked',
                                                                     'date': 'Wed, 27 Apr 2022 08:08:52 GMT',
                                                                     'server': 'AmazonS3', 'connection': 'close'},
                                                     'RetryAttempts': 1}}

        def __mock_make_api_call(self, operation_name, kwargs):
            if operation_name == 'CreateBucket':
                raise ClientError(create_bucket_response, operation_name)
            elif operation_name == 'HeadBucket':
                raise ClientError(head_bucket_response, operation_name)

        with mock.patch('botocore.client.BaseClient._make_api_call', new=__mock_make_api_call):
            with pytest.raises(ClientError):
                CloudUtility.upload_file('tests/testing_data/actions/actions.yml', bucket_name, 'test/actions.yml')

    def test_delete_file(self):
        bucket_name = 'kairon'
        delete_object_response = {'ResponseMetadata': {'RequestId': 'BQFVQHD1KSD5V6RZ',
                                                       'HostId': 't2uudD7x2V+rRHO4dp2XBqdmAOaWwlnsII7gs1JbYcrntVKRaZSpHxNPJEww+s5dCzCQOg2uero=',
                                                       'HTTPStatusCode': 204,
                                                       'HTTPHeaders': {'x-amz-bucket-region': 'us-east-1',
                                                                       'x-amz-request-id': 'BQFVQHD1KSD5V6RZ',
                                                                       'x-amz-id-2': 't2uudD7x2V+rRHO4dp2XBqdmAOaWwlnsII7gs1JbYcrntVKRaZSpHxNPJEww+s5dCzCQOg2uero=',
                                                                       'content-type': 'application/xml',
                                                                       'date': 'Wed, 27 Apr 2022 08:53:05 GMT',
                                                                       'server': 'AmazonS3', 'connection': 'close'},
                                                       'RetryAttempts': 0}}

        def __mock_make_api_call(self, operation_name, kwargs):
            if operation_name == 'DeleteObject':
                return delete_object_response

        with mock.patch('botocore.client.BaseClient._make_api_call', new=__mock_make_api_call):
            CloudUtility.delete_file(bucket_name, 'tests/testing_data/actions/actions.yml')

    def test_delete_file_not_exists(self):
        bucket_name = 'kairon'
        delete_object_response = {'ResponseMetadata': {'RequestId': 'BQFVQHD1KSD5V6RZ',
                                                       'HostId': 't2uudD7x2V+rRHO4dp2XBqdmAOaWwlnsII7gs1JbYcrntVKRaZSpHxNPJEww+s5dCzCQOg2uero=',
                                                       'HTTPStatusCode': 204,
                                                       'HTTPHeaders': {'x-amz-bucket-region': 'us-east-1',
                                                                       'x-amz-request-id': 'BQFVQHD1KSD5V6RZ',
                                                                       'x-amz-id-2': 't2uudD7x2V+rRHO4dp2XBqdmAOaWwlnsII7gs1JbYcrntVKRaZSpHxNPJEww+s5dCzCQOg2uero=',
                                                                       'content-type': 'application/xml',
                                                                       'date': 'Wed, 27 Apr 2022 08:53:05 GMT',
                                                                       'server': 'AmazonS3', 'connection': 'close'},
                                                       'RetryAttempts': 0}}

        def __mock_make_api_call(self, operation_name, kwargs):
            if operation_name == 'DeleteObject':
                return delete_object_response

        with mock.patch('botocore.client.BaseClient._make_api_call', new=__mock_make_api_call):
            CloudUtility.delete_file(bucket_name, 'tests/testing_data/actions/actions.yml')

    def test_trigger_lambda_model_training_executor_log_when_success(self):
        mock_env = Utility.environment.copy()
        mock_env['events']['executor']['type'] = 'aws_lambda'
        mock_env['events']['task_definition'][EventClass.model_training] = 'train-model'
        response_payload = json.dumps({'response': "Query submittes"}).encode("utf-8")
        response = {'StatusCode': 200, 'FunctionError': 'Unhandled',
                    'LogResult': 'U1RBUlQgUmVxdWVzdElkOiBlOTJiMWNjMC02MjcwLTQ0OWItOA3O=',
                    'ExecutedVersion': '$LATEST',
                    'Payload': StreamingBody(io.BytesIO(response_payload),
                                             len(response_payload))}

        def __mock_make_api_call(self, operation_name, kwargs):
            assert kwargs == {'FunctionName': 'train-model', 'InvocationType': 'RequestResponse', 'LogType': 'Tail',
                              'Payload': b'[{"name":"BOT","value":"test_bot"},{"name":"USER","value":"test_user"}]'}
            if operation_name == 'Invoke':
                return response

            raise Exception("Invalid operation_name")

        with patch.dict(Utility.environment, mock_env):
            with mock.patch('botocore.client.BaseClient._make_api_call', new=__mock_make_api_call):
                resp = CloudUtility.trigger_lambda(EventClass.model_training,
                                                   [{"name": "BOT", "value": "test_bot"},
                                                    {"name": "USER", "value": "test_user"}],
                                                   task_type=TASK_TYPE.EVENT.value)
                assert resp == response

        from kairon.shared.events.data_objects import ExecutorLogs
        logs = ExecutorLogs.objects(task_type='Event',
                                    data=[{"name": "BOT", "value": "test_bot"}, {"name": "USER", "value": "test_user"}])
        log = logs[0].to_mongo().to_dict()
        assert log['task_type'] == 'Event'
        assert log['event_class'] == 'model_training'
        assert log['data'] == [{"name": "BOT", "value": "test_bot"}, {"name": "USER", "value": "test_user"}]
        assert log['status'] == 'Completed'
        assert log['response'] == {
            'StatusCode': 200,
            'FunctionError': 'Unhandled',
            'LogResult': 'U1RBUlQgUmVxdWVzdElkOiBlOTJiMWNjMC02MjcwLTQ0OWItOA3O=',
            'ExecutedVersion': '$LATEST',
            'Payload': {'response': 'Query submittes'}
        }
        assert log['from_executor'] is False
        assert log['elapsed_time']

    def test_trigger_lambda_model_training_executor_log_when_failed(self):
        mock_env = Utility.environment.copy()
        mock_env['events']['executor']['type'] = 'aws_lambda'
        mock_env['events']['task_definition'][EventClass.model_training] = 'train-model'
        response_payload = json.dumps({'response': "Query submittes"}).encode("utf-8")
        response = {'StatusCode': 200, 'FunctionError': 'Unhandled',
                    'LogResult': 'U1RBUlQgUmVxdWVzdElkOiBlOTJiMWNjMC02MjcwLTQ0OWItOA3O=',
                    'ExecutedVersion': '$LATEST',
                    'Payload': StreamingBody(io.BytesIO(response_payload),
                                             len(response_payload))}

        def __mock_make_api_call(self, operation_name, kwargs):
            assert kwargs == {'FunctionName': 'train-model', 'InvocationType': 'RequestResponse', 'LogType': 'Tail',
                              'Payload': b'[{"name":"BOT","value":"test_bot"},{"name":"USER","value":"test_user"}]'}

            raise Exception("Parameter validation failed: Invalid type for parameter FunctionName, value: None, "
                            "type: <class 'NoneType'>, valid types: <class 'str'>")

        with patch.dict(Utility.environment, mock_env):
            with mock.patch('botocore.client.BaseClient._make_api_call', new=__mock_make_api_call):
                with pytest.raises(AppException):
                    CloudUtility.trigger_lambda(EventClass.model_training,
                                                [{"name": "BOT", "value": "test_bot"},
                                                 {"name": "USER", "value": "test_user"}],
                                                task_type=TASK_TYPE.EVENT.value)

        from kairon.shared.events.data_objects import ExecutorLogs
        logs = ExecutorLogs.objects(task_type='Event',
                                    data=[{"name": "BOT", "value": "test_bot"}, {"name": "USER", "value": "test_user"}])
        log = logs[1].to_mongo().to_dict()
        pytest.executor_log_id = log['executor_log_id']
        assert log['task_type'] == 'Event'
        assert log['event_class'] == 'model_training'
        assert log['data'] == [{"name": "BOT", "value": "test_bot"}, {"name": "USER", "value": "test_user"}]
        assert log['status'] == 'Fail'
        assert log['response'] == {}
        assert log['from_executor'] is False
        assert log['exception'] == ("Parameter validation failed: Invalid type for parameter FunctionName, "
                                    "value: None, type: <class 'NoneType'>, valid types: <class 'str'>")
        assert log['elapsed_time']

    def test_trigger_lambda_model_training_executor_log_when_already_exist(self):
        mock_env = Utility.environment.copy()
        mock_env['events']['executor']['type'] = 'aws_lambda'
        mock_env['events']['task_definition'][EventClass.model_training] = 'train-model'
        response_payload = json.dumps({'response': "Query submittes"}).encode("utf-8")
        response = {'StatusCode': 200, 'FunctionError': 'Unhandled',
                    'LogResult': 'U1RBUlQgUmVxdWVzdElkOiBlOTJiMWNjMC02MjcwLTQ0OWItOA3O=',
                    'ExecutedVersion': '$LATEST',
                    'Payload': StreamingBody(io.BytesIO(response_payload),
                                             len(response_payload))}

        def __mock_make_api_call(self, operation_name, kwargs):
            assert kwargs == {'FunctionName': 'train-model', 'InvocationType': 'RequestResponse', 'LogType': 'Tail',
                              'Payload': b'[{"name":"BOT","value":"test_bot"},{"name":"USER","value":"test_user"}]'}
            if operation_name == 'Invoke':
                return response

            raise Exception("Invalid operation_name")

        with patch.dict(Utility.environment, mock_env):
            with mock.patch('botocore.client.BaseClient._make_api_call', new=__mock_make_api_call):
                resp = CloudUtility.trigger_lambda(EventClass.model_training,
                                                   [{"name": "BOT", "value": "test_bot"},
                                                    {"name": "USER", "value": "test_user"}],
                                                   task_type=TASK_TYPE.EVENT.value)
                assert resp == response

        from kairon.shared.events.data_objects import ExecutorLogs
        from kairon.events.executors.base import ExecutorBase
        executor = ExecutorBase()
        executor.log_task(event_class=EventClass.model_training.value, task_type=TASK_TYPE.EVENT.value,
                          data=[{"name": "BOT", "value": "test_bot"}, {"name": "USER", "value": "test_user"}],
                          executor_log_id=pytest.executor_log_id, status=EVENT_STATUS.INITIATED.value)

        logs = ExecutorLogs.objects(executor_log_id=pytest.executor_log_id)
        assert len(logs) == 2
        log = logs[1].to_mongo().to_dict()
        assert log['task_type'] == 'Event'
        assert log['event_class'] == 'model_training'
        assert log['data'] == [{"name": "BOT", "value": "test_bot"}, {"name": "USER", "value": "test_user"}]
        assert log['status'] == 'Initiated'
        assert log['response'] == {}
        assert log['executor_log_id'] == pytest.executor_log_id

    def test_trigger_lambda_model_training(self):
        mock_env = Utility.environment.copy()
        mock_env['events']['executor']['type'] = 'aws_lambda'
        mock_env['events']['task_definition'][EventClass.model_training] = 'train-model'
        response_payload = json.dumps({'response': "Query submittes"}).encode("utf-8")
        response = {'StatusCode': 200, 'FunctionError': 'Unhandled',
                            'LogResult': 'U1RBUlQgUmVxdWVzdElkOiBlOTJiMWNjMC02MjcwLTQ0OWItOA3O=',
                            'ExecutedVersion': '$LATEST',
                            'Payload': StreamingBody(io.BytesIO(response_payload),
                                                     len(response_payload))}

        def __mock_make_api_call(self, operation_name, kwargs):
            assert kwargs == {'FunctionName': 'train-model', 'InvocationType': 'RequestResponse', 'LogType': 'Tail',
                              'Payload': b'[{"name":"BOT","value":"test"},{"name":"USER","value":"test_user"}]'}
            if operation_name == 'Invoke':
                return response

            raise Exception("Invalid operation_name")

        with patch.dict(Utility.environment, mock_env):
            with mock.patch('botocore.client.BaseClient._make_api_call', new=__mock_make_api_call):
                resp = CloudUtility.trigger_lambda(EventClass.model_training,
                                                   [{"name": "BOT", "value": "test"},
                                                    {"name": "USER", "value": "test_user"}],
                                                   task_type=TASK_TYPE.EVENT.value
                                                   )
                assert resp == response

    def test_trigger_lambda_model_testing(self):
        mock_env = Utility.environment.copy()
        mock_env['events']['executor']['type'] = 'aws_lambda'
        mock_env['events']['task_definition'][EventClass.model_testing] = 'test-model'
        response_payload = json.dumps({'response': "Query submittes"}).encode("utf-8")
        response = {'StatusCode': 200, 'FunctionError': 'Unhandled',
                            'LogResult': 'U1RBUlQgUmVxdWVzdElkOiBlOTJiMWNjMC02MjcwLTQ0OWItOA3O=',
                            'ExecutedVersion': '$LATEST',
                            'Payload': StreamingBody(io.BytesIO(response_payload),
                                                     len(response_payload))}

        def __mock_make_api_call(self, operation_name, kwargs):
            assert kwargs == {'FunctionName': 'test-model', 'InvocationType': 'RequestResponse', 'LogType': 'Tail',
                              'Payload': b'[{"name":"BOT","value":"test"},{"name":"USER","value":"test_user"}]'}
            if operation_name == 'Invoke':
                return response

            raise Exception("Invalid operation_name")

        with patch.dict(Utility.environment, mock_env):
            with mock.patch('botocore.client.BaseClient._make_api_call', new=__mock_make_api_call):
                resp = CloudUtility.trigger_lambda(EventClass.model_testing,
                                                   [{"name": "BOT", "value": "test"},
                                                    {"name": "USER", "value": "test_user"}],
                                                   task_type=TASK_TYPE.EVENT.value
                                                   )
                assert resp == response

    def test_trigger_lambda_data_importer(self):
        mock_env = Utility.environment.copy()
        mock_env['events']['executor']['type'] = 'aws_lambda'
        mock_env['events']['task_definition'][EventClass.data_importer] = 'data-importer'
        response_payload = json.dumps({'response': "Query submittes"}).encode("utf-8")
        response = {'StatusCode': 200, 'FunctionError': 'Unhandled',
                    'LogResult': 'U1RBUlQgUmVxdWVzdElkOiBlOTJiMWNjMC02MjcwLTQ0OWItOA3O=',
                    'ExecutedVersion': '$LATEST',
                    'Payload': StreamingBody(io.BytesIO(response_payload),
                                             len(response_payload))}

        def __mock_make_api_call(self, operation_name, kwargs):
            assert kwargs == {'FunctionName': 'data-importer', 'InvocationType': 'RequestResponse', 'LogType': 'Tail',
                              'Payload': b'[{"name":"BOT","value":"test"},{"name":"USER","value":"test_user"}]'}
            if operation_name == 'Invoke':
                return response

            raise Exception("Invalid operation_name")

        with patch.dict(Utility.environment, mock_env):
            with mock.patch('botocore.client.BaseClient._make_api_call', new=__mock_make_api_call):
                resp = CloudUtility.trigger_lambda(EventClass.data_importer,
                                                   [{"name": "BOT", "value": "test"},
                                                    {"name": "USER", "value": "test_user"}],
                                                   task_type=TASK_TYPE.EVENT.value)
                assert resp == response

    def test_trigger_lambda_public_search(self):
        mock_env = Utility.environment.copy()
        mock_env['events']['executor']['type'] = 'aws_lambda'
        mock_env['events']['task_definition'][EventClass.web_search] = 'public_search'
        response_payload = json.dumps({'response': "Query submittes"}).encode("utf-8")
        response = {'StatusCode': 200, 'FunctionError': 'Unhandled',
                    'LogResult': 'U1RBUlQgUmVxdWVzdElkOiBlOTJiMWNjMC02MjcwLTQ0OWItOA3O=',
                    'ExecutedVersion': '$LATEST',
                    'Payload': StreamingBody(io.BytesIO(response_payload),
                                             len(response_payload))}

        def __mock_make_api_call(self, operation_name, kwargs):
            assert kwargs == {'FunctionName': 'public_search', 'InvocationType': 'RequestResponse', 'LogType': 'Tail',
                              'Payload': b'{"text":"demo","site":"www.google.com","topn":3}'}
            if operation_name == 'Invoke':
                return response

            raise Exception("Invalid operation_name")

        with patch.dict(Utility.environment, mock_env):
            with mock.patch('botocore.client.BaseClient._make_api_call', new=__mock_make_api_call):
                resp = CloudUtility.trigger_lambda(EventClass.web_search,
                                                   {"text": "demo", "site": "www.google.com", "topn": 3})
                assert resp == response

    def test_trigger_lambda_delete_history(self):
        mock_env = Utility.environment.copy()
        mock_env['events']['executor']['type'] = 'aws_lambda'
        mock_env['events']['task_definition'][EventClass.delete_history] = 'delete-history'
        response_payload = json.dumps({'response': "Query submittes"}).encode("utf-8")
        response = {'StatusCode': 200, 'FunctionError': 'Unhandled',
                    'LogResult': 'U1RBUlQgUmVxdWVzdElkOiBlOTJiMWNjMC02MjcwLTQ0OWItOA3O=',
                    'ExecutedVersion': '$LATEST',
                    'Payload': StreamingBody(io.BytesIO(response_payload),
                                             len(response_payload))}

        def __mock_make_api_call(self, operation_name, kwargs):
            assert kwargs == {'FunctionName': 'delete-history', 'InvocationType': 'RequestResponse', 'LogType': 'Tail',
                              'Payload': b'[{"name":"BOT","value":"test"},{"name":"USER","value":"test_user"}]'}
            if operation_name == 'Invoke':
                return response

            raise Exception("Invalid operation_name")

        with patch.dict(Utility.environment, mock_env):
            with mock.patch('botocore.client.BaseClient._make_api_call', new=__mock_make_api_call):
                resp = CloudUtility.trigger_lambda(EventClass.delete_history,
                                                   [{"name": "BOT", "value": "test"},
                                                    {"name": "USER", "value": "test_user"}],
                                                   task_type=TASK_TYPE.EVENT.value)
                assert resp == response

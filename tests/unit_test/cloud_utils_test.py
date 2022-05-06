from unittest import mock
import pytest
from boto3 import Session
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from kairon.shared.cloud.utils import CloudUtility


class TestCloudUtils:

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
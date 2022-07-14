import os
import re
from io import BytesIO
from unittest.mock import patch

import pytest
from boto3 import Session
from botocore.exceptions import ClientError
from fastapi import UploadFile
from mongoengine import connect, DoesNotExist

from kairon.shared.utils import Utility
from kairon.exceptions import AppException
from kairon.shared.data.assets_processor import AssetsProcessor
from kairon.shared.data.data_objects import BotAssets


class TestAssetsProcessor:

    @pytest.fixture(scope='session', autouse=True)
    def init(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    @pytest.mark.asyncio
    async def test_add_asset(self, monkeypatch):
        bot = "test"
        user = "test_user"
        asset_type = "bot_icon"
        file_path = 'tests/testing_data/yml_training_files/config.yml'
        monkeypatch.setitem(Utility.environment['storage']['assets'], 'allowed_extensions', ['.yml'])
        file = UploadFile(filename="file.yml", file=BytesIO(open(file_path, 'rb').read()))
        with patch("boto3.session.Session.client", autospec=True):
            url = await AssetsProcessor.add_asset(bot, user, file, asset_type)
        asset = BotAssets.objects(asset_type=asset_type, bot=bot, user=user, status=True).get()
        assert asset.path == 'application/test/bot_icon.yml'
        assert asset.url == url

    @pytest.mark.asyncio
    async def test_add_asset_no_type(self):
        bot = "test"
        user = "test_user"
        file_path = 'tests/testing_data/yml_training_files/config.yml'
        file = UploadFile(filename="file.yml", file=BytesIO(open(file_path, 'rb').read()))
        with pytest.raises(AppException, match="asset_type is required"):
            await AssetsProcessor.add_asset(bot, user, file, " ")

    @pytest.mark.asyncio
    async def test_add_asset_not_allowed(self):
        bot = "test"
        user = "test_user"
        asset_type = "bot_icon"
        file_path = 'tests/testing_data/yml_training_files/config.yml'
        file = UploadFile(filename="file.yml", file=BytesIO(open(file_path, 'rb').read()))
        with pytest.raises(AppException, match=re.escape(f'Only {Utility.environment["storage"]["assets"].get("allowed_extensions")} type files allowed')):
            await AssetsProcessor.add_asset(bot, user, file, "bot_icon")
        assert BotAssets.objects(asset_type=asset_type, bot=bot, user=user, status=True).get()

    @pytest.mark.asyncio
    async def test_add_asset_already_exists(self, monkeypatch):
        bot = "test"
        user = "test_user"
        asset_type = "bot_icon"
        file_path = 'tests/testing_data/yml_training_files/config.yml'
        monkeypatch.setitem(Utility.environment['storage']['assets'], 'allowed_extensions', ['.yml'])
        file = UploadFile(filename="file.yml", file=BytesIO(open(file_path, 'rb').read()))
        with patch("boto3.session.Session.client", autospec=True):
            url = await AssetsProcessor.add_asset(bot, user, file, asset_type)
        asset = BotAssets.objects(asset_type=asset_type, bot=bot, user=user, status=True).get()
        assert asset.path == 'application/test/bot_icon.yml'
        assert asset.url == url

    @pytest.mark.asyncio
    async def test_add_asset_upload_failed(self, monkeypatch):
        bot = "test"
        user = "test_user"
        asset_type = "bot_icon"
        file_path = 'tests/testing_data/yml_training_files/config.yml'
        monkeypatch.setitem(Utility.environment['storage']['assets'], 'allowed_extensions', ['.yml'])
        file = UploadFile(filename="file.yml", file=BytesIO(open(file_path, 'rb').read()))

        def __mock_upload_error(*args, **kwargs):
            api_resp = {'ResponseMetadata': {'RequestId': 'BQFVQHD1KSD5V6RZ',
                                                     'HostId': 't2uudD7x2V+rRHO4dp2XBqdmAOaWwlnsII7gs1JbYcrntVKRaZSpHxNPJEww+s5dCzCQOg2uero=',
                                                     'HTTPStatusCode': 400,
                                                     'HTTPHeaders': {'x-amz-bucket-region': 'us-east-1',
                                                                     'x-amz-request-id': 'BQFVQHD1KSD5V6RZ',
                                                                     'x-amz-id-2': 't2uudD7x2V+rRHO4dp2XBqdmAOaWwlnsII7gs1JbYcrntVKRaZSpHxNPJEww+s5dCzCQOg2uero=',
                                                                     'content-type': 'application/xml',
                                                                     'date': 'Wed, 27 Apr 2022 08:53:05 GMT',
                                                                     'server': 'AmazonS3', 'connection': 'close'},
                                                     'RetryAttempts': 3}}
            raise ClientError(api_resp, "HeadBucket")

        with patch("kairon.shared.cloud.utils.CloudUtility.upload_file", autospec=True) as mock_upload:
            mock_upload.side_effect = __mock_upload_error
            with pytest.raises(AppException, match="File upload failed"):
                await AssetsProcessor.add_asset(bot, user, file, asset_type)

    def test_list_assets(self):
        bot = "test"
        assert list(AssetsProcessor.list_assets(bot)) == [{
            "asset_type": "bot_icon", "url": 'https://ui-bucket.s3.amazonaws.com/application/test/bot_icon.yml'}]

    def test_delete_asset_not_exists(self):
        bot = "test"
        user = "test_user"
        asset_type = "user_icon"

        with pytest.raises(AppException, match="Asset does not exists"):
            AssetsProcessor.delete_asset(bot, user, asset_type)

        bot = "test_bot"
        asset_type = "bot_icon"
        with pytest.raises(AppException, match="Asset does not exists"):
            AssetsProcessor.delete_asset(bot, user, asset_type)

    def test_delete_asset(self):
        bot = "test"
        user = "test_user"
        asset_type = "bot_icon"
        with patch("boto3.session.Session.client", autospec=True):
            AssetsProcessor.delete_asset(bot, user, asset_type)
        with pytest.raises(DoesNotExist):
            BotAssets.objects(asset_type=asset_type, bot=bot, user=user, status=True).get()

    def test_list_assets_empty(self):
        bot = "test"
        assert list(AssetsProcessor.list_assets(bot)) == []

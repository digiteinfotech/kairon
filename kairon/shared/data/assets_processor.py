import os
import tempfile
from datetime import datetime
from typing import Text

from fastapi import File
from mongoengine import DoesNotExist

from kairon.shared.utils import Utility
from kairon.exceptions import AppException
from kairon.shared.data.data_objects import BotAssets


class AssetsProcessor:

    @staticmethod
    async def add_asset(bot: Text, user: Text, file: File, asset_type: Text):
        if Utility.check_empty_string(asset_type):
            raise AppException("asset_type is required")
        temp_path = tempfile.mkdtemp()
        path = os.path.join(temp_path, file.filename)
        Utility.write_to_file(path, await file.read())
        url, path = Utility.upload_bot_assets_to_s3(bot, asset_type, path)
        if Utility.is_exist(BotAssets, raise_error=False, asset_type=asset_type, bot=bot, status=True):
            asset = BotAssets.objects(asset_type=asset_type, bot=bot, user=user).get()
        else:
            asset = BotAssets(asset_type=asset_type, path=path, url=url, bot=bot)
        asset.user = user
        asset.update_timestamp = datetime.utcnow()
        asset.save()
        return url

    @staticmethod
    def delete_asset(bot: Text, user: Text, asset_type: Text):
        try:
            asset = BotAssets.objects(asset_type=asset_type, bot=bot, status=True).get()
            Utility.delete_bot_assets_on_s3(asset.path)
            asset.status = False
            asset.user = user
            asset.timestamp = datetime.utcnow()
            asset.save()
        except DoesNotExist:
            raise AppException("Asset does not exists")

    @staticmethod
    def list_assets(bot: Text):
        for asset in BotAssets.objects(bot=bot, status=True):
            asset = asset.to_mongo().to_dict()
            asset.pop('_id')
            asset.pop('status')
            asset.pop('bot')
            asset.pop('user')
            asset.pop('timestamp')
            asset.pop('path')
            yield asset

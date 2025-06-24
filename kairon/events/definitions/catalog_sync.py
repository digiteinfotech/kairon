import json
from typing import Text
from kairon import Utility
from loguru import logger

from kairon.catalog_sync.definitions.factory import CatalogSyncFactory
from kairon.events.definitions.base import EventsBase
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.catalog_sync.data_objects import CatalogSyncLogs
from kairon.shared.constants import EventClass
from kairon.shared.data.constant import SyncType, SYNC_STATUS
from kairon.shared.catalog_sync.catalog_sync_log_processor import CatalogSyncLogProcessor


class CatalogSync(EventsBase):
    """
    Validates and processes data from catalog (e.g., Petpooja) before importing it
    to knowledge vault and meta
    """

    def __init__(self, bot: Text, user: Text, provider: Text, **kwargs):
        """
        Initialise event.
        """
        sync_class = CatalogSyncFactory.get_instance(provider)
        self.catalog_sync = sync_class(
            bot=bot,
            user=user,
            provider=provider,
            sync_type=kwargs.get("sync_type", SyncType.item_toggle),
            token=kwargs.get("token", "")
        )
        self.catalog_sync.data = []

    async def validate(self, **kwargs):
        """
        Validates if an event is already running for that particular bot and
        checks if the event trigger limit has been exceeded.
        Then, preprocesses the received request
        """
        request = kwargs.get("request_body")
        self.catalog_sync.data = request
        is_event_data = await self.catalog_sync.validate(request_body = request)
        return is_event_data

    def enqueue(self, **kwargs):
        """
        Send event to event server
        """
        try:
            log_id = CatalogSyncLogProcessor.add_log(self.catalog_sync.bot, self.catalog_sync.user, self.catalog_sync.provider, self.catalog_sync.sync_type, sync_status=SYNC_STATUS.ENQUEUED.value)
            payload = {
                'bot': self.catalog_sync.bot,
                'user': self.catalog_sync.user,
                'provider': self.catalog_sync.provider,
                'sync_type': self.catalog_sync.sync_type,
                'token': self.catalog_sync.token,
                'log_id': log_id
            }
            Utility.request_event_server(EventClass.catalog_integration, payload)
        except Exception as e:
            CatalogSyncLogProcessor.delete_enqueued_event_log(self.catalog_sync.bot)
            raise e

    async def execute(self, **kwargs):
        """
        Execute the document content import event.
        """
        AccountProcessor.load_system_properties()
        log_id = kwargs.get("log_id")

        if not log_id:
            logger.error("Missing log_id in event payload")
            return

        try:
            log_doc = CatalogSyncLogs.objects(id=log_id).get()
            self.catalog_sync.data = log_doc.raw_payload
            initiate_import, stale_primary_keys= await self.catalog_sync.preprocess(request_body=self.catalog_sync.data)
            await self.catalog_sync.execute(data=self.catalog_sync.data, initiate_import = initiate_import,stale_primary_keys = stale_primary_keys)
        except Exception as e:
            logger.error(str(e))
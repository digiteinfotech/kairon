from typing import Text

from dotenv import set_key

from kairon import Utility
from loguru import logger

from kairon.catalog_sync.definitions.base import CatalogSyncBase
from kairon.exceptions import AppException
from kairon.meta.processor import MetaProcessor
from kairon.shared.cognition.processor import CognitionDataProcessor
from kairon.shared.constants import EventClass
from kairon.shared.data.constant import SyncType, SYNC_STATUS
from kairon.shared.data.data_objects import POSIntegrations, BotSyncConfig
from kairon.shared.catalog_sync.catalog_sync_log_processor import CatalogSyncLogProcessor
from kairon.shared.utils import MailUtility


class PetpoojaSync(CatalogSyncBase):
    """
    Validates and processes data from catalog (e.g., Petpooja) before importing it
    to knowledge vault and meta
    """

    def __init__(self, bot: Text, user: Text, provider: Text, **kwargs):
        """
        Initialise event.
        """
        self.bot = bot
        self.user = user
        self.provider = provider
        self.token = kwargs.get("token", "")
        self.sync_type = kwargs.get("sync_type", SyncType.item_toggle)
        self.data = []

    async def validate(self, **kwargs):
        """
        Validates if an event is already running for that particular bot and
        checks if the event trigger limit has been exceeded.
        Then, preprocesses the received request
        """
        try:
            request = kwargs.get("request_body")
            CatalogSyncLogProcessor.is_sync_in_progress(self.bot)
            CatalogSyncLogProcessor.is_limit_exceeded(self.bot)
            CatalogSyncLogProcessor.add_log(self.bot, self.user, self.provider, self.sync_type,
                                            sync_status=SYNC_STATUS.INITIATED.value, raw_payload=request)

            CatalogSyncLogProcessor.is_sync_type_allowed(self.bot, self.sync_type)
            if not CatalogSyncLogProcessor.is_catalog_collection_exists(self.bot) and CatalogSyncLogProcessor.is_ai_enabled(self.bot):
                CatalogSyncLogProcessor.create_catalog_collection(bot=self.bot, user=self.user)
            CatalogSyncLogProcessor.add_log(self.bot, self.user, sync_status=SYNC_STATUS.VALIDATING_REQUEST)
            if self.sync_type == SyncType.push_menu:
                CatalogSyncLogProcessor.validate_item_ids(request)
                CatalogSyncLogProcessor.validate_item_fields(self.bot, request, self.provider)
                CatalogSyncLogProcessor.validate_image_configurations(self.bot, self.user)
            else:
                CatalogSyncLogProcessor.validate_item_toggle_request(request)
            return True
        except Exception as e:
            execution_id = CatalogSyncLogProcessor.get_execution_id_for_bot(self.bot)
            await MailUtility.format_and_send_mail(
                    mail_type="catalog_sync_status", email="himanshu.gupta@nimblework.com", bot = self.bot, executionID = execution_id,
                    sync_status=SYNC_STATUS.VALIDATING_FAILED, message = str(e), first_name = "HG"
                )
            CatalogSyncLogProcessor.add_log(self.bot, self.user, sync_status=SYNC_STATUS.FAILED.value,
                                            exception=str(e),
                                            status="Failure")
            return str(e)

    async def preprocess(self, **kwargs):
        """
        Transform and preprocess incoming payload data into `self.data`
        for catalog sync and meta sync.
        """
        sync_status = SYNC_STATUS.VALIDATING_REQUEST_SUCCESS
        try:
            cognition_processor = CognitionDataProcessor()
            sync_status=SYNC_STATUS.PREPROCESSING
            CatalogSyncLogProcessor.add_log(self.bot, self.user, sync_status=sync_status)
            request = kwargs.get("request_body")
            if self.sync_type == SyncType.push_menu:
                self.data = cognition_processor.preprocess_push_menu_data(self.bot, request, self.provider)
            else:
                self.data = cognition_processor.preprocess_item_toggle_data(self.bot, request, self.provider)
            sync_status = SYNC_STATUS.PREPROCESSING_COMPLETED
            CatalogSyncLogProcessor.add_log(self.bot, self.user, sync_status=sync_status, processed_payload= self.data)
            stale_primary_keys = CognitionDataProcessor.save_ai_data(self.data, self.bot, self.user, self.sync_type)
            initiate_import = True
            if CatalogSyncLogProcessor.is_ai_enabled(self.bot):
                restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(self.bot)
                catalog_name = f"{restaurant_name}_{branch_name}_catalog"
                sync_status = SYNC_STATUS.VALIDATING_KNOWLEDGE_VAULT_DATA
                CatalogSyncLogProcessor.add_log(self.bot, self.user, sync_status=sync_status)
                error_summary = cognition_processor.validate_data("id", catalog_name,
                                                                  self.sync_type.lower(), self.data.get("kv", []), self.bot)
                if error_summary:
                    initiate_import = False
                    sync_status = SYNC_STATUS.SAVE.value
                    CatalogSyncLogProcessor.add_log(self.bot, self.user, validation_errors=error_summary,
                                                    sync_status=sync_status, status="Failure")
            return initiate_import, stale_primary_keys
        except Exception as e:
            execution_id = CatalogSyncLogProcessor.get_execution_id_for_bot(self.bot)
            await MailUtility.format_and_send_mail(
                mail_type="catalog_sync_status", email="himanshu.gupta@nimblework.com", bot=self.bot,
                executionID=execution_id,
                sync_status=sync_status, message=str(e), first_name="HG"
            )
            CatalogSyncLogProcessor.add_log(self.bot, self.user, sync_status=SYNC_STATUS.FAILED.value,
                                            exception=str(e),
                                            status="Failure")
            return None


    async def execute(self, **kwargs):
        """
        Execute the document content import event.
        """
        self.data = kwargs.get("data", {})
        cognition_processor = CognitionDataProcessor()
        initiate_import = kwargs.get("initiate_import", False)
        stale_primary_keys = kwargs.get("stale_primary_keys")
        status = "Failure"
        sync_status = SYNC_STATUS.PREPROCESSING_COMPLETED
        try:
            knowledge_vault_data = self.data.get("kv", [])
            restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(self.bot)
            catalog_name = f"{restaurant_name}_{branch_name}_catalog"

            if not CatalogSyncLogProcessor.is_ai_enabled(self.bot) and not CatalogSyncLogProcessor.is_meta_enabled(self.bot):
                CatalogSyncLogProcessor.add_log(self.bot, self.user,
                                                exception="Sync to knowledge vault and Meta is not allowed for this bot. Contact Support!!",
                                                status="Success")
                raise Exception("Sync to knowledge vault and Meta is not allowed for this bot. Contact Support!!")

            if initiate_import and CatalogSyncLogProcessor.is_ai_enabled(self.bot):
                result = await cognition_processor.upsert_data("id", catalog_name,
                                                                   self.sync_type.lower(), knowledge_vault_data,
                                                                   self.bot, self.user)
                stale_primary_keys = result.get("stale_ids")
            else:
                sync_status = SYNC_STATUS.COMPLETED.value
                CatalogSyncLogProcessor.add_log(self.bot, self.user,
                                                exception="Sync to knowledge vault is not allowed for this bot. Contact Support!!",
                                                status="Success")

            if not CatalogSyncLogProcessor.is_meta_enabled(self.bot):
                sync_status = SYNC_STATUS.COMPLETED.value
                CatalogSyncLogProcessor.add_log(self.bot, self.user,
                                                exception="Sync to Meta is not allowed for this bot. Contact Support!!",
                                                status="Success")

            integrations_doc = POSIntegrations.objects(bot=self.bot, provider=self.provider,
                                                    sync_type=self.sync_type).first()
            if integrations_doc and 'meta_config' in integrations_doc:
                sync_status=SYNC_STATUS.SAVE_META.value
                CatalogSyncLogProcessor.add_log(self.bot, self.user, sync_status=sync_status)
                meta_processor = MetaProcessor(integrations_doc.meta_config.get('access_token'),
                                               integrations_doc.meta_config.get('catalog_id'))

                meta_payload = self.data.get("meta", [])
                if self.sync_type == SyncType.push_menu:
                    meta_processor.preprocess_data(self.bot, meta_payload, "CREATE", self.provider)
                    await meta_processor.push_meta_catalog()
                    if stale_primary_keys:
                        delete_payload = meta_processor.preprocess_delete_data(stale_primary_keys)
                        await meta_processor.delete_meta_catalog(delete_payload)
                    status = "Success"
                else:
                    meta_processor.preprocess_data(self.bot, meta_payload, "UPDATE", self.provider)
                    await meta_processor.update_meta_catalog()
                    status = "Success"
            execution_id = CatalogSyncLogProcessor.get_execution_id_for_bot(self.bot)
            sync_status=SYNC_STATUS.COMPLETED.value
            await MailUtility.format_and_send_mail(
                mail_type="catalog_sync_status", email="himanshu.gupta@nimblework.com", bot=self.bot,
                executionID=execution_id,
                sync_status=sync_status, message="Catalog has been synced successfully", first_name="HG"
            )
            CatalogSyncLogProcessor.add_log(self.bot, self.user, sync_status=sync_status, status=status)
        except Exception as e:
            print(str(e))
            execution_id = CatalogSyncLogProcessor.get_execution_id_for_bot(self.bot)
            await MailUtility.format_and_send_mail(
                mail_type="catalog_sync_status", email="himanshu.gupta@nimblework.com", bot=self.bot,
                executionID=execution_id,
                sync_status=sync_status, message=str(e), first_name="HG"
            )
            if not CatalogSyncLogProcessor.is_meta_enabled(self.bot) and not CatalogSyncLogProcessor.is_ai_enabled(self.bot):
                CatalogSyncLogProcessor.add_log(self.bot, self.user,
                                                sync_status=SYNC_STATUS.COMPLETED.value)
            else:
                CatalogSyncLogProcessor.add_log(self.bot, self.user,
                                                    exception=str(e),
                                                    status="Failure",
                                                    sync_status=sync_status)
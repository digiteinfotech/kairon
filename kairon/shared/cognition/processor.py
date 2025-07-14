import json
from datetime import datetime
from pathlib import Path
from typing import Text, Dict, Any, List, Optional
import json
from loguru import logger
from mongoengine import DoesNotExist, Q
from pydantic import constr, create_model, ValidationError
from pymongo import UpdateOne

from kairon import Utility
from kairon.exceptions import AppException
from kairon.meta.processor import MetaProcessor
from kairon.shared.actions.data_objects import PromptAction, DatabaseAction
from kairon.shared.catalog_sync.data_objects import CatalogProviderMapping
from kairon.shared.cognition.data_objects import CognitionData, CognitionSchema, ColumnMetadata, CollectionData
from kairon.shared.data.constant import DEFAULT_LLM, SyncType
from kairon.shared.data.data_objects import POSIntegrations, PetpoojaSyncConfig
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.data.utils import DataUtility
from kairon.shared.models import CognitionDataType, CognitionMetadataType, VaultSyncType
from tqdm import tqdm
import uuid


class CognitionDataProcessor:
    """
    Class contains logic for saves, updates and deletes bot content and cognition content
    """

    @staticmethod
    def is_collection_limit_exceeded(bot, user, collection):
        """
        checks if collection limit is exhausted

        :param bot: bot id
        :param user: user
        :param collection: Name of collection
        :return: boolean
        :raises: AppException
        """

        bot_settings = MongoProcessor.get_bot_settings(bot, user)
        bot_settings = bot_settings.to_mongo().to_dict()
        collections = list(CognitionSchema.objects(bot=bot).distinct(field='collection_name'))
        if collection not in collections and len(collections) >= bot_settings["cognition_collections_limit"]:
            return True
        else:
            return False

    @staticmethod
    def is_collection_limit_exceeded_for_mass_uploading(bot:str, user:str, collection_names:List[str], overwrite:bool = False):
        """
        checks if collection limit is exhausted

        :param bot: bot id
        :param user: user
        :param collection_names: List of names of collection
        :return: boolean
        :raises: AppException
        """

        bot_settings = MongoProcessor.get_bot_settings(bot, user)
        bot_settings = bot_settings.to_mongo().to_dict()
        if overwrite:
            return len(collection_names) > bot_settings["cognition_collections_limit"]
        else:
            collections = list(CognitionSchema.objects(bot=bot).distinct(field='collection_name'))
            new_to_add = [collection for collection in collection_names if collection not in collections]
            return  len(new_to_add) + len(collections) > bot_settings["cognition_collections_limit"]



    @staticmethod
    def is_column_collection_limit_exceeded(bot, user, metadata):
        """
        checks if columns in collection limit is exhausted

        :param bot: bot id
        :param user: user
        :param metadata: schema
        :return: boolean
        """
        bot_settings = MongoProcessor.get_bot_settings(bot, user)
        bot_settings = bot_settings.to_mongo().to_dict()
        return len(metadata) > bot_settings["cognition_columns_per_collection_limit"]

    @staticmethod
    def is_same_column_in_metadata(metadata):
        """
        checks if there are same columns in metadata

        :param metadata: schema
        :return: boolean
        """
        if len(metadata) < 2:
            return False
        column_names = [item["column_name"] for item in metadata]
        unique_column_names = set(column_names)
        return len(unique_column_names) < len(column_names)

    def save_cognition_schema(self, schema: Dict, user: Text, bot: Text):
        Utility.is_exist(
            CognitionSchema, exp_message="Collection already exists!",
            collection_name__iexact=schema.get('collection_name'), bot=bot)
        if CognitionDataProcessor.is_collection_limit_exceeded(bot, user, schema.get('collection_name')):
            raise AppException('Collection limit exceeded!')
        if schema.get('metadata') and CognitionDataProcessor.is_column_collection_limit_exceeded(bot, user, schema.get(
                'metadata')):
            raise AppException('Column limit exceeded for collection!')
        if schema.get('metadata') and CognitionDataProcessor.is_same_column_in_metadata(schema.get('metadata')):
            raise AppException('Columns cannot be same in the schema!')
        metadata_obj = CognitionSchema(bot=bot, user=user)
        metadata_obj.metadata = [ColumnMetadata(**meta) for meta in schema.get('metadata') or []]
        metadata_obj.collection_name = schema.get('collection_name')
        metadata_id = metadata_obj.save().to_mongo().to_dict()["_id"].__str__()
        return metadata_id

    def delete_cognition_schema(self, schema_id: str, bot: Text, user: str = None):
        try:
            metadata = CognitionSchema.objects(bot=bot, id=schema_id).get()
            CognitionDataProcessor.validate_collection_name(bot, metadata['collection_name'])
            CognitionData.objects(Q(collection=metadata['collection_name']) & Q(bot=bot)).delete()
            Utility.delete_documents(metadata, user)
        except DoesNotExist:
            raise AppException("Schema does not exists!")

    def list_cognition_schema(self, bot: Text):
        """
        fetches metadata

        :param bot: bot id
        :return: yield dict
        """
        for value in CognitionSchema.objects(bot=bot, activeStatus=True):
            final_data = {}
            item = value.to_mongo().to_dict()
            metadata = item.pop("metadata")
            collection = item.pop('collection_name', None)
            final_data["_id"] = item["_id"].__str__()
            final_data['metadata'] = metadata
            final_data['collection_name'] = collection
            yield final_data

    @staticmethod
    def validate_metadata_and_payload(bot, payload):
        data = payload.get('data')
        collection = payload.get('collection', None)
        matched_metadata = CognitionDataProcessor.find_matching_metadata(bot, data, collection)
        for metadata_dict in matched_metadata['metadata']:
            column_name = metadata_dict['column_name']
            if column_name in data:
                if isinstance(data[column_name], str):
                    data[column_name] = data[column_name].strip()
                data[column_name] = CognitionDataProcessor.validate_column_values(data, metadata_dict)
        return data

    def save_cognition_data(self, payload: Dict, user: Text, bot: Text):
        from kairon import Utility

        bot_settings = MongoProcessor.get_bot_settings(bot=bot, user=user)
        if not bot_settings["llm_settings"]['enable_faq']:
            raise AppException('Faq feature is disabled for the bot! Please contact support.')

        if payload.get('content_type') == CognitionDataType.text.value and len(payload.get('data').split()) < 10:
            raise AppException("Content should contain atleast 10 words.")

        if payload.get('collection'):
            if not Utility.is_exist(CognitionSchema, bot=bot, collection_name__iexact=payload.get('collection'),
                                    raise_error=False):
                raise AppException('Collection does not exist!')
            if payload.get('content_type') == CognitionDataType.text.value and \
                    not Utility.is_exist(CognitionSchema, bot=bot, metadata=[],
                                         collection_name__iexact=payload.get('collection'), raise_error=False):
                raise AppException('Text content type does not have schema!')
        if payload.get('content_type') == CognitionDataType.json.value:
            payload['data'] = CognitionDataProcessor.validate_metadata_and_payload(bot, payload)

        payload_obj = CognitionData()
        payload_obj.data = payload.get('data')
        payload_obj.content_type = payload.get('content_type')
        payload_obj.collection = payload.get('collection', None)
        payload_obj.user = user
        payload_obj.bot = bot
        payload_id = payload_obj.save().to_mongo().to_dict()["_id"].__str__()
        return payload_id

    def update_cognition_data(self, row_id: str, payload: Dict, user: Text, bot: Text):
        from kairon import Utility

        data = payload['data']
        content_type = payload['content_type']
        if payload.get('content_type') == CognitionDataType.text.value and len(payload.get('data').split()) < 10:
            raise AppException("Content should contain atleast 10 words.")
        Utility.is_exist(CognitionData, bot=bot, id__ne=row_id, data=data,
                         exp_message="Payload data already exists!")
        if payload.get('collection') and not Utility.is_exist(CognitionSchema, bot=bot,
                                                              collection_name__iexact=payload.get('collection'),
                                                              raise_error=False):
            raise AppException('Collection does not exist!')
        try:
            payload_obj = CognitionData.objects(bot=bot, id=row_id).get()
            if content_type == CognitionDataType.json.value:
                payload['data'] = CognitionDataProcessor.validate_metadata_and_payload(bot, payload)
            payload_obj.data = data
            payload_obj.content_type = content_type
            payload_obj.collection = payload.get('collection', None)
            payload_obj.user = user
            payload_obj.timestamp = datetime.utcnow()
            payload_obj.save()
        except DoesNotExist:
            raise AppException("Payload with given id not found!")

    def delete_cognition_data(self, row_id: str, bot: Text, user: str = None):
        try:
            payload = CognitionData.objects(bot=bot, id=row_id).get()
            Utility.delete_documents(payload, user)
        except DoesNotExist:
            raise AppException("Payload does not exists!")

    def delete_multiple_cognition_data(self, row_ids: List[str], bot: Text, user: str = None):
        """
        Deletes multiple cognition entries in bulk.
        """
        if not row_ids:
            raise AppException("row_ids list cannot be empty!")
        query = {"id__in": row_ids}
        Utility.hard_delete_document([CognitionData], bot=bot,user=user, **query)

    def delete_all_cognition_data_by_collection(self, collection_name: Text, bot: Text):
        """
        Deletes all documents from the specified collection for a given bot.

        @param bot: The bot ID for which data should be deleted.
        @param collection_name: The name of the collection from which data should be deleted.
        """
        CognitionData.objects(bot=bot, collection=collection_name).delete()

    def list_cognition_data(self, bot: Text, start_idx: int = 0, page_size: int = 10, **kwargs):
        """
        fetches content

        :param bot: bot id
        :param start_idx: start index
        :param page_size: page size
        :return: yield dict
        """
        kwargs["bot"] = bot
        search = kwargs.pop('data', None)
        cognition_data = CognitionData.objects(**kwargs)
        if search:
            cognition_data = cognition_data.search_text(search)
        for value in cognition_data.skip(start_idx).limit(page_size).order_by('-id'):
            final_data = {}
            item = value.to_mongo().to_dict()
            data = item.pop("data")
            data_type = item.pop("content_type")
            final_data["row_id"] = item["_id"].__str__()
            final_data['data'] = data
            final_data['content_type'] = data_type
            final_data['collection'] = item.get('collection', None)
            final_data['user'] = item.get('user')
            final_data['bot'] = item.get('bot')
            yield final_data

    def get_cognition_data(self, bot: Text, start_idx: int = 0, page_size: int = 10, **kwargs):
        processor = MongoProcessor()
        collection = kwargs.pop('collection', None)
        collection = collection.lower() if collection else None
        kwargs['collection'] = collection
        cognition_data = list(self.list_cognition_data(bot, start_idx, page_size, **kwargs))
        row_cnt = processor.get_row_count(CognitionData, bot, **kwargs)
        return cognition_data, row_cnt

    @staticmethod
    def validate_column_values(data: Any, schema: Dict):
        if schema and isinstance(data, dict):
            data_type = schema['data_type']
            column_name = schema['column_name']
            if column_name in data and data[column_name] is not None:
                value = data[column_name]

                if data_type == CognitionMetadataType.int.value and not isinstance(value, int):
                    raise AppException(
                        f"Invalid data type for '{column_name}': Expected integer value")

                if data_type == CognitionMetadataType.float.value:
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        raise AppException(
                            f"Invalid data type for '{column_name}': Expected float value"
                        )

                if data_type == CognitionMetadataType.str.value and not isinstance(value, str):
                    raise AppException(
                        f"Invalid data type for '{column_name}': Expected string value")

                return value
            else:
                raise AppException(f"Column '{column_name}' does not exist or has no value.")

    @staticmethod
    def find_matching_metadata(bot: Text, data: Any, collection: Text = None):
        columns = list(data.keys())
        try:
            matching_metadata = CognitionSchema.objects(Q(metadata__column_name__in=columns) &
                                                        Q(collection_name__iexact=collection) &
                                                        Q(bot=bot)).get()
            return matching_metadata
        except DoesNotExist as e:
            logger.exception(e)
            raise AppException("Columns do not exist in the schema!")

    @staticmethod
    def validate_collection_name(bot: Text, collection: Text):
        prompt_action = list(PromptAction.objects(bot=bot, llm_prompts__data__iexact=collection))
        database_action = list(DatabaseAction.objects(bot=bot, collection__iexact=collection))
        if prompt_action:
            raise AppException(f'Cannot remove collection {collection} linked to action "{prompt_action[0].name}"!')
        if database_action:
            raise AppException(f'Cannot remove collection {collection} linked to action "{database_action[0].name}"!')

    @staticmethod
    def get_pydantic_type(data_type: str):
        if data_type == 'str':
            return (constr(strict=True, min_length=1), ...)
        elif data_type == 'int':
            return (int, ...)
        elif data_type == 'float':
            return (float, ...)
        else:
            raise ValueError(f"Unsupported data type: {data_type}")

    def validate_data(self, primary_key_col: str, collection_name: str, sync_type: str, data: List[Dict], bot: str) -> Dict:
        """
        Validates each dictionary in the data list according to the expected schema from column_dict.

        Args:
            data: List of dictionaries where each dictionary represents a row to be validated.
            collection_name: The name of the collection (table name).
            sync_type: The type of the event being validated.
            bot: The bot identifier.
            primary_key_col: The primary key column for identifying rows.

        Returns:
            Dict: Summary of validation errors, if any.
        """
        self._validate_sync_type(sync_type)
        event_validations = VaultSyncType[sync_type].value

        self._validate_collection_exists(collection_name)
        column_dict = MongoProcessor().get_column_datatype_dict(bot, collection_name)

        error_summary = {}

        existing_documents = CognitionData.objects(bot=bot, collection=collection_name).as_pymongo()
        existing_document_map = {
            doc["data"].get(primary_key_col): doc
            for doc in existing_documents
            if doc["data"].get(primary_key_col) is not None
        }

        for row in data:
            row_key = row.get(primary_key_col)
            if not row_key:
                raise AppException(f"Primary key '{primary_key_col}' must exist in each row.")

            row_errors = []

            if "column_length_mismatch" in event_validations:
                if len(row.keys()) != len(column_dict.keys()):
                    row_errors.append({
                        "status": "Column length mismatch",
                        "expected_columns": list(column_dict.keys()),
                        "actual_columns": list(row.keys())
                    })
            if "invalid_columns" in event_validations:
                expected_columns = list(column_dict.keys())
                if sync_type == VaultSyncType.item_toggle.name:
                    expected_columns = [primary_key_col + " + any from " + str([col for col in column_dict.keys() if col != primary_key_col])]
                if not set(row.keys()).issubset(set(column_dict.keys())):
                    row_errors.append({
                        "status": "Invalid columns in input data",
                        "expected_columns": expected_columns,
                        "actual_columns": list(row.keys())
                    })

            if "document_non_existence" in event_validations:
                if row_key not in existing_document_map:
                    row_errors.append({
                        "status": "Document does not exist",
                        "primary_key": row_key,
                        "message": f"No document found for '{primary_key_col}': {row_key}"
                    })

            if row_errors:
                error_summary[row_key] = row_errors
                continue

            model_fields = {}
            for column_name in row.keys():
                value = column_dict.get(column_name)
                model_fields[column_name] = self.get_pydantic_type(value)

            DynamicModel = create_model('DynamicModel', **model_fields)

            if "pydantic_validation" in event_validations:
                try:
                    DynamicModel(**row)
                except ValidationError as e:
                    error_details = []
                    for error in e.errors():
                        column_name = error['loc'][0]
                        input_value = row.get(column_name)
                        status = "Required Field is Empty" if input_value == "" else "Invalid DataType"
                        error_details.append({
                            "column_name": column_name,
                            "input": input_value,
                            "status": status
                        })
                    error_summary[row_key] = error_details

        return error_summary

    def _validate_sync_type(self, sync_type: str):
        if sync_type not in VaultSyncType.__members__.keys():
            raise AppException("Sync type does not exist")

    def _validate_collection_exists(self, collection_name: str):
        if not CognitionSchema.objects(collection_name=collection_name).first():
            raise AppException(f"Collection '{collection_name}' does not exist.")

    async def save_pos_integration_config(self, configuration: Dict, bot: Text, user: Text, sync_type: Text = None):
        """
        Creates or updates POS integration config for a given bot and provider.

        :param configuration: Input config dictionary (from request)
        :param bot: Bot ID
        :param user: User ID
        :param sync_type: Optional sync type
        :return: integration endpoint
        """
        self._validate_sync_type(sync_type)

        provider = configuration["provider"]
        config_data = configuration["config"]
        meta_config = configuration.get("meta_config", {})
        smart_catalog_enabled = configuration.get("smart_catalog_enabled", False)
        meta_enabled = configuration.get("meta_enabled", False)
        sync_options = configuration.get("sync_options")

        sync_options = PetpoojaSyncConfig(**sync_options)

        integration = POSIntegrations.objects(
            bot=bot,
            provider=provider,
            sync_type=sync_type
        ).first()

        if integration and integration.smart_catalog_enabled and not smart_catalog_enabled:
            await self.delete_existing_kv_catalog_data(bot)

        if integration and integration.meta_enabled and not meta_enabled:
            await self.delete_existing_meta_catalog_data(bot, meta_config)

        if integration:
            integration.config = config_data
            integration.meta_config = meta_config
            integration.smart_catalog_enabled = smart_catalog_enabled
            integration.meta_enabled = meta_enabled
            integration.sync_options = sync_options
            integration.timestamp = datetime.utcnow()
            integration.user = user
        else:
            integration = POSIntegrations(
                bot=bot,
                user=user,
                provider=provider,
                sync_type=sync_type,
                config=config_data,
                meta_config=meta_config,
                smart_catalog_enabled=smart_catalog_enabled,
                meta_enabled=meta_enabled,
                sync_options=sync_options,
                timestamp=datetime.utcnow(),
            )
        integration.save()

        other_provider_integrations = POSIntegrations.objects(bot=bot, provider=provider, sync_type__ne=sync_type)

        for doc in other_provider_integrations:
            doc.smart_catalog_enabled = smart_catalog_enabled
            doc.meta_enabled = meta_enabled
            doc.config = config_data
            doc.meta_config = meta_config
            doc.sync_options = sync_options
            doc.timestamp = datetime.utcnow()
            doc.save()

        integration_endpoint = DataUtility.get_integration_endpoint(integration)
        return integration_endpoint

    async def delete_existing_meta_catalog_data(self, bot: str, meta_config: Dict):
        """
        Deletes metadata items from Meta catalog if meta_enabled is turned off.
        """
        restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(bot)
        catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"

        existing_docs = CollectionData.objects(
            collection_name=catalog_data_collection,
            bot=bot,
            status=True
        )

        meta_ids = [
            doc.data.get("meta", {}).get("id")
            for doc in existing_docs
            if doc.data.get("meta", {}).get("id")
        ]

        access_token = meta_config.get("access_token")
        catalog_id = meta_config.get("catalog_id")

        if meta_ids:
            meta_processor = MetaProcessor(access_token, catalog_id)
            delete_payload = meta_processor.preprocess_delete_data(meta_ids)
            await meta_processor.delete_meta_catalog(delete_payload)

    async def delete_existing_kv_catalog_data(self, bot: str):
        """
        Deletes knowledge vault items from Mongo and Qdrant vector store if smart_catalog_enabled is turned off.
        """

        from kairon.shared.llm.processor import LLMProcessor

        restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(bot)
        catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"
        collection_name = f"{restaurant_name}_{branch_name}_catalog"

        existing_docs = CollectionData.objects(
            collection_name=catalog_data_collection,
            bot=bot,
            status=True
        )

        kv_ids = [
            doc.data.get("kv", {}).get("id")
            for doc in existing_docs
            if doc.data.get("kv", {}).get("id")
        ]

        if not kv_ids:
            return

        stale_docs = CognitionData.objects(
            bot=bot,
            collection=collection_name,
            data__id__in=kv_ids
        ).as_pymongo()

        doc_ids = []
        vector_ids = []

        for doc in stale_docs:
            doc_ids.append(doc["_id"])
            vector_ids.append(doc["vector_id"])

        CognitionData.objects(id__in=doc_ids).delete()
        logger.info(f"Deleted {len(doc_ids)} stale KV documents from MongoDB.")

        llm_processor = LLMProcessor(bot, DEFAULT_LLM)
        qdrant_collection = f"{bot}_{collection_name}_faq_embd"

        await llm_processor.__delete_collection_points__(
            qdrant_collection,
            vector_ids,
            "Cannot delete stale points from Qdrant!"
        )
        logger.info(f"Deleted {len(vector_ids)} stale points from Qdrant.")

    @staticmethod
    def list_pos_integration_configs(bot: str) -> List[Dict]:
        """
        Helper to fetch POS integration config for a provider and bot.
        If provider is 'petpooja', merge all its sync_types into one document.
        """
        documents = POSIntegrations.objects(bot=bot)
        if not documents:
            return []

        sync_types = list({doc.sync_type for doc in documents if doc.sync_type})
        base_doc = documents[0].to_mongo().to_dict()
        base_doc.pop("_id", None)
        base_doc["sync_type"] = sync_types

        return [base_doc]

    @staticmethod
    def delete_pos_integration_config(bot: str, provider: str, sync_type: Optional[str] = None) -> Dict:
        """
        Helper to delete POS integration config for a provider and sync_type
        """
        query = {"bot": bot, "provider": provider}
        if sync_type:
            query["sync_type"] = sync_type

        integration = POSIntegrations.objects(**query)
        if not integration:
            raise AppException("Integration config not found")

        deleted_count = integration.count()
        integration.delete()

        result = {"provider": provider, "deleted_count": deleted_count}
        if sync_type:
            result["sync_type"] = sync_type
        return result

    @staticmethod
    def get_pos_integration_endpoint(bot: str, provider: str, sync_type: str):
        """
        Helper to retrieve POS integration endpoint
        """
        integration = POSIntegrations.objects(bot=bot, provider=provider,
                                              sync_type=sync_type).get()
        DataUtility.get_integration_endpoint(integration)
        return DataUtility.get_integration_endpoint(integration)

    @staticmethod
    def preprocess_push_menu_data(bot, json_data, provider):
        """
        Preprocess the JSON data received from Petpooja to extract relevant fields for knowledge base or meta synchronization.
        Handles different event types ("push_menu" vs others) and uses metadata to drive the field extraction and defaulting.
        """
        doc = CatalogProviderMapping.objects(provider=provider).first()
        if not doc:
            raise Exception(f"Metadata mappings not found for provider={provider}")

        category_map = {
            cat["categoryid"]: cat["categoryname"]
            for cat in json_data.get("categories", [])
        }

        provider_mappings = {
            "meta": doc.meta_mappings,
            "kv": doc.kv_mappings
        }

        data = {sync_target: [] for sync_target in provider_mappings}
        for item in json_data.get("items", []):
            for sync_target, fields in provider_mappings.items():
                transformed_item = {"id": item["itemid"]}

                for target_field, field_config in fields.items():
                    source_key = field_config.get("source")
                    default_value = field_config.get("default")
                    value = item.get(source_key) if source_key else None

                    if target_field == "availability":
                        value = "in stock" if int(value or 0) > 0 else default_value
                    elif target_field == "facebook_product_category":
                        category_id = value or ""
                        value = f"Food and drink > {category_map.get(category_id, 'General')}"
                    elif target_field == "image_url":
                        value = CognitionDataProcessor.resolve_image_link(bot, item["itemid"])
                    elif target_field == "price":
                        value = float(value)
                    if not value:
                        value = default_value

                    transformed_item[target_field] = value

                data[sync_target].append(transformed_item)

        return data

    @staticmethod
    def preprocess_item_toggle_data(bot, json_data, provider):
        doc = CatalogProviderMapping.objects(provider=provider).first()
        if not doc:
            raise Exception(f"Metadata mappings not found for provider={provider}")

        provider_mappings = {
            "meta": doc.meta_mappings,
            "kv": doc.kv_mappings
        }

        in_stock = json_data["inStock"]
        item_ids = json_data["itemID"]
        availability = "in stock" if in_stock else "out of stock"
        processed_data = [{"id": item_id, "availability": availability} for item_id in item_ids]

        data = {sync_target: processed_data for sync_target in provider_mappings}

        return data

    @staticmethod
    def resolve_image_link(bot: str, item_id: str):
        restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(bot)
        catalog_images_collection = f"{restaurant_name}_{branch_name}_catalog_images"

        document = CollectionData.objects(
            collection_name=catalog_images_collection,
            data__item_id=int(item_id),
            data__image_type="local"
        ).first()

        if not document:
            document = CollectionData.objects(
                collection_name=catalog_images_collection,
                bot=bot,
                data__image_type="global"
            ).first()

        if document:
            data = document.data or {}
            image_link = data.get("image_url")

            if image_link:
                return image_link
        else:
            raise Exception(f"Image URL not found for {item_id} in {catalog_images_collection}")

    async def upsert_data(self, primary_key_col: str, collection_name: str, sync_type: str, data: List[Dict], bot: str,
                          user: Text):
        """
        Upserts data into the CognitionData collection in batches and syncs embeddings with Qdrant.

        Args:
            primary_key_col: The primary key column name to check for uniqueness.
            collection_name: The collection name (table).
            sync_type: The type of the event being upserted.
            data: List of rows of data to upsert.
            bot: The bot identifier associated with the data.
            user: The user.
        """

        from kairon.shared.llm.processor import LLMProcessor
        llm_processor = LLMProcessor(bot, DEFAULT_LLM)
        suffix = "_faq_embd"
        qdrant_collection = f"{bot}_{collection_name}{suffix}" if collection_name else f"{bot}{suffix}"

        if not await llm_processor.__collection_exists__(qdrant_collection):
            await llm_processor.__create_collection__(qdrant_collection)

        existing_documents = CognitionData.objects(bot=bot, collection=collection_name).as_pymongo()

        existing_document_map = {
            doc["data"].get(primary_key_col): doc for doc in existing_documents
        }

        processed_keys = set()

        update_operations = []
        insert_operations = []

        embedding_payloads = []
        search_payloads = []
        vector_ids = []

        batch_size = 50
        for i in tqdm(range(0, len(data), batch_size), desc="Syncing Knowledge Vault"):
            batch_contents = data[i:i + batch_size]

            for row in batch_contents:
                primary_key_value = row.get(primary_key_col)
                existing_document = existing_document_map.get(primary_key_value)

                vector_id = str(uuid.uuid4()) if not existing_document else existing_document.get("vector_id")

                merged_data = row
                if existing_document:
                    existing_data = existing_document.get("data", {})
                    merged_data = {**existing_data, **row}
                    update_operations.append(UpdateOne(
                        {"_id": existing_document["_id"]},
                        {"$set": {"data": merged_data, "timestamp": datetime.utcnow()}}
                    ))
                else:
                    new_doc = CognitionData(
                        data=merged_data,
                        vector_id=vector_id,
                        content_type=CognitionDataType.json.value,
                        collection=collection_name,
                        bot=bot,
                        user=user
                    )
                    insert_operations.append(new_doc)

                processed_keys.add(primary_key_value)

                metadata = self.find_matching_metadata(bot, merged_data, collection_name)
                search_payload, embedding_payload = Utility.retrieve_search_payload_and_embedding_payload(merged_data,
                                                                                                          metadata)

                embedding_payloads.append(embedding_payload)
                search_payloads.append(search_payload)
                vector_ids.append(vector_id)

            if update_operations:
                CognitionData._get_collection().bulk_write(update_operations)
                logger.info(f"Updated {len(update_operations)} documents in MongoDB")

            if insert_operations:
                CognitionData.objects.insert(insert_operations, load_bulk=False)
                logger.info(f"Inserted {len(insert_operations)} new documents in MongoDB")

            update_operations.clear()
            insert_operations.clear()
            if embedding_payloads:
                embeddings = await llm_processor.get_embedding(embedding_payloads, user,
                                                               invocation="knowledge_vault_sync")
                points = [{'id': vector_ids[idx], 'vector': embeddings[idx], 'payload': search_payloads[idx]}
                          for idx in range(len(vector_ids))]
                await llm_processor.__collection_upsert__(qdrant_collection, {'points': points},
                                                          err_msg="Unable to upsert data in qdrant! Contact support")
                logger.info(f"Upserted {len(points)} points in Qdrant.")

            embedding_payloads.clear()
            search_payloads.clear()
            vector_ids.clear()

        remaining_primary_keys = []
        if sync_type == VaultSyncType.push_menu.name:
            stale_docs = [doc for key, doc in existing_document_map.items() if key not in processed_keys]

            if stale_docs:
                doc_ids = []
                vector_ids = []
                remaining_primary_keys = []

                for doc in stale_docs:
                    doc_ids.append(doc["_id"])
                    vector_ids.append(doc["vector_id"])
                    remaining_primary_keys.append(doc["data"].get(primary_key_col))

                CognitionData.objects(id__in=doc_ids).delete()
                logger.info(f"Deleted {len(stale_docs)} stale documents from MongoDB.")

                await llm_processor.__delete_collection_points__(qdrant_collection, vector_ids,
                                                                 "Cannot delete stale points fro Qdrant!")
                logger.info(f"Deleted {len(stale_docs)} stale points from Qdrant.")

        return {"message": "Upsert complete!", "stale_ids": remaining_primary_keys}

    @staticmethod
    def save_ai_data(processed_data: dict, bot: str, user: str, sync_type: str):
        """
        Save each item in kv + meta of the processed payload into CollectionData,
        with 'data' stored as {"kv": {...}, "meta": {...}}.
        Performs partial update for `item_toggle`, full replace otherwise.
        """
        restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(bot)
        catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"

        kv_items = {item["id"]: item for item in processed_data.get("kv", [])}
        meta_items = {item["id"]: item for item in processed_data.get("meta", [])}
        incoming_ids = set(kv_items.keys())

        existing_docs = CollectionData.objects(
            collection_name=catalog_data_collection,
            bot=bot,
            status=True
        )
        existing_data_map = {doc.data.get("kv", {}).get("id"): doc for doc in existing_docs}
        existing_ids = set(existing_data_map.keys())

        for item_id in incoming_ids:
            kv = kv_items[item_id]
            meta = meta_items.get(item_id, {})
            existing_doc = existing_data_map.get(item_id)

            if existing_doc:
                if sync_type == SyncType.item_toggle:
                    for key, value in kv.items():
                        existing_doc.data["kv"][key] = value
                    for key, value in meta.items():
                        existing_doc.data["meta"][key] = value
                else:
                    existing_doc.data = {"kv": kv, "meta": meta}

                existing_doc.timestamp = datetime.utcnow()
                existing_doc.user = user
                existing_doc.save()
            else:
                CollectionData(
                    collection_name=catalog_data_collection,
                    data={"kv": kv, "meta": meta},
                    user=user,
                    bot=bot,
                    timestamp=datetime.utcnow(),
                    status=True
                ).save()

        stale_ids = []
        if sync_type == SyncType.push_menu:
            stale_ids = list(existing_ids - incoming_ids)
            if stale_ids:
                CollectionData.objects(
                    collection_name=catalog_data_collection,
                    bot=bot,
                    status=True,
                    data__kv__id__in=stale_ids
                ).delete()

        return stale_ids

    @staticmethod
    def load_catalog_provider_mappings():
        """
        Load and store catalog provider mappings from a JSON file.

        :param file_path: Path to the mappings JSON file.
        :raises AppException: If file does not exist or mapping format is invalid.
        """
        file_path = "./metadata/catalog_provider_mappings.json"
        path = Path(file_path)

        if not path.exists():
            raise AppException(f"Mappings file not found at {file_path}")

        with open(path, "r") as f:
            mapping_data = json.load(f)

        for provider, mappings in mapping_data.items():
            meta = mappings.get("meta")
            kv = mappings.get("kv")

            if not meta or not kv:
                raise AppException(f"Mappings for provider '{provider}' is missing required 'meta' or 'kv' fields.")

            try:
                metadata_doc = CatalogProviderMapping.objects.get(provider=provider)
                metadata_doc.update(
                    set__meta_mappings=meta,
                    set__kv_mappings=kv
                )
            except DoesNotExist:
                CatalogProviderMapping(
                    provider=provider,
                    meta_mappings=meta,
                    kv_mappings=kv
                ).save()


    @staticmethod
    def get_restaurant_and_branch_name(bot: Text):
        integration = POSIntegrations.objects(bot=bot).first()
        if not integration:
            raise Exception(f"No POS integration config found for bot: {bot}")

        restaurant_name = integration.config.get("restaurant_name").replace(" ", "_")
        branch_name = integration.config.get("branch_name").replace(" ", "_")
        return restaurant_name.lower(), branch_name.lower()

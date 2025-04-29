import json
from datetime import datetime
from pathlib import Path
from typing import Text, Dict, Any, List
import json
from loguru import logger
from mongoengine import DoesNotExist, Q
from pydantic import constr, create_model, ValidationError
from pymongo import UpdateOne

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.actions.data_objects import PromptAction, DatabaseAction
from kairon.shared.catalog_sync.data_objects import CatalogProviderMapping
from kairon.shared.cognition.data_objects import CognitionData, CognitionSchema, ColumnMetadata, CollectionData
from kairon.shared.constants import CatalogSyncClass
from kairon.shared.data.constant import DEFAULT_LLM, SyncType
from kairon.shared.data.data_objects import BotSyncConfig, POSIntegrations
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

    def delete_collection_data(self, collection_id: str, bot: Text, user: Text):
        try:
            collection = CollectionData.objects(bot=bot, id=collection_id).get()
            collection.delete(user=user)
        except DoesNotExist:
            raise AppException("Collection Data does not exists!")

    @staticmethod
    def validate_collection_payload(collection_name, is_secure, data):
        if not collection_name:
            raise AppException("collection name is empty")

        if not isinstance(is_secure, list):
            raise AppException("is_secure should be list of keys")

        if is_secure:
            if not data or not isinstance(data, dict):
                raise AppException("Invalid value for data")

    def save_collection_data(self, payload: Dict, user: Text, bot: Text):
        collection_name = payload.get("collection_name", None)
        data = payload.get('data')
        is_secure = payload.get('is_secure')
        CognitionDataProcessor.validate_collection_payload(collection_name, is_secure, data)

        data = CognitionDataProcessor.prepare_encrypted_data(data, is_secure)

        collection_obj = CollectionData()
        collection_obj.data = data
        collection_obj.is_secure = is_secure
        collection_obj.collection_name = collection_name
        collection_obj.user = user
        collection_obj.bot = bot
        collection_id = collection_obj.save().to_mongo().to_dict()["_id"].__str__()
        return collection_id

    def update_collection_data(self, collection_id: str, payload: Dict, user: Text, bot: Text):
        collection_name = payload.get("collection_name", None)
        data = payload.get('data')
        is_secure = payload.get('is_secure')
        CognitionDataProcessor.validate_collection_payload(collection_name, is_secure, data)

        data = CognitionDataProcessor.prepare_encrypted_data(data, is_secure)

        try:
            collection_obj = CollectionData.objects(bot=bot, id=collection_id, collection_name=collection_name).get()
            collection_obj.data = data
            collection_obj.collection_name = collection_name
            collection_obj.is_secure = is_secure
            collection_obj.user = user
            collection_obj.timestamp = datetime.utcnow()
            collection_obj.save()
        except DoesNotExist:
            raise AppException("Collection Data with given id and collection_name not found!")
        return collection_id

    @staticmethod
    def prepare_encrypted_data(data, is_secure):
        encrypted_data = {}
        for key, value in data.items():
            if key in is_secure:
                encrypted_data[key] = Utility.encrypt_message(value)
            else:
                encrypted_data[key] = value
        return encrypted_data

    @staticmethod
    def prepare_decrypted_data(data, is_secure):
        decrypted_data = {}
        for key, value in data.items():
            if key in is_secure:
                decrypted_data[key] = Utility.decrypt_message(value)
            else:
                decrypted_data[key] = value
        return decrypted_data

    def list_collection_data(self, bot: Text):
        """
        fetches collection data

        :param bot: bot id
        :return: yield dict
        """
        for value in CollectionData.objects(bot=bot):
            final_data = {}
            item = value.to_mongo().to_dict()
            collection_name = item.pop('collection_name', None)
            is_secure = item.pop('is_secure')
            data = item.pop('data')
            data = CognitionDataProcessor.prepare_decrypted_data(data, is_secure)
            final_data["_id"] = item["_id"].__str__()
            final_data['collection_name'] = collection_name
            final_data['is_secure'] = is_secure
            final_data['data'] = data
            yield final_data

    def get_collection_data_with_id(self, bot: Text, **kwargs):
        """
        fetches collection data based on the filters provided

        :param bot: bot id
        :return: yield dict
        """
        try:
            collection_id = kwargs.pop("collection_id")
            collection_data = CollectionData.objects(bot=bot, id=collection_id).get()
            final_data = {}
            item = collection_data.to_mongo().to_dict()
            collection_name = item.pop('collection_name', None)
            is_secure = item.pop('is_secure')
            data = item.pop('data')
            data = CognitionDataProcessor.prepare_decrypted_data(data, is_secure)
            final_data["_id"] = item["_id"].__str__()
            final_data['collection_name'] = collection_name
            final_data['is_secure'] = is_secure
            final_data['data'] = data
        except DoesNotExist:
            raise AppException("Collection data does not exists!")
        return final_data

    def get_collection_data(self, bot: Text, **kwargs):
        """
        fetches collection data based on the filters provided

        :param bot: bot id
        :return: yield dict
        """
        collection_name = kwargs.pop("collection_name")
        collection_name = collection_name.lower()
        keys = kwargs.pop("key", None)
        values = kwargs.pop("value", None)
        if len(keys) != len(values):
            raise AppException("Keys and values lists must be of the same length.")

        query = {"bot": bot, "collection_name": collection_name}
        query.update({
            f"data__{key}": value for key, value in zip(keys, values) if key and value
        })

        for value in CollectionData.objects(**query):
            final_data = {}
            item = value.to_mongo().to_dict()
            collection_name = item.pop('collection_name', None)
            is_secure = item.pop('is_secure')
            data = item.pop('data')
            data = CognitionDataProcessor.prepare_decrypted_data(data, is_secure)
            final_data["_id"] = item["_id"].__str__()
            final_data['collection_name'] = collection_name
            final_data['is_secure'] = is_secure
            final_data['data'] = data
            yield final_data

    def get_collection_data_with_timestamp(self, bot: Text, collection_name: Text, **kwargs):
        """
        fetches collection data based on the filters provided

        :param bot: bot id
        :param collection_name: collection name
        :return: yield dict
        """
        collection_name = collection_name.lower()
        start_time = kwargs.pop("start_time", None)
        end_time = kwargs.pop("end_time", None)
        data_filter = kwargs.pop("data_filter", {}) if isinstance(kwargs.get("data_filter"), dict) else json.loads(
            kwargs.pop("data_filter", "{}"))

        query = {"bot": bot, "collection_name": collection_name}
        if start_time:
            query["timestamp__gte"] = start_time
        if end_time:
            query["timestamp__lte"] = end_time

        query.update({
            f"data__{key}": value for key, value in data_filter.items() if key and value
        })

        for value in CollectionData.objects(**query):
            final_data = {}
            item = value.to_mongo().to_dict()
            collection_name = item.pop('collection_name', None)
            is_secure = item.pop('is_secure')
            data = item.pop('data')
            data = CognitionDataProcessor.prepare_decrypted_data(data, is_secure)
            final_data["_id"] = item["_id"].__str__()
            final_data['collection_name'] = collection_name
            final_data['is_secure'] = is_secure
            final_data['data'] = data
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

    # async def upsert_data(self, primary_key_col: str, collection_name: str, sync_type: str, data: List[Dict], bot: str, user: Text):
    #     """
    #     Upserts data into the CognitionData collection.
    #     If document with the primary key exists, it will be updated.
    #     If not, it will be inserted.
    #
    #     Args:
    #         primary_key_col: The primary key column name to check for uniqueness.
    #         collection_name: The collection name (table).
    #         sync_type: The type of the event being upserted
    #         data: List of rows of data to upsert.
    #         bot: The bot identifier associated with the data.
    #         user: The user
    #     """
    #
    #     from kairon.shared.llm.processor import LLMProcessor
    #     llm_processor = LLMProcessor(bot, DEFAULT_LLM)
    #     suffix = "_faq_embd"
    #     qdrant_collection = f"{bot}_{collection_name}{suffix}" if collection_name else f"{bot}{suffix}"
    #
    #     if await llm_processor.__collection_exists__(qdrant_collection) is False:
    #         await llm_processor.__create_collection__(qdrant_collection)
    #
    #     existing_documents = CognitionData.objects(bot=bot, collection=collection_name).as_pymongo()
    #
    #     existing_document_map = {
    #         doc["data"].get(primary_key_col): doc for doc in existing_documents
    #     }
    #
    #     for row in data:
    #         primary_key_value = row.get(primary_key_col)
    #
    #         existing_document = existing_document_map.get(primary_key_value)
    #
    #         if sync_type == "item_toggle" and existing_document:
    #             existing_data = existing_document.get("data", {})
    #             merged_data = {**existing_data, **row}
    #             logger.debug(f"Merged row for {primary_key_col} {primary_key_value}: {merged_data}")
    #         else:
    #             merged_data = row
    #
    #         payload = {
    #             "data": merged_data,
    #             "content_type": CognitionDataType.json.value,
    #             "collection": collection_name
    #         }
    #
    #         if existing_document:
    #             row_id = str(existing_document["_id"])
    #             self.update_cognition_data(row_id, payload, user, bot)
    #             updated_document = CognitionData.objects(id=row_id).first()
    #             if not isinstance(updated_document, dict):
    #                 updated_document = updated_document.to_mongo().to_dict()
    #             logger.info(f"Row with {primary_key_col}: {primary_key_value} updated in MongoDB")
    #             await self.sync_with_qdrant(llm_processor, qdrant_collection, bot, updated_document, user,
    #                                         primary_key_col)
    #         else:
    #             row_id = self.save_cognition_data(payload, user, bot)
    #             new_document = CognitionData.objects(id=row_id).first()
    #             if not isinstance(new_document, dict):
    #                 new_document = new_document.to_mongo().to_dict()
    #             logger.info(f"Row with {primary_key_col}: {primary_key_value} inserted in MongoDB")
    #             await self.sync_with_qdrant(llm_processor, qdrant_collection, bot, new_document, user, primary_key_col)
    #
    #     return {"message": "Upsert complete!"}
    def _validate_sync_type(self, sync_type: str):
        if sync_type not in VaultSyncType.__members__.keys():
            raise AppException("Sync type does not exist")

    def _validate_collection_exists(self, collection_name: str):
        if not CognitionSchema.objects(collection_name=collection_name).first():
            raise AppException(f"Collection '{collection_name}' does not exist.")


    def save_pos_integration_config(self, configuration: Dict, bot: Text, user: Text, sync_type: Text = None):
        """
        save or updates data integration configuration
        :param configuration: config dict
        :param bot: bot id
        :param user: user id
        :param sync_type: event type
        :return: None
        """
        self._validate_sync_type(sync_type)
        try:
            integration = POSIntegrations.objects(bot= bot, provider = configuration['provider'], sync_type = sync_type).get()
            integration.config = configuration['config']
            integration.meta_config = configuration['meta_config']
        except DoesNotExist:
            integration = POSIntegrations(**configuration)
        integration.bot = bot
        integration.user = user
        integration.sync_type = sync_type
        integration.timestamp = datetime.utcnow()

        if 'meta_config' in configuration:
            integration.meta_config = configuration['meta_config']

        integration.save()
        integration_endpoint = DataUtility.get_integration_endpoint(integration)
        return integration_endpoint


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

        in_stock = json_data["body"]["inStock"]
        item_ids = json_data["body"]["itemID"]
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
            data__image_type = "local"
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
                search_payload, embedding_payload = Utility.retrieve_search_payload_and_embedding_payload(merged_data, metadata)

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

        remaining_primary_keys =[]
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

                await llm_processor.__delete_collection_points__(qdrant_collection, vector_ids, "Cannot delete stale points fro Qdrant!")
                logger.info(f"Deleted {len(stale_docs)} stale points from Qdrant.")

        return {"message": "Upsert complete!", "stale_ids": remaining_primary_keys}

    @staticmethod
    def save_ai_data(processed_data: dict, bot: str, user: str, sync_type: str):
        """
        Save each item in `kv` of the processed payload into CollectionData individually.
        """
        restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(bot)
        catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"

        kv_items = processed_data.get("kv", [])
        incoming_data_map = {item["id"]: item for item in kv_items}
        incoming_ids = set(incoming_data_map.keys())

        existing_docs = CollectionData.objects(
            collection_name=catalog_data_collection,
            bot=bot,
            status=True
        )
        existing_data_map = {doc.data.get("id"): doc for doc in existing_docs}
        existing_ids = set(existing_data_map.keys())

        for item_id, item in incoming_data_map.items():
            if item_id in existing_data_map:
                doc = existing_data_map[item_id]
                if sync_type == SyncType.item_toggle:
                    for key, value in item.items():
                        doc.data[key] = value
                else:
                    doc.data = item
                doc.timestamp = datetime.utcnow()
                doc.user = user
                doc.save()
            else:
                CollectionData(
                    collection_name=catalog_data_collection,
                    data=item,
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
                    data__id__in=stale_ids
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
    def add_bot_sync_config(request_data, bot: Text, user: Text):
        if request_data.provider.lower() == CatalogSyncClass.petpooja:
            if BotSyncConfig.objects(branch_bot=bot,provider=CatalogSyncClass.petpooja).first():
                return

            bot_sync_config = BotSyncConfig(
                process_push_menu=False,
                process_item_toggle=False,
                parent_bot=bot,
                restaurant_name=request_data.config.get("restaurant_name"),
                provider=CatalogSyncClass.petpooja,
                branch_name=request_data.config.get("branch_name"),
                branch_bot=bot,
                ai_enabled=False,
                meta_enabled=False,
                user=user
            )
            bot_sync_config.save()

    @staticmethod
    def get_restaurant_and_branch_name(bot: Text):
        config = BotSyncConfig.objects(branch_bot=bot).first()
        if not config:
            raise Exception(f"No bot sync config found for bot: {bot}")
        restaurant_name = config.restaurant_name.replace(" ", "_")
        branch_name = config.branch_name.replace(" ", "_")
        return restaurant_name.lower(), branch_name.lower()

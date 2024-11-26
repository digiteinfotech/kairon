from datetime import datetime
from typing import Text, Dict, Any, List

from loguru import logger
from mongoengine import DoesNotExist, Q
from pydantic import constr, create_model, ValidationError

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.actions.data_objects import PromptAction, DatabaseAction
from kairon.shared.cognition.data_objects import CognitionData, CognitionSchema, ColumnMetadata, CollectionData
from kairon.shared.data.constant import DEFAULT_LLM
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.models import CognitionDataType, CognitionMetadataType, VaultSyncEventType


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

    @staticmethod
    def validate_metadata_and_payload(bot, payload):
        data = payload.get('data')
        collection = payload.get('collection', None)
        matched_metadata = CognitionDataProcessor.find_matching_metadata(bot, data, collection)
        for metadata_dict in matched_metadata['metadata']:
            CognitionDataProcessor.validate_column_values(data, metadata_dict)

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
            CognitionDataProcessor.validate_metadata_and_payload(bot, payload)

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
                CognitionDataProcessor.validate_metadata_and_payload(bot, payload)
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
            if column_name in data and data[column_name] and data_type == CognitionMetadataType.int.value:
                try:
                    return int(data[column_name])
                except ValueError:
                    raise AppException("Invalid data type!")
            elif column_name in data and data[column_name] and data_type == CognitionMetadataType.float.value:
                try:
                    return float(data[column_name])
                except ValueError:
                    raise AppException("Invalid data type!")
            else:
                return data[column_name]

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

    def validate_data(self, primary_key_col: str, collection_name: str, event_type: str, data: List[Dict], bot: str) -> Dict:
        """
        Validates each dictionary in the data list according to the expected schema from column_dict.

        Args:
            data: List of dictionaries where each dictionary represents a row to be validated.
            collection_name: The name of the collection (table name).
            event_type: The type of the event being validated.
            bot: The bot identifier.
            primary_key_col: The primary key column for identifying rows.

        Returns:
            Dict: Summary of validation errors, if any.
        """
        self._validate_event_type(event_type)
        event_validations = VaultSyncEventType[event_type].value

        self._validate_collection_exists(collection_name)
        column_dict = MongoProcessor().get_column_datatype_dict(bot, collection_name)

        error_summary = {}

        existing_documents = CognitionData.objects(bot=bot, collection=collection_name).as_pymongo()
        existing_document_map = {
            doc["data"].get(primary_key_col): doc
            for doc in existing_documents
            if doc["data"].get(primary_key_col) is not None  # Ensure primary key exists in map
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
                if event_type == "field_update":
                    expected_columns = [primary_key_col + " + any from " + str([col for col in column_dict.keys() if col != primary_key_col])]
                if not set(row.keys()).issubset(set(column_dict.keys())):
                    row_errors.append({
                        "status": "Invalid columns in input data",
                        "expected_columns": expected_columns,
                        "actual_columns": list(row.keys())
                    })

            if "document_non_existence" in event_validations:
                if str(row_key) not in existing_document_map:
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

    async def upsert_data(self, primary_key_col: str, collection_name: str, event_type: str, data: List[Dict], bot: str, user: Text):
        """
        Upserts data into the CognitionData collection.
        If document with the primary key exists, it will be updated.
        If not, it will be inserted.

        Args:
            primary_key_col: The primary key column name to check for uniqueness.
            collection_name: The collection name (table).
            event_type: The type of the event being upserted
            data: List of rows of data to upsert.
            bot: The bot identifier associated with the data.
            user: The user
        """

        from kairon.shared.llm.processor import LLMProcessor
        llm_processor = LLMProcessor(bot, DEFAULT_LLM)
        suffix = "_faq_embd"
        qdrant_collection = f"{bot}_{collection_name}{suffix}" if collection_name else f"{bot}{suffix}"

        if await llm_processor.__collection_exists__(qdrant_collection) is False:
            await llm_processor.__create_collection__(qdrant_collection)

        existing_documents = CognitionData.objects(bot=bot, collection=collection_name).as_pymongo()

        existing_document_map = {
            doc["data"].get(primary_key_col): doc for doc in existing_documents
        }

        for row in data:
            row = {str(key): str(value) for key, value in row.items()}
            primary_key_value = row.get(primary_key_col)

            existing_document = existing_document_map.get(primary_key_value)

            if event_type == "field_update" and existing_document:
                existing_data = existing_document.get("data", {})
                merged_data = {**existing_data, **row}
                logger.debug(f"Merged row for {primary_key_col} {primary_key_value}: {merged_data}")
            else:
                merged_data = row

            payload = {
                "data": merged_data,
                "content_type": CognitionDataType.json.value,
                "collection": collection_name
            }

            if existing_document:
                row_id = str(existing_document["_id"])
                self.update_cognition_data(row_id, payload, user, bot)
                updated_document = CognitionData.objects(id=row_id).first()
                if not isinstance(updated_document, dict):
                    updated_document = updated_document.to_mongo().to_dict()
                logger.info(f"Row with {primary_key_col}: {primary_key_value} updated in MongoDB")
                await self.sync_with_qdrant(llm_processor, qdrant_collection, bot, updated_document, user,
                                            primary_key_col)
            else:
                row_id = self.save_cognition_data(payload, user, bot)
                new_document = CognitionData.objects(id=row_id).first()
                if not isinstance(new_document, dict):
                    new_document = new_document.to_mongo().to_dict()
                logger.info(f"Row with {primary_key_col}: {primary_key_value} inserted in MongoDB")
                await self.sync_with_qdrant(llm_processor, qdrant_collection, bot, new_document, user, primary_key_col)

        return {"message": "Upsert complete!"}

    async def sync_with_qdrant(self, llm_processor, collection_name, bot, document, user, primary_key_col):
        """
        Syncs a document with Qdrant vector database by generating embeddings and upserting them.

        Args:
            llm_processor (LLMProcessor): Instance of LLMProcessor for embedding and Qdrant operations.
            collection_name (str): Name of the Qdrant collection.
            bot (str): Bot identifier.
            document (CognitionData): Document to sync with Qdrant.
            user (Text): User performing the operation.

        Raises:
            AppException: If Qdrant upsert operation fails.
        """
        try:
            metadata = self.find_matching_metadata(bot, document['data'], document.get('collection'))
            search_payload, embedding_payload = Utility.retrieve_search_payload_and_embedding_payload(
                document['data'], metadata)
            embeddings = await llm_processor.get_embedding(embedding_payload, user, invocation='knowledge_vault_sync')
            points = [{'id': document['vector_id'], 'vector': embeddings, 'payload': search_payload}]
            await llm_processor.__collection_upsert__(collection_name, {'points': points},
                                                      err_msg="Unable to train FAQ! Contact support")
            logger.info(f"Row with {primary_key_col}: {document['data'].get(primary_key_col)} upserted in Qdrant.")
        except Exception as e:
            raise AppException(f"Failed to sync document with Qdrant: {str(e)}")

    def _validate_event_type(self, event_type: str):
        if event_type not in VaultSyncEventType.__members__.keys():
            raise AppException("Event type does not exist")

    def _validate_collection_exists(self, collection_name: str):
        if not CognitionSchema.objects(collection_name=collection_name).first():
            raise AppException(f"Collection '{collection_name}' does not exist.")

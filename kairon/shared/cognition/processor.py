from datetime import datetime
from typing import Text, Dict, Any

from loguru import logger
from mongoengine import DoesNotExist, Q

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.actions.data_objects import PromptAction, DatabaseAction
from kairon.shared.cognition.data_objects import CognitionData, CognitionSchema, ColumnMetadata, CollectionData
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.models import CognitionDataType, CognitionMetadataType


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
            cognition_data = list(CognitionData.objects(Q(collection=metadata['collection_name']) &
                                                        Q(bot=bot)))
            if cognition_data:
                for data in cognition_data:
                    data.delete()
            Utility.delete_documents(metadata, user)
        except DoesNotExist:
            raise AppException("Schema does not exists!")

    def list_cognition_schema(self, bot: Text):
        """
        fetches metadata

        :param bot: bot id
        :return: yield dict
        """
        for value in CognitionSchema.objects(bot=bot):
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
            f"{key}": value for key, value in zip(keys, values) if key and value
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

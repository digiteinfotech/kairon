import json
from datetime import datetime
from typing import Text, Dict, Any, List

from mongoengine import DoesNotExist

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.cognition.data_objects import CognitionData, CognitionSchema, ColumnMetadata
from kairon.shared.data.data_objects import BotSettings
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.models import CognitionDataType, CognitionMetadataType


class CognitionDataProcessor:
    """
    Class contains logic for saves, updates and deletes bot content and cognition content
    """

    def is_collection_limit_exceeded(self, bot, collection):
        """
        checks if collection limit is exhausted

        :param bot: bot id
        :param collection: Name of collection
        :return: boolean
        :raises: AppException
        """

        collections = self.list_cognition_collections(bot)
        doc_count = CognitionData.objects(
            bot=bot, collection__ne=None,
        ).count()
        if collection not in collections and doc_count >= BotSettings.objects(
                bot=bot).get().cognition_collections_limit:
            return True
        else:
            return False

    def is_column_collection_limit_exceeded(self, bot, metadata):
        """
        checks if columns in collection limit is exhausted

        :param bot: bot id
        :param metadata: schema
        :return: boolean
        :raises: AppException
        """
        count = sum('column_name' in metadata_dict for metadata_dict in metadata.get('metadata'))

        return count >= BotSettings.objects(bot=bot).get().cognition_columns_per_collection_limit

    def save_content(self, content: Text, user: Text, bot: Text, collection: Text = None):
        if collection:
            if self.is_collection_limit_exceeded(bot, collection):
                raise AppException('Collection limit exceeded!')
        bot_settings = MongoProcessor.get_bot_settings(bot=bot, user=user)
        if not bot_settings["llm_settings"]['enable_faq']:
            raise AppException('Faq feature is disabled for the bot! Please contact support.')
        if len(content.split()) < 10:
            raise AppException("Content should contain atleast 10 words.")

        content_obj = CognitionData()
        content_obj.data = content
        content_obj.collection = collection
        content_obj.user = user
        content_obj.bot = bot
        id = (
            content_obj.save().id.__str__()
        )
        return id

    def update_content(self, content_id: str, content: Text, user: Text, bot: Text, collection: Text = None):
        if len(content.split()) < 10:
            raise AppException("Content should contain atleast 10 words.")

        Utility.is_exist(CognitionData, bot=bot, id__ne=content_id, data=content,
                         content_type__ne=CognitionDataType.json.value,
                         exp_message="Text already exists!")

        try:
            content_obj = CognitionData.objects(bot=bot, id=content_id).get()
            content_obj.data = content
            content_obj.collection = collection
            content_obj.user = user
            content_obj.timestamp = datetime.utcnow()
            content_obj.save()
        except DoesNotExist:
            raise AppException("Content with given id not found!")

    def delete_content(self, content_id: str, user: Text, bot: Text):
        try:
            content = CognitionData.objects(bot=bot, id=content_id).get()
            content.delete()
        except DoesNotExist:
            raise AppException("Text does not exists!")

    def get_content(self, bot: Text, **kwargs):
        """
        fetches content

        :param bot: bot id
        :return: yield dict
        """
        kwargs["bot"] = bot
        search = kwargs.pop('data', None)
        start_idx = kwargs.pop('start_idx', 0)
        page_size = kwargs.pop('page_size', 10)
        cognition_data = CognitionData.objects(**kwargs)
        if search:
            cognition_data = cognition_data.search_text(search)
        for value in cognition_data.skip(start_idx).limit(page_size):
            item = value.to_mongo().to_dict()
            item.pop('timestamp')
            item["_id"] = item["_id"].__str__()
            yield item

    def list_cognition_collections(self, bot: Text):
        """
        Retrieve cognition data.
        :param bot: bot id
        """
        collections = list(CognitionData.objects(bot=bot).distinct(field='collection'))
        return collections

    def save_cognition_schema(self, metadata: Dict, user: Text, bot: Text):
        if self.is_column_collection_limit_exceeded(bot, metadata):
            raise AppException('Column limit exceeded for collection!')
        Utility.is_exist(CognitionSchema, bot=bot, collection_name=metadata.get('collection_name'),
                         exp_message="Collection already exists!")
        column_name = [meta['column_name'] for meta in metadata.get('metadata')]
        for column in column_name:
            Utility.is_exist(CognitionSchema, bot=bot, metadata__column_name=column,
                             exp_message="Column already exists!")
        metadata_obj = CognitionSchema(bot=bot, user=user)
        metadata_obj.metadata = [ColumnMetadata(**meta) for meta in metadata.get('metadata')]
        metadata_obj.collection_name = metadata.get('collection_name', None)
        metadata_id = metadata_obj.save().to_mongo().to_dict()["_id"].__str__()
        return metadata_id

    def update_cognition_schema(self, metadata_id: str, metadata: Dict, user: Text, bot: Text):
        metadata_items = metadata.get('metadata')
        Utility.is_exist(CognitionSchema, bot=bot, id__ne=metadata_id, metadata=metadata_items,
                         exp_message="Schema already exists!")
        try:
            metadata_obj = CognitionSchema.objects(bot=bot, id=metadata_id).get()
            metadata_obj.metadata = [ColumnMetadata(**meta) for meta in metadata.get('metadata')]
            metadata_obj.collection_name = metadata.get('collection_name')
            metadata_obj.bot = bot
            metadata_obj.user = user
            metadata_obj.timestamp = datetime.utcnow()
            metadata_obj.save()
        except DoesNotExist:
            raise AppException("Schema with given id not found!")

    def delete_cognition_schema(self, metadata_id: str, bot: Text):
        try:
            metadata = CognitionSchema.objects(bot=bot, id=metadata_id).get()
            metadata.delete()
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

    def __validate_metadata_and_payload(self, payload, bot: Text):
        data = payload.get('data')
        collection = payload.get('collection', None)
        matched_metadata = self.find_matching_metadata(data, collection)
        if not matched_metadata:
            raise AppException("Metadata related to payload not found!")
        for metadata_dict in matched_metadata:
            self.retrieve_data(data, metadata_dict)

    def save_cognition_data(self, payload: Dict, user: Text, bot: Text):
        bot_settings = MongoProcessor.get_bot_settings(bot=bot, user=user)
        if not bot_settings["llm_settings"]['enable_faq']:
            raise AppException('Faq feature is disabled for the bot! Please contact support.')
        if payload.get('content_type') != CognitionDataType.text.value:
            self.__validate_metadata_and_payload(payload, bot)
        payload_obj = CognitionData()
        payload_obj.data = payload.get('data')
        payload_obj.content_type = payload.get('content_type')
        payload_obj.collection = payload.get('collection', None)
        payload_obj.user = user
        payload_obj.bot = bot
        payload_id = payload_obj.save().to_mongo().to_dict()["_id"].__str__()
        return payload_id

    def update_cognition_data(self, payload_id: str, payload: Dict, user: Text, bot: Text):
        data = payload['data']
        content_type = payload['content_type']
        Utility.is_exist(CognitionData, bot=bot, id__ne=payload_id, data=data,
                         content_type__ne=CognitionDataType.json.value,
                         exp_message="Payload data already exists!")

        try:
            payload_obj = CognitionData.objects(bot=bot, id=payload_id).get()
            payload_obj.data = data
            payload_obj.content_type = content_type
            payload_obj.collection = payload.get('collection', None)
            payload_obj.user = user
            payload_obj.timestamp = datetime.utcnow()
            payload_obj.save()
        except DoesNotExist:
            raise AppException("Payload with given id not found!")

    def delete_cognition_data(self, payload_id: str, bot: Text):
        try:
            payload = CognitionData.objects(bot=bot, id=payload_id).get()
            payload.delete()
        except DoesNotExist:
            raise AppException("Payload does not exists!")

    def list_cognition_data(self, bot: Text):
        """
        fetches content

        :param bot: bot id
        :return: yield dict
        """
        for value in CognitionData.objects(bot=bot):
            final_data = {}
            item = value.to_mongo().to_dict()
            data = item.pop("data")
            data_type = item.pop("content_type")
            final_data["_id"] = item["_id"].__str__()
            final_data['content'] = data
            final_data['content_type'] = data_type
            final_data['collection'] = item.get('collection', None)
            yield final_data

    @staticmethod
    def retrieve_data(data: Any, metadata: Dict):
        if metadata and isinstance(data, dict):
            data_type = metadata['metadata']['data_type']
            column_name = metadata['metadata']['column_name']
            if column_name in data and data[column_name] and data_type == CognitionMetadataType.int.value:
                try:
                    return int(data[column_name])
                except ValueError:
                    raise AppException("Invalid data type!")
            else:
                return data[column_name]

    @staticmethod
    def find_matching_metadata(data: Any, collection: Text = None):
        matching_metadata = list(CognitionSchema.objects.aggregate([
                                     {"$match": {"collection_name": collection, "metadata": {
                                         "$elemMatch": {"column_name": {"$in": [key for key in data.keys()]}}}}},
                                     {"$unwind": "$metadata"},
                                     {"$match": {"metadata.column_name": {"$in": [key for key in data.keys()]}}},
                                     {"$project": {"_id": 1, "collection_name": 1, "metadata": 1}}
                                 ]))
        return matching_metadata

    @staticmethod
    def get_embeddings_and_payload_data(data: Any, metadata: List):
        search_payload = {}
        create_embedding_data = {}
        for metadata_item in metadata:
            column_name = metadata_item["metadata"]["column_name"]
            if column_name in data.keys():
                converted_value = CognitionDataProcessor.retrieve_data(data, metadata_item)
                if converted_value and metadata_item["metadata"]["enable_search"]:
                    search_payload[column_name] = converted_value
                if converted_value and metadata_item["metadata"]["create_embeddings"]:
                    create_embedding_data[column_name] = converted_value
        create_embedding_data = json.dumps(create_embedding_data)
        return search_payload, create_embedding_data

from datetime import datetime
import json
from fastapi import HTTPException
from typing import Dict, Text, List
import re
from mongoengine import DoesNotExist

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.cognition.data_objects import CollectionData
from loguru import logger
from typing import List

class DataProcessor:

    @staticmethod
    def validate_collection_payload(collection_name, is_secure, data):
        if not collection_name.strip():
            raise AppException("collection name is empty")

        if not isinstance(is_secure, list):
            raise AppException("is_secure should be list of keys")

        if is_secure:
            if not data or not isinstance(data, dict):
                raise AppException("Invalid value for data")

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

    @staticmethod
    def get_crud_metadata(bot: Text, collection_name: Text, **kwargs) -> dict:
        from genson import SchemaBuilder
        from genson.schema.node import SchemaGenerationError

        documents = CollectionData.objects(bot=bot, collection_name=collection_name)

        if not documents:
            logger.warning(f"Collection Data not found: bot={bot}, collection_name={collection_name}")
            return {"type": "object", "properties": {}}

        builder = SchemaBuilder()
        builder.add_schema({"type": "object", "properties": {}})

        for doc in documents:
            nested_data = getattr(doc, "data", None)
            if isinstance(nested_data, dict):
                try:
                    builder.add_object(nested_data)
                except SchemaGenerationError as e:
                    logger.warning(
                        f"Skipping document with invalid data structure: {nested_data}. Reason: {str(e)}"
                    )
            else:
                logger.warning("Invalid or missing 'data' field in a document.")

        return builder.to_schema()

    @staticmethod
    def save_collection_data(payload: Dict, user: Text, bot: Text):
        collection_name = payload.get("collection_name", None)
        data = payload.get('data')
        is_secure = payload.get('is_secure')
        is_non_editable = payload.get('is_non_editable')
        DataProcessor.validate_collection_payload(collection_name, is_secure, data)

        data = DataProcessor.prepare_encrypted_data(data, is_secure)

        collection_obj = CollectionData()
        collection_obj.data = data
        collection_obj.is_secure = is_secure
        collection_obj.is_non_editable = is_non_editable
        collection_obj.collection_name = collection_name
        collection_obj.user = user
        collection_obj.bot = bot
        collection_id = collection_obj.save().to_mongo().to_dict()["_id"].__str__()
        return collection_id

    @staticmethod
    def update_collection_data( collection_id: str, payload: Dict, user: Text, bot: Text):
        collection_name = payload.get("collection_name")
        data = payload.get("data", {})
        is_secure = payload.get("is_secure", [])
        is_non_editable = payload.get("is_non_editable", [])

        DataProcessor.validate_collection_payload(collection_name, is_secure, data)
        data = DataProcessor.prepare_encrypted_data(data, is_secure)

        try:
            collection_obj = CollectionData.objects(bot=bot, id=collection_id, collection_name=collection_name).get()
            filtered_data = {
                k: v for k, v in data.items()
                if k not in is_non_editable
            }

            collection_obj.data.update(filtered_data)
            collection_obj.collection_name = collection_name
            collection_obj.is_secure = is_secure
            collection_obj.is_non_editable = is_non_editable
            collection_obj.user = user
            collection_obj.timestamp = datetime.utcnow()
            collection_obj.save()
        except DoesNotExist:
            raise AppException("Collection Data with given id and collection_name not found!")

        return collection_id

    @staticmethod
    def delete_collection_data( collection_id: str, bot: Text, user: Text):
        try:
            collection = CollectionData.objects(bot=bot, id=collection_id).get()
            collection.delete(user=user)
        except DoesNotExist:
            raise AppException("Collection Data does not exists!")

    @staticmethod
    def delete_collection_data_with_user( bot: Text, user: Text):
        collection_count = CollectionData.objects(bot=bot, user=user).delete()
        if collection_count == 0:
            logger.error(f"No collection data found for bot='{bot}', user='{user}' to delete.")

    @staticmethod
    def get_broadcast_collection_data(bot: Text, collection_name: str, filters: List[Dict]) -> List[Dict]:
        from more_itertools import unique_everseen

        filters_dict = {
            "bot": bot,
            "collection_name": collection_name
        }

        for f in filters:
            column = f.get("column")
            condition = f.get("condition")
            value = f.get("value")

            field_name = f"data__{column}" + (f"__{condition}" if condition else "")
            filters_dict[field_name] = value

        qs = CollectionData.objects(**filters_dict)

        data = list(unique_everseen(qs, key=lambda doc: json.dumps(doc.data, sort_keys=True)))
        data = [doc.data for doc in data]

        return data

    @staticmethod
    def list_collection_data(bot: Text):
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
            is_non_editable = item.pop('is_non_editable')
            data = item.pop('data')
            data = DataProcessor.prepare_decrypted_data(data, is_secure)
            final_data["_id"] = item["_id"].__str__()
            final_data['collection_name'] = collection_name
            final_data['is_secure'] = is_secure
            final_data['is_non_editable'] = is_non_editable
            final_data['data'] = data
            yield final_data

    @staticmethod
    def get_collection_data_with_id( bot: Text, **kwargs):
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
            is_non_editable = item.pop('is_non_editable')
            data = item.pop('data')
            data = DataProcessor.prepare_decrypted_data(data, is_secure)
            final_data["_id"] = item["_id"].__str__()
            final_data['collection_name'] = collection_name
            final_data['is_secure'] = is_secure
            final_data['is_non_editable'] = is_non_editable
            final_data['data'] = data
        except DoesNotExist:
            raise AppException("Collection data does not exists!")
        return final_data

    @staticmethod
    def get_collection_data(bot: Text, **kwargs):
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
        result_limit = kwargs.pop("result_limit", None)

        if result_limit is not None:
            mongo_query = CollectionData.objects(**query).limit(result_limit)
        else:
            mongo_query = CollectionData.objects(**query)

        for value in mongo_query:
            final_data = {}
            item = value.to_mongo().to_dict()
            collection_name = item.pop('collection_name', None)
            is_secure = item.pop('is_secure')
            is_non_editable = item.pop('is_non_editable')
            data = item.pop('data')
            data = DataProcessor.prepare_decrypted_data(data, is_secure)
            final_data["_id"] = item["_id"].__str__()
            final_data['collection_name'] = collection_name
            final_data['is_secure'] = is_secure
            final_data['is_non_editable'] = is_non_editable
            final_data['data'] = data
            yield final_data

    @staticmethod
    def get_collection_data_with_timestamp(bot: Text, collection_name: Text, **kwargs):
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
            is_non_editable = item.pop('is_non_editable')
            data = item.pop('data')
            data = DataProcessor.prepare_decrypted_data(data, is_secure)
            final_data["_id"] = item["_id"].__str__()
            final_data['collection_name'] = collection_name
            final_data['is_secure'] = is_secure
            final_data['is_non_editable'] = is_non_editable
            final_data['data'] = data
            yield final_data

    @staticmethod
    def get_all_collections(bot: str):
        pipeline = [
                    {"$match": {"bot": bot}},
                    {"$group": {"_id": "$collection_name", "count": {"$sum": 1}}},
                    {"$project": {"collection_name": "$_id", "count": 1, "_id": 0}}
            ]
        result = list(CollectionData.objects(bot=bot).aggregate(pipeline))

        return result

    @staticmethod
    def delete_collection(bot: str, name: str):
        result = CollectionData.objects(bot=bot, collection_name=name).delete()
        if result > 0:
            message = f"Collection {name} deleted successfully!"
        else:
            message = f"Collection {name} does not exist!"
        return [message, result]

    @staticmethod
    def save_bulk_collection_data(payloads: List[Dict], user: Text, bot: Text, collection_name: Text):
        collection_docs = []
        errors = []
        collection_name=collection_name

        for index, payload in enumerate(payloads):
            try:
                data = payload.get("data")
                is_secure = payload.get("is_secure")
                is_non_editable = payload.get("is_non_editable")

                DataProcessor.validate_collection_payload(collection_name, is_secure, data)
                encrypted_data = DataProcessor.prepare_encrypted_data(data, is_secure)

                collection_obj = CollectionData(
                    collection_name=collection_name,
                    data=encrypted_data,
                    is_secure=is_secure,
                    is_non_editable=is_non_editable,
                    user=user,
                    bot=bot,
                )
                collection_docs.append(collection_obj)
            except Exception as e:
                errors.append({
                    "index": index,
                    "error": str(e)
                })

        if errors:
            raise AppException(f"Errors in bulk insert: {errors}")

        if collection_docs:
            try:
                CollectionData.objects.insert(collection_docs)
            except Exception as e:
                raise AppException(f"Bulk insert failed: {str(e)}")
        return {
            "status" : "success",
            "errors" : []
        }

    @staticmethod
    def validate_collection_name(collection_name):
        try:
            if not collection_name or not collection_name.strip():
                raise ValueError("Collection name cannot be empty.")
            if len(collection_name) > 64:
                raise ValueError("Collection name cannot exceed 64 characters.")
            if not re.match(r"^[A-Za-z][A-Za-z0-9_-]*$", collection_name):
                raise ValueError(
                    "Collection name must start with a letter and contain only letters, numbers, underscores, or hyphens.")
        except Exception as e:
            raise HTTPException(status_code=422, detail=str(e))



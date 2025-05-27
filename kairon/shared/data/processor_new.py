from typing import Dict, Text

from kairon.shared.cognition.data_objects import CollectionData
from datetime import datetime
from mongoengine.errors import DoesNotExist
from kairon.exceptions import AppException


class DataProcessor:

    @staticmethod
    def get_all_collections(bot: str):
        collection_names = CollectionData.objects(bot=bot).distinct("collection_name")
        result = []
        for name in collection_names:
            count = CollectionData.objects(bot=bot, collection_name=name).count()
            result.append({
                "collection_name": name,
                "count": count
            })
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
    def list_collection_data(bot: str, name: str):
        docs = CollectionData.objects(bot=bot, collection_name=name)
        output = []
        for doc in docs:
            output.append({
                "id": str(doc.id),
                "collection_name": doc.collection_name,
                "is_secure": list(doc.is_secure),
                "data": doc.data,
                "status": doc.status,
                "timestamp": doc.timestamp.isoformat(),
                "user": doc.user,
                "bot": doc.bot
            })
        return output

    @staticmethod
    def update_crud_collection_data(collection_id: str, payload: Dict, user: Text, bot: Text):
        from ..cognition.processor import CognitionDataProcessor

        collection_name = payload.get("collection_name")
        data = payload.get("data", {})
        is_secure = payload.get("is_secure", [])
        is_editable = payload.get("is_editable", [])

        CognitionDataProcessor.validate_collection_payload(collection_name, is_secure, data)
        data = CognitionDataProcessor.prepare_encrypted_data(data, is_secure)

        try:
            collection_obj = CollectionData.objects(bot=bot, id=collection_id, collection_name=collection_name).get()

            # Remove uneditable keys from update
            filtered_data = {
                k: v for k, v in data.items()
                if k not in is_editable
            }

            collection_obj.data.update(filtered_data)
            collection_obj.collection_name = collection_name
            collection_obj.is_secure = is_secure
            collection_obj.is_editable = is_editable
            collection_obj.user = user
            collection_obj.timestamp = datetime.utcnow()
            collection_obj.save()
        except DoesNotExist:
            raise AppException("Collection Data with given id and collection_name not found!")

        return collection_id

    @staticmethod
    def save_crud_collection_data(payload: Dict, user: Text, bot: Text):
        from ..cognition.processor import CognitionDataProcessor
        collection_name = payload.get("collection_name", None)
        data = payload.get('data')
        is_secure = payload.get('is_secure')
        is_editable = payload.get('is_editable')
        CognitionDataProcessor.validate_collection_payload(collection_name, is_secure, data)

        data = CognitionDataProcessor.prepare_encrypted_data(data, is_secure)

        collection_obj = CollectionData()
        collection_obj.data = data
        collection_obj.is_secure = is_secure
        collection_obj.is_editable = is_editable
        collection_obj.collection_name = collection_name
        collection_obj.user = user
        collection_obj.bot = bot
        collection_id = collection_obj.save().to_mongo().to_dict()["_id"].__str__()
        return collection_id

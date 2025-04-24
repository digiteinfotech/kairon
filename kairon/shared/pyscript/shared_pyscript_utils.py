from typing import Text, Dict, Callable, List
from typing import Text
from loguru import logger
from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.cognition.data_objects import CollectionData
from kairon.api.app.routers.bot.data import CognitionDataProcessor
cognition_processor = CognitionDataProcessor()

class PyscriptSharedUtility:

    def fetch_collection_data(query: dict):
        collection_data = CollectionData.objects(**query)

        for value in collection_data:
            final_data = {}
            item = value.to_mongo().to_dict()
            collection_name = item.pop('collection_name', None)
            is_secure = item.pop('is_secure')
            data = item.pop('data')
            data = cognition_processor.prepare_decrypted_data(data, is_secure)

            final_data["_id"] = str(item["_id"])
            final_data['collection_name'] = collection_name
            final_data['is_secure'] = is_secure
            final_data['data'] = data

            yield final_data


    @staticmethod
    def get_data(collection_name: str, user: str, data_filter: dict, bot: Text = None):
        if not bot:
            raise Exception("Missing bot id")

        collection_name = collection_name.lower()

        query = {"bot": bot, "collection_name": collection_name}

        query.update({f"data__{key}": value for key, value in data_filter.items()})
        data = list(PyscriptSharedUtility.fetch_collection_data(query))
        return {"data": data}


    @staticmethod
    def add_data(user: str, payload: dict, bot: str = None):
        if not bot:
            raise Exception("Missing bot id")

        collection_id = cognition_processor.save_collection_data(payload, user, bot)
        return {
            "message": "Record saved!",
            "data": {"_id": collection_id}
        }


    @staticmethod
    def update_data(collection_id: str, user: str, payload: dict, bot: str = None):
        if not bot:
            raise Exception("Missing bot id")

        collection_id = cognition_processor.update_collection_data(collection_id, payload, user, bot)
        return {
            "message": "Record updated!",
            "data": {"_id": collection_id}
        }


    @staticmethod
    def delete_data(collection_id: str, user: Text, bot: Text = None):
        if not bot:
            raise Exception("Missing bot id")

        cognition_processor.delete_collection_data(collection_id, bot, user)

        return {
            "message": f"Collection with ID {collection_id} has been successfully deleted.",
            "data": {"_id": collection_id}
        }

    @staticmethod
    def delete_schedule_job(event_id: Text, bot: Text):
        if not bot:
            raise AppException("Missing bot id")

        if not event_id:
            raise AppException("Missing event id")

        logger.info(f"event: {event_id}, bot: {bot}")

        event_server = Utility.environment['events']['server_url']

        http_response = ActionUtility.execute_http_request(
            f"{event_server}/api/events/{event_id}",
            "DELETE")

        if not http_response.get("success"):
            raise AppException(http_response)
        else:
            logger.info(http_response)
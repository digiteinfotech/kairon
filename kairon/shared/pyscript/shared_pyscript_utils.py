from datetime import date, datetime
from typing import Text

import pytz
from dateutil.parser import isoparse
from loguru import logger
from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.cognition.data_objects import CollectionData
from kairon.api.app.routers.bot.data import CognitionDataProcessor
from kairon.shared.data.collection_processor import DataProcessor

cognition_processor = CognitionDataProcessor()

class PyscriptSharedUtility:

    @staticmethod
    def fetch_collection_data(query: dict):

        collection_data = CollectionData.objects(__raw__= query)

        for value in collection_data:
            final_data = {}
            item = value.to_mongo().to_dict()
            collection_name = item.pop('collection_name', None)
            is_secure = item.pop('is_secure')
            is_non_editable=item.pop('is_non_editable')
            data = item.pop('data')
            data = DataProcessor.prepare_decrypted_data(data, is_secure)

            final_data["_id"] = str(item["_id"])
            final_data['collection_name'] = collection_name
            final_data['is_secure'] = is_secure
            final_data['is_non_editable']=is_non_editable
            final_data['timestamp'] = item.get("timestamp")
            final_data['data'] = data

            yield final_data

    @staticmethod
    def ensure_datetime(dt):
        if isinstance(dt, str):
            dt = isoparse(dt)
        elif isinstance(dt, date) and not isinstance(dt, datetime):
            dt = datetime.combine(dt, datetime.min.time()).replace(tzinfo=pytz.UTC)
        elif isinstance(dt, datetime):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=pytz.UTC)
        return dt

    @staticmethod
    def get_data(collection_name: str, user: str, data_filter: dict, kwargs=None, bot: Text = None):
        if not bot:
            raise Exception("Missing bot id")

        collection_name = collection_name.lower()
        query = {"bot": bot, "collection_name": collection_name}
        start_time = kwargs.pop("start_time", None) if kwargs else None
        end_time = kwargs.pop("end_time", None) if kwargs else None

        start_time = PyscriptSharedUtility.ensure_datetime(start_time) if start_time else None
        end_time = PyscriptSharedUtility.ensure_datetime(end_time) if end_time else None
        if start_time:
            query.setdefault("timestamp", {})["$gte"] = start_time
        if end_time:
            query.setdefault("timestamp", {})["$lte"] = end_time
        if data_filter.get("raw_query"):
            query.update(data_filter.get("raw_query"))
        else:
            query.update({f"data.{key}": value for key, value in data_filter.items()})
        data = list(PyscriptSharedUtility.fetch_collection_data(query))
        return {"data": data}

    @staticmethod
    def get_crud_metadata(collection_name: Text, user: Text,  bot: Text = None):
        if not bot:
            raise Exception("Missing bot id")

        if not collection_name:
            raise Exception("Missing collection name")

        metadata = DataProcessor.get_crud_metadata(user, bot, collection_name)
        return metadata


    @staticmethod
    def add_data(user: str, payload: dict, bot: str = None):
        if not bot:
            raise Exception("Missing bot id")

        collection_id = DataProcessor.save_collection_data(payload, user, bot)
        return {
            "message": "Record saved!",
            "data": {"_id": collection_id}
        }


    @staticmethod
    def update_data(collection_id: str, user: str, payload: dict, bot: str = None):
        if not bot:
            raise Exception("Missing bot id")

        collection_id = DataProcessor.update_collection_data(collection_id, payload, user, bot)
        return {
            "message": "Record updated!",
            "data": {"_id": collection_id}
        }


    @staticmethod
    def delete_data(collection_id: str, user: Text, bot: Text = None):
        if not bot:
            raise Exception("Missing bot id")

        DataProcessor.delete_collection_data(collection_id, bot, user)

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
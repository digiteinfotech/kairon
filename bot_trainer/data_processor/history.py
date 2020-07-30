from datetime import datetime, timedelta
from typing import Text

import pandas as pd
from loguru import logger
from pymongo import MongoClient
from rasa.core.tracker_store import MongoTrackerStore, DialogueStateTracker

from bot_trainer.exceptions import AppException
from bot_trainer.utils import Utility
from .processor import MongoProcessor


class ChatHistory:
    """Class contains logic for fetching history data and metrics from mongo tracker"""

    mongo_processor = MongoProcessor()

    @staticmethod
    def get_tracker_and_domain(bot: Text):
        """
        loads domain data and mongo tracker

        :param bot: bot id
        :return: tuple domain, tracker
        """
        domain = ChatHistory.mongo_processor.load_domain(bot)
        message = None
        try:
            endpoint = ChatHistory.mongo_processor.get_endpoints(bot)
            tracker = MongoTrackerStore(
                domain=domain,
                host=endpoint["tracker_endpoint"]["url"],
                db=endpoint["tracker_endpoint"]["db"],
                username=endpoint["tracker_endpoint"].get("username"),
                password=endpoint["tracker_endpoint"].get("password"),
            )
        except Exception as e:
            logger.info(e)
            message = "Loading test conversation! " + str(e)
            tracker = Utility.get_local_mongo_store(bot, domain)

        return domain, tracker, message

    @staticmethod
    def fetch_chat_history(bot: Text, sender, month: int = 1):
        """
        fetches chat history

        :param month: default is current month and max is last 6 months
        :param bot: bot id
        :param sender: history details for user
        :param latest_history: whether to fetch latest or complete history
        :return: list of conversations
        """
        events, message = ChatHistory.fetch_user_history(
            bot, sender, month=month
        )
        return list(ChatHistory.__prepare_data(bot, events)), message

    @staticmethod
    def fetch_chat_users(bot: Text, month: int = 1):
        """
        fetches user list who has conversation with the agent

        :param month: default is current month and max is last 6 months
        :param bot: bot id
        :return: list of user id
        """
        client, db_name, collection, message = ChatHistory.get_mongo_connection(bot)
        db = client.get_database(db_name)
        conversations = db.get_collection(collection)
        users = []
        try:
            values = conversations.find({"events.timestamp": {"$gte": Utility.get_timestamp_previous_month(month)}}, {"_id": 0, "sender_id": 1})
            users = [
                sender["sender_id"]
                for sender in values
            ]
        except Exception as e:
            raise AppException(e)
        finally:
            client.close()
        return users, message

    @staticmethod
    def __prepare_data(bot: Text, events, show_session=False):
        bot_action = None
        training_examples, ids = ChatHistory.mongo_processor.get_all_training_examples(
            bot
        )
        if events:
            event_list = ["user", "bot"]
            if show_session:
                event_list.append("session_started")
            for i in range(events.__len__()):
                event = events[i]
                if event["event"] in event_list:
                    result = {
                        "event": event["event"],
                        "time": datetime.fromtimestamp(event["timestamp"]).time(),
                        "date": datetime.fromtimestamp(event["timestamp"]).date(),
                    }

                    if event.get("text"):
                        result["text"] = event.get("text")
                        text_data = str(event.get("text")).lower()
                        result["is_exists"] = text_data in training_examples
                        if result["is_exists"]:
                            result["_id"] = ids[training_examples.index(text_data)]

                    if event["event"] == "user":
                        parse_data = event["parse_data"]
                        result["intent"] = parse_data["intent"]["name"]
                        result["confidence"] = parse_data["intent"]["confidence"]
                    elif event["event"] == "bot":
                        if bot_action:
                            result["action"] = bot_action

                    if result:
                        yield result
                else:
                    bot_action = (
                        event["name"] if event["event"] == "action" else None
                    )

    @staticmethod
    def fetch_user_history(bot: Text, sender_id: Text, month: int = 1):
        """
        loads list of conversation events from chat history

        :param month: default is current month and max is last 6 months
        :param bot: bot id
        :param sender_id: user id
        :param latest_history: whether to fetch latest history or complete history, default is latest
        :return: list of conversation events
        """
        client, db_name, collection, message = ChatHistory.get_mongo_connection(bot)
        try:
            db = client.get_database(db_name)
            conversations = db.get_collection(collection)
            values = list(conversations
                 .aggregate([{"$match": {"sender_id": sender_id, "events.timestamp": {"$gte": Utility.get_timestamp_previous_month(month)}}},
                             {"$unwind": "$events"},
                             {"$match": {"events.event": {"$in": ["user", "bot", "action"]}}},
                             {"$group": {"_id": None, "events": {"$push": "$events"}}},
                             {"$project": {"_id": 0, "events": 1}}])
                 )
            if values:
                return (
                    values[0]['events'],
                    message
                )
            return {}, message
        except Exception as e:
            raise AppException(e)
        finally:
            client.close()

    @staticmethod
    def visitor_hit_fallback(bot: Text, month: int = 1):
        """
        Counts the number of times, the agent was unable to provide a response to users

        :param bot: bot id
        :param month: default is current month and max is last 6 months
        :return: list of visitor fallback
        """

        client, database, collection, message = ChatHistory.get_mongo_connection(bot)
        db = client.get_database(database)
        conversations = db.get_collection(collection)
        values = []
        try:
            values = list(conversations.aggregate([{"$unwind": "$events"},
                                                  {"$match": {"events.event": "action", "events.timestamp": {"$gte": Utility.get_timestamp_previous_month(month)}}},
                                                  {"$group": {"_id": "$sender_id", "total_count": {"$sum": 1},
                                                              "events": {"$push": "$events"}}},
                                                  {"$unwind": "$events"},
                                                  {"$match": {
                                                      "events.name": {"$regex": ".*fallback*.", "$options": "$i"}}},
                                                  {"$group": {"_id": None, "total_count": {"$first": "$total_count"},
                                                              "fallback_count": {"$sum": 1}}},
                                                  {"$project": {"total_count": 1, "fallback_count": 1, "_id": 0}}
                                                  ], allowDiskUse=True))
        except Exception as e:
            message = str(e)
        finally:
            client.close()
        print(values)
        if not values:
            fallback_count = 0
            total_count = 0
        else:
            fallback_count = values[0]['fallback_count'] if values[0]['fallback_count'] else 0
            total_count = values[0]['total_count'] if values[0]['total_count'] else 0
        return (
            {"fallback_count": fallback_count, "total_count": total_count},
            message,
        )

    @staticmethod
    def conversation_steps(bot: Text, month: int = 1):
        """
        calculates the number of conversation steps between agent and users

        :param bot: bot id
        :param month: default is current month and max is last 6 months
        :return: list of conversation step count
        """
        client, database, collection, message = ChatHistory.get_mongo_connection(bot)
        db = client.get_database(database)
        conversations = db.get_collection(collection)
        values = list(conversations
             .aggregate([{"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
                         {"$match": {"events.event": {"$in": ["user", "bot"]},
                                     "events.timestamp": {"$gte": Utility.get_timestamp_previous_month(month)}}},
                         {"$group": {"_id": "$sender_id", "events": {"$push": "$events"},
                                     "allevents": {"$push": "$events"}}},
                         {"$unwind": "$events"},
                         {"$project": {
                             "_id": 1,
                             "events": 1,
                             "following_events": {
                                 "$arrayElemAt": [
                                     "$allevents",
                                     {"$add": [{"$indexOfArray": ["$allevents", "$events"]}, 1]}
                                 ]
                             }
                         }},
                         {"$project": {
                             "user_event": "$events.event",
                             "bot_event": "$following_events.event",
                         }},
                         {"$match": {"user_event": "user", "bot_event": "bot"}},
                         {"$group": {"_id": "$_id", "event": {"$sum": 1}}},
                         {"$project": {
                             "sender_id": "$_id",
                             "_id": 0,
                             "event": 1,
                         }}
                         ], allowDiskUse=True)
             )
        return values, message

    @staticmethod
    def conversation_time(bot: Text, month: int = 1):
        """
        calculates the duration of between agent and users

        :param bot: bot id
        :param month: default is current month and max is last 6 months
        :return: list of users duration
        """
        client, database, collection, message = ChatHistory.get_mongo_connection(bot)
        db = client.get_database(database)
        conversations = db.get_collection(collection)
        values = list(conversations
             .aggregate([{"$unwind": "$events"},
                         {"$match": {"events.event": {"$in": ["user", "bot"]},
                                     "events.timestamp": {"$gte": Utility.get_timestamp_previous_month(month)}}},
                         {"$group": {"_id": "$sender_id", "events": {"$push": "$events"},
                                     "allevents": {"$push": "$events"}}},
                         {"$unwind": "$events"},
                         {"$project": {
                             "_id": 1,
                             "events": 1,
                             "following_events": {
                                 "$arrayElemAt": [
                                     "$allevents",
                                     {"$add": [{"$indexOfArray": ["$allevents", "$events"]}, 1]}
                                 ]
                             }
                         }},
                         {"$project": {
                             "user_event": "$events.event",
                             "bot_event": "$following_events.event",
                             "time_diff": {
                                 "$subtract": ["$following_events.timestamp", "$events.timestamp"]
                             }
                         }},
                         {"$match": {"user_event": "user", "bot_event": "bot"}},
                         {"$group": {"_id": "$_id", "time": {"$sum": "$time_diff"}}},
                         {"$project": {
                             "sender_id": "$_id",
                             "_id": 0,
                             "time": 1,
                         }}
                         ], allowDiskUse=True)
             )
        return values, message

    @staticmethod
    def get_conversations(bot: Text):
        """
        fetches all the conversations between agent and users

        :param bot: bot id
        :return: list of conversations, message
        """
        _, tracker, message = ChatHistory.get_tracker_and_domain(bot)
        conversations = []
        try:
            conversations = list(tracker.conversations.find())
        except Exception as e:
            raise AppException(e)
        finally:
            tracker.client.close()
        return (conversations, message)

    @staticmethod
    def __fetch_history_metrics(bot: Text, show_session=False, filter_columns=None):
        filter_events = ["user", "bot"]
        if show_session:
            filter_events.append("session_started")

        if not filter_columns:
            filter_columns = [
                "sender_id",
                "event",
                "name",
                "text",
                "timestamp",
                "input_channel",
                "message_id",
            ]
        records, message = ChatHistory.get_conversations(bot)
        data_frame = pd.DataFrame(list(records))
        if not data_frame.empty:
            data_frame = data_frame.explode(column="events")
            data_frame = pd.concat(
                [
                    data_frame.drop(["events"], axis=1),
                    data_frame["events"].apply(pd.Series),
                ],
                axis=1,
            )
            data_frame.fillna("", inplace=True)
            data_frame["name"] = data_frame["name"].shift()
            data_frame = data_frame[data_frame["event"].isin(filter_events)]
            data_frame = data_frame[filter_columns]
        return data_frame, message

    @staticmethod
    def user_with_metrics(bot, month=1):
        """
        fetches user with the steps and time in conversation

        :param bot: bot id
        :param month: default is current month and max is last 6 months
        :return: list of users with step and time in conversation
        """
        client, database, collection, message = ChatHistory.get_mongo_connection(bot)
        db = client.get_database(database)
        conversations = db.get_collection(collection)
        users = []
        try:
            list(
                conversations.aggregate([{"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
                                         {"$match": {"events.event": {"$in": ["user", "bot"]},
                                                     "events.timestamp": {"$gte": Utility.get_timestamp_previous_month(month)}}},
                                         {"$group": {"_id": "$sender_id",
                                                     "latest_event_time": {"$first": "$latest_event_time"},
                                                     "events": {"$push": "$events"},
                                                     "allevents": {"$push": "$events"}}},
                                         {"$unwind": "$events"},
                                         {"$project": {
                                             "_id": 1,
                                             "events": 1,
                                             "latest_event_time": 1,
                                             "following_events": {
                                                 "$arrayElemAt": [
                                                     "$allevents",
                                                     {"$add": [{"$indexOfArray": ["$allevents", "$events"]}, 1]}
                                                 ]
                                             }
                                         }},
                                         {"$project": {
                                             "latest_event_time": 1,
                                             "user_timestamp": "$events.timestamp",
                                             "bot_timestamp": "$following_events.timestamp",
                                             "user_event": "$events.event",
                                             "bot_event": "$following_events.event",
                                             "time_diff": {
                                                 "$subtract": ["$following_events.timestamp", "$events.timestamp"]
                                             }
                                         }},
                                         {"$match": {"user_event": "user", "bot_event": "bot"}},
                                         {"$group": {"_id": "$_id",
                                                     "latest_event_time": {"$first": "$latest_event_time"},
                                                     "steps": {"$sum": 1}, "time": {"$sum": "$time_diff"}}},
                                         {"$project": {
                                             "sender_id": "$_id",
                                             "_id": 0,
                                             "steps": 1,
                                             "time": 1,
                                             "latest_event_time": 1,
                                         }}
                                         ], allowDiskUse=True))
        except Exception as e:
            logger.info(e)
        finally:
            client.close()
        return users, message

    @staticmethod
    def get_mongo_connection(bot: Text):
        message = None
        try:
            endpoint = ChatHistory.mongo_processor.get_endpoints(bot)
            client = MongoClient(host=endpoint["tracker_endpoint"]["url"],
                                 username=endpoint["tracker_endpoint"].get("username"),
                                 password=endpoint["tracker_endpoint"].get("password"))
            db_name = endpoint["tracker_endpoint"]['db']
            collection = "conversations"
        except Exception as e:
            message = "Loading test conversation! " + str(e)
            username, password, url, db_name = Utility.get_local_db()
            client = MongoClient(host=url,
                                 username=username,
                                 password=password)
            collection = bot
        return client, db_name, collection, message
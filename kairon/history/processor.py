from datetime import datetime
from typing import Text

from loguru import logger
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.actions.utils import ActionUtility


class HistoryProcessor:

    """
    Class contains logic for fetching history data and metrics from mongo tracker."""

    @staticmethod
    def get_mongo_connection():
        url = Utility.environment["tracker"]["url"]
        config = ActionUtility.extract_db_config(url)
        message = f"Loading host:{config.get('host')}, db:{config.get('db')}"
        client = MongoClient(host=url)
        return client, message

    @staticmethod
    def fetch_chat_history(collection: Text, sender, month: int = 1):

        """
        Fetches chat history.

        :param month: default is current month and max is last 6 months
        :param collection: collection to connect to
        :param sender: history details for user
        :return: list of conversations
        """
        events, message = HistoryProcessor.fetch_user_history(
            collection, sender, month=month
        )
        return list(HistoryProcessor.__prepare_data(events)), message

    @staticmethod
    def fetch_chat_users(collection: Text, month: int = 1):

        """
        Fetch users.

        Fetches user list who has conversation with the agent

        :param collection: collection to connect to
        :param month: default is current month and max is last 6 months
        :return: list of user id
        """
        client, message = HistoryProcessor.get_mongo_connection()
        message = ' '.join([message, f', collection: {collection}'])
        with client as client:
            db = client.get_database()
            conversations = db.get_collection(collection)
            try:
                values = conversations.find({"events.timestamp": {"$gte": Utility.get_timestamp_previous_month(month)}},
                                            {"_id": 0, "sender_id": 1})
                users = [
                    sender["sender_id"]
                    for sender in values
                ]
                return users, message
            except ServerSelectionTimeoutError as e:
                logger.error(e)
                raise AppException(f'Could not connect to tracker: {e}')
            except Exception as e:
                logger.error(e)
                raise AppException(e)

    @staticmethod
    def __prepare_data(events):
        bot_action = None
        if events:
            event_list = ["user", "bot"]
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
    def fetch_user_history(collection: Text, sender_id: Text, month: int = 1):

        """
        List conversation events.

        Loads list of conversation events from chat history

        :param month: default is current month and max is last 6 months
        :param collection: collection to connect to
        :param sender_id: user id
        :return: list of conversation events
        """
        client, message = HistoryProcessor.get_mongo_connection()
        message = ' '.join([message, f', collection: {collection}'])
        with client as client:
            try:
                db = client.get_database()
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
                return [], message
            except ServerSelectionTimeoutError as e:
                logger.error(e)
                raise AppException(f'Could not connect to tracker: {e}')
            except Exception as e:
                logger.error(e)
                raise AppException(e)

    @staticmethod
    def visitor_hit_fallback(collection: Text,
                             month: int = 1,
                             fallback_action: str = 'action_default_fallback',
                             nlu_fallback_action: str = None):

        """
        Fallback count for bot.

        Counts the number of times, the agent was unable to provide a response to users

        :param collection: collection to connect to
        :param month: default is current month and max is last 6 months
        :param fallback_action: fallback action configured for bot
        :param nlu_fallback_action: nlu fallback configured for bot
        :return: list of visitor fallback
        """
        client, message = HistoryProcessor.get_mongo_connection()
        message = ' '.join([message, f', collection: {collection}'])
        default_actions = Utility.load_default_actions()
        with client as client:
            db = client.get_database()
            conversations = db.get_collection(collection)
            fallback_counts, total_counts = [], []
            try:
                fallback_counts = list(conversations.aggregate([{"$unwind": "$events"},
                                                                {"$match": {"events.event": "action",
                                                                            "events.name": {"$nin": default_actions},
                                                                            "events.timestamp": {
                                                                        "$gte": Utility.get_timestamp_previous_month(
                                                                                    month)}}},
                                                                {"$match": {'$or': [{"events.name": fallback_action},
                                                                                    {
                                                                                "events.name": nlu_fallback_action}]}},
                                                                {"$group": {"_id": None,
                                                                            "fallback_count": {"$sum": 1}}},
                                                                {"$project": {"fallback_count": 1, "_id": 0}}
                                                                ], allowDiskUse=True))

                total_counts = list(conversations.aggregate([{"$unwind": "$events"},
                                                             {"$match": {"events.event": "action",
                                                                         "events.name": {"$nin": default_actions},
                                                                         "events.timestamp": {
                                                                         "$gte": Utility.get_timestamp_previous_month(
                                                                                 month)}}},
                                                             {"$group": {"_id": None, "total_count": {"$sum": 1}}},
                                                             {"$project": {"total_count": 1, "_id": 0}}
                                                             ], allowDiskUse=True))

            except Exception as e:
                logger.error(e)
                message = '\n'.join([message, str(e)])
            if not (fallback_counts and total_counts):
                fallback_count = 0
                total_count = 0
            else:
                fallback_count = fallback_counts[0]['fallback_count'] if fallback_counts[0]['fallback_count'] else 0
                total_count = total_counts[0]['total_count'] if total_counts[0]['total_count'] else 0
            return (
                {"fallback_count": fallback_count, "total_count": total_count},
                message,
            )

    @staticmethod
    def conversation_steps(collection: Text, month: int = 1):

        """
        Total conversation steps for bot.

        calculates the number of conversation steps between agent and users

        :param collection: collection to connect to
        :param month: default is current month and max is last 6 months
        :return: list of conversation step count
        """
        values = []
        client, message = HistoryProcessor.get_mongo_connection()
        message = ' '.join([message, f', collection: {collection}'])
        with client as client:
            db = client.get_database()
            conversations = db.get_collection(collection)
            try:
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
            except Exception as e:
                logger.error(e)
                message = '\n'.join([message, str(e)])

            return values, message

    @staticmethod
    def conversation_time(collection: Text, month: int = 1):

        """
        Total conversation time for bot.

        Calculates the duration of between agent and users.

        :param collection: collection to connect to
        :param month: default is current month and max is last 6 months
        :return: list of users duration
        """
        client, message = HistoryProcessor.get_mongo_connection()
        message = ' '.join([message, f', collection: {collection}'])
        db = client.get_database()
        conversations = db.get_collection(collection)
        values = []
        try:
            values = list(conversations.aggregate([{"$unwind": "$events"},
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
        except Exception as e:
            logger.error(e)
            message = '\n'.join([message, str(e)])
        return values, message

    @staticmethod
    def user_with_metrics(collection: Text, month=1):

        """
        Fetches user with the steps and time in conversation.

        :param collection: collection to connect to
        :param month: default is current month and max is last 6 months
        :return: list of users with step and time in conversation
        """
        client, message = HistoryProcessor.get_mongo_connection()
        message = ' '.join([message, f', collection: {collection}'])
        with client as client:
            db = client.get_database()
            conversations = db.get_collection(collection)
            users = []
            try:
                users = list(
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
                                             }},
                                             {"$sort": {"latest_event_time": -1}}
                                             ], allowDiskUse=True))
            except Exception as e:
                logger.error(e)
                message = '\n'.join([message, str(e)])
            return users, message

    @staticmethod
    def engaged_users(collection: Text, month: int = 1, conversation_limit: int = 10):

        """
        Counts the number of engaged users having a minimum number of conversation steps.

        :param collection: collection to connect to
        :param month: default is current month and max is last 6 months
        :param conversation_limit: conversation step number to determine engaged users
        :return: number of engaged users
        """

        client, message = HistoryProcessor.get_mongo_connection()
        message = ' '.join([message, f', collection: {collection}'])
        with client as client:
            db = client.get_database()
            conversations = db.get_collection(collection)
            values = []
            try:
                values = list(
                     conversations.aggregate([{"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
                                              {"$match": {"events.event": {"$in": ["user", "bot"]},
                                                          "events.timestamp": {
                                                              "$gte": Utility.get_timestamp_previous_month(month)}}
                                               },
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
                                             {"$match": {"event": {"$gte": conversation_limit}}},
                                             {"$group": {"_id": None, "event": {"$sum": 1}}},
                                             {"$project": {
                                              "_id": 0,
                                              "event": 1,
                                              }}
                                              ], allowDiskUse=True)
                                           )
            except Exception as e:
                logger.error(e)
                message = '\n'.join([message, str(e)])
            if not values:
                event = 0
            else:
                event = values[0]['event'] if values[0]['event'] else 0
            return (
                {"engaged_users": event},
                message
            )

    @staticmethod
    def new_users(collection: Text, month: int = 1):

        """
        Counts the number of new users of the bot.

        :param collection: collection to connect to
        :param month: default is current month and max is last 6 months
        :return: number of new users
        """

        client, message = HistoryProcessor.get_mongo_connection()
        message = ' '.join([message, f', collection: {collection}'])
        with client as client:
            db = client.get_database()
            conversations = db.get_collection(collection)
            values = []
            try:
                values = list(
                     conversations.aggregate([{"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
                                              {"$match": {"events.name": {"$regex": ".*session_start*.", "$options": "$i"}}},
                                              {"$group": {"_id": '$sender_id', "count": {"$sum": 1},
                                                          "latest_event_time": {"$first": "$latest_event_time"}}},
                                              {"$match": {"count": {"$lte": 1}}},
                                              {"$match": {"latest_event_time": {
                                                              "$gte": Utility.get_timestamp_previous_month(month)}}},
                                              {"$group": {"_id": None, "count": {"$sum": 1}}},
                                              {"$project": {"_id": 0, "count": 1}}
                                              ]))
            except Exception as e:
                logger.error(e)
                message = '\n'.join([message, str(e)])
            if not values:
                count = 0
            else:
                count = values[0]['count'] if values[0]['count'] else 0
            return (
                {"new_users": count},
                message
            )

    @staticmethod
    def successful_conversations(collection: Text,
                                 month: int = 1,
                                 fallback_action: str = 'action_default_fallback',
                                 nlu_fallback_action: str = 'nlu_fallback'):

        """
        Counts the number of successful conversations of the bot

        :param collection: collection to connect to
        :param month: default is current month and max is last 6 months
        :param fallback_action: fallback action configured for bot
        :param nlu_fallback_action: nlu fallback configured for bot
        :return: number of successful conversations
        """
        client, message = HistoryProcessor.get_mongo_connection()
        message = ' '.join([message, f', collection: {collection}'])
        with client as client:
            db = client.get_database()
            conversations = db.get_collection(collection)
            total = []
            fallback_count = []
            try:
                total = list(
                    conversations.aggregate([{"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
                                             {"$match": {"events.timestamp": {"$gte": Utility.get_timestamp_previous_month(month)}}},
                                             {"$group": {"_id": "$sender_id"}},
                                             {"$group": {"_id": None, "count": {"$sum": 1}}},
                                             {"$project": {"_id": 0, "count": 1}}
                                             ]))
            except Exception as e:
                logger.error(e)
                message = '\n'.join([message, str(e)])

            try:
                fallback_count = list(
                    conversations.aggregate([
                        {"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
                        {"$match": {"events.timestamp": {"$gte": Utility.get_timestamp_previous_month(month)}}},
                        {"$match": {'$or': [{"events.name": fallback_action}, {"events.name": nlu_fallback_action}]}},
                        {"$group": {"_id": "$sender_id"}},
                        {"$group": {"_id": None, "count": {"$sum": 1}}},
                        {"$project": {"_id": 0, "count": 1}}
                    ]))

            except Exception as e:
                logger.error(e)
                message = '\n'.join([message, str(e)])

            if not total:
                total_count = 0
            else:
                total_count = total[0]['count'] if total[0]['count'] else 0

            if not fallback_count:
                fallbacks_count = 0
            else:
                fallbacks_count = fallback_count[0]['count'] if fallback_count[0]['count'] else 0

            return (
                {"successful_conversations": total_count-fallbacks_count},
                message
            )

    @staticmethod
    def user_retention(collection: Text, month: int = 1):

        """
        Computes the user retention percentage of the bot

        :param collection: collection to connect to
        :param month: default is current month and max is last 6 months
        :return: user retention percentage
        """

        client, message = HistoryProcessor.get_mongo_connection()
        message = ' '.join([message, f', collection: {collection}'])
        with client as client:
            db = client.get_database()
            conversations = db.get_collection(collection)
            total = []
            repeating_users = []
            try:
                total = list(
                    conversations.aggregate([{"$match": {"latest_event_time": {
                        "$gte": Utility.get_timestamp_previous_month(month)}}},
                        {"$group": {"_id": None, "count": {"$sum": 1}}},
                        {"$project": {"_id": 0, "count": 1}}
                    ]))
            except Exception as e:
                logger.error(e)
                message = '\n'.join([message, str(e)])

            try:
                repeating_users = list(
                    conversations.aggregate([{"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
                                             {"$match": {"events.name": {"$regex": ".*session_start*.", "$options": "$i"}}},
                                             {"$group": {"_id": '$sender_id', "count": {"$sum": 1},
                                                         "latest_event_time": {"$first": "$latest_event_time"}}},
                                             {"$match": {"count": {"$gte": 2}}},
                                             {"$match": {"latest_event_time": {
                                                 "$gte": Utility.get_timestamp_previous_month(month)}}},
                                             {"$group": {"_id": None, "count": {"$sum": 1}}},
                                             {"$project": {"_id": 0, "count": 1}}
                                             ]))

            except Exception as e:
                logger.error(e)
                message = '\n'.join([message, str(e)])

            if not total:
                total_count = 1
            else:
                total_count = total[0]['count'] if total[0]['count'] else 1

            if not repeating_users:
                repeat_count = 0
            else:
                repeat_count = repeating_users[0]['count'] if repeating_users[0]['count'] else 0

            return (
                {"user_retention": 100*(repeat_count/total_count)},
                message
            )

    @staticmethod
    def engaged_users_range(collection: Text, month: int = 6, conversation_limit: int = 10):

        """
        Computes the trend for engaged user count

        :param collection: collection to connect to
        :param month: default is 6 months
        :param conversation_limit: conversation step number to determine engaged users
        :return: dictionary of counts of engaged users for the previous months
        """

        client, message = HistoryProcessor.get_mongo_connection()
        message = ' '.join([message, f', collection: {collection}'])
        with client as client:
            db = client.get_database()
            conversations = db.get_collection(collection)
            engaged = []
            try:
                engaged = list(
                    conversations.aggregate([{"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
                                          {"$match": {"events.event": {"$in": ["user", "bot"]},
                                                      "events.timestamp": {
                                                          "$gte": Utility.get_timestamp_previous_month(month)}}
                                           },

                                          {"$addFields": {"month": {
                                              "$month": {"$toDate": {"$multiply": ["$events.timestamp", 1000]}}}}},

                                          {"$group": {"_id": {"month": "$month", "sender_id": "$sender_id"},
                                                      "events": {"$push": "$events"},
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
                                          {"$match": {"event": {"$gte": conversation_limit}}},
                                          {"$group": {"_id": "$_id.month", "count": {"$sum": 1}}},
                                          {"$project": {
                                              "_id": 1,
                                              "count": 1,
                                          }}
                                          ], allowDiskUse=True)
                )
            except Exception as e:
                logger.error(e)
                message = '\n'.join([message, str(e)])
            engaged_users = {d['_id']: d['count'] for d in engaged}
            return (
                {"engaged_user_range": engaged_users},
                message
            )

    @staticmethod
    def new_users_range(collection: Text, month: int = 6):

        """
        Computes the trend for new user count

        :param collection: collection to connect to
        :param month: default is 6 months
        :return: dictionary of counts of new users for the previous months
        """

        client, message = HistoryProcessor.get_mongo_connection()
        message = ' '.join([message, f', collection: {collection}'])
        with client as client:
            db = client.get_database()
            conversations = db.get_collection(collection)
            values = []
            try:
                values = list(
                    conversations.aggregate([{"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
                                          {"$match": {
                                              "events.name": {"$regex": ".*session_start*.", "$options": "$i"}}},
                                          {"$group": {"_id": '$sender_id', "count": {"$sum": 1},
                                                      "latest_event_time": {"$first": "$latest_event_time"}}},
                                          {"$match": {"count": {"$lte": 1}}},
                                          {"$match": {"latest_event_time": {
                                              "$gte": Utility.get_timestamp_previous_month(month)}}},
                                          {"$addFields": {"month": {
                                              "$month": {"$toDate": {"$multiply": ["$latest_event_time", 1000]}}}}},

                                          {"$group": {"_id": "$month", "count": {"$sum": 1}}},
                                          {"$project": {"_id": 1, "count": 1}}
                                          ]))
            except Exception as e:
                logger.error(e)
                message = '\n'.join([message, str(e)])
            new_users = {d['_id']: d['count'] for d in values}
            return (
                {"new_user_range": new_users},
                message
            )

    @staticmethod
    def successful_conversation_range(collection: Text,
                                      month: int = 6,
                                      fallback_action: str = 'action_default_fallback',
                                      nlu_fallback_action: str = 'nlu_fallback'):

        """
        Computes the trend for successful conversation count

        :param collection: collection to connect to
        :param month: default is 6 months
        :param fallback_action: fallback action configured for bot
        :param nlu_fallback_action: nlu fallback configured for bot
        :return: dictionary of counts of successful bot conversations for the previous months
        """
        client, message = HistoryProcessor.get_mongo_connection()
        message = ' '.join([message, f', collection: {collection}'])
        with client as client:
            db = client.get_database()
            conversations = db.get_collection(collection)
            total = []
            fallback_count = []
            try:
                total = list(
                    conversations.aggregate([
                        {"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
                        {"$match": {"events.timestamp": {"$gte": Utility.get_timestamp_previous_month(month)}}},
                        {"$addFields": {"month": {"$month": {"$toDate": {"$multiply": ["$events.timestamp", 1000]}}}}},

                        {"$group": {"_id": {"month": "$month", "sender_id": "$sender_id"}}},
                        {"$group": {"_id": "$_id.month", "count": {"$sum": 1}}},
                        {"$project": {"_id": 1, "count": 1}}
                    ]))

                fallback_count = list(
                    conversations.aggregate([
                        {"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
                        {"$match": {"events.timestamp": {"$gte": Utility.get_timestamp_previous_month(month)}}},
                        {"$match": {'$or': [{"events.name": fallback_action}, {"events.name": nlu_fallback_action}]}},
                        {"$addFields": {"month": {"$month": {"$toDate": {"$multiply": ["$events.timestamp", 1000]}}}}},

                        {"$group": {"_id": {"month": "$month", "sender_id": "$sender_id"}}},
                        {"$group": {"_id": "$_id.month", "count": {"$sum": 1}}},
                        {"$project": {"_id": 1, "count": 1}}
                    ]))
            except Exception as e:
                logger.error(e)
                message = '\n'.join([message, str(e)])
            total_users = {d['_id']: d['count'] for d in total}
            final_fallback = {d['_id']: d['count'] for d in fallback_count}
            final_fallback = {k: final_fallback.get(k, 0) for k in total_users.keys()}
            success = {k: total_users[k] - final_fallback[k] for k in total_users.keys()}
            return (
                {"success_conversation_range": success},
                message
            )

    @staticmethod
    def user_retention_range(collection: Text, month: int = 6):

        """
        Computes the trend for user retention percentages

        :param collection: collection to connect to
        :param month: default is 6 months
        :return: dictionary of user retention percentages for the previous months
        """

        client, message = HistoryProcessor.get_mongo_connection()
        message = ' '.join([message, f', collection: {collection}'])
        with client as client:
            db = client.get_database()
            conversations = db.get_collection(collection)
            total = []
            repeating_users = []
            try:
                total = list(
                    conversations.aggregate([{"$match": {"latest_event_time": {
                        "$gte": Utility.get_timestamp_previous_month(month)}}},
                        {"$addFields": {"month": {"$month": {"$toDate": {"$multiply": ["$latest_event_time", 1000]}}}}},
                        {"$group": {"_id": "$month", "count": {"$sum": 1}}},
                        {"$project": {"_id": 1, "count": 1}}
                    ]))

                repeating_users = list(
                    conversations.aggregate([{"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
                                             {"$match": {
                                                 "events.name": {"$regex": ".*session_start*.", "$options": "$i"}}},
                                             {"$group": {"_id": '$sender_id', "count": {"$sum": 1},
                                                         "latest_event_time": {"$first": "$latest_event_time"}}},
                                             {"$match": {"count": {"$gte": 2}}},
                                             {"$match": {"latest_event_time": {
                                                 "$gte": Utility.get_timestamp_previous_month(month)}}},
                                             {"$addFields": {"month": {
                                                 "$month": {"$toDate": {"$multiply": ["$latest_event_time", 1000]}}}}},
                                             {"$group": {"_id": "$month", "count": {"$sum": 1}}},
                                             {"$project": {"_id": 1, "count": 1}}
                                             ]))
            except Exception as e:
                logger.error(e)
                message = '\n'.join([message, str(e)])
            total_users = {d['_id']: d['count'] for d in total}
            repeat_users = {d['_id']: d['count'] for d in repeating_users}
            retention = {k: 100 * (repeat_users[k] / total_users[k]) for k in repeat_users.keys()}
            return (
                {"retention_range": retention},
                message
            )

    @staticmethod
    def fallback_count_range(collection: Text,
                             month: int = 6,
                             fallback_action: str = 'action_default_fallback',
                             nlu_fallback_action: str = 'nlu_fallback'):

        """
        Computes the trend for fallback counts
        :param collection: collection to connect to
        :param month: default is 6 months
        :param fallback_action: fallback action configured for bot
        :param nlu_fallback_action: nlu fallback configured for bot
        :return: dictionary of fallback counts for the previous months
        """
        client, message = HistoryProcessor.get_mongo_connection()
        message = ' '.join([message, f', collection: {collection}'])
        with client as client:
            db = client.get_database()
            conversations = db.get_collection(collection)
            action_counts = []
            fallback_counts = []
            try:

                fallback_counts = list(
                    conversations.aggregate([{"$unwind": {"path": "$events"}},
                                             {"$match": {"events.event": "action",
                                                         "events.timestamp": {
                                                             "$gte": Utility.get_timestamp_previous_month(
                                                                 month)}}},
                                             {"$match": {'$or': [{"events.name": fallback_action},
                                                                 {"events.name": nlu_fallback_action}]}},
                                             {"$addFields": {"month": {
                                                 "$month": {"$toDate": {"$multiply": ["$events.timestamp", 1000]}}}}},
                                             {"$group": {"_id": "$month", "count": {"$sum": 1}}},
                                             {"$project": {"_id": 1, "count": 1}}
                                             ]))
                action_counts = list(
                    conversations.aggregate([{"$unwind": {"path": "$events"}},
                                             {"$match": {"$and": [{"events.event": "action"},
                                             {"events.name": {"$nin": ['action_listen', 'action_session_start']}}]}},
                                             {"$match": {"events.timestamp": {
                                              "$gte": Utility.get_timestamp_previous_month(month)}}},
                                             {"$addFields": {"month": {
                                              "$month": {"$toDate": {"$multiply": ["$events.timestamp", 1000]}}}}},
                                             {"$group": {"_id": "$month", "total_count": {"$sum": 1}}},
                                             {"$project": {"_id": 1, "total_count": 1}}
                                             ]))
            except Exception as e:
                logger.error(e)
                message = '\n'.join([message, str(e)])
            action_count = {d['_id']: d['total_count'] for d in action_counts}
            fallback_count = {d['_id']: d['count'] for d in fallback_counts}
            final_trend = {k: 100*(fallback_count.get(k)/action_count.get(k)) for k in list(fallback_count.keys())}
            return (
                {"fallback_counts": final_trend},
                message
            )

    @staticmethod
    def flatten_conversations(collection: Text, month: int = 3, sort_by_date: bool = True):

        """
        Retrieves the flattened conversation data of the bot
        :param collection: collection to connect to
        :param month: default is 3 months
        :param sort_by_date: This flag sorts the records by timestamp if set to True
        :return: dictionary of the bot users and their conversation data
        """

        client, message = HistoryProcessor.get_mongo_connection()
        message = ' '.join([message, f', collection: {collection}'])
        with client as client:
            db = client.get_database()
            conversations = db.get_collection(collection)
            user_data = []
            try:

                user_data = list(
                    conversations.aggregate(
                        [{"$match": {"latest_event_time": {"$gte": Utility.get_timestamp_previous_month(month)}}},
                         {"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
                         {"$match": {"$or": [{"events.event": {"$in": ['bot', 'user']}},
                         {"$and": [{"events.event": "action"},
                         {"events.name": {"$nin": ['action_listen', 'action_session_start']}}]}]}},
                         {"$match": {"events.timestamp": {"$gte": Utility.get_timestamp_previous_month(month)}}},
                         {"$group": {"_id": "$sender_id", "events": {"$push": "$events"},
                            "allevents": {"$push": "$events"}}},
                         {"$unwind": "$events"},
                         {"$match": {"events.event": 'user'}},
                         {"$group": {"_id": "$_id", "events": {"$push": "$events"}, "user_array":
                         {"$push": "$events"}, "all_events": {"$first": "$allevents"}}},
                         {"$unwind": "$events"},
                         {"$project": {"user_input": "$events.text", "intent": "$events.parse_data.intent.name",
                            "message_id": "$events.message_id",
                            "timestamp": "$events.timestamp",
                            "confidence": "$events.parse_data.intent.confidence",
                            "action_bot_array": {
                            "$cond": [{"$gte": [{"$indexOfArray": ["$all_events", {"$arrayElemAt":
                            ["$user_array", {"$add": [{"$indexOfArray": ["$user_array","$events"]}, 1]}]}]},
                         {"$indexOfArray": ["$all_events", "$events"]}]},
                         {"$slice": ["$all_events", {"$add": [{"$indexOfArray":["$all_events", "$events"]}, 1]},
                         {"$subtract": [{"$subtract": [{"$indexOfArray": ["$all_events", {"$arrayElemAt":
                            ["$user_array", {"$add": [{"$indexOfArray": ["$user_array", "$events"]}, 1]}]}]},
                         {"$indexOfArray": ["$all_events", "$events"]}]}, 1]}]}, {"$slice": ["$all_events",
                         {"$add": [{"$indexOfArray": ["$all_events", "$events"]}, 1]}, 100]}]}}},
                         {"$addFields": {"t_stamp": {"$toDate": {"$multiply": ["$timestamp", 1000]}}}},
                         {"$project": {"user_input": 1, "intent": 1, "confidence": 1, "action": "$action_bot_array.name"
                          , "timestamp": "$t_stamp", "bot_response": "$action_bot_array.text", "sort": {
                             "$cond": {"if": sort_by_date, "then": "$t_stamp", "else": "_id"}}}},
                         {"$sort": {"sort": -1}},
                         {"$project": {"user_input": 1, "intent": 1, "confidence": 1, "action": 1,
                                       "timestamp": {'$dateToString': {'format': "%d-%m-%Y %H:%M:%S", 'date': '$timestamp'}}, "bot_response": 1}}
                         ], allowDiskUse=True))
            except Exception as e:
                logger.error(e)
                message = '\n'.join([message, str(e)])

            return (
                {"conversation_data": user_data},
                message
            )

    @staticmethod
    def total_conversation_range(collection: Text, month: int = 6):

        """
        Computes the trend for conversation count

        :param collection: collection to connect to
        :param month: default is 6 months
        :return: dictionary of counts of bot conversations for the previous months
        """

        client, message = HistoryProcessor.get_mongo_connection()
        message = ' '.join([message, f', collection: {collection}'])
        with client as client:
            db = client.get_database()
            conversations = db.get_collection(collection)
            total = []
            try:
                total = list(
                    conversations.aggregate([
                        {"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
                        {"$match": {"events.timestamp": {"$gte": Utility.get_timestamp_previous_month(month)}}},
                        {"$addFields": {"month": {"$month": {"$toDate": {"$multiply": ["$events.timestamp", 1000]}}}}},

                        {"$group": {"_id": {"month": "$month", "sender_id": "$sender_id"}}},
                        {"$group": {"_id": "$_id.month", "count": {"$sum": 1}}},
                        {"$project": {"_id": 1, "count": 1}}
                    ]))

            except Exception as e:
                logger.error(e)
                message = '\n'.join([message, str(e)])
            total_users = {d['_id']: d['count'] for d in total}
            return (
                {"total_conversation_range": total_users},
                message
            )

    @staticmethod
    def top_n_intents(collection: Text, month: int = 1, top_n: int = 10):

        """
        Fetches the top n identified intents of the bot for a given time

        :param month: default is current month and max is last 6 months
        :param collection: collection to connect to
        :param top_n: The first n number of most occurring intents
        :return: list of intents and their counts
        """
        client, message = HistoryProcessor.get_mongo_connection()
        with client as client:
            try:
                db = client.get_database()
                conversations = db.get_collection(collection)
                values = list(
                    conversations.aggregate([
                        {"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
                        {"$match": {"events.timestamp": {"$gte": Utility.get_timestamp_previous_month(month)}}},
                        {"$project": {"intent": "$events.parse_data.intent.name", "_id": 0}},
                        {"$group": {"_id": "$intent", "count": {"$sum": 1}}},
                        {"$match": {"_id": {"$ne": None}}},
                        {"$sort": {"count": -1}},
                        {"$limit": top_n}
                    ]))

                return values, message
            except Exception as e:
                logger.error(e)
                raise AppException(e)

    @staticmethod
    def top_n_actions(collection: Text, month: int = 1, top_n: int = 10):

        """
        Fetches the top n identified actions of the bot for a given time

        :param month: default is current month and max is last 6 months
        :param collection: collection to connect to
        :param top_n: The first n number of most occurring actions
        :return: list of actions and their counts
        """
        client, message = HistoryProcessor.get_mongo_connection()
        with client as client:
            try:
                db = client.get_database()
                conversations = db.get_collection(collection)
                values = list(
                    conversations.aggregate([
                        {"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
                        {"$match": {"events.timestamp": {"$gte": Utility.get_timestamp_previous_month(month)}}},
                        {"$match": {"events.event": "action"}},
                        {"$match": {"events.name": {"$nin": ['action_listen', 'action_session_start']}}},
                        {"$project": {"action": "$events.name", "_id": 0}},
                        {"$group": {"_id": "$action", "count": {"$sum": 1}}},
                        {"$sort": {"count": -1}},
                        {"$limit": top_n}
                      ]))

                return values, message
            except Exception as e:
                logger.error(e)
                raise AppException(e)

    @staticmethod
    def average_conversation_step_range(collection: Text, month: int = 6):

        """
        Computes the trend for average conversation step count

        :param collection: collection to connect to
        :param month: default is 6 months
        :return: dictionary of counts of average conversation step for the previous months
        """
        client, message = HistoryProcessor.get_mongo_connection()
        message = ' '.join([message, f', collection: {collection}'])
        with client as client:
            db = client.get_database()
            conversations = db.get_collection(collection)
            total = []
            steps = []
            try:
                steps = list(conversations.aggregate([{"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
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
                                             "timestamp": "$events.timestamp",
                                             "user_event": "$events.event",
                                             "bot_event": "$following_events.event",
                                         }},
                                         {"$match": {"user_event": "user", "bot_event": "bot"}},
                                         {"$addFields": {
                                             "month": {"$month": {"$toDate": {"$multiply": ["$timestamp", 1000]}}}}},
                                         {"$group": {"_id": "$month", "event": {"$sum": 1}}}
                                         ], allowDiskUse=True)
                             )

                total = list(
                    conversations.aggregate([
                        {"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
                        {"$match": {"events.timestamp": {"$gte": Utility.get_timestamp_previous_month(month)}}},
                        {"$addFields": {"month": {"$month": {"$toDate": {"$multiply": ["$events.timestamp", 1000]}}}}},

                        {"$group": {"_id": {"month": "$month", "sender_id": "$sender_id"}}},
                        {"$group": {"_id": "$_id.month", "count": {"$sum": 1}}},
                        {"$project": {"_id": 1, "count": 1}}
                    ]))
            except Exception as e:
                logger.error(e)
                message = '\n'.join([message, str(e)])
            conv_steps = {d['_id']: d['event'] for d in steps}
            user_count = {d['_id']: d['count'] for d in total}
            conv_steps = {k: conv_steps.get(k, 0) for k in user_count.keys()}
            avg_conv_steps = {k: conv_steps[k] / user_count[k] for k in user_count.keys()}
            return (
                {"Conversation_step_range": avg_conv_steps},
                message
            )

    @staticmethod
    def word_cloud(collection: Text, u_bound=1, l_bound=0, stopword_list=None, month=1):

        """
        Creates the string that is necessary for the word cloud formation

        :param month: default is current month and max is last 6 months
        :param collection: collection to connect to
        :param u_bound: The upper bound for the slider to filter the words for the wordcloud
        :param l_bound: The lower bound for the slider to filter the words for the wordcloud
        :param stopword_list: The stopword list that is used to filter extra words
        :return: the string for word cloud formation
        """

        from nltk.corpus import stopwords
        if stopword_list is None:
            stopword_list = []
        client, message = HistoryProcessor.get_mongo_connection()
        with client as client:
            try:
                db = client.get_database()
                conversations = db.get_collection(collection)
                word_list = list(conversations.aggregate(
                    [{"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
                     {"$match": {"events.timestamp": {"$gte": Utility.get_timestamp_previous_month(month)}}},
                     {"$match": {"events.event": 'user'}},
                     {"$project": {"user_input": "$events.text", "_id": 0}},
                     {"$group": {"_id": None, "input": {"$push": "$user_input"}}},
                     {"$project": {"input": 1, "_id": 0}}
                     ], allowDiskUse=True))

                if word_list:
                    if u_bound < l_bound:
                        raise AppException("Upper bound cannot be lesser than lower bound")
                    unique_string = (" ").join(word_list[0]['input']).lower()
                    unique_string = unique_string.replace('?', '')
                    wordlist = unique_string.split()
                    stops = set(stopwords.words('english'))
                    stops.update(stopword_list)
                    wordlist = [word for word in wordlist if word not in stops]
                    freq_dict = Utility.word_list_to_frequency(wordlist)
                    sorted_dict = Utility.sort_frequency_dict(freq_dict)
                    upper_bound, lower_bound = round((1 - u_bound) * len(sorted_dict)), round((1 - l_bound) * len(sorted_dict))
                    filtered_words = [word[1] for word in sorted_dict[upper_bound:lower_bound]]
                    word_cloud_string = (" ").join([word for word in wordlist if word in filtered_words])
                    return word_cloud_string, message
                else:
                    return "", message

            except Exception as e:
                logger.error(e)
                raise AppException(e)

    @staticmethod
    def user_input_count(collection: Text, month: int = 6):

        """
        Gets the user inputs along with their frequencies

        :param collection: collection to connect to
        :param month: default is 6 months
        :return: dictionary of counts of user inputs for the given duration
        """

        client, message = HistoryProcessor.get_mongo_connection()
        message = ' '.join([message, f', collection: {collection}'])
        with client as client:
            db = client.get_database()
            conversations = db.get_collection(collection)
            user_input = []
            try:
                user_input = list(conversations.aggregate(
                    [{"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
                     {"$match": {"events.timestamp": {"$gte": Utility.get_timestamp_previous_month(month)}}},
                     {"$match": {"events.event": 'user'}},
                     {"$project": {"user_input": {"$toLower": "$events.text"}, "_id": 0}},
                     {"$group": {"_id": "$user_input", "count": {"$sum": 1}}},
                     {"$sort": {"count": -1}}
                     ], allowDiskUse=True))
            except Exception as e:
                logger.error(e)
                message = '\n'.join([message, str(e)])
            return (
                user_input, message
            )

    @staticmethod
    def average_conversation_time_range(collection: Text, month: int = 6):

        """
        Computes the trend for average conversation time

        :param collection: collection to connect to
        :param month: default is 6 months
        :return: dictionary of counts of average conversation time for the previous months
        """
        client, message = HistoryProcessor.get_mongo_connection()
        message = ' '.join([message, f', collection: {collection}'])
        with client as client:
            db = client.get_database()
            conversations = db.get_collection(collection)
            total = []
            time = []
            try:
                time = list(conversations.aggregate([{"$unwind": "$events"},
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
                                 "timestamp": "$events.timestamp",
                                 "user_event": "$events.event",
                                 "bot_event": "$following_events.event",
                                 "time_diff": {
                                     "$subtract": ["$following_events.timestamp", "$events.timestamp"]
                                 }
                             }},
                             {"$match": {"user_event": "user", "bot_event": "bot"}},
                           {"$addFields": {"month": {"$month": {"$toDate": {"$multiply": ["$timestamp", 1000]}}}}},
                            {"$group": {"_id": "$month", "time": {"$sum": "$time_diff"}}}
                             ], allowDiskUse=True)
                 )

                total = list(
                    conversations.aggregate([
                        {"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
                        {"$match": {"events.timestamp": {"$gte": Utility.get_timestamp_previous_month(month)}}},
                        {"$addFields": {"month": {"$month": {"$toDate": {"$multiply": ["$events.timestamp", 1000]}}}}},

                        {"$group": {"_id": {"month": "$month", "sender_id": "$sender_id"}}},
                        {"$group": {"_id": "$_id.month", "count": {"$sum": 1}}},
                        {"$project": {"_id": 1, "count": 1}}
                    ]))
            except Exception as e:
                logger.error(e)
                message = '\n'.join([message, str(e)])
            conv_time = {d['_id']: d['time'] for d in time}
            user_count = {d['_id']: d['count'] for d in total}
            conv_time = {k: conv_time.get(k, 0) for k in user_count.keys()}
            avg_conv_time = {k: conv_time[k] / user_count[k] for k in user_count.keys()}
            return (
                {"Conversation_time_range": avg_conv_time},
                message
            )

    @staticmethod
    def user_fallback_dropoff(collection: Text, month: int = 6,
                              fallback_action: str = 'action_default_fallback',
                              nlu_fallback_action: str = 'nlu_fallback'):

        """
        Computes the list of users that dropped off after encountering fallback

        :param collection: collection to connect to
        :param fallback_action: fallback action configured for bot
        :param nlu_fallback_action: nlu fallback configured for bot
        :param month: default is 6 months
        :return: dictionary of users and their dropoff counts
        """
        client, message = HistoryProcessor.get_mongo_connection()
        message = ' '.join([message, f', collection: {collection}'])
        with client as client:
            db = client.get_database()
            conversations = db.get_collection(collection)
            new_session, single_session = [], []
            try:
                new_session = list(
                    conversations.aggregate([{"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
                                             {"$match": {"events.timestamp": {
                                                 "$gte": Utility.get_timestamp_previous_month(month)},
                                                         "events.name": {"$ne": "action_listen"},
                                                         "events.event": {
                                                             "$nin": ["session_started", "restart", "bot"]}}},
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
                                             {"$match": {'$or': [{"events.name": fallback_action},
                                                                 {"events.name": nlu_fallback_action}],
                                                         "following_events.name": "action_session_start"}},
                                             {"$group": {"_id": "$_id", "count": {"$sum": 1}}},
                                             {"$sort": {"count": -1}}
                                             ], allowDiskUse=True)
                )

                single_session = list(
                    conversations.aggregate([{"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
                                             {"$match": {"events.timestamp": {
                                                 "$gte": Utility.get_timestamp_previous_month(month)},
                                                         "events.name": {"$ne": "action_listen"},
                                                         "events.event": {
                                                             "$nin": ["session_started", "restart", "bot"]}}},
                                             {"$group": {"_id": "$sender_id", "events": {"$push": "$events"}}},
                                             {"$addFields": {"last_event": {"$last": "$events"}}},
                                             {"$match": {'$or': [{"last_event.name": fallback_action},
                                                                 {"last_event.name": nlu_fallback_action}]}},
                                             {"$addFields": {"count": 1}},
                                             {"$project": {"_id": 1, "count": 1}}
                                             ], allowDiskUse=True)
                )
            except Exception as e:
                logger.error(e)
                message = '\n'.join([message, str(e)])
            new_session = {d['_id']: d['count'] for d in new_session}
            single_session = {d['_id']: d['count'] for d in single_session}
            for record in single_session:
                if record in new_session:
                    new_session[record] = new_session[record] + 1
                else:
                    new_session[record] = single_session[record]
            return (
                {"Dropoff_list": new_session},
                message
            )

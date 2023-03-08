from datetime import datetime, date, timedelta
from typing import Text

from loguru import logger
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

from kairon.shared.utils import Utility
from kairon.exceptions import AppException


class HistoryProcessor:
    """
    Class contains logic for fetching history data and metrics from mongo tracker."""

    @staticmethod
    def get_mongo_connection():
        url = Utility.environment["tracker"]["url"]
        return MongoClient(host=url)

    @staticmethod
    def fetch_chat_history(collection: Text, sender,
                           from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                           to_date: date = datetime.utcnow().date()):

        """
        Fetches chat history.

        :param from_date: default is last month date
        :param to_date: default is current month today date
        :param collection: collection to connect to
        :param sender: history details for user
        :return: list of conversations
        """
        Utility.validate_from_date_and_to_date(from_date, to_date)
        events, message = HistoryProcessor.fetch_user_history(
            collection, sender, from_date=from_date, to_date=to_date
        )
        return list(HistoryProcessor.__prepare_data(events)), message

    @staticmethod
    def fetch_chat_users(collection: Text,
                         from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                         to_date: date = datetime.utcnow().date()):

        """
        Fetch users.

        Fetches user list who has conversation with the agent

        :param collection: collection to connect to
        :param from_date: default is last month date
        :param to_date: default is current month today date
        :return: list of user id
        """
        Utility.validate_from_date_and_to_date(from_date, to_date)
        client = HistoryProcessor.get_mongo_connection()
        with client as client:
            db = client.get_database()
            conversations = db.get_collection(collection)
            try:
                values = conversations.distinct(key="sender_id",
                                                filter={"event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                                            "$lte": Utility.get_timestamp_from_date(to_date)}})
                return values, None
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
                        result['data'] = event['data']
                        if event.get('metadata'):
                            result["action"] = event['metadata']['utter_action']
                        else:
                            result["action"] = bot_action

                    if result:
                        yield result
                else:
                    bot_action = (
                        event["name"] if event["event"] == "action" else None
                    )

    @staticmethod
    def fetch_user_history(collection: Text, sender_id: Text,
                           from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                           to_date: date = datetime.utcnow().date()):

        """
        List conversation events.

        Loads list of conversation events from chat history

        :param from_date: default is last month date
        :param to_date: default is current month date
        :param collection: collection to connect to
        :param sender_id: user id
        :return: list of conversation events
        """
        try:
            client = HistoryProcessor.get_mongo_connection()
            message = None
            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                values = list(conversations
                              .aggregate([{"$match": {"sender_id": sender_id, "event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                                                                  "$lte": Utility.get_timestamp_from_date(to_date)}}},
                                          {"$match": {"event.event": {"$in": ["user", "bot", "action"]}}},
                                          {"$group": {"_id": None, "events": {"$push": "$event"}}},
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
                             from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                             to_date: date = datetime.utcnow().date(),
                             fallback_action: str = 'action_default_fallback',
                             nlu_fallback_action: str = None):

        """
        Fallback count for bot.

        Counts the number of times, the agent was unable to provide a response to users

        :param collection: collection to connect to
        :param from_date: default is last month date
        :param to_date: default is current month today date
        :param fallback_action: fallback action configured for bot
        :param nlu_fallback_action: nlu fallback configured for bot
        :return: list of visitor fallback
        """
        Utility.validate_from_date_and_to_date(from_date, to_date)
        fallback_counts, total_counts = [], []
        message = None
        try:
            client = HistoryProcessor.get_mongo_connection()
            default_actions = Utility.load_default_actions()
            with client as clt:
                db = clt.get_database()
                conversations = db.get_collection(collection)
                fallback_counts = list(conversations.aggregate([
                                                                {"$match": {"event.event": "action",
                                                                            "event.name": {"$in": [fallback_action, nlu_fallback_action]},
                                                                            "event.timestamp": {
                                                                                "$gte": Utility.get_timestamp_from_date(from_date),
                                                                                "$lte": Utility.get_timestamp_from_date(to_date)}
                                                                            }
                                                                 },
                                                                {"$group": {"_id": None, "fallback_count": {"$sum": 1}}},
                                                                {"$project": {"fallback_count": 1, "_id": 0}}
                                                                ], allowDiskUse=True))

                total_counts = list(conversations.aggregate([
                                                             {"$match": {"event.event": "user",
                                                                         "event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                                                             "$lte": Utility.get_timestamp_from_date(to_date)
                                                                                             }
                                                                         }
                                                              },
                                                             {"$group": {"_id": None, "total_count": {"$sum": 1}}},
                                                             {"$project": {"total_count": 1, "_id": 0}}
                                                             ], allowDiskUse=True))

        except Exception as e:
            logger.error(e)
            message = str(e)
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
    def conversation_steps(collection: Text,
                           from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                           to_date: date = datetime.utcnow().date()):

        """
        Total conversation steps for bot.

        calculates the number of conversation steps between agent and users

        :param collection: collection to connect to
        :param from_date: default is last month date
        :param to_date: default is current month today date
        :return: list of conversation step count
        """
        Utility.validate_from_date_and_to_date(from_date, to_date)
        values = []
        try:
            client = HistoryProcessor.get_mongo_connection()
            message = None
            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                values = list(conversations
                              .aggregate([{"$match": {"event.event": "user",
                                                      "event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                                          "$lte": Utility.get_timestamp_from_date(to_date)}
                                                      }
                                          },
                                          {"$group": {"_id": "$sender_id",
                                                      "event": {"$sum": 1}
                                                     }
                                          },
                                          {"$project": {
                                              "sender_id": "$_id",
                                              "_id": 0,
                                              "event": 1
                                          }}
                                          ], allowDiskUse=True)
                              )
        except Exception as e:
            logger.error(e)
            message = str(e)

        return values, message

    @staticmethod
    def user_with_metrics(collection: Text,
                          from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                          to_date: date = datetime.utcnow().date()):

        """
        Fetches user with the steps and time in conversation.

        :param collection: collection to connect to
        :param from_date: default is last month date
        :param to_date: default is current month today date
        :return: list of users with step and time in conversation
        """
        Utility.validate_from_date_and_to_date(from_date, to_date)
        users = []
        try:
            client = HistoryProcessor.get_mongo_connection()
            message = None
            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                users = list(
                    conversations.aggregate([{"$match": {"event.event": "user",
                                                         "event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                                             "$lte": Utility.get_timestamp_from_date(to_date)}}},
                                             {"$group": {"_id": "$sender_id",
                                                         "latest_event_time": {"$last": "$event.timestamp"},
                                                         "steps": {"$sum": 1},}
                                              },
                                             {"$project": {
                                                 "sender_id": "$_id",
                                                 "_id": 0,
                                                 "steps": 1,
                                                 "latest_event_time": 1,
                                             }},
                                             {"$sort": {"latest_event_time": -1}}
                                             ], allowDiskUse=True))
        except Exception as e:
            logger.error(e)
            message = str(e)
        return users, message

    @staticmethod
    def engaged_users(collection: Text,
                      from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                      to_date: date = datetime.utcnow().date(),
                      conversation_limit: int = 10):

        """
        Counts the number of engaged users having a minimum number of conversation steps.

        :param collection: collection to connect to
        :param from_date: default is last month date
        :param to_date: default is current month today date
        :param conversation_limit: conversation step number to determine engaged users
        :return: number of engaged users
        """
        Utility.validate_from_date_and_to_date(from_date, to_date)
        values = []
        message = None
        try:
            client = HistoryProcessor.get_mongo_connection()
            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                values = list(
                    conversations.aggregate([{"$match": {"event.event": "user",
                                                         "event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                                             "$lte": Utility.get_timestamp_from_date(to_date)}}
                                              },
                                             {"$group": {"_id": "$sender_id", "event": {"$sum": 1}}},
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
            message = str(e)
        if not values:
            event = 0
        else:
            event = values[0]['event'] if values[0]['event'] else 0
        return (
            {"engaged_users": event},
            message
        )

    @staticmethod
    def new_users(collection: Text,
                  from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                  to_date: date = datetime.utcnow().date()):

        """
        Counts the number of new users of the bot.

        :param collection: collection to connect to
        :param from_date: default is last month date
        :param to_date: default is current month today date
        :return: number of new users
        """

        Utility.validate_from_date_and_to_date(from_date, to_date)
        values = []
        try:
            client = HistoryProcessor.get_mongo_connection()
            message = None
            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                values = list(
                    conversations.aggregate([{"$match": { "event.name": {"$regex": ".*session_start*."}}},
                                             {"$group": {"_id": '$sender_id',
                                                         "latest_event_time": {"$first": "$event.timestamp"},
                                                          "count": {"$sum": 1}
                                                         }
                                             },
                                             {"$match": {
                                                 "latest_event_time": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                                       "$lte": Utility.get_timestamp_from_date(to_date)},
                                                 "count": {"$eq": 1},
                                                }
                                             },
                                             {"$group": {"_id": None, "count": {"$sum": 1}}},
                                             {"$project": {"_id": 0, "count": 1}}
                                             ]))
        except Exception as e:
            logger.error(e)
            message = str(e)
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
                                 from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                                 to_date: date = datetime.utcnow().date(),
                                 fallback_action: str = 'action_default_fallback',
                                 nlu_fallback_action: str = 'nlu_fallback'):

        """
        Counts the number of successful conversations of the bot

        :param collection: collection to connect to
        :param from_date: default is last month date
        :param to_date: default is current month today date
        :param fallback_action: fallback action configured for bot
        :param nlu_fallback_action: nlu fallback configured for bot
        :return: number of successful conversations
        """
        Utility.validate_from_date_and_to_date(from_date, to_date)
        total = []
        fallback_count = []
        try:
            client = HistoryProcessor.get_mongo_connection()
            message = None
            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                total = list(
                    conversations.aggregate([{"$match": {
                                                        "event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                                            "$lte": Utility.get_timestamp_from_date(to_date)},
                                                        "event.event": "user"
                                                        }
                                             },
                                             {"$group": {"_id": None, "count": {"$sum": 1}}},
                                             {"$project": {"_id": 0, "count": 1}}
                                             ]))

                fallback_count = list(
                    conversations.aggregate([
                        {"$match": {
                            "event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                "$lte": Utility.get_timestamp_from_date(to_date)},
                            "event.name": {"$in": [fallback_action, nlu_fallback_action]}
                        }
                        },
                        {"$group": {"_id": None, "count": {"$sum": 1}}},
                        {"$project": {"_id": 0, "count": 1}}
                    ]))

        except Exception as e:
            logger.error(e)
            message = str(e)

        if not total:
            total_count = 0
        else:
            total_count = total[0]['count'] if total[0]['count'] else 0

        if not fallback_count:
            fallbacks_count = 0
        else:
            fallbacks_count = fallback_count[0]['count'] if fallback_count[0]['count'] else 0

        return (
            {"successful_conversations": total_count - fallbacks_count, "total": total_count},
            message
        )

    @staticmethod
    def user_retention(collection: Text,
                       from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                       to_date: date = datetime.utcnow().date()):

        """
        Computes the user retention percentage of the bot

        :param collection: collection to connect to
        :param from_date: default is last month date
        :param to_date: default is current month today date
        :return: user retention percentage
        """
        Utility.validate_from_date_and_to_date(from_date, to_date)
        total = []
        repeating_users = []
        message = None
        try:
            client = HistoryProcessor.get_mongo_connection()
            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                total = list(conversations.distinct("sender_id")).__len__()
                repeating_users = list(
                    conversations.aggregate([{"$match": { "event.name": {"$regex": ".*session_start*."}}},
                                             {"$group": {"_id": '$sender_id',
                                                         "latest_event_time": {"$last": "$event.timestamp"},
                                                          "count": {"$sum": 1}
                                                         }
                                             },
                                             {"$match": {
                                                 "latest_event_time": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                                       "$lte": Utility.get_timestamp_from_date(to_date)},
                                                 "count": {"$gte": 2},
                                                }
                                             },
                                             {"$group": {"_id": None, "count": {"$sum": 1}}},
                                             {"$project": {"_id": 0, "count": 1}}
                                             ]))

        except Exception as e:
            logger.error(e)
            if message:
                message = '\n'.join([message, str(e)])
            else:
                message = str(e)

        total_count = total if total else 1

        if not repeating_users:
            repeat_count = 0
        else:
            repeat_count = repeating_users[0]['count'] if repeating_users[0]['count'] else 0

        return (
            {"user_retention": 100 * (repeat_count / total_count)},
            message
        )

    @staticmethod
    def engaged_users_range(collection: Text,
                            from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                            to_date: date = datetime.utcnow().date(),
                            conversation_limit: int = 10):

        """
        Computes the trend for engaged user count

        :param collection: collection to connect to
        :param from_date: default is last month date
        :param to_date: default is current month today date
        :param conversation_limit: conversation step number to determine engaged users
        :return: dictionary of counts of engaged users for the previous months
        """
        Utility.validate_from_date_and_to_date(from_date, to_date)
        engaged = []
        try:
            client = HistoryProcessor.get_mongo_connection()
            message = None
            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                engaged = list(
                    conversations.aggregate([{"$match": {"event.event": "user",
                                                         "event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                                             "$lte": Utility.get_timestamp_from_date(to_date)}
                                                         }
                                             },
                                             {"$addFields": {"month": { "$month": {"$toDate": {"$multiply": ["$event.timestamp", 1000]}}}}},
                                             {"$group": {"_id": {"month": "$month", "sender_id": "$sender_id"}, "count": {"$sum": 1}}},
                                             {"$match": {"count": {"$gte": conversation_limit}}},
                                             {"$group": {"_id": "$_id.month", "count": {"$sum": "$count"}}},
                                             {"$project": {
                                                 "_id": 1,
                                                 "count": 1,
                                             }}
                                             ], allowDiskUse=True)
                )
        except Exception as e:
            logger.error(e)
            message = str(e)
        engaged_users = {d['_id']: d['count'] for d in engaged}
        return (
            {"engaged_user_range": engaged_users},
            message
        )

    @staticmethod
    def new_users_range(collection: Text,
                        from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                        to_date: date = datetime.utcnow().date()):

        """
        Computes the trend for new user count

        :param collection: collection to connect to
        :param from_date: default is last month date
        :param to_date: default is current month today date
        :return: dictionary of counts of new users for the previous months
        """
        Utility.validate_from_date_and_to_date(from_date, to_date)
        values = []
        try:
            client = HistoryProcessor.get_mongo_connection()
            message = None
            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                values = list(
                    conversations.aggregate([{"$match": {"event.name": {"$regex": ".*session_start*."}}},
                                             {"$group": {"_id": '$sender_id',
                                                         "latest_event_time": {"$first": "$event.timestamp"},
                                                         "count": {"$sum": 1}
                                                         }
                                              },
                                             {"$addFields": {"month": { "$month": {"$toDate": {"$multiply": ["$latest_event_time", 1000]}}}}},
                                             {"$match": {
                                                 "latest_event_time": {
                                                     "$gte": Utility.get_timestamp_from_date(from_date),
                                                     "$lte": Utility.get_timestamp_from_date(to_date)
                                                 },
                                                 "count": {"$eq": 1},
                                             }},
                                             {"$group": {"_id": "$month", "count": {"$sum": 1}}},
                                             {"$project": {"_id": 1, "count": 1}}
                                             ]))
        except Exception as e:
            logger.error(e)
            message = str(e)
        new_users = {d['_id']: d['count'] for d in values}
        return (
            {"new_user_range": new_users},
            message
        )

    @staticmethod
    def successful_conversation_range(collection: Text,
                                      from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                                      to_date: date = datetime.utcnow().date(),
                                      fallback_action: str = 'action_default_fallback',
                                      nlu_fallback_action: str = 'nlu_fallback'):

        """
        Computes the trend for successful conversation count

        :param collection: collection to connect to
        :param from_date: default is last month date
        :param to_date: default is current month today date
        :param fallback_action: fallback action configured for bot
        :param nlu_fallback_action: nlu fallback configured for bot
        :return: dictionary of counts of successful bot conversations for the previous months
        """
        Utility.validate_from_date_and_to_date(from_date, to_date)
        total = []
        total_unsuccess = []
        try:
            client = HistoryProcessor.get_mongo_connection()
            message = None
            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                total = list(
                    conversations.aggregate([
                        {"$match":
                            {
                            "event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                "$lte": Utility.get_timestamp_from_date(to_date)},
                            "event.event": "user"
                        }
                        },
                        {"$addFields": {"month": {"$month": {"$toDate": {"$multiply": ["$event.timestamp", 1000]}}}}},
                        {"$group": {"_id": "$month", "count": {"$sum": 1}}},
                        {"$project": {"_id": 1, "count": 1}}
                    ], allowDiskUse=True))
                total_unsuccess = list(
                    conversations.aggregate([
                        {"$match":
                            {
                                "event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                    "$lte": Utility.get_timestamp_from_date(to_date)},
                                "event.event": {"$in": [fallback_action, nlu_fallback_action]}
                            }
                        },
                        {"$addFields": {"month": {"$month": {"$toDate": {"$multiply": ["$event.timestamp", 1000]}}}}},
                        {"$group": {"_id": "$month", "count": {"$sum": 1}}},
                        {"$project": {"_id": 1, "count": 1}}
                    ], allowDiskUse=True))
        except Exception as e:
            logger.error(e)
            message = str(e)
        unsuccess_dict = {item["_id"]: item["count"]   for item in total_unsuccess}
        total_dict = {item["_id"]: item["count"] for item in total_unsuccess}
        successful = [{key: value - unsuccess_dict[key]}  for key, value in total_dict.items()]
        return (
            {"successful": successful, "total": total},
            message
        )

    @staticmethod
    def user_retention_range(collection: Text,
                             from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                             to_date: date = datetime.utcnow().date()):

        """
        Computes the trend for user retention percentages

        :param collection: collection to connect to
        :param from_date: default is last month date
        :param to_date: default is current month today date
        :return: dictionary of user retention percentages for the previous months
        """
        Utility.validate_from_date_and_to_date(from_date, to_date)
        total = []
        repeating_users = []
        try:
            client = HistoryProcessor.get_mongo_connection()
            message = None
            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                total = list(
                    conversations.aggregate([{"$match": {"event.name": {"$regex": ".*session_start*."},
                                                         "event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                                             "$lte": Utility.get_timestamp_from_date(to_date)}
                                                         }
                                              },
                        {"$addFields": {"month": {"$month": {"$toDate": {"$multiply": ["$event.timestamp", 1000]}}}}},
                        {"$group": {"_id": "$month", "count": {"$sum": 1}}},
                        {"$project": {"_id": 1, "count": 1}}
                    ]))
                repeating_users = list(
                    conversations.aggregate([{"$match": {"event.name": {"$regex": ".*session_start*."},
                                                         "event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                                             "$lte": Utility.get_timestamp_from_date(to_date)}
                                                         }
                                              },
                                             {"$group": {"_id": '$sender_id', "count": {"$sum": 1},
                                                         "latest_event_time": {"$last": "$event.timestamp"}}},
                                             {"$match": {"count": {"$gte": 2}}},
                                             {"$addFields": {"month": {
                                                 "$month": {"$toDate": {"$multiply": ["$latest_event_time", 1000]}}}}},
                                             {"$group": {"_id": "$month", "count": {"$sum": "$count"}}},
                                             {"$project": {"_id": 1, "count": 1}}
                                             ]))
        except Exception as e:
            logger.error(e)
            message = str(e)
        total_users = {d['_id']: d['count'] for d in total}
        repeat_users = {d['_id']: d['count'] for d in repeating_users}
        retention = {k: 100 * (repeat_users[k] / total_users[k]) for k in repeat_users.keys()}
        return (
            {"retention_range": retention},
            message
        )

    @staticmethod
    def fallback_count_range(collection: Text,
                             from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                             to_date: date = datetime.utcnow().date(),
                             fallback_action: str = 'action_default_fallback',
                             nlu_fallback_action: str = 'nlu_fallback'):

        """
        Computes the trend for fallback counts
        :param collection: collection to connect to
        :param from_date: default is last month date
        :param to_date: default is current month today date
        :param fallback_action: fallback action configured for bot
        :param nlu_fallback_action: nlu fallback configured for bot
        :return: dictionary of fallback counts for the previous months
        """
        Utility.validate_from_date_and_to_date(from_date, to_date)
        action_counts = []
        fallback_counts = []
        try:
            client = HistoryProcessor.get_mongo_connection()
            message = None
            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                fallback_counts = list(
                    conversations.aggregate([{"$match": {"event.event": "action",
                                                         "event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                                             "$lte": Utility.get_timestamp_from_date(to_date)},
                                                         "event.name": {"$in": [fallback_action, nlu_fallback_action]}
                                                         }
                                              },
                                             {"$addFields": {"month": {"$month": {"$toDate": {"$multiply": ["$event.timestamp", 1000]}}}}},
                                             {"$group": {"_id": "$month", "count": {"$sum": 1}}},
                                             {"$project": {"_id": 1, "count": 1}}
                                             ]))
                action_counts = list(
                    conversations.aggregate([{"$match": {"$and":
                                                             [
                                                                 {"event.event": "action"},
                                                                 {"event.name": {"$nin": ['action_listen', 'action_session_start']}},
                                                                 {"event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                                                      "$lte": Utility.get_timestamp_from_date(to_date)}}
                                                             ],
                                                        }
                                             },
                                             {"$addFields": {"month": { "$month": {"$toDate": {"$multiply": ["$event.timestamp", 1000]}}}}},
                                             {"$group": {"_id": "$month", "total_count": {"$sum": 1}}},
                                             {"$project": {"_id": 1, "total_count": 1}}
                                             ]))
        except Exception as e:
            logger.error(e)
            message = str(e)
        action_count = {d['_id']: d['total_count'] for d in action_counts}
        fallback_count = {d['_id']: d['count'] for d in fallback_counts}
        final_trend = {k: 100 * (fallback_count.get(k) / action_count.get(k)) for k in list(fallback_count.keys())}
        return (
            {"fallback_count_rate": final_trend, "total_fallback_count": fallback_count},
            message
        )

    @staticmethod
    def flatten_conversations(collection: Text, from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                              to_date: date = datetime.utcnow().date(), sort_by_date: bool = True):

        """
        Retrieves the flattened conversation data of the bot
        :param collection: collection to connect to
        :param from_date: default is last month date
        :param to_date: default is current month today date
        :param sort_by_date: This flag sorts the records by timestamp if set to True
        :return: dictionary of the bot users and their conversation data
        """
        Utility.validate_from_date_and_to_date(from_date, to_date)
        user_data = []
        try:
            client = HistoryProcessor.get_mongo_connection()
            message = None
            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                user_data = list(
                    conversations.aggregate(
                        [{"$match": { "$and": [
                                                {"event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                                     "$lte": Utility.get_timestamp_from_date(to_date)}},
                                                {"$or": [{"event.event": {"$in": ['bot', 'user']}},
                                                         {"$and": [{"event.event": "action"},
                                                                   {"event.name": {"$nin": ['action_session_start', 'action_listen']}}]}]}
                                              ]
                                    }
                          },
                         {"$sort": {"event.timestamp": 1}},
                         {"$group": {"_id": "$sender_id", "events": {"$push": "$event"},
                                     "allevents": {"$push": "$event"}}},
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
                                                                                                      ["$user_array", {
                                                                                                          "$add": [{
                                                                                                                       "$indexOfArray": [
                                                                                                                           "$user_array",
                                                                                                                           "$events"]},
                                                                                                                   1]}]}]},
                                                               {"$indexOfArray": ["$all_events", "$events"]}]},
                                                     {"$slice": ["$all_events", {
                                                         "$add": [{"$indexOfArray": ["$all_events", "$events"]}, 1]},
                                                                 {"$subtract": [{"$subtract": [
                                                                     {"$indexOfArray": ["$all_events", {"$arrayElemAt":
                                                                                                            [
                                                                                                                "$user_array",
                                                                                                                {
                                                                                                                    "$add": [
                                                                                                                        {
                                                                                                                            "$indexOfArray": [
                                                                                                                                "$user_array",
                                                                                                                                "$events"]},
                                                                                                                        1]}]}]},
                                                                     {"$indexOfArray": ["$all_events", "$events"]}]},
                                                                                1]}]}, {"$slice": ["$all_events",
                                                                                                   {"$add": [{
                                                                                                                 "$indexOfArray": [
                                                                                                                     "$all_events",
                                                                                                                     "$events"]},
                                                                                                             1]},
                                                                                                   100]}]}}},
                         {"$addFields": {"t_stamp": {"$toDate": {"$multiply": ["$timestamp", 1000]}}}},
                         {"$project": {"user_input": 1, "intent": 1, "confidence": 1, "action": "$action_bot_array.name"
                             , "timestamp": "$t_stamp", "bot_response_text": "$action_bot_array.text",
                                       "bot_response_data": "$action_bot_array.data",
                                       "sort": {"$cond": {"if": sort_by_date, "then": "$t_stamp", "else": "_id"}}}},
                         {"$sort": {"sort": -1}},
                         {"$project": {"user_input": 1, "intent": 1, "confidence": 1, "action": 1,
                                       "timestamp": {
                                           '$dateToString': {'format': "%d-%m-%Y %H:%M:%S", 'date': '$timestamp'}},
                                       "bot_response_text": 1, "bot_response_data": 1}}
                         ], allowDiskUse=True))
        except Exception as e:
            logger.error(e)
            message = str(e)

        return (
            {"conversation_data": user_data},
            message
        )

    @staticmethod
    def total_conversation_range(collection: Text,
                                 from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                                 to_date: date = datetime.utcnow().date()):

        """
        Computes the trend for conversation count

        :param collection: collection to connect to
        :param from_date: default is last month date
        :param to_date: default is current month today date
        :return: dictionary of counts of bot conversations for the previous months
        """
        Utility.validate_from_date_and_to_date(from_date, to_date)
        total = []
        try:
            client = HistoryProcessor.get_mongo_connection()
            message = None
            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                total = list(
                    conversations.aggregate([
                        {"$match": {"event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                        "$lte": Utility.get_timestamp_from_date(to_date)}}},
                        {"$addFields": {"month": {"$month": {"$toDate": {"$multiply": ["$event.timestamp", 1000]}}}}},

                        {"$group": {"_id": {"month": "$month", "sender_id": "$sender_id"}}},
                        {"$group": {"_id": "$_id.month", "count": {"$sum": 1}}},
                        {"$project": {"_id": 1, "count": 1}}
                    ], allowDiskUse=True))

        except Exception as e:
            logger.error(e)
            message = str(e)
        total_users = {d['_id']: d['count'] for d in total}
        return (
            {"total_conversation_range": total_users},
            message
        )

    @staticmethod
    def top_n_intents(collection: Text,
                      from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                      to_date: date = datetime.utcnow().date(),
                      top_n: int = 10):

        """
        Fetches the top n identified intents of the bot for a given time

        :param from_date: default is last month date
        :param to_date: default is current month today date
        :param collection: collection to connect to
        :param top_n: The first n number of most occurring intents
        :return: list of intents and their counts
        """
        Utility.validate_from_date_and_to_date(from_date, to_date)
        try:
            client = HistoryProcessor.get_mongo_connection()
            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                values = list(
                    conversations.aggregate([
                        {"$match": {"event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                        "$lte": Utility.get_timestamp_from_date(to_date)}}},
                        {"$project": {"intent": "$event.parse_data.intent.name", "_id": 0}},
                        {"$group": {"_id": "$intent", "count": {"$sum": 1}}},
                        {"$match": {"_id": {"$ne": None}}},
                        {"$sort": {"count": -1}},
                        {"$limit": top_n}
                    ], allowDiskUse=True))
            return values, None
        except Exception as e:
            logger.error(e)
            raise AppException(e)

    @staticmethod
    def top_n_actions(collection: Text,
                      from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                      to_date: date = datetime.utcnow().date(),
                      top_n: int = 10):

        """
        Fetches the top n identified actions of the bot for a given time

        :param from_date: default is last month date
        :param to_date: default is current month today date
        :param collection: collection to connect to
        :param top_n: The first n number of most occurring actions
        :return: list of actions and their counts
        """
        Utility.validate_from_date_and_to_date(from_date, to_date)
        try:
            client = HistoryProcessor.get_mongo_connection()
            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                values = list(
                    conversations.aggregate([
                        {"$match": {"event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                        "$lte": Utility.get_timestamp_from_date(to_date)},
                                    "event.event": "action",
                                    "event.name": {"$nin": ['action_listen', 'action_session_start']}
                                    }

                         },
                        {"$project": {"action": "$event.name", "_id": 0}},
                        {"$group": {"_id": "$action", "count": {"$sum": 1}}},
                        {"$sort": {"count": -1}},
                        {"$limit": top_n}
                    ], allowDiskUse=True))

            return values, None
        except Exception as e:
            logger.error(e)
            raise AppException(e)

    @staticmethod
    def average_conversation_step_range(collection: Text,
                                        from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                                        to_date: date = datetime.utcnow().date()):

        """
        Computes the trend for average conversation step count

        :param collection: collection to connect to
        :param from_date: default is last month date
        :param to_date: default is current month today date
        :return: dictionary of counts of average conversation step for the previous months
        """
        Utility.validate_from_date_and_to_date(from_date, to_date)
        total = []
        steps = []
        try:
            client = HistoryProcessor.get_mongo_connection()
            message = None
            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                steps = list(
                    conversations.aggregate([{"$match": {"event.event": "user",
                                                         "event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                                             "$lte": Utility.get_timestamp_from_date(to_date)}
                                                         }
                                              },
                                             {"$addFields": {
                                                 "month": {
                                                     "$month": {"$toDate": {"$multiply": ["$timestamp", 1000]}}}}},
                                             {"$group": {"_id": "$month", "event": {"$sum": 1}}}
                                             ], allowDiskUse=True)
                    )

                total = list(
                    conversations.aggregate([
                        {"$match": {"event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                        "$lte": Utility.get_timestamp_from_date(to_date)},
                                    "event.event": "user"
                                    }

                         },
                        {"$addFields": {"month": {"$month": {"$toDate": {"$multiply": ["$event.timestamp", 1000]}}}}},
                        {"$group": {"_id": {"month": "$month", "sender_id": "$sender_id"}}},
                        {"$group": {"_id": "$_id.month", "count": {"$sum": 1}}},
                        {"$project": {"_id": 1, "count": 1}}
                    ], allowDiskUse=True))
        except Exception as e:
            logger.error(e)
            message = str(e)
        conv_steps = {d['_id']: d['event'] for d in steps}
        user_count = {d['_id']: d['count'] for d in total}
        conv_steps = {k: conv_steps.get(k, 0) for k in user_count.keys()}
        avg_conv_steps = {k: conv_steps[k] / user_count[k] for k in user_count.keys()}
        return (
            {"average_conversation_steps": avg_conv_steps, "total_conversation_steps": conv_steps},
            message
        )

    @staticmethod
    def word_cloud(collection: Text, u_bound=1, l_bound=0, stopword_list=None,
                   from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                   to_date: date = datetime.utcnow().date()):

        """
        Creates the string that is necessary for the word cloud formation

        :param from_date: default is last month date
        :param to_date: default is current month today date
        :param collection: collection to connect to
        :param u_bound: The upper bound for the slider to filter the words for the wordcloud
        :param l_bound: The lower bound for the slider to filter the words for the wordcloud
        :param stopword_list: The stopword list that is used to filter extra words
        :return: the string for word cloud formation
        """

        from nltk.corpus import stopwords

        Utility.validate_from_date_and_to_date(from_date, to_date)
        if stopword_list is None:
            stopword_list = []

        try:
            client = HistoryProcessor.get_mongo_connection()
            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                word_list = list(conversations.aggregate(
                    [{"$match": {"event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                     "$lte": Utility.get_timestamp_from_date(to_date)},
                                 "event.event": "user"
                                 }
                     },
                     {"$project": {"user_input": "$event.text", "_id": 0}},
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
                upper_bound, lower_bound = round((1 - u_bound) * len(sorted_dict)), round(
                    (1 - l_bound) * len(sorted_dict))
                filtered_words = [word[1] for word in sorted_dict[upper_bound:lower_bound]]
                word_cloud_string = (" ").join([word for word in wordlist if word in filtered_words])
                return word_cloud_string, None
            else:
                return "", None

        except Exception as e:
            logger.error(e)
            raise AppException(e)

    @staticmethod
    def user_input_count(collection: Text,
                         from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                         to_date: date = datetime.utcnow().date()):

        """
        Gets the user inputs along with their frequencies

        :param collection: collection to connect to
        :param from_date: default is last month date
        :param to_date: default is current month today date
        :return: dictionary of counts of user inputs for the given duration
        """
        Utility.validate_from_date_and_to_date(from_date, to_date)
        user_input = []
        try:
            client = HistoryProcessor.get_mongo_connection()
            message = None
            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                user_input = list(conversations.aggregate(
                    [{"$match": {"event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                     "$lte": Utility.get_timestamp_from_date(to_date)},
                                 "event.event": "user"
                                }
                     },
                     {"$project": {"user_input": {"$toLower": "$event.text"}, "_id": 0}},
                     {"$group": {"_id": "$user_input", "count": {"$sum": 1}}},
                     {"$sort": {"count": -1}}
                     ], allowDiskUse=True))
        except Exception as e:
            logger.error(e)
            message = str(e)
        return (
            user_input, message
        )

    @staticmethod
    def user_fallback_dropoff(collection: Text,
                              from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                              to_date: date = datetime.utcnow().date(),
                              fallback_action: str = 'action_default_fallback',
                              nlu_fallback_action: str = 'nlu_fallback'):

        """
        Computes the list of users that dropped off after encountering fallback

        :param collection: collection to connect to
        :param fallback_action: fallback action configured for bot
        :param nlu_fallback_action: nlu fallback configured for bot
        :param from_date: default is last month date
        :param to_date: default is current month today date
        :return: dictionary of users and their dropoff counts
        """
        Utility.validate_from_date_and_to_date(from_date, to_date)
        new_session, single_session = [], []
        try:
            client = HistoryProcessor.get_mongo_connection()
            message = None
            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                new_session = list(
                    conversations.aggregate([{"$match": {"event.timestamp": {
                        "$gte": Utility.get_timestamp_from_date(from_date),
                        "$lte": Utility.get_timestamp_from_date(to_date)
                    },
                                                 "event.name": {"$ne": "action_listen"},
                                                 "event.event": {
                                                     "$nin": ["session_started", "restart", "bot"]}}},
                                             {"$group": {"_id": "$sender_id", "events": {"$push": "$event"},
                                                         "allevents": {"$push": "$event"}}},
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
                    conversations.aggregate([
                                             {"$match": {"event.timestamp": {
                                                 "$gte": Utility.get_timestamp_from_date(from_date),
                                                 "$lte": Utility.get_timestamp_from_date(to_date)
                                            },
                                                 "event.name": {"$ne": "action_listen"},
                                                 "event.event": {
                                                     "$nin": ["session_started", "restart", "bot"]}}},
                                             {"$group": {"_id": "$sender_id", "events": {"$push": "$event"}}},
                                             {"$addFields": {"last_event": {"$last": "$events"}}},
                                             {"$match": {'$or': [{"last_event.name": fallback_action},
                                                                 {"last_event.name": nlu_fallback_action}]}},
                                             {"$addFields": {"count": 1}},
                                             {"$project": {"_id": 1, "count": 1}}
                                             ], allowDiskUse=True)
            )
        except Exception as e:
            logger.error(e)
            message = str(e)
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

    @staticmethod
    def intents_before_dropoff(collection: Text,
                               from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                               to_date: date = datetime.utcnow().date()):

        """
        Computes the identified intents and their counts for users before dropping off from the conversations

        :param collection: collection to connect to
        :param from_date: default is last month date
        :param to_date: default is current month today date
        :return: dictionary of intents and their counts for the respective users
        """
        Utility.validate_from_date_and_to_date(from_date, to_date)
        new_session_dict, single_session_dict = {}, {}
        try:
            client = HistoryProcessor.get_mongo_connection()
            message = None
            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                new_session_list = list(
                    conversations.aggregate([
                                             {"$match": {"event.timestamp": {
                                                 "$gte": Utility.get_timestamp_from_date(from_date),
                                                 "$lte": Utility.get_timestamp_from_date(to_date)
                                             }}},
                                             {"$match": {"$or": [{"event.event": "user"},
                                                                 {"event.name": "action_session_start"}]}},
                                             {"$group": {"_id": "$sender_id", "events": {"$push": "$event"},
                                                         "allevents": {"$push": "$event"}}},
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
                                             {"$match": {"following_events.name": "action_session_start"}},
                                             {"$project": {"_id": 1, "intent": "$events.parse_data.intent.name"}},
                                             {"$group": {"_id": {"sender_id": "$_id", "intent": "$intent"},
                                                         "count": {"$sum": 1}}},
                                             {"$project": {"_id": "$_id.sender_id", "intent": "$_id.intent",
                                                           "count": 1}}
                                             ], allowDiskUse=True))

                for record in new_session_list:
                    if not record["_id"] in new_session_dict:
                        new_session_dict[record["_id"]] = {record["intent"]: record["count"]}
                    else:
                        new_session_dict[record["_id"]][record["intent"]] = record["count"]

                single_session_list = list(
                    conversations.aggregate([
                                             {"$match": {"event.timestamp": {
                                                 "$gte": Utility.get_timestamp_from_date(from_date),
                                                 "$lte": Utility.get_timestamp_from_date(to_date)
                                             }}},
                                             {"$match": {"$or": [{"event.event": "user"},
                                                                 {"event.name": "action_session_start"}]}},
                                             {"$group": {"_id": "$sender_id", "events": {"$push": "$event"}}},
                                             {"$addFields": {"last_event": {"$last": "$events"}}},
                                             {"$match": {"last_event.event": "user"}},
                                             {"$project": {"_id": 1, "intent": "$last_event.parse_data.intent.name"}},
                                             {"$addFields": {"count": 1}}], allowDiskUse=True))

                single_session_dict = {record["_id"]: {record["intent"]: record["count"]} for record in
                                       single_session_list}

        except Exception as e:
            logger.error(e)
            message = str(e)

        for record in single_session_dict:
            if record in new_session_dict:
                if list(single_session_dict[record].keys())[0] in new_session_dict[record]:
                    new_session_dict[record][list(single_session_dict[record].keys())[0]] = \
                    new_session_dict[record][list(single_session_dict[record].keys())[0]] + 1
                else:
                    new_session_dict[record][list(single_session_dict[record].keys())[0]] = \
                    single_session_dict[record][list(single_session_dict[record].keys())[0]]
            else:
                new_session_dict[record] = single_session_dict[record]

        return (
            new_session_dict,
            message
        )

    @staticmethod
    def unsuccessful_session(collection: Text,
                             from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                             to_date: date = datetime.utcnow().date(),
                             fallback_action: str = 'action_default_fallback',
                             nlu_fallback_action: str = 'nlu_fallback'):

        """
        Computes the count of sessions for a user that had a fallback

        :param collection: collection to connect to
        :param fallback_action: fallback action configured for bot
        :param nlu_fallback_action: nlu fallback configured for bot
        :param from_date: default is last month date
        :param to_date: default is current month today date
        :return: dictionary of users and their unsuccessful session counts
        """
        Utility.validate_from_date_and_to_date(from_date, to_date)
        new_session, single_session = [], []
        try:
            client = HistoryProcessor.get_mongo_connection()
            message = None
            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                new_session = list(
                    conversations.aggregate([
                                             {"$match": {"event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                                             "$lte": Utility.get_timestamp_from_date(to_date)},
                                                         "event.name": {
                                                             "$in": ["action_session_start", fallback_action,
                                                                     nlu_fallback_action]}
                                                         }

                                             },
                                             {"$group": {"_id": "$sender_id", "events": {"$push": "$event"},
                                                         "allevents": {"$push": "$event"}}},
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

                                             ], allowDiskUse=True))

                single_session = list(
                    conversations.aggregate([{"$match": {"event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                                             "$lte": Utility.get_timestamp_from_date(to_date)},
                                                         "event.name": {
                                                             "$in": ["action_session_start", fallback_action,
                                                                     nlu_fallback_action]}
                                                         }

                                             },
                                             {"$group": {"_id": "$sender_id", "events": {"$push": "$event"}}},
                                             {"$addFields": {"last_event": {"$last": "$events"}}},
                                             {"$match": {'$or': [{"last_event.name": fallback_action},
                                                                 {"last_event.name": nlu_fallback_action}]}},
                                             {"$addFields": {"count": 1}},
                                             {"$project": {"_id": 1, "count": 1}}
                                             ], allowDiskUse=True)
                    )
        except Exception as e:
            logger.error(e)
            message = str(e)
        new_session = {d['_id']: d['count'] for d in new_session}
        single_session = {d['_id']: d['count'] for d in single_session}
        for record in single_session:
            if record in new_session:
                new_session[record] = new_session[record] + 1
            else:
                new_session[record] = single_session[record]
        return (
            new_session,
            message
        )

    @staticmethod
    def session_count(collection: Text,
                      from_date: date = (datetime.utcnow() - timedelta(30)).date(),
                      to_date: date = datetime.utcnow().date()):

        """
        Computes the total session count for users for the past months

        :param collection: collection to connect to
        :param from_date: default is last month date
        :param to_date: default is current month today date
        :return: dictionary of users and their session counts
        """
        Utility.validate_from_date_and_to_date(from_date, to_date)
        new_session, single_session = [], []
        try:
            client = HistoryProcessor.get_mongo_connection()
            message = None
            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                new_session = list(
                    conversations.aggregate([{"$match": {"event.timestamp": {
                        "$gte": Utility.get_timestamp_from_date(from_date),
                        "$lte": Utility.get_timestamp_from_date(to_date)
                    },
                                                 "event.name": "action_session_start"
                                             }},
                                             {"$group": {"_id": "$sender_id", "count": {"$sum": 1}}}
                                             ], allowDiskUse=True))

                single_session = list(
                    conversations.aggregate([{"$match": {"event.timestamp": {"$gte": Utility.get_timestamp_from_date(from_date),
                                                                             "$lte": Utility.get_timestamp_from_date(to_date)},
                                                         "$or": [{"event.event": "user"},
                                                                 {"event.name": "action_session_start"}]
                                                        }
                                              },
                                             {"$group": {"_id": "$sender_id", "events": {"$push": "$event"}}},
                                             {"$addFields": {"first_event": {"$first": "$events"}}},
                                             {"$match": {"first_event.event": "user"}},
                                             {"$project": {"_id": 1}},
                                             {"$addFields": {"count": 1}}], allowDiskUse=True))
        except Exception as e:
            logger.error(e)
            message = str(e)
        new_session = {d['_id']: d['count'] for d in new_session}
        single_session = {d['_id']: d['count'] for d in single_session}
        for record in single_session:
            if record in new_session:
                new_session[record] = new_session[record] + 1
            else:
                new_session[record] = single_session[record]
        return (
            new_session,
            message
        )

    @staticmethod
    def delete_user_history(
            collection: Text, sender_id: Text,
            till_date: date = datetime.utcnow().date()
    ):

        """
        Deletes chat history for specific user in a bot

        Archives conversations based on month to conversations_archive DB

        :param till_date: default is current month today date
        :param collection: collection to connect to
        :param sender_id: user id
        :return: string message
        """
        till_date_timestamp = Utility.get_timestamp_from_date(till_date)
        HistoryProcessor.archive_user_history(collection=collection, sender_id=sender_id,
                                              till_date_timestamp=till_date_timestamp)
        HistoryProcessor.delete_user_conversations(collection=collection, sender_id=sender_id,
                                                   till_date_timestamp=till_date_timestamp)

    @staticmethod
    def archive_user_history(collection: Text, sender_id: Text, till_date_timestamp: float):

        """
        Archives conversations based on month to conversations_archive DB

        :param collection: collection to connect to
        :param sender_id: user id
        :param till_date_timestamp: the timestamp based on till_date
        :return: none
        """
        try:
            archive_db = Utility.environment['history_server']['deletion']['archive_db']
            client = HistoryProcessor.get_mongo_connection()
            archive_collection = f"{collection}.{sender_id}"

            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                conversations.aggregate([{"$match": {"sender_id": sender_id}},
                                         {"$match": {"event.timestamp": {"$lte": till_date_timestamp}}},
                                         {"$project": {"_id":0}},
                                         {"$merge": {"into": {"db": archive_db, "coll": archive_collection},
                                                     "on": "_id",
                                                     "whenMatched": "keepExisting",
                                                     "whenNotMatched": "insert"}}
                                         ], allowDiskUse=True)
        except Exception as e:
            logger.error(e)
            raise AppException(e)

    @staticmethod
    def delete_user_conversations(collection: Text, sender_id: Text, till_date_timestamp: float):

        """
        Removes archived conversations events from existing collection

        :param collection: collection to connect to
        :param sender_id: user id
        :param till_date_timestamp: the timestamp based on till_date
        :return: none
        """
        try:
            client = HistoryProcessor.get_mongo_connection()

            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)

                # Remove Archived Events
                conversations.delete_many(filter={'sender_id': sender_id,
                                                  "event.timestamp": {'$lte': till_date_timestamp}})
        except Exception as e:
            logger.error(e)
            raise AppException(e)

    @staticmethod
    def fetch_chat_users_for_delete(collection: Text, till_date_timestamp: float):

        """
        Fetch users.

        Fetches user list who has conversation with the agent before specified month

        :param collection: collection to connect to
        :param till_date_timestamp: the timestamp based on till_date
        :return: list of user id
        """
        try:
            client = HistoryProcessor.get_mongo_connection()

            with client as client:
                db = client.get_database()
                conversations = db.get_collection(collection)
                values = list(conversations.distinct("sender_id", {"event.timestamp": {"$lte": till_date_timestamp}}))
                return values
        except Exception as e:
            logger.error(e)
            raise AppException(e)

    @staticmethod
    def delete_bot_history(
            collection: Text,
            till_date: date = datetime.utcnow().date()
    ):

        """
        Deletes chat history for all users in a bot

        Archives conversations based on month to conversations_archive DB

        :param till_date: default is current month today date
        :param collection: collection to connect to
        :return: string message
        """
        till_date_timestamp = Utility.get_timestamp_from_date(till_date)
        try:
            users = HistoryProcessor.fetch_chat_users_for_delete(
                collection=collection, till_date_timestamp=till_date_timestamp
            )

            for sender_id in users:
                HistoryProcessor.archive_user_history(collection=collection, sender_id=sender_id,
                                                      till_date_timestamp=till_date_timestamp)

                HistoryProcessor.delete_user_conversations(collection=collection, sender_id=sender_id,
                                                           till_date_timestamp=till_date_timestamp)
            return "Deleting User history!"
        except Exception as e:
            logger.error(e)
            raise AppException(e)
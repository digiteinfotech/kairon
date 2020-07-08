from datetime import datetime
from typing import Text

import pandas as pd
from rasa.core.tracker_store import MongoTrackerStore, DialogueStateTracker
from bot_trainer.utils import Utility
from .processor import MongoProcessor
from loguru import logger


class ChatHistory:
    """
    Class contains logic for fetching history data and metrics from mongo tracker
    """

    mongo_processor = MongoProcessor()

    @staticmethod
    def get_tracker_and_domain(bot: Text):
        """
        loads domain data and mongo tracker

        :param bot: bot id
        :return: tuple domain, tracker
        """
        domain = ChatHistory.mongo_processor.load_domain(bot)
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
            tracker = Utility.get_local_mongo_store(bot, domain)
        return (domain, tracker)

    @staticmethod
    def fetch_chat_history(bot: Text, sender, latest_history=False):
        """
        fetches chat history

        :param bot: bot id
        :param sender: history details for user
        :param latest_history: whether to fetch latest or complete history
        :return: list of conversations
        """
        events = ChatHistory.fetch_user_history(
            bot, sender, latest_history=latest_history
        )
        return list(ChatHistory.__prepare_data(bot, events))

    @staticmethod
    def fetch_chat_users(bot: Text):
        """
        fetches user list who has conversation with the agent

        :param bot: bot id
        :return: list of user id

        """
        _, tracker = ChatHistory.get_tracker_and_domain(bot)
        return tracker.keys()

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
                event_data = event.as_dict()
                if event_data["event"] in event_list:
                    result = {
                        "event": event_data["event"],
                        "time": datetime.fromtimestamp(event_data["timestamp"]).time(),
                        "date": datetime.fromtimestamp(event_data["timestamp"]).date(),
                    }

                    if event_data.get("text"):
                        result["text"] = event_data.get("text")
                        text_data = str(event_data.get("text")).lower()
                        result["is_exists"] = text_data in training_examples
                        if result["is_exists"]:
                            result["_id"] = ids[training_examples.index(text_data)]

                    if event_data["event"] == "user":
                        parse_data = event_data["parse_data"]
                        result["intent"] = parse_data["intent"]["name"]
                        result["confidence"] = parse_data["intent"]["confidence"]
                    elif event_data["event"] == "bot":
                        if bot_action:
                            result["action"] = bot_action

                    if result:
                        yield result
                else:
                    bot_action = (
                        event_data["name"] if event_data["event"] == "action" else None
                    )

    @staticmethod
    def fetch_user_history(bot: Text, sender_id: Text, latest_history=True):
        """
        loads list of conversation events from chat history

        :param bot: bot id
        :param sender_id: user id
        :param latest_history: whether to fetch latest history or complete history, default is latest
        :return: list of conversation events
        """
        domain, tracker = ChatHistory.get_tracker_and_domain(bot)
        if latest_history:
            return tracker.retrieve(sender_id).as_dialogue().events
        else:
            user_conversation = tracker.conversations.find_one({"sender_id": sender_id})
            if user_conversation:
                return (
                    DialogueStateTracker.from_dict(
                        sender_id, list(user_conversation["events"]), domain.slots
                    )
                    .as_dialogue()
                    .events
                )

    @staticmethod
    def visitor_hit_fallback(bot: Text):
        """
        Counts the number of times, the agent was unable to provide a response to users

        :param bot: bot id
        :return: list of visitor fallback
        """
        data_frame = ChatHistory.__fetch_history_metrics(bot)
        if data_frame.empty:
            fallback_count = 0
            total_count = 0
        else:
            fallback_count = data_frame[
                data_frame["name"] == "action_default_fallback"
            ].count()["name"]
            total_count = data_frame.count()["name"]
        return {"fallback_count": int(fallback_count), "total_count": int(total_count)}

    @staticmethod
    def conversation_steps(bot: Text):
        """
        calculates the number of conversation steps between agent and users

        :param bot: bot id
        :return: list of conversation step count
        """
        """
        data_frame = data_frame.groupby(['sender_id', data_frame.event.ne('session_started')])
        data_frame = data_frame.size().reset_index()
        data_frame.rename(columns={0: 'count'}, inplace=True)
        data_frame = data_frame[data_frame['event'] != 0]
        return data_frame.to_json(orient='records')
        """
        data_frame = ChatHistory.__fetch_history_metrics(bot)
        if data_frame.empty:
            return {}
        else:
            data_frame["prev_event"] = data_frame["event"].shift()
            data_frame["prev_timestamp"] = data_frame["timestamp"].shift()
            data_frame.fillna("", inplace=True)
            data_frame = data_frame[
                ((data_frame["event"] == "bot") & (data_frame["prev_event"] == "user"))
            ]
            return (
                data_frame.groupby(["sender_id"])
                .count()
                .reset_index()[["sender_id", "event"]]
                .to_dict(orient="records")
            )

    @staticmethod
    def conversation_time(bot: Text):
        """
        calculates the duration of between agent and users

        :param bot: bot id
        :return: list of users duration
        """
        data_frame = ChatHistory.__fetch_history_metrics(bot)
        if data_frame.empty:
            return {}
        else:
            data_frame["prev_event"] = data_frame["event"].shift()
            data_frame["prev_timestamp"] = data_frame["timestamp"].shift()
            data_frame.fillna("", inplace=True)
            data_frame = data_frame[
                ((data_frame["event"] == "bot") & (data_frame["prev_event"] == "user"))
            ]
            data_frame["time"] = pd.to_datetime(
                data_frame["timestamp"], unit="s"
            ) - pd.to_datetime(data_frame["prev_timestamp"], unit="s")
            return (
                data_frame[["sender_id", "time"]]
                .groupby("sender_id")
                .sum()
                .reset_index()
                .to_dict(orient="records")
            )

    @staticmethod
    def get_conversations(bot: Text):
        """
        fetches all the conversations between agent and users

        :param bot: bot id
        :return: list of conversations
        """
        _, tracker = ChatHistory.get_tracker_and_domain(bot)
        return list(tracker.conversations.find())

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
        records = ChatHistory.get_conversations(bot)
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
        return data_frame

import itertools
from typing import Any, Dict, Iterable, List, Optional, Text

from loguru import logger
from pymongo import IndexModel, ASCENDING, DESCENDING
from pymongo.collection import Collection
from rasa.core.brokers.broker import EventBroker
from rasa.core.tracker_store import SerializedTrackerAsText
from rasa.core.tracker_store import TrackerStore
from rasa.shared.core.domain import Domain
from rasa.shared.core.trackers import DialogueStateTracker, EventVerbosity
from uuid6 import uuid7

from kairon.shared.utils import Utility


class KMongoTrackerStore(TrackerStore, SerializedTrackerAsText):
    def __init__(
        self,
        domain: Domain,
        host: Optional[Text] = "mongodb://localhost:27017",
        db: Optional[Text] = "kairon",
        username: Optional[Text] = None,
        password: Optional[Text] = None,
        auth_source: Optional[Text] = "admin",
        collection: Optional[Text] = "conversations",
        event_broker: Optional[EventBroker] = None,
        **kwargs: Dict[Text, Any],
    ) -> None:
        if Utility.environment.get("env") == "test":
            from mongomock import MongoClient

            self.client = MongoClient(
                host,
                username=username,
                password=password,
                authSource=auth_source,
                connect=False,
            )
        else:
            from pymongo import MongoClient

            self.client = MongoClient(
                host,
                username=username,
                password=password,
                authSource=auth_source,
                # delay connect until process forking is done
                connect=False,
            )

        self.db = self.client.get_database(db)
        self.collection = collection
        super().__init__(domain, event_broker, **kwargs)

        self._ensure_indices()
        logger.debug(f"collection: {collection}, db: {db}, env: {Utility.environment.get('env')}")

    @property
    def conversations(self) -> Collection:
        """Returns the current conversation."""
        return self.db[self.collection]

    def _ensure_indices(self) -> None:
        indexes = [
            IndexModel([("sender_id", ASCENDING), ("event.event", ASCENDING)]),
            IndexModel([("type", ASCENDING), ("timestamp", ASCENDING)]),
            IndexModel([("sender_id", ASCENDING), ("conversation_id", ASCENDING)]),
            IndexModel([("event.event", ASCENDING), ("event.timestamp", DESCENDING)]),
            IndexModel([("event.name", ASCENDING), ("event.timestamp", DESCENDING)]),
            IndexModel([("event.timestamp", DESCENDING)]),
            IndexModel([("sender_id", ASCENDING), ("type", ASCENDING), ("event.event", ASCENDING)]),
            IndexModel([("sender_id", ASCENDING), ("type", ASCENDING), ("event.event", ASCENDING), ("event.timestamp", ASCENDING)]),
        ]
        self.conversations.create_indexes(indexes)

    @staticmethod
    def _current_tracker_state_without_events(tracker: DialogueStateTracker) -> Dict:
        # get current tracker state and remove `events` key from state
        # since events are pushed separately in the `update_one()` operation
        state = tracker.current_state(EventVerbosity.ALL)
        state.pop("events", None)

        return state

    async def save(self, tracker: DialogueStateTracker):
        """Saves the current conversation state."""
        if len(tracker.events):
            await self.stream_events(tracker)

            additional_events = self._additional_events(tracker)
            if additional_events:
                sender_id = tracker.sender_id
                conversation_id = uuid7().hex
                flattened_conversation = {
                    "type": "flattened",
                    "sender_id": sender_id,
                    "conversation_id": conversation_id,
                    "data": {},
                }
                actions_predicted = []
                bot_responses = []
                data = []
                metadata = {}
                for event in additional_events:
                    event = event.as_dict()
                    if not event.get("metadata"):
                        event["metadata"] = {}
                    event["metadata"].update(metadata)
                    data.append(
                        {
                            "sender_id": sender_id,
                            "conversation_id": conversation_id,
                            "event": event,
                            "tag": "tracker_store",
                            "type": "bot",
                        }
                    )
                    if event["event"] == "user":
                        flattened_conversation["timestamp"] = event.get("timestamp")
                        flattened_conversation["data"]["user_input"] = event.get("text")
                        flattened_conversation["data"]["intent"] = event["parse_data"][
                            "intent"
                        ]["name"]
                        flattened_conversation["data"]["confidence"] = event["parse_data"][
                            "intent"
                        ]["confidence"]
                        metadata = event.get("metadata")
                    elif event["event"] == "action":
                        actions_predicted.append(event.get("name"))
                    elif event["event"] == "bot":
                        bot_responses.append(
                            {
                                "text": event.get("text"),
                                "data": event.get("data"),
                                "utter_action": event.get("metadata", {}).get('utter_action')
                            }
                        )
                flattened_conversation["data"]["action"] = actions_predicted
                flattened_conversation["data"]["bot_response"] = bot_responses
                flattened_conversation["metadata"] = metadata
                flattened_conversation["tag"] = "tracker_store"
                data.append(flattened_conversation)
                if data:
                    records = self.conversations.insert_many(data)
                    logger.info(f"db: {self.db.name}, collection: {self.collection}, env: {Utility.environment['env']}, records: {len(records.inserted_ids)}")

    async def _retrieve(
        self, sender_id: Text, fetch_events_from_all_sessions: bool
    ) -> Optional[List[Dict[Text, Any]]]:

        stored = self.get_stored_events(sender_id, fetch_events_from_all_sessions)
        # look for conversations which have used an `int` sender_id in the past
        # and update them.
        if not stored and sender_id.isdigit():
            self.conversations.update_many(
                {"sender_id": int(sender_id)}, {"$set": {"sender_id": str(sender_id)}}
            )

        if not stored:
            return None

        return stored

    async def retrieve(self, sender_id: Text) -> Optional[DialogueStateTracker]:
        # TODO: Remove this in Rasa Open Source 3.0 along with the
        # deprecation warning in the constructor
        events = await self._retrieve(sender_id, fetch_events_from_all_sessions=False)

        if not events:
            return None

        return DialogueStateTracker.from_dict(sender_id, events, self.domain.slots)

    async def retrieve_full_tracker(
        self, conversation_id: Text
    ) -> Optional[DialogueStateTracker]:
        events = await self._retrieve(
            conversation_id, fetch_events_from_all_sessions=True
        )

        if not events:
            return None

        return DialogueStateTracker.from_dict(
            conversation_id, events, self.domain.slots
        )

    async def keys(self) -> Iterable[Text]:
        """Returns sender_ids of the Mongo Tracker Store."""
        return [c["sender_id"] for c in self.conversations.distinct(key="sender_id")]

    def get_stored_events(self, sender_id: Text, fetch_events_from_all_sessions: bool):
        filter_query = {"sender_id": sender_id, "type": "bot"}

        if not fetch_events_from_all_sessions:
            last_session = list(
                self.conversations.aggregate(
                    [
                        {
                            "$match": {
                                "sender_id": sender_id,
                                "event.event": "session_started",
                                "type": "bot"
                            }
                        },
                        {"$sort": {"event.timestamp": 1}},
                        {"$group": {"_id": "$sender_id", "event": {"$last": "$event"}}},
                    ]
                )
            )
            filter_query["event.event"] = {"$ne": "session_started"}

            if last_session:
                filter_query["event.timestamp"] = {
                    "$gte": last_session[0]["event"]["timestamp"]
                }

        stored = list(
            self.conversations.aggregate(
                [
                    {"$match": filter_query},
                    {"$sort": {"event.timestamp": 1}},
                    {"$group": {"_id": "$sender_id", "events": {"$push": "$event"}}},
                    {"$project": {"sender_id": "$_id", "events": 1, "_id": 0}},
                ]
            )
        )
        if not stored:
            return None
        return stored[0]["events"]

    def get_latest_session_events_count(self, sender_id: Text):
        filter_query = {"sender_id": sender_id, 'type': 'bot'}

        last_session = list(
            self.conversations.aggregate(
                [
                    {
                        "$match": {
                            "sender_id": sender_id,
                            "event.event": "session_started",
                            "type": 'bot'
                        }
                    },
                    {"$sort": {"event.timestamp": 1}},
                    {"$group": {"_id": "$sender_id", "event": {"$last": "$event"}}},
                ]
            )
        )
        filter_query["event.event"] = {"$ne": "session_started"}

        if last_session:
            filter_query["event.timestamp"] = {
                "$gte": last_session[0]["event"]["timestamp"]
            }

        stored = list(
            self.conversations.aggregate(
                [
                    {"$match": filter_query},
                    {"$sort": {"event.timestamp": 1}},
                    {"$group": {"_id": "$sender_id", "count": {"$sum": 1}}},
                    {"$project": {"sender_id": "$_id", "count": 1, "_id": 0}},
                ]
            )
        )
        if stored:
            return stored[0]["count"]
        else:
            return None

    def _additional_events(self, tracker: DialogueStateTracker) -> List:
        count = self.get_latest_session_events_count(tracker.sender_id)
        total_events = len(tracker.events)
        logger.debug(tracker.events)
        logger.debug(f"tracker existing events : {count}")
        logger.debug(f"tracker total events : {total_events}")
        if count:
            return list(itertools.islice(tracker.events, count, total_events))
        return tracker.events

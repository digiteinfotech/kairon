import itertools
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Optional,
    Text,
    Iterator
)

import pymongo
from pymongo import IndexModel
from pymongo.collection import Collection
from rasa.core.brokers.broker import EventBroker
from rasa.core.tracker_store import TrackerStore
from rasa.shared.core.domain import Domain
from rasa.shared.core.trackers import (
    DialogueStateTracker,
)
from uuid6 import uuid7


class KMongoTrackerStore(TrackerStore):

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
        from pymongo.database import Database
        from pymongo import MongoClient

        self.client = MongoClient(
            host,
            username=username,
            password=password,
            authSource=auth_source,
            # delay connect until process forking is done
            connect=False,
        )

        self.db = Database(self.client, db)
        self.collection = collection
        super().__init__(domain, event_broker, **kwargs)

        self._ensure_indices()

    @property
    def conversations(self) -> Collection:
        """Returns the current conversation."""
        return self.db[self.collection]

    def _ensure_indices(self) -> None:
        index1 = IndexModel([("event.event", pymongo.ASCENDING), ("event.timestamp", pymongo.DESCENDING)])
        index2 = IndexModel([("type", pymongo.ASCENDING)])
        index3 = IndexModel([("sender_id", pymongo.ASCENDING), ("conversation_id", pymongo.ASCENDING)])
        self.conversations.create_indexes([index1, index2, index3])

    def save(self, tracker, timeout=None):
        """Saves the current conversation state."""
        if self.event_broker:
            self.stream_events(tracker)

        additional_events = self._additional_events(tracker)
        sender_id = tracker.sender_id
        conversation_id = uuid7().hex
        flattened_conversation = {"type": "flattened", "sender_id": sender_id, "conversation_id": conversation_id, "data": {}}
        actions_predicted = []
        bot_responses = []
        data = []
        for event in additional_events:
            event = event.as_dict()
            data.append({"sender_id": sender_id, "conversation_id": conversation_id, "event": event})
            if event['event'] == 'user':
                flattened_conversation['timestamp'] = event.get('timestamp')
                flattened_conversation["data"]['user_input'] = event.get('text')
                flattened_conversation["data"]['intent'] = event['parse_data']['intent']['name']
                flattened_conversation["data"]['confidence'] = event['parse_data']['intent']['confidence']
            elif event['event'] == 'action':
                actions_predicted.append(event.get('name'))
            elif event['event'] == 'bot':
                bot_responses.append({"text": event.get('text'), "data": event.get('data')})
        flattened_conversation["data"]['action'] = actions_predicted
        flattened_conversation["data"]['bot_response'] = bot_responses
        data.append(flattened_conversation)
        if data:
            self.conversations.insert_many(data)

    def _retrieve(
            self, sender_id: Text, fetch_events_from_all_sessions: bool
    ) -> Optional[List[Dict[Text, Any]]]:

        events = self.get_stored_events(sender_id, fetch_events_from_all_sessions)
        # look for conversations which have used an `int` sender_id in the past
        # and update them.
        if not events and sender_id.isdigit():
            self.conversations.update_many(
                {"sender_id": int(sender_id)},
                {"$set": {"sender_id": str(sender_id)}}
            )

        if not events:
            return None

        return events

    def retrieve(self, sender_id: Text) -> Optional[DialogueStateTracker]:
        # TODO: Remove this in Rasa Open Source 3.0 along with the
        # deprecation warning in the constructor
        if self.retrieve_events_from_previous_conversation_sessions:
            return self.retrieve_full_tracker(sender_id)

        events = self._retrieve(sender_id, fetch_events_from_all_sessions=False)

        if not events:
            return None

        return DialogueStateTracker.from_dict(sender_id, events, self.domain.slots)

    def retrieve_full_tracker(
            self, conversation_id: Text
    ) -> Optional[DialogueStateTracker]:
        events = self._retrieve(conversation_id, fetch_events_from_all_sessions=True)

        if not events:
            return None

        return DialogueStateTracker.from_dict(
            conversation_id, events, self.domain.slots
        )

    def keys(self) -> Iterable[Text]:
        """Returns sender_ids of the Mongo Tracker Store."""
        return [c["sender_id"] for c in self.conversations.distinct(key="sender_id")]

    def get_stored_events(self, sender_id: Text, fetch_events_from_all_sessions: bool):
        filter_query = {"sender_id": sender_id}

        if not fetch_events_from_all_sessions:
            last_session = list(self.conversations.aggregate([
                {"$match": {"sender_id": sender_id, "event.event": "session_started"}},
                {"$group": {"_id": "$sender_id", "event": {"$last": "$event"}}},
            ]))
            filter_query["event.event"] = {"$ne": "session_started"}

            if last_session:
                filter_query["event.timestamp"] = {"$gte": last_session[0]['event']['timestamp']}

        stored = list(self.conversations.aggregate([
            {"$match": filter_query},
            {"$group": {"_id": "$sender_id", "events": {"$push": "$event"}}},
            {"$project": {"sender_id": "$_id", "events": 1, "_id": 0}}
        ]))
        if not stored:
            return None
        return stored[0]['events']

    def _additional_events(self, tracker: DialogueStateTracker) -> Iterator:
        events = self.get_stored_events(tracker.sender_id, False)
        if events:
            number_events_since_last_session = len(events)
            return itertools.islice(
                tracker.events, number_events_since_last_session, len(tracker.events)
            )
        else:
            return tracker.events

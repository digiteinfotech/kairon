from rasa.core.tracker_store import MongoTrackerStore, DialogueStateTracker
from rasa.core.domain import Domain

class ChatHistory:
    def __init__(self, domainFile: str, mongo_url :str, mongo_db = 'conversation'):
        self.domain = Domain.load(domainFile)
        self.tracker = MongoTrackerStore(domain=self.domain, host=mongo_url, db=mongo_db)

    def fetch_chat_history(self, sender, latest_history = False):
        events = self.__fetch_user_history(sender, latest_history=latest_history)
        return list(self.__prepare_data(events))

    def fetch_chat_users(self):
        return self.tracker.keys()

    def __prepare_data(self, events, show_session = False):
        bot_action = None
        for i in range(events.__len__()):
            event = events[i]
            event_data = event.as_dict()
            if event_data['event'] not in ['action', 'rewind']:
                result = {'event': event_data['event'], 'timestamp': event_data['timestamp']}

                if event_data['event'] not in ['session_started', 'rewind']:
                    result['text'] = event_data['text']

                if event_data['event'] == 'user':
                    parse_data = event_data['parse_data']
                    result['intent'] = parse_data['intent']['name']
                    result['confidence'] = parse_data['intent']['confidence']
                elif event_data['event'] == 'bot':
                    if bot_action:
                        result['action'] = bot_action

                if event_data['event'] == 'session_started' and not show_session:
                    continue
                yield result
            else:
                bot_action = event_data['name'] if event_data['event'] == 'action' else None

    def __fetch_history_for_metrics(self):
        records = self.tracker.conversations.find()
        for record in records:
            events = record['events']
            sender_id = record['sender_id']


    def __fetch_user_history(self, sender_id, latest_history = True):
        if latest_history:
            return self.tracker.retrieve(sender_id).as_dialogue().events
        else:
            user_conversation = self.tracker.conversations.find_one({"sender_id": sender_id})
            return DialogueStateTracker.from_dict(sender_id, list(user_conversation['events']), self.domain.slots).as_dialogue().events

from rasa.core.tracker_store import MongoTrackerStore
from rasa.core.domain import Domain
class ChatHistory:
    def __init__(self, domainFile: str, mongo_url :str, mongo_db = 'conversation'):
        self.domain = Domain.load(domainFile)
        self.tracker = MongoTrackerStore(domain=self.domain, host=mongo_url, db=mongo_db)

    def fetch_chat_history(self, sender):
        events = self.tracker.retrieve(sender).as_dialogue().events
        for event in events:
            event_data = event.as_dict()
            if event_data['event'] in ['user', 'bot']:
                yield {'event': event_data['event'], 'text': event_data['text']}

    def fetch_chat_users(self):
        return self.tracker.keys()
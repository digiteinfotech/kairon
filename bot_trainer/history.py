from rasa.core.tracker_store import MongoTrackerStore
from rasa.core.domain import Domain
class ChatHistory:
    def __init__(self, domainFile: str, mongo_url :str, mongo_db = 'conversation'):
        self.domain = Domain.load(domainFile)
        self.tracker = MongoTrackerStore(domain=self.domain, host=mongo_url, db=mongo_db)

    def fetch_chat_history(self, sender):
        events = self.tracker.retrieve(sender).as_dialogue().events
        bot_utterance = None
        for i in range(events.__len__()):
            event = events[i]
            event_data = event.as_dict()
            if event_data['event'] in  ['user', 'bot']:
                result = {'event': event_data['event'], 'text': event_data['text'], 'timestamp' : event_data['timestamp']}
                if event_data['event']  == 'user':
                    parse_data = event_data['parse_data']
                    result['intent'] = parse_data['intent'] ['name']
                    result['confidence'] = parse_data['intent']['confidence']
                elif event_data['event'] == 'bot':
                        if bot_utterance:
                            result['response'] = bot_utterance
                yield result
            else:
                bot_utterance = event_data['name'] if event_data['event'] == 'action' else None

    def fetch_chat_users(self):
        return self.tracker.keys()
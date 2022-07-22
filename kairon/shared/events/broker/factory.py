from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.events.broker.mongo import MongoBroker

Utility.load_environment()


class BrokerFactory:

    __brokers = {
        "mongo": MongoBroker
    }

    @staticmethod
    def get_instance():
        """
        Factory to retrieve instance of broker configured for event.
        """
        broker_type = Utility.environment['events']['queue'].get('type')
        if broker_type not in BrokerFactory.__brokers.keys():
            valid_types = [br for br in BrokerFactory.__brokers.keys()]
            raise AppException(f"Not a valid broker type. Accepted types: {valid_types}")
        return BrokerFactory.__brokers[broker_type].create_instance()

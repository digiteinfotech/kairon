from kairon.events.definitions.content_importer import DocContentImporterEvent
from kairon.events.definitions.data_generator import DataGenerationEvent
from kairon.events.definitions.data_importer import TrainingDataImporterEvent
from kairon.events.definitions.history_delete import DeleteHistoryEvent
from kairon.events.definitions.message_broadcast import MessageBroadcastEvent
from kairon.events.definitions.model_testing import ModelTestingEvent
from kairon.events.definitions.model_training import ModelTrainingEvent
from kairon.events.definitions.multilingual import MultilingualEvent
from kairon.exceptions import AppException
from kairon.shared.constants import EventClass
from kairon.events.definitions.faq_importer import FaqDataImporterEvent


class EventFactory:

    __events = {
        EventClass.model_training: ModelTrainingEvent,
        EventClass.model_testing: ModelTestingEvent,
        EventClass.delete_history: DeleteHistoryEvent,
        EventClass.data_importer: TrainingDataImporterEvent,
        EventClass.multilingual: MultilingualEvent,
        EventClass.data_generator: DataGenerationEvent,
        EventClass.faq_importer: FaqDataImporterEvent,
        EventClass.message_broadcast: MessageBroadcastEvent,
        EventClass.content_importer: DocContentImporterEvent
    }

    @staticmethod
    def get_instance(event_class: EventClass):
        """
        Factory to retrieve event implementation for execution.

        :param event_class: valid event class
        """
        if event_class not in EventFactory.__events.keys():
            valid_events = [ev.value for ev in EventClass]
            raise AppException(f"{event_class} is not a valid event. Accepted event types: {valid_events}")
        return EventFactory.__events[event_class]

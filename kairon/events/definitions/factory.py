from kairon.events.definitions.agentic_flow import AgenticFlowEvent
from kairon.events.definitions.analytic_pipeline_handler import AnalyticsPipelineEvent
from kairon.events.definitions.content_importer import DocContentImporterEvent
from kairon.events.definitions.data_importer import TrainingDataImporterEvent
from kairon.events.definitions.faq_importer import FaqDataImporterEvent
from kairon.events.definitions.history_delete import DeleteHistoryEvent
from kairon.events.definitions.mail_channel import MailReadEvent
from kairon.events.definitions.message_broadcast import MessageBroadcastEvent
from kairon.events.definitions.model_testing import ModelTestingEvent
from kairon.events.definitions.model_training import ModelTrainingEvent
from kairon.events.definitions.multilingual import MultilingualEvent
from kairon.events.definitions.upload_handler import UploadHandler
from kairon.exceptions import AppException
from kairon.shared.constants import EventClass
from kairon.events.definitions.catalog_sync import CatalogSync


class EventFactory:

    __events = {
        EventClass.model_training: ModelTrainingEvent,
        EventClass.model_testing: ModelTestingEvent,
        EventClass.delete_history: DeleteHistoryEvent,
        EventClass.data_importer: TrainingDataImporterEvent,
        EventClass.multilingual: MultilingualEvent,
        EventClass.faq_importer: FaqDataImporterEvent,
        EventClass.message_broadcast: MessageBroadcastEvent,
        EventClass.content_importer: DocContentImporterEvent,
        EventClass.mail_channel_read_mails: MailReadEvent,
        EventClass.agentic_flow: AgenticFlowEvent,
        EventClass.catalog_integration: CatalogSync,
        EventClass.upload_file_handler: UploadHandler,
        EventClass.analytics_pipeline: AnalyticsPipelineEvent
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

import datetime

from bson import ObjectId
from loguru import logger
from mongoengine import signals, QuerySet
from mongoengine.signals import Namespace

_custom_signal = Namespace()

auditlog = _custom_signal.signal("auditlog")

def handler(event1):
    """Signal decorator to allow use of callback functions as class decorators."""

    def decorator(fn):
        def apply(cls):
            event1.connect(fn, sender=cls)
            return cls

        fn.apply = apply
        return fn

    return decorator


@handler(signals.post_save)
def push_notification(sender, document, **kwargs):
    from kairon.shared.utils import Utility
    from kairon.shared.data.data_objects import ModelTraining, ModelDeployment
    from kairon.shared.importer.data_objects import ValidationLogs
    from kairon.shared.test.data_objects import ModelTestingLogs

    is_enabled = Utility.environment['notifications']['enable']
    message_type_events = [ModelTraining, ModelTestingLogs, ModelDeployment, ValidationLogs]
    message_type_events = {event.__name__ for event in message_type_events}
    if is_enabled:
        try:
            metadata = document.to_mongo().to_dict()

            for key in metadata:
                if isinstance(metadata[key], ObjectId) or isinstance(metadata[key], datetime.datetime):
                    metadata[key] = metadata[key].__str__()

            if sender.__name__ in message_type_events:
                event_type = 'message'
            elif kwargs.get('created'):
                event_type = 'create'
            else:
                event_type = 'update'
                if metadata.get('status') is False:
                    event_type = 'delete'
            Utility.push_notification(document.bot, event_type, sender.__name__, metadata)
        except Exception as e:
            logger.exception(e)


def push_bulk_update_notification(sender, documents, **kwargs):
    from kairon.shared.utils import Utility

    is_enabled = Utility.environment['notifications']['enable']
    if is_enabled:
        try:
            if isinstance(documents, QuerySet):
                documents = list(documents)
            if documents:
                channel = kwargs['bot']
                event_type = kwargs['event_type']
                metadata = []
                for doc in documents:
                    doc = doc.to_mongo().to_dict()
                    metadata.append({'_id': doc['_id'].__str__()})
                Utility.push_notification(channel, event_type, sender.__name__, metadata)
        except Exception as e:
            logger.exception(e)


def auditlogger_handler(event1):
    """Signal decorator to allow use of callback functions as class decorators."""
    def decorator(fn):
        def log(cls):
            event1.connect(fn, sender=cls)
            return cls

        fn.log = log
        return fn

    return decorator


@auditlogger_handler(auditlog)
def auditlogger(sender, document, **kwargs):

    from kairon.shared.data.audit.processor import AuditDataProcessor
    AuditDataProcessor.save_and_publish_auditlog(document, sender.__name__, **kwargs)

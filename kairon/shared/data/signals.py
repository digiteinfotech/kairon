import datetime
from bson import ObjectId
from mongoengine import signals, QuerySet
from loguru import logger


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
    from kairon import Utility
    from kairon.shared.data.data_objects import ModelTraining, ModelDeployment, TrainingDataGenerator
    from kairon.shared.importer.data_objects import ValidationLogs
    from kairon.shared.test.data_objects import ModelTestingLogs

    is_enabled = Utility.environment['notifications']['enable']
    message_type_events = [ModelTraining, ModelTestingLogs, ModelDeployment, TrainingDataGenerator, ValidationLogs]
    message_type_events = {event.__name__ for event in message_type_events}
    if is_enabled:
        try:
            metadata = document.to_mongo().to_dict()

            for key in metadata:
                if isinstance(metadata[key], ObjectId):
                    metadata[key] = metadata[key].__str__()
                elif isinstance(metadata[key], datetime.datetime):
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
    from kairon import Utility

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


from kairon.shared.actions.data_objects import GoogleSearchAction, EmailActionConfig, JiraAction, ZendeskAction
signals.pre_save_post_validation.connect(GoogleSearchAction.pre_save_post_validation, sender=GoogleSearchAction)
signals.pre_save_post_validation.connect(EmailActionConfig.pre_save_post_validation, sender=EmailActionConfig)
signals.pre_save_post_validation.connect(JiraAction.pre_save_post_validation, sender=JiraAction)
signals.pre_save_post_validation.connect(ZendeskAction.pre_save_post_validation, sender=ZendeskAction)

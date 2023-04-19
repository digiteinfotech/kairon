from mongoengine import Document, StringField, DateTimeField, DictField, DynamicDocument, EmbeddedDocument, \
    EmbeddedDocumentField, ValidationError, ListField, BooleanField

from kairon import Utility
from kairon.shared.data.signals import push_notification
from datetime import datetime
from kairon.shared.chat.notifications.constants import MessageBroadcastLogType
from croniter import croniter


class SchedulerConfiguration(EmbeddedDocument):
    """
    expression_type: Only supports cron jobs for now. Can be extended to ``date``, ``interval`` in future.
    schedule: When the job should be run.
            Eg: "* * * * *", "30 5 * * *"
    """
    expression_type = StringField(default="cron", choices=["cron"])
    schedule = StringField(required=True)

    def validate(self, clean=True):
        if clean:
            self.clean()

        if self.expression_type == "cron":
            if not self.schedule or not croniter.is_valid(self.schedule):
                raise ValidationError(f"Invalid cron expression: '{self.schedule}'")
            first_occurrence = croniter(self.schedule).get_next(ret_type=datetime)
            second_occurrence = croniter(self.schedule).get_next(ret_type=datetime, start_time=first_occurrence)
            min_trigger_interval = Utility.environment["events"]["scheduler"]["min_trigger_interval"]
            if (second_occurrence - first_occurrence).total_seconds() < min_trigger_interval:
                raise ValidationError(f"recurrence interval must be at least {min_trigger_interval} seconds!")

    def clean(self):
        self.schedule = self.schedule.strip()


class RecipientsConfiguration(EmbeddedDocument):
    """
    recipient_type: If dynamic, it will be assumed that recipients are not hard coded numbers and
                contains expression which will be evaluated using expression evaluator.
    recipients: a static value(eg: "XYZ") or expression(eg: ${data.list.number})
    """
    recipient_type = StringField(required=True, choices=["static", "dynamic"])
    recipients = StringField(required=True)

    def validate(self, clean=True):
        if clean:
            self.clean()

    def clean(self):
        self.recipients = self.recipients.strip()


class DataExtractionConfiguration(EmbeddedDocument):
    """
    method: GET
    url: request url
    headers: request headers
    request_body: if request method is GET, request_body will be passed as parameters.
    """
    method = StringField(required=True, default="GET")
    url = StringField(required=True)
    headers = DictField()
    request_body = DictField()


class TemplateConfiguration(EmbeddedDocument):
    """
    template_type: If dynamic, it will be assumed that template_id and data contain expression and will
                  be evaluated using expression evaluator.
    template_id: Notification template id or an expression. Eg: ${response.list.template-id}.
    data: Can have key value pairs where each key is a placeholder and value will be evaluated.
         Eg:
            0 : ${request.list.name}
            1 : ${request.list.crop}
            2 : ${request.list.activity}
    """
    template_type = StringField(required=True, choices=["static", "dynamic"])
    template_id = StringField(required=True)
    namespace = StringField(required=True)
    data = StringField()

    def validate(self, clean=True):
        if clean:
            self.clean()

    def clean(self):
        if self.data:
            self.data = self.data.strip()


@push_notification.apply
class MessageBroadcastSettings(Document):
    name = StringField(required=True)
    connector_type = StringField(required=True)
    scheduler_config = EmbeddedDocumentField(SchedulerConfiguration)
    data_extraction_config = EmbeddedDocumentField(DataExtractionConfiguration)
    recipients_config = EmbeddedDocumentField(RecipientsConfiguration, required=True)
    template_config = ListField(EmbeddedDocumentField(TemplateConfiguration), required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    status = BooleanField(default=True)
    timestamp = DateTimeField(default=datetime.utcnow)


@push_notification.apply
class MessageBroadcastLogs(DynamicDocument):
    reference_id = StringField(required=True)
    log_type = StringField(required=True, choices=[m.value for m in MessageBroadcastLogType])
    bot = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

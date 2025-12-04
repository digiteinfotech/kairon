import pytz
from mongoengine import Document, StringField, DateTimeField, DynamicDocument, EmbeddedDocument, \
    EmbeddedDocumentField, ValidationError, ListField, BooleanField, IntField, DictField

from kairon import Utility
from kairon.shared.data.audit.data_objects import Auditlog
from kairon.shared.data.signals import push_notification
from datetime import datetime
from kairon.shared.chat.broadcast.constants import MessageBroadcastLogType, MessageBroadcastType
from croniter import croniter


class SchedulerConfiguration(EmbeddedDocument):
    """
    Unified scheduler configuration model.

    Supports:
    - expression_type="cron": recurring schedule based on cron string.
      Example: "* * * * *", "30 5 * * *"
    - expression_type="epoch": one-time schedule based on future epoch time.
      Example: 1765438200
    """

    expression_type = StringField(required=True, choices=["cron", "epoch"])
    schedule = StringField(required=True)
    timezone = StringField(required=True)

    def validate(self, clean=True):
        if clean:
            self.clean()

        if not self.timezone or not self.timezone.strip():
            raise ValidationError("timezone is required for all schedules!")
        try:
            pytz.timezone(self.timezone)
        except pytz.UnknownTimeZoneError:
            raise ValidationError(f"Unknown timezone: {self.timezone}")

        if self.expression_type == "cron":
            if not self.schedule or not croniter.is_valid(self.schedule):
                raise ValidationError(f"Invalid cron expression: '{self.schedule}'")

            first_occurrence = croniter(self.schedule).get_next(ret_type=datetime)
            second_occurrence = croniter(
                self.schedule, start_time=first_occurrence
            ).get_next(ret_type=datetime)

            min_trigger_interval = Utility.environment["events"]["scheduler"]["min_trigger_interval"]
            if (second_occurrence - first_occurrence).total_seconds() < min_trigger_interval:
                raise ValidationError(
                    f"Recurrence interval must be at least {min_trigger_interval} seconds!"
                )

    def clean(self):
        """Strip strings and normalize types."""
        if self.schedule and isinstance(self.schedule, str):
            self.schedule = self.schedule.strip()
        if self.timezone and isinstance(self.timezone, str):
            self.timezone = self.timezone.strip()



class RecipientsConfiguration(EmbeddedDocument):
    """
    recipient_type: If dynamic, it will be assumed that recipients are not hard coded numbers and
                contains expression which will be evaluated using expression evaluator.
    recipients: a static value(eg: "XYZ") or expression(eg: ${data.list.number})
    """
    recipients = StringField(required=True)

    def validate(self, clean=True):
        if clean:
            self.clean()

    def clean(self):
        if not Utility.check_empty_string(self.recipients):
            self.recipients = self.recipients.strip()

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
    template_id = StringField(required=True)
    language = StringField(default="en")
    data = StringField()

    def validate(self, clean=True):
        if clean:
            self.clean()

    def clean(self):
        if not Utility.check_empty_string(self.data):
            self.data = self.data.strip()


@push_notification.apply
class MessageBroadcastSettings(Auditlog):
    name = StringField(required=True)
    connector_type = StringField(required=True)
    broadcast_type = StringField(required=True, choices=[MessageBroadcastType.static.value, MessageBroadcastType.dynamic.value, MessageBroadcastType.flow.value])
    scheduler_config = EmbeddedDocumentField(SchedulerConfiguration)
    recipients_config = EmbeddedDocumentField(RecipientsConfiguration)
    template_config = ListField(EmbeddedDocumentField(TemplateConfiguration))
    collection_config = DictField(default=dict)
    pyscript = StringField()
    flowname = StringField()
    template_name = StringField(default=None)
    language_code = StringField(default=None)
    retry_count = IntField(default=0)
    bot = StringField(required=True)
    user = StringField(required=True)
    status = BooleanField(default=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    meta = {"indexes": [{"fields": ["bot", ("id", "bot", "status")]}]}

    def validate(self, clean=True):
        if self.broadcast_type == MessageBroadcastType.static.value:
            if not self.template_config or not self.recipients_config:
                raise ValidationError("recipients_config and template_config is required for static broadcasts!")
        if self.broadcast_type == MessageBroadcastType.dynamic.value and Utility.check_empty_string(self.pyscript):
            raise ValidationError("pyscript is required for dynamic broadcasts!")
        if self.scheduler_config:
            self.scheduler_config.validate()
        if self.recipients_config:
            self.recipients_config.validate()
        for template in self.template_config or []:
            template.validate()


@push_notification.apply
class MessageBroadcastLogs(DynamicDocument):
    reference_id = StringField(required=True)
    log_type = StringField(required=True, choices=[m.value for m in MessageBroadcastLogType])
    bot = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    meta = {"indexes": [{"fields": ["bot", ("bot", "reference_id", "-timestamp")]}]}


@push_notification.apply
class AnalyticsPipelineLogs(DynamicDocument):
    event_id = StringField(required=True)
    status = StringField(required=True)
    pipeline_name = StringField()
    callback_name = StringField
    exception = StringField()
    start_time = DateTimeField()
    end_time = DateTimeField()

    meta = {
        "indexes": [
            "event_id",
            "status",
            "-start_time",
            "-end_time"
        ]
    }


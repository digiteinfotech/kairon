from mongoengine import Document

from kairon.shared.actions.data_objects import ActionServerLogs
from kairon.shared.callback.data_objects import CallbackLog
from kairon.shared.catalog_sync.data_objects import CatalogSyncLogs
from kairon.shared.channels.mail.data_objects import MailResponseLog
from kairon.shared.content_importer.data_objects import ContentValidationLogs
from kairon.shared.custom_widgets.data_objects import CustomWidgetsRequestLog
from kairon.shared.data.audit.data_objects import AuditLogData
from kairon.shared.data.data_objects import ConversationsHistoryDeleteLogs
from kairon.shared.events.data_objects import ExecutorLogs
from kairon.shared.importer.data_objects import ValidationLogs
from kairon.shared.llm.data_objects import LLMLogs
from kairon.shared.log_system.factory import LogHandlerFactory
from kairon.shared.metering.data_object import Metering
from kairon.shared.multilingual.data_objects import BotReplicationLogs
from kairon.shared.test.data_objects import ModelTestingLogs


class LogExecutor:
    DOC_TYPE_MAPPING = {
        "content": ContentValidationLogs,
        "importer": ValidationLogs,
        "history_deletion": ConversationsHistoryDeleteLogs,
        "multilingual": BotReplicationLogs,
        "catalog": CatalogSyncLogs,
        "custom_widget": CustomWidgetsRequestLog,
        "mail_channel": MailResponseLog,
        "callback_logs": CallbackLog,
        "llm": LLMLogs,
        "actions": ActionServerLogs,
        "executor": ExecutorLogs,
        "agent_handoff": Metering,
        "audit": AuditLogData,
        "action_server_logs": ActionServerLogs,
        "model_test": ModelTestingLogs
    }

    @staticmethod
    def get_logs(bot, log_type, start_idx=0, page_size=10, **kwargs):
        if log_type not in LogExecutor.DOC_TYPE_MAPPING:
            return [], 0
        doc_type = LogExecutor.DOC_TYPE_MAPPING[log_type]
        handler = LogHandlerFactory.get_handler(log_type, doc_type, bot, start_idx, page_size, **kwargs)
        return handler.get_logs_and_count()

    @staticmethod
    def get_logs_count(document: Document, **kwargs):
        return document.objects(**kwargs).count()

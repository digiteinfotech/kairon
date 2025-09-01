from abc import ABC, abstractmethod
from datetime import datetime,timedelta

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
from kairon.shared.metering.data_object import Metering
from kairon.shared.multilingual.data_objects import BotReplicationLogs
from kairon.shared.test.data_objects import ModelTestingLogs


class BaseLogHandler(ABC):
    def __init__(self, doc_type, bot, start_idx, page_size, **kwargs):
        self.doc_type = doc_type
        self.bot = bot
        self.start_idx = start_idx
        self.page_size = page_size
        self.kwargs = kwargs

    @abstractmethod
    def get_logs_and_count(self):
        pass

    __doc_type_mapping = {
        "content": ContentValidationLogs,
        "importer": ValidationLogs,
        "history_deletion": ConversationsHistoryDeleteLogs,
        "multilingual": BotReplicationLogs,
        "catalog": CatalogSyncLogs,
        "custom_widget": CustomWidgetsRequestLog,
        "mail_channel": MailResponseLog,
        "callback": CallbackLog,
        "llm": LLMLogs,
        "actions": ActionServerLogs,
        "executor": ExecutorLogs,
        "agent_handoff": Metering,
        "audit": AuditLogData,
        "model_test": ModelTestingLogs
    }

    @classmethod
    def _get_doc_type(cls, log_type: str):
        return cls.__doc_type_mapping.get(log_type)

    @staticmethod
    def get_logs_count(document: Document, **kwargs) -> int:
        return document.objects(**kwargs).count()

    @classmethod
    def _get_handler(cls, log_type: str, bot: str, start_idx: int = 0, page_size: int = 10, **kwargs):
        from kairon.shared.log_system.factory import LogHandlerFactory

        doc_type = cls._get_doc_type(log_type)
        if not doc_type:
            return None

        return LogHandlerFactory.get_handler(log_type, doc_type, bot, start_idx, page_size, **kwargs)

    @staticmethod
    def convert_logs_cursor_to_dict(logs_cursor):
        logs = []
        for log in logs_cursor:
            log_dict = log.to_mongo().to_dict()
            if "_id" in log_dict:
                log_dict["_id"] = str(log_dict["_id"])
            if "data" in log_dict and log_dict["data"] and "_id" in log_dict["data"]:
                log_dict["data"]["_id"] = str(log_dict["data"]["_id"])
            logs.append(log_dict)
        return logs

    @staticmethod
    def get_logs(bot, log_type: str, start_idx: int = 0, page_size: int = 10, **kwargs):
        handler = BaseLogHandler._get_handler(log_type, bot, start_idx, page_size, **kwargs)
        return handler.get_logs_and_count() if handler else ([], 0)

    @staticmethod
    def get_logs_search_result(bot, log_type: str, start_idx: int = 0, page_size: int = 10, **kwargs):
        handler = BaseLogHandler._get_handler(log_type, bot, start_idx, page_size, **kwargs)
        if log_type == "mail_channel":
            return handler.get_logs_for_search_query_for_unix_time() if handler else ([], 0)
        return handler.get_logs_for_search_query() if handler else ([], 0)

    @staticmethod
    def get_default_dates(kwargs, logs):
        from_date = kwargs.pop("from_date", None) or (datetime.utcnow() - timedelta(days=30))
        to_date = kwargs.pop("to_date", None) or datetime.utcnow()
        if logs == "count":
            return from_date, to_date
        elif logs == "search":
            query = {}
            stamp = kwargs.pop("stamp", "timestamp")
            query[f"{stamp}__gte"] = from_date
            query[f"{stamp}__lte"] = to_date + timedelta(days=1)
            query.update(kwargs)
            return query

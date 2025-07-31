import os
from datetime import date

import pytest
from unittest.mock import MagicMock, patch

from kairon.shared.actions.data_objects import ActionServerLogs
from kairon.shared.callback.data_objects import CallbackLog
from kairon.shared.custom_widgets.data_objects import CustomWidgetsRequestLog
from kairon.shared.data.audit.data_objects import AuditLogData
from kairon.shared.events.data_objects import ExecutorLogs
from kairon.shared.llm.data_objects import LLMLogs
from kairon.shared.log_system.base import BaseLogHandler
from kairon.shared.log_system.factory import LogHandlerFactory
from kairon.shared.log_system.handlers.actions_logs_handler import ActionLogHandler
from kairon.shared.log_system.handlers.audit_logs_handler import AuditLogHandler
from kairon.shared.log_system.handlers.callback_logs_handler import CallbackLogHandler
from kairon.shared.log_system.handlers.default_log_handler import DefaultLogHandler
from kairon.shared.log_system.handlers.executor_logs_handler import ExecutorLogHandler
from kairon.shared.log_system.handlers.live_agent_logs_handler import AgentHandoffLogHandler
from kairon.shared.log_system.handlers.llm_logs_handler import LLMLogHandler
from kairon.shared.log_system.handlers.model_testing_logs_handler import ModelTestingHandler
from kairon.shared.metering.data_object import Metering
from kairon.shared.test.data_objects import ModelTestingLogs
from kairon.shared.utils import Utility
from kairon.shared.data.processor import MongoProcessor
mongo_processor = MongoProcessor()

os.environ["system_file"] = "./tests/testing_data/system.yaml"
Utility.load_environment()
Utility.load_system_metadata()

doc_type = "log"
bot = "test_bot"
start_idx = 0
page_size = 10
common_kwargs = {"user": "test@user.com"}

@pytest.mark.parametrize(
    "log_type, expected_class",
    [
        ("llm", LLMLogHandler),
        ("actions", ActionLogHandler),
        ("callback", CallbackLogHandler),
        ("executor", ExecutorLogHandler),
        ("agent_handoff", AgentHandoffLogHandler),
        ("audit", AuditLogHandler),
        ("unknown_type", DefaultLogHandler),
        ("model_test", ModelTestingHandler)
    ]
)
def test_log_handler_factory_returns_correct_handler(log_type, expected_class):
    handler = LogHandlerFactory.get_handler(
        log_type, doc_type, bot, start_idx, page_size, **common_kwargs
    )
    assert isinstance(handler, expected_class)


@pytest.mark.parametrize(
    "log_type, expected_handler_class, doc_type",
    [
        ("llm", LLMLogHandler, LLMLogs),
        ("actions", ActionLogHandler, ActionServerLogs),
        ("callback", CallbackLogHandler, CallbackLog),
        ("executor", ExecutorLogHandler, ExecutorLogs),
        ("agent_handoff", AgentHandoffLogHandler, Metering),
        ("audit", AuditLogHandler, AuditLogData),
        ("custom_widget", DefaultLogHandler, CustomWidgetsRequestLog),
        ("model_test", ModelTestingHandler, ModelTestingLogs)

    ]
)
def test_get_logs_with_mocked_handlers(log_type, expected_handler_class, doc_type):
    dummy_logs = [{"message": "log1"}, {"message": "log2"}]
    dummy_count = 2

    mock_handler = MagicMock()
    mock_handler.get_logs_and_count.return_value = (dummy_logs, dummy_count)

    with patch("kairon.shared.log_system.factory.LogHandlerFactory.get_handler", return_value=mock_handler) as mocked_get_handler:
        logs, count = BaseLogHandler.get_logs(bot="test_bot", log_type=log_type, start_idx=0, page_size=10)

        assert logs == dummy_logs
        assert count == dummy_count

        mocked_get_handler.assert_called_once_with(
            log_type, doc_type, "test_bot", 0, 10
        )

@pytest.mark.parametrize(
    "log_type, keys, values, expected",
    [
        ("actions", ["from_date", "to_date", "status"], ["2025-01-01", "2025-07-30", "Success"], {
            "from_date": date(2025, 1, 1),
            "to_date": date(2025, 7, 30),
            "status": "Success"
        }),
        ("audit", ["action"], ["save"], {
            "action": "save"
        }),
    ]
)
def test_sanitize_query_filter_valid(log_type, keys, values, expected):
    result = mongo_processor.sanitize_query_filter(log_type, keys, values)
    assert result == expected


@pytest.mark.parametrize(
    "log_type, keys, values, expected_exception, expected_message",
    [
        ("unknown_type", ["status"], ["Success"], ValueError, "Unsupported log type: unknown_type"),
        ("actions", ["status"], [], ValueError, "Number of keys and values must match."),
        ("actions", [""], ["Success"], ValueError, "Search key cannot be empty or blank."),
        ("actions", ["non_existing_key"], ["Success"], ValueError, "Invalid query key: 'non_existing_key'"),
        ("actions", ["sta tus"], ["Success"], ValueError, "Invalid query key: 'sta tus' for log_type: 'actions'"),
        ("actions", ["status"], [""], ValueError, "Search value cannot be empty or blank."),
        ("actions", ["from_date"], ["not-a-date"], ValueError, "Invalid isoformat string"),
    ]
)
def test_sanitize_query_filter_invalid(log_type, keys, values, expected_exception, expected_message):
    with pytest.raises(expected_exception) as exc:
        mongo_processor.sanitize_query_filter(log_type, keys, values)
    assert expected_message in str(exc.value)
import os
import pytest
from unittest.mock import MagicMock, patch

from kairon.shared.actions.data_objects import ActionServerLogs
from kairon.shared.callback.data_objects import CallbackLog
from kairon.shared.custom_widgets.data_objects import CustomWidgetsRequestLog
from kairon.shared.data.audit.data_objects import AuditLogData
from kairon.shared.events.data_objects import ExecutorLogs
from kairon.shared.llm.data_objects import LLMLogs
from kairon.shared.log_system.factory import LogHandlerFactory
from kairon.shared.log_system.executor import LogExecutor
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
        ("action_server_logs", ActionLogHandler),
        ("callback_logs", CallbackLogHandler),
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
        ("action_server_logs", ActionLogHandler, ActionServerLogs),
        ("callback_logs", CallbackLogHandler, CallbackLog),
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

    with patch("kairon.shared.log_system.executor.LogHandlerFactory.get_handler", return_value=mock_handler) as mocked_get_handler:
        logs, count = LogExecutor.get_logs(bot="test_bot", log_type=log_type, start_idx=0, page_size=10)

        assert logs == dummy_logs
        assert count == dummy_count

        mocked_get_handler.assert_called_once_with(
            log_type, doc_type, "test_bot", 0, 10
        )
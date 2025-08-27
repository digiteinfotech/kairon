import os
from datetime import date, datetime,timedelta

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
class DummyRequest:
    def __init__(self, query_params):
        self.query_params = query_params

@pytest.fixture
def mock_action_handler():
    h = ActionLogHandler(
        doc_type=MagicMock(),
        bot="test-bot",
        start_idx=0,
        page_size=10,
    )
    h.kwargs = {}
    return h

def test_query_includes_dates(mock_action_handler):
    custom_from = datetime(2025, 8, 1, 10, 0, 0)
    custom_to = datetime(2025, 8, 5, 18, 0, 0)
    mock_action_handler.kwargs = {"from_date": custom_from, "to_date": custom_to}
    mock_action_handler.doc_type.objects = MagicMock()
    mock_action_handler.get_logs_count = MagicMock(return_value=0)

    try:
        mock_action_handler.get_logs_and_count()
    except Exception:
        pass

    query = mock_action_handler.doc_type.objects.call_args.kwargs
    assert query["timestamp__gte"] == custom_from
    assert query["timestamp__lte"] == custom_to

def test_default_dates_for_actions_logs(mock_action_handler):
    mock_action_handler.doc_type.objects = MagicMock()
    mock_action_handler.get_logs_count = MagicMock(return_value=0)

    try:
        mock_action_handler.get_logs_and_count()
    except Exception:
        pass

    query = mock_action_handler.doc_type.objects.call_args.kwargs
    from_date = query["timestamp__gte"]
    to_date = query["timestamp__lte"]
    now = datetime.utcnow()
    expected_from = (now - timedelta(days=30)).date()
    expected_to = now.date()
    assert from_date.date() == expected_from
    assert to_date.date() == expected_to

def mock_audit_handler(kwargs=None):
    return AuditLogHandler(
        doc_type=MagicMock(),
        bot="test-bot",
        start_idx=0,
        page_size=10,
        **(kwargs or {})
    )

def test_default_from_to_dates_for_audit_logs():
    handler = mock_audit_handler()
    handler.doc_type.objects = MagicMock()

    try:
        handler.get_logs_and_count()
    except Exception:
        pass

    query = handler.doc_type.objects.call_args.kwargs
    now = datetime.utcnow()
    expected_from = (now - timedelta(days=30)).date()
    expected_to = now.date()
    assert query["timestamp__gte"].date() == expected_from
    assert query["timestamp__lte"].date() == expected_to
    assert query["attributes__key"] == "bot"
    assert query["attributes__value"] == "test-bot"

def test_custom_from_to_dates_for_audit_logs():
    from_date = datetime(2025, 1, 10, 0, 0, 0)
    to_date = datetime(2025, 1, 20, 23, 59, 59)
    handler = mock_audit_handler(kwargs={"from_date": from_date, "to_date": to_date})
    handler.doc_type.objects = MagicMock()

    try:
        handler.get_logs_and_count()
    except Exception:
        pass

    query = handler.doc_type.objects.call_args.kwargs
    assert query["timestamp__gte"] == from_date
    assert query["timestamp__lte"] == to_date
    assert query["attributes__key"] == "bot"
    assert query["attributes__value"] == "test-bot"

def mock_callback_handler(kwargs=None):
    return CallbackLogHandler(
        doc_type=MagicMock(),
        bot="test-bot",
        start_idx=0,
        page_size=10,
        **(kwargs or {})
    )

def test_default_from_to_dates_for_callback_logs():
    handler = mock_callback_handler()
    handler.doc_type.objects = MagicMock()

    try:
        handler.get_logs_and_count()
    except Exception:
        pass

    query_kwargs = handler.doc_type.objects.call_args.kwargs
    now = datetime.utcnow()
    expected_from = (now - timedelta(days=30)).date()
    expected_to = now.date()
    assert query_kwargs["timestamp__gte"].date() == expected_from
    assert query_kwargs["timestamp__lte"].date() == expected_to
    assert query_kwargs["bot"] == "test-bot"

def test_custom_from_to_dates_for_callback_logs():
    from_date = datetime(2025, 8, 1, 0, 0, 0)
    to_date = datetime(2025, 8, 15, 23, 59, 59)
    handler = mock_callback_handler(kwargs={"from_date": from_date, "to_date": to_date})
    handler.doc_type.objects = MagicMock()

    try:
        handler.get_logs_and_count()
    except Exception:
        pass

    query_kwargs = handler.doc_type.objects.call_args.kwargs
    assert query_kwargs["timestamp__gte"] == from_date
    assert query_kwargs["timestamp__lte"] == to_date
    assert query_kwargs["bot"] == "test-bot"

def mock_executor_handler(kwargs=None):
    return ExecutorLogHandler(
        doc_type=MagicMock(),
        bot="test-bot",
        start_idx=0,
        page_size=10,
        **(kwargs or {})
    )

def test_default_from_to_dates_for_executor_logs():
    handler = mock_executor_handler()
    handler.doc_type.objects = MagicMock()

    try:
        handler.get_logs_and_count()
    except Exception:
        pass

    query_kwargs = handler.doc_type.objects.call_args.kwargs
    now = datetime.utcnow()
    expected_from = (now - timedelta(days=30)).date()
    expected_to = now.date()
    assert query_kwargs["timestamp__gte"].date() == expected_from
    assert query_kwargs["timestamp__lte"].date() == expected_to
    assert query_kwargs["bot"] == "test-bot"

def test_custom_from_to_dates_for_executor_logs():
    from_date = datetime(2025, 8, 1, 0, 0, 0)
    to_date = datetime(2025, 8, 15, 23, 59, 59)
    handler = mock_executor_handler(kwargs={"from_date": from_date, "to_date": to_date})
    handler.doc_type.objects = MagicMock()

    try:
        handler.get_logs_and_count()
    except Exception:
        pass

    query_kwargs = handler.doc_type.objects.call_args.kwargs
    assert query_kwargs["timestamp__gte"] == from_date
    assert query_kwargs["timestamp__lte"] == to_date
    assert query_kwargs["bot"] == "test-bot"

def mock_llm_handler(kwargs=None):
    return LLMLogHandler(
        doc_type=MagicMock(),
        bot="test-bot",
        start_idx=0,
        page_size=10,
        **(kwargs or {})
    )

def test_default_from_to_dates_for_llm_logs():
    handler = mock_llm_handler()
    handler.doc_type.objects = MagicMock()

    try:
        handler.get_logs_and_count()
    except Exception:
        pass

    query_kwargs = handler.doc_type.objects.call_args.kwargs
    now = datetime.utcnow()
    expected_from = (now - timedelta(days=30)).date()
    expected_to = now.date()
    assert query_kwargs["start_time__gte"].date() == expected_from
    assert query_kwargs["start_time__lte"].date() == expected_to
    assert query_kwargs["metadata__bot"] == "test-bot"

def test_custom_from_to_dates_for_llm_logs():
    from_date = datetime(2025, 8, 1, 0, 0, 0)
    to_date = datetime(2025, 8, 15, 23, 59, 59)
    handler = mock_llm_handler(kwargs={"from_date": from_date, "to_date": to_date})
    handler.doc_type.objects = MagicMock()

    try:
        handler.get_logs_and_count()
    except Exception:
        pass

    query_kwargs = handler.doc_type.objects.call_args.kwargs
    assert query_kwargs["start_time__gte"] == from_date
    assert query_kwargs["start_time__lte"] == to_date
    assert query_kwargs["metadata__bot"] == "test-bot"

def mock_model_testing_handler(kwargs=None):
    return ModelTestingHandler(
        doc_type=ModelTestingLogs,
        bot="test-bot",
        start_idx=0,
        page_size=10,
        **(kwargs or {})
    )

def test_default_from_to_dates_for_model_testing_logs():
    handler = mock_model_testing_handler()
    handler.doc_type.objects = MagicMock()

    try:
        handler.get_logs_and_count()
    except Exception:
        pass

    query_kwargs = handler.doc_type.objects.call_args.kwargs
    now = datetime.utcnow()
    expected_from = (now - timedelta(days=30)).date()
    expected_to = now.date()

    assert query_kwargs["start_timestamp__gte"].date() == expected_from
    assert query_kwargs["start_timestamp__lte"].date() == expected_to
    assert query_kwargs["bot"] == "test-bot"

def test_custom_from_to_dates_for_model_testing_logs():
    from_date = datetime(2025, 8, 1, 0, 0, 0)
    to_date = datetime(2025, 8, 15, 23, 59, 59)
    handler = mock_model_testing_handler(kwargs={"from_date": from_date, "to_date": to_date})
    handler.doc_type.objects = MagicMock()

    try:
        handler.get_logs_and_count()
    except Exception:
        pass

    query_kwargs = handler.doc_type.objects.call_args.kwargs
    assert query_kwargs["start_timestamp__gte"] == from_date
    assert query_kwargs["start_timestamp__lte"] == to_date
    assert query_kwargs["bot"] == "test-bot"

@pytest.mark.parametrize(
    "log_type, query_params, expected",
    [
        (
            "actions",
            {"from_date": "2025-01-01", "to_date": "2025-07-30", "status": "Success"},
            {"from_date": date(2025, 1, 1), "to_date": date(2025, 7, 30), "status": "Success"}
        ),
        (
            "audit",
            {"action": "save"},
            {"action": "save"}
        ),
        (
            "audit",
            {"start_idx": "0", "page_size": "10"},
            {"start_idx": 0, "page_size": 10}
        )
    ]
)
def test_sanitize_query_filter_valid(monkeypatch, log_type, query_params, expected):
    class DummyDoc:
        _fields = {
            "status": str,
            "action": str,
            "user": str,
            "result": str,
        }

    monkeypatch.setattr(BaseLogHandler, "_get_doc_type", lambda lt: DummyDoc())

    req = DummyRequest(query_params)
    result = mongo_processor.sanitize_query_filter(log_type, req)
    assert result == expected


@pytest.mark.parametrize(
    "log_type, query_params, expected_exception, expected_message",
    [
        # Invalid log type
        ("unknown_type", {"status": "Success"}, ValueError, "Unsupported log type: unknown_type"),

        # Invalid date format
        ("actions", {"from_date": "2025-13-01"}, ValueError, "Invalid date format for 'from_date'"),
        ("actions", {"to_date": "not-a-date"}, ValueError, "Invalid date format for 'to_date'"),

        # Non-integer start_idx/page_size
        ("actions", {"start_idx": "ten"}, ValueError, "'start_idx' must be a valid integer."),
        ("actions", {"page_size": "ten"}, ValueError, "'page_size' must be a valid integer."),

        # Empty key
        ("actions", {"": "Success"}, ValueError, "Search key cannot be empty or blank."),

        # Key not in document fields
        ("actions", {"non_existing_key": "Success"}, ValueError, "Invalid query key: 'non_existing_key'"),

        # Empty value
        ("actions", {"status": ""}, ValueError, "Search value for key 'status' cannot be empty or blank."),

    ]
)
def test_sanitize_query_filter_invalid(monkeypatch, log_type, query_params, expected_exception, expected_message):
    class DummyDoc:
        _fields = {
            "status": str,
            "action": str,
            "user": str,
            "result": str,
        }

    monkeypatch.setattr(BaseLogHandler, "_get_doc_type", lambda lt: DummyDoc() if lt != "unknown_type" else None)


    if "sta@tus" in query_params:
        monkeypatch.setattr(Utility, "special_match", lambda s, pattern=None: False if s == "sta@tus" else True)
    elif "@#Failure" in query_params.values():
        monkeypatch.setattr(Utility, "special_match", lambda s, pattern=None: False if s == "@#Failure" else True)
    else:
        monkeypatch.setattr(Utility, "special_match", lambda s, pattern=None: True)

    monkeypatch.setattr(Utility, "check_empty_string", lambda s: s.strip() == "")

    req = DummyRequest(query_params)

    with pytest.raises(expected_exception) as exc:
        mongo_processor.sanitize_query_filter(log_type, req)

    assert expected_message in str(exc.value)
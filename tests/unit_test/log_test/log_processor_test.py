import os
from datetime import date, datetime, timedelta

import pytest
from unittest.mock import MagicMock, patch

from kairon.exceptions import AppException
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
from kairon.shared.log_system.handlers.file_upload_logs_handler import FileUploadHandler
from kairon.shared.upload_handler.data_objects import UploadHandlerLogs
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
        ("model_test", ModelTestingHandler),
        ("file_upload", FileUploadHandler)
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
        ("model_test", ModelTestingHandler, ModelTestingLogs),
        ("file_upload", FileUploadHandler, UploadHandlerLogs)

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
    ist_offset = timedelta(hours=5, minutes=30)
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
    assert query["timestamp__gte"] == custom_from - ist_offset
    assert query["timestamp__lte"] == custom_to - ist_offset + timedelta(days=1)
    assert query["bot"] == "test-bot"
    assert query["trigger_info__trigger_id"] == ""

def test_default_dates_for_actions_logs():
    fixed_from = datetime(2025, 8, 12, 18, 30, 0)
    fixed_to = datetime(2025, 9, 11, 18, 30, 0)

    with patch(
        "kairon.shared.log_system.base.BaseLogHandler.get_default_dates",
        return_value=(fixed_from, fixed_to)
    ):
        handler = ActionLogHandler(
            doc_type=MagicMock(),
            bot="test-bot",
            start_idx=0,
            page_size=10,
            kwargs={}
        )
        handler.doc_type.objects = MagicMock()
        handler.get_logs_count = MagicMock(return_value=0)
        handler.get_logs_and_count()

        query = handler.doc_type.objects.call_args.kwargs
        assert query["timestamp__gte"] == fixed_from
        assert query["timestamp__lte"] == fixed_to
        assert query["bot"] == "test-bot"
        assert query["trigger_info__trigger_id"] == ""

def mock_audit_handler(kwargs=None):
    return AuditLogHandler(
        doc_type=MagicMock(),
        bot="test-bot",
        start_idx=0,
        page_size=10,
        **(kwargs or {})
    )

def test_default_from_to_dates_for_audit_logs():
    fixed_utc_now = datetime(2025, 8, 12, 12, 0, 0)
    ist_offset = timedelta(hours=5, minutes=30)

    expected_from = datetime.combine(
        (fixed_utc_now - timedelta(days=30)).date(), datetime.min.time()
    ) - ist_offset
    expected_to = datetime.combine(fixed_utc_now.date(), datetime.min.time()) - ist_offset + timedelta(days=1)

    handler = AuditLogHandler(
        doc_type=MagicMock(), bot="test-bot", start_idx=0, page_size=10, kwargs={}
    )
    handler.doc_type.objects = MagicMock()

    with patch(
            "kairon.shared.log_system.base.BaseLogHandler.get_default_dates",
            return_value=(expected_from, expected_to)
    ):
        handler.get_logs_and_count()

    query = handler.doc_type.objects.call_args.kwargs
    assert query["timestamp__gte"] == expected_from
    assert query["timestamp__lte"] == expected_to
    assert query["attributes__key"] == "bot"
    assert query["attributes__value"] == "test-bot"

def test_custom_from_to_dates_for_audit_logs():
    from_date = datetime(2025, 1, 10, 0, 0, 0)
    to_date = datetime(2025, 1, 20, 23, 59, 59)
    ist_offset = timedelta(hours=5, minutes=30)

    expected_from = from_date - ist_offset
    expected_to = to_date - ist_offset + timedelta(days=1)

    handler = mock_audit_handler(kwargs={"from_date": from_date, "to_date": to_date})
    handler.doc_type.objects = MagicMock()

    try:
        handler.get_logs_and_count()
    except Exception:
        pass

    query = handler.doc_type.objects.call_args.kwargs
    assert query["timestamp__gte"] == expected_from
    assert query["timestamp__lte"] == expected_to
    assert query["attributes__key"] == "bot"
    assert query["attributes__value"] == "test-bot"

def mock_callback_handler(kwargs=None):
    if kwargs is None:
        kwargs = {}
    return CallbackLogHandler(
        doc_type=CallbackLog,
        bot="test-bot",
        start_idx=0,
        page_size=10,
        kwargs=kwargs
    )

def test_default_from_to_dates_for_callback_logs():
    fixed_from = datetime(2025, 7, 12, 18, 30, 0)
    fixed_to = datetime(2025, 8, 12, 18, 30, 0)
    with patch(
        "kairon.shared.log_system.base.BaseLogHandler.get_default_dates",
        return_value=(fixed_from, fixed_to)
    ):
        handler = CallbackLogHandler(
            doc_type=CallbackLog,
            bot="test-bot",
            start_idx=0,
            page_size=10,
            kwargs={}
        )

        handler.doc_type.objects = MagicMock()
        handler.get_logs_and_count()
        query_kwargs = handler.doc_type.objects.call_args.kwargs
        assert query_kwargs["timestamp__gte"] == fixed_from
        assert query_kwargs["timestamp__lte"] == fixed_to

def test_custom_from_to_dates_for_callback_logs():
    from_date = datetime(2025, 8, 1, 0, 0, 0)
    to_date = datetime(2025, 8, 15, 23, 59, 59)
    with patch(
        "kairon.shared.log_system.base.BaseLogHandler.get_default_dates",
        return_value=(from_date, to_date)
    ):
        handler = CallbackLogHandler(
            doc_type=CallbackLog,
            bot="test-bot",
            start_idx=0,
            page_size=10,
            kwargs={"from_date": from_date, "to_date": to_date}
        )
        handler.doc_type.objects = MagicMock()
        handler.get_logs_and_count()

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
    fixed_from = datetime(2025, 7, 12, 18, 30, 0)
    fixed_to = datetime(2025, 8, 12, 18, 30, 0)
    with patch(
        "kairon.shared.log_system.base.BaseLogHandler.get_default_dates",
        return_value=(fixed_from, fixed_to)
    ):
        handler = ExecutorLogHandler(
            doc_type=ExecutorLogs,
            bot="test-bot",
            start_idx=0,
            page_size=10,
            kwargs={}
        )
        handler.doc_type.objects = MagicMock()
        handler.get_logs_and_count()
        query_kwargs = handler.doc_type.objects.call_args.kwargs
        assert query_kwargs["timestamp__gte"] == fixed_from, \
            f"Expected timestamp__gte={fixed_from}, got {query_kwargs['timestamp__gte']}"
        assert query_kwargs["timestamp__lte"] == fixed_to, \
            f"Expected timestamp__lte={fixed_to}, got {query_kwargs['timestamp__lte']}"
        assert query_kwargs["bot"] == "test-bot"

def test_custom_from_to_dates_for_executor_logs():
    from_date = datetime(2025, 8, 1, 0, 0, 0)
    to_date = datetime(2025, 8, 15, 23, 59, 59)
    ist_offset = timedelta(hours=5, minutes=30)
    adjusted_from = from_date - ist_offset
    adjusted_to = to_date - ist_offset + timedelta(days=1)

    handler = mock_executor_handler(kwargs={"from_date": from_date, "to_date": to_date})
    handler.doc_type.objects = MagicMock()

    try:
        handler.get_logs_and_count()
    except Exception:
        pass

    query_kwargs = handler.doc_type.objects.call_args.kwargs
    assert query_kwargs["timestamp__gte"] == adjusted_from
    assert query_kwargs["timestamp__lte"] == adjusted_to

def mock_llm_handler(kwargs=None):
    return LLMLogHandler(
        doc_type=MagicMock(),
        bot="test-bot",
        start_idx=0,
        page_size=10,
        **(kwargs or {})
    )

def test_default_from_to_dates_for_llm_logs():
    fixed_from = datetime(2025, 7, 12, 18, 30, 0)
    fixed_to = datetime(2025, 8, 12, 18, 30, 0)
    with patch.object(BaseLogHandler, "get_default_dates", return_value=(fixed_from, fixed_to)):
        handler = LLMLogHandler(
            doc_type=LLMLogs,
            bot="test-bot",
            start_idx=0,
            page_size=10,
            kwargs={}
        )

        handler.doc_type.objects = MagicMock()
        handler.get_logs_and_count()
        query_kwargs = handler.doc_type.objects.call_args.kwargs
        assert query_kwargs["start_time__gte"] == fixed_from
        assert query_kwargs["start_time__lte"] == fixed_to
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
    ist_offset = timedelta(hours=5, minutes=30)
    assert query_kwargs["start_time__gte"] == from_date - ist_offset
    assert query_kwargs["start_time__lte"] == to_date - ist_offset + timedelta(days=1)
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
    fixed_now = datetime(2025, 8, 12, 12, 0, 0)
    ist_offset = timedelta(hours=5, minutes=30)
    expected_from = (fixed_now - timedelta(days=30)) - ist_offset
    expected_to = (fixed_now - ist_offset) + timedelta(days=1)

    with patch("kairon.shared.log_system.handlers.model_testing_logs_handler.BaseLogHandler.get_default_dates",
               return_value=(expected_from, expected_to)):
        handler = ModelTestingHandler(
            doc_type=ModelTestingLogs,
            bot="test_bot",
            start_idx=0,
            page_size=10
        )
        handler.doc_type.objects = MagicMock()
        handler.get_logs_and_count()
        query_kwargs = handler.doc_type.objects.call_args.kwargs

        got_from = query_kwargs["start_timestamp__gte"]
        got_to = query_kwargs["start_timestamp__lte"]
        assert got_from == expected_from
        assert got_to == expected_to

def test_custom_from_to_dates_for_model_testing_logs():
    from_date = datetime(2025, 8, 1, 0, 0, 0)
    to_date = datetime(2025, 8, 15, 23, 59, 59)
    handler = mock_model_testing_handler(kwargs={"from_date": from_date, "to_date": to_date})
    handler.doc_type.objects = MagicMock()

    try:
        handler.get_logs_and_count()
    except Exception:
        pass
    ist_offset = timedelta(hours=5, minutes=30)
    expected_from = from_date - ist_offset
    expected_to = (to_date - ist_offset) + timedelta(days=1)

    query_kwargs = handler.doc_type.objects.call_args.kwargs
    assert query_kwargs["start_timestamp__gte"] == expected_from
    assert query_kwargs["start_timestamp__lte"] == expected_to
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
        ("actions", {"from_date": "2025-13-01"}, AppException, "Invalid date format for 'from_date'"),
        ("actions", {"to_date": "not-a-date"}, AppException, "Invalid date format for 'to_date'"),

        # Non-integer start_idx/page_size
        ("actions", {"start_idx": "ten"}, AppException, "'start_idx' must be a valid integer."),
        ("actions", {"page_size": "ten"}, AppException, "'page_size' must be a valid integer."),

        # Empty key
        ("actions", {"": "Success"}, AppException, "Search key cannot be empty or blank."),

        # Key not in document fields
        ("actions", {"non_existing_key": "Success"}, AppException, "Invalid query key: 'non_existing_key'"),

        # Empty value
        ("actions", {"status": ""}, AppException, "Search value for key 'status' cannot be empty or blank."),

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


def build_match_stage(kwargs, bot="test-bot"):
    query = BaseLogHandler.get_default_dates(kwargs.copy(), "search")

    from_date = query.pop("start_timestamp__gte", None)
    to_date = query.pop("start_timestamp__lte", None)
    match_stage = {"bot": bot}
    match_stage["$and"] = [
        {"start_timestamp": {"$exists": True}},
        {"start_timestamp": {"$gte": from_date, "$lte": to_date}},
    ]

    for k, v in list(query.items()):
        if v is None:
            continue
        if k == "is_augmented":
            match_stage["is_augmented"] = v.lower() == "true"
        else:
            match_stage[k] = v

    return match_stage

def test_match_stage_with_is_augmented_true():
    kwargs = {
        "from_date": datetime(2025, 9, 1),
        "to_date": datetime(2025, 9, 10),
        "is_augmented": "true",
    }

    match_stage = build_match_stage(kwargs)
    assert match_stage["bot"] == "test-bot"
    assert "is_augmented" in match_stage
    assert match_stage["is_augmented"] is True

def test_match_stage_with_is_augmented_false():
    kwargs = {
        "from_date": datetime(2025, 9, 1),
        "to_date": datetime(2025, 9, 10),
        "is_augmented": "false",
    }

    match_stage = build_match_stage(kwargs)
    assert match_stage["is_augmented"] is False


def test_match_stage_with_other_field():
    kwargs = {
        "from_date": datetime(2025, 9, 1),
        "to_date": datetime(2025, 9, 10),
        "status": "completed",
    }

    match_stage = build_match_stage(kwargs)
    assert match_stage["status"] == "completed"
    assert "$and" in match_stage
    assert isinstance(match_stage["$and"], list)

def test_match_stage_skips_none_values():
    kwargs = {
        "from_date": datetime(2025, 9, 1),
        "to_date": datetime(2025, 9, 10),
        "event_status": None,
    }
    match_stage = build_match_stage(kwargs)
    assert "event_status" not in match_stage

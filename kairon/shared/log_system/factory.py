from kairon.shared.log_system.handlers.actions_logs_handler import ActionLogHandler
from kairon.shared.log_system.handlers.audit_logs_handler import AuditLogHandler
from kairon.shared.log_system.handlers.callback_logs_handler import CallbackLogHandler
from kairon.shared.log_system.handlers.default_log_handler import DefaultLogHandler
from kairon.shared.log_system.handlers.executor_logs_handler import ExecutorLogHandler
from kairon.shared.log_system.handlers.live_agent_logs_handler import AgentHandoffLogHandler
from kairon.shared.log_system.handlers.llm_logs_handler import LLMLogHandler
from kairon.shared.log_system.handlers.model_testing_logs_handler import ModelTestingHandler


class LogHandlerFactory:
    handler_map = {
        "llm": LLMLogHandler,
        "action_server_logs": ActionLogHandler,
        "callback_logs": CallbackLogHandler,
        "executor": ExecutorLogHandler,
        "agent_handoff": AgentHandoffLogHandler,
        "audit": AuditLogHandler,
        "model_test": ModelTestingHandler
    }

    @staticmethod
    def get_handler(log_type, doc_type, bot, start_idx, page_size, **kwargs):
        handler_cls = LogHandlerFactory.handler_map.get(log_type, DefaultLogHandler)
        return handler_cls(doc_type, bot, start_idx, page_size, **kwargs)

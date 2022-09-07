from enum import Enum


class MetricType(str, Enum):
    test_chat = "test_chat"
    prod_chat = "prod_chat"
    agent_handoff = "agent_handoff"
    user_metrics = "user_metrics"
    user_login = "user_login"

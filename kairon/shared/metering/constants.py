from enum import Enum


class MetricType(str, Enum):
    test_chat = "test_chat"
    prod_chat = "prod_chat"

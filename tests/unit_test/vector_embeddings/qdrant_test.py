from unittest import mock

import pytest

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.vector_embeddings.db.factory import VectorEmbeddingsDbFactory
from kairon.shared.vector_embeddings.db.qdrant import Qdrant


class TestQdrant:

    @mock.patch.object(ActionUtility, "execute_http_request", autospec=True)
    def test_embedding_search_valid_request_body(self, mock_http_request):
        Utility.load_environment()
        qdrant = Qdrant('5f50fd0a56v098ca10d75d2e')
        request_body = {"ids": [0], "with_payload": True, "with_vector": True}
        mock_http_request.return_value = 'expected_result'
        result = qdrant.embedding_search(request_body)
        assert result == 'expected_result'

    @mock.patch.object(ActionUtility, "execute_http_request", autospec=True)
    def test_payload_search_valid_request_body(self, mock_http_request):
        Utility.load_environment()
        qdrant = Qdrant('5f50fd0a56v098ca10d75d2e')
        request_body = {"filter": {"should": [{"key": "city", "match": {"value": "London"}},
                                              {"key": "color", "match": {"value": "red"}}]}}
        mock_http_request.return_value = 'expected_result'
        result = qdrant.payload_search(request_body)
        assert result == 'expected_result'

    @mock.patch.object(ActionUtility, "execute_http_request", autospec=True)
    def test_perform_operation_valid_op_type_and_request_body(self, mock_http_request):
        Utility.load_environment()
        qdrant = Qdrant('5f50fd0a56v098ca10d75d2e')
        request_body = {}
        mock_http_request.return_value = 'expected_result'
        result_embedding = qdrant.perform_operation('embedding_search', request_body)
        assert result_embedding == 'expected_result'
        result_payload = qdrant.perform_operation('payload_search', request_body)
        assert result_payload == 'expected_result'

    def test_embedding_search_empty_request_body(self):
        Utility.load_environment()
        qdrant = Qdrant('5f50fd0a56v098ca10d75d2e')
        with pytest.raises(ActionFailure):
            qdrant.embedding_search({})

    def test_payload_search_empty_request_body(self):
        Utility.load_environment()
        qdrant = Qdrant('5f50fd0a56v098ca10d75d2e')
        with pytest.raises(ActionFailure):
            qdrant.payload_search({})

    def test_perform_operation_invalid_op_type(self):
        Utility.load_environment()
        qdrant = Qdrant('5f50fd0a56v098ca10d75d2e')
        request_body = {}
        with pytest.raises(AppException, match="Operation type not supported"):
            qdrant.perform_operation("vector_search", request_body)

    def test_get_instance_raises_exception_when_db_not_implemented(self):
        with pytest.raises(AppException, match="Database not yet implemented!"):
            VectorEmbeddingsDbFactory.get_instance("mongo")

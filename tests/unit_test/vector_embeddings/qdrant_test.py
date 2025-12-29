import os

from unittest import mock
from mongoengine import connect

import pytest

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.admin.constants import BotSecretType
from kairon.shared.admin.data_objects import BotSecrets, LLMSecret
from kairon.shared.data.data_objects import LLMSettings
from kairon.shared.vector_embeddings.db.factory import DatabaseFactory
from kairon.shared.vector_embeddings.db.qdrant import Qdrant
import litellm
from kairon.shared.llm.processor import LLMProcessor
from kairon.shared.actions.models import DbActionOperationType
import numpy as np
import litellm


class TestQdrant:

    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    @pytest.mark.asyncio
    @mock.patch.dict(
        Utility.environment,
        {'vector': {"key": "TEST", 'db': 'http://localhost:6333'}}
    )
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    @mock.patch.object(ActionUtility, "execute_http_request", autospec=True)
    async def test_embedding_search_valid_request_body(
            self, mock_http_request, mock_get_embedding
    ):
        # -------------------- SETUP --------------------
        embedding = list(np.random.random(LLMProcessor.__embedding__))
        user = "test"

        Utility.load_environment()

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key="key_value",
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot="5f50fd0a56v098ca10d75d2g",
            user="user"
        )
        llm_secret.save()

        qdrant = Qdrant(
            '5f50fd0a56v098ca10d75d2g',
            '5f50fd0a56v098ca10d75d2g',
            LLMSettings(provider="openai").to_mongo().to_dict()
        )

        # -------------------- MOCKS --------------------
        mock_get_embedding.return_value = [embedding]
        mock_http_request.return_value = 'expected_result'

        # -------------------- EXECUTE --------------------
        result = await qdrant.perform_operation(
            {'embedding_search': 'Hi'},
            user=user
        )

        # -------------------- ASSERT --------------------
        assert result == 'expected_result'
        mock_get_embedding.assert_called_once()
        mock_http_request.assert_called_once()

    @pytest.mark.asyncio
    @mock.patch.object(ActionUtility, "execute_http_request", autospec=True)
    async def test_payload_search_valid_request_body(self, mock_http_request):
        Utility.load_environment()
        qdrant = Qdrant('5f50fd0a56v098ca10d75d2g', '5f50fd0a56v098ca10d75d2g',
                        LLMSettings(provider="openai").to_mongo().to_dict())
        request_body = {DbActionOperationType.payload_search : {"filter": {"should": [{"key": "city", "match": {"value": "London"}},
                                              {"key": "color", "match": {"value": "red"}}]}}}
        mock_http_request.return_value = 'expected_result'
        result = await qdrant.perform_operation(request_body, user="test")
        assert result == 'expected_result'

    @pytest.mark.asyncio
    async def test_perform_operation_valid_op_type_and_request_body(self):
        Utility.load_environment()
        user = "test"
        qdrant = Qdrant('5f50fd0a56v098ca10d75d2g', '5f50fd0a56v098ca10d75d2g',
                        LLMSettings(provider="openai").to_mongo().to_dict())
        request_body = {}
        with pytest.raises(ActionFailure):
            await qdrant.perform_operation({'embedding_search':  request_body}, user=user)

        with pytest.raises(ActionFailure):
            await qdrant.perform_operation({'payload_search':  request_body}, user=user)

    @pytest.mark.asyncio
    async def test_embedding_search_empty_request_body(self):
        Utility.load_environment()
        user = "test"
        qdrant = Qdrant('5f50fd0a56v098ca10d75d2g', '5f50fd0a56v098ca10d75d2g',
                        LLMSettings(provider="openai").to_mongo().to_dict())
        with pytest.raises(ActionFailure):
            await qdrant.perform_operation({'embedding_search': ''}, user=user)

    @pytest.mark.asyncio
    async def test_payload_search_empty_request_body(self):
        Utility.load_environment()
        qdrant = Qdrant('5f50fd0a56v098ca10d75d2g', '5f50fd0a56v098ca10d75d2g',
                        LLMSettings(provider="openai").to_mongo().to_dict())
        with pytest.raises(ActionFailure):
            await qdrant.perform_operation({'payload_search': {}}, user="test")

    @pytest.mark.asyncio
    async def test_perform_operation_invalid_op_type(self):
        Utility.load_environment()
        qdrant = Qdrant('5f50fd0a56v098ca10d75d2g', '5f50fd0a56v098ca10d75d2g',
                        LLMSettings(provider="openai").to_mongo().to_dict())
        request_body = {}
        with pytest.raises(ActionFailure, match="No Operation to perform"):
            await qdrant.perform_operation({"vector_search": request_body}, user="test")

    def test_get_instance_raises_exception_when_db_not_implemented(self):
        with pytest.raises(AppException, match="Database not yet implemented!"):
            DatabaseFactory.get_instance("mongo")

    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    @mock.patch.object(ActionUtility, "execute_http_request", autospec=True)
    async def test_embedding_search_valid_request_body_payload(self, mock_http_request, mock_get_embedding):
        text_embedding_3_small_embeddings = [np.random.random(1536).tolist()]
        colbertv2_0_embeddings = [[np.random.random(128).tolist()]]
        bm25_embeddings = [{
            "indices": [1850593538, 11711171],
            "values": [1.66, 1.66]
        }]

        embeddings = {
            "dense": text_embedding_3_small_embeddings,
            "rerank": colbertv2_0_embeddings,
            "sparse": bm25_embeddings,
        }

        mock_get_embedding.return_value = embeddings
        Utility.load_environment()
        qdrant = Qdrant('5f50fd0a56v098ca10d75d2g', '5f50fd0a56v098ca10d75d2g',
                        LLMSettings(provider="openai").to_mongo().to_dict())
        mock_http_request.return_value = 'expected_result'
        result = await qdrant.perform_operation({'embedding_search': 'Hi'}, user="test")
        assert result == 'expected_result'

        mock_http_request.assert_called_once()
        called_args = mock_http_request.call_args
        called_payload = called_args.kwargs['request_body']
        assert called_payload == {'query': embeddings,
                                  'with_payload': True,
                                  'limit': 10}
        assert called_args.kwargs[
                   'http_url'] == 'http://localhost:6333/collections/5f50fd0a56v098ca10d75d2g/points/query'
        assert called_args.kwargs['request_method'] == 'POST'

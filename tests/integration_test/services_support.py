import io
import asyncio
import os
import re
import shutil
import tarfile
import tempfile
import time
from datetime import datetime, timedelta, date
from io import BytesIO
from unittest import mock
from unittest.mock import patch, MagicMock, AsyncMock
from urllib.parse import urljoin
from zipfile import ZipFile
from zoneinfo import ZoneInfo

import pytest
import pytz
import responses
import ujson as json
import yaml
from botocore.exceptions import ClientError
from bson import ObjectId
from fastapi.testclient import TestClient
from jira import JIRAError
from mongoengine import connect
from mongoengine.queryset.base import BaseQuerySet
from pipedrive.exceptions import UnauthorizedError
from pydantic import SecretStr
from rasa.shared.utils.io import read_config_file
from slack_sdk.web.slack_response import SlackResponse

from kairon.shared.clock import utc_from_timestamp, utc_now
from kairon.events.definitions.upload_handler import UploadHandler
from kairon.shared.account.data_objects import UserActivityLog
from kairon.shared.account.data_objects import UserEmailConfirmation
from kairon.shared.actions.models import ActionParameterType, DbActionOperationType, DbQueryValueType, ActionType
from kairon.shared.admin.data_objects import LLMSecret, LLMMetadata
from kairon.shared.callback.data_objects import CallbackLog, CallbackRecordStatusType, CallbackConfig
from kairon.shared.channels.mail.data_objects import MailResponseLog, MailStatus
from kairon.shared.chat.broadcast.data_objects import AnalyticsPipelineLogs
from kairon.shared.chat.data_objects import Channels
from kairon.shared.content_importer.content_processor import ContentImporterLogProcessor
from kairon.shared.importer.data_objects import ValidationLogs
from kairon.shared.utils import Utility, MailUtility
from kairon.shared.llm.processor import LLMProcessor
import numpy as np

Utility.load_system_metadata()

from pathlib import Path
from kairon.api.app.main import app
from kairon.events.definitions.multilingual import MultilingualEvent
from kairon.exceptions import AppException
from kairon.idp.processor import IDPProcessor
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.actions.data_objects import ActionServerLogs, ScheduleAction, Actions, ParallelActionConfig, \
    PyscriptActionConfig, PromptAction, HttpActionConfig, AnalyticsPipelineConfig
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.auth import Authentication
from kairon.shared.cloud.utils import CloudUtility
from kairon.shared.cognition.data_objects import CognitionSchema, CognitionData, CollectionData, SchemaMetadata
from kairon.shared.constants import EventClass, ChannelTypes, KaironSystemSlots
from kairon.shared.data.audit.data_objects import AuditLogData
from kairon.shared.data.constant import (
    UTTERANCE_TYPE,
    EVENT_STATUS,
    TOKEN_TYPE,
    AuditlogActions,
    KAIRON_TWO_STAGE_FALLBACK,
    FeatureMappings,
    DEFAULT_NLU_FALLBACK_RESPONSE,
    DEFAULT_LLM, TASK_TYPE, STATUSES
)
from kairon.shared.data.data_objects import (
    Stories,
    Rules,
    Utterances,
    Intents,
    TrainingExamples,
    Responses,
    ChatClientConfig,
    BotSettings,
    LLMSettings,
    DemoRequestLogs, UserMediaData, POSIntegrations
)
from kairon.events.definitions.catalog_sync import CatalogSync
from kairon.meta.processor import MetaProcessor
from kairon.shared.catalog_sync.data_objects import CatalogProviderMapping, CatalogSyncLogs
from kairon.shared.cognition.processor import CognitionDataProcessor
from kairon.shared.data.model_processor import ModelProcessor
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.data.utils import DataUtility
from kairon.shared.metering.constants import MetricType
from kairon.shared.models import StoryEventType, UserMediaUploadStatus
from kairon.shared.models import User
from kairon.shared.multilingual.processor import MultilingualLogProcessor
from kairon.shared.multilingual.utils.translator import Translator
from kairon.shared.organization.processor import OrgProcessor
from kairon.shared.sso.clients.google import GoogleSSO
from urllib.parse import urlencode
from deepdiff import DeepDiff
from fastapi import HTTPException

os.environ["system_file"] = "./tests/testing_data/system.yaml"
client = TestClient(app)
access_token = None
refresh_token = None
token_type = None


def _bind_default_documents_to_current_connection():
    # disconnect() only clears classes still stored in mongoengine's registry.
    # stress_test.data_objects registers its own Account, Bot, and User under
    # those names, so the kairon classes keep a collection on the old mongomock
    # client while sequence ids restart on the new one.
    from mongoengine import Document
    from mongoengine.connection import DEFAULT_CONNECTION_NAME, _connections, _dbs, get_connection

    if DEFAULT_CONNECTION_NAME not in _connections:
        return
    client = get_connection(DEFAULT_CONNECTION_NAME)
    cached_db = _dbs.get(DEFAULT_CONNECTION_NAME)
    if cached_db is not None and getattr(cached_db, "client", None) is not client:
        _dbs.pop(DEFAULT_CONNECTION_NAME, None)

    pending = list(Document.__subclasses__())
    seen = set()
    while pending:
        doc_cls = pending.pop()
        if doc_cls in seen:
            continue
        seen.add(doc_cls)
        pending.extend(doc_cls.__subclasses__())
        meta = getattr(doc_cls, "_meta", None)
        if meta is None or meta.get("db_alias", DEFAULT_CONNECTION_NAME) != DEFAULT_CONNECTION_NAME:
            continue
        cached = doc_cls.__dict__.get("_collection")
        if cached is None:
            continue
        cached_client = getattr(getattr(cached, "database", None), "client", None)
        if cached_client is not None and cached_client is not client:
            doc_cls._collection = None


@pytest.fixture(autouse=True, scope="function")
def setup():
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    Utility.load_environment()
    connect(**Utility.mongoengine_connection(Utility.environment["database"]["url"]))
    _bind_default_documents_to_current_connection()
    AccountProcessor.load_system_properties()

    LLMSecret.objects.delete()
    LLMMetadata.objects.delete()

    LLMMetadata(
        provider="openai",
        schema="https://json-schema.org/draft/2020-12/schema",
        type="object",
        description="Open AI Models for Prompt",
        properties={
            "temperature": {
                "type": "number",
                "default": 0.0,
                "minimum": 0.0,
                "maximum": 2.0,
                "description": "The temperature hyperparameter controls the creativity or randomness of the generated responses."
            },
            "max_tokens": {
                "type": "integer",
                "default": 300,
                "minimum": 5,
                "maximum": 4096,
                "description": "The max_tokens hyperparameter limits the length of generated responses in chat completion using ChatGPT."
            },
            "model": {
                "type": "string",
                "default": "gpt-4.1-mini",
                "enum": [
                    "gpt-3.5-turbo",
                    "gpt-4.1-nano",
                    "gpt-4.1-mini",
                    "gpt-4.1"
                ],
                "description": "The model hyperparameter is the ID of the model to use."
            },
            "top_p": {
                "type": "number",
                "default": 0.0,
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "The top_p hyperparameter is a value that controls the diversity of the generated responses."
            },
            "n": {
                "type": "integer",
                "default": 1,
                "minimum": 1,
                "maximum": 5,
                "description": "The n hyperparameter controls the number of different response options that are generated by the model."
            },
            "stop": {
                "anyOf": [
                    {"type": "string"},
                    {
                        "type": "array",
                        "maxItems": 4,
                        "items": {"type": "string"}
                    },
                    {"type": "integer"},
                    {"type": "null"}
                ],
                "type": [
                    "string",
                    "array",
                    "integer",
                    "null"
                ],
                "default": None,
                "description": "The stop hyperparameter is used to specify a list of tokens that should be used to indicate the end of a generated response."
            },
            "presence_penalty": {
                "type": "number",
                "default": 0.0,
                "minimum": -2.0,
                "maximum": 2.0,
                "description": "The presence_penalty hyperparameter penalizes the model for generating words that are not present in the context or input prompt."
            },
            "frequency_penalty": {
                "type": "number",
                "default": 0.0,
                "minimum": -2.0,
                "maximum": 2.0,
                "description": "The frequency_penalty hyperparameter penalizes the model for generating words that have already been generated in the current response."
            },
            "logit_bias": {
                "type": "object",
                "default": {},
                "description": "The logit_bias hyperparameter helps prevent GPT-3 from generating unwanted tokens or encourage generation of desired tokens."
            }
        },
        user="user"
    ).save()

    LLMMetadata(
        provider="anthropic",
        schema="https://json-schema.org/draft/2020-12/schema",
        type="object",
        description="Anthropic AI Models for Prompt",
        properties={
            "max_tokens": {
                "type": "integer",
                "default": 1024,
                "minimum": 5,
                "maximum": 4096,
                "description": "The max_tokens hyperparameter limits the length of generated responses."
            },
            "model": {
                "type": "string",
                "default": "claude-3-7-sonnet-20250219",
                "enum": [
                    "claude-3-7-sonnet-20250219"
                ],
                "description": "The model hyperparameter is the ID of the Anthropic model."
            }
        },
        user="user"
    ).save()

    LLMSecret(
        llm_type="openai",
        api_key="value",
        models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
        user="user"
    ).save()

    LLMSecret(
        llm_type="anthropic",
        api_key="value",
        models=["claude-3-7-sonnet-20250219"],
        user="user"
    ).save()

    yield

    LLMSecret.objects.delete()
    LLMMetadata.objects.delete()


# Train posts only check that training started and a model archive is written.
# Uploaded yaml and the stored bot config stay as they are. The file rasa
# trains on is rewritten to this pipeline. The first call trains once.
# Later calls copy that archive.
_FAST_TRAIN_CONFIG = (
    "recipe: default.v1\n"
    "language: en\n"
    "pipeline:\n"
    "- name: KeywordIntentClassifier\n"
    "policies:\n"
    "- name: MemoizationPolicy\n"
    "- name: RulePolicy\n"
)
_FAST_MODEL_DIR = tempfile.mkdtemp(prefix="kairon_fast_model_")
_FAST_MODEL = {"path": None}


def _validate_keyword_map_once(self):
    # Rasa pops the same overlapping keyword once per longer example.
    import re

    re_flag = 0 if self.case_sensitive else re.IGNORECASE
    ambiguous = []
    for keyword1, intent1 in self.intent_keyword_map.items():
        for keyword2, intent2 in self.intent_keyword_map.items():
            if (
                re.search(r"\b" + keyword1 + r"\b", keyword2, flags=re_flag)
                and intent1 != intent2
            ):
                ambiguous.append(keyword1)
    for keyword in ambiguous:
        self.intent_keyword_map.pop(keyword, None)


def _fast_rasa_train(*args, **kwargs):
    output = kwargs.get("output")
    if _FAST_MODEL["path"] and os.path.isfile(_FAST_MODEL["path"]) and isinstance(output, str):
        from rasa.model_training import TrainingResult

        os.makedirs(output, exist_ok=True)
        dest = os.path.join(output, f"{utc_now().strftime('%Y%m%d-%H%M%S%f')}.tar.gz")
        shutil.copy(_FAST_MODEL["path"], dest)
        return TrainingResult(model=dest)

    from rasa.api import train as rasa_train
    from rasa.nlu.classifiers.keyword_intent_classifier import KeywordIntentClassifier

    original_validate = KeywordIntentClassifier._validate_keyword_map
    KeywordIntentClassifier._validate_keyword_map = _validate_keyword_map_once

    config_path = kwargs.get("config")
    if config_path is None and len(args) > 1:
        config_path = args[1]
    if isinstance(config_path, str) and os.path.isfile(config_path):
        with open(config_path, "w") as config_file:
            config_file.write(_FAST_TRAIN_CONFIG)
    core_args = dict(kwargs.get("core_additional_arguments") or {})
    core_args["augmentation_factor"] = 0
    kwargs["core_additional_arguments"] = core_args
    try:
        result = rasa_train(*args, **kwargs)
    finally:
        KeywordIntentClassifier._validate_keyword_map = original_validate
    if result.model and os.path.isfile(result.model):
        stable = os.path.join(_FAST_MODEL_DIR, os.path.basename(result.model))
        shutil.copy(result.model, stable)
        _FAST_MODEL["path"] = stable
    return result


@pytest.fixture(autouse=True)
def fast_rasa_training(monkeypatch):
    monkeypatch.setattr("kairon.train.train", _fast_rasa_train)


def pytest_configure():
    return {
        "token_type": None,
        "access_token": None,
        "refresh_token": None,
        "username": None,
        "bot": None,
        "content_id": None,
    }


async def mock_smtp(*args, **kwargs):
    return None


def mock_sync_noop(*args, **kwargs):
    return None


def complete_end_to_end_event_execution(bot, user, event_class, **kwargs):
    from kairon.events.definitions.data_importer import TrainingDataImporterEvent
    from kairon.events.definitions.model_training import ModelTrainingEvent
    from kairon.events.definitions.model_testing import ModelTestingEvent
    from kairon.events.definitions.history_delete import DeleteHistoryEvent
    from kairon.events.definitions.content_importer import DocContentImporterEvent


    if event_class == EventClass.data_importer:
        overwrite = kwargs.get('overwrite', True)
        TrainingDataImporterEvent(bot, user, import_data=True, overwrite=overwrite).execute()
    elif event_class == EventClass.catalog_integration:
        provider = kwargs.get('provider')
        sync_type = kwargs.get('sync_type')
        token = kwargs.get('token')
        sync_ref_id = kwargs.get('sync_ref_id')
        asyncio.run(CatalogSync(bot, user, provider, sync_type=sync_type, token=token).execute(sync_ref_id=sync_ref_id))
    elif event_class == EventClass.model_training:
        ModelTrainingEvent(bot, user).execute()
    elif event_class == EventClass.content_importer:
        table_name = kwargs.get('table_name')
        overwrite = kwargs.get('overwrite', False)
        DocContentImporterEvent(bot, user, table_name, overwrite=overwrite).execute()
    elif event_class==EventClass.upload_file_handler:
        upload_type=kwargs.get("upload_type")
        collection_name=kwargs.get("collection_name")
        overwrite=kwargs.get("overwrite", False)
        UploadHandler(bot=bot, user=user, upload_type=upload_type, collection_name=collection_name, overwrite=overwrite).execute()
    elif event_class == EventClass.model_testing:
        ModelTestingEvent(bot, user).execute()
    elif event_class == EventClass.delete_history:
        DeleteHistoryEvent(bot, user).execute()
    elif event_class == EventClass.multilingual:
        MultilingualEvent(
            bot,
            user,
            dest_lang=kwargs.get("kwargs"),
            translate_responses=kwargs.get("translate_responses"),
            translate_actions=kwargs.get("translate_actions"),
        ).execute()



# Shared by services_test.py and services_test_*.py.
# Pytest collects those files in filename order. They share this client,
# the mongomock setup, and the fast-train archive.

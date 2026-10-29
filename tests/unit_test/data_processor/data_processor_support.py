import asyncio
import glob
import os
import re
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import List
from unittest import mock

import ujson as json
import yaml
from bson import ObjectId

from kairon.shared.clock import utc_from_timestamp, utc_now
from kairon.meta.processor import MetaProcessor
from kairon.shared.catalog_sync.data_objects import CatalogProviderMapping
from kairon.shared.content_importer.data_objects import ContentValidationLogs
from kairon.shared.data.collection_processor import DataProcessor
from kairon.shared.utils import Utility
from kairon.shared.llm.processor import LLMProcessor

os.environ["system_file"] = "./tests/testing_data/system.yaml"
Utility.load_environment()
Utility.load_system_metadata()


from unittest.mock import patch, AsyncMock, MagicMock
import numpy as np
import pandas as pd
import pytest
import responses
from fastapi import UploadFile, HTTPException
from jira import JIRAError, JIRA
from mongoengine import connect, DoesNotExist
from mongoengine.errors import ValidationError
from mongoengine.queryset.base import BaseQuerySet
from pipedrive.exceptions import UnauthorizedError
from pydantic import SecretStr
from rasa.core.agent import Agent
from rasa.shared.constants import DEFAULT_DOMAIN_PATH, DEFAULT_DATA_PATH, DEFAULT_CONFIG_PATH, \
    DEFAULT_NLU_FALLBACK_INTENT_NAME
from rasa.shared.core.constants import RULE_SNIPPET_ACTION_NAME
from rasa.shared.core.events import UserUttered, ActionExecuted
from rasa.shared.core.training_data.structures import StoryGraph, RuleStep, Checkpoint
from rasa.shared.importers.rasa import Domain, RasaFileImporter
from rasa.shared.nlu.training_data.training_data import TrainingData
from rasa.shared.utils.io import read_config_file
from starlette.datastructures import Headers
from starlette.requests import Request

from kairon.api import models
from kairon.api.models import HttpActionParameters, HttpActionConfigRequest, ActionResponseEvaluation, \
    SetSlotsUsingActionResponse, PromptActionConfigRequest, DatabaseActionRequest, PyscriptActionRequest, \
    ScheduleActionRequest
from kairon.exceptions import AppException
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.actions.data_objects import HttpActionConfig, ActionServerLogs, Actions, SlotSetAction, \
    FormValidationAction, GoogleSearchAction, JiraAction, PipedriveLeadsAction, HubspotFormsAction, HttpActionResponse, \
    HttpActionRequestBody, EmailActionConfig, CustomActionRequestParameters, ZendeskAction, RazorpayAction, \
    DatabaseAction, SetSlotsFromResponse, PyscriptActionConfig, WebSearchAction, PromptAction, UserQuestion, DbQuery, \
    CallbackActionConfig, CustomActionDynamicParameters, ScheduleAction, LiveAgentActionConfig, \
    KaironTwoStageFallbackAction, ParallelActionConfig, TriggerInfo
from kairon.shared.callback.data_objects import CallbackConfig, encrypt_secret
from kairon.shared.actions.models import ActionType, DispatchType, DbActionOperationType, DbQueryValueType, \
    ActionParameterType
from kairon.shared.admin.data_objects import LLMSecret, LLMMetadata
from kairon.shared.auth import Authentication
from kairon.shared.chat.data_objects import Channels
from kairon.shared.cognition.data_objects import CognitionData, CognitionSchema, ColumnMetadata, CollectionData, SchemaMetadata
from kairon.shared.cognition.processor import CognitionDataProcessor
from kairon.shared.constants import SLOT_SET_TYPE, EventClass
from kairon.shared.data.audit.data_objects import AuditLogData
from kairon.shared.data.constant import ENDPOINT_TYPE, STATUSES
from kairon.shared.data.constant import UTTERANCE_TYPE, EVENT_STATUS, STORY_EVENT, ALLOWED_DOMAIN_FORMATS, \
    ALLOWED_CONFIG_FORMATS, ALLOWED_NLU_FORMATS, ALLOWED_STORIES_FORMATS, ALLOWED_RULES_FORMATS, REQUIREMENTS, \
    DEFAULT_NLU_FALLBACK_RULE, SLOT_TYPE, KAIRON_TWO_STAGE_FALLBACK, AuditlogActions, TOKEN_TYPE, GPT_LLM_FAQ, \
    DEFAULT_CONTEXT_PROMPT, DEFAULT_NLU_FALLBACK_RESPONSE, DEFAULT_SYSTEM_PROMPT, DEFAULT_LLM
from kairon.shared.data.data_objects import (TrainingExamples,
                                             Slots,
                                             Entities, EntitySynonyms, RegexFeatures,
                                             Intents,
                                             Responses,
                                             ModelTraining, StoryEvents, Stories, ResponseCustom, ResponseText,
                                             Rules, Configs,
                                             Utterances, BotSettings, ChatClientConfig, LookupTables, Forms,
                                             SlotMapping, KeyVault, MultiflowStories, LLMSettings,
                                             MultiflowStoryEvents, Synonyms,
                                             Lookup, POSIntegrations, PetpoojaSyncConfig
                                             )
from kairon.shared.data.history_log_processor import HistoryDeletionLogProcessor
from kairon.shared.data.model_processor import ModelProcessor
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.data.utils import DataUtility
from kairon.shared.importer.processor import DataImporterLogProcessor
from kairon.shared.live_agent.live_agent import LiveAgentHandler
from kairon.shared.metering.constants import MetricType
from kairon.shared.metering.data_object import Metering
from kairon.shared.models import StoryEventType, HttpContentType, CognitionDataType, VaultSyncType
from kairon.shared.multilingual.processor import MultilingualLogProcessor
from kairon.shared.test.data_objects import ModelTestingLogs
from kairon.shared.test.processor import ModelTestingLogProcessor
from kairon.train import train_model_for_bot, start_training

# These tests only check that a model archive is written. The stored bot config
# still has DIET and TED; rewriting the file rasa trains on keeps that config.
# The first call trains this pipeline once. Later calls copy that archive.
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


@pytest.fixture(autouse=True)
def fast_rasa_training(monkeypatch):
    def _reuse(output):
        from rasa.model_training import TrainingResult

        os.makedirs(output, exist_ok=True)
        dest = os.path.join(output, f"{utc_now().strftime('%Y%m%d-%H%M%S%f')}.tar.gz")
        shutil.copy(_FAST_MODEL["path"], dest)
        return TrainingResult(model=dest)

    def _train(*args, **kwargs):
        output = kwargs.get("output")
        if _FAST_MODEL["path"] and os.path.isfile(_FAST_MODEL["path"]) and isinstance(output, str):
            return _reuse(output)

        from rasa.api import train as rasa_train

        config_path = kwargs.get("config")
        if config_path is None and len(args) > 1:
            config_path = args[1]
        if isinstance(config_path, str) and os.path.isfile(config_path):
            with open(config_path, "w") as config_file:
                config_file.write(_FAST_TRAIN_CONFIG)
        core_args = dict(kwargs.get("core_additional_arguments") or {})
        core_args["augmentation_factor"] = 0
        kwargs["core_additional_arguments"] = core_args
        result = rasa_train(*args, **kwargs)
        if result.model and os.path.isfile(result.model):
            stable = os.path.join(_FAST_MODEL_DIR, os.path.basename(result.model))
            shutil.copy(result.model, stable)
            _FAST_MODEL["path"] = stable
        return result

    monkeypatch.setattr("kairon.train.train", _train)


from deepdiff import DeepDiff


# Shared by data_processor_test.py and data_processor_test_*.py.
# Pytest collects those files in filename order. They share this mongomock
# connection and the fast-train archive.

class MongoProcessorTestBase:
    @pytest.fixture(autouse=True, scope='class')
    def init_connection(self):
        connect(**Utility.mongoengine_connection())

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

        yield

        LLMMetadata.objects.delete()

    @pytest.fixture()
    def get_training_data(self):

        async def _read_and_get_data(path: str):
            domain_path = os.path.join(path, DEFAULT_DOMAIN_PATH)
            training_data_path = os.path.join(path, DEFAULT_DATA_PATH)
            config_path = os.path.join(path, DEFAULT_CONFIG_PATH)
            chat_client_config_path = os.path.join(path, "chat_client_config.yml")
            http_actions_path = os.path.join(path, 'actions.yml')
            multiflow_story_path = os.path.join(path, 'multiflow_stories.yml')
            bot_content_path = os.path.join(path, 'bot_content.yml')
            importer = RasaFileImporter.load_from_config(config_path=config_path,
                                                         domain_path=domain_path,
                                                         training_data_paths=training_data_path)
            domain = importer.get_domain()
            story_graph = importer.get_stories()
            config = importer.get_config()
            nlu = importer.get_nlu_data(config.get('language'))
            http_actions = Utility.read_yaml(http_actions_path)
            multiflow_stories = Utility.read_yaml(multiflow_story_path)
            bot_content = Utility.read_yaml(bot_content_path)
            chat_client_config = Utility.read_yaml(chat_client_config_path)
            return nlu, story_graph, domain, config, http_actions, multiflow_stories, bot_content, chat_client_config

        return _read_and_get_data
    
    @pytest.fixture()
    def mock_collection_data(self):
        CollectionData(
            bot="test_bot",
            user="test_user_1",
            collection_name="details",
            data={
                "name": "Mahesh",
                "mobile_number": "9876543000",
                "crop": "wheat",
                "status": "stage-1",
                "age": "22"
            }
        ).save()
        CollectionData(
            bot="test_bot",
            user="test_user_1",
            collection_name="details",
            data={
                "name": "Mayank",
                "mobile_number": "9876543000",
                "crop": "wheat",
                "status": "stage-1",
                "age": "22"
            }
        ).save()
        CollectionData(
            bot="test_bot",
            user="test_user_1",
            collection_name="details",
            data={
                "name": "Ganesh",
                "mobile_number": "9876543001",
                "crop": "Paddy",
                "status": "stage-2",
                "age": "23"
            }
        ).save()
        CollectionData(
            bot="test_bot", 
            user="test_user_1", 
            collection_name="crop_details",
            data={
                "name": "Mahesh",
                "mobile_number": "9876543000",
                "crop": "wheat",
                "status": "stage-1",
                "age": "26"
            }
        ).save()
        CollectionData(
            bot="test_bot",
            user="test_user_1",
            collection_name="crop_details",
            data={
                "name": "Mahesh",
                "mobile_number": "9876543000",
                "crop": "wheat",
                "status": "stage-1",
                "age": "26"
            }
        ).save()
        CollectionData(
            bot="test_bot",
            user="test_user_1",
            collection_name="crop_details",
            data={
                "name": "Ganesh",
                "mobile_number": "9876543001",
                "crop": "Paddy",
                "status": "stage-2",
                "age": "26"
            }
        ).save()
        CollectionData(
            bot="test_bot",
            user="test_user_1",
            collection_name="crop_details",
            data={
                "name": "Hitesh",
                "mobile_number": "9876543001",
                "crop": "Okra",
                "status": "stage-4",
                "age": "27"
            }
        ).save()
        CollectionData(
            bot="test_bot",
            user="test_user_1",
            collection_name="crop_details",
            data={
                "name": "Hitesh",
                "mobile_number": "9876543002",
                "crop": "wheat",
                "status": "stage-3",
                "age": "27"
            }
        ).save()
        CollectionData(
            bot="test_bot",
            user="test_user_1",
            collection_name="details",
            data={
                "name": "Aniket",
                "mobile_number": "9876543003",
                "crop": "Okra",
                "status": "stage-4",
                "age": "26"
            }
        ).save()

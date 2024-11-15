import asyncio
import glob
import os
import re
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import List

import ujson as json
import yaml

from kairon.shared.content_importer.data_objects import ContentValidationLogs
from kairon.shared.rest_client import AioRestClient
from kairon.shared.utils import Utility
from kairon.shared.llm.processor import LLMProcessor

os.environ["system_file"] = "./tests/testing_data/system.yaml"
Utility.load_environment()
Utility.load_system_metadata()


from unittest.mock import patch, ANY
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
from pydantic import SecretStr, constr
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
    KaironTwoStageFallbackAction
from kairon.shared.callback.data_objects import CallbackConfig, encrypt_secret
from kairon.shared.actions.models import ActionType, DispatchType, DbActionOperationType, DbQueryValueType, \
    ActionParameterType
from kairon.shared.admin.data_objects import LLMSecret
from kairon.shared.auth import Authentication
from kairon.shared.chat.data_objects import Channels
from kairon.shared.cognition.data_objects import CognitionData, CognitionSchema, ColumnMetadata
from kairon.shared.cognition.processor import CognitionDataProcessor
from kairon.shared.constants import SLOT_SET_TYPE, EventClass
from kairon.shared.data.audit.data_objects import AuditLogData
from kairon.shared.data.constant import ENDPOINT_TYPE
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
                                             Lookup
                                             )
from kairon.shared.data.history_log_processor import HistoryDeletionLogProcessor
from kairon.shared.data.model_processor import ModelProcessor
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.data.utils import DataUtility
from kairon.shared.importer.processor import DataImporterLogProcessor
from kairon.shared.live_agent.live_agent import LiveAgentHandler
from kairon.shared.metering.constants import MetricType
from kairon.shared.metering.data_object import Metering
from kairon.shared.models import StoryEventType, HttpContentType, CognitionDataType
from kairon.shared.multilingual.processor import MultilingualLogProcessor
from kairon.shared.test.data_objects import ModelTestingLogs
from kairon.shared.test.processor import ModelTestingLogProcessor
from kairon.train import train_model_for_bot, start_training
from deepdiff import DeepDiff
import litellm


class TestMongoProcessor:

    @pytest.fixture(autouse=True, scope='class')
    def init_connection(self):
        connect(**Utility.mongoengine_connection())

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

    # def test_add_schedule_action_a(self):
    #     bot = "test"
    #     user = "test"
    #     expected_data = {
    #         "name": "test_schedule_action",
    #         "schedule_time": {"value": "2024-08-06T09:00:00.000+0530", "parameter_type": "value"},
    #         "timezone": None,
    #         "schedule_action": "test_pyscript",
    #         "response_text": "action scheduled",
    #         "params_list": [],
    #         "dispatch_bot_response": True
    #     }
    #
    #     processor = MongoProcessor()
    #     processor.add_schedule_action(expected_data, bot, user)
    #
    #     actual_data = list(processor.list_schedule_action(bot))
    #     assert expected_data.get("name") == actual_data[0]["name"]

    def test_add_complex_story_with_slot(self):
        processor = MongoProcessor()
        story_name = "story with slot"
        bot = "test_slot"
        user = "test_user"
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "is_new_user", "type": "SLOT", "value": None},
            {"name": "utter_welcome_user", "type": "BOT"},
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        pytest.story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name=story_name, bot=bot).get()
        assert len(story.events) == 3

        steps.insert(2, {"name": "persona", "type": "SLOT", "value": "positive"})
        processor.update_complex_story(pytest.story_id, story_dict, bot, user)
        story = Stories.objects(block_name=story_name, bot=bot).get()
        assert story.to_mongo().to_dict()["events"] == [{'name': 'greet', 'type': 'user'},
                                                        {'name': 'is_new_user', 'type': 'slot'},
                                                        {'name': 'persona', 'type': 'slot', 'value': 'positive'},
                                                        {'name': 'utter_welcome_user', 'type': 'action'}]
        stories = list(processor.get_stories(bot))
        assert stories[0]["steps"] == [{'name': 'greet', 'type': 'INTENT'},
                                       {'name': 'is_new_user', 'type': 'SLOT', 'value': None},
                                       {'name': 'persona', 'type': 'SLOT', 'value': 'positive'},
                                       {'name': 'utter_welcome_user', 'type': 'BOT'}]

    def test_add_prompt_action_with_gpt_feature_disabled(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        request = {"system_prompt": DEFAULT_SYSTEM_PROMPT, "context_prompt": DEFAULT_CONTEXT_PROMPT,
                   "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
                   "num_bot_responses": 5}
        with pytest.raises(AppException, match="Faq feature is disabled for the bot! Please contact support."):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_invalid_slots(self):
        processor = MongoProcessor()
        bot = 'testing_bot'
        user = 'testing_user'
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'test_add_prompt_action_with_invalid_slots', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini',
                                       'top_p': 0.0,
                                       'n': 1, 'stop': None, 'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.',
                                    'instructions': 'Answer question based on the context below.', 'type': 'system',
                                    'source': 'static',
                                    'is_enabled': True},
                                   {'name': 'Similarity Prompt',
                                    "data": "Bot_collection",
                                    'hyperparameters': {'top_results': 10,
                                                        'similarity_threshold': 1.70},
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Identification Prompt',
                                    'data': 'info',
                                    'instructions': 'Answer according to the context', 'type': 'user', 'source': 'slot',
                                    'is_enabled': True}]}
        with pytest.raises(AppException, match="Slot with name info not found!"):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_invalid_http_action(self):
        processor = MongoProcessor()
        bot = 'testt_bot'
        user = 'testt_user'
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'test_add_prompt_action_with_invalid_http_action', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini',
                                       'top_p': 0.0,
                                       'n': 1, 'stop': None, 'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.',
                                    'instructions': 'Answer question based on the context below.', 'type': 'system',
                                    'source': 'static',
                                    'is_enabled': True},
                                   {'name': 'Similarity Prompt',
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True,
                                    "data": "Bot_collection",
                                    'hyperparameters': {'top_results': 10,
                                                        'similarity_threshold': 1.70}},
                                   {'name': 'Http action Prompt',
                                    'data': 'test_http_action',
                                    'instructions': 'Answer according to the context', 'type': 'user',
                                    'source': 'action',
                                    'is_enabled': True}]}
        with pytest.raises(AppException, match="Action with name test_http_action not found!"):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_invalid_similarity_threshold(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'test_prompt_action_similarity', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini',
                                       'top_p': 0.0,
                                       'n': 1, 'stop': None, 'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Similarity Prompt',
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True,
                                    "data": "Bot_collection",
                                    'hyperparameters': {'top_results': 10,
                                                        'similarity_threshold': 1.70},
                                    },
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}]}
        with pytest.raises(ValidationError, match="similarity_threshold should be within 0.3 and 1"):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_invalid_top_results(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request = {'name': 'test_prompt_action_invalid_top_results', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini',
                                       'top_p': 0.0,
                                       'n': 1, 'stop': None, 'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Similarity Prompt',
                                    "data": "Bot_collection",
                                    'hyperparameters': {'top_results': 40,
                                                        'similarity_threshold': 0.3},
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}]}
        with pytest.raises(ValidationError, match="top_results should not be greater than 30"):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_utter(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request = {'name': 'utter_test_add_prompt_action',
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        with pytest.raises(AppException, match='Action name cannot start with utter_'):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_empty_collection_for_bot_content_prompt(self):
        processor = MongoProcessor()
        bot = 'bot'
        user = 'user'
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'test_add_prompt_action_with_empty_collection_for_bot_content_prompt',
                   'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Similarity Prompt',
                                    'data': '',
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}]}
        processor.add_prompt_action(request, bot, user)
        prompt_action = processor.get_prompt_action(bot)
        prompt_action[0].pop("_id")
        assert not DeepDiff(prompt_action, [
            {'name': 'test_add_prompt_action_with_empty_collection_for_bot_content_prompt',
             'num_bot_responses': 5,
             'failure_message': "I'm sorry, I didn't quite understand that. Could you rephrase?",
             'user_question': {'type': 'from_user_message'},
             'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini', 'top_p': 0.0,
                                 'n': 1, 'stop': None, 'presence_penalty': 0.0,
                                 'frequency_penalty': 0.0, 'logit_bias': {}},
             'llm_type': 'openai',
             'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.',
                              'type': 'system', 'source': 'static', 'is_enabled': True},
                             {'name': 'Similarity Prompt', 'data': 'default',
                              'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                              'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                             {'name': 'Query Prompt', 'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                              'instructions': 'Answer according to the context', 'type': 'query', 'source': 'static',
                              'is_enabled': True},
                             {'name': 'Query Prompt', 'data': 'If there is no specific query, assume that user is aking about java programming.',
                              'instructions': 'Answer according to the context', 'type': 'query', 'source': 'static', 'is_enabled': True}],
             'instructions': [], 'set_slots': [], 'dispatch_response': True, 'status': True}], ignore_order=True)

    def test_add_prompt_action_with_bot_content_prompt(self):
        processor = MongoProcessor()
        bot = 'bot'
        user = 'user'
        request = {'name': 'test_add_prompt_action_with_bot_content_prompt',
                   'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Similarity Prompt',
                                    'data': 'Bot_collection',
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}]}
        processor.add_prompt_action(request, bot, user)
        prompt_action = processor.get_prompt_action(bot)
        prompt_action[1].pop("_id")
        assert not DeepDiff(prompt_action[1], {
            'name': 'test_add_prompt_action_with_bot_content_prompt',
            'num_bot_responses': 5,
            'failure_message': "I'm sorry, I didn't quite understand that. Could you rephrase?",
            'user_question': {'type': 'from_user_message'},
            'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini', 'top_p': 0.0,
                                'n': 1, 'stop': None, 'presence_penalty': 0.0,
                                'frequency_penalty': 0.0, 'logit_bias': {}},
            'llm_type': 'openai',
            'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.',
                             'type': 'system', 'source': 'static', 'is_enabled': True},
                            {'name': 'Similarity Prompt', 'data': 'Bot_collection',
                             'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                             'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                            {'name': 'Query Prompt', 'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                             'instructions': 'Answer according to the context', 'type': 'query', 'source': 'static',
                             'is_enabled': True},
                            {'name': 'Query Prompt', 'data': 'If there is no specific query, assume that user is aking about java programming.',
                             'instructions': 'Answer according to the context', 'type': 'query', 'source': 'static', 'is_enabled': True}],
            'instructions': [], 'set_slots': [], 'dispatch_response': True, 'status': True}, ignore_order=True)

    def test_add_prompt_action_with_invalid_query_prompt(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request = {'name': 'test_add_prompt_action_with_invalid_query_prompt',
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Similarity Prompt', "data": "Bot_collection",
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'history', 'is_enabled': True}],
                   "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
                   "num_bot_responses": 5}
        with pytest.raises(ValidationError, match="Query prompt must have static source!"):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_invalid_num_bot_responses(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request = {'name': 'test_add_prompt_action_with_invalid_num_bot_responses',
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Similarity Prompt', "data": "Bot_collection",
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}],
                   "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
                   "num_bot_responses": 15}
        with pytest.raises(ValidationError, match="num_bot_responses should not be greater than 5"):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_invalid_system_prompt_source(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request = {'name': 'test_add_prompt_action_with_invalid_system_prompt_source',
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'history',
                                    'is_enabled': True},
                                   {'name': 'Similarity Prompt', "data": "Bot_collection",
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}],
                   "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE, "num_bot_responses": 5}
        with pytest.raises(ValidationError, match="System prompt must have static source!"):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_multiple_system_prompt(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request = {'name': 'test_add_prompt_action_with_multiple_system_prompt',
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'System Prompt', 'data': 'You are a personal assistant.',
                                    'instructions': 'Answer question based on the context below.', 'type': 'system',
                                    'source': 'static',
                                    'is_enabled': True},
                                   {'name': 'Similarity Prompt', "data": "Bot_collection",
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}],
                   "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE, "num_bot_responses": 5}
        with pytest.raises(ValidationError, match="Only one system prompt can be present!"):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_empty_llm_prompt_name(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request = {'name': 'test_add_prompt_action_with_empty_llm_prompt_name',
                   'llm_prompts': [{'name': '', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Similarity Prompt', "data": "Bot_collection",
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}],
                   "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE, "num_bot_responses": 5}
        with pytest.raises(ValidationError, match="Name cannot be empty!"):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_empty_data_for_static_prompt(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request = {'name': 'test_add_prompt_action_with_empty_data_for_static_prompt',
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Similarity Prompt', "data": "Bot_collection",
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': '', 'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}],
                   "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE, "num_bot_responses": 5}
        with pytest.raises(ValidationError, match="data is required for static prompts!"):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_multiple_history_source_prompts(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request = {'name': 'test_add_prompt_action_with_multiple_history_source_prompts',
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True},
                                   {'name': 'Analytical Prompt', 'type': 'user', 'source': 'history',
                                    'is_enabled': True},
                                   {'name': 'Similarity Prompt', "data": "Bot_collection",
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}],
                   "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE, "num_bot_responses": 5}
        with pytest.raises(ValidationError, match="Only one history source can be present!"):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_no_system_prompts(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request = {'name': 'test_add_prompt_action_with_no_system_prompts',
                   'llm_prompts': [
                       {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True},
                       {'name': 'Similarity Prompt', "data": "Bot_collection",
                        'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                        'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                       {'name': 'Another Similarity Prompt', "data": "Bot_collection_two",
                        'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                        'type': 'user', 'source': 'bot_content', 'is_enabled': True}
                   ],
                   "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE, "num_bot_responses": 5}
        with pytest.raises(ValidationError, match="System prompt is required!"):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_empty_llm_prompts(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request = {'name': 'test_add_prompt_action_with_empty_llm_prompts', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini',
                                       'top_p': 0.0,
                                       'n': 1, 'stop': None, 'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': []}
        with pytest.raises(ValidationError, match="llm_prompts are required!"):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_faq_action_with_default_values_and_instructions(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request = {'name': 'test_add_prompt_action_faq_action_with_default_values',
                   'user_question': {'type': 'from_slot', 'value': 'prompt_question'},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}],
                   'instructions': ['Answer in a short manner.', 'Keep it simple.'],
                   "set_slots": [{"name": "gpt_result", "value": "${data}", "evaluation_type": "expression"},
                                 {"name": "gpt_result_type", "value": "${data.type}", "evaluation_type": "script"}],
                   "dispatch_response": False
                   }
        pytest.action_id = processor.add_prompt_action(request, bot, user)
        action = list(processor.get_prompt_action(bot))
        action[0].pop("_id")
        assert not DeepDiff(action, [{'name': 'test_add_prompt_action_faq_action_with_default_values', 'num_bot_responses': 5,
                           'failure_message': "I'm sorry, I didn't quite understand that. Could you rephrase?",
                           'user_question': {'type': 'from_slot', 'value': 'prompt_question'},
                           'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini',
                                               'top_p': 0.0, 'n': 1, 'stop': None,
                                               'presence_penalty': 0.0, 'frequency_penalty': 0.0, 'logit_bias': {}},
                           'llm_type': 'openai',
                           'llm_prompts': [
                               {'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                'source': 'static', 'is_enabled': True},
                               {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}],
                           'instructions': ['Answer in a short manner.', 'Keep it simple.'],
                           'set_slots': [{'name': 'gpt_result', 'value': '${data}', 'evaluation_type': 'expression'},
                                         {'name': 'gpt_result_type', 'value': '${data.type}',
                                          'evaluation_type': 'script'}], 'dispatch_response': False, 'status': True}], ignore_order=True)

    def test_add_prompt_action_with_invalid_temperature_hyperparameter(self):
        processor = MongoProcessor()
        bot = 'test_bot_one'
        user = 'test_user_one'
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'test_add_prompt_action_with_invalid_temperature_hyperparameter', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 3.0, 'max_tokens': 300, 'model': 'gpt-4o-mini',
                                       'top_p': 0.0,
                                       'n': 1, 'stop': None, 'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        with pytest.raises(ValidationError, match=re.escape("['temperature']: 3.0 is greater than the maximum of 2.0")):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_invalid_stop_hyperparameter(self):
        processor = MongoProcessor()
        bot = 'test_bot_two'
        user = 'test_user_two'
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'test_add_prompt_action_with_invalid_stop_hyperparameter', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini',
                                       'top_p': 0.0,
                                       'n': 1, 'stop': ["\n", ".", "?", "!", ";"],
                                       'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        with pytest.raises(ValidationError,
                           match=re.escape('[\'stop\']: ["\\n",".","?","!",";"] is not valid under any of the schemas listed in the \'anyOf\' keyword')):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_invalid_presence_penalty_hyperparameter(self):
        processor = MongoProcessor()
        bot = 'test_bot_three'
        user = 'test_user_three'
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'test_add_prompt_action_with_invalid_presence_penalty_hyperparameter',
                   'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini',
                                       'top_p': 0.0,
                                       'n': 1, 'stop': '?', 'presence_penalty': -3.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        with pytest.raises(ValidationError, match=re.escape("['presence_penalty']: -3.0 is less than the minimum of -2.0")):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_invalid_frequency_penalty_hyperparameter(self):
        processor = MongoProcessor()
        bot = 'test_bot_four'
        user = 'test_user_four'
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'test_add_prompt_action_with_invalid_frequency_penalty_hyperparameter',
                   'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini',
                                       'top_p': 0.0,
                                       'n': 1, 'stop': '?', 'presence_penalty': 0.0,
                                       'frequency_penalty': 3.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        with pytest.raises(ValidationError, match=re.escape("['frequency_penalty']: 3.0 is greater than the maximum of 2.0")):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_invalid_max_tokens_hyperparameter(self):
        processor = MongoProcessor()
        bot = 'test_bot_five'
        user = 'test_user_five'
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'test_add_prompt_action_with_invalid_max_tokens_hyperparameter', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 2, 'model': 'gpt-4o-mini',
                                       'top_p': 0.0,
                                       'n': 1, 'stop': '?', 'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        with pytest.raises(ValidationError, match=re.escape("['max_tokens']: 2 is less than the minimum of 5")):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_zero_max_tokens_hyperparameter(self):
        processor = MongoProcessor()
        bot = 'test_bot_six'
        user = 'test_user_six'
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'test_add_prompt_action_with_zero_max_tokens_hyperparameter', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 0, 'model': 'gpt-4o-mini',
                                       'top_p': 0.0,
                                       'n': 1, 'stop': '?', 'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        with pytest.raises(ValidationError, match=re.escape("['max_tokens']: 0 is less than the minimum of 5")):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_invalid_top_p_hyperparameter(self):
        processor = MongoProcessor()
        bot = 'test_bot_seven'
        user = 'test_user_seven'
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'test_add_prompt_action_with_invalid_top_p_hyperparameter', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 256, 'model': 'gpt-4o-mini',
                                       'top_p': 3.0,
                                       'n': 1, 'stop': '?', 'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        with pytest.raises(ValidationError, match=re.escape("['top_p']: 3.0 is greater than the maximum of 1.0")):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_invalid_n_hyperparameter(self):
        processor = MongoProcessor()
        bot = 'test_bot_eight'
        user = 'test_user_eight'
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'test_add_prompt_action_with_invalid_n_hyperparameter', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 200, 'model': 'gpt-4o-mini',
                                       'top_p': 0.0,
                                       'n': 7, 'stop': '?', 'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        with pytest.raises(ValidationError, match=re.escape("['n']: 7 is greater than the maximum of 5")):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_zero_n_hyperparameter(self):
        processor = MongoProcessor()
        bot = 'test_bot_nine'
        user = 'test_user_nine'
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'test_add_prompt_action_with_zero_n_hyperparameter', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 200, 'model': 'gpt-4o-mini',
                                       'top_p': 0.0,
                                       'n': 0, 'stop': '?', 'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        with pytest.raises(ValidationError, match=re.escape("['n']: 0 is less than the minimum of 1")):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_invalid_logit_bias_hyperparameter(self):
        processor = MongoProcessor()
        bot = 'test_bot_ten'
        user = 'test_user_ten'
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'test_add_prompt_action_with_invalid_logit_bias_hyperparameter', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 200, 'model': 'gpt-4o-mini',
                                       'top_p': 0.0,
                                       'n': 2, 'stop': '?', 'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': 'a'},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        with pytest.raises(ValidationError, match=re.escape('[\'logit_bias\']: "a" is not of type "object"')):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_faq_action_already_exist(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request = {'name': 'test_add_prompt_action_faq_action_with_default_values',
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        with pytest.raises(AppException, match='Action exists!'):
            processor.add_prompt_action(request, bot, user)

    def test_edit_prompt_action_does_not_exist(self):
        processor = MongoProcessor()
        bot = 'invalid_bot'
        user = 'test_user'
        action_id = '646344d6f7fa1a62db69cceb'
        request = {'name': 'test_edit_prompt_action_does_not_exist',
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Similarity Prompt', "data": "Bot_collection",
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}],
                   "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
                   "num_bot_responses": 5}
        with pytest.raises(AppException, match="Action not found"):
            processor.edit_prompt_action(action_id, request, bot, user)

    def test_edit_prompt_action_faq_action(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request = {'name': 'test_edit_prompt_action_faq_action',
                   'user_question': {'type': 'from_user_message'},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Similarity Prompt', 'data': 'Bot_collection',
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}],
                   "failure_message": "updated_failure_message",
                   "use_query_prompt": True, "use_bot_responses": True, "query_prompt": "updated_query_prompt",
                   "num_bot_responses": 5, "hyperparameters": Utility.get_llm_hyperparameters('openai'),
                   "set_slots": [{"name": "gpt_result", "value": "${data}", "evaluation_type": "expression"},
                                 {"name": "gpt_result_type", "value": "${data.type}", "evaluation_type": "script"}],
                   "dispatch_response": False
                   }
        processor.edit_prompt_action(pytest.action_id, request, bot, user)
        action = list(processor.get_prompt_action(bot))
        action[0].pop("_id")
        assert not DeepDiff(action, [{'name': 'test_edit_prompt_action_faq_action', 'num_bot_responses': 5,
                           'failure_message': 'updated_failure_message', 'user_question': {'type': 'from_user_message'},
                           'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini',
                                               'top_p': 0.0, 'n': 1, 'stop': None,
                                               'presence_penalty': 0.0, 'frequency_penalty': 0.0, 'logit_bias': {}},
                           'llm_type': 'openai',
                           'llm_prompts': [
                               {'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                'source': 'static', 'is_enabled': True},
                               {'name': 'Similarity Prompt', 'data': 'Bot_collection',
                                'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                'type': 'user', 'source': 'bot_content', 'is_enabled': True}, {'name': 'Query Prompt',
                                                                                               'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                                                                               'instructions': 'Answer according to the context',
                                                                                               'type': 'query',
                                                                                               'source': 'static',
                                                                                               'is_enabled': True},
                               {'name': 'Query Prompt',
                                'data': 'If there is no specific query, assume that user is aking about java programming.',
                                'instructions': 'Answer according to the context', 'type': 'query', 'source': 'static',
                                'is_enabled': True}], 'instructions': [],
                           'set_slots': [{'name': 'gpt_result', 'value': '${data}', 'evaluation_type': 'expression'},
                                         {'name': 'gpt_result_type', 'value': '${data.type}',
                                          'evaluation_type': 'script'}], 'dispatch_response': False, 'status': True}],
                            ignore_order=True)
        request = {'name': 'test_edit_prompt_action_faq_action_again',
                   'user_question': {'type': 'from_slot', 'value': 'prompt_question'},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static'}],
                   'instructions': ['Answer in a short manner.', 'Keep it simple.']}
        processor.edit_prompt_action(pytest.action_id, request, bot, user)
        action = list(processor.get_prompt_action(bot))
        action[0].pop("_id")
        assert not DeepDiff(action, [{'name': 'test_edit_prompt_action_faq_action_again', 'num_bot_responses': 5,
                           'failure_message': "I'm sorry, I didn't quite understand that. Could you rephrase?",
                           'user_question': {'type': 'from_slot', 'value': 'prompt_question'},
                           'llm_type': 'openai',
                           'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini',
                                               'top_p': 0.0, 'n': 1, 'stop': None,
                                               'presence_penalty': 0.0, 'frequency_penalty': 0.0, 'logit_bias': {}},
                           'llm_prompts': [
                               {'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                'source': 'static', 'is_enabled': True}],
                           'instructions': ['Answer in a short manner.', 'Keep it simple.'], 'set_slots': [],
                           'dispatch_response': True, 'status': True}], ignore_order=True)

    def test_edit_prompt_action_faq_action_llm_type_and_hyperparameters(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request = {'name': 'test_edit_prompt_action_faq_action',
                   'user_question': {'type': 'from_user_message'},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Similarity Prompt', 'data': 'Bot_collection',
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}],
                   "failure_message": "updated_failure_message",
                   "llm_type": "anthropic",
                   "hyperparameters": Utility.get_llm_hyperparameters('anthropic'),
                   "use_query_prompt": True, "use_bot_responses": True, "query_prompt": "updated_query_prompt",
                   "num_bot_responses": 5,
                   "set_slots": [{"name": "gpt_result", "value": "${data}", "evaluation_type": "expression"},
                                 {"name": "gpt_result_type", "value": "${data.type}", "evaluation_type": "script"}],
                   "dispatch_response": False
                   }
        processor.edit_prompt_action(pytest.action_id, request, bot, user)
        action = list(processor.get_prompt_action(bot))
        action[0].pop("_id")
        print(action)
        assert not DeepDiff(action, [{'name': 'test_edit_prompt_action_faq_action', 'num_bot_responses': 5,
                                      'failure_message': 'updated_failure_message',
                                      'user_question': {'type': 'from_user_message'},
                                      'hyperparameters': {'max_tokens': 1024, 'model': 'claude-3-haiku-20240307'},
                                      'llm_type': 'anthropic',
                                      'llm_prompts': [
                                          {'name': 'System Prompt', 'data': 'You are a personal assistant.',
                                           'type': 'system',
                                           'source': 'static', 'is_enabled': True},
                                          {'name': 'Similarity Prompt', 'data': 'Bot_collection',
                                           'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                           'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                          {'name': 'Query Prompt',
                                           'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                           'instructions': 'Answer according to the context',
                                           'type': 'query',
                                           'source': 'static',
                                           'is_enabled': True},
                                          {'name': 'Query Prompt',
                                           'data': 'If there is no specific query, assume that user is aking about java programming.',
                                           'instructions': 'Answer according to the context', 'type': 'query',
                                           'source': 'static',
                                           'is_enabled': True}], 'instructions': [],
                                      'set_slots': [
                                          {'name': 'gpt_result', 'value': '${data}', 'evaluation_type': 'expression'},
                                          {'name': 'gpt_result_type', 'value': '${data.type}',
                                           'evaluation_type': 'script'}], 'dispatch_response': False, 'status': True}],
                            ignore_order=True)

    def test_edit_prompt_action_with_less_hyperparameters(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request = {'name': 'test_edit_prompt_action_with_less_hyperparameters',
                   'user_question': {'type': 'from_slot', 'value': 'prompt_question'},
                   'llm_prompts': [
                       {'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                        'source': 'static', 'is_enabled': True},
                       {'name': 'Similarity Prompt', 'data': 'Bot_collection',
                        'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                        'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                       {'name': 'Query Prompt',
                        'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                        'instructions': 'Answer according to the context', 'type': 'query', 'source': 'static',
                        'is_enabled': True},
                       {'name': 'Query Prompt',
                        'data': 'If there is no specific query, assume that user is aking about java programming.',
                        'instructions': 'Answer according to the context', 'type': 'query',
                        'source': 'static', 'is_enabled': True}],
                   "failure_message": "updated_failure_message", "top_results": 10, "similarity_threshold": 0.70,
                   "use_query_prompt": True, "use_bot_responses": True, "query_prompt": "updated_query_prompt",
                   "num_bot_responses": 5, "hyperparameters": {"temperature": 0.0,
                                                               "max_tokens": 300,
                                                               "model": "gpt-4o-mini",
                                                               "top_p": 0.0,
                                                               "n": 1}}

        processor.edit_prompt_action(pytest.action_id, request, bot, user)
        action = list(processor.get_prompt_action(bot))
        action[0].pop("_id")
        assert not DeepDiff(action, [{'name': 'test_edit_prompt_action_with_less_hyperparameters', 'num_bot_responses': 5,
                           'failure_message': 'updated_failure_message',
                           'user_question': {'type': 'from_slot', 'value': 'prompt_question'},
                           'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini',
                                               'top_p': 0.0, 'n': 1, 'stop': None,
                                               'presence_penalty': 0.0, 'frequency_penalty': 0.0, 'logit_bias': {}},
                           'llm_type': 'openai',
                           'llm_prompts': [
                               {'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                'source': 'static', 'is_enabled': True},
                               {'name': 'Similarity Prompt', 'data': 'Bot_collection',
                                'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                'type': 'user', 'source': 'bot_content', 'is_enabled': True}, {'name': 'Query Prompt',
                                                                                               'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                                                                               'instructions': 'Answer according to the context',
                                                                                               'type': 'query',
                                                                                               'source': 'static',
                                                                                               'is_enabled': True},
                               {'name': 'Query Prompt',
                                'data': 'If there is no specific query, assume that user is aking about java programming.',
                                'instructions': 'Answer according to the context', 'type': 'query', 'source': 'static',
                                'is_enabled': True}], 'instructions': [], 'set_slots': [], 'dispatch_response': True,
                           'status': True}], ignore_order=True)

    def test_get_prompt_action_does_not_exist(self):
        processor = MongoProcessor()
        bot = 'invalid_bot'
        action = list(processor.get_prompt_action(bot))
        assert action == []

    def test_get_prompt_faq_action(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        action = list(processor.get_prompt_action(bot))
        action[0].pop("_id")
        assert not DeepDiff(action, [{'name': 'test_edit_prompt_action_with_less_hyperparameters', 'num_bot_responses': 5,
                           'failure_message': 'updated_failure_message',
                           'user_question': {'type': 'from_slot', 'value': 'prompt_question'},
                           'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini',
                                               'top_p': 0.0, 'n': 1, 'stop': None,
                                               'presence_penalty': 0.0, 'frequency_penalty': 0.0, 'logit_bias': {}},
                           'llm_type': 'openai',
                           'llm_prompts': [
                               {'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                'source': 'static', 'is_enabled': True},
                               {'name': 'Similarity Prompt', 'data': 'Bot_collection',
                                'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                'type': 'user', 'source': 'bot_content', 'is_enabled': True}, {'name': 'Query Prompt',
                                                                                               'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                                                                               'instructions': 'Answer according to the context',
                                                                                               'type': 'query',
                                                                                               'source': 'static',
                                                                                               'is_enabled': True},
                               {'name': 'Query Prompt',
                                'data': 'If there is no specific query, assume that user is aking about java programming.',
                                'instructions': 'Answer according to the context', 'type': 'query', 'source': 'static',
                                'is_enabled': True}], 'instructions': [], 'set_slots': [], 'dispatch_response': True,
                           'status': True}], ignore_order=True)
    def test_delete_prompt_action(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        processor.delete_action("test_add_prompt_action_faq_action_with_default_values", bot, user)

    def test_delete_prompt_action_already_deleted(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        with pytest.raises(AppException,
                           match=f'Action with name "test_add_prompt_action_faq_action_with_default_values" not found'):
            processor.delete_action('test_add_prompt_action_faq_action_with_default_values', bot, user)

    def test_delete_prompt_action_not_present(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        with pytest.raises(AppException, match=f'Action with name "non_existent_kairon_faq_action" not found'):
            processor.delete_action('non_existent_kairon_faq_action', bot, user)

    def test_get_live_agent(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        live_agent = processor.get_live_agent(bot=bot)
        assert live_agent == []

    def test_enable_live_agent(self):
        processor = MongoProcessor()
        bot_settings = BotSettings.objects(bot='test_bot').get()
        bot_settings.live_agent_enabled = True
        bot_settings.save()
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request_data = {
            "bot_response": "connecting to live agent",
            "dispatch_bot_response": False,
        }
        result = processor.enable_live_agent(request_data=request_data, bot=bot, user=user)
        assert result is True

    def test_get_live_agent_after_enabled(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        live_agent = processor.get_live_agent(bot=bot)
        print(live_agent)
        assert live_agent == {'name': 'live_agent_action', 'bot_response': 'connecting to live agent', 'agent_connect_response': 'Connected to live agent', 'agent_disconnect_response': 'Disconnected from live agent', 'agent_not_available_response': 'No agents available', 'dispatch_bot_response': False, 'dispatch_agent_connect_response': True, 'dispatch_agent_disconnect_response': True, 'dispatch_agent_not_available_response': True}


    def test_enable_live_agent_already_exist(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request_data = {
            "bot_response": "connecting to live agent",
            "dispatch_bot_response": False,
        }
        result = processor.enable_live_agent(request_data=request_data, bot=bot, user=user)
        assert result is False

    def test_edit_live_agent(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request_data = {
            "bot_response": "connecting to different live agent...",
            "dispatch_bot_response": True,
        }
        result = processor.edit_live_agent(request_data=request_data, bot=bot, user=user)

        live_agent = processor.get_live_agent(bot=bot)
        print(live_agent)
        assert live_agent == {'name': 'live_agent_action', 'bot_response': 'connecting to different live agent...', 'agent_connect_response': 'Connected to live agent', 'agent_disconnect_response': 'Disconnected from live agent', 'agent_not_available_response': 'No agents available', 'dispatch_bot_response': True, 'dispatch_agent_connect_response': True, 'dispatch_agent_disconnect_response': True, 'dispatch_agent_not_available_response': True}

    def test_list_live_agent_actions(self):
        processor = MongoProcessor()
        res = processor.load_live_agent_action(bot='test_bot')
        assert res == {'live_agent_action': [
                            {'name': 'live_agent_action',
                             'bot_response': 'connecting to different live agent...',
                             'agent_connect_response': 'Connected to live agent',
                             'agent_disconnect_response': 'Disconnected from live agent',
                             'agent_not_available_response': 'No agents available',
                             'dispatch_bot_response': True,
                             'dispatch_agent_connect_response': True,
                             'dispatch_agent_disconnect_response': True,
                             'dispatch_agent_not_available_response': True}
                        ]}
        gen = processor.list_live_agent_actions('test_bot', True)
        list_data = list(gen)
        assert list_data[0]['name'] == 'live_agent_action'
        assert list_data[0]['bot_response'] == 'connecting to different live agent...'
        assert list_data[0].get('_id')
        assert len(list_data[0]['_id']) == 24

    def test_enable_live_agent_service_not_available(self):
        bot = "test_bot"
        user = "test_user"
        request_data = {"key": "value"}
        processor = MongoProcessor() 
        with patch.object(processor, 'is_live_agent_enabled', return_value=False):
            with pytest.raises(AppException, match="Live agent service is not available for the bot"):
                processor.enable_live_agent(request_data, bot, user)

    def test_disable_live_agent(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request_data = {
            "bot_response": "connecting to different live agent...",
            "dispatch_bot_response": True,
        }
        result = processor.disable_live_agent(bot=bot, user=user)

        live_agent = processor.get_live_agent(bot=bot)
        assert live_agent == []

    def test_edit_live_agent_does_not_exist(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request_data = {
            "bot_response": "connecting to different live agent...",
            "dispatch_bot_response": True,
        }
        with pytest.raises(AppException, match=f'Live agent not enabled for the bot'):
            result = processor.edit_live_agent(request_data=request_data, bot=bot, user=user)


    def test_get_callback_service_log_with_conditions(self):
        bot = "test_bot"
        service = MongoProcessor()

        with patch('kairon.shared.callback.data_objects.CallbackLog.get_logs', return_value=(["log1", "log2"], 2)) as mock_get_logs:
            name = "test_callback"
            sender_id = "test_sender"
            channel = "test_channel"
            identifier = "test_identifier"
            start = 0
            limit = 100

            logs, total_count = service.get_callback_service_log(
                bot=bot,
                name=name,
                sender_id=sender_id,
                channel=channel,
                identifier=identifier,
                start=start,
                limit=limit
            )

            expected_query = {
                "bot": bot,
                "callback_name": name,
                "sender_id": sender_id,
                "channel": channel,
                "identifier": identifier
            }
            mock_get_logs.assert_called_once_with(expected_query, start, limit)
            assert logs == ["log1", "log2"]
            assert total_count == 2

    def test_get_callback_service_log_without_conditions(self):
        bot = "test_bot"
        service = MongoProcessor()

        with patch('kairon.shared.callback.data_objects.CallbackLog.get_logs', return_value=(["log1", "log2"], 2)) as mock_get_logs:

            logs, total_count = service.get_callback_service_log(bot=bot)

            expected_query = {"bot": bot}
            mock_get_logs.assert_called_once_with(expected_query, 0, 100)
            assert logs == ["log1", "log2"]
            assert total_count == 2

    def test_auditlog_event_config_does_not_exist(self):
        result = MongoProcessor.get_auditlog_event_config("nobot")
        assert result == {}

    def test_auditlog_event_config_does_not_exist_none(self):
        result = MongoProcessor.get_auditlog_event_config(None)
        assert result == {}

    @pytest.mark.asyncio
    async def test_load_from_path(self):
        processor = MongoProcessor()
        result = await (
            processor.save_from_path(
                "./tests/testing_data/initial", bot="tests", user="testUser"
            )
        )
        assert result is None

    def test_edit_bot_settings_does_not_exist(self):
        processor = MongoProcessor()
        bot_settings = {
            "analytics": {'fallback_intent': 'nlu_fallback'},
        }
        with pytest.raises(AppException, match='Bot Settings for the bot not found'):
            processor.edit_bot_settings(bot_settings, 'new_test_bot', 'test')

    def test_edit_bot_settings(self):
        processor = MongoProcessor()
        BotSettings(bot='new_test_bot', user='test').save()
        bot_settings = {
            "analytics": {'fallback_intent': 'utter_please_rephrase'},
        }
        processor.edit_bot_settings(bot_settings, 'new_test_bot', 'test')
        updated_settings = processor.get_bot_settings('new_test_bot', 'test')
        assert not updated_settings.ignore_utterances
        assert not updated_settings.force_import
        assert updated_settings.status
        assert updated_settings.timestamp
        assert updated_settings.user
        assert updated_settings.bot
        assert updated_settings.analytics.to_mongo().to_dict() == {'fallback_intent': 'utter_please_rephrase'}
        assert updated_settings.llm_settings.to_mongo().to_dict() == {'enable_faq': False, 'provider': 'openai'}

    def test_abort_current_event_with_no_model_training_event(self):
        mongo_processor = MongoProcessor()
        bot = "test_bot"
        user = "test_user"
        with pytest.raises(AppException, match="No Enqueued model_training present for this bot."):
            mongo_processor.abort_current_event(bot=bot, user=user, event_type=EventClass.model_training)

    def test_abort_current_event_with_no_model_testing_event(self):
        mongo_processor = MongoProcessor()
        bot = "test_bot"
        user = "test_user"
        with pytest.raises(AppException, match="No Enqueued model_testing present for this bot."):
            mongo_processor.abort_current_event(bot=bot, user=user, event_type=EventClass.model_testing)

    def test_abort_current_event_with_no_delete_history_event(self):
        mongo_processor = MongoProcessor()
        bot = "test_bot"
        user = "test_user"
        with pytest.raises(AppException, match="No Enqueued delete_history present for this bot."):
            mongo_processor.abort_current_event(bot=bot, user=user, event_type=EventClass.delete_history)

    def test_abort_current_event_with_no_data_importer_event(self):
        mongo_processor = MongoProcessor()
        bot = "test_bot"
        user = "test_user"
        with pytest.raises(AppException, match="No Enqueued data_importer present for this bot."):
            mongo_processor.abort_current_event(bot=bot, user=user, event_type=EventClass.data_importer)

    @patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
    def test_abort_current_event_with_model_training(self, mock_event_server):
        mongo_processor = MongoProcessor()
        bot = "test_bot"
        user = "test_user"
        mock_event_server.return_value = {"success": True, "message": "Event triggered successfully!"}
        ModelProcessor.set_training_status(bot=bot, user=user, status=EVENT_STATUS.ENQUEUED.value)
        mongo_processor.abort_current_event(bot=bot, user=user, event_type=EventClass.model_training)
        model_training_object = ModelTraining.objects(bot=bot).get()
        assert model_training_object.status == EVENT_STATUS.ABORTED.value

    @patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
    def test_abort_current_event_with_model_testing(self, mock_event_server):
        mongo_processor = MongoProcessor()
        bot = "test_bot"
        user = "test_user"
        mock_event_server.return_value = {"success": True, "message": "Event triggered successfully!"}
        ModelTestingLogProcessor.log_test_result(bot=bot, user=user, event_status=EVENT_STATUS.ENQUEUED.value)
        mongo_processor.abort_current_event(bot=bot, user=user, event_type=EventClass.model_testing)
        model_testing_object = ModelTestingLogs.objects(bot=bot).get()
        assert model_testing_object.event_status == EVENT_STATUS.ABORTED.value

    @pytest.mark.asyncio
    async def test_save_from_path_yml(self):
        processor = MongoProcessor()
        result = await (
            processor.save_from_path(
                "./tests/testing_data/yml_training_files", bot="test_load_yml", user="testUser"
            )
        )
        assert result is None
        assert len(list(Intents.objects(bot="test_load_yml", user="testUser", use_entities=False))) == 5
        assert len(list(Intents.objects(bot="test_load_yml", user="testUser", use_entities=True))) == 27
        assert len(
            list(Slots.objects(bot="test_load_yml", user="testUser", influence_conversation=True, status=True))) == 12
        assert len(
            list(Slots.objects(bot="test_load_yml", user="testUser", influence_conversation=False, status=True))) == 10
        multiflow_stories = processor.load_multiflow_stories_yaml(bot='test_load_yml')
        print(multiflow_stories['multiflow_story'][0]['events'][0])
        step_data = multiflow_stories['multiflow_story'][0]['events'][0]['step']
        assert step_data['component_id'] is not None
        fields = ['block_name', 'start_checkpoints', 'end_checkpoints', 'events', 'metadata', 'template_type']
        for item in fields:
            assert item in multiflow_stories['multiflow_story'][0].keys()

    def test_bot_id_change(self):
        bot_id = Slots.objects(bot="test_load_yml", user="testUser", influence_conversation=False, name='bot').get()
        assert bot_id['initial_value'] == "test_load_yml"

    def test_validate_data_success(self):
        bot = 'test_bot'
        user = 'test_user'
        collection_name = 'groceries'
        primary_key_col = "id"

        metadata = [
            {
                "column_name": "id",
                "data_type": "int",
                "enable_search": True,
                "create_embeddings": True
            },
            {
                "column_name": "item",
                "data_type": "str",
                "enable_search": True,
                "create_embeddings": True
            },
            {
                "column_name": "price",
                "data_type": "float",
                "enable_search": True,
                "create_embeddings": True
            },
            {
                "column_name": "quantity",
                "data_type": "int",
                "enable_search": True,
                "create_embeddings": True
            }
        ]

        cognition_schema = CognitionSchema(
            metadata=[ColumnMetadata(**item) for item in metadata],
            collection_name=collection_name,
            user=user,
            bot=bot,
            timestamp=datetime.utcnow()
        )
        cognition_schema.validate(clean=True)
        cognition_schema.save()

        data = [
            {"id": 1, "item": "Juice", "price": 2.50, "quantity": 10},
            {"id": 2, "item": "Apples", "price": 1.20, "quantity": 20},
            {"id": 3, "item": "Bananas", "price": 0.50, "quantity": 15},
        ]

        processor = CognitionDataProcessor()
        validation_summary = processor.validate_data(
            primary_key_col=primary_key_col,
            collection_name=collection_name,
            data=data,
            bot=bot
        )

        assert validation_summary == {}
        CognitionSchema.objects(bot=bot, collection_name="groceries").delete()

    def test_validate_data_missing_collection(self):
        bot = 'test_bot'
        collection_name = 'nonexistent_collection'
        primary_key_col = "id"
        data = [{"id": 1, "item": "Juice", "price": 2.50, "quantity": 10}]

        processor = CognitionDataProcessor()

        with pytest.raises(AppException, match=f"Collection '{collection_name}' does not exist."):
            processor.validate_data(
                primary_key_col=primary_key_col,
                collection_name=collection_name,
                data=data,
                bot=bot
            )

    def test_validate_data_missing_primary_key(self):
        bot = 'test_bot'
        user = 'test_user'
        collection_name = 'groceries'
        primary_key_col = "id"

        metadata = [
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True},
            {"column_name": "price", "data_type": "float", "enable_search": True, "create_embeddings": True},
            {"column_name": "quantity", "data_type": "int", "enable_search": True, "create_embeddings": True}
        ]

        cognition_schema = CognitionSchema(
            metadata=[ColumnMetadata(**item) for item in metadata],
            collection_name=collection_name,
            user=user,
            bot=bot,
            timestamp=datetime.utcnow()
        )
        cognition_schema.validate(clean=True)
        cognition_schema.save()

        data = [
            {"item": "Juice", "price": 2.50, "quantity": 10}
        ]

        processor = CognitionDataProcessor()

        with pytest.raises(AppException, match=f"Primary key '{primary_key_col}' must exist in each row."):
            processor.validate_data(
                primary_key_col=primary_key_col,
                collection_name=collection_name,
                data=data,
                bot=bot
            )
        CognitionSchema.objects(bot=bot, collection_name="groceries").delete()

    def test_validate_data_column_header_mismatch(self):
        bot = 'test_bot'
        user = 'test_user'
        collection_name = 'groceries'
        primary_key_col = "id"

        metadata = [
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True},
            {"column_name": "price", "data_type": "float", "enable_search": True, "create_embeddings": True},
            {"column_name": "quantity", "data_type": "int", "enable_search": True, "create_embeddings": True}
        ]

        cognition_schema = CognitionSchema(
            metadata=[ColumnMetadata(**item) for item in metadata],
            collection_name=collection_name,
            user=user,
            bot=bot,
            timestamp=datetime.utcnow()
        )
        cognition_schema.validate(clean=True)
        cognition_schema.save()

        data = [
            {"id": "1", "item": "Juice", "quantity": 10, "discount": 0.10}
        ]

        processor = CognitionDataProcessor()
        validation_summary = processor.validate_data(
            primary_key_col=primary_key_col,
            collection_name=collection_name,
            data=data,
            bot=bot
        )

        assert "1" in validation_summary
        assert validation_summary["1"][0]["status"] == "Column headers mismatch"
        assert validation_summary["1"][0]["expected_columns"] == ["id", "item", "price", "quantity"]
        assert validation_summary["1"][0]["actual_columns"] == ["id", "item", "quantity", "discount"]
        CognitionSchema.objects(bot=bot, collection_name="groceries").delete()

    @pytest.mark.asyncio
    @patch.object(LLMProcessor, "__collection_exists__", autospec=True)
    @patch.object(LLMProcessor, "__create_collection__", autospec=True)
    @patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
    @patch.object(litellm, "aembedding", autospec=True)
    async def test_upsert_data_success(self, mock_embedding, mock_collection_upsert, mock_create_collection,
                                       mock_collection_exists):
        bot = 'test_bot'
        user = 'test_user'
        collection_name = 'groceries'
        primary_key_col = 'id'

        metadata = [
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True},
            {"column_name": "price", "data_type": "float", "enable_search": True, "create_embeddings": True},
            {"column_name": "quantity", "data_type": "int", "enable_search": True, "create_embeddings": True},
        ]

        cognition_schema = CognitionSchema(
            metadata=[ColumnMetadata(**item) for item in metadata],
            collection_name=collection_name,
            user=user,
            bot=bot,
            timestamp=datetime.utcnow()
        )
        cognition_schema.validate(clean=True)
        cognition_schema.save()

        dummy_data = {
            "id": "2",
            "item": "Milk",
            "price": "2.80",
            "quantity": "5"
        }
        existing_document = CognitionData(
            data=dummy_data,
            content_type="json",
            collection=collection_name,
            user=user,
            bot=bot,
            timestamp=datetime.utcnow()
        )
        existing_document.save()

        upsert_data = [
            {"id": 1, "item": "Juice", "price": "2.50", "quantity": "10"},  # New entry
            {"id": 2, "item": "Milk", "price": "3.00", "quantity": "5"}  # Existing entry to be updated
        ]

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key="openai_key",
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        mock_collection_exists.return_value = False
        mock_create_collection.return_value = None
        mock_collection_upsert.return_value = None

        embedding = list(np.random.random(1532))
        mock_embedding.return_value = {'data': [{'embedding': embedding}, {'embedding': embedding}]}

        processor = CognitionDataProcessor()

        result = await processor.upsert_data(
            primary_key_col=primary_key_col,
            collection_name=collection_name,
            data=upsert_data,
            bot=bot,
            user=user
        )

        upserted_data = list(CognitionData.objects(bot=bot, collection=collection_name))

        assert result["message"] == "Upsert complete!"
        assert len(upserted_data) == 2

        inserted_record = next((item for item in upserted_data if item.data["id"] == "1"), None)
        assert inserted_record is not None
        assert inserted_record.data["item"] == "Juice"
        assert inserted_record.data["price"] == "2.50"
        assert inserted_record.data["quantity"] == "10"

        updated_record = next((item for item in upserted_data if item.data["id"] == "2"), None)
        assert updated_record is not None
        assert updated_record.data["item"] == "Milk"
        assert updated_record.data["price"] == "3.00"  # Updated price
        assert updated_record.data["quantity"] == "5"

        CognitionSchema.objects(bot=bot, collection_name="groceries").delete()
        CognitionData.objects(bot=bot, collection="groceries").delete()
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    @patch.object(LLMProcessor, "__collection_exists__", autospec=True)
    @patch.object(LLMProcessor, "__create_collection__", autospec=True)
    @patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
    @patch.object(litellm, "aembedding", autospec=True)
    async def test_upsert_data_empty_data_list(self, mock_embedding, mock_collection_upsert, mock_create_collection,
                                               mock_collection_exists):
        bot = 'test_bot'
        user = 'test_user'
        collection_name = 'groceries'
        primary_key_col = 'id'

        metadata = [
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True},
            {"column_name": "price", "data_type": "float", "enable_search": True, "create_embeddings": True},
            {"column_name": "quantity", "data_type": "int", "enable_search": True, "create_embeddings": True},
        ]

        cognition_schema = CognitionSchema(
            metadata=[ColumnMetadata(**item) for item in metadata],
            collection_name=collection_name,
            user=user,
            bot=bot,
            timestamp=datetime.utcnow()
        )
        cognition_schema.validate(clean=True)
        cognition_schema.save()

        dummy_data = {
            "id": "2",
            "item": "Milk",
            "price": "2.80",
            "quantity": "5"
        }
        existing_document = CognitionData(
            data=dummy_data,
            content_type="json",
            collection=collection_name,
            user=user,
            bot=bot,
            timestamp=datetime.utcnow()
        )
        existing_document.save()

        upsert_data = []

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key="openai_key",
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        mock_collection_exists.return_value = False
        mock_create_collection.return_value = None
        mock_collection_upsert.return_value = None

        embedding = list(np.random.random(1532))
        mock_embedding.return_value = {'data': [{'embedding': embedding}, {'embedding': embedding}]}

        processor = CognitionDataProcessor()
        result = await processor.upsert_data(
            primary_key_col=primary_key_col,
            collection_name=collection_name,
            data=upsert_data,
            bot=bot,
            user=user
        )

        data = list(CognitionData.objects(bot=bot, collection=collection_name))

        assert result["message"] == "Upsert complete!"
        assert len(data) == 1

        existing_record = data[0]
        assert existing_record.data["id"] == "2"
        assert existing_record.data["item"] == "Milk"
        assert existing_record.data["price"] == "2.80"
        assert existing_record.data["quantity"] == "5"

        CognitionSchema.objects(bot=bot, collection_name=collection_name).delete()
        CognitionData.objects(bot=bot, collection=collection_name).delete()
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    @patch.object(litellm, "aembedding", autospec=True)
    @patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
    async def test_sync_with_qdrant_success(self, mock_collection_upsert, mock_embedding):
        bot = "test_bot"
        user = "test_user"
        collection_name = "groceries"
        primary_key_col = "id"

        metadata = [
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True},
            {"column_name": "price", "data_type": "float", "enable_search": True, "create_embeddings": True},
            {"column_name": "quantity", "data_type": "int", "enable_search": True, "create_embeddings": True},
        ]

        cognition_schema = CognitionSchema(
            metadata=[ColumnMetadata(**item) for item in metadata],
            collection_name=collection_name,
            user=user,
            bot=bot,
            timestamp=datetime.utcnow()
        )
        cognition_schema.validate(clean=True)
        cognition_schema.save()

        document_data = {
            "id": "2",
            "item": "Milk",
            "price": "2.80",
            "quantity": "5"
        }
        document = CognitionData(
            data=document_data,
            content_type="json",
            collection=collection_name,
            user=user,
            bot=bot,
            timestamp=datetime.utcnow()
        )
        document.save()
        if not isinstance(document, dict):
            document = document.to_mongo().to_dict()

        embedding = list(np.random.random(1532))
        mock_embedding.return_value = {'data': [{'embedding': embedding}, {'embedding': embedding}]}

        mock_collection_upsert.return_value = None

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key="openai_key",
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        processor = CognitionDataProcessor()
        llm_processor = LLMProcessor(bot, DEFAULT_LLM)
        await processor.sync_with_qdrant(
            llm_processor=llm_processor,
            collection_name=collection_name,
            bot=bot,
            document=document,
            user=user,
            primary_key_col=primary_key_col
        )

        mock_embedding.assert_called_once_with(
            model="text-embedding-3-small",
            input=['{"id":2,"item":"Milk","price":2.8,"quantity":5}'],
            metadata={'user': user, 'bot': bot, 'invocation': 'knowledge_vault_sync'},
            api_key="openai_key",
            num_retries=3
        )
        mock_collection_upsert.assert_called_once_with(
            llm_processor,
            collection_name,
            {
                "points": [
                    {
                        "id": 12,
                        "vector": embedding,
                        "payload": {'id': 2, 'item': 'Milk', 'price': 2.8, 'quantity': 5}
                    }
                ]
            },
            err_msg="Unable to train FAQ! Contact support"
        )

        CognitionSchema.objects(bot=bot, collection_name="groceries").delete()
        CognitionData.objects(bot=bot, collection="groceries").delete()
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    @patch.object(litellm, "aembedding", autospec=True)
    @patch.object(AioRestClient, "request", autospec=True)
    async def test_sync_with_qdrant_upsert_failure(self, mock_request, mock_embedding):
        bot = "test_bot"
        user = "test_user"
        collection_name = "groceries"
        primary_key_col = "id"

        metadata = [
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True},
            {"column_name": "price", "data_type": "float", "enable_search": True, "create_embeddings": True},
            {"column_name": "quantity", "data_type": "int", "enable_search": True, "create_embeddings": True},
        ]

        cognition_schema = CognitionSchema(
            metadata=[ColumnMetadata(**item) for item in metadata],
            collection_name=collection_name,
            user=user,
            bot=bot,
            timestamp=datetime.utcnow()
        )
        cognition_schema.validate(clean=True)
        cognition_schema.save()

        document_data = {
            "id": "2",
            "item": "Milk",
            "price": "2.80",
            "quantity": "5"
        }
        document = CognitionData(
            data=document_data,
            content_type="json",
            collection=collection_name,
            user=user,
            bot=bot,
            timestamp=datetime.utcnow()
        )
        document.save()
        if not isinstance(document, dict):
            document = document.to_mongo().to_dict()

        embedding = list(np.random.random(1532))
        mock_embedding.return_value = {'data': [{'embedding': embedding}, {'embedding': embedding}]}

        mock_request.side_effect = ConnectionError("Failed to connect to Qdrant")

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key="openai_key",
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        processor = CognitionDataProcessor()
        llm_processor = LLMProcessor(bot, DEFAULT_LLM)

        with pytest.raises(AppException, match="Failed to sync document with Qdrant: Failed to connect to Qdrant"):
            await processor.sync_with_qdrant(
                llm_processor=llm_processor,
                collection_name=collection_name,
                bot=bot,
                document=document,
                user=user,
                primary_key_col=primary_key_col
            )

        mock_embedding.assert_called_once_with(
            model="text-embedding-3-small",
            input=['{"id":2,"item":"Milk","price":2.8,"quantity":5}'],
            metadata={'user': user, 'bot': bot, 'invocation': 'knowledge_vault_sync'},
            api_key="openai_key",
            num_retries=3
        )

        CognitionSchema.objects(bot=bot, collection_name="groceries").delete()
        CognitionData.objects(bot=bot, collection="groceries").delete()
        LLMSecret.objects.delete()

    def test_get_pydantic_type_int(self):
        result = CognitionDataProcessor().get_pydantic_type('int')
        expected = (int, ...)
        assert result == expected

    def test_get_pydantic_type_float(self):
        result = CognitionDataProcessor.get_pydantic_type('float')
        expected = (float, ...)
        assert result == expected

    def test_get_pydantic_type_invalid(self):
        with pytest.raises(ValueError, match="Unsupported data type: unknown"):
            CognitionDataProcessor.get_pydantic_type('unknown')

    def test_save_and_validate_success(self):
        bot = 'test_bot'
        user = 'test_user'
        table_name = 'test_table'

        metadata = [
            {
                "column_name": "order_id",
                "data_type": "int",
                "enable_search": True,
                "create_embeddings": True
            },
            {
                "column_name": "order_priority",
                "data_type": "str",
                "enable_search": True,
                "create_embeddings": True
            },
            {
                "column_name": "sales",
                "data_type": "float",
                "enable_search": True,
                "create_embeddings": True
            },
            {
                "column_name": "profit",
                "data_type": "float",
                "enable_search": True,
                "create_embeddings": True
            }
        ]

        cognition_schema = CognitionSchema(
            metadata=[ColumnMetadata(**item) for item in metadata],
            collection_name=table_name,
            user=user,
            bot=bot,
            timestamp=datetime.utcnow()
        )
        cognition_schema.validate(clean=True)  # Validate before saving
        cognition_schema.save()

        file_content = b"order_id,order_priority,sales,profit\n1,High,100.0,50.0\n"
        doc_content = UploadFile(filename="Salesstore.csv", file=BytesIO(file_content))

        processor = MongoProcessor()

        error_message = processor.save_and_validate(bot, user, doc_content, table_name)
        content_dir = os.path.join('doc_content_upload_records', bot)
        file_path = os.path.join(content_dir, doc_content.filename)

        assert os.path.exists(file_path)

        assert error_message == {}
        shutil.rmtree(os.path.dirname(file_path))

    def test_save_and_validate_header_mismatch_missing_columns(self):
        bot = 'test_bot'
        user = 'test_user'
        table_name = 'test_table'

        file_content = b"order_id,order_priority,sales\n1,High,100.0\n"
        doc_content = UploadFile(filename="Salesstore_header_mismatch.csv", file=BytesIO(file_content))

        processor = MongoProcessor()

        error_message = processor.save_and_validate(bot, user, doc_content, table_name)
        content_dir = os.path.join('doc_content_upload_records', bot)
        file_path = os.path.join(content_dir, doc_content.filename)

        assert os.path.exists(file_path)

        assert 'Header mismatch' in error_message
        assert "Expected headers ['order_id', 'order_priority', 'sales', 'profit'] but found ['order_id', 'order_priority', 'sales']" in \
               error_message['Header mismatch']
        assert 'Missing columns' in error_message
        assert "{'profit'}" in error_message['Missing columns']

        shutil.rmtree(os.path.dirname(file_path))

    def test_save_and_validate_header_mismatch_extra_columns(self):
        bot = 'test_bot'
        user = 'test_user'
        table_name = 'test_table'

        file_content = b"order_id,order_priority,sales,profit,order_quantity\n1,High,100.0,50.0,87\n"
        doc_content = UploadFile(filename="Salesstore_extra_columns.csv", file=BytesIO(file_content))

        processor = MongoProcessor()

        error_message = processor.save_and_validate(bot, user, doc_content, table_name)
        content_dir = os.path.join('doc_content_upload_records', bot)
        file_path = os.path.join(content_dir, doc_content.filename)

        assert os.path.exists(file_path)

        assert 'Header mismatch' in error_message
        assert "Expected headers ['order_id', 'order_priority', 'sales', 'profit'] but found ['order_id', 'order_priority', 'sales', 'profit', 'order_quantity']" in \
               error_message['Header mismatch']
        assert 'Extra columns' in error_message
        assert "{'order_quantity'}" in error_message['Extra columns']

        shutil.rmtree(os.path.dirname(file_path))

    def test_validate_schema_and_log_success(self):
        bot = 'test_bot'
        user = 'test_user'
        table_name = 'test_table'

        file_content = b"order_id,order_priority,sales,profit\n1,High,100.0,50.0\n"
        doc_content = UploadFile(filename="Salesstore.csv", file=BytesIO(file_content))

        processor = MongoProcessor()

        result = processor.validate_schema_and_log(bot, user, doc_content, table_name)

        assert result is True

        log = ContentValidationLogs.objects(bot=bot).first()
        assert log is not None
        assert log.is_data_uploaded is True
        assert log.file_received == doc_content.filename
        assert log.validation_errors == {}
        assert log.status is None
        assert log.event_status == EVENT_STATUS.INITIATED.value
        ContentValidationLogs.objects.delete()

    def test_validate_schema_and_log_failure(self):
        bot = 'test_bot'
        user = 'test_user'
        table_name = 'test_table'

        file_content = b"order_id,order_priority,sales\n1,High,100.0\n"
        doc_content = UploadFile(filename="Salesstore_header_mismatch.csv", file=BytesIO(file_content))

        processor = MongoProcessor()

        result = processor.validate_schema_and_log(bot, user, doc_content, table_name)

        assert result is False, "Schema validation should fail due to header mismatch."

        log = ContentValidationLogs.objects(bot=bot).first()
        print(log.to_mongo())
        assert log is not None
        assert log.is_data_uploaded is True
        assert log.file_received == doc_content.filename
        assert log.validation_errors is not None
        assert log.end_timestamp is not None
        assert log.status == "Failure"
        assert log.event_status == EVENT_STATUS.COMPLETED.value

    def test_validate_doc_content_success(self):
        """
        Test case for valid content where all rows pass validation.
        """

        column_dict = {
            'order_id': 'int',
            'order_priority': 'str',
            'sales': 'float'
        }

        doc_content = [
            {'order_id': '1', 'order_priority': 'High', 'sales': '100.0'},
            {'order_id': '2', 'order_priority': 'Low', 'sales': '200.5'},
            {'order_id': '3', 'order_priority': 'Medium', 'sales': '150.75'}
        ]
        processor = MongoProcessor()
        summary = processor.validate_doc_content(column_dict, doc_content)

        assert summary == {}

    def test_validate_doc_content_invalid_datatype(self):
        """
        Test case for content where a row has invalid data type.
        """

        column_dict = {
            'order_id': 'int',
            'order_priority': 'str',
            'sales': 'float'
        }

        doc_content = [
            {'order_id': '1', 'order_priority': 'High', 'sales': '100.0'},
            {'order_id': '2', 'order_priority': 'Low', 'sales': 'invalid_sales'},
            {'order_id': '3', 'order_priority': 'Medium', 'sales': '150.75'}
        ]

        processor = MongoProcessor()
        summary = processor.validate_doc_content(column_dict, doc_content)

        assert len(summary) == 1
        assert "Row 3" in summary
        assert summary["Row 3"][0]['column_name'] == 'sales'
        assert summary["Row 3"][0]['status'] == 'Invalid DataType'

    def test_validate_doc_content_missing_required_field(self):
        """
        Test case for content where a row is missing a required field.
        """

        column_dict = {
            'order_id': 'int',
            'order_priority': 'str',
            'sales': 'float'
        }

        doc_content = [
            {'order_id': '1', 'order_priority': 'High', 'sales': '100.0'},
            {'order_id': '2', 'order_priority': 'Low', 'sales': ''},
            {'order_id': '3', 'order_priority': 'Medium', 'sales': '150.75'}
        ]

        processor = MongoProcessor()
        summary = processor.validate_doc_content(column_dict, doc_content)

        assert len(summary) == 1
        assert "Row 3" in summary
        assert summary["Row 3"][0]['column_name'] == 'sales'
        assert summary["Row 3"][0]['status'] == 'Required Field is Empty'

    def test_validate_doc_content_multiple_errors(self):
        """
        Test case for content where multiple rows have errors.
        """

        column_dict = {
            'order_id': 'int',
            'order_priority': 'str',
            'sales': 'float'
        }

        doc_content = [
            {'order_id': 'invalid_id', 'order_priority': 'High', 'sales': '100.0'},
            {'order_id': '', 'order_priority': 'Low', 'sales': 'invalid_sales'},
            {'order_id': '3', 'order_priority': 'Medium', 'sales': '150.75'}
        ]

        processor = MongoProcessor()
        summary = processor.validate_doc_content(column_dict, doc_content)

        assert len(summary) == 2

        assert "Row 2" in summary
        assert summary["Row 2"][0]['column_name'] == 'order_id'
        assert summary["Row 2"][0]['status'] == 'Invalid DataType'

        assert "Row 3" in summary
        assert len(summary["Row 3"]) == 2
        assert summary["Row 3"][0]['column_name'] == 'order_id'
        assert summary["Row 3"][0]['status'] == 'Required Field is Empty'
        assert summary["Row 3"][1]['column_name'] == 'sales'
        assert summary["Row 3"][1]['status'] == 'Invalid DataType'

    def test_get_error_report_file_path_success(self):
        bot = "test_bot"
        event_id = "12345"

        base_dir = os.path.join('content_upload_summary', bot)
        os.makedirs(base_dir, exist_ok=True)
        expected_path = os.path.join(base_dir, f'failed_rows_with_errors_{event_id}.csv')

        with open(expected_path, 'w') as f:
            f.write("dummy content")

        processor = MongoProcessor()
        result = processor.get_error_report_file_path(bot, event_id)
        assert result == expected_path

    def test_get_error_report_file_path_file_not_found(self):
        """ Test case where the file does not exist """
        bot = "test_bot"
        event_id = "67890"

        processor = MongoProcessor()
        try:
            processor.get_error_report_file_path(bot, event_id)
        except HTTPException as e:
            assert e.status_code == 404
            assert e.detail == "Error Report not found"

    def test_get_error_report_file_path_invalid_event_id(self):
        """ Test case for invalid event ID """
        bot = "test_bot"
        event_id = "invalid!@"

        processor = MongoProcessor()
        try:
            processor.get_error_report_file_path(bot, event_id)
        except HTTPException as e:
            assert e.status_code == 400, f"Expected status code 400, but got {e.status_code}"
            assert e.detail == "Invalid event ID"

    @pytest.fixture()
    def save_actions(self):
        from unittest import mock
        import textwrap
        from kairon.shared.actions.data_objects import SetSlots, CustomActionParameters

        HttpActionConfig(
            action_name="http_action_1",
            response=HttpActionResponse(value="The value of ${data.a.b.3} in ${data.a.b.d.0} is ${data.a.b.d}"),
            http_url="http://localhost:8081/mock",
            request_method="GET",
            headers=[HttpActionRequestBody(key="bot", parameter_type="slot", value="bot", encrypt=True),
                     HttpActionRequestBody(key="user", parameter_type="value", value="1011", encrypt=True),
                     HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True),
                     HttpActionRequestBody(key="email", parameter_type="key_vault", value="EMAIL", encrypt=False)],
            params_list=[HttpActionRequestBody(key="bot", parameter_type="slot", value="bot", encrypt=True),
                         HttpActionRequestBody(key="user", parameter_type="value", value="1011", encrypt=False),
                         HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True),
                         HttpActionRequestBody(key="name", parameter_type="key_vault", value="FIRSTNAME",
                                               encrypt=False),
                         HttpActionRequestBody(key="contact", parameter_type="key_vault", value="CONTACT",
                                               encrypt=False)],
            set_slots=[SetSlotsFromResponse(name="name", value="${data.a.b.d}"),
                       SetSlotsFromResponse(name="age", value="${data.a.b.d.0}")],
            bot="testing_bot",
            user="user"
        ).save()

        HttpActionConfig(
            action_name="http_action_2",
            response=HttpActionResponse(value="The value of ${data.a.b.3} in ${data.a.b.d.0} is ${data.a.b.d}"),
            http_url="http://localhost:8081/mock",
            request_method="GET",
            headers=[HttpActionRequestBody(key="bot", parameter_type="slot", value="bot", encrypt=True),
                     HttpActionRequestBody(key="user", parameter_type="value", value="1011", encrypt=True),
                     HttpActionRequestBody(key="name", parameter_type="slot", value="name", encrypt=True),
                     HttpActionRequestBody(key="email", parameter_type="key_vault", value="EMAIL", encrypt=False)],
            params_list=[HttpActionRequestBody(key="bot", parameter_type="slot", value="bot", encrypt=True),
                         HttpActionRequestBody(key="user", parameter_type="value", value="1011", encrypt=False),
                         HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True),
                         HttpActionRequestBody(key="name", parameter_type="key_vault", value="FIRSTNAME",
                                               encrypt=False),
                         HttpActionRequestBody(key="contact", parameter_type="key_vault", value="CONTACT",
                                               encrypt=False)],
            set_slots=[SetSlotsFromResponse(name="name", value="${data.a.b.d}"),
                       SetSlotsFromResponse(name="location", value="${data.a.b.d.0}")],
            bot="testing_bot",
            user="user"
        ).save()

        SlotSetAction(
            name="slot_set_action_1",
            set_slots=[SetSlots(name="location", type="reset_slot", value="location"),
                       SetSlots(name="name", type="from_value", value="end_user"),
                       SetSlots(name="age", type="reset_slot")],
            bot="testing_bot",
            user="user"
        ).save()
        SlotSetAction(
            name="slot_set_action_2",
            set_slots=[SetSlots(name="name", type="reset_slot", value="")],
            bot="testing_bot",
            user="user"
        ).save()

        with patch('kairon.shared.utils.SMTP', autospec=True):
            EmailActionConfig(
                action_name="email_action_1",
                smtp_url="test.test.com",
                smtp_port=293,
                smtp_password=CustomActionRequestParameters(key='smtp_password', value="test"),
                from_email=CustomActionRequestParameters(value="name", parameter_type="slot"),
                to_email=CustomActionParameters(value=["test@test.com"], parameter_type="value"),
                subject="test",
                response="Email Triggered",
                bot="testing_bot",
                user="user"
            ).save()
            EmailActionConfig(
                action_name="email_action_2",
                smtp_url="test.test.com",
                smtp_port=293,
                smtp_password=CustomActionRequestParameters(key='smtp_password', value="slot"),
                from_email=CustomActionRequestParameters(value="test@test.com", parameter_type="value"),
                to_email=CustomActionParameters(value=["test@test.com"], parameter_type="value"),
                subject="test",
                response="Email Triggered",
                bot="testing_bot",
                user="user"
            ).save()
            EmailActionConfig(
                action_name="email_action_3",
                smtp_url="test.test.com",
                smtp_port=293,
                smtp_password=CustomActionRequestParameters(key='smtp_password', value="test"),
                from_email=CustomActionRequestParameters(value="from_email", parameter_type="slot"),
                to_email=CustomActionParameters(value="name", parameter_type="slot"),
                subject="test",
                response="Email Triggered",
                bot="testing_bot",
                user="user"
            ).save()
            EmailActionConfig(
                action_name="email_action_4",
                smtp_url="test.test.com",
                smtp_port=293,
                smtp_password=CustomActionRequestParameters(key='name', parameter_type="slot", value="name"),
                from_email=CustomActionRequestParameters(value="test@test.com", parameter_type="value"),
                to_email=CustomActionParameters(value=["test@test.com"], parameter_type="value"),
                subject="test",
                response="Email Triggered",
                bot="testing_bot",
                user="user"
            ).save()
            EmailActionConfig(
                action_name="email_action_5",
                smtp_url="test.test.com",
                smtp_port=293,
                smtp_userid=CustomActionRequestParameters(key='name', parameter_type="slot", value="name"),
                smtp_password=CustomActionRequestParameters(key='smtp_password', value="test"),
                from_email=CustomActionRequestParameters(value="test@test.com", parameter_type="value"),
                to_email=CustomActionParameters(value=["test@test.com"], parameter_type="value"),
                subject="test",
                response="Email Triggered",
                bot="testing_bot",
                user="user"
            ).save()
            EmailActionConfig(
                action_name="email_action_6",
                smtp_url="test.test.com",
                smtp_port=293,
                smtp_userid=CustomActionRequestParameters(key='name', parameter_type="slot", value="name"),
                smtp_password=CustomActionRequestParameters(key='smtp_password', value="test"),
                from_email=CustomActionRequestParameters(value="test@test.com", parameter_type="value"),
                to_email=CustomActionParameters(value=["test@test.com"], parameter_type="value"),
                custom_text=CustomActionRequestParameters(key='bot', parameter_type="slot", value="bot"),
                subject="test",
                response="Email Triggered",
                bot="testing_bot",
                user="user"
            ).save()

        GoogleSearchAction(
            name="google_action_1",
            api_key=CustomActionRequestParameters(value='1234567890'),
            search_engine_id='asdfg::123456',
            bot="testing_bot",
            user="user",
            dispatch_response=False,
            num_results=3,
            set_slot="name"
        ).save()
        GoogleSearchAction(
            name="google_action_2",
            api_key=CustomActionRequestParameters(key='name', parameter_type="slot", value='name'),
            search_engine_id='asdfg::123456',
            bot="testing_bot",
            user="user",
            dispatch_response=False,
            num_results=3,
            set_slot="location"
        ).save()

        with mock.patch('zenpy.Zenpy'):
            ZendeskAction(
                name="zendesk_action_1",
                subdomain='digite751',
                user_name='udit.pandey@digite.com',
                api_token=CustomActionRequestParameters(value='1234567890'),
                subject='new ticket',
                response='ticket created',
                bot="testing_bot",
                user="user"
            ).save()
            ZendeskAction(
                name="zendesk_action_2",
                subdomain='digite751',
                user_name='udit.pandey@digite.com',
                api_token=CustomActionRequestParameters(key="name", parameter_type="slot", value='name'),
                subject='new ticket',
                response='ticket created',
                bot="testing_bot",
                user="user"
            ).save()

        def _mock_response(*args, **kwargs):
            return None

        with mock.patch('kairon.shared.actions.data_objects.JiraAction.validate', new=_mock_response):
            JiraAction(
                name="jira_action_1",
                url='https://test-digite.atlassian.net',
                user_name='test@digite.com',
                api_token=CustomActionRequestParameters(key="name", parameter_type="slot", value='name'),
                project_key='HEL',
                issue_type='Bug',
                summary='fallback',
                response='Successfully created',
                bot="testing_bot",
                user="user"
            ).save()
            JiraAction(
                name="jira_action_2",
                url='https://test-digite.atlassian.net',
                user_name='test@digite.com',
                api_token=CustomActionRequestParameters(key="location", parameter_type="slot", value='location'),
                project_key='HEL',
                issue_type='Bug',
                summary='fallback',
                response='Successfully created',
                bot="testing_bot",
                user="user"
            ).save()

        with mock.patch('pipedrive.client.Client'):
            metadata = {'name': 'location', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
            PipedriveLeadsAction(
                name="pipedrive_action_1",
                domain='https://digite751.pipedrive.com/',
                api_token=CustomActionRequestParameters(key="name", parameter_type="slot", value='name'),
                title='new lead generated',
                response='lead created',
                metadata=metadata,
                bot="testing_bot",
                user="user"
            ).save()
            metadata = {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
            PipedriveLeadsAction(
                name="pipedrive_action_2",
                domain='https://digite751.pipedrive.com/',
                api_token=CustomActionRequestParameters(key="location", parameter_type="slot", value='location'),
                title='new lead generated',
                response='lead created',
                metadata=metadata,
                bot="testing_bot",
                user="user"
            ).save()
        llm_prompts = [
            {'name': 'System Prompt',
             'data': 'You are a personal assistant. Answer question based on the context below.',
             'type': 'system', 'source': 'static', 'is_enabled': True},
            {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True},
            {'name': 'Query Prompt', 'data': "What kind of language is python?", 'instructions': 'Rephrase the query.',
             'type': 'query', 'source': 'static', 'is_enabled': False},
            {'name': 'Similarity Prompt',
             'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
             'type': 'user', 'source': 'bot_content', 'data': 'python',
             'hyperparameters': {"top_results": 10, "similarity_threshold": 0.70},
             'is_enabled': True}
        ]
        PromptAction(
            name="prompt_action_1",
            llm_type="openai",
            hyperparameters=Utility.get_llm_hyperparameters("openai"),
            num_bot_responses=2,
            llm_prompts=llm_prompts,
            user_question=UserQuestion(type="from_slot", value="name"),
            set_slots=[SetSlotsFromResponse(name="location", value="${data.a.b.d.0}")],
            bot="testing_bot",
            user="user"
        ).save()
        PromptAction(
            name="prompt_action_2",
            llm_type="openai",
            hyperparameters=Utility.get_llm_hyperparameters("openai"),
            num_bot_responses=2,
            llm_prompts=llm_prompts,
            user_question=UserQuestion(type="from_slot", value="location"),
            set_slots=[SetSlotsFromResponse(name="name", value="${data.a.b.d}")],
            bot="testing_bot",
            user="user"
        ).save()

        llm_prompts = [
            {'name': 'System Prompt',
             'data': 'You are a personal assistant. Answer question based on the context below.',
             'type': 'system', 'source': 'static', 'is_enabled': True},
            {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True},
            {'name': 'Query Prompt', 'data': "What kind of language is python?", 'instructions': 'Rephrase the query.',
             'type': 'query', 'source': 'static', 'is_enabled': False},
            {'name': 'Similarity Prompt',
             'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
             'type': 'user', 'source': 'bot_content', 'data': 'python',
             'hyperparameters': {"top_results": 10, "similarity_threshold": 0.70},
             'is_enabled': True},
            {'name': 'Name Prompt',
             'data': 'name',
             'instructions': 'Answer according to the context', 'type': 'user', 'source': 'slot',
             'is_enabled': True},
            {'name': 'Location Prompt',
             'data': 'location',
             'instructions': 'Answer according to the context', 'type': 'user', 'source': 'slot',
             'is_enabled': True}
        ]
        PromptAction(
            name="prompt_action_3",
            llm_type="anthropic",
            hyperparameters=Utility.get_llm_hyperparameters("anthropic"),
            num_bot_responses=2,
            llm_prompts=llm_prompts,
            user_question=UserQuestion(type="from_user_message", value="hello"),
            bot="testing_bot",
            user="user"
        ).save()
        WebSearchAction(
            name="web_search_action_1",
            website="https://www.w3schools.com/",
            topn=1,
            set_slot='location',
            bot="testing_bot",
            user="user"
        ).save()
        WebSearchAction(
            name="web_search_action_2",
            website="https://www.w3schools.com/",
            topn=1,
            set_slot='name',
            bot="testing_bot",
            user="user"
        ).save()
        RazorpayAction(
            name="razorpay_action_1",
            api_key=CustomActionRequestParameters(value="API_KEY", parameter_type="ActionParameterType.key_vault"),
            api_secret=CustomActionRequestParameters(value="API_SECRET", parameter_type="ActionParameterType.key_vault"),
            amount=CustomActionRequestParameters(value="amount", parameter_type="slot"),
            currency=CustomActionRequestParameters(value="INR", parameter_type="value"),
            username=CustomActionRequestParameters(parameter_type="sender_id"),
            email=CustomActionRequestParameters(parameter_type="sender_id"),
            contact=CustomActionRequestParameters(value="name", parameter_type="slot"),
            notes=[
                CustomActionRequestParameters(key="order_id", parameter_type="slot",
                                              value="order_id", encrypt=True),
                CustomActionRequestParameters(key="location", parameter_type="slot",
                                              value="location", encrypt=False),
            ],
            bot="testing_bot",
            user="user"
        ).save()
        RazorpayAction(
            name="razorpay_action_2",
            api_key=CustomActionRequestParameters(value="API_KEY", parameter_type="key_vault"),
            api_secret=CustomActionRequestParameters(value="API_SECRET", parameter_type="key_vault"),
            amount=CustomActionRequestParameters(value="location", parameter_type="slot"),
            currency=CustomActionRequestParameters(value="INR", parameter_type="value"),
            username=CustomActionRequestParameters(parameter_type="sender_id"),
            email=CustomActionRequestParameters(parameter_type="sender_id"),
            contact=CustomActionRequestParameters(value="contact", parameter_type="slot"),
            notes=[
                CustomActionRequestParameters(key="name", parameter_type="slot",
                                              value="name", encrypt=True),
                CustomActionRequestParameters(key="phone_number", parameter_type="value",
                                              value="9876543210", encrypt=False),
            ],
            bot="testing_bot",
            user="user"
        ).save()

        script = """
        name = slot["name"]
        bot_response = slots
        type = text
        """
        script = textwrap.dedent(script)
        PyscriptActionConfig(
            name="pyscript_action_1",
            source_code=script,
            dispatch_response=True,
            bot="testing_bot",
            user="user"
        ).save()
        script = """
        slots = {"location": "Bangalore"}
        bot_response = slots
        type = text
        """
        script = textwrap.dedent(script)
        PyscriptActionConfig(
            name="pyscript_action_2",
            source_code=script,
            dispatch_response=True,
            bot="testing_bot",
            user="user"
        ).save()
        DatabaseAction(
            name="database_action_1",
            collection='vector_db_collection',
            payload=[DbQuery(query_type=DbActionOperationType.payload_search.value,
                             type=DbQueryValueType.from_slot.value,
                             value="name")],
            response=HttpActionResponse(value="The value of ${data.0.city} with color ${data.0.color} is ${data.0.id}"),
            set_slots=[SetSlotsFromResponse(name="city_value", value="${data.0.id}")],
            bot="testing_bot",
            user="user"
        ).save()
        DatabaseAction(
            name="database_action_2",
            collection='vector_db_collection',
            payload=[DbQuery(query_type=DbActionOperationType.payload_search.value,
                             type=DbQueryValueType.from_slot.value,
                             value="search")],
            response=HttpActionResponse(value="The value of ${data.0.city} with color ${data.0.color} is ${data.0.id}"),
            set_slots=[SetSlotsFromResponse(name="location", value="${data.0.id}")],
            bot="testing_bot",
            user="user"
        ).save()

        CallbackConfig(
            name="callback_script2",
            pyscript_code="bot_response='hello world'",
            validation_secret=encrypt_secret(
                "gAAAAABmqK71xDb4apnxOAfJjDUv1lrCTooWNX0GPyBHhqW1KBlblUqGNPwsX1V7FlIlgpwWGRWljiYp9mYAf1eG4AcG1dTXQuZCndCewox"),
            execution_mode="sync",
            bot="6697add6b8e47524eb983373",
        ).save()

        CallbackActionConfig(
            name="callback_action1",
            callback_name="callback_script2",
            dynamic_url_slot_name="location",
            metadata_list=[],
            bot_response="Hello",
            dispatch_bot_response=True,
            bot="testing_bot",
            user="user"
        ).save()
        CallbackActionConfig(
            name="callback_action2",
            callback_name="callback_script2",
            dynamic_url_slot_name="name",
            metadata_list=[],
            bot_response="Hello",
            dispatch_bot_response=True,
            bot="testing_bot",
            user="user"
        ).save()
        ScheduleAction(
            name="schedule_action_1",
            bot="testing_bot",
            user="user",
            schedule_time=CustomActionDynamicParameters(parameter_type=ActionParameterType.slot.value,
                                                        value="name"),
            schedule_action="callback_script2",
            timezone="Asia/Kolkata",
            response_text="Action schedule",
            params_list=[CustomActionRequestParameters(key="bot", parameter_type="slot", value="bot", encrypt=True),
                         CustomActionRequestParameters(key="user", parameter_type="value", value="1011", encrypt=False)]
        ).save()
        ScheduleAction(
            name="schedule_action_2",
            bot="testing_bot",
            user="user",
            schedule_time=CustomActionDynamicParameters(parameter_type=ActionParameterType.slot.value,
                                                        value="location"),
            schedule_action="callback_script2",
            timezone="Asia/Kolkata",
            response_text="Action schedule",
            params_list=[CustomActionRequestParameters(key="name", parameter_type="slot", value="name", encrypt=True),
                         CustomActionRequestParameters(key="user", parameter_type="value", value="1011", encrypt=False)]
        ).save()
        LiveAgentActionConfig(
            name="live_agent_action",
            bot_response="Connecting to live agent",
            dispatch_bot_response=True,
            bot="testing_bot",
            user="user",
        ).save()
        KaironTwoStageFallbackAction(
            name="two_stage_fallback_action",
            text_recommendations={
                "count": 3,
                "use_intent_ranking": True
            },
            bot="testing_bot",
            user="user",
        ).save()
        semantic_expression = "if ((location in ['Mumbai', 'Bangalore'] && location.startsWith('M') " \
                              "&& location.endsWith('i')) || location.length() > 20) " \
                              "{return true;} else {return false;}"
        FormValidationAction(
            name="form_validation_action",
            slot="location",
            validation_semantic=semantic_expression,
            bot="testing_bot",
            user="user"
        ).save()

    def test_get_slot_actions(self, save_actions):
        processor = MongoProcessor()
        actions = processor.get_slot_mapped_actions('testing_bot', 'name')
        print(actions)
        assert actions == {
            'http_action': ['http_action_1', 'http_action_2'],
            'email_action': ['email_action_1', 'email_action_3', 'email_action_4', 'email_action_5', 'email_action_6'],
            'zendesk_action': ['zendesk_action_2'],
            'jira_action': ['jira_action_1'],
            'slot_set_action': ['slot_set_action_1', 'slot_set_action_2'],
            'google_search_action': ['google_action_1', 'google_action_2'],
            'pipedrive_leads_action': ['pipedrive_action_1', 'pipedrive_action_2'],
            'prompt_action': ['prompt_action_1', 'prompt_action_2', 'prompt_action_3'],
            'web_search_action': ['web_search_action_2'],
            'razorpay_action': ['razorpay_action_1', 'razorpay_action_2'],
            'pyscript_action': ['pyscript_action_1'],
            'database_action': ['database_action_1'],
            'callback_action': ['callback_action2'],
            'schedule_action': ['schedule_action_1', 'schedule_action_2']
        }

        actions = processor.get_slot_mapped_actions('testing_bot', 'bot')
        print(actions)
        assert actions == {
            'http_action': ['http_action_1', 'http_action_2'],
            'email_action': ['email_action_6'],
            'zendesk_action': [],
            'jira_action': [],
            'slot_set_action': [],
            'google_search_action': [],
            'pipedrive_leads_action': [],
            'prompt_action': [],
            'web_search_action': [],
            'razorpay_action': [],
            'pyscript_action': [],
            'database_action': [],
            'callback_action': [],
            'schedule_action': ['schedule_action_1']
        }

        actions = processor.get_slot_mapped_actions('testing_bot', 'location')
        print(actions)
        assert actions == {
            'http_action': ['http_action_2'],
            'email_action': [],
            'zendesk_action': [],
            'jira_action': ['jira_action_2'],
            'slot_set_action': ['slot_set_action_1'],
            'google_search_action': ['google_action_2'],
            'pipedrive_leads_action': ['pipedrive_action_1', 'pipedrive_action_2'],
            'prompt_action': ['prompt_action_1', 'prompt_action_2', 'prompt_action_3'],
            'web_search_action': ['web_search_action_1'],
            'razorpay_action': ['razorpay_action_1', 'razorpay_action_2'],
            'pyscript_action': ['pyscript_action_2'],
            'database_action': ['database_action_2'],
            'callback_action': ['callback_action1'],
            'schedule_action': ['schedule_action_2']
        }

    def test_get_collection_data_with_no_collection_data(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = CognitionDataProcessor()
        response = list(processor.list_collection_data(bot))

        assert response == []

    def test_save_collection_data_with_with_keys_not_present(self):
        bot = 'test_bot'
        user = 'test_user'
        request_body = {
            "collection_name": "user",
            "is_secure": ["name", "mobile_number", "address"],
            "data": {
                "name": "Mahesh",
                "age": 24,
                "mobile_number": "9876543210",
                "location": "Bangalore"
            }
        }
        processor = CognitionDataProcessor()
        with pytest.raises(ValidationError, match='is_secure contains keys that are not present in data'):
            processor.save_collection_data(request_body, user, bot)


    def test_save_collection_data_with_collection_name_empty(self):
        bot = 'test_bot'
        user = 'test_user'
        request_body = {
            "collection_name": "",
            "is_secure": ["name", "mobile_number"],
            "data": {
                "name": "Mahesh",
                "age": 24,
                "mobile_number": "9876543210",
                "location": "Bangalore"
            }
        }
        processor = CognitionDataProcessor()
        with pytest.raises(AppException, match='collection name is empty'):
            processor.save_collection_data(request_body, user, bot)

    def test_save_collection_data_with_invalid_is_secure(self):
        bot = 'test_bot'
        user = 'test_user'
        request_body = {
            "collection_name": "user",
            "is_secure": "name, mobile_number",
            "data": {
                "name": "Mahesh",
                "age": 24,
                "mobile_number": "9876543210",
                "location": "Bangalore"
            }
        }
        processor = CognitionDataProcessor()
        with pytest.raises(AppException, match='is_secure should be list of keys'):
            processor.save_collection_data(request_body, user, bot)

    def test_save_collection_data_with_invalid_data(self):
        bot = 'test_bot'
        user = 'test_user'
        request_body = {
            "collection_name": "user",
            "is_secure": ["name", "mobile_number"],
            "data": "Mahesh"
        }
        processor = CognitionDataProcessor()
        with pytest.raises(AppException, match='Invalid value for data'):
            processor.save_collection_data(request_body, user, bot)

    def test_save_collection_data(self):
        bot = 'test_bot'
        user = 'test_user'
        request_body = {
            "collection_name": "user",
            "is_secure": ["name", "mobile_number"],
            "data": {
                "name": "Mahesh",
                "age": 24,
                "mobile_number": "9876543210",
                "location": "Bangalore"
            }
        }
        processor = CognitionDataProcessor()
        collection_id = processor.save_collection_data(request_body, user, bot)
        pytest.collection_id = collection_id

    def test_save_collection_data_with_collection_name_already_exist(self):
        request_body = {
            "collection_name": "user",
            "is_secure": [],
            "data": {
                "name": "Hitesh",
                "age": 25,
                "mobile_number": "989284928928",
                "location": "Mumbai"
            }
        }
        bot = 'test_bot'
        user = 'test_user'

        processor = CognitionDataProcessor()
        processor.save_collection_data(request_body, user, bot)

    def test_get_collection_data(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = CognitionDataProcessor()
        response = list(processor.list_collection_data(bot))

        for coll in response:
            coll.pop("_id")
        assert response == [
            {
                'collection_name': 'user',
                'is_secure': ['name', 'mobile_number'],
                'data': {
                    'name': 'Mahesh',
                    'age': 24,
                    'mobile_number': '9876543210',
                    'location': 'Bangalore'
                }
            },
            {
                'collection_name': 'user',
                'is_secure': [],
                'data': {
                    'name': 'Hitesh',
                    'age': 25,
                    'mobile_number': '989284928928',
                    'location': 'Mumbai'
                }
            }
        ]

    def test_update_collection_data_with_keys_not_present(self):
        request_body = {
            "collection_name": "user",
            "is_secure": ["name", "mobile_number", "aadhar"],
            "data": {
                "name": "Mahesh",
                "age": 24,
                "mobile_number": "9876543210",
                "location": "Bangalore"
            }
        }

        bot = 'test_bot'
        user = 'test_user'

        processor = CognitionDataProcessor()
        with pytest.raises(ValidationError, match='is_secure contains keys that are not present in data'):
            processor.update_collection_data(pytest.collection_id, request_body, user, bot)

    def test_update_collection_data_with_collection_name_empty(self):
        request_body = {
            "collection_name": "",
            "is_secure": ["name", "mobile_number"],
            "data": {
                "name": "Mahesh",
                "age": 24,
                "mobile_number": "9876543210",
                "location": "Bangalore"
            }
        }

        bot = 'test_bot'
        user = 'test_user'

        processor = CognitionDataProcessor()
        with pytest.raises(AppException, match='collection name is empty'):
            processor.update_collection_data(pytest.collection_id, request_body, user, bot)

    def test_update_collection_data_with_invalid_is_secure(self):
        request_body = {
            "collection_name": "user",
            "is_secure": "name, mobile_number",
            "data": {
                "name": "Mahesh",
                "age": 24,
                "mobile_number": "9876543210",
                "location": "Bangalore"
            }
        }
        bot = 'test_bot'
        user = 'test_user'

        processor = CognitionDataProcessor()
        with pytest.raises(AppException, match='is_secure should be list of keys'):
            processor.update_collection_data(pytest.collection_id, request_body, user, bot)

    def test_update_collection_data_with_invalid_data(self):
        request_body = {
            "collection_name": "user",
            "is_secure": ["name", "mobile_number"],
            "data": "Mahesh"
        }

        bot = 'test_bot'
        user = 'test_user'

        processor = CognitionDataProcessor()
        with pytest.raises(AppException, match='Invalid value for data'):
            processor.update_collection_data(pytest.collection_id, request_body, user, bot)

    def test_update_collection_data(self):
        request_body = {
            "collection_name": "user",
            "is_secure": ["mobile_number", "location"],
            "data": {
                "name": "Mahesh",
                "age": 24,
                "mobile_number": "9876543210",
                "location": "Bangalore"
            }
        }
        bot = 'test_bot'
        user = 'test_user'

        processor = CognitionDataProcessor()
        pytest.collection_id = processor.update_collection_data(pytest.collection_id, request_body, user, bot)

    def test_update_collection_data_doesnot_exist(self):
        request_body = {
            "collection_name": "user_details",
            "is_secure": ["mobile_number", "location"],
            "data": {
                "name": "Mahesh",
                "age": 24,
                "mobile_number": "9876543210",
                "location": "Bangalore"
            }
        }

        bot = 'test_bot'
        user = 'test_user'

        processor = CognitionDataProcessor()
        with pytest.raises(AppException, match='Collection Data with given id and collection_name not found!'):
            processor.update_collection_data(pytest.collection_id, request_body, user, bot)

    def test_get_collection_data_after_update(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = CognitionDataProcessor()
        response = list(processor.list_collection_data(bot))

        for coll in response:
            coll.pop("_id")
        assert response == [
            {
                'collection_name': 'user',
                'is_secure': ['mobile_number', 'location'],
                'data': {
                    'name': 'Mahesh',
                    'age': 24,
                    'mobile_number': '9876543210',
                    'location': 'Bangalore'
                }
            },
            {
                'collection_name': 'user',
                'is_secure': [],
                'data': {
                    'name': 'Hitesh',
                    'age': 25,
                    'mobile_number': '989284928928',
                    'location': 'Mumbai'
                }
            }
        ]

    def test_get_collection_data_with_mismatch_filter_length(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = CognitionDataProcessor()
        with pytest.raises(AppException, match='Keys and values lists must be of the same length.'):
            list(processor.get_collection_data(bot, collection_name="user", key=["name", "location"],
                                               value=["Mahesh"]))

    def test_get_collection_data_with_filters(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = CognitionDataProcessor()
        response = list(processor.get_collection_data(bot, collection_name="user", key=["name"],
                                                      value=["Mahesh"]))
        for coll in response:
            coll.pop("_id")
        assert response == [
            {
                'collection_name': 'user',
                'is_secure': ['mobile_number', 'location'],
                'data': {
                    'name': 'Mahesh',
                    'age': 24,
                    'mobile_number': '9876543210',
                    'location': 'Bangalore'
                }
            }
        ]
        response = list(processor.get_collection_data(bot, collection_name="user", key=["name", "location"],
                                                      value=["Mahesh", "Mumbai"]))
        for coll in response:
            coll.pop("_id")
        assert response == []
        response = list(processor.get_collection_data(bot, collection_name="user", key=["name", "location"],
                                                      value=["Hitesh", "Mumbai"]))
        for coll in response:
            coll.pop("_id")
        assert response == [
            {
                'collection_name': 'user',
                'is_secure': [],
                'data': {
                    'name': 'Hitesh',
                    'age': 25,
                    'mobile_number': '989284928928',
                    'location': 'Mumbai'
                }
            }
        ]

    def test_get_collection_data_with_collection_id(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = CognitionDataProcessor()
        response = processor.get_collection_data_with_id(bot, collection_id=pytest.collection_id)
        print(response)
        assert response == {
            '_id': pytest.collection_id,
            'collection_name': 'user',
            'is_secure': ['mobile_number', 'location'],
            'data': {
                'name': 'Mahesh',
                'age': 24,
                'mobile_number': '9876543210',
                'location': 'Bangalore'
            }
        }

    def test_delete_collection_data_doesnot_exist(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = CognitionDataProcessor()
        with pytest.raises(AppException, match='Collection Data does not exists!'):
            processor.delete_collection_data("66b1d6218d29ff530381eed5", bot, user)

    def test_delete_collection_data(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = CognitionDataProcessor()
        processor.delete_collection_data(pytest.collection_id, bot, user)

    def test_get_collection_data_with_collection_id_doesnot_exists(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = CognitionDataProcessor()
        with pytest.raises(AppException, match='Collection data does not exists!'):
            processor.get_collection_data_with_id(bot, collection_id=pytest.collection_id)

    def test_get_collection_data_after_delete(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = CognitionDataProcessor()
        response = list(processor.list_collection_data(bot))

        for coll in response:
            coll.pop("_id")
        assert response == [
            {
                'collection_name': 'user',
                'is_secure': [],
                'data': {
                    'name': 'Hitesh',
                    'age': 25,
                    'mobile_number': '989284928928',
                    'location': 'Mumbai'
                }
            }
        ]

    def test_add_pyscript_action_empty_name(self):
        bot = 'test_bot'
        user = 'test_user'
        action = "test_add_pyscript_action_empty_name"
        script = "bot_response='hello world'"
        processor = MongoProcessor()
        pyscript_config = PyscriptActionRequest(
            name=action,
            source_code=script,
            dispatch_response=False,
        )
        pyscript_config_dict = pyscript_config.dict()
        pyscript_config_dict['name'] = ''
        with pytest.raises(ValidationError, match="Action name cannot be empty"):
            processor.add_pyscript_action(pyscript_config_dict, user, bot)

    def test_add_pyscript_action_empty_source_code(self):
        bot = 'test_bot'
        user = 'test_user'
        action = "test_add_pyscript_action_empty_source_code"
        script = "bot_response='hello world'"
        processor = MongoProcessor()
        pyscript_config = PyscriptActionRequest(
            name=action,
            source_code=script,
            dispatch_response=False,
        )
        pyscript_config_dict = pyscript_config.dict()
        pyscript_config_dict['source_code'] = ''
        with pytest.raises(ValidationError, match="Source code cannot be empty"):
            processor.add_pyscript_action(pyscript_config_dict, user, bot)

    def test_add_pyscript_action_with_utter(self):
        bot = 'test_bot'
        user = 'test_user'
        action = "test_add_pyscript_action_empty_name"
        script = "bot_response='hello world'"
        processor = MongoProcessor()
        pyscript_config = PyscriptActionRequest(
            name=action,
            source_code=script,
            dispatch_response=False,
        )
        pyscript_config_dict = pyscript_config.dict()
        pyscript_config_dict['name'] = "utter_add_pyscript_action_empty_name"
        with pytest.raises(AppException, match="Action name cannot start with utter_"):
            processor.add_pyscript_action(pyscript_config_dict, user, bot)

    def test_add_pyscript_action(self):
        bot = 'test_bot'
        user = 'test_user'
        action = "test_add_pyscript_action"
        script = "bot_response='hello world'"
        processor = MongoProcessor()
        pyscript_config = PyscriptActionRequest(
            name=action,
            source_code=script,
            dispatch_response=False,
        )
        action_id = processor.add_pyscript_action(pyscript_config.dict(), user, bot)
        assert Actions.objects(name=action, status=True, bot=bot).get()
        pyscript_config_action = PyscriptActionConfig.objects(name=action, bot=bot, status=True).get()
        assert str(pyscript_config_action.id) == action_id
        assert pyscript_config_action.name == action
        assert pyscript_config_action.source_code == script
        assert not pyscript_config_action.dispatch_response

    def test_add_pyscript_action_with_name_already_exist(self):
        bot = 'test_bot'
        user = 'test_user'
        action = "test_add_pyscript_action"
        script = "bot_response='hello world'"
        processor = MongoProcessor()
        pyscript_config = PyscriptActionRequest(
            name=action,
            source_code=script,
            dispatch_response=False,
        )
        with pytest.raises(AppException, match="Action exists!"):
            processor.add_pyscript_action(pyscript_config.dict(), user, bot)

    def test_add_pyscript_action_case_insensitivity(self):
        bot = 'test_bot'
        user = 'test_user'
        action = "TEST_ADD_PYSCRIPT_ACTION_CASE_INSENSITIVITY"
        script = "bot_response='hello world'"
        processor = MongoProcessor()
        pyscript_config = PyscriptActionRequest(
            name=action,
            source_code=script,
            dispatch_response=False,
        )
        action_id = processor.add_pyscript_action(pyscript_config.dict(), user, bot)
        assert Actions.objects(name="test_add_pyscript_action_case_insensitivity", status=True, bot=bot).get()
        pyscript_config_action = PyscriptActionConfig.objects(name="test_add_pyscript_action_case_insensitivity",
                                                              bot=bot, status=True).get()
        assert str(pyscript_config_action.id) == action_id
        assert pyscript_config_action.name == "test_add_pyscript_action_case_insensitivity"
        assert pyscript_config_action.source_code == script
        assert not pyscript_config_action.dispatch_response

    def test_update_pyscript_action_doesnot_exist(self):
        bot = 'test_bot'
        user = 'test_user'
        action = "test_update_pyscript_action"
        script = "bot_response='hello world'"
        processor = MongoProcessor()
        pyscript_config = PyscriptActionRequest(
            name=action,
            source_code=script,
            dispatch_response=False,
        )
        with pytest.raises(AppException, match='Action with name "test_update_pyscript_action" not found'):
            processor.update_pyscript_action(pyscript_config.dict(), user, bot)

    def test_update_pyscript_action(self):
        bot = 'test_bot'
        user = 'test_user'
        action = "test_add_pyscript_action"
        script = "bot_response='hello world'"
        processor = MongoProcessor()
        pyscript_config = PyscriptActionRequest(
            name=action,
            source_code=script,
            dispatch_response=True,
        )
        action_id = processor.update_pyscript_action(pyscript_config.dict(), user, bot)
        assert Actions.objects(name=action, status=True, bot=bot).get()
        pyscript_config_action = PyscriptActionConfig.objects(name=action, bot=bot, status=True).get()
        assert pyscript_config_action.name == action
        assert pyscript_config_action.source_code == script
        assert pyscript_config_action.dispatch_response

    def test_list_pyscript_actions(self):
        bot = 'test_bot'
        user = 'test_user'
        script1 = "bot_response='hello world'"
        script2 = "bot_response='hello world'"
        processor = MongoProcessor()
        actions = list(processor.list_pyscript_actions(bot, True))
        assert len(actions) == 2
        assert actions[0]['name'] == 'test_add_pyscript_action'
        assert actions[0]['source_code'] == script1
        assert actions[0]['dispatch_response']
        assert actions[1]['name'] == 'test_add_pyscript_action_case_insensitivity'
        assert actions[1]['source_code'] == script2
        assert not actions[1]['dispatch_response']

    def test_delete_pyscript_action(self):
        name = 'test_add_pyscript_action'
        bot = 'test_bot'
        user = 'test_user'
        processor = MongoProcessor()
        processor.delete_action(name, bot, user)
        actions = list(processor.list_pyscript_actions(bot, True))
        assert len(actions) == 1

    def test_delete_pyscript_action_already_deleted(self):
        name = 'test_add_pyscript_action'
        bot = 'test_bot'
        user = 'test_user'
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Action with name "test_add_pyscript_action" not found'):
            processor.delete_action(name, bot, user)

    def test_add_pyscript_action_with_story(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "test_add_pyscript_action_case_insensitivity", "type": "PYSCRIPT_ACTION"},
        ]
        story_dict = {'name': "story with pyscript action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with pyscript action", bot=bot,
                                events__name='test_add_pyscript_action_case_insensitivity', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == "story with pyscript action"]
        assert story_with_form[0]['steps'] == [
            {"name": "greet", "type": "INTENT"},
            {"name": "test_add_pyscript_action_case_insensitivity", "type": "PYSCRIPT_ACTION"},
        ]
        processor.delete_complex_story(story_id, 'STORY', bot, user)

    def test_add_or_overwrite_config_no_existing_config(self):
        bot = 'test_config'
        user = 'test_config'
        processor = MongoProcessor()
        config = Utility.read_yaml('./tests/testing_data/valid_yml/config.yml')
        processor.add_or_overwrite_config(config, bot, user)
        config = Configs.objects().get(bot=bot).to_mongo().to_dict()
        assert config['language'] == 'fr'
        assert len(config['pipeline']) == 9
        assert len(config['policies']) == 3
        rule_policy = next((comp for comp in config["policies"] if 'RulePolicy' in comp['name']), {})
        assert rule_policy['core_fallback_action_name'] == 'action_small_talk'
        assert rule_policy['core_fallback_threshold'] == 0.75
        assert Rules.objects(block_name__iexact=DEFAULT_NLU_FALLBACK_RULE, bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_please_rephrase', bot=bot, status=True).get()

    def test_add_or_overwrite_config(self):
        bot = 'test_config'
        user = 'test_config'
        processor = MongoProcessor()
        config = Utility.read_yaml('./tests/testing_data/valid_yml/config.yml')
        idx = next((idx for idx, comp in enumerate(config["policies"]) if 'RulePolicy' in comp['name']), {})
        del config['policies'][idx]
        processor.add_or_overwrite_config(config, bot, user)
        config = Configs.objects().get(bot=bot).to_mongo().to_dict()
        assert config['language'] == 'fr'
        assert len(config['pipeline']) == 9
        assert len(config['policies']) == 3
        rule_policy = next((comp for comp in config["policies"] if 'RulePolicy' in comp['name']), {})
        assert rule_policy['core_fallback_action_name'] == 'action_default_fallback'
        assert rule_policy['core_fallback_threshold'] == 0.3
        assert Rules.objects(block_name__iexact=DEFAULT_NLU_FALLBACK_RULE, bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_please_rephrase', bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_default', bot=bot, status=True).get()

    def test_add_or_overwrite_config_user_fallback(self):
        bot = 'test_config'
        user = 'test_config'
        processor = MongoProcessor()
        config = Utility.read_yaml('./tests/testing_data/valid_yml/config.yml')
        comp = next((comp for comp in config["pipeline"] if comp['name'] == 'DIETClassifier'), {})
        comp['epoch'] = 200
        comp = next((comp for comp in config["policies"] if 'RulePolicy' in comp['name']), {})
        comp['core_fallback_action_name'] = 'action_error'
        comp['core_fallback_threshold'] = 0.5
        processor.add_or_overwrite_config(config, bot, user)
        config = Configs.objects().get(bot=bot).to_mongo().to_dict()
        assert config['language'] == 'fr'
        assert len(config['pipeline']) == 9
        assert len(config['policies']) == 3
        diet_classifier = next((comp for comp in config["pipeline"] if comp['name'] == 'DIETClassifier'), {})
        assert diet_classifier['epoch'] == 200
        rule_policy = next((comp for comp in config["policies"] if 'RulePolicy' in comp['name']), {})
        assert rule_policy['core_fallback_action_name'] == 'action_error'
        assert rule_policy['core_fallback_threshold'] == 0.5
        assert Rules.objects(block_name__iexact=DEFAULT_NLU_FALLBACK_RULE, bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_please_rephrase', bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_default', bot=bot, status=True).get()

    def test_add_or_overwrite_config_no_action_and_threshold(self):
        bot = 'test_config'
        user = 'test_config'
        processor = MongoProcessor()
        config = Utility.read_yaml('./tests/testing_data/valid_yml/config.yml')
        comp = next((comp for comp in config["policies"] if 'RulePolicy' in comp['name']), {})
        del comp['core_fallback_action_name']
        del comp['core_fallback_threshold']
        processor.add_or_overwrite_config(config, bot, user)
        config = Configs.objects().get(bot=bot).to_mongo().to_dict()
        assert config['language'] == 'fr'
        assert len(config['pipeline']) == 9
        assert len(config['policies']) == 3
        rule_policy = next((comp for comp in config["policies"] if 'RulePolicy' in comp['name']), {})
        assert rule_policy['core_fallback_action_name'] == 'action_default_fallback'
        assert rule_policy['core_fallback_threshold'] == 0.3
        assert Rules.objects(block_name__iexact=DEFAULT_NLU_FALLBACK_RULE, bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_please_rephrase', bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_default', bot=bot, status=True).get()

    def test_add_or_overwrite_config_with_fallback_classifier(self):
        bot = 'test_config'
        user = 'test_config'
        processor = MongoProcessor()
        config = Utility.read_yaml('./tests/testing_data/valid_yml/config.yml')
        config["pipeline"].append({'name': 'FallbackClassifier', 'threshold': 0.7})
        processor.add_or_overwrite_config(config, bot, user)
        config = Configs.objects().get(bot=bot).to_mongo().to_dict()
        assert config['language'] == 'fr'
        assert len(config['pipeline']) == 9
        assert len(config['policies']) == 3
        diet_classifier = next((comp for comp in config["pipeline"] if comp['name'] == 'DIETClassifier'), {})
        assert diet_classifier['epochs'] == 5
        rule_policy = next((comp for comp in config["policies"] if 'RulePolicy' in comp['name']), {})
        assert rule_policy['core_fallback_action_name'] == 'action_small_talk'
        assert rule_policy['core_fallback_threshold'] == 0.75
        assert Rules.objects(block_name__iexact=DEFAULT_NLU_FALLBACK_RULE, bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_please_rephrase', bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_default', bot=bot, status=True).get()

    def test_add_or_overwrite_config_with_fallback_policy(self):
        bot = 'test_config'
        user = 'test_config'
        processor = MongoProcessor()
        config = Utility.read_yaml('./tests/testing_data/valid_yml/config.yml')
        config['policies'].append({'name': 'FallbackPolicy', 'nlu_threshold': 0.75, 'core_threshold': 0.3})
        processor.add_or_overwrite_config(config, bot, user)
        config = Configs.objects().get(bot=bot).to_mongo().to_dict()
        assert config['language'] == 'fr'
        assert len(config['pipeline']) == 9
        assert len(config['policies']) == 3
        diet_classifier = next((comp for comp in config["pipeline"] if comp['name'] == 'DIETClassifier'), {})
        assert diet_classifier['epochs'] == 5
        rule_policy = next((comp for comp in config["policies"] if 'RulePolicy' in comp['name']), {})
        assert rule_policy['core_fallback_action_name'] == 'action_small_talk'
        assert rule_policy['core_fallback_threshold'] == 0.75
        assert not next((comp for comp in config["policies"] if comp['name'] == 'FallbackPolicy'), None)
        assert Rules.objects(block_name__iexact=DEFAULT_NLU_FALLBACK_RULE, bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_please_rephrase', bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_default', bot=bot, status=True).get()

    def test_add_or_overwrite_gpt_classifier_config_with_bot_id(self):
        bot = 'test_config'
        user = 'test_config'
        processor = MongoProcessor()
        config = Utility.read_yaml('./template/config/openai-classifier.yml')
        processor.add_or_overwrite_config(config, bot, user)
        config = Configs.objects().get(bot=bot).to_mongo().to_dict()
        assert config['language'] == 'en'
        assert config['pipeline'] == [{'name': 'kairon.shared.nlu.classifier.openai.OpenAIClassifier', 'bot_id': bot}]
        assert config['policies'] == [{'name': 'MemoizationPolicy'}, {'epochs': 200, 'name': 'TEDPolicy'},
                                      {'core_fallback_action_name': 'action_default_fallback',
                                       'core_fallback_threshold': 0.3, 'enable_fallback_prediction': False,
                                       'max_history': 5,
                                       'name': 'RulePolicy'}]

    def test_add_or_overwrite_gpt_featurizer_config_with_bot_id(self):
        bot = 'test_config'
        user = 'test_config'
        processor = MongoProcessor()
        config = Utility.read_yaml('./template/config/openai-featurizer.yml')
        processor.add_or_overwrite_config(config, bot, user)
        config = Configs.objects().get(bot=bot).to_mongo().to_dict()
        assert config['language'] == 'en'
        assert config['pipeline'] == [{'name': 'WhitespaceTokenizer'}, {'name': 'CountVectorsFeaturizer',
                                                                        'min_ngram': 1, 'max_ngram': 2},
                                      {'name': 'kairon.shared.nlu.featurizer.openai.OpenAIFeaturizer', 'bot_id': bot},
                                      {'name': 'DIETClassifier', 'epochs': 50, 'constrain_similarities': True,
                                       'entity_recognition': False},
                                      {'name': 'FallbackClassifier', 'threshold': 0.8}]
        assert config['policies'] == [{'name': 'MemoizationPolicy'}, {'epochs': 200, 'name': 'TEDPolicy'},
                                      {'core_fallback_action_name': 'action_default_fallback',
                                       'core_fallback_threshold': 0.3, 'enable_fallback_prediction': False,
                                       'max_history': 5,
                                       'name': 'RulePolicy'}]

    @pytest.mark.asyncio
    async def test_upload_case_insensitivity(self):
        processor = MongoProcessor()
        await (
            processor.save_from_path(
                "./tests/testing_data/upper_case_data", bot="test_upload_case_insensitivity", user="testUser"
            )
        )
        training_data = processor.load_nlu("test_upload_case_insensitivity")
        assert isinstance(training_data, TrainingData)
        assert training_data.intents == {'deny', 'greet'}
        assert training_data.entity_synonyms == {'Bangalore': 'karnataka', 'bengaluru': 'karnataka',
                                                 'karnataka': 'karnataka', 'KA': 'karnataka'}
        assert Synonyms.objects(bot="test_upload_case_insensitivity").get(name="karnataka")
        assert training_data.regex_features == [{'name': 'application_name', 'pattern': '[azAz09\\s+]*'},
                                                {'name': 'email_id', 'pattern': '[^@]+@[^@]+\\.[^@]+'}]
        assert training_data.lookup_tables == [{'name': 'application_name', 'elements': ['Firefox', 'Chrome', 'Tor']},
                                               {'name': 'location', 'elements': ['Mumbai', 'Karnataka', 'Bangalore']}]
        lookups = list(Lookup.objects(bot="test_upload_case_insensitivity", status=True).values_list("name"))
        assert all(item in lookups for item in ['application_name', 'location'])
        story_graph = processor.load_stories("test_upload_case_insensitivity")
        assert story_graph.story_steps[0].block_name == 'greet'
        assert story_graph.story_steps[1].block_name == 'say goodbye'
        domain = processor.load_domain("test_upload_case_insensitivity")
        assert all(slot.name in ['user', 'location', 'email_id', 'application_name', 'bot', 'kairon_action_response',
                                 'order', 'payment', 'http_status_code', 'image', 'audio', 'video', 'document',
                                 'doc_url', 'longitude', 'latitude', 'flow_reply', 'quick_reply',
                                 'session_started_metadata', 'requested_slot'] for slot in domain.slots)
        assert not DeepDiff(list(domain.responses.keys()), ['utter_please_rephrase', 'utter_greet', 'utter_goodbye',
                                                            'utter_default'], ignore_order=True)
        assert not DeepDiff(domain.entities,
                            ['user', 'location', 'email_id', 'application_name', 'bot', 'kairon_action_response',
                             'order', 'payment', 'http_status_code', 'image', 'audio', 'video', 'document', 'doc_url',
                             'longitude', 'latitude', 'flow_reply', 'quick_reply'], ignore_order=True)
        assert domain.forms == {'ask_user': {'required_slots': ['user', 'email_id']},
                                'ask_location': {'required_slots': ['location', 'application_name']}}
        assert domain.user_actions == ['ACTION_GET_GOOGLE_APPLICATION', 'ACTION_GET_MICROSOFT_APPLICATION',
                                       'utter_default', 'utter_goodbye', 'utter_greet', 'utter_please_rephrase']
        assert processor.fetch_actions('test_upload_case_insensitivity') == ['ACTION_GET_GOOGLE_APPLICATION',
                                                                             'ACTION_GET_MICROSOFT_APPLICATION']
        assert domain.intents == ['back', 'deny', 'greet', 'nlu_fallback', 'out_of_scope', 'restart', 'session_start']
        assert domain.responses == {
            'utter_please_rephrase': [{'text': "I'm sorry, I didn't quite understand that. Could you rephrase?"}],
            'utter_greet': [{'text': 'Hey! How are you?'}], 'utter_goodbye': [{'text': 'Bye'}],
            'utter_default': [{'text': 'Can you rephrase!'}]}
        rules = processor.fetch_rule_block_names("test_upload_case_insensitivity")
        assert rules == ['rule which will not wait for user message once it was applied',
                         'ask the user to rephrase whenever they send a message with low nlu confidence']
        actions = processor.load_http_action("test_upload_case_insensitivity")
        assert actions == {'http_action': [
            {'action_name': 'ACTION_GET_GOOGLE_APPLICATION', 'http_url': 'http://www.alphabet.com',
             'content_type': 'json',
             'response': {'value': 'json', 'dispatch': True, 'evaluation_type': 'expression', 'dispatch_type': 'text'},
             'request_method': 'GET', 'headers': [
                {'_cls': 'HttpActionRequestBody', 'key': 'testParam1', 'value': '', 'parameter_type': 'chat_log',
                 'encrypt': False},
                {'_cls': 'HttpActionRequestBody', 'key': 'testParam2', 'value': '', 'parameter_type': 'user_message',
                 'encrypt': False},
                {'_cls': 'HttpActionRequestBody', 'key': 'testParam3', 'value': '', 'parameter_type': 'value',
                 'encrypt': False},
                {'_cls': 'HttpActionRequestBody', 'key': 'testParam4', 'value': '', 'parameter_type': 'intent',
                 'encrypt': False},
                {'_cls': 'HttpActionRequestBody', 'key': 'testParam5', 'value': '', 'parameter_type': 'sender_id',
                 'encrypt': False},
                {'_cls': 'HttpActionRequestBody', 'key': 'testParam4', 'value': 'testValue1',
                 'parameter_type': 'slot', 'encrypt': False}],
             'params_list': [{'_cls': 'HttpActionRequestBody', 'key': 'testParam1', 'value': 'testValue1',
                              'parameter_type': 'value', 'encrypt': False},
                             {'_cls': 'HttpActionRequestBody', 'key': 'testParam2', 'value': 'testValue1',
                              'parameter_type': 'slot', 'encrypt': False}],
             'dynamic_params': {
                 "farmid": '120d37d6-6159-45f1-a3d0-edfead442971',
                 "fields": [
                     {
                         "fieldid": '58ce899a-b5ad-4a76-905b-e615672c0c66',
                         "duration_min": 2
                     }
                 ]
             }},
            {'action_name': 'ACTION_GET_MICROSOFT_APPLICATION',
             'response': {'value': 'json', 'dispatch': True, 'evaluation_type': 'expression', 'dispatch_type': 'text'},
             'http_url': 'http://www.alphabet.com', 'request_method': 'GET', 'content_type': 'json',
             'params_list': [{'_cls': 'HttpActionRequestBody', 'key': 'testParam1', 'value': 'testValue1',
                              'parameter_type': 'value', 'encrypt': False},
                             {'_cls': 'HttpActionRequestBody', 'key': 'testParam2', 'value': 'testValue1',
                              'parameter_type': 'slot', 'encrypt': False},
                             {'_cls': 'HttpActionRequestBody', 'key': 'testParam1', 'value': '',
                              'parameter_type': 'chat_log', 'encrypt': False},
                             {'_cls': 'HttpActionRequestBody', 'key': 'testParam2', 'value': '',
                              'parameter_type': 'user_message', 'encrypt': False},
                             {'_cls': 'HttpActionRequestBody', 'key': 'testParam3', 'value': '',
                              'parameter_type': 'value', 'encrypt': False},
                             {'_cls': 'HttpActionRequestBody', 'key': 'testParam4', 'value': '',
                              'parameter_type': 'intent', 'encrypt': False},
                             {'_cls': 'HttpActionRequestBody', 'key': 'testParam5', 'value': '',
                              'parameter_type': 'sender_id', 'encrypt': False},
                             {'_cls': 'HttpActionRequestBody', 'key': 'testParam4', 'value': 'testValue1',
                              'parameter_type': 'slot', 'encrypt': False}]}]}
        assert set(Utterances.objects(bot='test_upload_case_insensitivity').values_list('name')) == {'utter_goodbye',
                                                                                                     'utter_greet',
                                                                                                     'utter_default',
                                                                                                     'utter_please_rephrase'}

    @pytest.mark.asyncio
    async def test_load_from_path_yml_training_files(self):
        processor = MongoProcessor()
        await (
            processor.save_from_path(
                "./tests/testing_data/yml_training_files", bot="test_load_from_path_yml_training_files", user="testUser"
            )
        )
        training_data = processor.load_nlu("test_load_from_path_yml_training_files")
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 305
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = processor.load_stories("test_load_from_path_yml_training_files")
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 16
        assert story_graph.story_steps[14].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[14].events[2].entities[0].get('start')
        assert not story_graph.story_steps[14].events[2].entities[0].get('end')
        assert story_graph.story_steps[14].events[2].entities[0]['value'] == 'like'
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdresponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[15].events[2].entities[0].get('start')
        assert not story_graph.story_steps[15].events[2].entities[0].get('end')
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdresponse'
        domain = processor.load_domain("test_load_from_path_yml_training_files")
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 24
        assert len([slot for slot in domain.slots if slot.influence_conversation is True]) == 12
        assert len([slot for slot in domain.slots if slot.influence_conversation is False]) == 12
        assert domain.intent_properties.__len__() == 32
        assert len([intent for intent in domain.intent_properties.keys() if
                    domain.intent_properties.get(intent)['used_entities']]) == 27
        assert len([intent for intent in domain.intent_properties.keys() if
                    not domain.intent_properties.get(intent)['used_entities']]) == 5
        assert domain.responses.keys().__len__() == 29
        assert domain.entities.__len__() == 24
        assert domain.forms.__len__() == 2
        assert domain.forms.__len__() == 2
        assert domain.forms['ticket_attributes_form'] == {
            'required_slots': ['date_time',
                               'priority']}
        assert domain.forms['ticket_file_form'] == {
            'required_slots': ['file']}
        assert isinstance(domain.forms, dict)
        assert domain.user_actions.__len__() == 48

        assert processor.list_actions('test_load_from_path_yml_training_files')["http_action"].__len__() == 17
        assert processor.list_actions('test_load_from_path_yml_training_files')["utterances"].__len__() == 29
        assert processor.list_actions('test_load_from_path_yml_training_files')["form_validation_action"].__len__() == 1
        assert domain.intents.__len__() == 32
        assert not Utility.check_empty_string(
            domain.responses["utter_cheer_up"][0]["image"]
        )
        assert domain.responses["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.responses["utter_offer_help"][0]["custom"]
        rules = processor.fetch_rule_block_names("test_load_from_path_yml_training_files")
        assert len(rules) == 4
        actions = processor.load_http_action("test_load_from_path_yml_training_files")
        actions_google = processor.load_google_search_action("test_load_from_path_yml_training_files")
        assert isinstance(actions, dict) is True
        assert len(actions['http_action']) == 17
        assert len(actions_google['google_search_action']) == 1
        assert Utterances.objects(bot='test_load_from_path_yml_training_files').count() == 29

    @pytest.mark.asyncio
    async def test_load_from_path_error(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            await (
                processor.save_from_path(
                    "./tests/testing_data/error", bot="tests", user="testUser"
                )
            )

    @pytest.mark.asyncio
    async def test_load_from_path_all_scenario(self):
        processor = MongoProcessor()
        await (
            processor.save_from_path("./tests/testing_data/all", bot="all", user="testUser")
        )
        training_data = processor.load_nlu("all")
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 292
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = processor.load_stories("all")
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 16
        assert story_graph.story_steps[14].events[2].intent['name'] == 'user_feedback'
        assert story_graph.story_steps[14].events[2].entities[0]['value'] == 'like'
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdresponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdresponse'
        domain = processor.load_domain("all")
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 23
        assert all(slot.mappings[0]['type'] == 'from_entity' and slot.mappings[0]['entity'] == slot.name for slot in
                   domain.slots if slot.name not in ['requested_slot', 'session_started_metadata'])
        assert domain.responses.keys().__len__() == 27
        assert domain.entities.__len__() == 23
        assert domain.forms.__len__() == 2
        assert domain.forms['ticket_attributes_form'] == {'required_slots': {}}
        assert isinstance(domain.forms, dict)
        assert domain.user_actions.__len__() == 27
        assert domain.intents.__len__() == 29
        assert not Utility.check_empty_string(
            domain.responses["utter_cheer_up"][0]["image"]
        )
        assert domain.responses["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.responses["utter_offer_help"][0]["custom"]
        assert Utterances.objects(bot='all').count() == 27

    @pytest.mark.asyncio
    async def test_load_from_path_all_scenario_append(self):
        processor = MongoProcessor()
        await (
            processor.save_from_path("./tests/testing_data/all",
                                     "all",
                                     overwrite=False,
                                     user="testUser")
        )
        training_data = processor.load_nlu("all")
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 292
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = processor.load_stories("all")
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 16
        assert story_graph.story_steps[14].events[2].intent['name'] == 'user_feedback'
        assert story_graph.story_steps[14].events[2].entities[0]['value'] == 'like'
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdresponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdresponse'
        domain = processor.load_domain("all")
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 23
        assert domain.responses.keys().__len__() == 27
        assert domain.entities.__len__() == 23
        assert domain.forms.__len__() == 2
        assert isinstance(domain.forms, dict)
        assert domain.user_actions.__len__() == 27
        assert domain.intents.__len__() == 29
        assert not Utility.check_empty_string(
            domain.responses["utter_cheer_up"][0]["image"]
        )
        assert domain.responses["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.responses["utter_offer_help"][0]["custom"]
        assert Utterances.objects(bot='all').count() == 27

    def test_load_nlu(self):
        processor = MongoProcessor()
        training_data = processor.load_nlu("tests")
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 52
        assert training_data.entity_synonyms.__len__() == 0
        assert training_data.regex_features.__len__() == 0
        assert training_data.lookup_tables.__len__() == 0

    def test_load_domain(self):
        processor = MongoProcessor()
        domain = processor.load_domain("tests")
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 15
        assert [s.name for s in domain.slots if s.name == 'kairon_action_response' and s.value is None]
        assert domain.responses.keys().__len__() == 11
        assert domain.entities.__len__() == 14
        assert domain.form_names.__len__() == 0
        assert domain.user_actions.__len__() == 11
        assert domain.intents.__len__() == 14
        assert Utterances.objects(bot="tests").count() == 11

    def test_load_stories(self):
        processor = MongoProcessor()
        story_graph = processor.load_stories("tests")
        assert isinstance(story_graph, StoryGraph)
        assert story_graph.story_steps.__len__() == 7

    def test_add_intent(self):
        processor = MongoProcessor()
        assert processor.add_intent("greeting", "tests", "testUser", is_integration=False)
        intent = Intents.objects(bot="tests").get(name="greeting")
        assert intent.name == "greeting"

    def test_get_intents(self):
        processor = MongoProcessor()
        actual = processor.get_intents("tests")
        assert actual.__len__() == 15

    def test_add_intent_with_underscore(self):
        processor = MongoProcessor()
        assert processor.add_intent("greeting_examples", "tests", "testUser", is_integration=False)
        intent = Intents.objects(bot="tests").get(name="greeting_examples")
        assert intent.name == "greeting_examples"

    def test_add_intent_duplicate(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.add_intent("greeting", "tests", "testUser", is_integration=False)

    def test_add_intent_duplicate_case_insensitive(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.add_intent("Greeting", "tests", "testUser", is_integration=False)

    def test_add_none_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_intent(None, "tests", "testUser", is_integration=False)

    def test_add_empty_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_intent("", "tests", "testUser", is_integration=False)

    def test_add_blank_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_intent("  ", "tests", "testUser", is_integration=False)

    def test_add_training_example(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example(["Hi, How are you?"], "greeting", "tests", "testUser", is_integration=False)
        )
        assert results[0]["_id"]
        assert results[0]["text"] == "Hi, How are you?"
        assert results[0]["message"] == "Training Example added"

    def test_add_same_training_example(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example(["Hi"], "greeting", "tests", "testUser", is_integration=False)
        )
        assert results[0]["_id"] is None
        assert results[0]["text"] == "Hi"
        assert results[0]["message"] == 'Training Example exists in intent: [\'greet\']'

    def test_add_training_example_duplicate_case_insensitive(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example(["hi"], "greeting", "tests", "testUser", is_integration=False)
        )
        assert results[0]["_id"] is None
        assert results[0]["text"] == "hi"
        assert results[0]["message"] == 'Training Example exists in intent: [\'greet\']'

    def test_add_training_example_none_text(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example([None], "greeting", "tests", "testUser", is_integration=False)
        )
        assert results[0]["_id"] is None
        assert results[0]["text"] is None
        assert (
                results[0]["message"]
                == "Training Example cannot be empty or blank spaces"
        )

    def test_add_training_example_empty_text(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example([""], "greeting", "tests", "testUser", is_integration=False)
        )
        assert results[0]["_id"] is None
        assert results[0]["text"] == ""
        assert (
                results[0]["message"]
                == "Training Example cannot be empty or blank spaces"
        )

    def test_add_training_example_blank_text(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example(["  "], "greeting", "tests", "testUser", is_integration=False)
        )
        assert results[0]["_id"] is None
        assert results[0]["text"] == "  "
        assert (
                results[0]["message"]
                == "Training Example cannot be empty or blank spaces"
        )

    def test_add_training_example_none_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            results = list(
                processor.add_training_example(
                    ["Hi! How are you"], None, "tests", "testUser", is_integration=False
                )
            )
            assert results[0]["_id"] is None
            assert results[0]["text"] == "Hi! How are you"
            assert (
                    results[0]["message"]
                    == "Intent cannot be empty or blank spaces"
            )

    def test_add_training_example_empty_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            results = list(
                processor.add_training_example(
                    ["Hi! How are you"], "", "tests", "testUser", is_integration=False
                )
            )
            assert results[0]["_id"] is None
            assert results[0]["text"] == "Hi! How are you"
            assert (
                    results[0]["message"]
                    == "Intent cannot be empty or blank spaces"
            )

    def test_add_training_example_blank_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            results = list(
                processor.add_training_example(
                    ["Hi! How are you"], "  ", "tests", "testUser", is_integration=False
                )
            )
            assert results[0]["_id"] is None
            assert results[0]["text"] == "Hi! How are you"
            assert (
                    results[0]["message"]
                    == "Intent cannot be empty or blank spaces"
            )

    def test_add_empty_training_example(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            results = list(
                processor.add_training_example([""], None, "tests", "testUser", is_integration=False)
            )
            assert results[0]["_id"] is None
            assert results[0]["text"] == "Hi! How are you"
            assert (
                    results[0]["message"]
                    == "Training Example cannot be empty or blank spaces"
            )

    def test_get_training_examples(self):
        processor = MongoProcessor()
        expected = ["hey", "hello", "hi", "good morning", "good evening", "hey there"]
        actual = list(processor.get_training_examples("greet", "tests"))
        assert actual.__len__() == expected.__len__()
        assert all(a_val["text"] in expected for a_val in actual)

    def test_get_training_examples_empty(self):
        processor = MongoProcessor()
        actual = list(processor.get_training_examples("greets", "tests"))
        assert actual.__len__() == 0

    def test_get_all_training_examples(self):
        processor = MongoProcessor()
        training_examples, ids = processor.get_all_training_examples("tests")
        assert training_examples
        assert ids

    def test_training_example_exists(self):
        processor = MongoProcessor()
        intent = processor.check_training_example_exists("hey", "tests")
        assert intent == {"is_exists": True, "intent": "greet"}

    def test_training_example_does_not_exists(self):
        processor = MongoProcessor()
        intent = processor.check_training_example_exists("hgbsncj", "tests")
        assert intent == {"is_exists": False, "intent": None}

    def test_get_training_examples_as_dict(self, monkeypatch):
        processor = MongoProcessor()
        training_examples_expected = {'hi': 'greet', 'hello': 'greet', 'ok': 'affirm', 'no': 'deny'}

        def _mongo_aggregation(*args, **kwargs):
            return [{'training_examples': training_examples_expected}]

        monkeypatch.setattr(BaseQuerySet, 'aggregate', _mongo_aggregation)
        training_examples = processor.get_training_examples_as_dict("tests")
        assert training_examples == training_examples_expected

    def test_get_training_examples_as_dict_no_examples_added(self, monkeypatch):
        processor = MongoProcessor()

        def _mongo_aggregation(*args, **kwargs):
            return []

        monkeypatch.setattr(BaseQuerySet, 'aggregate', _mongo_aggregation)
        training_examples = processor.get_training_examples_as_dict("tests_bot")
        assert training_examples == {}

    def test_add_training_example_with_entity(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example(
                ["Log a [critical issue](priority)"],
                "get_priority",
                "tests",
                "testUser",
                is_integration=False
            )
        )
        assert results[0]["_id"]
        assert results[0]["text"] == "Log a [critical issue](priority)"
        assert results[0]["message"] == "Training Example added"
        intents = processor.get_intents("tests")
        assert any("get_priority" == intent["name"] for intent in intents)
        entities = processor.get_entities("tests")
        assert any("priority" == entity["name"] for entity in entities)
        new_training_example = TrainingExamples.objects(bot="tests").get(
            text="Log a critical issue"
        )
        slots = Slots.objects(bot="tests")
        new_slot = slots.get(name="priority")
        assert slots.__len__() == 15
        assert new_slot.name == "priority"
        assert new_slot.type == "text"
        assert new_training_example.text == "Log a critical issue"

    def test_get_training_examples_with_entities(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example(
                ["Make [TKT456](ticketID) a [critical issue](priority)"],
                "get_priority",
                "tests",
                "testUser",
                is_integration=False
            )
        )
        assert results[0]["_id"]
        assert (
                results[0]["text"] == "Make [TKT456](ticketid) a [critical issue](priority)"
        )
        assert results[0]["message"] == "Training Example added"
        actual = list(processor.get_training_examples("get_priority", "tests"))
        slots = Slots.objects(bot="tests")
        new_slot = slots.get(name="ticketid")
        assert any(
            [value["text"] == "Log a [critical issue](priority)" for value in actual]
        )
        assert any(
            [
                value["text"] == "Make [TKT456](ticketid) a [critical issue](priority)"
                for value in actual
            ]
        )
        assert slots.__len__() == 16
        assert new_slot.name == "ticketid"
        assert new_slot.type == "text"
        expected = ["hey", "hello", "hi", "good morning", "good evening", "hey there"]
        actual = list(processor.get_training_examples("greet", "tests"))
        assert actual.__len__() == expected.__len__()
        assert all(a_val["text"] in expected for a_val in actual)

    def test_delete_training_example(self):
        processor = MongoProcessor()
        training_examples = list(processor.get_training_examples(intent="get_priority", bot="tests"))
        expected_length = training_examples.__len__() - 1
        training_example = training_examples[0]
        expected_text = training_example['text']
        processor.remove_document(
            TrainingExamples, training_example['_id'], "tests", "testUser"
        )
        new_training_examples = list(
            processor.get_training_examples(intent="get_priority", bot="tests")
        )
        assert new_training_examples.__len__() == expected_length
        assert any(
            expected_text != example["text"] for example in new_training_examples
        )

    def test_add_training_example_multiple(self):
        processor = MongoProcessor()
        actual = list(processor.add_training_example(["Log a [critical issue](priority)",
                                                      "Make [TKT456](ticketID) a [high issue](priority)"],
                                                     intent="get_priority",
                                                     bot="tests", user="testUser", is_integration=False))
        assert actual[0]['message'] == 'Training Example exists in intent: [\'get_priority\']'
        assert actual[1]['message'] == "Training Example added"

    def test_add_entity(self):
        processor = MongoProcessor()
        assert processor.add_entity("file_text", "tests", "testUser")
        enitity = Entities.objects(bot="tests", status=True).get(name="file_text")
        assert enitity.name == "file_text"

    def test_get_entities(self):
        processor = MongoProcessor()
        expected = ["bot", "priority", "file_text", "ticketid", 'kairon_action_response', 'image', 'video', 'audio',
                    'doc_url', 'document', 'order', 'payment', 'quick_reply', 'longitude', 'latitude', 'flow_reply',
                    'http_status_code']
        actual = processor.get_entities("tests")
        assert actual.__len__() == expected.__len__()
        assert all(item["name"] in expected for item in actual)

    def test_add_entity_duplicate(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            assert processor.add_entity("file_text", "tests", "testUser")

    def test_add_entity_duplicate_case_insensitive(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            assert processor.add_entity("File_Text", "tests", "testUser")

    def test_add_none_entity(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_entity(None, "tests", "testUser")

    def test_add_empty_entity(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_entity("", "tests", "testUser")

    def test_add_blank_entity(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_entity("  ", "tests", "testUser")

    def test_add_action(self):
        processor = MongoProcessor()
        assert processor.add_action("get_priority", "test", "testUser")
        action = Actions.objects(bot="test").get(name="get_priority")
        assert action.name == "get_priority"

    def test_add_action_starting_with_utter(self):
        processor = MongoProcessor()
        assert not processor.add_action("utter_get_priority", "test", "testUser")
        with pytest.raises(DoesNotExist):
            Actions.objects(bot="test").get(name="utter_get_priority")

    def test__action_data_object(self):
        assert Actions(name="test_action", bot='test', user='test')

    def test_data_obj_action_empty(self):
        with pytest.raises(ValidationError):
            Actions(name=" ", bot='test', user='test').save()

    def test_data_obj_action_starting_with_utter(self):
        with pytest.raises(ValidationError):
            Actions(name="utter_get_priority", bot='test', user='test').save()

    def test_get_actions(self):
        processor = MongoProcessor()
        actual = processor.get_actions("test")
        assert actual.__len__() == 1
        assert actual[0]['name'] == 'get_priority'

    def test_add_action_duplicate(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.add_action("get_priority", "test", "testUser")

    def test_add_action_duplicate_case_insensitive(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            assert processor.add_action("Utter_Priority", "tests", "testUser") is None

    def test_add_none_action(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_action(None, "tests", "testUser")

    def test_add_empty_action(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_action("", "tests", "testUser")

    def test_add_blank_action(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_action("  ", "tests", "testUser")

    def test_add_text_response(self):
        processor = MongoProcessor()
        assert processor.add_text_response("Great", "utter_Happy", "tests", "testUser")
        response = Responses.objects(
            bot="tests", name="utter_happy", text__text="Great"
        ).get()
        assert response.name == "utter_happy"
        assert response.text.text == "Great"

    def test_add_custom_response(self):
        processor = MongoProcessor()
        jsondata = {"type": "section",
                    "text": {
                        "text": "Make a bet on when the world will end:",
                        "type": "mrkdwn",
                        "accessory": {"type": "datepicker",
                                      "initial_date": "2019-05-21",
                                      "placeholder": {"type": "plain_text",
                                                      "text": "Select a date"}}}}
        assert processor.add_custom_response(jsondata, "utter_custom", "tests", "testUser")
        response = Responses.objects(
            bot="tests", name="utter_custom", custom__custom=jsondata
        ).get()
        assert response.name == "utter_custom"
        assert response.custom.custom == jsondata

    def test_add_text_response_case_insensitive(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.add_text_response("Great", "Utter_Happy", "tests", "testUser")

    def test_add_custom_response_case_insensitive(self):
        processor = MongoProcessor()
        jsondata = {"type": "section",
                    "text": {
                        "text": "Make a bet on when the world will end:",
                        "type": "mrkdwn",
                        "accessory": {"type": "datepicker",
                                      "initial_date": "2019-05-21",
                                      "placeholder": {"type": "plain_text",
                                                      "text": "Select a date"}}}}
        with pytest.raises(AppException, match='Utterance already exists!'):
            processor.add_custom_response(jsondata, "UTTER_CUSTOM", "tests", "testUser")

    def test_add_text_response_duplicate(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.add_text_response("Great", "utter_happy", "tests", "testUser")

    def test_add_custom_response_duplicate(self):
        processor = MongoProcessor()
        jsondata = {"type": "section",
                    "text": {
                        "text": "Make a bet on when the world will end:",
                        "type": "mrkdwn",
                        "accessory": {"type": "datepicker",
                                      "initial_date": "2019-05-21",
                                      "placeholder": {"type": "plain_text",
                                                      "text": "Select a date"}}}}
        with pytest.raises(AppException, match='Utterance already exists!'):
            processor.add_custom_response(jsondata, "utter_custom", "tests", "testUser")

    def test_add_custom_dict_check_response(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match="Utterance must be dict type and must not be empty"):
            processor.add_custom_response("Greetings", "utter_happy", "tests", "testUser")

    def test_get_text_response(self):
        processor = MongoProcessor()
        expected = ["Great, carry on!", "Great"]
        actual = list(processor.get_response("utter_happy", "tests"))
        assert actual.__len__() == expected.__len__()
        assert all(
            item["value"]["text"] in expected
            for item in actual
            if "text" in item["value"]
        )

    def test_get_custom_response(self):
        processor = MongoProcessor()
        actual = list(processor.get_response("utter_custom", "tests"))
        actual = actual[0]
        actual.pop("_id")
        assert actual == {'value': {'custom': {'type': 'section',
                                               'text': {'text': 'Make a bet on when the world will end:',
                                                        'type': 'mrkdwn', 'accessory': {'type': 'datepicker',
                                                                                        'initial_date': '2019-05-21',
                                                                                        'placeholder': {
                                                                                            'type': 'plain_text',
                                                                                            'text': 'Select a date'}}}}},
                          'type': 'json'}

    def test_get_text_response_empty_utterance(self):
        processor = MongoProcessor()
        actual = list(processor.get_response("", "tests"))
        assert actual.__len__() == 0
        actual = list(processor.get_response(" ", "tests"))
        assert actual.__len__() == 0

    def test_delete_text_response(self):
        processor = MongoProcessor()
        responses = list(processor.get_response(name="utter_happy", bot="tests"))
        expected_length = responses.__len__() - 1
        response = responses[0]
        expected_text = response['value']['text']
        processor.remove_document(Responses, response['_id'], "tests", "testUser")
        actual = list(processor.get_response("utter_happy", "tests"))
        assert actual.__len__() == expected_length
        assert all(
            expected_text != item["value"]["text"]
            for item in actual
            if "text" in item["value"]
        )

    def test_add_none_text_response(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_text_response(None, "utter_happy", "tests", "testUser")

    def test_add_none_custom_response(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_custom_response(None, "utter_custom", "tests", "testUser")

    def test_add_empty_text_Response(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_text_response("", "utter_happy", "tests", "testUser")

    def test_add_empty_custom_response(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_custom_response("", "utter_custom", "tests", "testUser")

    def test_add_blank_text_response(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_text_response("", "utter_happy", "tests", "testUser")

    def test_add_blank_custom_response(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_custom_response("", "utter_custom", "tests", "testUser")

    def test_add_none_response_name(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_text_response("Greet", None, "tests", "testUser")

    def test_add_none_custom_response_name(self):
        processor = MongoProcessor()
        jsondata = {"type": "section",
                    "text": {
                        "text": "Make a bet on when the world will end:",
                        "type": "mrkdwn",
                        "accessory": {"type": "datepicker",
                                      "initial_date": "2019-05-21",
                                      "placeholder": {"type": "plain_text",
                                                      "text": "Select a date"}}}}
        with pytest.raises(AppException):
            processor.add_custom_response(jsondata, None, "tests", "testUser")

    def test_add_empty_response_name(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_text_response("Welcome", "", "tests", "testUser")

    def test_add_blank_response_name(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_text_response("Welcome", " ", "tests", "testUser")

    def test_edit_custom_responses_duplicate(self):
        processor = MongoProcessor()
        jsondata = {"type": "section",
                    "text": {
                        "text": "Make a bet on when the world will end:",
                        "type": "mrkdwn",
                        "accessory": {"type": "button",
                                      "initial_date": "2019-05-21",
                                      "placeholder": {"type": "plain_text",
                                                      "text": "Select a date"}}}}
        assert processor.add_custom_response(jsondata, "utter_custom", "tests", "testUser")
        responses = list(processor.get_response("utter_custom", "tests"))
        with pytest.raises(AppException, match="Utterance already exists!"):
            processor.edit_custom_response(responses[0]["_id"], jsondata, name="utter_happy", bot="tests",
                                           user="testUser")

    def test_edit_custom_responses_empty(self):
        processor = MongoProcessor()
        jsondata = {}
        responses = list(processor.get_response("utter_custom", "tests"))
        with pytest.raises(ValidationError, match="Utterance must be dict type and must not be empty"):
            processor.edit_custom_response(responses[0]["_id"], jsondata, name="utter_custom", bot="tests",
                                           user="testUser")

    def test_edit_custom_responses(self):
        processor = MongoProcessor()
        jsondata = {"type": "section",
                    "text": {
                        "text": "Make a bet",
                        "type": "mrkdwn",
                        "accessory": {"type": "button",
                                      "initial_date": "2019-05-21",
                                      "placeholder": {"type": "plain_text",
                                                      "text": "Select a date"}}}}
        responses = list(processor.get_response("utter_custom", "tests"))
        processor.edit_custom_response(responses[0]["_id"], jsondata, name="utter_custom", bot="tests", user="testUser")
        responses = list(processor.get_response("utter_custom", "tests"))
        assert any(response['value']['custom'] == jsondata and response['type'] == "json"
                   for response in responses if "custom" in response['value'])

    def test_get_session_config(self):
        processor = MongoProcessor()
        session_config = processor.get_session_config("tests")
        assert session_config
        assert all(
            session_config[key] for key in ["sesssionExpirationTime", "carryOverSlots"]
        )

    def test_update_session_config(self):
        processor = MongoProcessor()
        session_config = processor.get_session_config("tests")
        assert session_config
        assert all(
            session_config[key] for key in ["sesssionExpirationTime", "carryOverSlots"]
        )
        id_updated = processor.add_session_config(
            id=session_config["_id"],
            sesssionExpirationTime=30,
            carryOverSlots=False,
            bot="tests",
            user="testUser",
        )
        assert id_updated == session_config["_id"]
        session_config = processor.get_session_config("tests")
        assert session_config["sesssionExpirationTime"] == 30
        assert session_config["carryOverSlots"] is False

    def test_add_session_config_duplicate(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_session_config(
                sesssionExpirationTime=30,
                carryOverSlots=False,
                bot="tests",
                user="testUser",
            )

    def test_add_session_config_empty_id(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_session_config(
                id="",
                sesssionExpirationTime=30,
                carryOverSlots=False,
                bot="tests",
                user="testUser",
            )

    def test_train_on_multiflow_story(self):
        bot = "tests"
        user = "testUser"
        processor = MongoProcessor()
        list(processor.add_training_example(["How is the sky today?"], intent="query", bot=bot, user=user,
                                            is_integration=False))
        list(processor.add_training_example(["Will it rain?"], intent="more_queries", bot=bot, user=user,
                                            is_integration=False))
        list(processor.add_training_example(["Bubye, will see you!"], intent="goodbye", bot=bot, user=user,
                                            is_integration=False))

        processor.add_response({"text": "It is Sunny!"}, "utter_query", bot, user)
        processor.add_response({"text": "See you, Bye!"}, "utter_goodbye", bot, user)
        processor.add_response({"text": "No, it won't rain."}, "utter_more_queries", bot, user)

        steps = [
            {"step": {"name": "query", "type": "INTENT", "node_id": "1", "component_id": "61m96mPGu2VexybDeVg1dLyH"},
             "connections": [
                 {"name": "utter_query", "type": "BOT", "node_id": "2", "component_id": "61uaImwNrsJI1pVphl8mZh20"}]
             },
            {"step": {"name": "utter_query", "type": "BOT", "node_id": "2", "component_id": "61uaImwNrsJI1pVphl8mZh20"},
             "connections": [
                 {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "62By0VXVLpUNDNPqkr5vRRzm"},
                 {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "62N9BCfSKVYOKoBivGhWDRHC"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "62N9BCfSKVYOKoBivGhWDRHC"},
             "connections": [
                 {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "62uzXd9Pj5a9tEbVBkMuVn3o"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5",
                      "component_id": "62uzXd9Pj5a9tEbVBkMuVn3o"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                      "component_id": "62ib6tlbgIGth8vBSwSYFvbS"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3",
                      "component_id": "62By0VXVLpUNDNPqkr5vRRzm"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                              "component_id": "62ib6tlbgIGth8vBSwSYFvbS"}]
             }
        ]

        story_dict = {'name': "story for training", 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        story = MultiflowStories.objects(block_name="story for training", bot=bot).get()
        assert len(story.events) == 6

    def test_add_session_config(self):
        processor = MongoProcessor()
        id_add = processor.add_session_config(
            sesssionExpirationTime=30, carryOverSlots=False, bot="test", user="testUser"
        )
        assert id_add

    def test_train_model(self):
        model = train_model_for_bot("tests")
        assert model
        folder = os.path.join("models/tests", '*.tar.gz')
        assert len(list(glob.glob(folder))) == 1

    def test_train_model_validate_deletion(self, monkeypatch):
        file = glob.glob(os.path.join("models/tests", '*.tar.gz'))[0]
        for i in range(7):
            shutil.copy(file, os.path.join("models/tests", "old_model", f"{i}.tar.gz"))

        def _mock_train(*args, **kwargs):
            ob = object()
            ob.model = file
            return ob

        with patch("rasa.train") as mock_tr:
            mock_tr.side_effect = _mock_train
            model = train_model_for_bot("tests")
        assert model
        folder = os.path.join("models/tests", '*.tar.gz')
        assert len(list(glob.glob(folder))) == 1
        folder = os.path.join("models/tests", "old_model", "*.tar.gz")
        assert len(list(glob.glob(folder))) == 4

    def test_start_training_done(self, monkeypatch):
        model_path = start_training("tests", "testUser")
        assert model_path
        model_training = ModelTraining.objects(bot="tests", status="Done")
        assert model_training.__len__() == 1
        assert model_training.first().model_path == model_path

    def test_start_training_done_with_intrumentation(self):
        with patch.dict(Utility.environment["apm"], {"enable": True, 'service_name': 'kairon'}, clear=True):
            processor = MongoProcessor()
            loop = asyncio.get_event_loop()
            loop.run_until_complete(processor.save_from_path(
                "./tests/testing_data/initial", bot="test_initial", user="testUser"
            ))

            model_path = start_training("test_initial", "testUser")
            assert model_path
            model_training = ModelTraining.objects(bot="test_initial", status="Done")
            assert model_training.__len__() == 1
            assert model_training.first().model_path == model_path

    def test_start_training_fail(self):
        start_training("test", "testUser")
        model_training = ModelTraining.objects(bot="test", status="Fail")
        assert model_training.__len__() == 1
        assert model_training.first().exception in str("Training data does not exists!")

    @patch.object(litellm, "aembedding", autospec=True)
    @patch("kairon.shared.rest_client.AioRestClient.request", autospec=True)
    @patch("kairon.shared.account.processor.AccountProcessor.get_bot", autospec=True)
    @patch("kairon.train.train_model_for_bot", autospec=True)
    def test_start_training_with_llm_faq(
            self, mock_train, mock_bot, mock_vec_client, mock_openai
    ):
        bot = "tests"
        user = "testUser"
        value = "nupurk"
        CognitionData(
            data="Welcome! Are you completely new to programming? If not then we presume you will be looking for information about why and how to get started with Python",
            bot=bot, user=user).save()
        CognitionData(
            data="Java is a high-level, class-based, object-oriented programming language that is designed to have as few implementation dependencies as possible.",
            bot=bot, user=user).save()
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key=value,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()
        MongoProcessor().add_action(GPT_LLM_FAQ, bot, user, False, ActionType.prompt_action.value)
        settings = BotSettings.objects(bot=bot).get()
        settings.llm_settings = LLMSettings(enable_faq=True)
        settings.save()
        embedding = list(np.random.random(1532))
        mock_openai.return_value = {'data': [{'embedding': embedding}, {'embedding': embedding}]}
        mock_bot.return_value = {"account": 1}
        mock_train.return_value = f"/models/{bot}"
        start_training(bot, user)
        settings = BotSettings.objects(bot=bot).get()
        settings.llm_settings = LLMSettings(enable_faq=False)
        settings.save()
        log = Metering.objects(bot=bot, metric_type=MetricType.faq_training.value).get()
        assert log["faq"] == 2
        search_event = StoryEvents(name=DEFAULT_NLU_FALLBACK_INTENT_NAME, type=UserUttered.type_name)
        rule = Rules.objects(bot=bot, events__match=search_event, status=True).get()
        assert rule.events == [
            StoryEvents(name=RULE_SNIPPET_ACTION_NAME, type=ActionExecuted.type_name),
            StoryEvents(name="nlu_fallback", type=UserUttered.type_name),
            StoryEvents(name='utter_please_rephrase', type=ActionExecuted.type_name)
        ]

    def test_add_endpoints(self):
        processor = MongoProcessor()
        config = {}
        processor.add_endpoints(config, bot="tests", user="testUser")
        endpoint = processor.get_endpoints("tests")
        assert endpoint.get("bot_endpoint") is None
        assert endpoint.get("action_endpoint") is None
        assert endpoint.get("tracker") is None

    def test_add_endpoints_add_bot_endpoint_empty_url(self):
        processor = MongoProcessor()
        config = {"bot_endpoint": {"url": ""}}
        with pytest.raises(AppException):
            processor.add_endpoints(config, bot="tests1", user="testUser")
            endpoint = processor.get_endpoints("tests1")
            assert endpoint.get("bot_endpoint") is None
            assert endpoint.get("action_endpoint") is None
            assert endpoint.get("tracker") is None

    def test_add_endpoints_add_bot_endpoint(self):
        processor = MongoProcessor()
        config = {"bot_endpoint": {"url": "http://localhost:5000/"}}
        processor.add_endpoints(config, bot="tests1", user="testUser")
        endpoint = processor.get_endpoints("tests1")
        assert endpoint["bot_endpoint"].get("url") == "http://localhost:5000/"
        assert endpoint.get("action_endpoint") is None
        assert endpoint.get("tracker") is None

    def test_add_endpoints_add_action_endpoint_empty_url(self):
        processor = MongoProcessor()
        config = {"action_endpoint": {"url": ""}}
        with pytest.raises(AppException):
            processor.add_endpoints(config, bot="tests2", user="testUser")
            endpoint = processor.get_endpoints("tests2")
            assert endpoint.get("bot_endpoint") is None
            assert endpoint.get("action_endpoint") is None
            assert endpoint.get("tracker") is None

    def test_add_endpoints_add_action_endpoint(self):
        processor = MongoProcessor()
        config = {"action_endpoint": {"url": "http://localhost:5000/"}}
        processor.add_endpoints(config, bot="tests2", user="testUser")
        endpoint = processor.get_endpoints("tests2")
        assert endpoint.get("bot_endpoint") is None
        assert endpoint.get("action_endpoint").get("url") == "http://localhost:5000/"
        assert endpoint.get("tracker") is None

    def test_add_endpoints_add_history_endpoint(self):
        processor = MongoProcessor()
        config = {
            "history_endpoint": {
                "url": "http://localhost:27017/",
                "token": "conversations"
            }
        }
        processor.add_endpoints(config, bot="tests3", user="testUser")
        endpoint = processor.get_endpoints("tests3")
        assert endpoint.get("bot_endpoint") is None
        assert endpoint.get("action_endpoint") is None
        assert endpoint.get("history_endpoint").get("url") == "http://localhost:27017/"
        assert endpoint.get("history_endpoint").get("token") == "conversations"

    def test_get_endpoints_mask_history_server_token(self):
        processor = MongoProcessor()
        config = {
            "history_endpoint": {
                "url": "http://localhost:27017/",
                "token": "conversations"
            }
        }
        processor.add_endpoints(config, bot="tests3", user="testUser")
        endpoint = processor.get_endpoints("tests3", mask_characters=True)
        assert endpoint.get("bot_endpoint") is None
        assert endpoint.get("action_endpoint") is None
        assert endpoint.get("history_endpoint").get("url") == "http://localhost:27017/"
        assert endpoint.get("history_endpoint").get("token") == "conversati***"

    def test_get_history_server_endpoint(self):
        processor = MongoProcessor()
        endpoint = processor.get_history_server_endpoint("tests3")
        assert endpoint.get("url") == "http://localhost:27017/"
        assert endpoint.get("token") == "conversations"
        assert endpoint.get("type") == 'user'

    def test_get_kairon_history_server_endpoint(self):
        processor = MongoProcessor()
        endpoint = processor.get_history_server_endpoint("test_bot")
        assert endpoint.get("url") == "http://localhost:8083"
        assert endpoint.get("token")
        assert endpoint.get("type") == 'kairon'

    def test_update_endpoints(self):
        processor = MongoProcessor()
        config = {
            "action_endpoint": {"url": "http://localhost:8000/"},
            "bot_endpoint": {"url": "http://localhost:5000/"},
            "history_endpoint": {
                "url": "http://localhost:27019/",
                "token": "kairon-history-user",
            },
        }
        processor.add_endpoints(config, bot="tests", user="testUser")
        endpoint = processor.get_endpoints("tests")
        assert endpoint.get("bot_endpoint").get("url") == "http://localhost:5000/"
        assert endpoint.get("action_endpoint").get("url") == "http://localhost:8000/"
        assert endpoint.get("history_endpoint").get("url") == "http://localhost:27019/"
        assert endpoint.get("history_endpoint").get("token") == "kairon-history-user"

    def test_update_endpoints_token_less_than_8_chars(self):
        processor = MongoProcessor()
        config = {
            "action_endpoint": {"url": "http://localhost:8000/"},
            "bot_endpoint": {"url": "http://localhost:5000/"},
            "history_endpoint": {
                "url": "http://localhost:27019/",
                "token": "kairon",
            },
        }
        with pytest.raises(AppException, match='token must contain at least 8 characters'):
            processor.add_endpoints(config, bot="tests", user="testUser")
        endpoint = processor.get_endpoints("tests")
        assert endpoint.get("bot_endpoint").get("url") == "http://localhost:5000/"
        assert endpoint.get("action_endpoint").get("url") == "http://localhost:8000/"
        assert endpoint.get("history_endpoint").get("url") == "http://localhost:27019/"
        assert endpoint.get("history_endpoint").get("token") == "kairon-history-user"

    def test_update_endpoints_token_with_space(self):
        processor = MongoProcessor()
        config = {
            "action_endpoint": {"url": "http://localhost:8000/"},
            "bot_endpoint": {"url": "http://localhost:5000/"},
            "history_endpoint": {
                "url": "http://localhost:27019/",
                "token": "kairon token",
            },
        }
        with pytest.raises(AppException, match='token cannot contain spaces'):
            processor.add_endpoints(config, bot="tests", user="testUser")
        endpoint = processor.get_endpoints("tests")
        assert endpoint.get("bot_endpoint").get("url") == "http://localhost:5000/"
        assert endpoint.get("action_endpoint").get("url") == "http://localhost:8000/"
        assert endpoint.get("history_endpoint").get("url") == "http://localhost:27019/"
        assert endpoint.get("history_endpoint").get("token") == "kairon-history-user"

    def test_update_endpoints_any(self):
        processor = MongoProcessor()
        config = {
            "action_endpoint": {"url": "http://127.0.0.1:8000/"},
            "bot_endpoint": {"url": "http://127.0.0.1:5000/"},
        }
        processor.add_endpoints(config, bot="tests", user="testUser")
        endpoint = processor.get_endpoints("tests")
        assert endpoint.get("bot_endpoint").get("url") == "http://127.0.0.1:5000/"
        assert endpoint.get("action_endpoint").get("url") == "http://127.0.0.1:8000/"
        assert endpoint.get("history_endpoint").get("url") == "http://localhost:27019/"
        assert endpoint.get("history_endpoint").get("token") == "kairon-history-user"

    def test_delete_endpoints(self):
        processor = MongoProcessor()
        config = {
            "bot_endpoint": {"url": "http://127.0.0.1:5000/"},
            "action_endpoint": {"url": "http://127.0.0.1:8000/"},
            "history_endpoint": {
                "url": "http://localhost:27019/",
                "token": "kairon-history-user",
            },
        }
        processor.add_endpoints(config, bot="test_delete_endpoint", user="testUser")

        processor.delete_endpoint('test_delete_endpoint', ENDPOINT_TYPE.BOT_ENDPOINT.value)
        endpoint = processor.get_endpoints("test_delete_endpoint")
        assert not endpoint.get(ENDPOINT_TYPE.BOT_ENDPOINT)
        assert endpoint.get("action_endpoint").get("url") == "http://127.0.0.1:8000/"
        assert endpoint.get("history_endpoint").get("url") == "http://localhost:27019/"

        processor.delete_endpoint('test_delete_endpoint', ENDPOINT_TYPE.ACTION_ENDPOINT.value)
        endpoint = processor.get_endpoints("test_delete_endpoint")
        assert not endpoint.get(ENDPOINT_TYPE.BOT_ENDPOINT)
        assert not endpoint.get(ENDPOINT_TYPE.ACTION_ENDPOINT)
        assert endpoint.get("history_endpoint").get("url") == "http://localhost:27019/"

        processor.delete_endpoint('test_delete_endpoint', ENDPOINT_TYPE.HISTORY_ENDPOINT.value)
        endpoint = processor.get_endpoints("test_delete_endpoint")
        assert not endpoint.get(ENDPOINT_TYPE.BOT_ENDPOINT.value)
        assert not endpoint.get(ENDPOINT_TYPE.ACTION_ENDPOINT.value)
        assert not endpoint.get(ENDPOINT_TYPE.HISTORY_ENDPOINT.value)

    def test_delete_endpoints_none(self):
        processor = MongoProcessor()
        config = {
            "bot_endpoint": {"url": "http://127.0.0.1:5000/"},
            "action_endpoint": {"url": "http://127.0.0.1:8000/"},
            "history_endpoint": {
                "url": "http://localhost:27019/",
                "token": "kairon-history-user",
            },
        }
        processor.add_endpoints(config, bot="test_delete_endpoint", user="testUser")

        with pytest.raises(AppException, match='endpoint_type is required for deletion'):
            processor.delete_endpoint('test_delete_endpoint', None)

    def test_delete_endpoints_not_exists(self):
        processor = MongoProcessor()
        with pytest.raises(AppException) as e:
            processor.delete_endpoint('test_delete_endpoints_not_exists', ENDPOINT_TYPE.BOT_ENDPOINT.value)
        assert str(e).__contains__("No Endpoint configured")

    def test_delete_endpoints_type_not_exists(self):
        processor = MongoProcessor()
        config = {
            "bot_endpoint": {"url": "http://127.0.0.1:5000/"},
        }
        processor.add_endpoints(config, bot="test_delete_endpoints_type_not_exists", user="testUser")

        with pytest.raises(AppException, match='Endpoint not configured'):
            processor.delete_endpoint('test_delete_endpoints_type_not_exists', ENDPOINT_TYPE.ACTION_ENDPOINT.value)

        processor.delete_endpoint('test_delete_endpoints_type_not_exists', ENDPOINT_TYPE.BOT_ENDPOINT.value)
        endpoint = processor.get_endpoints("test_delete_endpoints_type_not_exists")
        assert not endpoint.get(ENDPOINT_TYPE.BOT_ENDPOINT.value)

        with pytest.raises(AppException, match='Endpoint not configured') as e:
            processor.delete_endpoint('test_delete_endpoints_type_not_exists', ENDPOINT_TYPE.HISTORY_ENDPOINT.value)

    def test_get_kairon_history_server_endpoint_none_configured(self):
        processor = MongoProcessor()
        Utility.environment['history_server']['url'] = None
        with pytest.raises(AppException, match='No history server endpoint configured'):
            endpoint = processor.get_history_server_endpoint("test_bot")

    def test_download_data_files(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        file = processor.download_files("tests", "user@integration.com")
        assert file.endswith(".zip")

    def test_download_data_files_multiflow_stories(self, monkeypatch):
        from zipfile import ZipFile
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        story_name = "multiflow_story_STORY_download_data_files"
        steps = [
            {"step": {"name": "asking", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_asking", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_asking", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "moodyy", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foodyy", "type": "HTTP_ACTION", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foodyy", "type": "HTTP_ACTION", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_foodyy", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_foodyy", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_moodyy", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "moodyy", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_moodyy", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6', "flow_type": 'STORY'}, {"node_id": "5", "flow_type": 'RULE'}]
        story_dict = {'name': story_name, 'steps': steps, "metadata": metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, "tests_download", "user@integration.com")

        steps_story = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "deny", "type": "INTENT"},
            {"name": "utter_deny", "type": "BOT"}
        ]
        story_dict_one = {'name': "story for download", 'steps': steps_story, 'type': 'STORY',
                          'template_type': 'CUSTOM'}
        processor.add_complex_story(story_dict_one, "tests_download", "user@integration.com")

        steps_rule = [
            {"name": "food", "type": "INTENT"},
            {"name": "utter_food", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        rule_dict = {'name': "rule for download", 'steps': steps_rule, 'type': 'RULE', 'template_type': 'RULE'}
        processor.add_complex_story(rule_dict, "tests_download", "user@integration.com")

        file = processor.download_files("tests_download", "user@integration.com")
        assert file.endswith(".zip")
        zip_file = ZipFile(file, mode='r')
        assert zip_file.getinfo('multiflow_stories.yml')
        assert zip_file.getinfo('data/stories.yml')
        file_info_multiflow_stories = zip_file.getinfo('multiflow_stories.yml')
        file_multiflow_stories = zip_file.read(file_info_multiflow_stories)
        assert file_multiflow_stories == b"multiflow_story:\n- block_name: multiflow_story_story_download_data_files\n  end_checkpoints: []\n  events:\n  - connections:\n    - component_id: 63uNJw1QvpQZvIpP07dxnmFU\n      name: utter_asking\n      node_id: '2'\n      type: BOT\n    step:\n      component_id: 637d0j9GD059jEwt2jPnlZ7I\n      name: asking\n      node_id: '1'\n      type: INTENT\n  - connections:\n    - component_id: 633w6kSXuz3qqnPU571jZyCv\n      name: moodyy\n      node_id: '3'\n      type: INTENT\n    - component_id: 63WKbWs5K0ilkujWJQpXEXGD\n      name: foodyy\n      node_id: '4'\n      type: HTTP_ACTION\n    step:\n      component_id: 63uNJw1QvpQZvIpP07dxnmFU\n      name: utter_asking\n      node_id: '2'\n      type: BOT\n  - connections:\n    - component_id: 63gm5BzYuhC1bc6yzysEnN4E\n      name: utter_foodyy\n      node_id: '5'\n      type: BOT\n    step:\n      component_id: 63WKbWs5K0ilkujWJQpXEXGD\n      name: foodyy\n      node_id: '4'\n      type: HTTP_ACTION\n  - connections: []\n    step:\n      component_id: 63gm5BzYuhC1bc6yzysEnN4E\n      name: utter_foodyy\n      node_id: '5'\n      type: BOT\n  - connections: []\n    step:\n      component_id: 634a9bwPPj2y3zF5HOVgLiXx\n      name: utter_moodyy\n      node_id: '6'\n      type: BOT\n  - connections:\n    - component_id: 634a9bwPPj2y3zF5HOVgLiXx\n      name: utter_moodyy\n      node_id: '6'\n      type: BOT\n    step:\n      component_id: 633w6kSXuz3qqnPU571jZyCv\n      name: moodyy\n      node_id: '3'\n      type: INTENT\n  metadata:\n  - flow_type: STORY\n    node_id: '6'\n  - flow_type: RULE\n    node_id: '5'\n  start_checkpoints:\n  - STORY_START\n  template_type: CUSTOM\n"
        file_stories = zip_file.getinfo('data/stories.yml')
        stories = zip_file.read(file_stories)
        assert stories == b'version: "3.1"\nstories:\n- story: story for download\n  steps:\n  - intent: greet\n  - action: utter_greet\n  - intent: deny\n  - action: utter_deny\n'
        file_rules = zip_file.getinfo('data/rules.yml')
        rules = zip_file.read(file_rules)
        assert rules == b'version: "3.1"\nrules:\n- rule: rule for download\n  steps:\n  - intent: food\n  - action: utter_food\n  - action: utter_cheer_up\n'
        zip_file.close()

        file_two = processor.download_files("tests_download", "user@integration.com", True)
        assert file_two.endswith(".zip")
        zip_file = ZipFile(file_two, mode='r')
        assert zip_file.getinfo('data/stories.yml')
        assert zip_file.getinfo('data/rules.yml')
        file_info_stories = zip_file.getinfo('data/stories.yml')
        file_info_rules = zip_file.getinfo('data/rules.yml')
        file_stories = zip_file.read(file_info_stories)
        file_rules = zip_file.read(file_info_rules)
        multiflow_story = zip_file.getinfo('multiflow_stories.yml')
        file_multiflow_story = zip_file.read(multiflow_story)
        assert file_stories == b'version: "3.1"\nstories:\n- story: story for download\n  steps:\n  - intent: greet\n  - action: utter_greet\n  - intent: deny\n  - action: utter_deny\n- story: multiflow_story_story_download_data_files_2\n  steps:\n  - intent: asking\n  - action: utter_asking\n  - intent: moodyy\n  - action: utter_moodyy\n'
        assert file_rules == b'version: "3.1"\nrules:\n- rule: rule for download\n  steps:\n  - intent: food\n  - action: utter_food\n  - action: utter_cheer_up\n- rule: multiflow_story_story_download_data_files_1\n  steps:\n  - intent: asking\n  - action: utter_asking\n  - action: foodyy\n  - action: utter_foodyy\n'
        assert file_multiflow_story == b"multiflow_story:\n- block_name: multiflow_story_story_download_data_files\n  end_checkpoints: []\n  events:\n  - connections:\n    - component_id: 63uNJw1QvpQZvIpP07dxnmFU\n      name: utter_asking\n      node_id: '2'\n      type: BOT\n    step:\n      component_id: 637d0j9GD059jEwt2jPnlZ7I\n      name: asking\n      node_id: '1'\n      type: INTENT\n  - connections:\n    - component_id: 633w6kSXuz3qqnPU571jZyCv\n      name: moodyy\n      node_id: '3'\n      type: INTENT\n    - component_id: 63WKbWs5K0ilkujWJQpXEXGD\n      name: foodyy\n      node_id: '4'\n      type: HTTP_ACTION\n    step:\n      component_id: 63uNJw1QvpQZvIpP07dxnmFU\n      name: utter_asking\n      node_id: '2'\n      type: BOT\n  - connections:\n    - component_id: 63gm5BzYuhC1bc6yzysEnN4E\n      name: utter_foodyy\n      node_id: '5'\n      type: BOT\n    step:\n      component_id: 63WKbWs5K0ilkujWJQpXEXGD\n      name: foodyy\n      node_id: '4'\n      type: HTTP_ACTION\n  - connections: []\n    step:\n      component_id: 63gm5BzYuhC1bc6yzysEnN4E\n      name: utter_foodyy\n      node_id: '5'\n      type: BOT\n  - connections: []\n    step:\n      component_id: 634a9bwPPj2y3zF5HOVgLiXx\n      name: utter_moodyy\n      node_id: '6'\n      type: BOT\n  - connections:\n    - component_id: 634a9bwPPj2y3zF5HOVgLiXx\n      name: utter_moodyy\n      node_id: '6'\n      type: BOT\n    step:\n      component_id: 633w6kSXuz3qqnPU571jZyCv\n      name: moodyy\n      node_id: '3'\n      type: INTENT\n  metadata:\n  - flow_type: STORY\n    node_id: '6'\n  - flow_type: RULE\n    node_id: '5'\n  start_checkpoints:\n  - STORY_START\n  template_type: CUSTOM\n"
        zip_file.close()

    def test_download_data_files_prompt_action(self, monkeypatch):
        from zipfile import ZipFile
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        BotSettings(bot="tests_download_prompt", user="user@integration.com",
                    llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'prompt_action_with_default_values',
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}
                                   ],
                   "set_slots": [{"name": "gpt_result", "value": "${data}", "evaluation_type": "expression"},
                                 {"name": "gpt_result_type", "value": "${data.type}", "evaluation_type": "script"}],
                   "dispatch_response": False
                   }
        processor.add_prompt_action(request, "tests_download_prompt", "user@integration.com")
        file = processor.download_files("tests_download_prompt", "user@integration.com")
        assert file.endswith(".zip")
        zip_file = ZipFile(file, mode='r')
        assert zip_file.getinfo('actions.yml')
        file_info_actions = zip_file.getinfo('actions.yml')
        file_content_actions = zip_file.read(file_info_actions)
        expected_content = b"name: System Prompt\n    source: static\n    type: system\n  - is_enabled: true"
        assert file_content_actions.__contains__(expected_content)
        zip_file.close()

    def test_download_data_files_empty_data(self, monkeypatch):
        from zipfile import ZipFile
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()

        file = processor.download_files("tests_download_empty_data", "user@integration.com")
        assert file.endswith(".zip")
        zip_file = ZipFile(file, mode='r')
        assert zip_file.filelist.__len__() == 9
        assert zip_file.getinfo('data/stories.yml')
        assert zip_file.getinfo('data/rules.yml')
        file_info_stories = zip_file.getinfo('data/stories.yml')
        file_info_rules = zip_file.getinfo('data/rules.yml')
        file_content_stories = zip_file.read(file_info_stories)
        file_content_rules = zip_file.read(file_info_rules)
        assert file_content_stories == b'version: "3.1"\n'
        assert file_content_rules == b'version: "3.1"\n'
        zip_file.close()

    def test_download_data_files_multiflow_stories_with_actions(self, monkeypatch):
        from zipfile import ZipFile
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        story_name = "multiflow_story_STORY_download_data_files_with_actions"
        steps = [
            {"step": {"name": "asking", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_asking", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_asking", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "moodyy", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foodyy", "type": "HTTP_ACTION", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foodyy", "type": "HTTP_ACTION", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_foody", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_foody", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_moodyy", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "moodyy", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_moodyy", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6', "flow_type": 'STORY'}, {"node_id": "5", "flow_type": 'RULE'}]
        story_dict = {'name': story_name, 'steps': steps, "metadata": metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, "tests_download_again", "user@integration.com")
        file = processor.download_files("tests_download_again", "user@integration.com", True)
        assert file.endswith(".zip")
        zip_file = ZipFile(file, mode='r')
        assert zip_file.getinfo('data/stories.yml')
        assert zip_file.getinfo('data/rules.yml')
        file_info_stories = zip_file.getinfo('data/stories.yml')
        file_info_rules = zip_file.getinfo('data/rules.yml')
        file_content_stories = zip_file.read(file_info_stories)
        file_content_rules = zip_file.read(file_info_rules)
        print(file_content_stories)
        print(file_content_rules)

        assert file_content_stories == b'version: "3.1"\nstories:\n- story: multiflow_story_story_download_data_files_with_actions_2\n  steps:\n  - intent: asking\n  - action: utter_asking\n  - intent: moodyy\n  - action: utter_moodyy\n'
        assert file_content_rules == b'version: "3.1"\nrules:\n- rule: multiflow_story_story_download_data_files_with_actions_1\n  steps:\n  - intent: asking\n  - action: utter_asking\n  - action: foodyy\n  - action: utter_foody\n'
        zip_file.close()

    def test_download_data_files_with_actions(self, monkeypatch):
        from zipfile import ZipFile

        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'tests', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }
        #add a http action to the bot
        act_config = HttpActionConfig()
        act_config.action_name = "my_http_action"
        act_config.bot = 'tests'
        act_config.user = 'user@integration.com'
        act_config.status = True
        act_config.http_url = "https://jsonplaceholder.typicode.com/posts/1"
        act_config.request_method = "GET"
        act_config.content_type = "json"
        act_config.response = HttpActionResponse(value='zxcvb')
        act_config.save()

        action = Actions()
        action.name = 'my_http_action'
        action.bot = 'tests'
        action.user = 'user@integration.com'
        action.status = True
        action.type = ActionType.http_action.value
        action.save()

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        file_path = processor.download_files("tests", "user@integration.com")

        assert file_path.endswith(".zip")
        zip_file = ZipFile(file_path, mode='r')
        assert zip_file.filelist.__len__() == 10
        assert zip_file.getinfo('chat_client_config.yml')
        assert zip_file.getinfo('config.yml')
        assert zip_file.getinfo('domain.yml')
        assert zip_file.getinfo('actions.yml')
        assert zip_file.getinfo('multiflow_stories.yml')
        assert zip_file.getinfo('bot_content.yml')
        assert zip_file.getinfo('data/stories.yml')
        assert zip_file.getinfo('data/rules.yml')
        assert zip_file.getinfo('data/nlu.yml')
        file_info = zip_file.getinfo('actions.yml')
        file_content = zip_file.read(file_info)
        actual_actions = file_content.decode(encoding='utf-8')
        actual_actions_dict = yaml.safe_load(actual_actions)
        assert actual_actions_dict == {'http_action': [
            {
                'action_name': 'my_http_action',
                'content_type': 'json',
                'http_url': 'https://jsonplaceholder.typicode.com/posts/1',
                'params_list': [],
                'request_method': 'GET',
                'response': {
                    'dispatch': True,
                    'dispatch_type': 'text',
                    'evaluation_type': 'expression',
                    'value': 'zxcvb',
                },
                'headers': [],
                'set_slots': []
            }]}
        zip_file.close()

    def test_load_action_configurations(self):
        processor = MongoProcessor()
        action_config = processor.load_action_configurations("tests")
        assert action_config == {'http_action': [
            {
                'action_name': 'my_http_action',
                'content_type': 'json',
                'http_url': 'https://jsonplaceholder.typicode.com/posts/1',
                'request_method': 'GET',
                'response': {
                    'dispatch': True,
                    'dispatch_type': 'text',
                    'evaluation_type': 'expression',
                    'value': 'zxcvb',
                },
            }
        ], 'jira_action': [], 'email_action': [], 'zendesk_action': [],
                                 'form_validation_action': [], 'slot_set_action': [], 'google_search_action': [],
                                 'pipedrive_leads_action': [], 'two_stage_fallback': [], 'prompt_action': [],
                                 'razorpay_action': [], 'pyscript_action': [], 'database_action': [], 'live_agent_action': []}

    def test_get_utterance_from_intent(self):
        processor = MongoProcessor()
        response = processor.get_utterance_from_intent("deny", "tests")
        assert response[0] == "utter_goodbye"
        assert response[1] == UTTERANCE_TYPE.BOT

    def test_get_utterance_from_empty_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.get_utterance_from_intent("", "tests")

    def test_get_stories(self):
        processor = MongoProcessor()
        stories = list(processor.get_stories("tests"))
        assert stories.__len__() == 8
        assert stories[0]['name'] == 'happy path'
        assert stories[0]['type'] == 'STORY'
        assert stories[0]['steps'][0]['name'] == 'greet'
        assert stories[0]['steps'][0]['type'] == 'INTENT'
        assert stories[0]['steps'][1]['name'] == 'utter_greet'
        assert stories[0]['steps'][1]['type'] == 'BOT'
        assert stories[0]['template_type'] == 'CUSTOM'

    def test_get_multiflow_stories(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greeting", "type": "INTENT", "node_id": "1", "component_id": "63bLGgJEl8dz0axb9FvrWvHq"},
             "connections": [
                 {"name": "utter_hiii", "type": "BOT", "node_id": "2", "component_id": "63IjWdIIpHgT36sJXpqnS7Mx"}]
             },
            {"step": {"name": "utter_hiii", "type": "BOT", "node_id": "2", "component_id": "63IjWdIIpHgT36sJXpqnS7Mx"},
             "connections": [
                 {"name": "record", "type": "INTENT", "node_id": "3", "component_id": "634nMJ9hAAtbgr6Wn1Fhm89D"},
                 {"name": "id", "type": "INTENT", "node_id": "4", "component_id": "632o76BgDW2eo3JOqDGk9RQW"}]
             },
            {"step": {"name": "id", "type": "INTENT", "node_id": "4", "component_id": "632o76BgDW2eo3JOqDGk9RQW"},
             "connections": [
                 {"name": "utter_id", "type": "BOT", "node_id": "5", "component_id": "637d13it2UNSslxVSbWZjBqO"}]
             },
            {"step": {"name": "utter_id", "type": "BOT", "node_id": "5", "component_id": "637d13it2UNSslxVSbWZjBqO"},
             "connections": None
             },
            {"step": {"name": "utter_record", "type": "BOT", "node_id": "6",
                      "component_id": "63e63sU5PHRQnnINYPZitORt"},
             "connections": None
             },
            {"step": {"name": "record", "type": "INTENT", "node_id": "3", "component_id": "634nMJ9hAAtbgr6Wn1Fhm89D"},
             "connections": [
                 {"name": "utter_record", "type": "BOT", "node_id": "6", "component_id": "63e63sU5PHRQnnINYPZitORt"}]
             }
        ]
        story_dict = {"name": "a different story", 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, "tester", "TesterUser")
        stories = list(processor.get_multiflow_stories("tester"))
        assert stories.__len__() == 1
        assert stories[0]['name'] == 'a different story'
        assert stories[0]['type'] == 'MULTIFLOW'
        print(stories[0]['steps'])
        assert stories[0]['steps'] == [
            {'step': {'name': 'greeting', 'type': 'INTENT', 'node_id': '1', 'component_id': '63bLGgJEl8dz0axb9FvrWvHq'},
             'connections': [
                 {'name': 'utter_hiii', 'type': 'BOT', 'node_id': '2', 'component_id': '63IjWdIIpHgT36sJXpqnS7Mx'}]},
            {'step': {'name': 'utter_hiii', 'type': 'BOT', 'node_id': '2', 'component_id': '63IjWdIIpHgT36sJXpqnS7Mx'},
             'connections': [
                 {'name': 'record', 'type': 'INTENT', 'node_id': '3', 'component_id': '634nMJ9hAAtbgr6Wn1Fhm89D'},
                 {'name': 'id', 'type': 'INTENT', 'node_id': '4', 'component_id': '632o76BgDW2eo3JOqDGk9RQW'}]},
            {'step': {'name': 'id', 'type': 'INTENT', 'node_id': '4', 'component_id': '632o76BgDW2eo3JOqDGk9RQW'},
             'connections': [
                 {'name': 'utter_id', 'type': 'BOT', 'node_id': '5', 'component_id': '637d13it2UNSslxVSbWZjBqO'}]},
            {'step': {'name': 'utter_id', 'type': 'BOT', 'node_id': '5', 'component_id': '637d13it2UNSslxVSbWZjBqO'},
             'connections': []}, {'step': {'name': 'utter_record', 'type': 'BOT', 'node_id': '6',
                                           'component_id': '63e63sU5PHRQnnINYPZitORt'},
                                  'connections': []},
            {'step': {'name': 'record', 'type': 'INTENT', 'node_id': '3', 'component_id': '634nMJ9hAAtbgr6Wn1Fhm89D'},
             'connections': [
                 {'name': 'utter_record', 'type': 'BOT', 'node_id': '6', 'component_id': '63e63sU5PHRQnnINYPZitORt'}]}]

    def test_get_multiflow_stories_with_STORY_metadata(self):
        processor = MongoProcessor()
        story_name = "get_multiflow_story_STORY"
        bot = "test_get_path_story"
        user = "test_get_user_path_story"
        steps = [
            {"step": {"name": "asker", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_ask", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_ask", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "moody", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foody", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foody", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_food", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_food", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "moody", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6', "flow_type": 'STORY'}, {"node_id": "5", "flow_type": 'STORY'}]
        story_dict = {'name': story_name, 'steps': steps, "metadata": metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = list(processor.get_multiflow_stories("test_get_path_story"))
        assert multiflow_story.__len__() == 1
        assert multiflow_story[0]['metadata'] == [{'node_id': '6', 'flow_type': 'STORY'},
                                                  {'node_id': '5', 'flow_type': 'STORY'}]
        assert multiflow_story[0]['name'] == 'get_multiflow_story_story'

    def test_get_multiflow_stories_with_RULE_metadata(self):
        processor = MongoProcessor()
        story_name = "get_multiflow_story_RULE"
        bot = "test_get_path_rule"
        user = "test_get_user_path_rule"
        steps = [
            {"step": {"name": "asker", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_asker", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_asker", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "moody", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foody", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foody", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_foody", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_foody", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_moody", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "moody", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_moody", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6', "flow_type": 'RULE'}, {"node_id": "5", "flow_type": 'RULE'}]
        story_dict = {'name': story_name, 'steps': steps, "metadata": metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = list(processor.get_multiflow_stories("test_get_path_rule"))
        assert multiflow_story.__len__() == 1
        assert multiflow_story[0]['metadata'] == [{"node_id": '6', "flow_type": 'RULE'},
                                                  {"node_id": "5", "flow_type": 'RULE'}]
        assert multiflow_story[0]['name'] == 'get_multiflow_story_rule'

    def test_get_multiflow_stories_with_empty_metadata(self):
        processor = MongoProcessor()
        story_name = "get_multiflow_story_empty_metadata"
        bot = "test_get_path_empty_metadata"
        user = "test_get_user_path_empty_metadata"
        steps = [
            {"step": {"name": "question", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_question", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_question", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "moody", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foody", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foody", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_foody", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_foody", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_moody", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "moody", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_moody", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = list(processor.get_multiflow_stories("test_get_path_empty_metadata"))
        assert multiflow_story.__len__() == 1
        assert multiflow_story[0]['metadata'] == []
        assert multiflow_story[0]['name'] == 'get_multiflow_story_empty_metadata'

    def test_get_multiflow_stories_with_empty_path_type_metadata(self):
        processor = MongoProcessor()
        story_name = "test_get_multiflow_stories_with_empty_path_type_metadata"
        bot = "test_get_empty_path_type_metadata"
        user = "test_get_user_empty_path_type_metadata"
        steps = [
            {"step": {"name": "questionairre", "type": "INTENT", "node_id": "1",
                      "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_questionairre", "type": "BOT", "node_id": "2",
                  "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_questionairre", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "moody", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foody", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foody", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_foody", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_foody", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_moody", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "moody", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_moody", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6'}, {"node_id": "5"}]
        story_dict = {'name': story_name, 'steps': steps, 'metadata': metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = list(processor.get_multiflow_stories("test_get_empty_path_type_metadata"))
        assert multiflow_story.__len__() == 1
        assert multiflow_story[0]['metadata'] == [{'node_id': '6', 'flow_type': 'STORY'},
                                                  {'node_id': '5', 'flow_type': 'STORY'}]
        assert multiflow_story[0]['name'] == 'test_get_multiflow_stories_with_empty_path_type_metadata'

    def test_get_multiflow_stories_with_STORY_metadata(self):
        processor = MongoProcessor()
        story_name = "get_multiflow_story_STORY"
        bot = "test_get_path_story"
        user = "test_get_user_path_story"
        steps = [
            {"step": {"name": "asker", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_ask", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_ask", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "moody", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foody", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foody", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_food", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_food", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "moody", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6', "flow_type": 'STORY'}, {"node_id": "5", "flow_type": 'STORY'}]
        story_dict = {'name': story_name, 'steps': steps, "metadata": metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = list(processor.get_multiflow_stories("test_get_path_story"))
        assert multiflow_story.__len__() == 1
        assert multiflow_story[0]['metadata'] == [{'node_id': '6', 'flow_type': 'STORY'},
                                                  {'node_id': '5', 'flow_type': 'STORY'}]
        assert multiflow_story[0]['name'] == 'get_multiflow_story_story'

    def test_get_multiflow_stories_with_RULE_metadata(self):
        processor = MongoProcessor()
        story_name = "get_multiflow_story_RULE"
        bot = "test_get_path_rule"
        user = "test_get_user_path_rule"
        steps = [
            {"step": {"name": "asker", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_asker", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_asker", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "moody", "type": "HTTP_ACTION", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foody", "type": "HTTP_ACTION", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foody", "type": "HTTP_ACTION", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_foody", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_foody", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "moody", "type": "HTTP_ACTION", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6', "flow_type": 'RULE'}, {"node_id": "5", "flow_type": 'RULE'}]
        story_dict = {'name': story_name, 'steps': steps, "metadata": metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = list(processor.get_multiflow_stories("test_get_path_rule"))
        assert multiflow_story.__len__() == 1
        assert multiflow_story[0]['metadata'] == [{"node_id": '6', "flow_type": 'RULE'},
                                                  {"node_id": "5", "flow_type": 'RULE'}]
        assert multiflow_story[0]['name'] == 'get_multiflow_story_rule'

    def test_get_multiflow_stories_with_empty_metadata(self):
        processor = MongoProcessor()
        story_name = "get_multiflow_story_empty_metadata"
        bot = "test_get_path_empty_metadata"
        user = "test_get_user_path_empty_metadata"
        steps = [
            {"step": {"name": "question", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_question", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_question", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "moody", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foody", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foody", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_foody", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_foody", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_moody", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "moody", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_moody", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = list(processor.get_multiflow_stories("test_get_path_empty_metadata"))
        assert multiflow_story.__len__() == 1
        assert multiflow_story[0]['metadata'] == []
        assert multiflow_story[0]['name'] == 'get_multiflow_story_empty_metadata'

    def test_get_multiflow_stories_with_empty_path_type_metadata(self):
        processor = MongoProcessor()
        story_name = "test_get_multiflow_stories_with_empty_path_type_metadata"
        bot = "test_get_empty_path_type_metadata"
        user = "test_get_user_empty_path_type_metadata"
        steps = [
            {"step": {"name": "questionairre", "type": "INTENT", "node_id": "1",
                      "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_questionairre", "type": "BOT", "node_id": "2",
                  "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_questionairre", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "moody", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foody", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foody", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_foody", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_foody", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_moody", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "moody", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_moody", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6'}, {"node_id": "5"}]
        story_dict = {'name': story_name, 'steps': steps, 'metadata': metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = list(processor.get_multiflow_stories("test_get_empty_path_type_metadata"))
        assert multiflow_story.__len__() == 1
        assert multiflow_story[0]['metadata'] == [{'node_id': '6', 'flow_type': 'STORY'},
                                                  {'node_id': '5', 'flow_type': 'STORY'}]
        assert multiflow_story[0]['name'] == 'test_get_multiflow_stories_with_empty_path_type_metadata'

    def test_edit_training_example_duplicate(self):
        processor = MongoProcessor()
        examples = list(processor.get_training_examples("greet", "tests"))
        with pytest.raises(AppException):
            processor.edit_training_example(examples[0]["_id"], example="hey there", intent="greet", bot="tests",
                                            user="testUser")

    def test_edit_training_example_does_not_exists(self):
        processor = MongoProcessor()
        examples = list(processor.get_training_examples("greet", "tests"))
        with pytest.raises(AppException):
            processor.edit_training_example(examples[0]["_id"], example="hey there", intent="happy", bot="tests",
                                            user="testUser")

    def test_edit_training_example(self):
        processor = MongoProcessor()
        examples = list(processor.get_training_examples("greet", "tests"))
        processor.edit_training_example(examples[0]["_id"], example="hey, there", intent="greet", bot="tests",
                                        user="testUser")
        examples = list(processor.get_training_examples("greet", "tests"))
        assert any(example['text'] == "hey, there" for example in examples)

    def test_edit_training_example_case_insensitive(self):
        processor = MongoProcessor()
        examples = list(processor.get_training_examples("greet", "tests"))
        processor.edit_training_example(examples[0]["_id"], example="hello, there", intent="greet", bot="tests",
                                        user="testUser")
        examples = list(processor.get_training_examples("greet", "tests"))
        assert any(example['text'] == "hello, there" for example in examples)

    def test_edit_training_example_with_entities(self):
        processor = MongoProcessor()
        examples = list(processor.get_training_examples("greet", "tests"))
        processor.edit_training_example(examples[0]["_id"], example="[Meghalaya](location) India", intent="greet",
                                        bot="tests", user="testUser")
        examples = list(processor.get_training_examples("greet", "tests"))
        assert any(example['text'] == "[Meghalaya](location) India" for example in examples)

    def test_edit_same_training_example_with_entities(self):
        processor = MongoProcessor()
        examples = list(
            processor.add_training_example(["What is the weather today"], intent="greet", bot="tests", user="test",
                                           is_integration=False))
        processor.edit_training_example(examples[0]["_id"], example="What is the weather [today](date)", intent="greet",
                                        bot="tests", user="testUser")
        examples = list(processor.get_training_examples("greet", "tests"))
        assert any(example['text'] == "What is the weather [today](date)" for example in examples)
        processor.edit_training_example(examples[0]["_id"], example="What is the weather today", intent="greet",
                                        bot="tests", user="testUser")
        example = TrainingExamples.objects(bot="tests", status=True).get(id=examples[0]["_id"])
        assert example.text == "What is the weather today"
        assert not example.entities

    def test_edit_responses_duplicate(self):
        processor = MongoProcessor()
        responses = list(processor.get_response("utter_happy", "tests"))
        with pytest.raises(AppException):
            processor.edit_text_response(responses[0]["_id"], "Great, carry on!", name="utter_happy", bot="tests",
                                         user="testUser")

    def test_edit_responses_does_not_exist(self):
        processor = MongoProcessor()
        responses = list(processor.get_response("utter_happy", "tests"))
        with pytest.raises(AppException):
            processor.edit_text_response(responses[0]["_id"], "Great, carry on!", name="utter_greet", bot="tests",
                                         user="testUser")

    def test_edit_responses_empty_response(self):
        processor = MongoProcessor()
        responses = list(processor.get_response("utter_happy", "tests"))
        with pytest.raises(ValidationError):
            processor.edit_text_response(responses[0]["_id"], "", name="utter_happy", bot="tests",
                                         user="testUser")
        with pytest.raises(ValidationError):
            processor.edit_text_response(responses[0]["_id"], " ", name="utter_happy", bot="tests",
                                         user="testUser")

    def test_edit_responses(self):
        processor = MongoProcessor()
        responses = list(processor.get_response("utter_happy", "tests"))
        processor.edit_text_response(responses[0]["_id"], "Great!", name="utter_happy", bot="tests", user="testUser")
        responses = list(processor.get_response("utter_happy", "tests"))
        assert any(response['value']['text'] == "Great!" for response in responses if "text" in response['value'])

    def test_edit_responses_case_insensitivity(self):
        processor = MongoProcessor()
        responses = list(processor.get_response("utter_happy", "tests"))
        processor.edit_text_response(responses[0]["_id"], "That's Great!", name="utter_happy", bot="tests",
                                     user="testUser")
        responses = list(processor.get_response("utter_happy", "tests"))
        assert any(
            response['value']['text'] == "That's Great!" for response in responses if "text" in response['value'])

    @responses.activate
    def test_start_training_done_using_event(self, monkeypatch):
        responses.add(
            responses.POST,
            "http://localhost/train",
            status=200,
            match=[responses.matchers.json_params_matcher({"bot": "test_event", "user": "testUser", "token": None})],
        )
        monkeypatch.setitem(Utility.environment['model']['train'], "event_url", "http://localhost/train")
        model_path = start_training("test_event", "testUser")
        assert model_path is None

    @responses.activate
    def test_start_training_done_using_event_and_token(self, monkeypatch):
        token = Authentication.create_access_token(data={"sub": "test@gmail.com"})
        responses.add(
            responses.POST,
            "http://localhost/train",
            status=200,
            match=[responses.matchers.json_params_matcher(
                {"bot": "test_event_with_token", "user": "testUser", "token": token})],
        )
        monkeypatch.setitem(Utility.environment['model']['train'], "event_url", "http://localhost/train")
        model_path = start_training("test_event_with_token", "testUser", token)
        assert model_path is None

    @responses.activate
    def test_start_training_done_reload_event(self, monkeypatch):
        token = Authentication.create_access_token(data={"sub": "test@gmail.com"})
        bot = "tests"
        responses.add(
            responses.GET,
            f"http://localhost/api/bot/{bot}/reload",
            json='{"message": "Reloading Model!"}',
            status=200
        )
        monkeypatch.setitem(Utility.environment['model']['agent'], "url", "http://localhost/")
        model_path = start_training("tests", "testUser", token)
        assert model_path

    @responses.activate
    def test_start_training_done_reload_event_without_token(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['model']['agent'], "url", "http://localhost/")
        responses.add(
            responses.GET,
            f"http://localhost/api/bot/tests/reload",
            json='{"message": "Reloading Model!"}',
            status=200
        )
        model_path = start_training("tests", "testUser")
        assert model_path

    def test_add_training_data(self):
        training_data = [
            models.TrainingData(intent="intent1",
                                training_examples=["example1", "example2"],
                                response="response1"),
            models.TrainingData(intent="intent2",
                                training_examples=["example3", "example4"],
                                response="response2")
        ]
        processor = MongoProcessor()
        processor.add_training_data(training_data, "training_bot", "training_user", False)
        assert Intents.objects(name="intent1").get() is not None
        assert Intents.objects(name="intent2").get() is not None
        training_examples = list(TrainingExamples.objects(intent="intent1"))
        assert training_examples is not None
        assert len(training_examples) == 2
        training_examples = list(TrainingExamples.objects(intent="intent2"))
        assert len(training_examples) == 2
        assert Responses.objects(name="utter_intent1") is not None
        assert Responses.objects(name="utter_intent2") is not None
        story = Stories.objects(block_name="path_intent1").get()
        assert story is not None
        assert story['events'][0]['name'] == 'intent1'
        assert story['events'][0]['type'] == StoryEventType.user
        assert story['events'][1]['name'] == "utter_intent1"
        assert story['events'][1]['type'] == StoryEventType.action
        story = Stories.objects(block_name="path_intent2").get()
        assert story is not None

    def test_add_training_data_with_invalid_training_example(self):
        training_data = [
            models.TrainingData(intent="intent3",
                                training_examples=[" ", "example"],
                                response="response3")]
        processor = MongoProcessor()
        processor.add_training_data(training_data, "training_bot", "training_user", False)
        assert Intents.objects(name="intent3").get() is not None
        training_examples = list(TrainingExamples.objects(intent="intent3"))
        assert training_examples is not None
        assert len(training_examples) == 1
        assert Responses.objects(name="utter_intent3") is not None
        story = Stories.objects(block_name="path_intent3").get()
        assert story is not None
        assert story['events'][0]['name'] == 'intent3'
        assert story['events'][0]['type'] == StoryEventType.user
        assert story['events'][1]['name'] == "utter_intent3"
        assert story['events'][1]['type'] == StoryEventType.action
        story = Stories.objects(block_name="path_intent3").get()
        assert story is not None

    def test_add_training_data_with_intent_exists(self):
        training_data = [
            models.TrainingData(intent="intent3",
                                training_examples=["example for intent3"],
                                response="response3")]
        processor = MongoProcessor()
        processor.add_training_data(training_data, "training_bot", "training_user", False)
        assert Intents.objects(name="intent3").get() is not None
        training_examples = list(TrainingExamples.objects(intent="intent3"))
        assert training_examples is not None
        assert len(training_examples) == 2
        assert Responses.objects(name="utter_intent3") is not None
        story = Stories.objects(block_name="path_intent3").get()
        assert story is not None
        assert story['events'][0]['name'] == 'intent3'
        assert story['events'][0]['type'] == StoryEventType.user
        assert story['events'][1]['name'] == "utter_intent3"
        assert story['events'][1]['type'] == StoryEventType.action
        story = Stories.objects(block_name="path_intent3").get()
        assert story is not None

    def test_delete_response(self):
        processor = MongoProcessor()
        intent = "test_delete_response_with_story"
        utterance = "utter_" + intent
        story = "path_" + intent
        bot = "testBot"
        user = "testUser"
        utter_intentA_1_id = processor.add_response({"text": "demo_response"}, utterance, bot, user)
        utter_intentA_2_id = processor.add_response({"text": "demo_response2"}, utterance, bot, user)
        resp = processor.get_response(utterance, bot)
        assert len(list(resp)) == 2
        processor.delete_response(utter_intentA_1_id, bot, user=user)
        resp = processor.get_response(utterance, bot)
        assert len(list(resp)) == 1
        assert Utterances.objects(name=utterance, bot=bot, status=True).get()
        processor.delete_response(utter_intentA_2_id, bot, user=user)
        resp = processor.get_response(utterance, bot)
        assert len(list(resp)) == 0
        with pytest.raises(DoesNotExist):
            Utterances.objects(name=utterance, bot=bot, status=True).get()

    def test_delete_response_non_existing(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_response("0123456789ab0123456789ab", "testBot")

    def test_delete_response_empty(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_response(" ", "testBot")

    def test_delete_utterance(self):
        processor = MongoProcessor()
        utterance = "test_delete_utterance"
        bot = "testBot"
        user = "testUser"
        processor.add_response({"text": "demo_response1"}, utterance, bot, user)
        Utterances.objects(name=utterance, bot=bot, status=True).get()
        processor.delete_utterance(utterance, bot, user=user)
        with pytest.raises(DoesNotExist):
            Utterances.objects(name=utterance, bot=bot, status=True).get()

    def test_delete_utterance_non_existing(self):
        processor = MongoProcessor()
        utterance = "test_delete_utterance_non_existing"
        bot = "testBot"
        user = "testUser"
        with pytest.raises(AppException):
            processor.delete_utterance(utterance, bot, user=user)

    def test_delete_utterance_empty(self):
        processor = MongoProcessor()
        utterance = " "
        bot = "testBot"
        user = "testUser"
        with pytest.raises(AppException):
            processor.delete_utterance(utterance, bot, user=user)

    def test_delete_utterance_name_having_no_responses(self):
        processor = MongoProcessor()
        utterance = "test_delete_utterance_name_having_no_responses"
        bot = "testBot"
        user = "testUser"
        processor.add_utterance_name(utterance, bot, user)
        processor.delete_utterance(utterance, bot, user=user)
        with pytest.raises(DoesNotExist):
            Utterances.objects(name__iexact=utterance, bot=bot, status=True).get()

    def test_add_slot_invalid_values(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'
        with pytest.raises(AppException, match='initial value must not be an empty string'):
            processor.add_slot(
                {"name": "bot", "type": "any", "initial_value": "", "influence_conversation": True},
                bot, user, raise_exception_if_exists=True
            )

        with pytest.raises(AppException, match='initial value must not be an empty string'):
            processor.add_slot(
                {"name": "bot", "type": "text", "initial_value": " ", "influence_conversation": False},
                bot, user, raise_exception_if_exists=True
            )

        with pytest.raises(AppException, match='initial value for type Text must be a string'):
            processor.add_slot(
                {"name": "bot", "type": "text", "initial_value": 123, "influence_conversation": True},
                bot, user, raise_exception_if_exists=False)

        with pytest.raises(AppException, match='initial value for type Boolean must be a true or false'):
            processor.add_slot(
                {"name": "bot", "type": "bool", "initial_value": "true", "influence_conversation": True},
                bot, user, raise_exception_if_exists=False)

        with pytest.raises(AppException, match='initial value for type List must be a list of elements'):
            processor.add_slot(
                {"name": "bot", "type": "list", "initial_value": "sample value", "influence_conversation": True},
                bot, user, raise_exception_if_exists=False)

        with pytest.raises(AppException, match='initial value for type Float must be a numeric value'):
            processor.add_slot(
                {"name": "bot", "type": "float", "initial_value": "invalid value", "min_value": 1, "max_value": 3,
                 "influence_conversation": True}, bot, user, raise_exception_if_exists=False)

        with pytest.raises(AppException, match='initial value for type Float must be a numeric value'):
            processor.add_slot(
                {"name": "bot", "type": "float", "initial_value": '0.7', "min_value": 0.5, "max_value": 1.0,
                 "influence_conversation": True}, bot, user, raise_exception_if_exists=False)

        with pytest.raises(AppException, match='min_value must be a numeric value'):
            processor.add_slot(
                {"name": "bot", "type": "float", "initial_value": 0.7, "min_value": '0.5', "max_value": 1.0,
                 "influence_conversation": True}, bot, user, raise_exception_if_exists=False)

        with pytest.raises(AppException, match='min_value must be less than max_value'):
            processor.add_slot(
                {"name": "bot", "type": "float", "initial_value": 0.7, "min_value": 1.0, "max_value": 0.5,
                 "influence_conversation": True}, bot, user, raise_exception_if_exists=False)

        with pytest.raises(AppException, match='only None is not valid values for Categorical type'):
            processor.add_slot(
                {"name": "bot", "type": "categorical", "values": [None], "influence_conversation": True},
                bot, user, raise_exception_if_exists=False)

    def test_add_slot_with_none(self):
        processor = MongoProcessor()
        bot = 'test_add_slot_with_none'
        user = 'test_user'
        processor.add_slot(
            {"name": "bot", "type": "text", "initial_value": None, "influence_conversation": True},
            bot, user, raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='bot', bot=bot, user=user).get()
        assert slot['name'] == 'bot'
        assert slot['type'] == 'text'
        assert slot['initial_value'] is None
        assert slot['influence_conversation']

        processor.add_slot(
            {"name": "is_authenticated", "type": "bool", "initial_value": None, "influence_conversation": True},
            bot, user, raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='is_authenticated', bot=bot, user=user).get()
        assert slot['name'] == 'is_authenticated'
        assert slot['type'] == 'bool'
        assert slot['initial_value'] is None
        assert slot['influence_conversation']

        processor.add_slot({"name": "color", "type": "categorical", "values": ["red", None, "blue"],
                            "initial_value": None, "influence_conversation": True},
                           bot, user, raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='color', bot=bot, user=user).get()
        assert slot['name'] == 'color'
        assert slot['type'] == 'categorical'
        assert slot['values'] == ["red", None, "blue"]
        assert slot['initial_value'] is None
        assert slot['influence_conversation']

        processor.add_slot(
            {"name": "range", "type": "float", "initial_value": None, "min_value": 0.1, "max_value": 0.3,
             "influence_conversation": True}, bot, user, raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='range', bot=bot, user=user).get()
        assert slot['name'] == 'range'
        assert slot['type'] == 'float'
        assert slot['min_value'] == 0.1
        assert slot['max_value'] == 0.3
        assert slot['initial_value'] is None
        assert slot['influence_conversation']

        processor.add_slot(
            {"name": "colors", "type": "list", "initial_value": None, "influence_conversation": True},
            bot, user, raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='colors', bot=bot, user=user).get()
        assert slot['name'] == 'colors'
        assert slot['type'] == 'list'
        assert slot['initial_value'] is None
        assert slot['influence_conversation']

    def test_add_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'
        processor.add_slot({"name": "bot", "type": "text", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='bot', bot=bot, user=user).get()
        assert slot['name'] == 'bot'
        assert slot['type'] == 'text'
        assert slot['initial_value'] is None
        assert slot['influence_conversation']
        assert Entities.objects(name='bot', bot=bot, user=user, status=True).get()

        processor.add_slot({"name": "bot", "type": "any", "initial_value": bot, "influence_conversation": False}, bot,
                           user, raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='bot', bot=bot, user=user).get()
        assert slot['name'] == 'bot'
        assert slot['type'] == 'any'
        assert slot['initial_value'] == bot
        assert not slot['influence_conversation']
        assert Entities.objects(name='bot', bot=bot, user=user, status=True).get()

    def test_add_duplicate_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        with pytest.raises(AppException):
            msg = processor.add_slot(
                {"name": "bot", "type": "any", "initial_value": bot, "influence_conversation": False}, bot, user,
                raise_exception_if_exists=True)
            assert msg == 'Slot already exists!'
            assert Entities.objects(name='bot', bot=bot, user=user, status=True).get()

    def test_add_empty_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        with pytest.raises(AppException):
            msg = processor.add_slot(
                {"name": "", "type": "invalid", "initial_value": bot, "influence_conversation": False}, bot, user,
                raise_exception_if_exists=False)
            assert msg == 'Slot Name cannot be empty or blank spaces'

    def test_add_invalid_slot_type(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        with pytest.raises(AppException):
            msg = processor.add_slot(
                {"name": "bot", "type": "invalid", "initial_value": bot, "influence_conversation": False}, bot, user,
                raise_exception_if_exists=False)
            assert msg == 'Invalid slot type.'

    def test_min_max_for_other_slot_types(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        for slot_type in SLOT_TYPE:
            if slot_type == SLOT_TYPE.FLOAT or slot_type == SLOT_TYPE.CATEGORICAL:
                continue
            else:
                processor.add_slot({"name": "bot", "type": slot_type, "max_value": 0.5, "min_value": 0.1,
                                    "influence_conversation": True}, bot, user, raise_exception_if_exists=False)
                slot = Slots.objects(name__iexact='bot', bot=bot, user=user).get()
                assert slot['name'] == 'bot'
                assert slot['type'] == slot_type
                assert slot['max_value'] is None
                assert slot['min_value'] is None

    def test_add_float_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'
        processor.add_slot({"name": "bot", "type": "float", "initial_value": 0.2, "max_value": 0.5, "min_value": 0.1,
                            "influence_conversation": True}, bot, user, raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='bot', bot=bot, user=user).get()
        assert slot['name'] == 'bot'
        assert slot['type'] == 'float'
        assert slot['initial_value'] == 0.2
        assert slot['influence_conversation']
        assert slot['max_value'] == 0.5
        assert slot['min_value'] == 0.1

    def test_values_for_other_slot_types(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        for slot_type in SLOT_TYPE:

            if slot_type == SLOT_TYPE.CATEGORICAL:
                continue
            else:
                processor.add_slot(
                    {"name": "bot", "type": slot_type, "values": ["red", "blue"],
                     "influence_conversation": True}, bot, user, raise_exception_if_exists=False)
                slot = Slots.objects(name__iexact='bot', bot=bot, user=user).get()
                assert slot['name'] == 'bot'
                assert slot['type'] == slot_type
                assert slot['values'] is None
                assert slot['influence_conversation']

    def test_add_categorical_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'
        processor.add_slot({"name": "color", "type": "categorical", "values": ["red", "blue"],
                            "influence_conversation": True}, bot, user, raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='color', bot=bot, user=user).get()
        assert slot['name'] == 'color'
        assert slot['type'] == 'categorical'
        assert slot['values'] == ["red", "blue"]
        assert slot['influence_conversation']

    def test_add_categorical_slot_without_values(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'
        with pytest.raises(ValidationError):
            msg = processor.add_slot({"name": "bot", "type": "categorical",
                                      "influence_conversation": True}, bot, user, raise_exception_if_exists=False)
            assert msg == "CategoricalSlot must have list of categories in values field"

    def test_delete_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        processor.delete_slot(slot_name='color', bot=bot, user=user)

        with pytest.raises(DoesNotExist):
            Slots.objects(name__iexact='color', bot=bot).get()
        assert not Entities.objects(name='color', bot=bot, status=True)

    def test_delete_slot_default_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        with pytest.raises(AppException, match='Default kAIron slot deletion not allowed'):
            processor.delete_slot(slot_name='bot', bot=bot, user=user)

        with pytest.raises(AppException, match='Default kAIron slot deletion not allowed'):
            processor.delete_slot(slot_name='kairon_action_response', bot=bot, user=user)

        with pytest.raises(AppException, match='Default kAIron slot deletion not allowed'):
            processor.delete_slot(slot_name='image', bot=bot, user=user)

        with pytest.raises(AppException, match='Default kAIron slot deletion not allowed'):
            processor.delete_slot(slot_name='video', bot=bot, user=user)

        with pytest.raises(AppException, match='Default kAIron slot deletion not allowed'):
            processor.delete_slot(slot_name='audio', bot=bot, user=user)

        with pytest.raises(AppException, match='Default kAIron slot deletion not allowed'):
            processor.delete_slot(slot_name='document', bot=bot, user=user)

        with pytest.raises(AppException, match='Default kAIron slot deletion not allowed'):
            processor.delete_slot(slot_name='doc_url', bot=bot, user=user)

        with pytest.raises(AppException, match='Default kAIron slot deletion not allowed'):
            processor.delete_slot(slot_name='order', bot=bot, user=user)

    def test_delete_slot_having_story_attached(self):
        processor = MongoProcessor()
        story_name = "delete story with slot"
        bot = "test_slot_delete"
        user = "test_user"
        slot_name = "is_new_user"
        slot = {"name": slot_name, "type": "any", "initial_value": None, "influence_conversation": False}
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": slot_name, "type": "SLOT", "value": None},
            {"name": "utter_welcome_user", "type": "BOT"},
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.add_slot(slot_value=slot, bot=bot, user=user)
        pytest.story_id = processor.add_complex_story(story_dict, bot, user)

        with pytest.raises(AppException) as e:
            processor.delete_slot(slot_name=slot_name, bot=bot, user=user)
            assert str(e) == "Slot is attached to story: ['delete story with slot']"

    def test_delete_slot_having_training_attached(self):
        processor = MongoProcessor()
        bot = "test_slot_delete_training"
        user = "test_user"
        slot_name = "time"
        intent = "greet"
        slot = {"name": slot_name, "type": "any", "initial_value": None, "influence_conversation": True}
        processor.add_slot(slot_value=slot, bot=bot, user=user)
        processor.add_intent(intent, bot=bot, user=user, is_integration=False)
        response = list(processor.add_training_example(["hi [Good Morning](time)"], intent, bot=bot, user=user,
                                                       is_integration=False))
        assert len(response) == 1
        with pytest.raises(AppException) as e:
            processor.delete_slot(slot_name=slot_name, bot=bot, user=user)
            assert str(e) == f"Slot is attached to training example: ['{intent}']"

    def test_delete_slot_having_multi_story_attached(self):
        processor = MongoProcessor()
        bot = "test_slot_delete_multi_story"
        user = "test_user"
        slot_name = "mood"
        story_name = "mood multi flow"
        slot = {"name": slot_name, "type": "any", "initial_value": None, "influence_conversation": True}
        processor.add_slot(slot_value=slot, bot=bot, user=user)
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "mood", "type": "SLOT", "value": "Happy", "node_id": "3",
                  "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "food", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "food", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_food", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_food", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "mood", "type": "SLOT", "value": "Happy", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        pytest.story_id = processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = MultiflowStories.objects(block_name=story_name, bot=bot).get()
        assert len(multiflow_story.events) == 6

        with pytest.raises(AppException) as e:
            processor.delete_slot(slot_name=slot_name, bot=bot, user=user)
            assert str(e) == f"Slot is attached to multiflow story: : ['{story_name}']"

    def test_delete_slot_having_slot_mapping_attached(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'
        slot_name = 'is_new_user'
        slot = {"name": slot_name, "type": "any", "initial_value": None, "influence_conversation": False}
        mapping = {"slot": slot_name, 'mapping': {'type': 'from_entity', 'entity': 'name'}}
        processor.add_slot(slot_value=slot, bot=bot, user=user)
        processor.add_slot_mapping(mapping, bot, user)

        with pytest.raises(AppException, match="Cannot delete slot without removing its mappings!"):
            processor.delete_slot(slot_name=slot_name, bot=bot, user=user)

        processor.delete_slot_mapping(slot_name, bot, user)
        processor.delete_slot(slot_name=slot_name, bot=bot, user=user)

    def test_delete_inexistent_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        with pytest.raises(AppException) as e:
            processor.delete_slot(slot_name='bot_doesnt_exist', bot=bot, user=user)
        assert str(e).__contains__('Slot does not exist.')

    def test_delete_empty_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        with pytest.raises(AppException) as e:
            processor.delete_slot(slot_name='', bot=bot, user=user)
        assert str(e).__contains__('Slot does not exist.')

    def test_delete_entity_not_exists(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Entity not found'):
            processor.delete_entity('entity_not_exists', 'test_bot', 'test_user')

    def test_fetch_rule_block_names(self):
        processor = MongoProcessor()
        Rules(
            block_name="rule1",
            condition_events_indices=[],
            start_checkpoints=["START"],
            end_checkpoints=["END"],
            events=[StoryEvents(name="greet", type="user"), StoryEvents(name="utter_greet", type="action")],
            bot="test_bot",
            user="rule_creator",
        ).save()
        Rules(
            block_name="rule2",
            condition_events_indices=[],
            start_checkpoints=["START"],
            end_checkpoints=["END"],
            events=[StoryEvents(name="greet", type="user"), StoryEvents(name="utter_greet", type="action")],
            bot="test_bot",
            user="rule_creator",
        ).save()
        block_names = processor.fetch_rule_block_names("test_bot")
        assert block_names[0] == "rule1"
        assert block_names[1] == "rule2"

    def test_fetch_rule_block_names_no_rules_present(self):
        processor = MongoProcessor()
        block_names = processor.fetch_rule_block_names("rule_creator")
        assert not block_names

    def test_save_rules(self):
        processor = MongoProcessor()
        intent = {
            STORY_EVENT.NAME.value: "greet",
            STORY_EVENT.CONFIDENCE.value: 1.0,
        }
        events = [UserUttered(text="greet", intent=intent),
                  ActionExecuted(action_name="utter_greet")]
        story_steps = [RuleStep(block_name="rule1",
                                start_checkpoints=[Checkpoint("START")],
                                end_checkpoints=[Checkpoint("END")],
                                events=events,
                                condition_events_indices={0}),
                       RuleStep(block_name="rule2",
                                start_checkpoints=[Checkpoint("START")],
                                end_checkpoints=[Checkpoint("END")],
                                events=events,
                                condition_events_indices={0})
                       ]
        processor.save_rules(story_steps, "test_save_rules", "rules_creator")
        rules = list(Rules.objects(bot="test_save_rules", user="rules_creator", status=True))
        assert rules[0]['block_name'] == "rule1"
        assert rules[0]['condition_events_indices'] == [0]
        assert rules[0]['start_checkpoints'] == ["START"]
        assert rules[0]['end_checkpoints'] == ["END"]
        assert rules[0]['events'][0]['name'] == "greet"
        assert rules[0]['events'][0]['type'] == "user"
        assert not rules[0]['events'][0]['value']
        assert rules[0]['events'][1]['name'] == "utter_greet"
        assert rules[0]['events'][1]['type'] == "action"
        assert not rules[0]['events'][1]['value']
        assert rules[1]['block_name'] == "rule2"

    def test_save_rules_already_present(self):
        processor = MongoProcessor()
        events = [UserUttered(text="greet"),
                  ActionExecuted(action_name="utter_greet")]
        Rules(block_name="rule2",
              start_checkpoints=["START"],
              end_checkpoints=["END"],
              events=[StoryEvents(name="greet", type="user"),
                      StoryEvents(name="utter_greet", type="action")],
              condition_events_indices={0}, bot="test_save_rules_already_present", user="rules_creator").save()
        story_steps = [RuleStep(block_name="rule1",
                                start_checkpoints=[Checkpoint("START")],
                                end_checkpoints=[Checkpoint("END")],
                                events=events,
                                condition_events_indices={0}),
                       RuleStep(block_name="rule2",
                                start_checkpoints=[Checkpoint("START")],
                                end_checkpoints=[Checkpoint("END")],
                                events=events,
                                condition_events_indices={0})
                       ]
        processor.save_rules(story_steps, "test_save_rules_already_present", "rules_creator")
        rules = list(Rules.objects(bot="test_save_rules_already_present", user="rules_creator", status=True))
        assert len(rules) == 2
        assert rules[0]['block_name'] == "rule2"
        assert rules[0]['condition_events_indices'] == [0]
        assert rules[0]['start_checkpoints'] == ["START"]
        assert rules[0]['end_checkpoints'] == ["END"]
        assert rules[0]['events'][0]['name'] == "greet"
        assert rules[0]['events'][0]['type'] == "user"
        assert not rules[0]['events'][0]['value']
        assert rules[0]['events'][1]['name'] == "utter_greet"
        assert rules[0]['events'][1]['type'] == "action"
        assert not rules[0]['events'][1]['value']
        assert rules[1]['block_name'] == "rule1"

    def test_get_rules_for_training(self):
        Rules(
            block_name="rule1",
            condition_events_indices=[],
            start_checkpoints=["START"],
            end_checkpoints=["END"],
            events=[StoryEvents(name="greet", type="user"), StoryEvents(name="utter_greet", type="action")],
            bot="test_get_rules_for_training",
            user="rule_creator",
        ).save()
        Rules(
            block_name="rule2",
            condition_events_indices=[],
            start_checkpoints=["START"],
            end_checkpoints=["END"],
            events=[StoryEvents(name="greet", type="user"), StoryEvents(name="utter_greet", type="action")],
            bot="test_get_rules_for_training",
            user="rule_creator",
        ).save()
        processor = MongoProcessor()
        rules = processor.get_rules_for_training("test_get_rules_for_training")
        assert isinstance(rules, StoryGraph)
        assert len(rules.story_steps) == 2

    def test_get_rules_no_rules_present(self):
        processor = MongoProcessor()
        rules = processor.get_rules_for_training("test_get_rules_no_rules_present")
        assert not rules.story_steps

    def test_delete_rules(self):
        processor = MongoProcessor()
        rules = (Rules.objects(bot="test_save_rules_already_present", user="rules_creator", status=True))
        assert rules
        processor.delete_rules("test_save_rules_already_present", "rules_creator")
        rules = (Rules.objects(bot="test_save_rules_already_present", user="rules_creator", status=True))
        assert not rules

    def test_delete_rules_no_rules(self):
        processor = MongoProcessor()
        rules = (Rules.objects(bot="test_save_rules_already_present", user="rules_creator", status=True))
        assert not rules
        processor.delete_rules("test_save_rules_already_present", "rules_creator")

    @pytest.mark.asyncio
    async def test_upload_and_save(self):
        processor = MongoProcessor()
        nlu_content = "nlu:\n  - intent: greet\n    examples: |\n      - hey\n      - hello".encode()
        stories_content = "stories:\n  - story: greet\n    steps:\n      - intent: greet\n      - action: utter_offer_help\n      - action: action_restart".encode()
        config_content = "language: en\npipeline:\n- name: WhitespaceTokenizer\n- name: RegexFeaturizer\n- name: LexicalSyntacticFeaturizer\n- name: CountVectorsFeaturizer\n- analyzer: char_wb\n  max_ngram: 4\n  min_ngram: 1\n  name: CountVectorsFeaturizer\n- epochs: 5\n  name: DIETClassifier\n- name: EntitySynonymMapper\n- epochs: 5\n  name: ResponseSelector\npolicies:\n- name: MemoizationPolicy\n- epochs: 5\n  max_history: 5\n  name: TEDPolicy\n- name: RulePolicy\n- core_threshold: 0.3\n  fallback_action_name: action_small_talk\n  name: FallbackPolicy\n  nlu_threshold: 0.75\n".encode()
        domain_content = "intents:\n- greet\nresponses:\n  utter_offer_help:\n  - text: 'how may i help you'\nactions:\n- utter_offer_help\n".encode()
        nlu = UploadFile(filename="nlu.yml", file=BytesIO(nlu_content))
        stories = UploadFile(filename="stories.yml", file=BytesIO(stories_content))
        config = UploadFile(filename="config.yml", file=BytesIO(config_content))
        domain = UploadFile(filename="domain.yml", file=BytesIO(domain_content))
        await processor.upload_and_save(nlu, domain, stories, config, None, None, None, None, "test_upload_and_save",
                                        "rules_creator")
        assert len(list(Intents.objects(bot="test_upload_and_save", user="rules_creator"))) == 6
        assert len(list(Stories.objects(bot="test_upload_and_save", user="rules_creator"))) == 1
        assert len(list(Responses.objects(bot="test_upload_and_save", user="rules_creator"))) == 3
        assert len(
            list(TrainingExamples.objects(intent="greet", bot="test_upload_and_save", user="rules_creator"))) == 2

    @pytest.mark.asyncio
    async def test_upload_and_save_with_rules(self):
        processor = MongoProcessor()
        nlu_content = "nlu:\n  - intent: greet\n    examples: |\n      - hey\n      - hello".encode()
        stories_content = "stories:\n  - story: greet\n    steps:\n      - intent: greet\n      - action: utter_offer_help\n      - action: action_restart".encode()
        config_content = "language: en\npipeline:\n- name: WhitespaceTokenizer\n- name: RegexFeaturizer\n- name: LexicalSyntacticFeaturizer\n- name: CountVectorsFeaturizer\n- analyzer: char_wb\n  max_ngram: 4\n  min_ngram: 1\n  name: CountVectorsFeaturizer\n- epochs: 5\n  name: DIETClassifier\n- name: EntitySynonymMapper\n- epochs: 5\n  name: ResponseSelector\npolicies:\n- name: MemoizationPolicy\n- epochs: 5\n  max_history: 5\n  name: TEDPolicy\n- name: RulePolicy\n- core_threshold: 0.3\n  fallback_action_name: action_small_talk\n  name: FallbackPolicy\n  nlu_threshold: 0.75\n".encode()
        domain_content = "intents:\n- greet\nresponses:\n  utter_offer_help:\n  - text: 'how may i help you'\nactions:\n- utter_offer_help\n".encode()
        rules_content = "rules:\n\n- rule: Only say `hello` if the user provided a location\n  condition:\n  - slot_was_set:\n    - location: true\n  steps:\n  - intent: greet\n  - action: utter_greet\n".encode()
        nlu = UploadFile(filename="nlu.yml", file=BytesIO(nlu_content))
        stories = UploadFile(filename="stories.yml", file=BytesIO(stories_content))
        config = UploadFile(filename="config.yml", file=BytesIO(config_content))
        domain = UploadFile(filename="domain.yml", file=BytesIO(domain_content))
        rules = UploadFile(filename="rules.yml", file=BytesIO(rules_content))
        await processor.upload_and_save(nlu, domain, stories, config, rules, None, None, None, "test_upload_and_save",
                                        "rules_creator")
        assert len(list(Intents.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 6
        assert len(list(Stories.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 1
        assert len(list(Responses.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 3
        assert len(
            list(TrainingExamples.objects(intent="greet", bot="test_upload_and_save", user="rules_creator",
                                          status=True))) == 2
        assert len(list(Rules.objects(bot="test_upload_and_save", user="rules_creator"))) == 2

    @pytest.mark.asyncio
    async def test_upload_and_save_with_http_action(self):
        processor = MongoProcessor()
        nlu_content = "nlu:\n  - intent: greet\n    examples: |\n      - hey\n      - hello".encode()
        stories_content = "stories:\n  - story: greet\n    steps:\n      - intent: greet\n      - action: utter_offer_help\n      - action: action_restart".encode()
        config_content = "language: en\npipeline:\n- name: WhitespaceTokenizer\n- name: RegexFeaturizer\n- name: LexicalSyntacticFeaturizer\n- name: CountVectorsFeaturizer\n- analyzer: char_wb\n  max_ngram: 4\n  min_ngram: 1\n  name: CountVectorsFeaturizer\n- epochs: 5\n  name: DIETClassifier\n- name: EntitySynonymMapper\n- epochs: 5\n  name: ResponseSelector\npolicies:\n- name: MemoizationPolicy\n- epochs: 5\n  max_history: 5\n  name: TEDPolicy\n- name: RulePolicy\n- core_threshold: 0.3\n  fallback_action_name: action_small_talk\n  name: FallbackPolicy\n  nlu_threshold: 0.75\n".encode()
        domain_content = "intents:\n- greet\nresponses:\n  utter_offer_help:\n  - text: 'how may i help you'\nactions:\n- utter_offer_help\n".encode()
        http_action_content = "http_action:\n- action_name: action_performanceUser1000@digite.com\n  http_url: http://www.alphabet.com\n  headers:\n  - key: auth_token\n    parameter_type: value\n    value: bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf\n  params_list:\n  - key: testParam1\n    parameter_type: value\n    value: testValue1\n  - key: testParam2\n    parameter_type: slot\n    value: testValue1\n  request_method: GET\n  response:\n    value: json\n".encode()
        nlu = UploadFile(filename="nlu.yml", file=BytesIO(nlu_content))
        stories = UploadFile(filename="stories.yml", file=BytesIO(stories_content))
        config = UploadFile(filename="config.yml", file=BytesIO(config_content))
        domain = UploadFile(filename="domain.yml", file=BytesIO(domain_content))
        http_action = UploadFile(filename="actions.yml", file=BytesIO(http_action_content))
        await processor.upload_and_save(nlu, domain, stories, config, None, http_action, None, None, "test_upload_and_save",
                                        "rules_creator")
        assert len(list(Intents.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 6
        assert len(list(Stories.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 1
        assert len(list(Responses.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 3
        assert len(
            list(TrainingExamples.objects(intent="greet", bot="test_upload_and_save", user="rules_creator",
                                          status=True))) == 2
        assert len(list(HttpActionConfig.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 1

    @pytest.mark.asyncio
    async def test_upload_and_save_with_empty_multiflow_stories(self):
        processor = MongoProcessor()
        nlu_content = 'version: "3.1"\nnlu:\n- intent: greet\n  examples: |\n    - hey\n    - hello\n    - hi\n    - good morning\n- intent: deny\n  examples: |\n    - no\n    - never\n    - I dont think so\n    - dont like that\n- intent: query\n  examples: |\n    - What is AI?\n    - Tell me about AI?\n    - Do you know about AI\n'.encode()
        stories_content = 'version: "3.1"\nstories:\n- story: greet\n  steps:\n  - intent: greet\n  - action: utter_greet\n  - action: action_restart\n'.encode()
        config_content = "language: en\npipeline:\n- name: WhitespaceTokenizer\n- name: RegexFeaturizer\n- name: LexicalSyntacticFeaturizer\n- name: CountVectorsFeaturizer\n- analyzer: char_wb\n  max_ngram: 4\n  min_ngram: 1\n  name: CountVectorsFeaturizer\n- epochs: 5\n  name: DIETClassifier\n- name: EntitySynonymMapper\n- epochs: 5\n  name: ResponseSelector\npolicies:\n- name: MemoizationPolicy\n- epochs: 5\n  max_history: 5\n  name: TEDPolicy\n- name: RulePolicy\n- core_threshold: 0.3\n  fallback_action_name: action_small_talk\n  name: FallbackPolicy\n  nlu_threshold: 0.75\n".encode()
        domain_content = "intents:\n- query\nresponses:\n  utter_query:\n  - text: 'Artificial intelligence is the simulation of human intelligence processes by machines, especially computer systems'\nactions:\n- utter_query\n".encode()
        http_action_content = "http_action:\n- action_name: action_performanceUser1000@digite.com\n  http_url: http://www.alphabet.com\n  headers:\n  - key: auth_token\n    parameter_type: value\n    value: bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf\n  params_list:\n  - key: testParam1\n    parameter_type: value\n    value: testValue1\n  - key: testParam2\n    parameter_type: slot\n    value: testValue1\n  request_method: GET\n  response:\n    value: json\n".encode()
        multiflow_stories_content = "multiflow_story:\n".encode()
        nlu = UploadFile(filename="nlu.yml", file=BytesIO(nlu_content))
        stories = UploadFile(filename="stories.yml", file=BytesIO(stories_content))
        config = UploadFile(filename="config.yml", file=BytesIO(config_content))
        domain = UploadFile(filename="domain.yml", file=BytesIO(domain_content))
        http_action = UploadFile(filename="actions.yml", file=BytesIO(http_action_content))
        multiflow_story = UploadFile(filename="multiflow_stories.yml", file=BytesIO(multiflow_stories_content))
        await processor.upload_and_save(nlu, domain, stories, config, None, http_action, multiflow_story, None,
                                        "test_upload_and_save",
                                        "rules_creator")
        assert len(list(Intents.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 6
        assert len(list(Stories.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 1
        assert len(list(Responses.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 3
        assert len(
            list(TrainingExamples.objects(intent="greet", bot="test_upload_and_save", user="rules_creator",
                                          status=True))) == 4
        assert len(list(MultiflowStories.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 0

    @pytest.mark.asyncio
    async def test_upload_and_save_with_empty_multiflow_stories_none(self):
        processor = MongoProcessor()
        nlu_content = 'version: "3.1"\nnlu:\n- intent: greet\n  examples: |\n    - hey\n    - hello\n    - hi\n    - good morning\n- intent: deny\n  examples: |\n    - no\n    - never\n    - I dont think so\n    - dont like that\n- intent: query\n  examples: |\n    - What is AI?\n    - Tell me about AI?\n    - Do you know about AI\n'.encode()
        stories_content = 'version: "3.1"\nstories:\n- story: greet\n  steps:\n  - intent: greet\n  - action: utter_greet\n  - action: action_restart\n'.encode()
        config_content = "language: en\npipeline:\n- name: WhitespaceTokenizer\n- name: RegexFeaturizer\n- name: LexicalSyntacticFeaturizer\n- name: CountVectorsFeaturizer\n- analyzer: char_wb\n  max_ngram: 4\n  min_ngram: 1\n  name: CountVectorsFeaturizer\n- epochs: 5\n  name: DIETClassifier\n- name: EntitySynonymMapper\n- epochs: 5\n  name: ResponseSelector\npolicies:\n- name: MemoizationPolicy\n- epochs: 5\n  max_history: 5\n  name: TEDPolicy\n- name: RulePolicy\n- core_threshold: 0.3\n  fallback_action_name: action_small_talk\n  name: FallbackPolicy\n  nlu_threshold: 0.75\n".encode()
        domain_content = "intents:\n- query\nresponses:\n  utter_query:\n  - text: 'Artificial intelligence is the simulation of human intelligence processes by machines, especially computer systems'\nactions:\n- utter_query\n".encode()
        http_action_content = "http_action:\n- action_name: action_performanceUser1000@digite.com\n  http_url: http://www.alphabet.com\n  headers:\n  - key: auth_token\n    parameter_type: value\n    value: bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf\n  params_list:\n  - key: testParam1\n    parameter_type: value\n    value: testValue1\n  - key: testParam2\n    parameter_type: slot\n    value: testValue1\n  request_method: GET\n  response:\n    value: json\n".encode()
        multiflow_stories_content = "".encode()
        nlu = UploadFile(filename="nlu.yml", file=BytesIO(nlu_content))
        stories = UploadFile(filename="stories.yml", file=BytesIO(stories_content))
        config = UploadFile(filename="config.yml", file=BytesIO(config_content))
        domain = UploadFile(filename="domain.yml", file=BytesIO(domain_content))
        http_action = UploadFile(filename="actions.yml", file=BytesIO(http_action_content))
        multiflow_story = UploadFile(filename="multiflow_stories.yml", file=BytesIO(multiflow_stories_content))
        await processor.upload_and_save(nlu, domain, stories, config, None, http_action, multiflow_story, None,
                                        "test_upload_and_save",
                                        "rules_creator")
        assert len(list(Intents.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 6
        assert len(list(Stories.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 1
        assert len(list(Responses.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 3
        assert len(
            list(TrainingExamples.objects(intent="greet", bot="test_upload_and_save", user="rules_creator",
                                          status=True))) == 4
        assert len(list(MultiflowStories.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 0

    @pytest.mark.asyncio
    async def test_upload_and_save_with_multiflow_stories(self):
        processor = MongoProcessor()
        nlu_content = 'version: "3.1"\nnlu:\n- intent: greet\n  examples: |\n    - hey\n    - hello\n    - hi\n    - good morning\n- intent: deny\n  examples: |\n    - no\n    - never\n    - I dont think so\n    - dont like that\n- intent: query\n  examples: |\n    - What is AI?\n    - Tell me about AI?\n    - Do you know about AI\n- intent: affirm\n  examples: |\n    - affirmative\n    - sure, please go ahead\n    - sounds good right\n'.encode()
        stories_content = 'version: "3.1"\nstories:\n- story: greet\n  steps:\n  - intent: greet\n  - action: utter_greet\n  - action: action_restart\n'.encode()
        config_content = "language: en\npipeline:\n- name: WhitespaceTokenizer\n- name: RegexFeaturizer\n- name: LexicalSyntacticFeaturizer\n- name: CountVectorsFeaturizer\n- analyzer: char_wb\n  max_ngram: 4\n  min_ngram: 1\n  name: CountVectorsFeaturizer\n- epochs: 5\n  name: DIETClassifier\n- name: EntitySynonymMapper\n- epochs: 5\n  name: ResponseSelector\npolicies:\n- name: MemoizationPolicy\n- epochs: 5\n  max_history: 5\n  name: TEDPolicy\n- name: RulePolicy\n- core_threshold: 0.3\n  fallback_action_name: action_small_talk\n  name: FallbackPolicy\n  nlu_threshold: 0.75\n".encode()
        domain_content = "intents:\n- greet\n- query\n- deny\n- affirm\nresponses:\n  utter_offer_help:\n  - text: 'how may i help you'\n  utter_query:\n  - text: 'Artificial intelligence is the simulation of human intelligence processes by machines, especially computer systems'\n  utter_goodbye:\n  - text: 'Bye'\n  utter_feedback:\n  - text: 'Thanks you for loving us. Keep using.'\nactions:\n- utter_offer_help\n- utter_query\n- utter_goodbye\n- utter_feedback\n".encode()
        http_action_content = "http_action:\n- action_name: action_performanceUser1000@digite.com\n  http_url: http://www.alphabet.com\n  headers:\n  - key: auth_token\n    parameter_type: value\n    value: bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf\n  params_list:\n  - key: testParam1\n    parameter_type: value\n    value: testValue1\n  - key: testParam2\n    parameter_type: slot\n    value: testValue1\n  request_method: GET\n  response:\n    value: json\n".encode()
        multiflow_stories_content = "multiflow_story:\n- block_name: mf_one_1\n  events:\n    - step:\n        name: query\n        type: INTENT\n        node_id: '1'\n      connections:\n        - name: utter_query\n          type: BOT\n          node_id: '2'\n    - step:\n        name: utter_query\n        type: BOT\n        node_id: '2'\n      connections:\n        - name: deny\n          type: INTENT\n          node_id: '3'\n        - name: affirm\n          type: INTENT\n          node_id: '4'\n    - step:\n        name: affirm\n        type: INTENT\n        node_id: '4'\n      connections:\n        - name: utter_feedback\n          type: BOT\n          node_id: '5'\n    - step:\n        name: utter_feedback\n        type: BOT\n        node_id: '5'\n      connections: null\n    - step:\n        name: utter_goodbye\n        type: BOT\n        node_id: '6'\n      connections: null\n    - step:\n        name: deny\n        type: INTENT\n        node_id: '3'\n      connections:\n        - name: utter_goodbye\n          type: BOT\n          node_id: '6'\n  metadata:\n    - node_id: '6'\n      flow_type: STORY\n  start_checkpoints: [STORY_START]\n  end_checkpoints:".encode()
        nlu = UploadFile(filename="nlu.yml", file=BytesIO(nlu_content))
        stories = UploadFile(filename="stories.yml", file=BytesIO(stories_content))
        config = UploadFile(filename="config.yml", file=BytesIO(config_content))
        domain = UploadFile(filename="domain.yml", file=BytesIO(domain_content))
        http_action = UploadFile(filename="actions.yml", file=BytesIO(http_action_content))
        multiflow_story = UploadFile(filename="multiflow_stories.yml", file=BytesIO(multiflow_stories_content))
        await processor.upload_and_save(nlu, domain, stories, config, None, http_action, multiflow_story, None,
                                        "test_upload_and_save",
                                        "rules_creator")
        assert len(list(Intents.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 9
        assert len(list(Stories.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 1
        assert len(list(Responses.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 6
        assert len(
            list(TrainingExamples.objects(intent="greet", bot="test_upload_and_save", user="rules_creator",
                                          status=True))) == 4
        assert len(list(MultiflowStories.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 1

    def test_load_and_delete_http_action(self):
        HttpActionConfig(
            action_name="act1",
            http_url="http://www.alphabet.com",
            request_method="POST",
            response=HttpActionResponse(value='zxcvb'),
            bot="test_http",
            user="http_creator",
        ).save()
        processor = MongoProcessor()
        actions = processor.load_http_action("test_http")
        assert actions
        assert isinstance(actions, dict)
        assert len(actions["http_action"]) == 1
        processor.delete_bot_actions(bot="test_http", user="http_creator")
        actions = processor.load_http_action("test_http")
        assert not actions['http_action']
        assert isinstance(actions, dict)

    def test_save_http_action_already_exists(self):
        test_dict = {"http_action": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                      "params_list": [{"key": 'location', "parameter_type": 'sender_id', "value": ''}],
                                      "request_method": "GET", "response": {"value": "${RESPONSE}"}},
                                     {"action_name": "test_save_http_action_already_exists",
                                      "http_url": "http://f2724.kairon.io/",
                                      "request_method": "GET", "response": {"value": "${RESPONSE}"}}
                                     ]}
        HttpActionConfig(action_name="test_save_http_action_already_exists",
                         http_url='http://kairon.ai',
                         response=HttpActionResponse(value='response'),
                         request_method='GET',
                         bot='test', user='test').save()
        Actions(name='test_save_http_action_already_exists', bot='test', user='test', status=True,
                type=ActionType.http_action.value).save()
        processor = MongoProcessor()
        processor.save_integrated_actions(test_dict, 'test', 'test')
        action = HttpActionConfig.objects(bot='test', user='test', status=True).get(
            action_name="test_save_http_action_already_exists")
        assert action
        assert action['http_url'] == "http://kairon.ai"
        assert not action['params_list']
        action = HttpActionConfig.objects(bot='test', user='test').get(action_name="rain_today")
        assert action
        assert action['http_url'] == "http://f2724.kairon.io/"
        assert action['params_list']

    def test_get_action_server_logs_empty(self):
        processor = MongoProcessor()
        logs = list(processor.get_action_server_logs("test_bot"))
        assert logs == []

    def test_get_action_server_logs(self):
        bot = "test_bot"
        bot_2 = "testing_bot"
        expected_intents = ["intent13", "intent11", "intent9", "intent8", "intent7", "intent6", "intent5",
                            "intent4", "intent3", "intent2"]
        request_params = {"key": "value", "key2": "value2"}
        ActionServerLogs(intent="intent1", action="http_action", sender="sender_id",
                         timestamp=datetime(2021, 4, 11, 11, 39, 48, 376000),
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot).save()
        ActionServerLogs(intent="intent2", action="http_action", sender="sender_id",
                         url="http://kairon-api.digite.com/api/bot",
                         request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot,
                         status="FAILURE").save()
        ActionServerLogs(intent="intent1", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot_2).save()
        ActionServerLogs(intent="intent3", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot,
                         status="FAILURE").save()
        ActionServerLogs(intent="intent4", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot).save()
        ActionServerLogs(intent="intent5", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot,
                         status="FAILURE").save()
        ActionServerLogs(intent="intent6", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot).save()
        ActionServerLogs(intent="intent7", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot).save()
        ActionServerLogs(intent="intent8", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot).save()
        ActionServerLogs(intent="intent9", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot).save()
        ActionServerLogs(intent="intent10", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot_2).save()
        ActionServerLogs(intent="intent11", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot).save()
        ActionServerLogs(intent="intent12", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot_2,
                         status="FAILURE").save()
        ActionServerLogs(intent="intent13", action="http_action", sender="sender_id_13",
                         request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot,
                         status="FAILURE").save()
        processor = MongoProcessor()
        logs = list(processor.get_action_server_logs(bot))
        assert len(logs) == 10
        assert [log['intent'] in expected_intents for log in logs]
        assert logs[0]['action'] == "http_action"
        assert any([log['request_params'] == request_params for log in logs])
        assert any([log['sender'] == "sender_id_13" for log in logs])
        assert any([log['api_response'] == "Response" for log in logs])
        assert any([log['bot_response'] == "Bot Response" for log in logs])
        assert any([log['status'] == "FAILURE" for log in logs])
        assert any([log['status'] == "SUCCESS" for log in logs])

        logs = list(processor.get_action_server_logs(bot_2))
        assert len(logs) == 3

    def test_get_action_server_logs_start_idx_page_size(self):
        processor = MongoProcessor()
        bot = "test_bot"
        bot_2 = "testing_bot"
        logs = list(processor.get_action_server_logs(bot, 10, 15))
        assert len(logs) == 1

        logs = list(processor.get_action_server_logs(bot, 10, 1))
        assert len(logs) == 1

        logs = list(processor.get_action_server_logs(bot, 0, 5))
        assert len(logs) == 5

        logs = list(processor.get_action_server_logs(bot_2, 0, 5))
        assert len(logs) == 3

        logs = list(processor.get_action_server_logs(bot_2, 2, 1))
        assert len(logs) == 1
        log = logs[0]
        assert log['intent'] == "intent1"

    def test_get_action_server_logs_cnt(self):
        processor = MongoProcessor()
        bot = "test_bot"
        bot_2 = "testing_bot"
        cnt = processor.get_row_count(ActionServerLogs, bot)
        assert cnt == 11

        cnt = processor.get_row_count(ActionServerLogs, bot_2)
        assert cnt == 3

    def test_get_existing_slots(self):
        Slots(
            name="location",
            type="text",
            initial_value="delhi",
            bot="test_get_existing_slots",
            user="bot_user",
        ).save()
        Slots(
            name="email_id",
            type="text",
            initial_value="bot_user@digite.com",
            bot="test_get_existing_slots",
            user="bot_user",
        ).save()
        Slots(
            name="username",
            type="text",
            initial_value="bot_user",
            bot="test_get_existing_slots",
            user="bot_user",
            status=False
        ).save()
        slots = list(MongoProcessor.get_existing_slots("test_get_existing_slots"))
        assert len(slots) == 2
        assert slots[0]['name'] == 'location'
        assert slots[1]['name'] == 'email_id'

    def test_get_existing_slots_bot_not_exists(self):
        slots = list(MongoProcessor.get_existing_slots("test_get_existing_slots_bot_not_exists"))
        assert len(slots) == 0

    @pytest.mark.asyncio
    async def test_save_training_data_all(self, get_training_data, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        path = 'tests/testing_data/yml_training_files'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions, multiflow_stories,  bot_content, chat_client_config = await get_training_data(
            path)

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, config, domain, story_graph, nlu, http_actions, multiflow_stories, bot_content,
                                           chat_client_config, overwrite=True)

        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 305
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 16
        assert story_graph.story_steps[14].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[14].events[2].entities[0].get('start')
        assert not story_graph.story_steps[14].events[2].entities[0].get('end')
        assert story_graph.story_steps[14].events[2].entities[0]['value'] == 'like'
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdresponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[15].events[2].entities[0].get('start')
        assert not story_graph.story_steps[15].events[2].entities[0].get('end')
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdresponse'
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 24
        assert len([slot for slot in domain.slots if slot.influence_conversation is True]) == 12
        assert len([slot for slot in domain.slots if slot.influence_conversation is False]) == 12
        assert domain.intent_properties.__len__() == 32
        assert len([intent for intent in domain.intent_properties.keys() if
                    domain.intent_properties.get(intent)['used_entities']]) == 27
        assert len([intent for intent in domain.intent_properties.keys() if
                    not domain.intent_properties.get(intent)['used_entities']]) == 5
        assert domain.responses.keys().__len__() == 29
        assert domain.entities.__len__() == 24
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 48
        assert domain.intents.__len__() == 32
        assert not Utility.check_empty_string(
            domain.responses["utter_cheer_up"][0]["image"]
        )
        assert domain.responses["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.responses["utter_offer_help"][0]["custom"]
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 4
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert len(actions['http_action']) == 17
        assert len(Actions.objects(type='http_action', bot=bot)) == 17
        multiflow_stories = mongo_processor.load_multiflow_stories_yaml(bot)
        assert isinstance(multiflow_stories, dict) is True
        bot_content = mongo_processor.load_bot_content(bot)
        assert isinstance(bot_content, list) is True

    @pytest.mark.asyncio
    async def test_save_training_data_no_rules_and_http_actions(self, get_training_data, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        path = 'tests/testing_data/all'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions, multiflow_stories, bot_content, chat_client_config = await get_training_data(
            path)

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, config, domain, story_graph, nlu, http_actions, multiflow_stories, bot_content,
                                           chat_client_config, overwrite=True)

        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 292
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 16
        assert story_graph.story_steps[14].events[2].intent['name'] == 'user_feedback'
        assert story_graph.story_steps[14].events[2].entities[0]['value'] == 'like'
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdresponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdresponse'
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 23
        assert domain.responses.keys().__len__() == 27
        assert domain.entities.__len__() == 23
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 27
        assert domain.intents.__len__() == 29
        assert not Utility.check_empty_string(
            domain.responses["utter_cheer_up"][0]["image"]
        )
        assert domain.responses["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.responses["utter_offer_help"][0]["custom"]
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert rules == ['ask the user to rephrase whenever they send a message with low nlu confidence']
        actions = mongo_processor.load_http_action(bot)
        assert not actions['http_action']
        assert Utterances.objects(bot=bot).count() == 27

    @pytest.mark.asyncio
    async def test_save_training_data_all_overwrite_slot_mapping(self, get_training_data, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com',
                'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        path = 'tests/testing_data/yml_training_files'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions, multiflow_stories, bot_content, chat_client_config = await get_training_data(
            path)
        domain.slots[0].mappings[0]['conditions'] = [{"active_loop": "ticket_attributes_form", "requested_slot": "date_time"}]
        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, config, domain, story_graph, nlu, http_actions, multiflow_stories, bot_content,
                                           chat_client_config, overwrite=True)

        slot_mapping = SlotMapping.objects(form_name="ticket_attributes_form").get()
        assert slot_mapping.slot == "date_time"

    @pytest.mark.asyncio
    async def test_save_training_data_all_overwrite(self, get_training_data, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        path = 'tests/testing_data/yml_training_files'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions, multiflow_stories, bot_content, chat_client_config = await get_training_data(
            path)

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, config, domain, story_graph, nlu, http_actions, multiflow_stories, bot_content,
                                           chat_client_config, overwrite=True)

        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 305
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 16
        assert story_graph.story_steps[14].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[14].events[2].entities[0].get('start')
        assert not story_graph.story_steps[14].events[2].entities[0].get('end')
        assert story_graph.story_steps[14].events[2].entities[0]['value'] == 'like'
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdresponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[15].events[2].entities[0].get('start')
        assert not story_graph.story_steps[15].events[2].entities[0].get('end')
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdresponse'
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 24
        assert len([slot for slot in domain.slots if slot.influence_conversation is True]) == 12
        assert len([slot for slot in domain.slots if slot.influence_conversation is False]) == 12
        assert domain.intent_properties.__len__() == 32
        assert len([intent for intent in domain.intent_properties.keys() if
                    domain.intent_properties.get(intent)['used_entities']]) == 27
        assert len([intent for intent in domain.intent_properties.keys() if
                    not domain.intent_properties.get(intent)['used_entities']]) == 5
        assert domain.responses.keys().__len__() == 29
        assert domain.entities.__len__() == 24
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 48
        assert domain.intents.__len__() == 32
        assert not Utility.check_empty_string(
            domain.responses["utter_cheer_up"][0]["image"]
        )
        assert domain.responses["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.responses["utter_offer_help"][0]["custom"]
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 4
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert len(actions['http_action']) == 17

    @pytest.mark.asyncio
    async def test_save_training_data_all_append(self, get_training_data, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        path = 'tests/testing_data/validator/append'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions, multiflow_stories, bot_content, chat_client_config = await get_training_data(
            path)

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, config, domain, story_graph, nlu, http_actions, multiflow_stories, bot_content,
                                           chat_client_config, overwrite=False,
                                           what=REQUIREMENTS.copy() - {"chat_client_config"})

        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 308
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 18
        assert story_graph.story_steps[14].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[14].events[2].entities[0].get('start')
        assert not story_graph.story_steps[14].events[2].entities[0].get('end')
        assert story_graph.story_steps[14].events[2].entities[0]['value'] == 'like'
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdresponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[15].events[2].entities[0].get('start')
        assert not story_graph.story_steps[15].events[2].entities[0].get('end')
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdresponse'
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 24
        assert len([slot for slot in domain.slots if slot.influence_conversation is True]) == 12
        assert len([slot for slot in domain.slots if slot.influence_conversation is False]) == 12
        assert domain.intent_properties.__len__() == 33
        assert len([intent for intent in domain.intent_properties.keys() if
                    domain.intent_properties.get(intent)['used_entities']]) == 27
        assert len([intent for intent in domain.intent_properties.keys() if
                    not domain.intent_properties.get(intent)['used_entities']]) == 6
        assert domain.responses.keys().__len__() == 31
        assert domain.entities.__len__() == 24
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 50
        assert domain.intents.__len__() == 33
        assert not Utility.check_empty_string(
            domain.responses["utter_cheer_up"][0]["image"]
        )
        assert domain.responses["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.responses["utter_offer_help"][0]["custom"]
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 4
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert len(actions['http_action']) == 17

    def test_delete_nlu_only(self):
        bot = 'test'
        user = 'test'
        mongo_processor = MongoProcessor()
        mongo_processor.delete_bot_data(bot, user, {"nlu"})
        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 0
        assert training_data.entity_synonyms.__len__() == 0
        assert training_data.regex_features.__len__() == 0
        assert training_data.lookup_tables.__len__() == 0
        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 18
        assert story_graph.story_steps[14].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[14].events[2].entities[0].get('start')
        assert not story_graph.story_steps[14].events[2].entities[0].get('end')
        assert story_graph.story_steps[14].events[2].entities[0]['value'] == 'like'
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdresponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[15].events[2].entities[0].get('start')
        assert not story_graph.story_steps[15].events[2].entities[0].get('end')
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdresponse'
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 24
        assert len([slot for slot in domain.slots if slot.influence_conversation is True]) == 12
        assert len([slot for slot in domain.slots if slot.influence_conversation is False]) == 12
        assert domain.intent_properties.__len__() == 33
        assert len([intent for intent in domain.intent_properties.keys() if
                    domain.intent_properties.get(intent)['used_entities']]) == 27
        assert len([intent for intent in domain.intent_properties.keys() if
                    not domain.intent_properties.get(intent)['used_entities']]) == 6
        assert domain.responses.keys().__len__() == 31
        assert domain.entities.__len__() == 24
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 50
        assert domain.intents.__len__() == 33
        assert not Utility.check_empty_string(
            domain.responses["utter_cheer_up"][0]["image"]
        )
        assert domain.responses["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.responses["utter_offer_help"][0]["custom"]
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 4
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert len(actions['http_action']) == 17

    @pytest.mark.asyncio
    async def test_save_nlu_only(self, get_training_data):
        path = 'tests/testing_data/yml_training_files'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions, multiflow_stories, bot_content, chat_client_config = await get_training_data(
            path)

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, nlu=nlu, overwrite=True, what={'nlu'})

        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 305
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1

    def test_delete_stories_only(self):
        bot = 'test'
        user = 'test'
        mongo_processor = MongoProcessor()
        mongo_processor.delete_bot_data(bot, user, {"stories"})
        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 305
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 0
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 24
        assert len([slot for slot in domain.slots if slot.influence_conversation is True]) == 12
        assert len([slot for slot in domain.slots if slot.influence_conversation is False]) == 12
        assert domain.intent_properties.__len__() == 33
        assert len([intent for intent in domain.intent_properties.keys() if
                    domain.intent_properties.get(intent)['used_entities']]) == 27
        assert len([intent for intent in domain.intent_properties.keys() if
                    not domain.intent_properties.get(intent)['used_entities']]) == 6
        assert domain.responses.keys().__len__() == 31
        assert domain.entities.__len__() == 24
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 50
        assert domain.intents.__len__() == 33
        assert not Utility.check_empty_string(
            domain.responses["utter_cheer_up"][0]["image"]
        )
        assert domain.responses["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.responses["utter_offer_help"][0]["custom"]
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 4
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert len(actions['http_action']) == 17

    def test_delete_multiflow_stories_only(self):
        bot = 'test'
        user = 'test'
        mongo_processor = MongoProcessor()
        mongo_processor.delete_bot_data(bot, user, {"multiflow_stories"})
        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 305
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 0
        multiflow_story = mongo_processor.load_linear_flows_from_multiflow_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 0
        print(multiflow_story)
        assert story_graph.story_steps.__len__() == 0
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 24
        assert len([slot for slot in domain.slots if slot.influence_conversation is True]) == 12
        assert len([slot for slot in domain.slots if slot.influence_conversation is False]) == 12
        assert domain.intent_properties.__len__() == 33
        assert len([intent for intent in domain.intent_properties.keys() if
                    domain.intent_properties.get(intent)['used_entities']]) == 27
        assert len([intent for intent in domain.intent_properties.keys() if
                    not domain.intent_properties.get(intent)['used_entities']]) == 6
        assert domain.responses.keys().__len__() == 31
        assert domain.entities.__len__() == 24
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 50
        assert domain.intents.__len__() == 33

    @pytest.mark.asyncio
    async def test_save_stories_only(self, get_training_data):
        path = 'tests/testing_data/yml_training_files'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions, multiflow_stories, bot_content, chat_client_config = await get_training_data(
            path)

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, story_graph=story_graph, overwrite=True, what={'stories'})

        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 16
        assert story_graph.story_steps[14].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[14].events[2].entities[0].get('start')
        assert not story_graph.story_steps[14].events[2].entities[0].get('end')
        assert story_graph.story_steps[14].events[2].entities[0]['value'] == 'like'
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdresponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[15].events[2].entities[0].get('start')
        assert not story_graph.story_steps[15].events[2].entities[0].get('end')
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdresponse'

    def test_delete_config_and_actions_only(self):
        bot = 'test'
        user = 'test'
        mongo_processor = MongoProcessor()
        mongo_processor.delete_bot_data(bot, user, {"config", "actions"})
        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 305
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 16
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 24
        assert domain.intent_properties.__len__() == 33
        assert domain.responses.keys().__len__() == 31
        assert domain.entities.__len__() == 24
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 31
        assert domain.intents.__len__() == 33
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 4
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert not actions['http_action']
        assert mongo_processor.load_config(bot)

    @pytest.mark.asyncio
    async def test_save_actions_and_config_only(self, get_training_data):
        path = 'tests/testing_data/yml_training_files'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions, multiflow_stories, bot_content, chat_client_config = await get_training_data(
            path)
        config['language'] = 'fr'

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, config=config, actions=http_actions, overwrite=True,
                                           what={'actions', 'config'})

        assert len(mongo_processor.load_http_action(bot)['http_action']) == 17
        config = mongo_processor.load_config(bot)
        assert config['language'] == 'fr'
        assert config['pipeline']
        assert config['policies']

    def test_delete_rules_and_domain_only(self):
        bot = 'test'
        user = 'test'
        mongo_processor = MongoProcessor()
        mongo_processor.delete_bot_data(bot, user, {"rules", "domain"})
        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 305
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 16
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 1
        assert domain.intent_properties.__len__() == 5
        assert domain.responses.keys().__len__() == 0
        assert domain.entities.__len__() == 0
        assert domain.form_names.__len__() == 0
        assert domain.user_actions.__len__() == 19
        assert domain.intents.__len__() == 5
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 0
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert len(actions['http_action']) == 17

    @pytest.mark.asyncio
    async def test_save_rules_and_domain_only(self, get_training_data):
        path = 'tests/testing_data/yml_training_files'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions, multiflow_stories, bot_content, chat_client_config = await get_training_data(
            path)

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, story_graph=story_graph, domain=domain, overwrite=True,
                                           what={'rules', 'domain'})

        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 3
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 24
        assert domain.intent_properties.__len__() == 32
        assert domain.responses.keys().__len__() == 27
        assert domain.entities.__len__() == 24
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 46
        assert domain.intents.__len__() == 32

    @pytest.fixture()
    def resource_prepare_training_data_for_validation_with_home_dir(self):
        tmp_dir = tempfile.mkdtemp()
        pytest.dir = tmp_dir
        yield 'resource_prepare_training_data_for_validation_with_home_dir'
        Utility.delete_directory(pytest.dir)

    @pytest.fixture()
    def resource_prepare_training_data_for_validation(self):
        yield 'resource_prepare_training_data_for_validation'
        Utility.delete_directory(os.path.join('training_data', 'test'))

    def test_prepare_training_data_for_validation_no_data(self, resource_prepare_training_data_for_validation):
        bot = 'test'
        processor = MongoProcessor()
        processor.prepare_training_data_for_validation(bot)
        bot_home = os.path.join('training_data', bot)
        assert os.path.exists(bot_home)
        dirs = os.listdir(bot_home)
        files = set(os.listdir(os.path.join(bot_home, dirs[0]))).union(
            os.listdir(os.path.join(bot_home, dirs[0], DEFAULT_DATA_PATH)))
        assert ALLOWED_DOMAIN_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_CONFIG_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_NLU_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_STORIES_FORMATS.intersection(files).__len__() == 1

    def test_prepare_training_data_for_validation_with_home_dir(self,
                                                                resource_prepare_training_data_for_validation_with_home_dir):
        bot = 'test'
        processor = MongoProcessor()
        processor.prepare_training_data_for_validation(bot, pytest.dir)
        bot_home = pytest.dir
        assert os.path.exists(bot_home)
        files = set(os.listdir(bot_home)).union(os.listdir(os.path.join(bot_home, DEFAULT_DATA_PATH)))
        assert ALLOWED_DOMAIN_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_CONFIG_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_NLU_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_STORIES_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_RULES_FORMATS.intersection(files).__len__() == 1

    @pytest.fixture()
    def resource_prepare_training_data_for_validation_nlu_only(self):
        pytest.nlu_only_tmp_dir = tempfile.mkdtemp()
        yield 'resource_prepare_training_data_for_validation_nlu_only'
        Utility.delete_directory(pytest.nlu_only_tmp_dir)

    @pytest.fixture()
    def resource_prepare_training_data_for_validation_rules_only(self):
        pytest.nlu_only_tmp_dir = tempfile.mkdtemp()
        yield 'resource_prepare_training_data_for_validation_rules_only'
        Utility.delete_directory(pytest.nlu_only_tmp_dir)

    def test_prepare_training_data_for_validation_nlu_domain_only(self,
                                                                  resource_prepare_training_data_for_validation_nlu_only):
        bot = 'test'
        processor = MongoProcessor()
        processor.prepare_training_data_for_validation(bot, pytest.nlu_only_tmp_dir, {'nlu', 'domain'})
        bot_home = pytest.nlu_only_tmp_dir
        assert os.path.exists(bot_home)
        files = set(os.listdir(os.path.join(bot_home))).union(
            os.listdir(os.path.join(bot_home, DEFAULT_DATA_PATH)))
        assert ALLOWED_DOMAIN_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_NLU_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_CONFIG_FORMATS.intersection(files).__len__() == 0
        assert ALLOWED_STORIES_FORMATS.intersection(files).__len__() == 0
        assert ALLOWED_RULES_FORMATS.intersection(files).__len__() == 0

    def test_prepare_training_data_for_validation_rules_only(self,
                                                             resource_prepare_training_data_for_validation_rules_only):
        bot = 'test'
        processor = MongoProcessor()
        processor.prepare_training_data_for_validation(bot, pytest.nlu_only_tmp_dir, {'rules'})
        bot_home = pytest.nlu_only_tmp_dir
        assert os.path.exists(bot_home)
        files = set(os.listdir(os.path.join(bot_home))).union(
            os.listdir(os.path.join(bot_home, DEFAULT_DATA_PATH)))
        assert ALLOWED_DOMAIN_FORMATS.intersection(files).__len__() == 0
        assert ALLOWED_NLU_FORMATS.intersection(files).__len__() == 0
        assert ALLOWED_CONFIG_FORMATS.intersection(files).__len__() == 0
        assert ALLOWED_STORIES_FORMATS.intersection(files).__len__() == 0
        assert ALLOWED_RULES_FORMATS.intersection(files).__len__() == 1

    def test_prepare_training_data_for_validation(self, resource_prepare_training_data_for_validation):
        bot = 'test'
        processor = MongoProcessor()
        processor.prepare_training_data_for_validation(bot)
        bot_home = os.path.join('training_data', bot)
        assert os.path.exists(bot_home)
        dirs = os.listdir(bot_home)
        files = set(os.listdir(os.path.join(bot_home, dirs[0]))).union(
            os.listdir(os.path.join(bot_home, dirs[0], DEFAULT_DATA_PATH)))
        assert ALLOWED_DOMAIN_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_CONFIG_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_NLU_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_STORIES_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_RULES_FORMATS.intersection(files).__len__() == 1

    @pytest.fixture()
    def resource_unzip_and_validate(self):
        pytest.bot = 'test_validate_and_prepare_data'
        data_path = 'tests/testing_data/yml_training_files'
        tmp_dir = tempfile.gettempdir()
        zip_file = os.path.join(tmp_dir, 'test')
        shutil.make_archive(zip_file, 'zip', data_path)
        pytest.zip = UploadFile(filename="test.zip", file=BytesIO(open(zip_file + '.zip', 'rb').read()))
        yield "resource_unzip_and_validate"
        os.remove(zip_file + '.zip')
        shutil.rmtree(os.path.join('training_data', pytest.bot))

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_zip(self, resource_unzip_and_validate):
        processor = MongoProcessor()
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', [pytest.zip], True)
        assert REQUIREMENTS == files_received
        assert is_event_data
        bot_data_home_dir = Utility.get_latest_file(os.path.join('training_data', pytest.bot))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'actions.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert not non_event_validation_summary

    @pytest.fixture()
    def resource_save_and_validate_training_files(self):
        pytest.bot = 'test_validate_and_prepare_data'
        config_path = 'tests/testing_data/yml_training_files/config.yml'
        chat_client_config_path = "tests/testing_data/yml_training_files/chat_client_config.yml"
        domain_path = 'tests/testing_data/yml_training_files/domain.yml'
        nlu_path = 'tests/testing_data/yml_training_files/data/nlu.yml'
        stories_path = 'tests/testing_data/yml_training_files/data/stories.yml'
        http_action_path = 'tests/testing_data/yml_training_files/actions.yml'
        rules_path = 'tests/testing_data/yml_training_files/data/rules.yml'
        pytest.config = UploadFile(filename="config.yml", file=BytesIO(open(config_path, 'rb').read()))
        pytest.chat_client_config = UploadFile(filename="chat_client_config.yml",
                                               file=BytesIO(open(chat_client_config_path, 'rb').read()))
        pytest.domain = UploadFile(filename="domain.yml", file=BytesIO(open(domain_path, 'rb').read()))
        pytest.nlu = UploadFile(filename="nlu.yml", file=BytesIO(open(nlu_path, 'rb').read()))
        pytest.stories = UploadFile(filename="stories.yml", file=BytesIO(open(stories_path, 'rb').read()))
        pytest.http_actions = UploadFile(filename="actions.yml", file=BytesIO(open(http_action_path, 'rb').read()))
        pytest.rules = UploadFile(filename="rules.yml", file=BytesIO(open(rules_path, 'rb').read()))
        pytest.non_nlu = UploadFile(filename="non_nlu.yml", file=BytesIO(open(rules_path, 'rb').read()))
        yield "resource_save_and_validate_training_files"
        shutil.rmtree(os.path.join('training_data', pytest.bot))

    @pytest.mark.asyncio
    async def test_load_chat_client_config(self, monkeypatch, resource_save_and_validate_training_files):
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        training_file = [pytest.chat_client_config]
        is_event_data = await processor.validate_and_log(pytest.bot, 'user@integration.com', training_file, True)
        chat_client_config = processor.load_chat_client_config(pytest.bot, 'user@integration.com')
        assert not is_event_data
        assert chat_client_config["config"]
        assert chat_client_config['white_listed_domain'] == ["*"]
        assert chat_client_config['config']['welcomeMessage'] == "Hello! How are you? This is Testing Welcome Message."
        assert chat_client_config['config']['name'] == "kairon_testing"
        assert not chat_client_config["config"].get('headers')
        assert not chat_client_config["config"].get('multilingual')
        assert not chat_client_config.get("_id")
        assert not chat_client_config.get("bot")
        assert not chat_client_config.get("status")
        assert not chat_client_config.get("user")
        assert not chat_client_config.get("timestamp")

    @pytest.mark.asyncio
    async def test_download_data_files_with_chat_client_config(self, monkeypatch,
                                                               resource_save_and_validate_training_files):
        from zipfile import ZipFile

        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        training_file = [pytest.chat_client_config]
        is_event_data = await processor.validate_and_log(pytest.bot, 'user@integration.com', training_file, True)
        file_path = processor.download_files(pytest.bot, "user@integration.com")
        assert file_path.endswith(".zip")
        zip_file = ZipFile(file_path, mode='r')
        assert zip_file.filelist.__len__() == 9
        assert zip_file.getinfo('chat_client_config.yml')

    @pytest.fixture()
    def resource_validate_and_prepare_data_save_actions_and_config_append(self):
        import ujson as json

        pytest.bot = 'test_validate_and_prepare_data'
        config = "language: fr\npipeline:\n- name: WhitespaceTokenizer\n- name: LexicalSyntacticFeaturizer\n-  name: DIETClassifier\npolicies:\n-  name: TEDPolicy".encode()
        actions = {"http_action": [
            {"action_name": "test_validate_and_prepare_data", "http_url": "http://www.alphabet.com",
             "request_method": "GET", "response": {"value": "json"}}]}
        actions = json.dumps(actions).encode('utf-8')
        pytest.config = UploadFile(filename="config.yml", file=BytesIO(config))
        pytest.http_actions = UploadFile(filename="actions.yml", file=BytesIO(actions))
        yield "resource_validate_and_prepare_data_save_actions_and_config_append"
        shutil.rmtree(os.path.join('training_data', pytest.bot))

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_training_files(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.config, pytest.domain, pytest.nlu, pytest.stories, pytest.http_actions, pytest.rules,
                         pytest.chat_client_config]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        assert REQUIREMENTS - {'multiflow_stories','bot_content'} == files_received
        assert is_event_data
        bot_data_home_dir = Utility.get_latest_file(os.path.join('training_data', pytest.bot))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'chat_client_config.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'actions.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert not non_event_validation_summary

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_nlu_only(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.nlu]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        assert {'nlu'} == files_received
        assert is_event_data
        bot_data_home_dir = Utility.get_latest_file(os.path.join('training_data', pytest.bot))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'actions.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert not non_event_validation_summary

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_stories_only(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.stories]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        assert {'stories'} == files_received
        assert is_event_data
        bot_data_home_dir = Utility.get_latest_file(os.path.join('training_data', pytest.bot))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'actions.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert not non_event_validation_summary

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_config(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.config]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        assert {'config'} == files_received
        assert not is_event_data
        assert not non_event_validation_summary.get("config")
        assert not non_event_validation_summary.get("http_actions")
        assert processor.list_http_actions(pytest.bot).__len__() == 0
        config = processor.load_config(pytest.bot)
        assert config['pipeline']
        assert config['policies']
        assert config['language']

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_chat_client_config(self, resource_save_and_validate_training_files,
                                                                     monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        training_file = [pytest.chat_client_config]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        assert {'chat_client_config'} == files_received
        assert not is_event_data
        assert not non_event_validation_summary.get("config")
        assert not non_event_validation_summary.get("http_actions")
        chat_client_config = processor.load_chat_client_config(pytest.bot, 'test')
        assert chat_client_config['config']
        assert chat_client_config['white_listed_domain'] == ["*"]
        assert chat_client_config['config']['welcomeMessage'] == "Hello! How are you? This is Testing Welcome Message."
        assert chat_client_config['config']['name'] == "kairon_testing"
        assert not chat_client_config.get("_id")
        assert not chat_client_config.get('status')
        assert not chat_client_config.get('user')
        assert not chat_client_config.get('bot')
        assert chat_client_config['white_listed_domain']

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_rules(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.rules]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        assert {'rules'} == files_received
        assert is_event_data
        bot_data_home_dir = Utility.get_latest_file(os.path.join('training_data', pytest.bot))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'actions.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert not non_event_validation_summary

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_actions(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.http_actions]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        print(non_event_validation_summary)
        assert {'actions'} == files_received
        assert not is_event_data
        assert not non_event_validation_summary.get("http_actions")
        assert not non_event_validation_summary.get("config")
        assert processor.list_http_actions(pytest.bot).__len__() == 17

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_domain(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.domain]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        assert {'domain'} == files_received
        assert is_event_data
        bot_data_home_dir = Utility.get_latest_file(os.path.join('training_data', pytest.bot))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'actions.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert not non_event_validation_summary

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_actions_and_config_overwrite(self,
                                                                               resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.http_actions, pytest.config]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        print(non_event_validation_summary)
        assert {'actions', 'config'} == files_received
        assert not is_event_data
        assert not non_event_validation_summary.get("http_actions")
        assert not non_event_validation_summary.get("config")
        assert processor.list_http_actions(pytest.bot).__len__() == 17
        config = processor.load_config(pytest.bot)
        assert config['pipeline']
        assert config['policies']
        assert config['language']

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_actions_and_config_append(self,
                                                                            resource_validate_and_prepare_data_save_actions_and_config_append):
        processor = MongoProcessor()
        training_file = [pytest.http_actions, pytest.config]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, False)
        assert {'actions', 'config'} == files_received
        assert not is_event_data
        assert not non_event_validation_summary.get("http_actions")
        assert not non_event_validation_summary.get("config")
        assert processor.list_http_actions(pytest.bot).__len__() == 18
        config = processor.load_config(pytest.bot)
        assert config['pipeline']
        assert config['policies']
        assert config['language'] == 'fr'

    @pytest.fixture()
    def resource_validate_and_prepare_data_no_valid_file_in_zip(self):
        data_path = 'tests/testing_data/validator'
        tmp_dir = tempfile.gettempdir()
        zip_file = os.path.join(tmp_dir, 'test')
        shutil.make_archive(zip_file, 'zip', data_path)
        pytest.zip = UploadFile(filename="test.zip", file=BytesIO(open(zip_file + '.zip', 'rb').read()))
        yield "resource_validate_and_prepare_data_no_valid_file_in_zip"
        os.remove(zip_file + '.zip')

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_no_valid_file_received(self,
                                                                    resource_validate_and_prepare_data_no_valid_file_in_zip):
        processor = MongoProcessor()
        bot = 'test_validate_and_prepare_data'
        with pytest.raises(AppException) as e:
            await processor.validate_and_prepare_data(bot, 'test', [pytest.zip], True)
        assert str(e).__contains__('Invalid files received')

    @pytest.fixture()
    def resource_validate_and_prepare_data_zip_actions_config(self):
        tmp_dir = tempfile.mkdtemp()
        pytest.bot = 'validate_and_prepare_data_zip_actions_config'
        zip_file = os.path.join(tmp_dir, 'test')
        shutil.copy2('tests/testing_data/yml_training_files/actions.yml', tmp_dir)
        shutil.copy2('tests/testing_data/yml_training_files/config.yml', tmp_dir)
        shutil.make_archive(zip_file, 'zip', tmp_dir)
        pytest.zip = UploadFile(filename="test.zip", file=BytesIO(open(zip_file + '.zip', 'rb').read()))
        yield "resource_validate_and_prepare_data_zip_actions_config"
        shutil.rmtree(tmp_dir)
        shutil.rmtree(os.path.join('training_data', pytest.bot))

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_zip_actions_config(self,
                                                                resource_validate_and_prepare_data_zip_actions_config):
        processor = MongoProcessor()
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', [pytest.zip], True)
        assert {'actions', 'config'} == files_received
        assert not is_event_data
        assert not non_event_validation_summary.get("http_actions")
        assert not non_event_validation_summary.get("config")
        assert processor.list_http_actions(pytest.bot).__len__() == 17
        config = processor.load_config(pytest.bot)
        assert config['pipeline']
        assert config['policies']
        assert config['language']

    @pytest.fixture()
    def resource_validate_and_prepare_data_invalid_zip_actions_config(self):
        import ujson as json
        tmp_dir = tempfile.mkdtemp()
        pytest.bot = 'validate_and_prepare_data_zip_actions_config'
        zip_file = os.path.join(tmp_dir, 'test')
        actions = Utility.read_yaml('tests/testing_data/yml_training_files/actions.yml')
        actions['http_action'][0].pop('action_name')
        actions['google_search_action'][0].pop('name')
        Utility.write_to_file(os.path.join(tmp_dir, 'actions.yml'), json.dumps(actions).encode())
        shutil.copy2('tests/testing_data/yml_training_files/config.yml', tmp_dir)
        shutil.make_archive(zip_file, 'zip', tmp_dir)
        pytest.zip = UploadFile(filename="test.zip", file=BytesIO(open(zip_file + '.zip', 'rb').read()))
        yield "resource_validate_and_prepare_data_zip_actions_config"
        shutil.rmtree(tmp_dir)
        shutil.rmtree(os.path.join('training_data', pytest.bot))

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_invalid_zip_actions_config(self,
                                                                        resource_validate_and_prepare_data_invalid_zip_actions_config):
        processor = MongoProcessor()
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', [pytest.zip], True)
        print(non_event_validation_summary)
        assert 'No name found for  [http_action]' in non_event_validation_summary['summary']['http_action'][0]
        assert files_received == {'actions', 'config'}
        assert not is_event_data

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_all_actions(self):
        with patch('kairon.shared.utils.SMTP'):
            with patch('kairon.shared.actions.data_objects.ZendeskAction.validate'):
                with patch('kairon.shared.actions.data_objects.JiraAction.validate'):
                    with patch('pipedrive.client.Client'):
                        processor = MongoProcessor()
                        BotSettings(bot='test_validate_and_prepare_data_all_actions', user='test',
                                    llm_settings=LLMSettings(enable_faq=True)).save()
                        actions = UploadFile(filename="actions.yml",
                                             file=BytesIO(open('tests/testing_data/actions/actions.yml', 'rb').read()))
                        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
                            'test_validate_and_prepare_data_all_actions', 'test', [actions], True)
                        assert non_event_validation_summary['summary'] == {
                            'http_action': [], 'slot_set_action': [], 'form_validation_action': [],
                            'email_action': [],
                            'google_search_action': [], 'jira_action': [], 'zendesk_action': [],
                            'pipedrive_leads_action': [], 'prompt_action': [], 'razorpay_action': [],
                            'pyscript_action': [], 'database_action': [], 'callback_action': [], 'callbackconfig': [],
                            'two_stage_fallback': [], 'schedule_action': [], 'web_search_action': [], 'live_agent_action': []
                        }
                        print(non_event_validation_summary)
                        assert non_event_validation_summary['component_count']['http_action'] == 4
                        assert non_event_validation_summary['component_count']['jira_action'] == 2
                        assert non_event_validation_summary['component_count']['google_search_action'] == 2
                        assert non_event_validation_summary['component_count']['zendesk_action'] == 2
                        assert non_event_validation_summary['component_count']['email_action'] == 2
                        assert non_event_validation_summary['component_count']['slot_set_action'] == 3
                        assert non_event_validation_summary['component_count']['form_validation_action'] == 4
                        assert non_event_validation_summary['component_count']['pipedrive_leads_action'] == 2
                        assert non_event_validation_summary['component_count']['prompt_action'] == 2
                        assert non_event_validation_summary['validation_failed'] is False
                        assert files_received == {'actions'}
                        assert not is_event_data
                        saved_actions = processor.load_action_configurations(
                            'test_validate_and_prepare_data_all_actions')
                        assert len(saved_actions['http_action']) == 4
                        assert len(saved_actions['slot_set_action']) == 3
                        assert len(saved_actions['form_validation_action']) == 4
                        assert len(saved_actions['jira_action']) == 2
                        assert len(saved_actions['google_search_action']) == 2
                        assert len(saved_actions['zendesk_action']) == 2
                        assert len(saved_actions['email_action']) == 2
                        assert len(saved_actions['pipedrive_leads_action']) == 2
                        assert len(saved_actions['prompt_action']) == 2
                        assert len(saved_actions['two_stage_fallback']) == 1
                        assert saved_actions['two_stage_fallback'][0]['name'] == "kairon_two_stage_fallback"
                        assert saved_actions['two_stage_fallback'][0]['text_recommendations'] == \
                               {'count': 0, 'use_intent_ranking': True}
                        assert saved_actions['two_stage_fallback'][0]['trigger_rules'] == \
                               [{'text': 'Hi', 'payload': 'greet', 'is_dynamic_msg': False}]
                        assert saved_actions['two_stage_fallback'][0]['fallback_message'] \
                               == "I could not understand you! Did you mean any of the suggestions below? " \
                                  "Or else please rephrase your question."

    @pytest.mark.asyncio
    async def test_load_action_configurations_with_two_stage_fallback(self):
        processor = MongoProcessor()
        saved_actions = processor.load_action_configurations('test_validate_and_prepare_data_all_actions')
        assert len(saved_actions['two_stage_fallback']) == 1
        two_stage_fallback_action = saved_actions['two_stage_fallback'][0]
        assert two_stage_fallback_action['name'] == "kairon_two_stage_fallback"
        assert two_stage_fallback_action['text_recommendations'] == {'count': 0, 'use_intent_ranking': True}
        assert two_stage_fallback_action['trigger_rules'] == [{'text': 'Hi', 'payload': 'greet',
                                                               'is_dynamic_msg': False}]
        assert two_stage_fallback_action['fallback_message'] \
               == "I could not understand you! Did you mean any of the suggestions below? " \
                  "Or else please rephrase your question."

    def test_save_component_properties_all(self):
        config = {"nlu_epochs": 200,
                  "response_epochs": 300,
                  "ted_epochs": 400,
                  "nlu_confidence_threshold": 0.6,
                  "action_fallback": "action_default_fallback"}
        Responses(name='utter_default', bot='test_all', user='test',
                  text=ResponseText(text='Sorry I didnt get that. Can you rephrase?')).save()
        processor = MongoProcessor()
        processor.save_component_properties(config, 'test_all', 'test')
        config = processor.load_config('test_all')
        nlu = next((comp for comp in config['pipeline'] if comp["name"] == "DIETClassifier"), None)
        assert nlu['name'] == 'DIETClassifier'
        assert nlu['epochs'] == 200
        response = next((comp for comp in config['pipeline'] if comp["name"] == "ResponseSelector"), None)
        assert response['name'] == 'ResponseSelector'
        assert response['epochs'] == 300
        action_fallback = next((comp for comp in config['policies'] if comp["name"] == "TEDPolicy"), None)
        assert action_fallback['name'] == 'TEDPolicy'
        assert action_fallback['epochs'] == 400
        nlu_fallback = next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        assert nlu_fallback['name'] == 'FallbackClassifier'
        assert nlu_fallback['threshold'] == 0.6
        rule_policy = next((comp for comp in config['policies'] if "RulePolicy" in comp["name"]), None)
        assert len(rule_policy) == 5
        assert rule_policy['core_fallback_action_name'] == 'action_default_fallback'
        assert rule_policy['core_fallback_threshold'] == 0.3
        expected = {'recipe': 'default.v1', 'language': 'en',
                    'pipeline': [{'name': 'WhitespaceTokenizer'}, {'name': 'RegexEntityExtractor'},
                                 {'model_name': 'bert', 'from_pt': True,
                                  'model_weights': 'google/bert_uncased_L-2_H-128_A-2',
                                  'name': 'kairon.shared.nlu.featurizer.lm_featurizer.LanguageModelFeaturizer'},
                                 {'name': 'LexicalSyntacticFeaturizer'},
                                 {'name': 'CountVectorsFeaturizer'},
                                 {'analyzer': 'char_wb', 'max_ngram': 4, 'min_ngram': 1,
                                  'name': 'CountVectorsFeaturizer'},
                                 {'epochs': 200, 'name': 'DIETClassifier'},
                                 {'name': 'FallbackClassifier', 'threshold': 0.6},
                                 {'name': 'EntitySynonymMapper'},
                                 {'epochs': 300, 'name': 'ResponseSelector'}],
                    'policies': [{'name': 'MemoizationPolicy'}, {'epochs': 400, 'max_history': 5, 'name': 'TEDPolicy'},
                                 {'core_fallback_action_name': 'action_default_fallback',
                                  'core_fallback_threshold': 0.3, 'enable_fallback_prediction': True,
                                  'max_history': 5,
                                  'name': 'RulePolicy'}]}
        assert not DeepDiff(config, expected, ignore_order=True)

    def test_get_config_properties(self):
        expected = {'nlu_confidence_threshold': 0.6,
                    'action_fallback_threshold': 0.3,
                    'action_fallback': 'action_default_fallback',
                    'ted_epochs': 400,
                    'nlu_epochs': 200,
                    'response_epochs': 300}
        processor = MongoProcessor()
        config = processor.list_epoch_and_fallback_config('test_all')
        assert config == expected

    def test_save_component_properties_action_fallback_threshold_greater(self):
        config = {"nlu_epochs": 200,
                  "response_epochs": 300,
                  "ted_epochs": 400,
                  "nlu_confidence_threshold": 0.6,
                  "action_fallback_threshold": 0.7,
                  "action_fallback": "action_default_fallback"}
        processor = MongoProcessor()
        with pytest.raises(AppException,
                           match='Action fallback threshold should always be smaller than nlu fallback threshold'):
            processor.save_component_properties(config, 'test_all', 'test')

    def test_save_component_properties_action_fallback(self):
        config = {"nlu_epochs": 200,
                  "response_epochs": 300,
                  "ted_epochs": 400,
                  "nlu_confidence_threshold": 0.6,
                  "action_fallback_threshold": 0.6,
                  "action_fallback": "action_default_fallback"}
        processor = MongoProcessor()
        processor.save_component_properties(config, 'test_all', 'test')
        config = processor.load_config('test_all')
        nlu = next((comp for comp in config['pipeline'] if comp["name"] == "DIETClassifier"), None)
        assert nlu['name'] == 'DIETClassifier'
        assert nlu['epochs'] == 200
        response = next((comp for comp in config['pipeline'] if comp["name"] == "ResponseSelector"), None)
        assert response['name'] == 'ResponseSelector'
        assert response['epochs'] == 300
        action_fallback = next((comp for comp in config['policies'] if comp["name"] == "TEDPolicy"), None)
        assert action_fallback['name'] == 'TEDPolicy'
        assert action_fallback['epochs'] == 400
        nlu_fallback = next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        assert nlu_fallback['name'] == 'FallbackClassifier'
        assert nlu_fallback['threshold'] == 0.6
        rule_policy = next((comp for comp in config['policies'] if "RulePolicy" in comp["name"]), None)
        assert len(rule_policy) == 5
        assert rule_policy['core_fallback_action_name'] == 'action_default_fallback'
        assert rule_policy['core_fallback_threshold'] == 0.6

    def test_get_config_properties_action_fallback(self):
        expected = {'nlu_confidence_threshold': 0.6,
                    'action_fallback_threshold': 0.6,
                    'action_fallback': 'action_default_fallback',
                    'ted_epochs': 400,
                    'nlu_epochs': 200,
                    'response_epochs': 300}
        processor = MongoProcessor()
        config = processor.list_epoch_and_fallback_config('test_all')
        assert config == expected

    def test_save_component_properties_epoch_only(self):
        config = {"nlu_epochs": 200,
                  "response_epochs": 300,
                  "ted_epochs": 400}
        processor = MongoProcessor()
        processor.save_component_properties(config, 'test_epoch_only', 'test')
        config = processor.load_config('test_epoch_only')
        nlu = next((comp for comp in config['pipeline'] if comp["name"] == "DIETClassifier"), None)
        assert nlu['name'] == 'DIETClassifier'
        assert nlu['epochs'] == 200
        response = next((comp for comp in config['pipeline'] if comp["name"] == "ResponseSelector"), None)
        assert response['name'] == 'ResponseSelector'
        assert response['epochs'] == 300
        ted = next((comp for comp in config['policies'] if comp["name"] == "TEDPolicy"), None)
        assert ted['name'] == 'TEDPolicy'
        assert ted['epochs'] == 400
        expected = {'recipe': 'default.v1', 'language': 'en',
                    'pipeline': [{'name': 'WhitespaceTokenizer'}, {'name': 'RegexEntityExtractor'},
                                 {'model_name': 'bert', 'from_pt': True,
                                  'model_weights': 'google/bert_uncased_L-2_H-128_A-2',
                                  'name': 'kairon.shared.nlu.featurizer.lm_featurizer.LanguageModelFeaturizer'},
                                 {'name': 'LexicalSyntacticFeaturizer'},
                                 {'name': 'CountVectorsFeaturizer'},
                                 {'analyzer': 'char_wb', 'max_ngram': 4, 'min_ngram': 1,
                                  'name': 'CountVectorsFeaturizer'},
                                 {'epochs': 200, 'name': 'DIETClassifier'},
                                 {'name': 'EntitySynonymMapper'},
                                 {'name': 'FallbackClassifier', 'threshold': 0.7},
                                 {'epochs': 300, 'name': 'ResponseSelector'}],
                    'policies': [{'name': 'MemoizationPolicy'}, {'epochs': 400, 'max_history': 5, 'name': 'TEDPolicy'},
                                 {'core_fallback_action_name': 'action_default_fallback',
                                  'core_fallback_threshold': 0.5, 'enable_fallback_prediction': True,
                                  'max_history': 5,
                                  'name': 'RulePolicy'}]}
        assert not DeepDiff(config, expected, ignore_order=True)

    def test_get_config_properties_epoch_only(self):
        expected = {'nlu_confidence_threshold': 0.7, 'action_fallback': 'action_default_fallback',
                    'action_fallback_threshold': 0.5, 'ted_epochs': 400, 'nlu_epochs': 200, 'response_epochs': 300}
        processor = MongoProcessor()
        config = processor.list_epoch_and_fallback_config('test_epoch_only')
        assert config == expected

    def test_save_component_properties_empty(self, monkeypatch):
        monkeypatch.setitem(Utility.environment["model"]["train"], "default_model_training_config_path",
                            "./tests/testing_data/kairon-default.yml")
        processor = MongoProcessor()
        with pytest.raises(AppException) as e:
            processor.save_component_properties({}, 'test_properties_empty', 'test')
        assert str(e).__contains__('At least one field is required')
        config = processor.load_config('test_properties_empty')
        assert config == Utility.read_yaml('./tests/testing_data/kairon-default.yml')
        nlu = next((comp for comp in config['pipeline'] if comp["name"] == "DIETClassifier"), None)
        assert nlu['name'] == 'DIETClassifier'
        assert nlu['epochs'] == 5
        response = next((comp for comp in config['pipeline'] if comp["name"] == "ResponseSelector"), None)
        assert response['name'] == 'ResponseSelector'
        assert response['epochs'] == 5
        ted = next((comp for comp in config['policies'] if comp["name"] == "TEDPolicy"), None)
        assert ted['name'] == 'TEDPolicy'
        assert ted['epochs'] == 5

    def test_get_config_properties_fallback_not_set(self):
        expected = {'nlu_confidence_threshold': 0.7, 'action_fallback': 'action_default_fallback',
                    'action_fallback_threshold': 0.5, 'ted_epochs': 10, 'nlu_epochs': 5, 'response_epochs': 10}
        processor = MongoProcessor()
        config = processor.list_epoch_and_fallback_config('test_fallback_not_set')
        assert config == expected

    def test_list_epochs_for_components_not_present(self):
        configs = Configs._from_son(
            read_config_file("./tests/testing_data/kairon-default.yml")
        ).to_mongo().to_dict()
        del configs['pipeline'][4]
        del configs['pipeline'][6]
        del configs['policies'][1]
        processor = MongoProcessor()
        processor.save_config(configs, 'test_list_component_not_exists', 'test')

        expected = {'nlu_confidence_threshold': 0.7, 'action_fallback': 'action_default_fallback',
                    'action_fallback_threshold': 0.5, 'ted_epochs': None, 'nlu_epochs': 5, 'response_epochs': 5}
        processor = MongoProcessor()
        actual = processor.list_epoch_and_fallback_config('test_list_component_not_exists')
        assert actual == expected

    def test_save_component_properties_component_not_exists(self):
        configs = Configs._from_son(
            read_config_file("./tests/testing_data/kairon-default.yml")
        ).to_mongo().to_dict()
        del configs['pipeline'][5]
        del configs['pipeline'][7]
        del configs['policies'][1]
        processor = MongoProcessor()
        processor.save_config(configs, 'test_component_not_exists', 'test')

        config = {"nlu_epochs": 10,
                  "response_epochs": 10,
                  "ted_epochs": 10}
        processor = MongoProcessor()
        processor.save_component_properties(config, 'test_component_not_exists', 'test')
        config = processor.load_config('test_component_not_exists')
        diet = next((comp for comp in config['pipeline'] if comp["name"] == "DIETClassifier"), None)
        assert diet['name'] == 'DIETClassifier'
        assert diet['epochs'] == 10
        response = next((comp for comp in config['pipeline'] if comp["name"] == "ResponseSelector"), None)
        assert response['name'] == 'ResponseSelector'
        assert response['epochs'] == 10
        ted = next((comp for comp in config['policies'] if comp["name"] == "TEDPolicy"), None)
        assert ted['name'] == 'TEDPolicy'
        assert ted['epochs'] == 10

    def test_save_component_fallback_not_configured(self):
        Actions(name='action_say_bye', bot='test_fallback_not_configured', user='test').save()
        configs = Configs._from_son(
            read_config_file("./tests/testing_data/kairon-default.yml")
        ).to_mongo().to_dict()
        del configs['pipeline'][6]
        del configs['policies'][2]
        processor = MongoProcessor()
        processor.save_config(configs, 'test_fallback_not_configured', 'test')

        config = {'nlu_confidence_threshold': 0.8,
                  'action_fallback': 'action_say_bye'}
        processor = MongoProcessor()
        processor.save_component_properties(config, 'test_fallback_not_configured', 'test')
        config = processor.load_config('test_fallback_not_configured')
        expected = {'recipe': 'default.v1', 'language': 'en',
                    'pipeline': [{'name': 'WhitespaceTokenizer'}, {'name': 'RegexEntityExtractor'},
                                 {'model_name': 'bert', 'from_pt': True,
                                  'model_weights': 'google/bert_uncased_L-2_H-128_A-2',
                                  'name': 'kairon.shared.nlu.featurizer.lm_featurizer.LanguageModelFeaturizer'},
                                 {'name': 'LexicalSyntacticFeaturizer'},
                                 {'name': 'CountVectorsFeaturizer'},
                                 {'epochs': 5, 'name': 'DIETClassifier'},
                                 {'name': 'FallbackClassifier', 'threshold': 0.8},
                                 {'epochs': 5, 'name': 'ResponseSelector'}],
                    'policies': [{'name': 'MemoizationPolicy'}, {'epochs': 5, 'name': 'TEDPolicy'},
                                 {'name': 'RulePolicy', 'max_history': 5, 'core_fallback_action_name': 'action_say_bye',
                                  'core_fallback_threshold': 0.3}]}
        assert not DeepDiff(config, expected, ignore_order=True)

    def test_save_component_properties_nlu_fallback_only(self):
        nlu_fallback = {"nlu_confidence_threshold": 0.75}
        processor = MongoProcessor()
        processor.save_component_properties(nlu_fallback, 'test_nlu_fallback_only', 'test')
        config = processor.load_config('test_nlu_fallback_only')
        nlu_fallback = next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        assert nlu_fallback['name'] == 'FallbackClassifier'
        assert nlu_fallback['threshold'] == 0.75
        rule_policy = next((comp for comp in config['policies'] if "RulePolicy" in comp["name"]), None)
        assert len(rule_policy) == 5
        expected = {'recipe': 'default.v1', 'language': 'en',
                    'pipeline': [{'name': 'WhitespaceTokenizer'}, {'name': 'RegexEntityExtractor'},
                                 {'model_name': 'bert', 'from_pt': True,
                                  'model_weights': 'google/bert_uncased_L-2_H-128_A-2',
                                  'name': 'kairon.shared.nlu.featurizer.lm_featurizer.LanguageModelFeaturizer'},
                                 {'name': 'LexicalSyntacticFeaturizer'},
                                 {'name': 'CountVectorsFeaturizer'},
                                 {'analyzer': 'char_wb', 'max_ngram': 4, 'min_ngram': 1,
                                  'name': 'CountVectorsFeaturizer'},
                                 {'epochs': 5, 'name': 'DIETClassifier'},
                                 {'name': 'FallbackClassifier', 'threshold': 0.75},
                                 {'name': 'EntitySynonymMapper'},
                                 {'epochs': 10, 'name': 'ResponseSelector'}],
                    'policies': [{'name': 'MemoizationPolicy'}, {'epochs': 10, 'max_history': 5, 'name': 'TEDPolicy'},
                                 {'core_fallback_action_name': 'action_default_fallback',
                                  'core_fallback_threshold': 0.5, 'enable_fallback_prediction': True,
                                  'max_history': 5,
                                  'name': 'RulePolicy'}]}
        assert not DeepDiff(config, expected)

    def test_save_component_properties_all_nlu_fallback_update_threshold(self):
        nlu_fallback = {"nlu_confidence_threshold": 0.7}
        processor = MongoProcessor()
        processor.save_component_properties(nlu_fallback, 'test_nlu_fallback_only', 'test')
        config = processor.load_config('test_nlu_fallback_only')
        nlu_fallback = next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        assert nlu_fallback['name'] == 'FallbackClassifier'
        assert nlu_fallback['threshold'] == 0.7
        rule_policy = next((comp for comp in config['policies'] if "RulePolicy" in comp["name"]), None)
        assert len(rule_policy) == 5

    def test_save_component_properties_action_fallback_only(self):
        nlu_fallback = {'action_fallback': 'action_say_bye'}
        Actions(name='action_say_bye', bot='test_action_fallback_only', user='test').save()
        processor = MongoProcessor()
        processor.save_component_properties(nlu_fallback, 'test_action_fallback_only', 'test')
        config = processor.load_config('test_action_fallback_only')
        assert next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        rule_policy = next((comp for comp in config['policies'] if "RulePolicy" in comp["name"]), None)
        assert len(rule_policy) == 5
        assert rule_policy['core_fallback_action_name'] == 'action_say_bye'
        assert rule_policy['core_fallback_threshold'] == 0.3
        expected = {'recipe': 'default.v1', 'language': 'en',
                    'pipeline': [{'name': 'WhitespaceTokenizer'}, {'name': 'RegexEntityExtractor'},
                                 {'model_name': 'bert', 'from_pt': True,
                                  'model_weights': 'google/bert_uncased_L-2_H-128_A-2',
                                  'name': 'kairon.shared.nlu.featurizer.lm_featurizer.LanguageModelFeaturizer'},
                                 {'name': 'LexicalSyntacticFeaturizer'},
                                 {'name': 'CountVectorsFeaturizer'},
                                 {'analyzer': 'char_wb', 'max_ngram': 4, 'min_ngram': 1,
                                  'name': 'CountVectorsFeaturizer'},
                                 {'epochs': 5, 'name': 'DIETClassifier'},
                                 {'name': 'EntitySynonymMapper'},
                                 {'name': 'FallbackClassifier', 'threshold': 0.7},
                                 {'epochs': 10, 'name': 'ResponseSelector'}],
                    'policies': [{'name': 'MemoizationPolicy'}, {'epochs': 10, 'max_history': 5, 'name': 'TEDPolicy'},
                                 {'core_fallback_action_name': 'action_say_bye', 'core_fallback_threshold': 0.3,
                                  'enable_fallback_prediction': True, 'max_history': 5, 'name': 'RulePolicy'}]}
        assert not DeepDiff(config, expected, ignore_order=True)

    def test_save_component_properties_all_action_fallback_update(self):
        nlu_fallback = {'action_fallback': 'action_say_bye_bye'}
        Actions(name='action_say_bye_bye', bot='test_action_fallback_only', user='test').save()
        processor = MongoProcessor()
        processor.save_component_properties(nlu_fallback, 'test_action_fallback_only', 'test')
        config = processor.load_config('test_action_fallback_only')
        assert next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        rule_policy = next((comp for comp in config['policies'] if "RulePolicy" in comp["name"]), None)
        assert len(rule_policy) == 5
        assert rule_policy['core_fallback_action_name'] == 'action_say_bye_bye'
        assert rule_policy['core_fallback_threshold'] == 0.3

    def test_save_component_properties_all_action_fallback_action_not_exists(self):
        nlu_fallback = {'action_fallback': 'action_say_hello'}
        processor = MongoProcessor()
        with pytest.raises(AppException) as e:
            processor.save_component_properties(nlu_fallback, 'test_action_fallback_only', 'test')
        assert str(e).__contains__("Action fallback action_say_hello does not exists")
        config = processor.load_config('test_action_fallback_only')
        assert next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        rule_policy = next((comp for comp in config['policies'] if "RulePolicy" in comp["name"]), None)
        assert len(rule_policy) == 5
        assert rule_policy['core_fallback_action_name'] == 'action_say_bye_bye'
        assert rule_policy['core_fallback_threshold'] == 0.3

    def test_save_component_properties_all_action_fallback_utter_default_not_set(self):
        nlu_fallback = {'action_fallback': 'action_default_fallback'}
        processor = MongoProcessor()
        Responses.objects(name="utter_default", bot="test_action_fallback_only").delete()
        with pytest.raises(AppException) as e:
            processor.save_component_properties(nlu_fallback, 'test_action_fallback_only', 'test')
        assert str(e).__contains__("Utterance utter_default not defined")
        config = processor.load_config('test_action_fallback_only')
        assert next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        rule_policy = next((comp for comp in config['policies'] if "RulePolicy" in comp["name"]), None)
        assert len(rule_policy) == 5
        assert rule_policy['core_fallback_action_name'] == 'action_say_bye_bye'
        assert rule_policy['core_fallback_threshold'] == 0.3

    def test_save_component_properties_all_action_fallback_utter_default_set(self):
        nlu_fallback = {'action_fallback': 'action_default_fallback'}
        Responses(name='utter_default', bot='test_action_fallback_only', user='test',
                  text={'text': 'Sorry I didnt get that. Can you rephrase?'}).save()
        processor = MongoProcessor()
        processor.save_component_properties(nlu_fallback, 'test_action_fallback_only', 'test')
        config = processor.load_config('test_action_fallback_only')
        assert next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        rule_policy = next((comp for comp in config['policies'] if "RulePolicy" in comp["name"]), None)
        assert len(rule_policy) == 5
        assert rule_policy['core_fallback_action_name'] == 'action_default_fallback'
        assert rule_policy['core_fallback_threshold'] == 0.3

    def test_add_synonym(self):
        processor = MongoProcessor()
        bot = 'add_synonym'
        user = 'test_user'
        processor.add_synonym("bot", bot, user)

        with pytest.raises(AppException, match="Synonym already exists!"):
            processor.add_synonym("bot", bot, user)

        with pytest.raises(ValidationError, match="Synonym cannot be empty or blank spaces"):
            processor.add_synonym(" ", bot, user)

        with pytest.raises(TypeError):
            processor.add_synonym(None, bot, user)

    def test_add_synonym_single_value(self):
        processor = MongoProcessor()
        bot = 'add_synonym_single_value'
        user = 'test_user'
        processor.add_synonym("bot", bot, user)
        processor.add_synonym_value("exp", "bot", bot, user)
        syn = list(EntitySynonyms.objects(name__exact='bot', bot=bot, user=user))
        assert syn[0]['name'] == "bot"
        assert syn[0]['value'] == "exp"

        with pytest.raises(AppException, match="Synonym value already exists"):
            processor.add_synonym_value(
                "exp", "bot", bot, user)

        with pytest.raises(ValidationError, match="Synonym name and value cannot be empty or blank spaces"):
            processor.add_synonym_value(
                " ", "bot", bot, user)

        with pytest.raises(TypeError):
            processor.add_synonym_value(
                None, "bot", bot, user)

        with pytest.raises(ValidationError, match="Synonym name and value cannot be empty or blank spaces"):
            processor.add_synonym_value(
                "exp", " ", bot, user)

        with pytest.raises(TypeError):
            processor.add_synonym_value(
                "exp", None, bot, user)

    def test_add__and_get_synonym(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        processor.add_synonym("bot", bot, user)
        processor.add_synonym_values(
            {"name": "bot", "value": ["exp"]}, bot, user)
        syn = list(EntitySynonyms.objects(name__iexact='bot', bot=bot, user=user))
        assert syn[0]['name'] == "bot"
        assert syn[0]['value'] == "exp"

    def test_get_specific_synonym(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        response = list(processor.get_synonym_values("bot", bot))
        assert response[0]["value"] == "exp"

    def test_add_duplicate_synonym(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        with pytest.raises(AppException) as exp:
            processor.add_synonym_values({"name": "bot", "value": ["exp"]}, bot, user)
        assert str(exp.value) == "Synonym value already exists"

    def test_edit_specific_synonym(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        response = list(processor.get_synonym_values("bot", bot))
        processor.edit_synonym(response[0]["_id"], "exp2", "bot", bot, user)
        response = list(processor.get_synonym_values("bot", bot))
        assert response[0]["value"] == "exp2"

    def test_edit_synonym_duplicate(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        response = list(processor.get_synonym_values("bot", bot))
        with pytest.raises(AppException):
            processor.edit_synonym(response[0]["_id"], "exp2", "bot", bot, user)

    def test_edit_synonym_unavailable(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        response = list(processor.get_synonym_values("bot", bot))
        with pytest.raises(AppException):
            processor.edit_synonym(response[0]["_id"], "exp3", "bottt", bot, user)

    def test_add_delete_synonym_value(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        processor.add_synonym_values({"name": "bot", "value": ["exp"]}, bot, user)
        response = list(processor.get_synonym_values("bot", bot))
        assert len(response) == 2
        processor.delete_synonym_value("bot", response[0]["_id"], bot, user=user)
        response = list(processor.get_synonym_values("bot", bot))
        assert len(response) == 1

    def test_delete_synonym_value_empty(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_synonym_value(" ", "df", "ff")

    def test_delete_non_existent_synonym(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_synonym_value(value_id="0123456789ab0123456789ab", synonym_name="df", bot="ff")

    def test_delete_synonym_name(self):
        processor = MongoProcessor()
        bot = 'test_delete_synonym'
        synonym_id = processor.add_synonym("bot", bot, "test")
        response = list(processor.fetch_synonyms(bot))
        assert len(response) == 1

        processor.add_synonym_value("test", "bot", bot, "test")
        response = list(processor.get_synonym_values("bot", bot))
        assert len(response) == 1

        processor.delete_synonym(synonym_id, bot, user="test")
        response = list(processor.fetch_synonyms(bot))
        assert len(response) == 0

        response = list(processor.get_synonym_values("bot", bot))
        assert len(response) == 0

    def test_delete_synonym_name_empty(self):
        processor = MongoProcessor()
        with pytest.raises(ValidationError):
            processor.delete_synonym(" ", "df")

    def test_delete_non_existent_synonym_name(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_synonym(id="0123456789ab0123456789ab", bot="df")

    def test_add_empty_synonym(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        with pytest.raises(AppException) as exp:
            processor.add_synonym_values({"synonym": "", "value": ["exp"]}, bot, user)
        assert str(exp.value) == "Synonym name cannot be an empty!"

    def test_add_synonym_with_empty_value_list(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        with pytest.raises(AppException) as exp:
            processor.add_synonym_values({"name": "bot", "value": []}, bot, user)
        assert str(exp.value) == "Synonym value cannot be an empty!"

    def test_add_synonym_with_empty_element_in_value_list(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        with pytest.raises(AppException) as exp:
            processor.add_synonym_values({"name": "bot", "value": ["df", '']}, bot, user)
        assert str(exp.value) == "Synonym value cannot be an empty!"

    def test_add_utterance(self):
        processor = MongoProcessor()
        processor.add_utterance_name('test_add', 'test', 'testUser')

    def test_add_utterance_already_exists(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Utterance exists'):
            processor.add_utterance_name('test_add', 'test', 'testUser', raise_error_if_exists=True)

    def test_add_utterance_empty(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Name cannot be empty'):
            processor.add_utterance_name(' ', 'test', 'testUser', True)

    def test_utterance_data_object(self):
        with pytest.raises(ValidationError, match='Utterance Name cannot be empty or blank spaces'):
            Utterances(name=' ', bot='test', user='user').save()

    def test_add_utterance_already_exists_no_exc(self):
        processor = MongoProcessor()
        assert not processor.add_utterance_name('test_add', 'test', 'testUser')

    def test_get_utterance(self):
        processor = MongoProcessor()
        actual = list(processor.get_utterances('test'))
        assert len(actual) == 28

    def test_delete_utterance_name_does_not_exists(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Utterance not found'):
            processor.delete_utterance_name('test_add_1', 'test', raise_exc=True)

    def test_delete_utterance_name_does_not_exists_no_exc(self):
        processor = MongoProcessor()
        processor.delete_utterance_name('test_add_1', 'test')

    def test_delete_utterance_name(self):
        processor = MongoProcessor()
        processor.delete_utterance_name('test_add', 'test', user="test")

    def test_get_bot_settings_not_added(self):
        processor = MongoProcessor()
        settings = processor.get_bot_settings('not_created', 'test')
        assert not settings.ignore_utterances
        assert not settings.force_import
        assert settings.status
        assert settings.timestamp
        assert settings.user
        assert settings.bot
        assert settings.llm_settings.to_mongo().to_dict() == {'enable_faq': False, 'provider': 'openai'}

    def test_get_bot_settings(self):
        processor = MongoProcessor()
        settings = BotSettings.objects(bot='not_created').get()
        settings.ignore_utterances = True
        settings.force_import = True
        settings.save()
        fresh_settings = processor.get_bot_settings('not_created', 'test')
        assert fresh_settings.ignore_utterances
        assert fresh_settings.force_import
        assert fresh_settings.status
        assert fresh_settings.timestamp
        assert fresh_settings.user
        assert fresh_settings.bot
        assert settings.llm_settings.to_mongo().to_dict() == {'enable_faq': False, 'provider': 'openai'}

    def test_save_bot_settings_error(self):
        with pytest.raises(ValidationError, match="refresh_token_expiry must be greater than chat_token_expiry!"):
            BotSettings(chat_token_expiry=60, refresh_token_expiry=60, bot="test", user="test").save()

    def test_save_chat_client_config_not_exists(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {'name': 'test', 'account': 1, 'user': 'user@integration.com', 'status': True}

        def _mock_list_bot_accessors(*args, **kwargs):
            yield {'accessor_email': 'user@integration.com'}

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        monkeypatch.setattr(AccountProcessor, 'list_bot_accessors', _mock_list_bot_accessors)
        processor = MongoProcessor()
        config_path = "./template/chat-client/default-config.json"
        config = json.load(open(config_path))
        processor.save_chat_client_config(config, 'test', 'testUser')
        saved_config = ChatClientConfig.objects(bot='test').get()
        assert saved_config.config == config
        assert saved_config.user == 'testUser'
        assert saved_config.timestamp
        assert saved_config.status

    def test_save_chat_client_config(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {'name': 'test', 'account': 1, 'user': 'user@integration.com', 'status': True}

        def _mock_list_bot_accessors(*args, **kwargs):
            yield {'accessor_email': 'user@integration.com'}

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        monkeypatch.setattr(AccountProcessor, 'list_bot_accessors', _mock_list_bot_accessors)
        processor = MongoProcessor()
        config_path = "./template/chat-client/default-config.json"
        config = json.load(open(config_path))
        config['headers'] = {}
        config['headers']['authorization'] = 'Bearer eygbsbvuyfhbsfinlasfmishfiufnasfmsnf'
        config['headers']['X-USER'] = 'user@integration.com'
        processor.save_chat_client_config(config, 'test', 'testUser')
        saved_config = ChatClientConfig.objects(bot='test').get()
        assert saved_config.config == config
        assert saved_config.status
        assert saved_config.white_listed_domain == ["*"]

    def test_get_chat_client_config_not_exists(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        config_path = "./template/chat-client/default-config.json"
        expected_config = json.load(open(config_path))
        actual_config = processor.get_chat_client_config('test_bot', 'user@integration.com')
        assert actual_config.config['headers']['authorization']['access_token']
        assert actual_config.config['headers']['authorization']['token_type'] == 'Bearer'
        assert actual_config.config['headers']['authorization']['refresh_token']
        assert actual_config.config['headers']['authorization']['access_token_ttl'] == 30
        assert actual_config.config['headers']['authorization']['refresh_token_ttl'] == 60
        ate = actual_config.config['headers']['authorization']['access_token_expiry']
        rte = actual_config.config['headers']['authorization']['refresh_token_expiry']
        ate_minutes = round((datetime.utcfromtimestamp(ate) - datetime.utcnow()).total_seconds() / 60)
        rte_minutes = round((datetime.utcfromtimestamp(rte) - datetime.utcnow()).total_seconds() / 60)
        assert 31 >= ate_minutes >= 29
        assert 61 >= rte_minutes >= 59
        assert actual_config.config['headers']['X-USER'] == 'user@integration.com'
        assert actual_config.config['api_server_host_url']
        del actual_config.config['api_server_host_url']
        assert actual_config.config['nudge_server_url']
        del actual_config.config['nudge_server_url']
        assert 'chat_server_base_url' in actual_config.config
        actual_config.config.pop('chat_server_base_url')
        actual_config.config.pop('live_agent_socket_url')
        headers = actual_config.config.pop('headers')
        expected_config['multilingual'] = {'enable': False, 'bots': []}
        expected_config['live_agent_enabled'] = True
        assert expected_config == actual_config.config

        primary_token_claims = Utility.decode_limited_access_token(headers['authorization']['access_token'])
        iat = datetime.fromtimestamp(primary_token_claims.get('iat'), tz=timezone.utc)
        claims = Utility.decode_limited_access_token(headers['authorization']['refresh_token'])
        assert claims['iat'] == primary_token_claims.get('iat')
        refresh_token_expiry = datetime.fromtimestamp(claims['exp'], tz=timezone.utc)
        assert round((refresh_token_expiry - iat).total_seconds() / 60) == 60
        del claims['iat']
        del claims['exp']
        assert claims == {'ttl': 30, 'bot': 'test_bot', 'sub': 'user@integration.com', 'type': 'refresh',
                          'role': 'tester', 'account': 2,
                          'primary-token-type': TOKEN_TYPE.DYNAMIC.value,
                          'primary-token-role': 'chat', 'primary-token-access-limit': [
                '/api/bot/.+/chat', '/api/bot/.+/agent/live/.+', '/api/bot/.+/conversation',
                '/api/bot/.+/metric/user/logs/user_metrics'
            ], 'access-limit': ['/api/auth/.+/token/refresh']}

    def test_get_chat_client_config_live_agent_enabled_false(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com',
                'status': True,
                "metadata": {"source_bot_id": None}
            }
        def _mock_is_live_agent_service_available(*args, **kwargs):
            return False
        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        monkeypatch.setattr(LiveAgentHandler, 'is_live_agent_service_available', _mock_is_live_agent_service_available)
        processor = MongoProcessor()
        actual_config = processor.get_chat_client_config('test_bot', 'user@integration.com')
        assert actual_config.config['live_agent_enabled'] == False


    def test_save_chat_client_config_without_whitelisted_domain(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {'name': 'test', 'account': 1, 'user': 'user@integration.com', 'status': True}

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        config_path = "./template/chat-client/default-config.json"
        config = json.load(open(config_path))
        config['headers'] = {}
        config['headers']['authorization'] = 'Bearer eygbsbvuyfhbsfinlasfmishfiufnasfmsnf'
        config['headers']['X-USER'] = 'user@integration.com'
        config.pop("whitelist")
        processor.save_chat_client_config(config, 'test', 'testUser')
        saved_config = ChatClientConfig.objects(bot='test').get()
        assert saved_config.config == config
        assert saved_config.status
        assert saved_config.white_listed_domain == ["*"]

    def test_save_chat_client_config_valid_white_list(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {'name': 'test', 'account': 1, 'user': 'user@integration.com', 'status': True}

        def _mock_list_bot_accessors(*args, **kwargs):
            yield {'accessor_email': 'user@integration.com'}

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        monkeypatch.setattr(AccountProcessor, 'list_bot_accessors', _mock_list_bot_accessors)
        processor = MongoProcessor()
        config_path = "./template/chat-client/default-config.json"
        config = json.load(open(config_path))
        config['headers'] = {}
        config['headers']['authorization'] = 'Bearer eygbsbvuyfhbsfinlasfmishfiufnasfmsnf'
        config['headers']['X-USER'] = 'user@integration.com'
        config['whitelist'] = ["kairon.digite.com", "kairon-api.digite.com"]
        processor.save_chat_client_config(config, 'test', 'testUser')
        saved_config = ChatClientConfig.objects(bot='test').get()
        assert saved_config.config == config
        assert saved_config.status
        assert saved_config.white_listed_domain == ["kairon.digite.com", "kairon-api.digite.com"]

    def test_validate_white_listed_domain_success(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {'name': 'test', 'account': 1, 'user': 'user@integration.com', 'status': True}

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/",
            "headers": Headers({
                'host': 'kairon.digite.com',
                'accept': 'application/json',
                'referer': 'https://kairon.digite.com'
            }).raw,
            "server": ("kairon.digite.com", 443),
        }

        request = Request(scope=scope)
        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        config_path = "./template/chat-client/default-config.json"
        config = json.load(open(config_path))
        config['headers'] = {}
        config['headers']['authorization'] = 'Bearer eygbsbvuyfhbsfinlasfmishfiufnasfmsnf'
        config['headers']['X-USER'] = 'user@integration.com'
        config['whitelist'] = ["kairon.digite.com", "kairon-api.digite.com"]
        processor.save_chat_client_config(config, 'test', 'testUser')

        fetched_config = processor.get_chat_client_config('test', 'user@integration.com')
        fetched_config = fetched_config.to_mongo().to_dict()
        assert Utility.validate_request(request, fetched_config)

    def test_validate_white_listed_domain_attackers(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {'name': 'test', 'account': 1, 'user': 'user@integration.com', 'status': True}

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/",
            "headers": Headers({
                'host': 'kairon.digite.com',
                'accept': 'application/json',
                'referer': 'http://attackers.com'
            }).raw,
            "server": ("kairon.digite.com", 443),
        }

        request = Request(scope=scope)
        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        config_path = "./template/chat-client/default-config.json"
        config = json.load(open(config_path))
        config['headers'] = {}
        config['headers']['authorization'] = 'Bearer eygbsbvuyfhbsfinlasfmishfiufnasfmsnf'
        config['headers']['X-USER'] = 'user@integration.com'
        config['whitelist'] = ["kairon.digite.com", "kairon-api.digite.com"]
        processor.save_chat_client_config(config, 'test', 'testUser')

        fetched_config = processor.get_chat_client_config('test', 'user@integration.com')
        fetched_config = fetched_config.to_mongo().to_dict()
        assert not Utility.validate_request(request, fetched_config)

    def test_get_chat_client_config(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {'name': 'test', 'account': 1, 'user': 'user@integration.com', 'status': True}

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        actual_config = processor.get_chat_client_config('test', 'user@integration.com')
        assert actual_config.config['headers']['authorization']
        assert actual_config.config['headers']['X-USER'] == 'user@integration.com'

    def test_get_chat_client_config_default_not_found(self, monkeypatch):
        def _mock_exception(*args, **kwargs):
            raise AppException('Config not found')

        def _mock_bot_info(*args, **kwargs):
            return {'name': 'test', 'account': 1, 'user': 'user@integration.com', 'status': True}

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        monkeypatch.setattr(os.path, 'exists', _mock_exception)
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Config not found'):
            processor.get_chat_client_config('test_bot', 'user@integration.com')

    def test_add__and_get_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        processor.add_regex(
            {"name": "bot", "pattern": "exp"}, bot, user)
        reg = RegexFeatures.objects(name__iexact='bot', bot=bot, user=user).get()
        assert reg['name'] == "bot"
        assert reg['pattern'] == "exp"

    def test_add__duplicate_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        with pytest.raises(AppException) as e:
            processor.add_regex({"name": "bot", "pattern": "f"}, bot=bot, user=user)
        assert str(e).__contains__("Regex name already exists!")

    def test_add__empty_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        with pytest.raises(AppException) as e:
            processor.add_regex({"name": "", "pattern": "f"}, bot=bot, user=user)
        assert str(e).__contains__("Regex name and pattern cannot be empty or blank spaces")

    def test_edit__and_get_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        processor.edit_regex(
            {"name": "bot", "pattern": "exp1"}, bot, user)
        reg = RegexFeatures.objects(name__iexact='bot', bot=bot, user=user).get()
        assert reg['name'] == "bot"
        assert reg['pattern'] == "exp1"

    def test_edit__unavailable_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        with pytest.raises(AppException) as e:
            processor.edit_regex({"name": "bot1", "pattern": "f"}, bot=bot, user=user)
        assert str(e).__contains__("Regex name does not exist!")

    def test_edit__empty_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        with pytest.raises(AppException) as e:
            processor.edit_regex({"name": "bot", "pattern": ""}, bot=bot, user=user)
        assert str(e).__contains__("Regex name and pattern cannot be empty or blank spaces")

    def test_delete__unavailable_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        with pytest.raises(AppException) as e:
            processor.delete_regex("f", bot=bot, user=user)
        assert str(e).__contains__("Regex name does not exist.")

    def test_delete__and_get_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        processor.delete_regex("bot", bot, user)
        with pytest.raises(DoesNotExist):
            RegexFeatures.objects(name__iexact='bot', bot=bot, status=True).get()

    def test_add__invalid_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        with pytest.raises(AppException) as e:
            processor.add_regex({"name": "bot11", "pattern": "[0-9]++"}, bot=bot, user=user)
        assert str(e).__contains__("invalid regular expression")

    def test_add_lookup(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup_value'
        user = 'test_user'

        processor.add_lookup("number", bot, user)
        processor.add_lookup_value("number", "one", bot, user)

        with pytest.raises(ValidationError, match="Lookup name and value cannot be empty or blank spaces"):
            processor.add_lookup_value("number", " ", bot, user)

        with pytest.raises(TypeError):
            processor.add_lookup_value("number", None, bot, user)

        with pytest.raises(ValidationError, match="Lookup name and value cannot be empty or blank spaces"):
            processor.add_lookup_value("number", "one", bot, user)

        with pytest.raises(ValidationError, match="Lookup name and value cannot be empty or blank spaces"):
            processor.add_lookup_value(" ", "one", bot, user)

        with pytest.raises(TypeError):
            processor.add_lookup_value(None, "one", bot, user)

    def test_add_lookup(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup'
        user = 'test_user'

        processor.add_lookup("number", bot, user)

        with pytest.raises(ValidationError, match="Lookup cannot be empty or blank spaces"):
            processor.add_lookup(" ", bot, user)

        with pytest.raises(TypeError):
            processor.add_lookup(None, bot, user)

        with pytest.raises(AppException, match="Lookup already exists!"):
            processor.add_lookup("number", bot, user)

    def test_add__and_get_lookup_values(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup_values'
        user = 'test_user'
        processor.add_lookup("number", bot, user)
        processor.add_lookup_values(
            {"name": "number", "value": ["one"]}, bot, user)
        table = list(LookupTables.objects(name__iexact='number', bot=bot, user=user))
        assert table[0]['name'] == "number"
        assert table[0]['value'] == "one"

    def test_get_specific_lookup(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup_values'
        response = list(processor.get_lookup_values("number", bot))
        assert response[0]["value"] == "one"

    def test_add_duplicate_lookup(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup_values'
        user = 'test_user'
        with pytest.raises(AppException) as exp:
            processor.add_lookup_values({"name": "number", "value": ["one"]}, bot, user)
        assert str(exp.value) == "Lookup value already exists"

    def test_edit_specific_lookup(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup_values'
        user = 'test_user'
        response = list(processor.get_lookup_values("number", bot))
        processor.edit_lookup_value(response[0]["_id"], "two", "number", bot, user)
        response = list(processor.get_lookup_values("number", bot))
        assert response[0]["value"] == "two"

    def test_edit_lookup_duplicate(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup_values'
        user = 'test_user'
        response = list(processor.get_lookup_values("number", bot))
        with pytest.raises(AppException):
            processor.edit_lookup_value(response[0]["_id"], "two", "number", bot, user)

    def test_edit_lookup_unavailable(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup_values'
        user = 'test_user'
        response = list(processor.get_lookup_values("number", bot))
        with pytest.raises(AppException):
            processor.edit_lookup_value(response[0]["_id"], "exp3", "bottt", bot, user)

    def test_add_delete_lookup_value(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup_values'
        user = 'test_user'
        processor.add_lookup_values({"name": "number", "value": ["one"]}, bot, user)
        response = list(processor.get_lookup_values("number", bot))
        assert len(response) == 2
        processor.delete_lookup_value(response[0]["_id"], "number", bot, user)
        response = list(processor.get_lookup_values("number", bot))
        assert len(response) == 1

    def test_delete_lookup_value_empty(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_lookup_value(" ", "df", "test", "test_user")

    def test_delete_non_existent_lookup(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_lookup_value("0123456789ab0123456789ab", "df", "test", "test_user")

    def test_delete_lookup_name(self):
        processor = MongoProcessor()
        bot = 'test_delete_lookup'
        user = 'test_user'
        lookup_id = processor.add_lookup("bot", bot, user)
        processor.add_lookup_value("bot", "exp", bot, user)
        assert len(list(processor.get_lookups(bot))) == 1
        assert len(list(processor.get_lookup_values("bot", bot))) == 1
        processor.delete_lookup(lookup_id, bot, user)
        response = list(processor.get_lookups(bot))
        assert len(response) == 0
        response = list(processor.get_lookup_values("bot", bot))
        assert len(response) == 0

    def test_delete_lookup_name_empty(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_lookup(" ", "df", "test")

    def test_delete_non_existent_lookup_name(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_lookup("0123456789ab0123456789ab", "df", "test")

    def test_add_empty_lookup(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup_values'
        user = 'test_user'
        with pytest.raises(AppException) as exp:
            processor.add_lookup_values({"name": "", "value": ["exp"]}, bot, user)
        assert str(exp.value) == "Lookup cannot be an empty string"

    def test_add_lookup_with_empty_value_list(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup_values'
        user = 'test_user'
        with pytest.raises(AppException) as exp:
            processor.add_lookup_values({"name": "bot", "value": []}, bot, user)
        assert str(exp.value) == "Lookup value cannot be an empty string"

    def test_add_lookup_with_empty_element_in_value_list(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup_values'
        user = 'test_user'
        processor.add_lookup("bot", bot, user)
        with pytest.raises(AppException) as exp:
            processor.add_lookup_values({"name": "bot", "value": ["df", '']}, bot, user)
        assert str(exp.value) == "Lookup value cannot be an empty string"

    def test_add_slot_mapping_slot_not_added(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        expected_slot = {"slot": "cuisine", 'mapping': {'type': 'from_entity', 'entity': 'name'}}
        with pytest.raises(AppException, match='Slot with name \"cuisine\" not found'):
            processor.add_slot_mapping(expected_slot, bot, user)

    def test_add_slot_with_mapping(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        expected_slot = {"slot": "name", 'mapping': {'type': 'from_intent', 'value': 'user'}}
        processor.add_slot_mapping(expected_slot, bot, user)
        slot = SlotMapping.objects(slot='name', bot=bot, user=user).get()
        assert slot.mapping == {'type': 'from_intent', 'value': 'user'}

    def test_add_slot_with_empty_mapping(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        expected_slot = {"slot": "name", 'mapping': {}}
        with pytest.raises(ValueError, match='At least one mapping is required'):
            processor.add_slot_mapping(expected_slot, bot, user)


    def test_update_slot_with_mapping(self):
        expected_slot = {"name": "age", "type": "float", "influence_conversation": True}
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        processor.add_slot(expected_slot, bot, user, raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='age', bot=bot, user=user).get()
        assert slot['name'] == 'age'
        assert slot['type'] == 'float'
        assert slot['initial_value'] is None
        assert slot['influence_conversation']

        expected_slot = {"slot": "age",
                         'mapping': {'type': 'from_intent', 'intent': ['get_age'], 'entity': 'age', 'value': '18',
                                      "conditions": [{"active_loop": "booking", "requested_slot": "age"}]}}
        processor.add_slot_mapping(expected_slot, bot, user)
        slot = Slots.objects(name__iexact='age', bot=bot, user=user).get()
        assert slot['name'] == 'age'
        assert slot['type'] == 'float'
        assert slot['initial_value'] is None
        assert slot['influence_conversation']
        slot = SlotMapping.objects(slot='age', bot=bot, user=user).get()
        assert slot.mapping == {'type': 'from_intent', 'intent': ['get_age'], 'value': '18',
                                 "conditions": [{"active_loop": "booking", "requested_slot": "age"}]}

    def test_remove_slot_mapping(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        processor.add_slot({"name": "occupation", "type": "text", "influence_conversation": True}, bot, user)
        expected_slot = {"slot": "occupation",
                         'mapping': [{'type': 'from_intent', 'intent': ['get_occupation'], 'value': 'business'},
                                     {'type': 'from_text', 'value': 'engineer',
                                      "conditions": [{"active_loop": "booking", "requested_slot": "engineer"}]},
                                     {'type': 'from_entity', 'entity': 'occupation'},
                                     {'type': 'from_trigger_intent', 'value': 'tester',
                                      'intent': ['get_business', 'is_engineer', 'is_tester'],
                                      'not_intent': ['get_age', 'get_name']}]}
        expected_slots = []
        for m in expected_slot['mapping']:
            expected_slots.append({"slot": "occupation", "mapping": m})
        for slot in expected_slots:
            processor.add_slot_mapping(slot, bot, user)
        processor.delete_slot_mapping("occupation", bot, user)
        slot = Slots.objects(name__iexact='occupation', bot=bot, user=user).get()
        assert slot['name'] == 'occupation'
        assert slot['type'] == 'text'
        assert slot['initial_value'] is None
        assert slot['influence_conversation']
        with pytest.raises(DoesNotExist):
            SlotMapping.objects(slot='occupation', bot=bot, status=True).get()
        expected_slots=[]
        expected_slot = {"slot": "occupation", 'mapping': [
            {'type': 'from_intent', 'intent': ['get_occupation'], 'value': 'business'},
            {'type': 'from_text', 'value': 'engineer',
             "conditions": [{"active_loop": "booking", "requested_slot": "engineer"}]},
            {'type': 'from_entity', 'entity': 'occupation'},
            {'type': 'from_trigger_intent', 'value': 'tester',
             'intent': ['get_business', 'is_engineer', 'is_tester'],
             'not_intent': ['get_age', 'get_name']}]}
        for m in expected_slot['mapping']:
            expected_slots.append({"slot": "occupation", "mapping": m})
        for slot in expected_slots:
            processor.add_slot_mapping(slot, bot, user)
        slots = SlotMapping.objects(slot='occupation', bot=bot, status=True)
        assert len(list(slots)) == 4


    def test_get_slot(self):
        bot = 'test'
        processor = MongoProcessor()
        slots = list(processor.get_existing_slots(bot))
        expected = [
            {'name': 'kairon_action_response', 'type': 'any', 'influence_conversation': False, '_has_been_set': False},
            {'name': 'bot', 'type': 'any', 'initial_value': 'test', 'influence_conversation': False,
             '_has_been_set': False},
            {'name': 'order', 'type': 'any', 'influence_conversation': False, '_has_been_set': False},
            {'name': 'payment', 'type': 'any', 'influence_conversation': False, '_has_been_set': False},
            {'name': 'flow_reply', 'type': 'any', 'influence_conversation': False, '_has_been_set': False},
            {'name': 'http_status_code', 'type': 'any', 'influence_conversation': False, '_has_been_set': False},
            {'name': 'image', 'type': 'text', 'influence_conversation': True, '_has_been_set': False},
            {'name': 'audio', 'type': 'text', 'influence_conversation': True, '_has_been_set': False},
            {'name': 'video', 'type': 'text', 'influence_conversation': True, '_has_been_set': False},
            {'name': 'document', 'type': 'text', 'influence_conversation': True, '_has_been_set': False},
            {'name': 'doc_url', 'type': 'text', 'influence_conversation': True, '_has_been_set': False},
            {'name': 'longitude', 'type': 'text', 'influence_conversation': True, '_has_been_set': False},
            {'name': 'latitude', 'type': 'text', 'influence_conversation': True, '_has_been_set': False},
            {'name': 'date_time', 'type': 'text', 'influence_conversation': True, '_has_been_set': False},
            {'name': 'category', 'type': 'text', 'influence_conversation': False, '_has_been_set': False},
            {'name': 'file', 'type': 'text', 'influence_conversation': False, '_has_been_set': False},
            {'name': 'file_error', 'type': 'text', 'influence_conversation': False, '_has_been_set': False},
            {'name': 'file_text', 'type': 'text', 'influence_conversation': False, '_has_been_set': False},
            {'name': 'name', 'type': 'text', 'influence_conversation': True, '_has_been_set': False},
            {'name': 'priority', 'type': 'categorical', 'values': ['low', 'medium', 'high', '__other__'],
             'influence_conversation': True, '_has_been_set': False},
            {'name': 'ticketid', 'type': 'float', 'initial_value': 1.0, 'max_value': 1.0, 'min_value': 0.0,
             'influence_conversation': True, '_has_been_set': False},
            {'name': 'age', 'type': 'float', 'max_value': 1.0, 'min_value': 0.0, 'influence_conversation': True,
             '_has_been_set': False},
            {'name': 'occupation', 'type': 'text', 'influence_conversation': True, '_has_been_set': False},
            {'name': 'quick_reply', 'type': 'text', 'influence_conversation': True, '_has_been_set': False}
        ]
        assert len(slots) == 24
        assert not DeepDiff(slots, expected, ignore_order=True)

    def test_update_slot_add_value_intent_and_not_intent(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        processor.add_slot({"name": "location", "type": "text", "influence_conversation": True}, bot, user)
        slot = {"slot": "location", 'mapping': {'type': 'from_text', 'value': 'user', 'entity': 'location'}}

        slot2 = {"slot": "location", 'mapping': {'type': 'from_entity', 'entity': 'location'}}
        id1 = processor.add_slot_mapping(slot, bot, user)
        id2 = processor.add_slot_mapping(slot2, bot, user)

        slots = [{"slot": "age", 'mapping': {'type': 'from_intent', 'intent': ['retrieve_age', 'ask_age'],
                                              'not_intent': ['get_age', 'affirm', 'deny'], 'value': 20}},
                 {"slot": "location",
                  'mapping': {'type': 'from_intent', 'intent': ['get_location'], 'value': 'Mumbai'}},
                 {"slot": "location",
                  'mapping': {'type': 'from_text', 'value': 'Bengaluru'}}]

        processor.add_slot_mapping(slots[0], bot, user)
        processor.update_slot_mapping(slots[1], id1)
        processor.update_slot_mapping(slots[2], id2)

        slots = list(processor.get_slot_mappings(bot))
        diff = DeepDiff(slots,
                        [{'slot': 'age', 'mapping': [{'type': 'from_intent', 'value': '18', 'intent': ['get_age'], 'conditions': [{'active_loop': 'booking', 'requested_slot': 'age'}]}, {'type': 'from_intent', 'value': 20, 'intent': ['retrieve_age', 'ask_age'], 'not_intent': ['get_age', 'affirm', 'deny']}]}, {'slot': 'date_time', 'mapping': [{'type': 'from_entity', 'entity': 'date_time'}]}, {'slot': 'file', 'mapping': [{'type': 'from_entity', 'entity': 'file'}]}, {'slot': 'location', 'mapping': [{'type': 'from_intent', 'value': 'Mumbai', 'intent': ['get_location']}, {'type': 'from_text', 'value': 'Bengaluru'}]}, {'slot': 'name', 'mapping': [{'type': 'from_intent', 'value': 'user'}]}, {'slot': 'occupation', 'mapping': [{'type': 'from_intent', 'value': 'business', 'intent': ['get_occupation']}, {'type': 'from_text', 'value': 'engineer', 'conditions': [{'active_loop': 'booking', 'requested_slot': 'engineer'}]}, {'type': 'from_entity', 'entity': 'occupation'}, {'type': 'from_trigger_intent', 'value': 'tester', 'intent': ['get_business', 'is_engineer', 'is_tester'], 'not_intent': ['get_age', 'get_name']}]}, {'slot': 'priority', 'mapping': [{'type': 'from_entity', 'entity': 'priority'}]}],
                        ignore_order=True,
                        )
        assert not diff

    def test_add_form_with_any_slot(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['what is your name?', 'name?'], 'slot': 'name',
                 'slot_set': {'type': 'custom', 'value': 'Mahesh'}},
                {'ask_questions': ['what is your age?', 'age?'], 'slot': 'age',
                 'slot_set': {'type': 'current', 'value': 22}},
                {'ask_questions': ['what is your occupation?', 'occupation?'], 'slot': 'occupation',
                 'slot_set': {'type': 'slot', 'value': 'occupation'}},
                {'ask_questions': ['what is your order?', 'order?'], 'slot': 'order',
                 'slot_set': {'type': 'slot', 'value': 'order'}}
                ]
        bot = 'test'
        user = 'user'
        with pytest.raises(AppException, match="form will not accept any type slots: {'order'}"):
            processor.add_form('know_user', path, bot, user)

    def test_add_form(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['what is your name?', 'name?'], 'slot': 'name',
                 'slot_set': {'type': 'custom', 'value': 'Mahesh'}},
                {'ask_questions': ['what is your age?', 'age?'], 'slot': 'age',
                 'slot_set': {'type': 'current', 'value': 22}},
                {'ask_questions': ['what is your occupation?', 'occupation?'], 'slot': 'occupation',
                 'slot_set': {'type': 'slot', 'value': 'occupation'}}]
        bot = 'test'
        user = 'user'
        assert processor.add_form('know_user', path, bot, user)
        form = Forms.objects(name='know_user', bot=bot).get()
        assert form.required_slots == ['name', 'age', 'occupation']
        assert Utterances.objects(name='utter_ask_know_user_name', bot=bot,
                                  status=True).get().form_attached == 'know_user'
        assert Utterances.objects(name='utter_ask_know_user_age', bot=bot,
                                  status=True).get().form_attached == 'know_user'
        assert Utterances.objects(name='utter_ask_know_user_occupation', bot=bot,
                                  status=True).get().form_attached == 'know_user'
        resp = list(Responses.objects(name='utter_ask_know_user_name', bot=bot, status=True))
        assert resp[0].text.text == 'what is your name?'
        assert resp[1].text.text == 'name?'
        resp = list(Responses.objects(name='utter_ask_know_user_age', bot=bot, status=True))
        assert resp[0].text.text == 'what is your age?'
        assert resp[1].text.text == 'age?'
        resp = list(Responses.objects(name='utter_ask_know_user_occupation', bot=bot, status=True))
        assert resp[0].text.text == 'what is your occupation?'
        assert resp[1].text.text == 'occupation?'

    def test_add_utterance_to_form(self):
        bot = 'test'
        user = 'user'
        processor = MongoProcessor()
        assert processor.add_text_response('your occupation?', 'utter_ask_know_user_occupation', bot, user, 'know_user')

    def test_delete_utterance_from_form_2(self):
        bot = 'test'
        user = 'user'
        processor = MongoProcessor()
        resp = list(Responses.objects(name='utter_ask_know_user_occupation', bot=bot, status=True))
        assert resp[0].text.text == 'what is your occupation?'
        assert resp[1].text.text == 'occupation?'
        assert resp[2].text.text == 'your occupation?'
        assert not processor.delete_response(str(resp[2].id), bot, user=user)

    def test_add_utterance_to_form_not_exists(self):
        bot = 'test'
        user = 'user'
        processor = MongoProcessor()
        with pytest.raises(AppException, match="Form 'know_user_here' does not exists"):
            processor.add_text_response('give occupation', 'utter_ask_know_user_occupation', bot, user,
                                        'know_user_here')

    def test_create_flow_with_empty_step_name(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "", "type": "FORM_ACTION"},
            {"name": "know_user", "type": "FORM_START"},
            {"type": "FORM_END"},
            {"name": "utter_submit", "type": "BOT"},
        ]
        story_dict = {'name': "activate form", 'steps': steps, 'type': 'RULE', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="Empty name is allowed only for active_loop"):
            processor.add_complex_story(story_dict, bot, user)

    def test_create_flow_with_invalid_slot_value(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "age", "type": "SLOT", "value": {'a': 1}},
            {"name": "utter_greet", "type": "BOT"},
        ]
        story_dict = {'name': "slot form one", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="slot values must be either None or of type int, str or boolean"):
            processor.add_complex_story(story_dict, bot, user)

    def test_create_flow_with_invalid_events(self):
        bot = 'test'
        user = 'user'
        steps = [
            {"name": "hi", "type": "user"},
            {"name": "utter_hi", "type": "action", "value": "Hello"},
        ]
        events = [StoryEvents(**step) for step in steps]
        with pytest.raises(ValidationError, match="Value is allowed only for slot events"):
            Stories(block_name="invalid events flow", bot=bot, user=user, events=events).save()

    def test_create_flow_with_int_slot_value(self):
        processor = MongoProcessor()
        story_name = "slot form two"
        bot = 'test'
        user = 'user'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "age", "type": "SLOT", "value": 23},
            {"name": "utter_greet", "type": "BOT"},
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name=story_name, bot=bot).get()
        assert len(story['events']) == 3

    def test_create_flow_with_none_slot_value(self):
        processor = MongoProcessor()
        story_name = "slot form three"
        bot = 'test'
        user = 'user'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "age", "type": "SLOT", "value": None},
            {"name": "utter_greet", "type": "BOT"},
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name=story_name, bot=bot).get()
        assert len(story['events']) == 3

    def test_create_flow_with_bool_slot_value(self):
        processor = MongoProcessor()
        story_name = "slot form four"
        bot = 'test'
        user = 'user'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "food", "type": "SLOT", "value": True},
            {"name": "utter_greet", "type": "BOT"},
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name=story_name, bot=bot).get()
        assert len(story['events']) == 3

    def test_create_flow_with_str_slot_value(self):
        processor = MongoProcessor()
        story_name = "slot form five"
        bot = 'test'
        user = 'user'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "cuisine", "type": "SLOT", "value": 'Indian'},
            {"name": "utter_greet", "type": "BOT"},
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name=story_name, bot=bot).get()
        assert len(story['events']) == 3

    def test_create_two_stage_fallback_rule(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "nlu_fallback", "type": "INTENT"},
            {"name": KAIRON_TWO_STAGE_FALLBACK, "type": "TWO_STAGE_FALLBACK_ACTION"}
        ]
        story_dict = {'name': "activate two stage fallback", 'steps': steps, 'type': 'RULE', 'template_type': 'CUSTOM'}
        pytest.two_stage_fallback_story_id = processor.add_complex_story(story_dict, bot, user)
        rule = Rules.objects(block_name="activate two stage fallback", bot=bot,
                             events__name=KAIRON_TWO_STAGE_FALLBACK, status=True).get()
        assert rule.to_mongo().to_dict()['events'] == [{'name': '...', 'type': 'action'},
                                                       {'name': 'nlu_fallback', 'type': 'user'},
                                                       {'name': KAIRON_TWO_STAGE_FALLBACK, 'type': 'action'}]
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == "activate two stage fallback"]
        assert story_with_form[0]['steps'] == steps

    def test_create_form_activation_and_deactivation_rule(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "know_user", "type": "FORM_ACTION"},
            {"name": "know_user", "type": "FORM_START"},
            {"type": "FORM_END"},
            {"name": "utter_submit", "type": "BOT"},
        ]
        story_dict = {'name': "activate form", 'steps': steps, 'type': 'RULE', 'template_type': 'CUSTOM'}
        pytest.activate_form_story_id = processor.add_complex_story(story_dict, bot, user)
        rule = Rules.objects(block_name="activate form", bot=bot, events__name='know_user', status=True).get()
        assert rule.events[2].type == 'action'
        assert rule.events[3].name == 'know_user'
        assert rule.events[3].type == 'active_loop'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'activate form']
        assert story_with_form[0]['steps'] == steps

    def test_create_unhappy_path_form_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "know_user", "type": "FORM_ACTION"},
            {"name": "know_user", "type": "FORM_START"},
            {"name": "deny", "type": "INTENT"},
            {"name": "utter_ask_continue", "type": "BOT"},
            {"name": "affirm", "type": "INTENT"},
            {"type": "FORM_END"},
            {"name": "utter_submit", "type": "BOT"},
        ]
        story_dict = {'name': "stop form + continue", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        pytest.form_continue_story_id = processor.add_complex_story(story_dict, bot, user)
        stories = Stories.objects(block_name="stop form + continue", bot=bot, events__name='know_user',
                                  status=True).get()
        assert stories.events[1].type == 'action'
        assert stories.events[2].type == 'active_loop'
        assert stories.events[2].name == 'know_user'
        assert stories.events[6].type == 'active_loop'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'stop form + continue']
        assert story_with_form[0]['steps'] == steps

    def test_create_unhappy_path_form_story_to_breakout(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "know_user", "type": "FORM_ACTION"},
            {"name": "know_user", "type": "FORM_START"},
            {"name": "deny", "type": "INTENT"},
            {"name": "utter_ask_continue", "type": "BOT"},
            {"name": "deny", "type": "INTENT"},
            {"type": "FORM_END"},
            {"name": "utter_submit", "type": "BOT"},
        ]
        story_dict = {'name': "stop form + stop", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        pytest.form_stop_story_id = processor.add_complex_story(story_dict, bot, user)
        stories = Stories.objects(block_name="stop form + stop", bot=bot, events__name='know_user', status=True).get()
        assert stories.events[1].type == 'action'
        assert stories.events[2].type == 'active_loop'
        assert stories.events[2].name == 'know_user'
        assert stories.events[6].type == 'active_loop'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'stop form + stop']
        assert story_with_form[0]['steps'] == steps

    def test_delete_slot_mapping_attached_to_form(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        with pytest.raises(AppException, match=re.escape('Slot mapping is required for form: [\'know_user\']')):
            processor.delete_slot_mapping("occupation", bot, user)

    def test_delete_slot_mapping_not_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        with pytest.raises(AppException, match='No slot mapping exists for slot: menu_card'):
            processor.delete_slot_mapping("menu_card", bot, user)

    def test_add_form_slots_not_exists(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['please give us your name?'], 'slot': 'name',
                 'mapping': [{'type': 'from_text', 'value': 'user', 'entity': 'name'},
                             {'type': 'from_entity', 'entity': 'name'}]},
                {'ask_questions': ['seats required?'], 'slot': 'num_people',
                 'mapping': [{'type': 'from_entity', 'intent': ['inform', 'request_restaurant'], 'entity': 'number'}]},
                {'ask_questions': ['type of cuisine?'], 'slot': 'cuisine',
                 'mapping': [{'type': 'from_entity', 'entity': 'cuisine'}]},
                {'ask_questions': ['outdoor seating required?'], 'slot': 'outdoor_seating',
                 'mapping': [{'type': 'from_entity', 'entity': 'seating'},
                             {'type': 'from_intent', 'intent': ['affirm'], 'value': True},
                             {'type': 'from_intent', 'intent': ['deny'], 'value': False}]},
                {'ask_questions': ['any preferences?'], 'slot': 'preferences',
                 'mapping': [{'type': 'from_text', 'not_intent': ['affirm']},
                             {'type': 'from_intent', 'intent': ['affirm'], 'value': 'no additional preferences'}]},
                {'ask_questions': ['Please give your feedback on your experience so far'], 'slot': 'feedback',
                 'mapping': [{'type': 'from_text'},
                             {'type': 'from_entity', 'entity': 'feedback'}]},
                ]
        bot = 'test'
        user = 'user'
        Slots(name='num_people', type="float", bot=bot, user=user).save()
        Slots(name='cuisine', type="text", bot=bot, user=user).save()

        with pytest.raises(AppException) as e:
            processor.add_form('form', path, bot, user)
            assert str(e).__contains__('slots not exists: {')

    def test_add_form_mapping_not_found(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['please give us your name?'], 'slot': 'name'},
                {'ask_questions': ['seats required?'], 'slot': 'num_people'},
                {'ask_questions': ['food choice?'], 'slot': 'category'},
                {'ask_questions': ['outdoor seating required?'], 'slot': 'outdoor_seating'}]
        bot = 'test'
        user = 'user'
        Slots(name='outdoor_seating', type="text", bot=bot, user=user).save()
        with pytest.raises(AppException, match=r"Mapping is required for slot: {.*}"):
            processor.add_form('restaurant_form', path, bot, user)

    def test_add_form_2(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['please give us your name?'], 'slot': 'name',
                 'slot_set': {'type': 'custom', 'value': 'Mahesh'}},
                {'ask_questions': ['seats required?'], 'slot': 'num_people',
                 'slot_set': {'type': 'current', 'value': 10}},
                {'ask_questions': ['type of cuisine?'], 'slot': 'cuisine',
                 'slot_set': {'type': 'slot', 'value': 'cuisine'}},
                {'ask_questions': ['outdoor seating required?'], 'slot': 'outdoor_seating'},
                {'ask_questions': ['any preferences?'], 'slot': 'preferences'},
                {'ask_questions': ['Please give your feedback on your experience so far'], 'slot': 'feedback',
                 'slot_set': {'type': 'custom', 'value': 'Very Nice!'}}]
        bot = 'test'
        user = 'user'
        slot = {"slot": "num_people",
                'mapping': {'type': 'from_entity', 'intent': ['inform', 'request_restaurant'], 'entity': 'number'}}
        processor.add_slot_mapping(slot, bot, user)
        slot = {"slot": "cuisine", 'mapping': {'type': 'from_entity', 'entity': 'cuisine'}}
        processor.add_slot_mapping(slot, bot, user)
        slot = {"slot": "outdoor_seating",
                'mapping': [{'type': 'from_entity', 'entity': 'seating'},
                            {'type': 'from_intent', 'intent': ['affirm'], 'value': True},
                            {'type': 'from_intent', 'intent': ['deny'], 'value': False}]}
        processor.add_slot({"name": "outdoor_seating", "type": "text", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)
        for s in slot['mapping']:
            processor.add_slot_mapping({"slot": slot["slot"], "mapping": s}, bot, user)
        slot = {"slot": "preferences",
                'mapping': [{'type': 'from_text', 'not_intent': ['affirm']},
                            {'type': 'from_intent', 'intent': ['affirm'], 'value': 'no additional preferences'}]}
        processor.add_slot({"name": "preferences", "type": "text", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)
        for s in slot['mapping']:
            processor.add_slot_mapping({"slot": slot["slot"], "mapping": s}, bot, user)
        slot = {"slot": "feedback", 'mapping': [{'type': 'from_text'},
                                                {'type': 'from_entity', 'entity': 'feedback'}]}
        processor.add_slot({"name": "feedback", "type": "text", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)
        for s in slot['mapping']:
            processor.add_slot_mapping({"slot": slot["slot"], "mapping": s}, bot, user)

        assert processor.add_form('restaurant_form', path, bot, user)
        form = Forms.objects(name='restaurant_form', bot=bot, status=True).get()
        assert form.required_slots == ['name', 'num_people', 'cuisine', 'outdoor_seating', 'preferences', 'feedback']
        assert Utterances.objects(name='utter_ask_restaurant_form_name', bot=bot, status=True).get()
        assert Utterances.objects(name='utter_ask_restaurant_form_num_people', bot=bot, status=True).get()
        assert Utterances.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()
        assert Utterances.objects(name='utter_ask_restaurant_form_outdoor_seating', bot=bot, status=True).get()
        assert Utterances.objects(name='utter_ask_restaurant_form_preferences', bot=bot, status=True).get()
        assert Utterances.objects(name='utter_ask_restaurant_form_feedback', bot=bot, status=True).get()
        assert Responses.objects(name='utter_ask_restaurant_form_name', bot=bot,
                                 status=True).get().text.text == 'please give us your name?'
        assert Responses.objects(name='utter_ask_restaurant_form_num_people', bot=bot,
                                 status=True).get().text.text == 'seats required?'
        assert Responses.objects(name='utter_ask_restaurant_form_cuisine', bot=bot,
                                 status=True).get().text.text == 'type of cuisine?'
        assert Responses.objects(name='utter_ask_restaurant_form_outdoor_seating', bot=bot,
                                 status=True).get().text.text == 'outdoor seating required?'
        assert Responses.objects(name='utter_ask_restaurant_form_preferences', bot=bot,
                                 status=True).get().text.text == 'any preferences?'
        assert Responses.objects(name='utter_ask_restaurant_form_feedback', bot=bot,
                                 status=True).get().text.text == 'Please give your feedback on your experience so far'

        validations_added = list(FormValidationAction.objects(name='validate_restaurant_form', bot=bot, status=True))
        assert len(validations_added) == 6
        assert validations_added[0].slot == 'name'
        assert validations_added[0].is_required
        assert validations_added[0].slot_set.type == 'custom'
        assert validations_added[0].slot_set.value == 'Mahesh'
        assert validations_added[1].slot == 'num_people'
        assert validations_added[1].is_required
        assert validations_added[1].slot_set.type == 'current'
        assert validations_added[1].slot_set.value == 10
        assert validations_added[2].slot == 'cuisine'
        assert validations_added[2].is_required
        assert validations_added[2].slot_set.type == 'slot'
        assert validations_added[2].slot_set.value == 'cuisine'
        assert validations_added[3].slot == 'outdoor_seating'
        assert validations_added[3].is_required
        assert validations_added[3].slot_set.type == 'current'
        assert not validations_added[3].slot_set.value
        assert validations_added[4].slot == 'preferences'
        assert validations_added[4].is_required
        assert validations_added[4].slot_set.type == 'current'
        assert not validations_added[4].slot_set.value
        assert validations_added[5].slot == 'feedback'
        assert validations_added[5].is_required
        assert validations_added[5].slot_set.type == 'custom'
        assert validations_added[5].slot_set.value == "Very Nice!"

    def test_add_form_already_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        with pytest.raises(AppException, match="Form with the name 'restaurant_form' already exists"):
            processor.add_form('restaurant_form', [], bot, user)

    def test_add_form_name_empty(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        with pytest.raises(AppException, match='Form name cannot be empty or spaces'):
            processor.add_form(' ', [], bot, user)

    def test_add_form_no_entity_and_mapping_type(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['what is your name?'], 'slot': 'name'},
                {'ask_questions': ['what is your age?'], 'slot': 'age'},
                {'ask_questions': ['where are you located?'], 'slot': 'category'}]
        bot = 'test'
        user = 'user'
        with pytest.raises(AppException, match="Mapping is required for slot: {'category'}"):
            processor.add_form('get_user', path, bot, user)

    def test_add_form_with_validations(self):
        processor = MongoProcessor()
        name_validation = "if (&& name.contains('i') && name.length() > 4 || !name.contains(" ")) " \
                          "{return true;} else {return false;}"
        age_validation = "if (age > 10 && age < 70) {return true;} else {return false;}"
        occupation_validation = "if (occupation in ['teacher', 'programmer', 'student', 'manager'] " \
                                "&& !occupation.contains(" ") && occupation.length() > 20) " \
                                "{return true;} else {return false;}"
        path = [{'ask_questions': ['your name?', 'ur name?'], 'slot': 'name',
                 'validation_semantic': name_validation,
                 'valid_response': 'got it',
                 'is_required': False,
                 'slot_set': {'type': 'custom', 'value': 'Mahesh'},
                 'invalid_response': 'please rephrase'},
                {'ask_questions': ['your age?', 'ur age?'], 'slot': 'age',
                 'validation_semantic': age_validation,
                 'valid_response': 'valid entry',
                 'is_required': True,
                 'slot_set': {'type': 'current', 'value': 22},
                 'invalid_response': 'please enter again'
                 },
                {'ask_questions': ['your occupation?', 'ur occupation?'], 'slot': 'occupation',
                 'validation_semantic': occupation_validation, 'is_required': False,
                 'slot_set': {'type': 'slot', 'value': 'occupation'}}]
        bot = 'test'
        user = 'user'
        assert processor.add_form('know_user_form', path, bot, user)
        form = Forms.objects(name='know_user_form', bot=bot).get()
        assert form.required_slots == ['name', 'age', 'occupation']
        assert Utterances.objects(name='utter_ask_know_user_form_name', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        assert Utterances.objects(name='utter_ask_know_user_form_age', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        assert Utterances.objects(name='utter_ask_know_user_form_occupation', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        resp = list(Responses.objects(name='utter_ask_know_user_form_name', bot=bot, status=True))
        assert resp[0].text.text == 'your name?'
        assert resp[1].text.text == 'ur name?'
        resp = list(Responses.objects(name='utter_ask_know_user_form_age', bot=bot, status=True))
        assert resp[0].text.text == 'your age?'
        assert resp[1].text.text == 'ur age?'
        resp = list(Responses.objects(name='utter_ask_know_user_form_occupation', bot=bot, status=True))
        assert resp[0].text.text == 'your occupation?'
        assert resp[1].text.text == 'ur occupation?'

        validations_added = list(FormValidationAction.objects(name='validate_know_user_form', bot=bot, status=True))
        assert len(validations_added) == 3
        assert validations_added[0].slot == 'name'
        assert validations_added[0].validation_semantic == "if (&& name.contains('i') && name.length() > 4 || " \
                                                           "!name.contains(" ")) {return true;} else {return false;}"
        assert validations_added[0].valid_response == 'got it'
        assert validations_added[0].invalid_response == 'please rephrase'
        assert not validations_added[0].is_required
        assert validations_added[0].slot_set.type == 'custom'
        assert validations_added[0].slot_set.value == 'Mahesh'

        assert validations_added[1].slot == 'age'
        assert validations_added[1].validation_semantic == \
               "if (age > 10 && age < 70) {return true;} else {return false;}"
        assert validations_added[1].valid_response == 'valid entry'
        assert validations_added[1].invalid_response == 'please enter again'
        assert validations_added[1].is_required
        assert validations_added[1].slot_set.type == 'current'
        assert validations_added[1].slot_set.value == 22

        assert validations_added[2].slot == 'occupation'
        assert validations_added[2].validation_semantic == \
               "if (occupation in ['teacher', 'programmer', 'student', 'manager'] && !occupation.contains(" ") " \
               "&& occupation.length() > 20) {return true;} else {return false;}"
        assert not validations_added[2].valid_response
        assert not validations_added[2].invalid_response
        assert not validations_added[2].is_required
        assert validations_added[2].slot_set.type == 'slot'
        assert validations_added[2].slot_set.value == 'occupation'

    def test_list_forms(self):
        processor = MongoProcessor()
        forms = list(processor.list_forms('test'))
        assert len(forms) == 5
        assert len([f['name'] for f in forms]) == 5
        assert len([f['_id'] for f in forms]) == 5
        required_slots = [f['required_slots'] for f in forms]
        assert required_slots == [['date_time', 'priority'], ['file'], ['name', 'age', 'occupation'],
                                  ['name', 'num_people', 'cuisine', 'outdoor_seating', 'preferences', 'feedback'],
                                  ['name', 'age', 'occupation']]

    def test_list_forms_no_form_added(self):
        processor = MongoProcessor()
        forms = list(processor.list_forms('new_bot'))
        assert forms == []

    def test_get_form(self):
        processor = MongoProcessor()
        forms = list(processor.list_forms('test'))
        form_id = [f['_id'] for f in forms if f['name'] == 'know_user'][0]
        form = processor.get_form(form_id, 'test')
        assert form['settings'][0]['slot'] == 'name'
        assert form['settings'][1]['slot'] == 'age'
        assert form['settings'][2]['slot'] == 'occupation'
        assert form['settings'][0]['ask_questions'][0]['_id']
        assert form['settings'][0]['ask_questions'][0]['value'] == {'text': 'name?'}
        assert form['settings'][0]['ask_questions'][1]['value'] == {'text': 'what is your name?'}
        assert form['settings'][1]['ask_questions'][0]['_id']
        assert form['settings'][1]['ask_questions'][0]['value'] == {'text': 'age?'}
        assert form['settings'][1]['ask_questions'][1]['value'] == {'text': 'what is your age?'}
        assert form['settings'][2]['ask_questions'][0]['_id']
        assert form['settings'][2]['ask_questions'][0]['value'] == {'text': 'occupation?'}
        assert form['settings'][2]['ask_questions'][1]['value'] == {'text': 'what is your occupation?'}
        assert form['settings'][0]['slot_set'] == {'type': 'custom', 'value': 'Mahesh'}
        assert not form['settings'][0]['validation_semantic']
        assert not form['settings'][0]['invalid_response']
        assert not form['settings'][0]['valid_response']
        assert form['settings'][1]['slot_set'] == {'type': 'current', 'value': 22}
        assert not form['settings'][1]['validation_semantic']
        assert not form['settings'][1]['invalid_response']
        assert not form['settings'][1]['valid_response']
        assert form['settings'][2]['slot_set'] == {'type': 'slot', 'value': 'occupation'}
        assert not form['settings'][2]['validation_semantic']
        assert not form['settings'][2]['invalid_response']
        assert not form['settings'][2]['valid_response']

    def test_get_form_with_validations(self):
        processor = MongoProcessor()
        forms = list(processor.list_forms('test'))
        form_id = [f['_id'] for f in forms if f['name'] == 'know_user_form'][0]
        form = processor.get_form(form_id, 'test')
        assert form['settings'][0]['slot'] == 'name'
        assert form['settings'][1]['slot'] == 'age'
        assert form['settings'][2]['slot'] == 'occupation'
        assert form['settings'][0]['ask_questions'][0]['_id']
        assert form['settings'][0]['ask_questions'][0]['value']['text']
        assert form['settings'][0]['ask_questions'][1]['value']['text']
        assert form['settings'][1]['ask_questions'][0]['_id']
        assert form['settings'][1]['ask_questions'][0]['value']['text']
        assert form['settings'][1]['ask_questions'][1]['value']['text']
        assert form['settings'][2]['ask_questions'][0]['_id']
        assert form['settings'][2]['ask_questions'][0]['value']['text']
        assert form['settings'][2]['ask_questions'][1]['value']['text']
        assert form['settings'][0]['validation_semantic'] == "if (&& name.contains('i') && name.length() > 4 || " \
                                                             "!name.contains(" ")) {return true;} else {return false;}"
        assert form['settings'][0]['invalid_response'] == 'please rephrase'
        assert form['settings'][0]['valid_response'] == 'got it'
        assert not form['settings'][0]['is_required']
        assert form['settings'][0]['slot_set'] == {'type': 'custom', 'value': 'Mahesh'}
        assert form['settings'][1]['validation_semantic'] == \
               "if (age > 10 && age < 70) {return true;} else {return false;}"
        assert form['settings'][1]['invalid_response'] == 'please enter again'
        assert form['settings'][1]['valid_response'] == 'valid entry'
        assert form['settings'][1]['is_required']
        assert form['settings'][1]['slot_set'] == {'type': 'current', 'value': 22}
        assert form['settings'][2]['validation_semantic'] == \
               "if (occupation in ['teacher', 'programmer', 'student', 'manager'] && !occupation.contains(" ") " \
               "&& occupation.length() > 20) {return true;} else {return false;}"
        assert not form['settings'][2]['invalid_response']
        assert not form['settings'][2]['valid_response']
        assert not form['settings'][2]['is_required']
        assert form['settings'][2]['slot_set'] == {'type': 'slot', 'value': 'occupation'}

    def test_get_form_not_added(self):
        import mongomock

        with pytest.raises(AppException, match='Form does not exists'):
            MongoProcessor().get_form(mongomock.ObjectId().__str__(), 'test')

    def test_get_form_having_on_intent_and_not_intent(self):
        processor = MongoProcessor()
        forms = list(processor.list_forms('test'))
        form_id = [f['_id'] for f in forms if f['name'] == 'restaurant_form'][0]
        form = MongoProcessor().get_form(form_id, 'test')
        assert form['settings'][0]['slot'] == 'name'
        assert form['settings'][1]['slot'] == 'num_people'
        assert form['settings'][2]['slot'] == 'cuisine'
        assert form['settings'][3]['slot'] == 'outdoor_seating'
        assert form['settings'][4]['slot'] == 'preferences'
        assert form['settings'][5]['slot'] == 'feedback'
        assert form['settings'][0]['ask_questions'][0]['_id']
        assert form['settings'][1]['ask_questions'][0]['_id']
        assert form['settings'][2]['ask_questions'][0]['_id']
        assert form['settings'][3]['ask_questions'][0]['_id']
        assert form['settings'][4]['ask_questions'][0]['_id']
        assert form['settings'][5]['ask_questions'][0]['_id']
        assert form['settings'][0]['ask_questions'][0]['value']['text']
        assert form['settings'][1]['ask_questions'][0]['value']['text']
        assert form['settings'][2]['ask_questions'][0]['value']['text']
        assert form['settings'][3]['ask_questions'][0]['value']['text']
        assert form['settings'][4]['ask_questions'][0]['value']['text']
        assert form['settings'][5]['ask_questions'][0]['value']['text']

    def test_edit_form_slot_not_present(self):
        processor = MongoProcessor()
        path = [{'ask_questions': 'which location would you prefer?', 'slot': 'restaurant_location',
                 'mapping': [{'type': 'from_text', 'value': 'user', 'entity': 'location'},
                             {'type': 'from_entity', 'entity': 'location'}]},
                {'ask_questions': 'seats required?', 'slot': 'num_people',
                 'mapping': [{'type': 'from_entity', 'intent': ['inform', 'request_restaurant'], 'entity': 'number'}]},
                {'ask_questions': 'type of cuisine?', 'slot': 'cuisine',
                 'mapping': [{'type': 'from_entity', 'entity': 'cuisine'}]},
                {'ask_questions': 'outdoor seating required?', 'slot': 'outdoor_seating',
                 'mapping': [{'type': 'from_entity', 'entity': 'seating'},
                             {'type': 'from_intent', 'intent': ['affirm'], 'value': True},
                             {'type': 'from_intent', 'intent': ['deny'], 'value': False}]},
                {'ask_questions': 'any preferences?', 'slot': 'preferences',
                 'mapping': [{'type': 'from_text', 'not_intent': ['affirm']},
                             {'type': 'from_intent', 'intent': ['affirm'], 'value': 'no additional preferences'}]},
                {'ask_questions': 'do you want to go with an AC room?', 'slot': 'ac_required',
                 'mapping': [{'type': 'from_intent', 'intent': ['affirm'], 'value': True},
                             {'type': 'from_intent', 'intent': ['deny'], 'value': False}]},
                {'ask_questions': 'Please give your feedback on your experience so far', 'slot': 'feedback',
                 'mapping': [{'type': 'from_text'},
                             {'type': 'from_entity', 'entity': 'feedback'}]}
                ]
        bot = 'test'
        user = 'user'

        with pytest.raises(AppException) as e:
            processor.edit_form('restaurant_form', path, bot, user)
            assert str(e).__contains__('slots not exists: {')

    def test_edit_form_change_validations(self):
        processor = MongoProcessor()
        name_validation = "if (&& name.contains('i') && name.length() > 4 || " \
                          "!name.contains(" ")) {return true;} else {return false;}"
        age_validation = "if (age > 10 && age < 70) {return true;} else {return false;}"
        path = [{'ask_questions': ['what is your name?', 'name?'], 'slot': 'name',
                 'validation_semantic': name_validation,
                 'valid_response': 'got it',
                 'is_required': True,
                 'slot_set': {'type': 'custom', 'value': 'Mahesh'},
                 'invalid_response': 'please rephrase'},
                {'ask_questions': ['what is your age?', 'age?'], 'slot': 'age',
                 'validation_semantic': age_validation,
                 'valid_response': 'valid entry',
                 'invalid_response': 'please enter again',
                 'is_required': False,
                 'slot_set': {'type': 'current', 'value': 22}
                 },
                {'ask_questions': ['what is your occupation?', 'occupation?'], 'slot': 'occupation',
                 'validation_semantic': None, 'is_required': False,
                 'slot_set': {'type': 'slot', 'value': 'occupation'}}]
        bot = 'test'
        user = 'user'
        processor.edit_form('know_user_form', path, bot, user)
        form = Forms.objects(name='know_user_form', bot=bot).get()
        assert form.required_slots == ['name', 'age', 'occupation']
        assert Utterances.objects(name='utter_ask_know_user_form_name', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        assert Utterances.objects(name='utter_ask_know_user_form_age', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        assert Utterances.objects(name='utter_ask_know_user_form_occupation', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        resp = list(Responses.objects(name='utter_ask_know_user_form_name', bot=bot, status=True))
        assert resp[0].text.text == 'your name?'
        assert resp[1].text.text == 'ur name?'
        resp = list(Responses.objects(name='utter_ask_know_user_form_age', bot=bot, status=True))
        assert resp[0].text.text == 'your age?'
        assert resp[1].text.text == 'ur age?'
        resp = list(Responses.objects(name='utter_ask_know_user_form_occupation', bot=bot, status=True))
        assert resp[0].text.text == 'your occupation?'
        assert resp[1].text.text == 'ur occupation?'

        validations_added = list(FormValidationAction.objects(name='validate_know_user_form', bot=bot, status=True))
        assert len(validations_added) == 3
        assert validations_added[0].slot == 'name'
        assert validations_added[0].validation_semantic == \
               "if (&& name.contains('i') && name.length() > 4 || " \
               "!name.contains(" ")) {return true;} else {return false;}"
        assert validations_added[0].valid_response == 'got it'
        assert validations_added[0].invalid_response == 'please rephrase'
        assert validations_added[0].is_required
        assert validations_added[0].slot_set.type == 'custom'
        assert validations_added[0].slot_set.value == 'Mahesh'

        assert validations_added[1].slot == 'age'
        assert validations_added[1].validation_semantic == \
               "if (age > 10 && age < 70) {return true;} else {return false;}"
        assert validations_added[1].valid_response == 'valid entry'
        assert validations_added[1].invalid_response == 'please enter again'
        assert not validations_added[1].is_required
        assert validations_added[1].slot_set.type == 'current'
        assert validations_added[1].slot_set.value == 22

        assert validations_added[2].slot == 'occupation'
        assert not validations_added[2].validation_semantic
        assert not validations_added[2].is_required
        assert validations_added[2].slot_set.type == 'slot'
        assert validations_added[2].slot_set.value == 'occupation'

    def test_edit_form_remove_validations(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['what is your name?', 'name?'], 'slot': 'name',
                 'mapping': [{'type': 'from_text', 'value': 'user', 'entity': 'name'},
                             {'type': 'from_entity', 'entity': 'name'}],
                 'validation_semantic': None,
                 'is_required': True,
                 'slot_set': {'type': 'custom', 'value': 'Mahesh'},
                 'valid_response': 'got it',
                 'invalid_response': 'please rephrase'},
                {'ask_questions': ['what is your age?', 'age?'], 'slot': 'age',
                 'mapping': [{'type': 'from_intent', 'intent': ['get_age'], 'entity': 'age', 'value': '18'}],
                 'validation_semantic': None,
                 'is_required': True,
                 'slot_set': {'type': 'current', 'value': 22},
                 'valid_response': 'valid entry',
                 'invalid_response': 'please enter again'
                 },
                {'ask_questions': ['what is your occupation?', 'occupation?'], 'slot': 'occupation',
                 'mapping': [
                     {'type': 'from_intent', 'intent': ['get_occupation'], 'entity': 'occupation', 'value': 'business'},
                     {'type': 'from_text', 'entity': 'occupation', 'value': 'engineer'},
                     {'type': 'from_entity', 'entity': 'occupation'},
                     {'type': 'from_trigger_intent', 'entity': 'occupation', 'value': 'tester',
                      'intent': ['get_business', 'is_engineer', 'is_tester'], 'not_intent': ['get_age', 'get_name']}],
                 'validation_semantic': None, 'is_required': False,
                 'slot_set': {'type': 'slot', 'value': 'occupation'}}]
        bot = 'test'
        user = 'user'
        processor.edit_form('know_user_form', path, bot, user)
        form = Forms.objects(name='know_user_form', bot=bot).get()
        assert form.required_slots == ['name', 'age', 'occupation']
        assert Utterances.objects(name='utter_ask_know_user_form_name', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        assert Utterances.objects(name='utter_ask_know_user_form_age', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        assert Utterances.objects(name='utter_ask_know_user_form_occupation', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        resp = list(Responses.objects(name='utter_ask_know_user_form_name', bot=bot, status=True))
        assert resp[0].text.text == 'your name?'
        assert resp[1].text.text == 'ur name?'
        resp = list(Responses.objects(name='utter_ask_know_user_form_age', bot=bot, status=True))
        assert resp[0].text.text == 'your age?'
        assert resp[1].text.text == 'ur age?'
        resp = list(Responses.objects(name='utter_ask_know_user_form_occupation', bot=bot, status=True))
        assert resp[0].text.text == 'your occupation?'
        assert resp[1].text.text == 'ur occupation?'

        validations = list(FormValidationAction.objects(name='validate_know_user_form', bot=bot, status=True))
        assert len(validations) == 3
        assert not validations[0].validation_semantic
        assert validations[0].valid_response == 'got it'
        assert validations[0].invalid_response == 'please rephrase'
        assert validations[0].is_required
        assert validations[0].slot_set.type == 'custom'
        assert validations[0].slot_set.value == 'Mahesh'
        assert not validations[1].validation_semantic
        assert validations[1].valid_response == 'valid entry'
        assert validations[1].invalid_response == 'please enter again'
        assert validations[1].is_required
        assert validations[1].slot_set.type == 'current'
        assert validations[1].slot_set.value == 22
        assert not validations[2].validation_semantic
        assert not validations[2].valid_response
        assert not validations[2].invalid_response
        assert not validations[2].is_required
        assert validations[2].slot_set.type == 'slot'
        assert validations[2].slot_set.value == 'occupation'

    def test_edit_form_add_validations(self):
        processor = MongoProcessor()
        name_validation = "if (&& name.contains('i') && name.length() > 4 || " \
                          "!name.contains(" ")) {return true;} else {return false;}"
        path = [{'ask_questions': ['what is your name?', 'name?'], 'slot': 'name',
                 'validation_semantic': name_validation,
                 'valid_response': 'got it',
                 'is_required': False,
                 'slot_set': {'type': 'custom', 'value': 'Mahesh'},
                 'invalid_response': 'please rephrase'},
                {'ask_questions': ['what is your age?', 'age?'], 'slot': 'age',
                 'validation_semantic': None,
                 'is_required': True,
                 'slot_set': {'type': 'current', 'value': 22},
                 'valid_response': 'valid entry',
                 'invalid_response': 'please enter again'
                 },
                {'ask_questions': ['what is your occupation?', 'occupation?'], 'slot': 'occupation',
                 'validation_semantic': None, 'is_required': False,
                 'slot_set': {'type': 'slot', 'value': 'occupation'}}]
        bot = 'test'
        user = 'user'
        processor.edit_form('know_user_form', path, bot, user)

        validations_added = list(FormValidationAction.objects(name='validate_know_user_form', bot=bot, status=True))
        assert len(validations_added) == 3
        assert validations_added[0].slot == 'name'
        assert validations_added[0].validation_semantic == "if (&& name.contains('i') && name.length() > 4 || " \
                                                           "!name.contains(" ")) {return true;} else {return false;}"
        assert validations_added[0].valid_response == 'got it'
        assert validations_added[0].invalid_response == 'please rephrase'
        assert not validations_added[0].is_required
        assert validations_added[0].slot_set.type == 'custom'
        assert validations_added[0].slot_set.value == 'Mahesh'
        assert validations_added[1].is_required
        assert validations_added[1].slot_set.type == 'current'
        assert validations_added[1].slot_set.value == 22
        assert not validations_added[2].is_required
        assert validations_added[2].slot_set.type == 'slot'
        assert validations_added[2].slot_set.value == 'occupation'

    def test_edit_form_with_any_slot(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['which location would you prefer?'], 'slot': 'location',
                 'slot_set': {'type': 'custom', 'value': 'Bangalore'}},
                {'ask_questions': ['seats required?'], 'slot': 'num_people',
                 'slot_set': {'type': 'current', 'value': 10}},
                {'ask_questions': ['type of cuisine?'], 'slot': 'cuisine',
                 'validation_semantic': "if (&& cuisine.contains('i') && cuisine.length() > 4 || "
                                        "!cuisine.contains(" ")) {return true;} else {return false;}",
                 'slot_set': {'type': 'current', 'value': 'Indian Cuisine'}},
                {'ask_questions': ['outdoor seating required?'], 'slot': 'outdoor_seating',
                 'slot_set': {'type': 'custom', 'value': True}},
                {'ask_questions': ['any preferences?'], 'slot': 'preferences',
                 'slot_set': {'type': 'current'}},
                {'ask_questions': ['do you want to go with an AC room?'], 'slot': 'ac_required',
                 'slot_set': {'type': 'slot', 'value': 'ac_required'}},
                {'ask_questions': ['Please give your feedback on your experience so far'], 'slot': 'feedback',
                 'slot_set': {'type': 'custom', 'value': 'Very Nice!'}}]
        bot = 'test'
        user = 'user'
        slot = {"slot": "ac_required",
                'mapping': {'type': 'from_intent', 'intent': ['affirm'], 'value': True}}
        slot2 = {"slot": "ac_required",
                  'mapping': {'type': 'from_intent', 'intent': ['deny'], 'value': False}}
        processor.add_slot({"name": "ac_required", "type": "any", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)
        processor.add_slot_mapping(slot, bot, user)
        processor.add_slot_mapping(slot2, bot, user)

        with pytest.raises(AppException, match="form will not accept any type slots: {'ac_required'}"):
            processor.edit_form('restaurant_form', path, bot, user)

    def test_edit_form_remove_and_add_slots(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['which location would you prefer?'], 'slot': 'location',
                 'slot_set': {'type': 'custom', 'value': 'Bangalore'}},
                {'ask_questions': ['seats required?'], 'slot': 'num_people',
                 'slot_set': {'type': 'current', 'value': 10}},
                {'ask_questions': ['type of cuisine?'], 'slot': 'cuisine',
                 'validation_semantic': "if (&& cuisine.contains('i') && cuisine.length() > 4 || "
                                        "!cuisine.contains(" ")) {return true;} else {return false;}",
                 'slot_set': {'type': 'current', 'value': 'Indian Cuisine'}},
                {'ask_questions': ['outdoor seating required?'], 'slot': 'outdoor_seating',
                 'slot_set': {'type': 'custom', 'value': True}},
                {'ask_questions': ['any preferences?'], 'slot': 'preferences',
                 'slot_set': {'type': 'current'}},
                {'ask_questions': ['do you want to go with an AC room?'], 'slot': 'ac_required',
                 'slot_set': {'type': 'slot', 'value': 'ac_required'}},
                {'ask_questions': ['Please give your feedback on your experience so far'], 'slot': 'feedback',
                 'slot_set': {'type': 'custom', 'value': 'Very Nice!'}}]
        bot = 'test'
        user = 'user'
        slot = {"slot": "ac_required",
                'mapping': {'type': 'from_intent', 'intent': ['affirm'], 'value': True}}
        slot2 = {"slot": "ac_required",
                'mapping':{'type': 'from_intent', 'intent': ['deny'], 'value': False}}
        processor.add_slot({"name": "ac_required", "type": "text", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)
        processor.delete_slot_mapping('ac_required', bot, user)
        processor.add_slot_mapping(slot, bot, user)
        processor.add_slot_mapping(slot2, bot, user)

        processor.edit_form('restaurant_form', path, bot, user)
        form = Forms.objects(name='restaurant_form', bot=bot, status=True).get()
        assert form.required_slots == ['location', 'num_people', 'cuisine', 'outdoor_seating', 'preferences',
                                       'ac_required', 'feedback']
        assert Utterances.objects(name='utter_ask_restaurant_form_location', bot=bot,
                                  status=True).get().form_attached == 'restaurant_form'
        assert Utterances.objects(name='utter_ask_restaurant_form_num_people', bot=bot,
                                  status=True).get().form_attached == 'restaurant_form'
        assert Utterances.objects(name='utter_ask_restaurant_form_cuisine', bot=bot,
                                  status=True).get().form_attached == 'restaurant_form'
        assert Utterances.objects(name='utter_ask_restaurant_form_outdoor_seating', bot=bot,
                                  status=True).get().form_attached == 'restaurant_form'
        assert Utterances.objects(name='utter_ask_restaurant_form_preferences', bot=bot,
                                  status=True).get().form_attached == 'restaurant_form'
        assert Utterances.objects(name='utter_ask_restaurant_form_feedback', bot=bot,
                                  status=True).get().form_attached == 'restaurant_form'
        assert Utterances.objects(name='utter_ask_restaurant_form_ac_required', bot=bot,
                                  status=True).get().form_attached == 'restaurant_form'
        with pytest.raises(DoesNotExist):
            Utterances.objects(name='utter_ask_restaurant_form_name', bot=bot, status=True).get()
        with pytest.raises(DoesNotExist):
            Responses.objects(name='utter_ask_restaurant_form_name', bot=bot, status=True).get()
        assert Responses.objects(name='utter_ask_restaurant_form_location',
                                 bot=bot, status=True).get().text.text == 'which location would you prefer?'
        assert Responses.objects(name='utter_ask_restaurant_form_num_people',
                                 bot=bot, status=True).get().text.text == 'seats required?'
        assert Responses.objects(name='utter_ask_restaurant_form_cuisine',
                                 bot=bot, status=True).get().text.text == 'type of cuisine?'
        assert Responses.objects(name='utter_ask_restaurant_form_outdoor_seating',
                                 bot=bot, status=True).get().text.text == 'outdoor seating required?'
        assert Responses.objects(name='utter_ask_restaurant_form_preferences',
                                 bot=bot, status=True).get().text.text == 'any preferences?'
        assert Responses.objects(name='utter_ask_restaurant_form_ac_required',
                                 bot=bot, status=True).get().text.text == 'do you want to go with an AC room?'
        assert Responses.objects(name='utter_ask_restaurant_form_feedback',
                                 bot=bot,
                                 status=True).get().text.text == 'Please give your feedback on your experience so far'

        validations_added = list(FormValidationAction.objects(name='validate_restaurant_form', bot=bot, status=True))
        assert len(validations_added) == 7
        assert validations_added[1].slot == 'cuisine'
        assert validations_added[1].validation_semantic == \
               "if (&& cuisine.contains('i') && cuisine.length() > 4 || !cuisine.contains(" ")) " \
               "{return true;} else {return false;}"
        assert validations_added[1].slot_set.type == 'current'
        assert validations_added[1].slot_set.value == 'Indian Cuisine'

    def test_edit_form_not_exists(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Form does not exists'):
            processor.edit_form('form_not_present', [], 'test', 'test')

    def test_edit_form_utterance_not_exists(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['provide your age?'], 'slot': 'age',
                 'slot_set': {'type': 'current', 'value': 27}},
                {'ask_questions': ['provide your location?'], 'slot': 'location',
                 'slot_set': {'type': 'custom', 'value': 'Delhi'}}]

        bot = 'test'
        user = 'user'
        utterance = Utterances.objects(name='utter_ask_know_user_name', bot=bot).get()
        utterance.delete()
        for response in Responses.objects(name='utter_ask_know_user_name', bot=bot):
            response.delete()

        processor.edit_form('know_user', path, bot, user)
        assert Forms.objects(name='know_user', bot=bot, status=True).get()
        assert Utterances.objects(name='utter_ask_know_user_age', bot=bot,
                                  status=True).get().form_attached == 'know_user'
        assert Utterances.objects(name='utter_ask_know_user_location', bot=bot,
                                  status=True).get().form_attached == 'know_user'
        assert len(Responses.objects(name='utter_ask_know_user_age', bot=bot, status=True)) == 2
        assert Responses.objects(name='utter_ask_know_user_location', bot=bot,
                                 status=True).get().text.text == 'provide your location?'
        validations_added = list(FormValidationAction.objects(name='validate_know_user', bot=bot, status=True))
        assert validations_added[0].is_required
        assert validations_added[0].slot_set.type == 'current'
        assert validations_added[0].slot_set.value == 27
        assert validations_added[1].is_required
        assert validations_added[1].slot_set.type == 'custom'
        assert validations_added[1].slot_set.value == 'Delhi'

    def test_delete_form_with_validations(self):
        bot = 'test'
        user = 'user'
        processor = MongoProcessor()
        processor.delete_form('know_user_form', bot, user)
        with pytest.raises(DoesNotExist):
            Forms.objects(name='know_user_form', bot=bot, status=True).get()
        form_validations = list(FormValidationAction.objects(name='know_user_form', bot=bot, status=True))
        assert not form_validations

    def test_delete_form_not_exists(self):
        bot = 'test'
        user = 'user'
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Form "get_user" does not exists'):
            processor.delete_form('get_user', bot, user)
        with pytest.raises(AppException, match='Form "form_not_present" does not exists'):
            processor.delete_form('form_not_present', bot, user)

    def test_delete_empty_form(self):
        bot = 'test'
        user = 'user'
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Form " " does not exists'):
            processor.delete_form(' ', bot, user)

    def test_delete_form_attached_to_rule(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        form_name = 'know_user'
        story_name = "stop form + continue"
        with pytest.raises(AppException,
                           match=re.escape(f'Cannot remove action "{form_name}" linked to flow "{story_name}"')):
            processor.delete_form(form_name, bot, user)

    def test_delete_rule_with_form(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        processor.delete_complex_story(pytest.activate_form_story_id, 'RULE', bot, user)
        with pytest.raises(DoesNotExist):
            Rules.objects(block_name="activate form", bot=bot, events__name='know_user', status=True).get()

    def test_delete_rule_with_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        processor.delete_complex_story(pytest.form_continue_story_id, 'STORY', bot, user)
        processor.delete_complex_story(pytest.form_stop_story_id, 'STORY', bot, user)
        with pytest.raises(DoesNotExist):
            Stories.objects(block_name="stop form + continue", bot=bot, events__name='know_user', status=True).get()
        with pytest.raises(DoesNotExist):
            Stories.objects(block_name="stop form + stop", bot=bot, events__name='know_user', status=True).get()

    def test_delete_form_utterance_deleted(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        utterance = Utterances.objects(name='utter_ask_know_user_age', bot=bot).get()
        utterance.delete()
        processor.delete_form('know_user', bot, user)
        with pytest.raises(DoesNotExist):
            Forms.objects(name='know_user', bot=bot, status=True).get()
        with pytest.raises(DoesNotExist):
            Utterances.objects(name='utter_ask_know_user_name', bot=bot, status=True).get()
        with pytest.raises(DoesNotExist):
            Responses.objects(name='utter_ask_know_user_name', bot=bot, status=True).get()
        with pytest.raises(DoesNotExist):
            Utterances.objects(name='utter_ask_know_user_location', bot=bot, status=True).get()
        with pytest.raises(DoesNotExist):
            Responses.objects(name='utter_ask_know_user_location', bot=bot, status=True).get()

    def test_delete_utterance_linked_to_form(self):
        processor = MongoProcessor()
        bot = 'test'
        with pytest.raises(AppException,
                           match='Utterance cannot be deleted as it is linked to form: restaurant_form'):
            processor.delete_utterance('utter_ask_restaurant_form_cuisine', bot, "test")
        assert Utterances.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()
        assert Responses.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()

    def test_delete_response_linked_to_form(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        response = Responses.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()
        with pytest.raises(AppException,
                           match='Utterance cannot be deleted as it is linked to form: restaurant_form'):
            processor.delete_response(str(response.id), bot)
        assert Utterances.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()
        assert Responses.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()

    def test_edit_utterance_for_form(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        response = Responses.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()
        processor.edit_text_response(str(response.id), 'what cuisine are you interested in?',
                                     'utter_ask_restaurant_form_cuisine', bot, user)
        assert Responses.objects(name='utter_ask_restaurant_form_cuisine', bot=bot,
                                 status=True).get().text.text == 'what cuisine are you interested in?'

    def test_delete_response_linked_to_form_validation_false(self):
        processor = MongoProcessor()
        bot = 'test'
        processor.delete_utterance('utter_ask_restaurant_form_cuisine', bot, False, user="test")
        with pytest.raises(DoesNotExist):
            Utterances.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()
        with pytest.raises(DoesNotExist):
            Responses.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()

    def test_add_utterance_to_story_that_is_attached_to_form(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_ask_restaurant_form_outdoor_seating", "type": "BOT"},
        ]
        story_dict = {'name': "story with form utterance", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(AppException,
                           match='utterance "utter_ask_restaurant_form_outdoor_seating" is attached to a form'):
            processor.add_complex_story(story_dict, bot, user)

    def test_delete_intent_attached_to_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        with pytest.raises(AppException, match='Cannot remove intent "greet" linked to flow "greet"'):
            processor.delete_intent('greet', bot, user, False)

    def test_add_story_with_form(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "restaurant_form", "type": "FORM_ACTION"},
            {"name": "utter_thanks", "type": "ACTION"},
        ]
        story_dict = {'name': "story with form", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        pytest.form_story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with form", bot=bot,
                                events__name='restaurant_form', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'story with form']
        assert story_with_form[0]['steps'] == [
            {'name': 'greet', 'type': 'INTENT'},
            {'name': 'restaurant_form', 'type': 'FORM_ACTION'},
            {'name': 'utter_thanks', 'type': 'BOT'}
        ]

    def test_get_story_with_form(self):
        processor = MongoProcessor()
        bot = 'test'
        stories = list(processor.get_stories(bot))
        assert stories[20]['name'] == 'story with form'
        assert stories[20]['type'] == 'STORY'
        assert stories[20]['steps'][0]['name'] == 'greet'
        assert stories[20]['steps'][0]['type'] == 'INTENT'
        assert stories[20]['steps'][1]['name'] == 'restaurant_form'
        assert stories[20]['steps'][1]['type'] == 'FORM_ACTION'
        assert stories[20]['template_type'] == 'CUSTOM'

    def test_delete_form_attached_to_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        with pytest.raises(AppException,
                           match='Cannot remove action "restaurant_form" linked to flow "story with form"'):
            processor.delete_form("restaurant_form", bot, user)

    def test_delete_story_with_form(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        processor.delete_complex_story(pytest.form_story_id, 'STORY', bot, user)
        assert not Stories.objects(block_name="story with form", bot=bot,
                                   events__name='restaurant_form')

    def test_update_story_step_that_is_attached_to_form(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        story_dict = {'name': "story without action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        pytest.story_id = processor.add_complex_story(story_dict, bot, user)

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_ask_restaurant_form_outdoor_seating", "type": "BOT"},
        ]
        story_dict = {'name': "story without action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(AppException,
                           match='utterance "utter_ask_restaurant_form_outdoor_seating" is attached to a form'):
            processor.update_complex_story(pytest.story_id, story_dict, bot, user)

    def test_add_slot_set_action_from_value_no_value_passed(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        Slots(name='name', type='text', bot=bot, user=user).save()
        action = {'name': 'action_set_slot', 'set_slots': [{'name': 'name', 'type': SLOT_SET_TYPE.FROM_VALUE.value}]}
        processor.add_slot_set_action(action, bot, user)
        assert Actions.objects(name='action_set_slot', type=ActionType.slot_set_action.value,
                               bot=bot, user=user, status=True).get()
        assert SlotSetAction.objects(name='action_set_slot', bot=bot, user=user, status=True).get()

    def test_add_story_with_slot_set_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "action_set_slot", "type": "SLOT_SET_ACTION"},
        ]
        story_dict = {'name': "story with slot_set_action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        pytest.slot_set_action_story_id = processor.add_complex_story(story_dict, bot, user)
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'story with slot_set_action']
        assert story_with_form[0]['steps'] == [
            {'name': 'greet', 'type': 'INTENT'},
            {'name': 'action_set_slot', 'type': 'SLOT_SET_ACTION'},
        ]

    def test_fetch_story_with_slot_set_action(self):
        processor = MongoProcessor()
        data = list(processor.get_stories("test"))
        slot_set_story = next(item for item in data if item['name'] == 'story with slot_set_action')
        assert slot_set_story['steps'] == [{'name': 'greet', 'type': 'INTENT'},
                                           {'name': 'action_set_slot', 'type': 'SLOT_SET_ACTION'}]
        assert slot_set_story['template_type'] == 'CUSTOM'
        assert slot_set_story['type'] == 'STORY'

    def test_add_slot_set_action_from_value(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': 'action_set_name_slot',
                  'set_slots': [{'name': 'name', 'type': SLOT_SET_TYPE.FROM_VALUE.value, 'value': '5'}]}
        processor.add_slot_set_action(action, bot, user)
        assert Actions.objects(name='action_set_name_slot', type=ActionType.slot_set_action.value,
                               bot=bot, user=user, status=True).get()
        assert SlotSetAction.objects(name='action_set_name_slot', bot=bot, user=user, status=True).get()

    def test_add_slot_set_action_reset(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        Slots(name='location', type='text', bot=bot, user=user).save()
        action = {'name': 'action_set_location_slot',
                  'set_slots': [{'name': 'location', 'type': SLOT_SET_TYPE.RESET_SLOT.value}]}
        processor.add_slot_set_action(action, bot, user)
        assert Actions.objects(name='action_set_location_slot', type=ActionType.slot_set_action.value,
                               bot=bot, user=user, status=True).get()
        assert SlotSetAction.objects(name='action_set_location_slot', bot=bot, user=user, status=True).get()

    def test_add_slot_set_action_already_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': 'action_set_name_slot', 'set_slots': [{'name': 'name', 'type': SLOT_SET_TYPE.FROM_VALUE.value,
                                                                 'value': '5'}]}
        with pytest.raises(AppException, match='Action exists!'):
            processor.add_slot_set_action(action, bot, user)

    def test_add_slot_set_action_name_empty(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': ' ', 'set_slots': [{'name': 'name', 'type': SLOT_SET_TYPE.FROM_VALUE.value, 'value': '5'}]}
        with pytest.raises(AppException, match='name cannot be empty or spaces'):
            processor.add_slot_set_action(action, bot, user)

        action = {'name': None, 'set_slots': [{'name': 'name', 'type': SLOT_SET_TYPE.FROM_VALUE.value, 'value': '5'}]}
        with pytest.raises(AppException, match='name cannot be empty or spaces'):
            processor.add_slot_set_action(action, bot, user)

    def test_add_slot_set_action_slot_empty(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': 'action_set_slot_name',
                  'set_slots': [{'name': ' ', 'type': SLOT_SET_TYPE.FROM_VALUE.value, 'value': '5'}]}
        with pytest.raises(AppException, match='slot name cannot be empty or spaces'):
            processor.add_slot_set_action(action, bot, user)

        action = {'name': 'action_set_slot_name',
                  'set_slots': [{'name': None, 'type': SLOT_SET_TYPE.FROM_VALUE.value, 'value': '5'}]}
        with pytest.raises(AppException, match='slot name cannot be empty or spaces'):
            processor.add_slot_set_action(action, bot, user)

    def test_add_slot_set_action_slot_not_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': 'action_set_slot_non_existant', 'set_slots': [{'name': 'non_existant',
                                                                         'type': SLOT_SET_TYPE.FROM_VALUE.value,
                                                                         'value': '5'}]}
        with pytest.raises(AppException, match='Slot with name "non_existant" not found'):
            processor.add_slot_set_action(action, bot, user)

    def test_add_slot_set_action_simple_action_with_same_name_present(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        Actions(name='action_trigger_some_api', bot=bot, user=user).save()
        action = {'name': 'action_trigger_some_api', 'set_slots': [{'name': 'some_api',
                                                                    'type': SLOT_SET_TYPE.FROM_VALUE.value,
                                                                    'value': '5'}]}
        with pytest.raises(AppException, match='Action exists!'):
            processor.add_slot_set_action(action, bot, user)

    def test_list_slot_set_actions(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = processor.list_slot_set_actions(bot)
        for action in actions:
            assert type(action['_id']) is str
        [action.pop('_id') for action in actions]
        assert actions == [{'name': 'action_set_slot', 'set_slots': [{'name': 'name', 'type': 'from_value'}]},
                           {'name': 'action_set_name_slot',
                            'set_slots': [{'name': 'name', 'type': 'from_value', 'value': '5'}]},
                           {'name': 'action_set_location_slot',
                            'set_slots': [{'name': 'location', 'type': 'reset_slot'}]}]

    def test_list_slot_set_actions_with_false(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = processor.list_slot_set_actions(bot, False)
        for action in actions:
            assert action.get('_id') is None
        assert actions == [{'name': 'action_set_slot', 'set_slots': [{'name': 'name', 'type': 'from_value'}]},
                           {'name': 'action_set_name_slot',
                            'set_slots': [{'name': 'name', 'type': 'from_value', 'value': '5'}]},
                           {'name': 'action_set_location_slot',
                            'set_slots': [{'name': 'location', 'type': 'reset_slot'}]}]

    def test_list_slot_set_actions_not_present(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        actions = processor.list_slot_set_actions(bot)
        assert len(actions) == 0

    def test_edit_slot_set_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        Slots(name='name_new', type='text', bot=bot, user=user).save()
        action = {'name': 'action_set_name_slot',
                  'set_slots': [{'name': 'name_new', 'type': SLOT_SET_TYPE.RESET_SLOT.value,
                                 'value': 'name'}]}
        processor.edit_slot_set_action(action, bot, user)
        assert Actions.objects(name='action_set_name_slot', type=ActionType.slot_set_action.value,
                               bot=bot, user=user, status=True).get()
        assert SlotSetAction.objects(name='action_set_name_slot', bot=bot, user=user, status=True).get()

    def test_edit_slot_set_action_not_present(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': 'action_non_existant',
                  'set_slots': [{'name': 'name_new', 'type': SLOT_SET_TYPE.FROM_VALUE.value,
                                 'value': 'name'}]}
        with pytest.raises(AppException, match=f'Slot setting action with name "{action["name"]}" not found'):
            processor.edit_slot_set_action(action, bot, user)

    def test_edit_slot_set_action_slot_not_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': 'action_set_name_slot',
                  'set_slots': [{'name': 'slot_non_existant', 'type': SLOT_SET_TYPE.FROM_VALUE.value,
                                 'value': 'name'}]}
        with pytest.raises(AppException, match=f'Slot with name "slot_non_existant" not found'):
            processor.edit_slot_set_action(action, bot, user)

    def test_edit_slot_set_action_name_empty(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': ' ', 'set_slots': [{'name': 'name', 'type': SLOT_SET_TYPE.FROM_VALUE.value,
                                              'value': 'name'}]}
        with pytest.raises(AppException, match=f'Slot setting action with name "{action["name"]}" not found'):
            processor.edit_slot_set_action(action, bot, user)

    def test_edit_slot_set_action_slot_empty(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': 'action_set_name_slot', 'set_slots': [{'name': ' ', 'type': SLOT_SET_TYPE.FROM_VALUE.value,
                                                                 'value': 'name'}]}
        with pytest.raises(AppException, match="slot name cannot be empty or spaces"):
            processor.edit_slot_set_action(action, bot, user)

    def test_delete_slot_set_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        processor.delete_action('action_set_name_slot', bot, user)

    def test_delete_slot_set_action_already_deleted(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        with pytest.raises(AppException, match=f'Action with name "action_set_name_slot" not found'):
            processor.delete_action('action_set_name_slot', bot, user)

    def test_delete_slot_set_action_not_present(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        with pytest.raises(AppException, match=f'Action with name "action_non_existant" not found'):
            processor.delete_action('action_non_existant', bot, user)

    def test_delete_slot_set_action_linked_to_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        Slots(name='age', type='text', bot=bot, user=user).save()
        action = {'name': 'action_set_age_slot', 'set_slots': [{'name': 'age', 'type': SLOT_SET_TYPE.RESET_SLOT.value}]}
        processor.add_slot_set_action(action, bot, user)
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "action_set_age_slot", "type": "SLOT_SET_ACTION"},
        ]
        story_dict = {'name': "story with slot set action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.add_complex_story(story_dict, bot, user)
        with pytest.raises(AppException,
                           match=f'Cannot remove action "action_set_age_slot" linked to flow "story with slot set action"'):
            processor.delete_action('action_set_age_slot', bot, user)

    def test_delete_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        Actions(name='action_custom', bot=bot, user=user).save()
        processor.delete_action('action_custom', bot, user)

    def test_delete_action_already_deleted(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        with pytest.raises(AppException, match=f'Action with name "action_custom" not found'):
            processor.delete_action('action_custom', bot, user)

    def test_delete_action_with_attached_http_action(self):
        processor = MongoProcessor()
        bot = 'tester_bot'
        http_url = 'http://www.google.com'
        action = 'tester_action'
        user = 'tester_user'
        response = "json"
        request_method = 'GET'
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        http_params_list: List[HttpActionParameters] = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value")]
        header: List[HttpActionParameters] = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=ActionResponseEvaluation(value=response),
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list,
            headers=header
        )
        prompt_action_config = PromptActionConfigRequest(
            name='test_delete_action_with_attached_http_action',
            llm_prompts=[{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                          'source': 'static', 'is_enabled': True},
                         {'name': 'Action Prompt',
                          'data': 'tester_action',
                          'instructions': 'Answer according to the context', 'type': 'user',
                          'source': 'action',
                          'is_enabled': True}],
            llm_type=DEFAULT_LLM,
            hyperparameters=Utility.get_default_llm_hyperparameters(),
            bot=bot
        )
        processor.add_http_action_config(http_action_config.dict(), user, bot)
        processor.add_prompt_action(prompt_action_config.dict(), bot, user)
        with pytest.raises(AppException, match=f'Action with name tester_action is attached with PromptAction!'):
            processor.delete_action('tester_action', bot, user)

    @responses.activate
    def test_push_notifications_enabled_create_type_event(self):
        bot = 'test_notifications'
        user = 'test'
        url = f"http://localhost/events/{bot}"
        with patch.dict(Utility.environment['notifications'], {"enable": True, "server_endpoint": url}):
            processor = MongoProcessor()
            responses.add(
                'POST',
                url,
                json={'message': 'Event added'}
            )
            processor.add_intent('greet', bot, user, False)
            request_body = responses.calls[0].request
            request_body = request_body.body.decode('utf8')
            request_body = json.loads(request_body)
            assert responses.calls[0].request.headers['Authorization']
            assert request_body['event_type'] == "create"
            assert request_body['event']['entity_type'] == "Intents"
            assert request_body['event']['data']['name'] == 'greet'
            assert request_body['event']['data']['bot'] == bot
            assert request_body['event']['data']['user'] == user
            assert not Utility.check_empty_string(request_body['event']['data']['timestamp'])
            assert request_body['event']['data']['status']
            assert not request_body['event']['data']['is_integration']
            assert not request_body['event']['data']['use_entities']

    @responses.activate
    def test_push_notifications_enabled_update_type_event(self):
        bot = "tests"
        user = 'testUser'
        url = "http://localhost/events"
        with patch.dict(Utility.environment['notifications'], {"enable": True, "server_endpoint": url}):
            processor = MongoProcessor()
            responses.add(
                'POST',
                f'{url}/tests',
                json={'message': 'Event updated'}
            )
            examples = list(processor.get_training_examples("greet", bot))
            processor.edit_training_example(examples[0]["_id"], example="[Kanpur](location) India", intent="greet",
                                            bot=bot, user=user)
            request_body = responses.calls[0].request
            request_body = request_body.body.decode('utf8')
            request_body = json.loads(request_body)
            assert responses.calls[0].request.headers['Authorization']
            assert request_body['event_type'] == "update"
            assert request_body['event']['entity_type'] == "TrainingExamples"
            assert request_body['event']['data']['intent'] == 'greet'
            assert not Utility.check_empty_string(request_body['event']['data']['text'])
            assert request_body['event']['data']['bot'] == bot
            assert request_body['event']['data']['user'] == user
            assert not Utility.check_empty_string(request_body['event']['data']['timestamp'])
            assert request_body['event']['data']['status']

    @responses.activate
    def test_push_notifications_enabled_delete_type_event(self):
        bot = "test"
        user = 'test'
        url = "http://localhost/events"
        with patch.dict(Utility.environment['notifications'], {"enable": True, "server_endpoint": url}):
            processor = MongoProcessor()

            responses.add(
                'POST',
                f'{url}/test',
                json={'message': 'Event deleted'}
            )
            processor.delete_complex_story(pytest.slot_set_action_story_id, 'STORY', bot, user)

    def test_push_notifications_enabled_update_type_event_connection_error(self):
        bot = "test"
        user = 'test'
        utterance = 'utter_notifications'
        processor = MongoProcessor()
        processor.add_utterance_name(utterance, bot, user, raise_error_if_exists=True)
        assert Utterances.objects(bot=bot, status=True, name__iexact=utterance).get()

    def test_push_notifications_enabled_delete_type_connection_error(self):
        bot = "test"
        user = 'test'
        story_name = 'test_push_notifications'
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_thanks", "type": "ACTION"},
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'STORY', 'template_type': 'Q&A'}
        story_id = processor.add_complex_story(story_dict, bot, user)
        processor.delete_complex_story(story_id, 'STORY', bot, user)
        with pytest.raises(DoesNotExist):
            Stories.objects(block_name=story_name, bot=bot, status=True).get()

    @responses.activate
    def test_add_jira_action(self):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action', 'url': url, 'user_name': 'test@digite.com',
            'api_token': {"value": 'ASDFGHJKL'}, 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        responses.add(
            'GET',
            f'{url}/rest/api/2/serverInfo',
            json={'baseUrl': 'https://udit-pandey.atlassian.net', 'version': '1001.0.0-SNAPSHOT',
                  'versionNumbers': [1001, 0, 0], 'deploymentType': 'Cloud', 'buildNumber': 100191,
                  'buildDate': '2022-02-11T05:35:40.000+0530', 'serverTime': '2022-02-15T10:54:09.906+0530',
                  'scmInfo': '831671b3b59f40b5108ef3f9491df89a1317ecaa', 'serverTitle': 'Jira',
                  'defaultLocale': {'locale': 'en_US'}}
        )
        responses.add(
            'GET',
            f'{url}/rest/api/2/project/HEL',
            json={'expand': 'description,lead,issueTypes,url,projectKeys,permissions,insight',
                  'self': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000', 'id': '10000', 'key': 'HEL',
                  'description': '', 'lead': {
                    'self': 'https://udit-pandey.atlassian.net/rest/api/2/user?accountId=6205e1585d18ad00729aa75f',
                    'accountId': '6205e1585d18ad00729aa75f', 'avatarUrls': {
                        '48x48': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '24x24': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '16x16': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '32x32': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png'},
                    'displayName': 'Udit Pandey', 'active': True}, 'components': [], 'issueTypes': [
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10001', 'id': '10001',
                     'description': 'A small, distinct piece of work.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10318?size=medium',
                     'name': 'Task', 'subtask': False, 'avatarId': 10318, 'hierarchyLevel': 0},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10002', 'id': '10002',
                     'description': 'A collection of related bugs, stories, and tasks.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10307?size=medium',
                     'name': 'Epic', 'subtask': False, 'avatarId': 10307, 'hierarchyLevel': 1},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10003', 'id': '10003',
                     'description': 'Subtasks track small pieces of work that are part of a larger task.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10316?size=medium',
                     'name': 'Bug', 'subtask': True, 'avatarId': 10316, 'hierarchyLevel': -1}],
                  'assigneeType': 'UNASSIGNED', 'versions': [], 'name': 'helicopter', 'roles': {
                    'atlassian-addons-project-access': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10007',
                    'Administrator': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10004',
                    'Viewer': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10006',
                    'Member': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10005'}, 'avatarUrls': {
                    '48x48': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408',
                    '24x24': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=small',
                    '16x16': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=xsmall',
                    '32x32': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=medium'},
                  'projectTypeKey': 'software', 'simplified': True, 'style': 'next-gen', 'isPrivate': False,
                  'properties': {}, 'entityId': '8a851ebf-72eb-461d-be68-4c2c28805440',
                  'uuid': '8a851ebf-72eb-461d-be68-4c2c28805440'}
        )
        processor = MongoProcessor()
        assert processor.add_jira_action(action, bot, user)

    def test_add_jira_action_already_exists(self):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action', 'url': url, 'user_name': 'test@digite.com',
            'api_token': {'value': 'ASDFGHJKL'}, 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        processor = MongoProcessor()
        with pytest.raises(AppException, match="Action exists!"):
            processor.add_jira_action(action, bot, user)

    def test_add_jira_action_existing_name(self):
        processor = MongoProcessor()
        bot = 'test'
        http_url = 'http://www.google.com'
        action = 'test_action'
        # file deepcode ignore HardcodedNonCryptoSecret: Random string for testing
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        http_params_list: List[HttpActionParameters] = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value")]
        header: List[HttpActionParameters] = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=ActionResponseEvaluation(value=response),
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list,
            headers=header
        )
        processor.add_http_action_config(http_action_config.dict(), user, bot)

        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'test_action', 'url': url, 'user_name': 'test@digite.com',
            'api_token': 'ASDFGHJKL', 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
            'response': {"value": 'We have logged a ticket'}
        }
        processor = MongoProcessor()
        with pytest.raises(AppException, match="Action exists!"):
            processor.add_jira_action(action, bot, user)

    @responses.activate
    def test_add_jira_action_different_bot(self):
        bot = 'test_2'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action', 'url': url, 'user_name': 'test@digite.com',
            'api_token': {'value': 'ASDFGHJKL'}, 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        responses.add(
            'GET',
            f'{url}/rest/api/2/serverInfo',
            json={'baseUrl': 'https://udit-pandey.atlassian.net', 'version': '1001.0.0-SNAPSHOT',
                  'versionNumbers': [1001, 0, 0], 'deploymentType': 'Cloud', 'buildNumber': 100191,
                  'buildDate': '2022-02-11T05:35:40.000+0530', 'serverTime': '2022-02-15T10:54:09.906+0530',
                  'scmInfo': '831671b3b59f40b5108ef3f9491df89a1317ecaa', 'serverTitle': 'Jira',
                  'defaultLocale': {'locale': 'en_US'}}
        )
        responses.add(
            'GET',
            f'{url}/rest/api/2/project/HEL',
            json={'expand': 'description,lead,issueTypes,url,projectKeys,permissions,insight',
                  'self': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000', 'id': '10000', 'key': 'HEL',
                  'description': '', 'lead': {
                    'self': 'https://udit-pandey.atlassian.net/rest/api/2/user?accountId=6205e1585d18ad00729aa75f',
                    'accountId': '6205e1585d18ad00729aa75f', 'avatarUrls': {
                        '48x48': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '24x24': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '16x16': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '32x32': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png'},
                    'displayName': 'Udit Pandey', 'active': True}, 'components': [], 'issueTypes': [
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10001', 'id': '10001',
                     'description': 'A small, distinct piece of work.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10318?size=medium',
                     'name': 'Task', 'subtask': False, 'avatarId': 10318, 'hierarchyLevel': 0},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10002', 'id': '10002',
                     'description': 'A collection of related bugs, stories, and tasks.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10307?size=medium',
                     'name': 'Epic', 'subtask': False, 'avatarId': 10307, 'hierarchyLevel': 1},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10003', 'id': '10003',
                     'description': 'Subtasks track small pieces of work that are part of a larger task.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10316?size=medium',
                     'name': 'Bug', 'subtask': True, 'avatarId': 10316, 'hierarchyLevel': -1}],
                  'assigneeType': 'UNASSIGNED', 'versions': [], 'name': 'helicopter', 'roles': {
                    'atlassian-addons-project-access': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10007',
                    'Administrator': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10004',
                    'Viewer': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10006',
                    'Member': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10005'}, 'avatarUrls': {
                    '48x48': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408',
                    '24x24': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=small',
                    '16x16': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=xsmall',
                    '32x32': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=medium'},
                  'projectTypeKey': 'software', 'simplified': True, 'style': 'next-gen', 'isPrivate': False,
                  'properties': {}, 'entityId': '8a851ebf-72eb-461d-be68-4c2c28805440',
                  'uuid': '8a851ebf-72eb-461d-be68-4c2c28805440'}
        )
        processor = MongoProcessor()
        assert processor.add_jira_action(action, bot, user)

    def test_add_jira_action_invalid_url(self, monkeypatch):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action_new', 'url': url, 'user_name': 'test@digite.com',
            'api_token': {'value': 'ASDFGHJKL'}, 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
            'response': 'We have logged a ticket'
        }

        def _mock_error(*args, **kwargs):
            raise JIRAError(status_code=404, url=url)

        monkeypatch.setattr(JIRA, '_create_http_basic_session', _mock_error)

        processor = MongoProcessor()
        with pytest.raises(ValidationError, match='Could not connect to url: *'):
            processor.add_jira_action(action, bot, user)

    def test_add_jira_action_invalid_url_runtime_error(self, monkeypatch):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action_new', 'url': url, 'user_name': 'test@digite.com',
            'api_token': {'value': 'ASDFGHJKL'}, 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
            'response': 'We have logged a ticket'
        }

        def _mock_error(*args, **kwargs):
            raise RuntimeError()

        monkeypatch.setattr(JIRA, '_create_http_basic_session', _mock_error)

        processor = MongoProcessor()
        with pytest.raises(ValidationError, match='Could not connect to url: *'):
            processor.add_jira_action(action, bot, user)

    @responses.activate
    def test_add_jira_action_invalid_project_key(self):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action_new', 'url': url, 'user_name': 'test@digite.com',
            'api_token': {'value': 'ASDFGHJKL'}, 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        responses.add(
            'GET',
            f'{url}/rest/api/2/serverInfo',
            json={'baseUrl': 'https://udit-pandey.atlassian.net', 'version': '1001.0.0-SNAPSHOT',
                  'versionNumbers': [1001, 0, 0], 'deploymentType': 'Cloud', 'buildNumber': 100191,
                  'buildDate': '2022-02-11T05:35:40.000+0530', 'serverTime': '2022-02-15T10:54:09.906+0530',
                  'scmInfo': '831671b3b59f40b5108ef3f9491df89a1317ecaa', 'serverTitle': 'Jira',
                  'defaultLocale': {'locale': 'en_US'}}
        )
        responses.add(
            'GET',
            f'{url}/rest/api/2/project/HEL',
            json={'errorMessages': ["No project could be found with key 'HAL'."], 'errors': {}},
            status=404
        )
        processor = MongoProcessor()
        with pytest.raises(ValidationError):
            processor.add_jira_action(action, bot, user)

    @responses.activate
    def test_add_jira_action_invalid_issue_type(self):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        issue_type = 'ProdIssue'
        action = {
            'name': 'jira_action_new', 'url': url, 'user_name': 'test@digite.com',
            'api_token': {'value': 'ASDFGHJKL'}, 'project_key': 'HEL', 'issue_type': issue_type, 'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        responses.add(
            'GET',
            f'{url}/rest/api/2/serverInfo',
            json={'baseUrl': 'https://udit-pandey.atlassian.net', 'version': '1001.0.0-SNAPSHOT',
                  'versionNumbers': [1001, 0, 0], 'deploymentType': 'Cloud', 'buildNumber': 100191,
                  'buildDate': '2022-02-11T05:35:40.000+0530', 'serverTime': '2022-02-15T10:54:09.906+0530',
                  'scmInfo': '831671b3b59f40b5108ef3f9491df89a1317ecaa', 'serverTitle': 'Jira',
                  'defaultLocale': {'locale': 'en_US'}}
        )
        responses.add(
            'GET',
            f'{url}/rest/api/2/project/HEL',
            json={'expand': 'description,lead,issueTypes,url,projectKeys,permissions,insight',
                  'self': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000', 'id': '10000', 'key': 'HEL',
                  'description': '', 'lead': {
                    'self': 'https://udit-pandey.atlassian.net/rest/api/2/user?accountId=6205e1585d18ad00729aa75f',
                    'accountId': '6205e1585d18ad00729aa75f', 'avatarUrls': {
                        '48x48': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '24x24': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '16x16': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '32x32': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png'},
                    'displayName': 'Udit Pandey', 'active': True}, 'components': [], 'issueTypes': [
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10001', 'id': '10001',
                     'description': 'A small, distinct piece of work.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10318?size=medium',
                     'name': 'Task', 'subtask': False, 'avatarId': 10318, 'hierarchyLevel': 0},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10002', 'id': '10002',
                     'description': 'A collection of related bugs, stories, and tasks.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10307?size=medium',
                     'name': 'Epic', 'subtask': False, 'avatarId': 10307, 'hierarchyLevel': 1},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10003', 'id': '10003',
                     'description': 'Subtasks track small pieces of work that are part of a larger task.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10316?size=medium',
                     'name': 'Bug', 'subtask': True, 'avatarId': 10316, 'hierarchyLevel': -1}],
                  'assigneeType': 'UNASSIGNED', 'versions': [], 'name': 'helicopter', 'roles': {
                    'atlassian-addons-project-access': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10007',
                    'Administrator': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10004',
                    'Viewer': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10006',
                    'Member': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10005'}, 'avatarUrls': {
                    '48x48': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408',
                    '24x24': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=small',
                    '16x16': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=xsmall',
                    '32x32': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=medium'},
                  'projectTypeKey': 'software', 'simplified': True, 'style': 'next-gen', 'isPrivate': False,
                  'properties': {}, 'entityId': '8a851ebf-72eb-461d-be68-4c2c28805440',
                  'uuid': '8a851ebf-72eb-461d-be68-4c2c28805440'}
        )
        processor = MongoProcessor()
        with pytest.raises(ValidationError, match=f"No issue type '{issue_type}' exists"):
            processor.add_jira_action(action, bot, user)

    @responses.activate
    def test_add_jira_action_parent_key_not_given_for_subtask(self):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action_new', 'url': url, 'user_name': 'test@digite.com',
            'api_token': {'value': 'ASDFGHJKL'}, 'project_key': 'HEL', 'issue_type': 'Subtask', 'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        responses.add(
            'GET',
            f'{url}/rest/api/2/serverInfo',
            json={'baseUrl': 'https://udit-pandey.atlassian.net', 'version': '1001.0.0-SNAPSHOT',
                  'versionNumbers': [1001, 0, 0], 'deploymentType': 'Cloud', 'buildNumber': 100191,
                  'buildDate': '2022-02-11T05:35:40.000+0530', 'serverTime': '2022-02-15T10:54:09.906+0530',
                  'scmInfo': '831671b3b59f40b5108ef3f9491df89a1317ecaa', 'serverTitle': 'Jira',
                  'defaultLocale': {'locale': 'en_US'}}
        )
        responses.add(
            'GET',
            f'{url}/rest/api/2/project/HEL',
            json={'expand': 'description,lead,issueTypes,url,projectKeys,permissions,insight',
                  'self': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000', 'id': '10000', 'key': 'HEL',
                  'description': '', 'lead': {
                    'self': 'https://udit-pandey.atlassian.net/rest/api/2/user?accountId=6205e1585d18ad00729aa75f',
                    'accountId': '6205e1585d18ad00729aa75f', 'avatarUrls': {
                        '48x48': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '24x24': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '16x16': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '32x32': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png'},
                    'displayName': 'Udit Pandey', 'active': True}, 'components': [], 'issueTypes': [
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10001', 'id': '10001',
                     'description': 'A small, distinct piece of work.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10318?size=medium',
                     'name': 'Task', 'subtask': False, 'avatarId': 10318, 'hierarchyLevel': 0},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10002', 'id': '10002',
                     'description': 'A collection of related bugs, stories, and tasks.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10307?size=medium',
                     'name': 'Subtask', 'subtask': True, 'avatarId': 10307, 'hierarchyLevel': 1},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10003', 'id': '10003',
                     'description': 'Subtasks track small pieces of work that are part of a larger task.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10316?size=medium',
                     'name': 'Bug', 'subtask': True, 'avatarId': 10316, 'hierarchyLevel': -1}],
                  'assigneeType': 'UNASSIGNED', 'versions': [], 'name': 'helicopter', 'roles': {
                    'atlassian-addons-project-access': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10007',
                    'Administrator': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10004',
                    'Viewer': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10006',
                    'Member': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10005'}, 'avatarUrls': {
                    '48x48': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408',
                    '24x24': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=small',
                    '16x16': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=xsmall',
                    '32x32': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=medium'},
                  'projectTypeKey': 'software', 'simplified': True, 'style': 'next-gen', 'isPrivate': False,
                  'properties': {}, 'entityId': '8a851ebf-72eb-461d-be68-4c2c28805440',
                  'uuid': '8a851ebf-72eb-461d-be68-4c2c28805440'}
        )
        processor = MongoProcessor()
        with pytest.raises(ValidationError, match="parent key is required for issues of type 'Subtask'"):
            processor.add_jira_action(action, bot, user)

    def test_list_jira_actions(self):
        bot = 'test'
        processor = MongoProcessor()
        jira_actions = list(processor.list_jira_actions(bot))
        jira_actions[0].pop("_id")
        assert jira_actions == [
            {'name': 'jira_action', 'url': 'https://test-digite.atlassian.net', 'user_name': 'test@digite.com',
             'api_token': {'_cls': 'CustomActionRequestParameters', 'key': 'api_token', 'encrypt': False,
                           'value': 'ASDFGHJKL', 'parameter_type': 'value'}, 'project_key': 'HEL', 'issue_type': 'Bug',
             'summary': 'new user',
             'response': 'We have logged a ticket'}]

        jira_actions = list(processor.list_jira_actions(bot, False))
        assert jira_actions == [
            {'name': 'jira_action', 'url': 'https://test-digite.atlassian.net', 'user_name': 'test@digite.com',
             'api_token': {'_cls': 'CustomActionRequestParameters', 'key': 'api_token', 'encrypt': False,
                           'value': 'ASDFGHJKL', 'parameter_type': 'value'},
             'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
             'response': 'We have logged a ticket'}]

    @responses.activate
    def test_edit_jira_action(self):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action', 'url': url, 'user_name': 'test@digite.com',
            'api_token': {'value': 'ASDFGHJKL'}, 'project_key': 'HEL', 'issue_type': 'Subtask', 'parent_key': 'HEL-4',
            'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        responses.add(
            'GET',
            f'{url}/rest/api/2/serverInfo',
            json={'baseUrl': 'https://udit-pandey.atlassian.net', 'version': '1001.0.0-SNAPSHOT',
                  'versionNumbers': [1001, 0, 0], 'deploymentType': 'Cloud', 'buildNumber': 100191,
                  'buildDate': '2022-02-11T05:35:40.000+0530', 'serverTime': '2022-02-15T10:54:09.906+0530',
                  'scmInfo': '831671b3b59f40b5108ef3f9491df89a1317ecaa', 'serverTitle': 'Jira',
                  'defaultLocale': {'locale': 'en_US'}}
        )
        responses.add(
            'GET',
            f'{url}/rest/api/2/project/HEL',
            json={'expand': 'description,lead,issueTypes,url,projectKeys,permissions,insight',
                  'self': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000', 'id': '10000', 'key': 'HEL',
                  'description': '', 'lead': {
                    'self': 'https://udit-pandey.atlassian.net/rest/api/2/user?accountId=6205e1585d18ad00729aa75f',
                    'accountId': '6205e1585d18ad00729aa75f', 'avatarUrls': {
                        '48x48': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '24x24': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '16x16': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '32x32': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png'},
                    'displayName': 'Udit Pandey', 'active': True}, 'components': [], 'issueTypes': [
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10001', 'id': '10001',
                     'description': 'A small, distinct piece of work.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10318?size=medium',
                     'name': 'Task', 'subtask': False, 'avatarId': 10318, 'hierarchyLevel': 0},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10002', 'id': '10002',
                     'description': 'A collection of related bugs, stories, and tasks.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10307?size=medium',
                     'name': 'Subtask', 'subtask': True, 'avatarId': 10307, 'hierarchyLevel': 1},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10003', 'id': '10003',
                     'description': 'Subtasks track small pieces of work that are part of a larger task.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10316?size=medium',
                     'name': 'Bug', 'subtask': True, 'avatarId': 10316, 'hierarchyLevel': -1}],
                  'assigneeType': 'UNASSIGNED', 'versions': [], 'name': 'helicopter', 'roles': {
                    'atlassian-addons-project-access': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10007',
                    'Administrator': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10004',
                    'Viewer': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10006',
                    'Member': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10005'}, 'avatarUrls': {
                    '48x48': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408',
                    '24x24': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=small',
                    '16x16': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=xsmall',
                    '32x32': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=medium'},
                  'projectTypeKey': 'software', 'simplified': True, 'style': 'next-gen', 'isPrivate': False,
                  'properties': {}, 'entityId': '8a851ebf-72eb-461d-be68-4c2c28805440',
                  'uuid': '8a851ebf-72eb-461d-be68-4c2c28805440'}
        )
        processor = MongoProcessor()
        assert not processor.edit_jira_action(action, bot, user)

    def test_edit_jira_action_not_exists(self):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action_not_exists', 'url': url, 'user_name': 'test@digite.com',
            'api_token': 'ASDFGHJKL', 'project_key': 'HEL', 'issue_type': 'Subtask', 'parent_key': 'HEL-4',
            'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        processor = MongoProcessor()
        with pytest.raises(AppException, match=f'Action with name "{action.get("name")}" not found'):
            processor.edit_jira_action(action, bot, user)

    def test_list_jira_actions_after_update(self):
        bot = 'test'
        processor = MongoProcessor()
        jira_actions = list(processor.list_jira_actions(bot))
        jira_actions[0].pop("_id")
        assert jira_actions == [
            {'name': 'jira_action', 'url': 'https://test-digite.atlassian.net', 'user_name': 'test@digite.com',
             'api_token': {'_cls': 'CustomActionRequestParameters', 'key': 'api_token', 'encrypt': False,
                           'value': 'ASDFGHJKL', 'parameter_type': 'value'}, 'project_key': 'HEL',
             'issue_type': 'Subtask', 'parent_key': 'HEL-4',
             'summary': 'new user', 'response': 'We have logged a ticket'}
        ]

        jira_actions = list(processor.list_jira_actions(bot, False))
        assert jira_actions == [
            {'name': 'jira_action', 'url': 'https://test-digite.atlassian.net', 'user_name': 'test@digite.com',
             'api_token': {'_cls': 'CustomActionRequestParameters', 'key': 'api_token', 'encrypt': False,
                           'value': 'ASDFGHJKL', 'parameter_type': 'value'}, 'project_key': 'HEL',
             'issue_type': 'Subtask', 'parent_key': 'HEL-4',
             'summary': 'new user', 'response': 'We have logged a ticket'}
        ]

    def test_add_jira_action_with_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "jira_action", "type": "JIRA_ACTION"},
        ]
        story_dict = {'name': "story with jira action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with jira action", bot=bot, events__name='jira_action',
                                status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'story with jira action']
        assert story_with_form[0]['steps'] == [
            {'name': 'greet', 'type': 'INTENT'},
            {'name': 'jira_action', 'type': 'JIRA_ACTION'},
        ]
        processor.delete_complex_story(story_id, 'STORY', bot, user)

    def test_add_schedule_action_with_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'

        expected_data = {
            "name": "schedule_mp2",
            "schedule_time": {"value": "2024-08-06T09:00:00.000+0530", "parameter_type": "value"},
            "timezone": None,
            "schedule_action": "test_pyscript",
            "response_text": "action scheduled",
            "params_list": [],
            "dispatch_bot_response": True
        }

        processor.add_schedule_action(expected_data, bot, user)


        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "schedule_mp2", "type": "SCHEDULE_ACTION"},
        ]
        story_dict = {'name': "story with schedule action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with schedule action", bot=bot, events__name='schedule_mp2',
                                status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'story with schedule action']
        assert story_with_form[0]['steps'] == [
            {'name': 'greet', 'type': 'INTENT'},
            {'name': 'schedule_mp2', 'type': 'SCHEDULE_ACTION'},
        ]
        processor.delete_complex_story(story_id, 'STORY', bot, user)

    def test_delete_jira_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        processor.delete_action('jira_action', bot, user)
        with pytest.raises(DoesNotExist):
            Actions.objects(name='jira_action', bot=bot).get()
        with pytest.raises(DoesNotExist):
            JiraAction.objects(name='jira_action', bot=bot).get()

    def test_list_zendesk_actions_empty(self):
        bot = 'test'
        processor = MongoProcessor()
        assert list(processor.list_zendesk_actions(bot)) == []

    def test_add_zendesk_action(self):
        bot = 'test'
        user = 'test'
        action = {'name': 'zendesk_action', 'subdomain': 'digite751', 'api_token': {'value': '123456789'},
                  'subject': 'new ticket', 'user_name': 'udit.pandey@digite.com', 'response': 'ticket filed'}
        processor = MongoProcessor()
        with patch('zenpy.Zenpy'):
            assert processor.add_zendesk_action(action, bot, user)

    def test_add_zendesk_action_with_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "zendesk_action", "type": "ZENDESK_ACTION"},
        ]
        story_dict = {'name': "story with zendesk action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with zendesk action", bot=bot,
                                events__name='zendesk_action', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'story with zendesk action']
        assert story_with_form[0]['steps'] == [
            {"name": "greet", "type": "INTENT"},
            {"name": "zendesk_action", "type": "ZENDESK_ACTION"},
        ]
        processor.delete_complex_story(story_id, 'STORY', bot, user)

    def test_add_zendesk_action_invalid_subdomain(self):
        bot = 'test'
        user = 'test'
        action = {'name': 'zendesk_action_1', 'subdomain': 'digite751', 'api_token': {'value': '123456789'},
                  'subject': 'new ticket',
                  'user_name': 'udit.pandey@digite.com', 'response': 'ticket filed'}

        def __mock_zendesk_error(*args, **kwargs):
            from zenpy.lib.exception import APIException
            raise APIException({"error": {"title": "No help desk at digite751.zendesk.com"}})

        processor = MongoProcessor()
        with patch('zenpy.Zenpy') as mock:
            mock.side_effect = __mock_zendesk_error
            with pytest.raises(ValidationError):
                assert processor.add_zendesk_action(action, bot, user)

    def test_add_zendesk_action_invalid_credentials(self):
        bot = 'test'
        user = 'test'
        action = {'name': 'zendesk_action_1', 'subdomain': 'digite751', 'api_token': {'value': '123456789'},
                  'subject': 'new ticket',
                  'user_name': 'udit.pandey@digite.com', 'response': 'ticket filed'}

        def __mock_zendesk_error(*args, **kwargs):
            from zenpy.lib.exception import APIException
            raise APIException({"error": "Couldn't authenticate you"})

        processor = MongoProcessor()
        with patch('zenpy.Zenpy') as mock:
            mock.side_effect = __mock_zendesk_error
            with pytest.raises(ValidationError):
                assert processor.add_zendesk_action(action, bot, user)

    def test_add_zendesk_action_already_exists(self):
        bot = 'test'
        user = 'test'
        action = {'name': 'zendesk_action', 'subdomain': 'digite751',
                  'api_token': {'value': '123456789'}, 'subject': 'new ticket',
                  'user_name': 'udit.pandey@digite.com', 'response': 'ticket filed'}
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Action exists!'):
            assert processor.add_zendesk_action(action, bot, user)

    def test_add_zendesk_action_existing_name(self):
        processor = MongoProcessor()
        bot = 'test'
        http_url = 'http://www.google.com'
        action = 'test_action_1'
        # file deepcode ignore HardcodedNonCryptoSecret: Random string for testing
        user = 'test'
        response = "json"
        request_method = 'GET'
        http_params_list: List[HttpActionParameters] = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value")]
        header: List[HttpActionParameters] = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=ActionResponseEvaluation(value=response),
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list,
            headers=header
        )
        processor.add_http_action_config(http_action_config.dict(), user, bot)

        bot = 'test'
        user = 'test'
        action = {'name': 'test_action_1', 'subdomain': 'digite751', 'api_token': {'value': '123456789'},
                  'subject': 'new ticket', 'user_name': 'udit.pandey@digite.com', 'response': {"value": 'ticket filed'}}
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Action exists!'):
            assert processor.add_zendesk_action(action, bot, user)

    def test_edit_zendesk_action(self):
        bot = 'test'
        user = 'test'
        action = {'name': 'zendesk_action', 'subdomain': 'digite756', 'api_token': {'value': '123456789999'},
                  'subject': 'new ticket',
                  'user_name': 'udit.pandey@digite.com', 'response': 'ticket filed here'}
        processor = MongoProcessor()
        with patch('zenpy.Zenpy'):
            processor.edit_zendesk_action(action, bot, user)

    def test_edit_zendesk_action_invalid_subdomain(self):
        bot = 'test'
        user = 'test'
        action = {'name': 'zendesk_action', 'subdomain': 'digite751', 'api_token': {'value': '123456789'},
                  'subject': 'new ticket', 'user_name': 'udit.pandey@digite.com',
                  'response': 'ticket filed'}

        def __mock_zendesk_error(*args, **kwargs):
            from zenpy.lib.exception import APIException
            raise APIException({"error": {"title": "No help desk at digite751.zendesk.com"}})

        processor = MongoProcessor()
        with patch('zenpy.Zenpy') as mock:
            mock.side_effect = __mock_zendesk_error
            with pytest.raises(ValidationError):
                assert processor.edit_zendesk_action(action, bot, user)

    def test_edit_zendesk_action_does_not_exists(self):
        bot = 'test'
        user = 'test'
        action = {'name': 'zendesk_action_1', 'subdomain': 'digite751', 'api_token': {'value': '123456789'},
                  'subject': 'new ticket',
                  'user_name': 'udit.pandey@digite.com', 'response': 'ticket filed'}
        processor = MongoProcessor()
        with pytest.raises(AppException, match=f'Action with name "{action.get("name")}" not found'):
            assert processor.edit_zendesk_action(action, bot, user)

    def test_list_zendesk_actions(self):
        bot = 'test'
        processor = MongoProcessor()
        zendesk_actions = list(processor.list_zendesk_actions(bot))
        zendesk_actions[0].pop("_id")
        assert zendesk_actions == [
            {'name': 'zendesk_action', 'subdomain': 'digite756', 'user_name': 'udit.pandey@digite.com',
             'api_token': {'_cls': 'CustomActionRequestParameters', 'key': 'api_token', 'encrypt': False,
                           'value': '123456789999', 'parameter_type': 'value'}, 'subject': 'new ticket',
             'response': 'ticket filed here'}]
        bot = 'test_1'
        processor = MongoProcessor()
        assert list(processor.list_zendesk_actions(bot)) == []

    def test_list_zendesk_actions_unmasked(self):
        bot = 'test'
        processor = MongoProcessor()
        zendesk_actions = list(processor.list_zendesk_actions(bot, False))
        assert zendesk_actions[0].get('_id') is None
        assert zendesk_actions == [
            {'name': 'zendesk_action', 'subdomain': 'digite756', 'user_name': 'udit.pandey@digite.com',
             'api_token': {'_cls': 'CustomActionRequestParameters', 'key': 'api_token', 'encrypt': False,
                           'value': '123456789999', 'parameter_type': 'value'}, 'subject': 'new ticket',
             'response': 'ticket filed here'}]

    def test_delete_zendesk_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        processor.delete_action('zendesk_action', bot, user)
        with pytest.raises(DoesNotExist):
            Actions.objects(name='zendesk_action', status=True, bot=bot).get()
        with pytest.raises(DoesNotExist):
            ZendeskAction.objects(name='zendesk_action', status=True, bot=bot).get()

    def test_add_pipedrive_leads_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'pipedrive_leads',
            'domain': 'https://digite751.pipedrive.com/',
            'api_token': {'value': '12345678'},
            'title': 'new lead',
            'response': 'I have failed to create lead for you',
            'metadata': {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
        }
        with patch('pipedrive.client.Client'):
            assert processor.add_pipedrive_action(action, bot, user)
        assert Actions.objects(name='pipedrive_leads', status=True, bot=bot).get()
        assert PipedriveLeadsAction.objects(name='pipedrive_leads', status=True, bot=bot).get()

    def test_add_pipedrive_leads_action_required_metadata_absent(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'pipedrive_invalid_metadata',
            'domain': 'https://digite751.pipedrive.com/',
            'api_token': {'value': '12345678'},
            'title': 'new lead',
            'response': 'I have failed to create lead for you',
            'metadata': {'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
        }
        with pytest.raises(ValidationError, match='metadata: name is required'):
            with patch('pipedrive.client.Client'):
                assert processor.add_pipedrive_action(action, bot, user)

    def test_add_pipedrive_leads_action_invalid_auth(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'pipedrive_invalid_metadata',
            'domain': 'https://digite751.pipedrive.com/',
            'api_token': {'value': '12345678'},
            'title': 'new lead',
            'response': 'I have failed to create lead for you',
            'metadata': {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
        }

        def __mock_exception(*args, **kwargs):
            raise UnauthorizedError('Invalid authentication', {'error_code': 401})

        with pytest.raises(ValidationError, match='Invalid authentication*'):
            with patch('pipedrive.client.Client', __mock_exception):
                assert processor.add_pipedrive_action(action, bot, user)

    def test_add_pipedrive_leads_action_with_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "pipedrive_leads", "type": "PIPEDRIVE_LEADS_ACTION"},
        ]
        story_dict = {'name': "story with pipedrive leads", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with pipedrive leads", bot=bot,
                                events__name='pipedrive_leads', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'story with pipedrive leads']
        assert story_with_form[0]['steps'] == [
            {"name": "greet", "type": "INTENT"},
            {"name": "pipedrive_leads", "type": "PIPEDRIVE_LEADS_ACTION"},
        ]
        processor.delete_complex_story(story_id, 'STORY', bot, user)

    def test_add_pipedrive_leads_action_duplicate(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'pipedrive_leads',
            'domain': 'https://digite751.pipedrive.com/',
            'api_token': {'value': '12345678'},
            'title': 'new lead',
            'response': 'I have failed to create lead for you',
            'metadata': {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
        }
        with pytest.raises(AppException, match='Action exists!'):
            processor.add_pipedrive_action(action, bot, user)

    def test_add_pipedrive_leads_action_existing_name(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'pipedrive_leads_action',
            'domain': 'https://digite751.pipedrive.com/',
            'api_token': {'value': '12345678'},
            'title': 'new lead',
            'response': 'I have failed to create lead for you',
            'metadata': {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
        }
        Actions(name='pipedrive_leads_action', type=ActionType.pipedrive_leads_action.value, bot=bot, user=user).save()
        with pytest.raises(AppException, match='Action exists!'):
            processor.add_pipedrive_action(action, bot, user)

    def test_list_pipedrive_leads_action_masked(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.list_pipedrive_actions(bot))
        assert actions[0]['name'] == 'pipedrive_leads'
        assert actions[0]['api_token'] == {'_cls': 'CustomActionRequestParameters', 'encrypt': False,
                                           'key': 'api_token', 'parameter_type': 'value', 'value': '12345678'}
        assert actions[0]['domain'] == 'https://digite751.pipedrive.com/'
        assert actions[0]['response'] == 'I have failed to create lead for you'
        assert actions[0]['title'] == 'new lead'
        assert actions[0]['metadata'] == {'name': 'name', 'org_name': 'organization', 'email': 'email',
                                          'phone': 'phone'}

    def test_edit_pipedrive_leads_action_not_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'pipedrive_invalid_metadata',
            'domain': 'https://digite751.pipedrive.com/',
            'api_token': {'value': '12345678'},
            'title': 'new lead',
            'response': 'I have failed to create lead for you',
            'metadata': {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
        }
        with pytest.raises(AppException, match='Action with name "pipedrive_invalid_metadata" not found'):
            processor.edit_pipedrive_action(action, bot, user)

    def test_edit_pipedrive_leads_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'pipedrive_leads',
            'domain': 'https://digite7.pipedrive.com/',
            'api_token': {'value': 'asdfghjklertyui'},
            'title': 'new lead generated',
            'response': 'Failed to create lead for you',
            'metadata': {'name': 'name', 'email': 'email', 'phone': 'phone'}
        }
        with patch('pipedrive.client.Client'):
            assert not processor.edit_pipedrive_action(action, bot, user)

    def test_list_pipedrive_leads_action(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.list_pipedrive_actions(bot, False))
        assert actions[0]['name'] == 'pipedrive_leads'
        assert actions[0]['api_token'] == {'_cls': 'CustomActionRequestParameters', 'encrypt': False,
                                           'key': 'api_token', 'parameter_type': 'value', 'value': 'asdfghjklertyui'}
        assert actions[0]['domain'] == 'https://digite7.pipedrive.com/'
        assert actions[0]['response'] == 'Failed to create lead for you'
        assert actions[0]['title'] == 'new lead generated'
        assert actions[0]['metadata'] == {'name': 'name', 'email': 'email', 'phone': 'phone'}

        actions = list(processor.list_pipedrive_actions(bot, True))
        assert actions[0]['name'] == 'pipedrive_leads'
        assert actions[0]['api_token'] == {'_cls': 'CustomActionRequestParameters', 'encrypt': False,
                                           'key': 'api_token', 'parameter_type': 'value', 'value': 'asdfghjklertyui'}
        assert actions[0]['domain'] == 'https://digite7.pipedrive.com/'
        assert actions[0]['response'] == 'Failed to create lead for you'
        assert actions[0]['title'] == 'new lead generated'
        assert actions[0]['metadata'] == {'name': 'name', 'email': 'email', 'phone': 'phone'}

    def test_delete_pipedrive_leads_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        processor.delete_action('pipedrive_leads', bot, user)
        with pytest.raises(DoesNotExist):
            Actions.objects(name='pipedrive_leads', status=True, bot=bot).get()
        with pytest.raises(DoesNotExist):
            PipedriveLeadsAction.objects(name='pipedrive_leads', status=True, bot=bot).get()

    def test_add_razorpay_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action_name = 'razorpay_action'
        action = {
            'name': action_name,
            'api_key': {"value": "API_KEY", "parameter_type": "key_vault"},
            'api_secret': {"value": "API_SECRET", "parameter_type": "kay_vault"},
            'amount': {"value": "amount", "parameter_type": "slot"},
            'currency': {"value": "INR", "parameter_type": "value"},
            'username': {"parameter_type": "sender_id"},
            'email': {"parameter_type": "sender_id"},
            'contact': {"value": "contact", "parameter_type": "slot"},
            'notes': [
                {"key": "order_id", "parameter_type": "slot", "value": "order_id"},
                {"key": "phone_number", "parameter_type": "value", "value": "9876543210"}
            ]
        }
        assert processor.add_razorpay_action(action, bot, user)
        assert Actions.objects(name=action_name, status=True, bot=bot).get()
        assert RazorpayAction.objects(name=action_name, status=True, bot=bot).get()

    def test_add_razorpay_action_required_fields_absent(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action_name = 'test_add_razorpay_action_required_fields_absent'
        action = {
            'name': action_name,
            'amount': {"value": "amount", "parameter_type": "slot"},
            'currency': {"value": "INR", "parameter_type": "value"},
            'username': {"parameter_type": "sender_id"},
            'email': {"parameter_type": "sender_id"},
            'contact': {"value": "contact", "parameter_type": "slot"},
        }
        with pytest.raises(ValidationError):
            processor.add_razorpay_action(action, bot, user)

    def test_add_razorpay_action_with_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "razorpay_action", "type": "RAZORPAY_ACTION"},
        ]
        story_dict = {'name': "story with razorpay action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with razorpay action", bot=bot,
                                events__name='razorpay_action', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == "story with razorpay action"]
        assert story_with_form[0]['steps'] == [
            {"name": "greet", "type": "INTENT"},
            {"name": "razorpay_action", "type": "RAZORPAY_ACTION"},
        ]
        processor.delete_complex_story(story_id, 'STORY', bot, user)

    def test_add_razorpay_action_duplicate(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action_name = 'razorpay_action'
        action = {
            'name': action_name,
            'api_key': {"value": "API_KEY", "parameter_type": "key_vault"},
            'api_secret': {"value": "API_SECRET", "parameter_type": "kay_vault"},
            'amount': {"value": "amount", "parameter_type": "slot"},
            'currency': {"value": "INR", "parameter_type": "value"},
            'username': {"parameter_type": "sender_id"},
            'email': {"parameter_type": "sender_id"},
            'contact': {"value": "contact", "parameter_type": "slot"},
        }
        with pytest.raises(AppException, match='Action exists!'):
            processor.add_razorpay_action(action, bot, user)

    def test_list_razorpay_action(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.get_razorpay_action_config(bot))
        actions[0].pop("timestamp")
        actions[0].pop("_id")
        assert actions == [
            {
                'name': 'razorpay_action',
                'api_key': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'api_key',
                    'encrypt': False,
                    'value': 'API_KEY',
                    'parameter_type': 'key_vault'
                },
                'api_secret': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'api_secret',
                    'encrypt': False,
                    'value': 'API_SECRET',
                    'parameter_type': 'kay_vault'
                },
                'amount': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'amount',
                    'encrypt': False,
                    'value': 'amount',
                    'parameter_type': 'slot'
                },
                'currency': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'currency',
                    'encrypt': False,
                    'value': 'INR',
                    'parameter_type': 'value'
                },
                'username': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'username',
                    'encrypt': False,
                    'parameter_type': 'sender_id'
                },
                'email': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'email',
                    'encrypt': False,
                    'parameter_type': 'sender_id'
                },
                'contact': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'contact',
                    'encrypt': False,
                    'value': 'contact',
                    'parameter_type': 'slot'
                },
                'notes': [
                    {
                        '_cls': 'CustomActionRequestParameters',
                        'key': 'order_id',
                        'encrypt': False,
                        'value': 'order_id',
                        'parameter_type': 'slot'
                    },
                    {
                        '_cls': 'CustomActionRequestParameters',
                        'key': 'phone_number',
                        'encrypt': False,
                        'value': '9876543210',
                        'parameter_type': 'value'
                    }
                ]
            }
        ]

    def test_list_razorpay_action_with_false(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.get_razorpay_action_config(bot, False))
        actions[0].pop("timestamp")
        assert actions[0].get("_id") is None
        assert actions == [
            {
                'name': 'razorpay_action',
                'api_key': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'api_key',
                    'encrypt': False,
                    'value': 'API_KEY',
                    'parameter_type': 'key_vault'
                },
                'api_secret': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'api_secret',
                    'encrypt': False,
                    'value': 'API_SECRET',
                    'parameter_type': 'kay_vault'
                },
                'amount': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'amount',
                    'encrypt': False,
                    'value': 'amount',
                    'parameter_type': 'slot'
                },
                'currency': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'currency',
                    'encrypt': False,
                    'value': 'INR',
                    'parameter_type': 'value'
                },
                'username': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'username',
                    'encrypt': False,
                    'parameter_type': 'sender_id'
                },
                'email': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'email',
                    'encrypt': False,
                    'parameter_type': 'sender_id'
                },
                'contact': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'contact',
                    'encrypt': False,
                    'value': 'contact',
                    'parameter_type': 'slot'
                },
                'notes': [
                    {
                        '_cls': 'CustomActionRequestParameters',
                        'key': 'order_id',
                        'encrypt': False,
                        'value': 'order_id',
                        'parameter_type': 'slot'
                    },
                    {
                        '_cls': 'CustomActionRequestParameters',
                        'key': 'phone_number',
                        'encrypt': False,
                        'value': '9876543210',
                        'parameter_type': 'value'
                    }
                ]
            }
        ]

    def test_edit_razorpay_action_not_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action_name = 'test_edit_razorpay_action_not_exists'
        action = {
            'name': action_name,
            'api_key': {"value": "API_KEY", "parameter_type": "key_vault"},
            'api_secret': {"value": "API_SECRET", "parameter_type": "kay_vault"},
            'amount': {"value": "amount", "parameter_type": "slot"},
            'currency': {"value": "INR", "parameter_type": "value"},
            'username': {"parameter_type": "sender_id"},
            'email': {"parameter_type": "sender_id"},
            'contact': {"value": "contact", "parameter_type": "slot"},
        }
        with pytest.raises(AppException, match='Action with name "test_edit_razorpay_action_not_exists" not found'):
            processor.edit_razorpay_action(action, bot, user)

    def test_edit_razorpay_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action_name = 'razorpay_action'
        action = {
            'name': action_name,
            'api_key': {"value": "API_KEY", "parameter_type": "key_vault"},
            'api_secret': {"value": "API_SECRET", "parameter_type": "kay_vault"},
            'amount': {"value": "amount", "parameter_type": "slot"},
            'currency': {"value": "INR", "parameter_type": "value"},
            'notes': [
                {"key": "phone_number", "parameter_type": "value", "value": "9876543210"}
            ]
        }
        assert not processor.edit_razorpay_action(action, bot, user)

    def test_list_razorpay_action_after_update(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.get_razorpay_action_config(bot))
        actions[0].pop("timestamp")
        actions[0].pop("_id")
        assert actions == [
            {
                'name': 'razorpay_action',
                'api_key': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'api_key',
                    'encrypt': False,
                    'value': 'API_KEY',
                    'parameter_type': 'key_vault'
                },
                'api_secret': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'api_secret',
                    'encrypt': False,
                    'value': 'API_SECRET',
                    'parameter_type': 'kay_vault'
                },
                'amount': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'amount',
                    'encrypt': False,
                    'value': 'amount',
                    'parameter_type': 'slot'
                },
                'currency': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'currency',
                    'encrypt': False,
                    'value': 'INR',
                    'parameter_type': 'value'
                },
                'notes': [
                    {
                        '_cls': 'CustomActionRequestParameters',
                        'key': 'phone_number',
                        'encrypt': False,
                        'value': '9876543210',
                        'parameter_type': 'value'
                    }
                ]
            }
        ]

    def test_delete_razorpay_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        processor.delete_action('razorpay_action', bot, user)
        with pytest.raises(DoesNotExist):
            Actions.objects(name='razorpay_action', status=True, bot=bot).get()
        with pytest.raises(DoesNotExist):
            RazorpayAction.objects(name='razorpay_action', status=True, bot=bot).get()

    @responses.activate
    def test_push_notifications_enabled_message_type_event(self, monkeypatch):
        bot = "test"
        user = 'test'
        url = "http://localhost/events"
        with patch.dict(Utility.environment['notifications'], {"enable": True, "server_endpoint": url}):
            responses.add(
                'POST',
                f'{url}/test',
                json={'message': 'Event in progress'}
            )
            ModelProcessor.set_training_status(bot, user, "Inprogress")
            request_body = responses.calls[0].request
            request_body = request_body.body.decode('utf8')
            request_body = json.loads(request_body)
            assert responses.calls[0].request.headers['Authorization']
            assert request_body['event_type'] == "message"
            assert request_body['event']['entity_type'] == "ModelTraining"
            assert request_body['event']['data']['status'] == 'Inprogress'
            assert request_body['event']['data']['bot'] == bot
            assert request_body['event']['data']['user'] == user
            assert not Utility.check_empty_string(request_body['event']['data']['start_timestamp'])

    def test_delete_valid_intent_only(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.delete_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        with pytest.raises(Exception):
            intent = Intents.objects(bot="tests", status=True).get(name="TestingDelGreeting")

    def test_delete_invalid_intent(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.delete_intent("TestingDelGreetingInvalid", "tests", "testUser", is_integration=False)

    def test_delete_empty_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AssertionError):
            processor.delete_intent("", "tests", "testUser", is_integration=False)

    def test_delete_valid_intent(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.delete_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)

    def test_delete_intent_case_insensitive(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.delete_intent("testingdelgreeting", "tests", "testUser", is_integration=False)

    def test_intent_no_stories(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.add_training_example(["Hows You Doing!"], "TestingDelGreeting", "tests", "testUser",
                                       is_integration=False)
        processor.delete_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        actual = processor.get_intents("tests")
        assert not any(intent['name'] == 'TestingDelGreeting' for intent in actual)
        actual = len(list(processor.get_training_examples("TestingDelGreeting", "tests")))
        assert not actual

    def test_get_intents_and_training_examples(self):
        processor = MongoProcessor()
        actual = processor.get_intents_and_training_examples("tests")
        assert len(actual) == 19

    def test_delete_intent_no_training_examples(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.delete_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        actual = processor.get_intents("tests")
        assert not any(intent['name'] == 'TestingDelGreeting' for intent in actual)

    def test_delete_intent_no_utterance(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.delete_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        actual = processor.get_intents("tests")
        assert not any(intent['name'] == 'TestingDelGreeting' for intent in actual)

    def test_delete_intent_with_examples_stories_utterance(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.add_training_example(["hello", "hi"], "TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.delete_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        actual = processor.get_intents("tests")
        assert not any(intent['name'] == 'TestingDelGreeting' for intent in actual)
        actual = list(processor.get_training_examples('TestingDelGreeting', "tests"))
        assert len(actual) == 0

    def test_move_training_example(self):
        processor = MongoProcessor()
        list(processor.add_training_example(["moving to another location", "i will stay"], "test_move_training_example",
                                            "tests", "testUser", is_integration=False))
        list(processor.add_training_example(
            ["moving to another intent [move_to_location](move_to_location)", "i will be here"],
            "move_training_example",
            "tests", "testUser", is_integration=False))
        list(processor.add_training_example(["this is forever"], "move_to_location",
                                            "tests", "testUser", is_integration=False))
        examples_to_move = ["moving to another location", "moving to another place",
                            "moving to another intent [move_to_location](move_to_location)", "this is new", "", " "]
        result = list(processor.add_or_move_training_example(examples_to_move, 'move_to_location', "tests", "testUser"))
        actual = list(processor.get_training_examples('move_to_location', "tests"))
        assert len(actual) == 5
        actual = list(processor.get_training_examples('test_move_training_example', "tests"))
        assert len(actual) == 1
        actual = list(processor.get_training_examples('move_training_example', "tests"))
        assert len(actual) == 1

    def test_move_training_example_intent_not_exists(self):
        processor = MongoProcessor()
        examples_to_move = ["moving to another location", "moving to another place", "", " "]
        with pytest.raises(AppException, match='Intent does not exists'):
            list(processor.add_or_move_training_example(examples_to_move, 'non_existent', "tests", "testUser"))

    def test_add_vector_embedding_action_config_op_embedding_search(self):
        processor = CognitionDataProcessor()
        processor_two = MongoProcessor()
        bot = 'test_vector_bot'
        user = 'test_vector_user'
        action = 'test_vectordb_action_op_embedding_search'
        response = '0'
        query_type = 'embedding_search'
        payload_body = {
            "ids": [
                0
            ],
            "with_payload": True,
            "with_vector": True
        }
        payload = {'type': 'from_value', 'value': payload_body, 'query_type': query_type,}
        schema = {
            "metadata": [
                {"column_name": "country", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "test_add_vector_embedding_action_config_op_embedding_search",
            "bot": bot,
            "user": user
        }
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        pytest.delete_schema_id_db_action = processor.save_cognition_schema(schema, user, bot)
        CognitionData(
            data={"country": "India"},
            content_type="json",
            collection="test_add_vector_embedding_action_config_op_embedding_search",
            bot=bot, user=user).save()
        vectordb_action_config = DatabaseActionRequest(
            name=action,
            collection='test_add_vector_embedding_action_config_op_embedding_search',
            payload=[payload],
            response=ActionResponseEvaluation(value=response)
        )
        processor_two.add_db_action(vectordb_action_config.dict(), user, bot)
        actual_vectordb_action = DatabaseAction.objects(name=action, bot=bot, status=True).get()
        assert actual_vectordb_action is not None
        assert Actions.objects(name=action, status=True, bot=bot).get()
        assert actual_vectordb_action['name'] == action
        assert actual_vectordb_action['payload'][0]['type'] == 'from_value'
        assert actual_vectordb_action['payload'][0]['value'] == {'ids': [0], 'with_payload': True, 'with_vector': True}
        assert actual_vectordb_action['payload'][0]['query_type'] == 'embedding_search'
        assert actual_vectordb_action['response']['value'] == '0'
        with pytest.raises(AppException,
                           match='Cannot remove collection test_add_vector_embedding_action_config_op_embedding_search linked to action "test_vectordb_action_op_embedding_search"!'):
            processor.delete_cognition_schema(pytest.delete_schema_id_db_action, bot, user=user)

    def test_add_vector_embedding_action_with_story(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot'
        user = 'test_vector_user'
        steps = [
            {"name": "helu", "type": "INTENT"},
            {"name": "test_vectordb_action_op_embedding_search", "type": "DATABASE_ACTION"},
        ]
        story_dict = {'name': "story with vector embedding action", 'steps': steps, 'type': 'STORY',
                      'template_type': 'CUSTOM'}
        story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with vector embedding action", bot=bot,
                                events__name='test_vectordb_action_op_embedding_search', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'story with vector embedding action']
        assert story_with_form[0]['steps'] == [
            {"name": "helu", "type": "INTENT"},
            {"name": "test_vectordb_action_op_embedding_search", "type": "DATABASE_ACTION"},
        ]
        processor.delete_complex_story(story_id, 'STORY', bot, user)

    def test_add_vector_embedding_action_config_op_payload_search(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot'
        user = 'test_vector_user'
        action = 'test_vectordb_action_op_payload_search'
        response = '1'
        query_type = 'payload_search'
        payload_body = {
            "filter": {
                "should": [
                    {"key": "city", "match": {"value": "London"}},
                    {"key": "color", "match": {"value": "red"}}
                ]
            }
        }
        payload = {'type': 'from_value', 'value': payload_body, 'query_type': query_type,}
        CognitionSchema(
            metadata=[{"column_name": "city", "data_type": "str", "enable_search": True, "create_embeddings": True},
                      {"column_name": "color", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            collection_name="test_add_vector_embedding_action_config_op_payload_search",
            bot=bot, user=user).save()
        CognitionData(
            data={"city": "London", "color": "red"},
            content_type="json",
            collection="test_add_vector_embedding_action_config_op_payload_search",
            bot=bot, user=user).save()
        vectordb_action_config = DatabaseActionRequest(
            name=action,
            collection='test_add_vector_embedding_action_config_op_payload_search',
            payload=[payload],
            response=ActionResponseEvaluation(value=response)
        )
        processor.add_db_action(vectordb_action_config.dict(), user, bot)
        actual_vectordb_action = DatabaseAction.objects(name=action, bot=bot, status=True).get()
        assert actual_vectordb_action is not None
        assert Actions.objects(name=action, status=True, bot=bot).get()
        assert actual_vectordb_action['name'] == action
        assert actual_vectordb_action['payload'][0]['type'] == 'from_value'
        assert actual_vectordb_action['payload'][0]['value'] == payload_body
        assert actual_vectordb_action['payload'][0]['query_type'] == 'payload_search'
        assert actual_vectordb_action['response']['value'] == '1'

    def test_add_vector_embedding_action_config_op_embedding_search_from_slot(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot'
        user = 'test_vector_user'
        action = 'test_vectordb_action_op_embedding_search_from_slot'
        response = 'nupur.khare'
        query_type = 'embedding_search'
        payload = {'type': 'from_slot', 'value': 'email', 'query_type': query_type,}
        processor.add_slot({"name": "email", "type": "text", "initial_value": "nupur.khare@digite.com",
                            "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)
        CognitionSchema(
            metadata=[{"column_name": "age", "data_type": "int", "enable_search": True, "create_embeddings": True}],
            collection_name="test_add_vector_embedding_action_config_op_embedding_search_from_slot",
            bot=bot, user=user).save()
        CognitionData(
            data={"age": 23},
            content_type="json",
            collection="test_add_vector_embedding_action_config_op_embedding_search_from_slot",
            bot=bot, user=user).save()
        vectordb_action_config = DatabaseActionRequest(
            name=action,
            collection='test_add_vector_embedding_action_config_op_embedding_search_from_slot',
            payload=[payload],
            response=ActionResponseEvaluation(value=response),
            set_slots=[SetSlotsUsingActionResponse(name="age", value="${data.age}", evaluation_type="expression")]
        )
        processor.add_db_action(vectordb_action_config.dict(), user, bot)
        actual_vectordb_action = DatabaseAction.objects(name=action, bot=bot, status=True).get()
        assert actual_vectordb_action is not None
        assert Actions.objects(name=action, status=True, bot=bot).get()
        assert actual_vectordb_action['name'] == action
        assert actual_vectordb_action[
                   'collection'] == 'test_add_vector_embedding_action_config_op_embedding_search_from_slot'
        assert actual_vectordb_action['payload'][0]['type'] == 'from_slot'
        assert actual_vectordb_action['payload'][0]['value'] == 'email'
        assert actual_vectordb_action['payload'][0]['query_type'] == 'embedding_search'
        assert actual_vectordb_action['response']['value'] == 'nupur.khare'

    def test_add_vector_embedding_action_config_op_embedding_search_from_slot_does_not_exists(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot_slot'
        user = 'test_vector_user_slot'
        action = 'test_vectordb_action_slot'
        response = 'nupur.khare'
        query_type = 'embedding_search'
        payload = {'type': 'from_slot', 'value': 'cuisine', 'query_type': query_type,}
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        vectordb_action_config = DatabaseActionRequest(
            name=action,
            collection='test_add_vector_embedding_action_config_op_embedding_search_from_slot_does_not_exists',
            payload=[payload],
            response=ActionResponseEvaluation(value=response),
            set_slots=[SetSlotsUsingActionResponse(name="age", value="${data.age}", evaluation_type="expression")]
        )
        with pytest.raises(AppException, match="Slot with name cuisine not found!"):
            processor.add_db_action(vectordb_action_config.dict(), user, bot)

    def test_add_vector_embedding_action_collection_does_not_exists(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot_slot'
        user = 'test_vector_user_slot'
        action = 'test_vectordb_action_collection_not_exists'
        response = '1'
        query_type = 'payload_search'
        payload_body = {
            "filter": {
                "should": [
                    {"key": "city", "match": {"value": "London"}},
                    {"key": "color", "match": {"value": "red"}}
                ]
            }
        }
        payload = {'type': 'from_value', 'value': payload_body, 'query_type': query_type,}
        vectordb_action_config = DatabaseActionRequest(
            name=action,
            collection='test_add_vector_embedding_action_collection_does_not_exists',
            payload=[payload],
            response=ActionResponseEvaluation(value=response),
        )
        with pytest.raises(AppException, match="Collection does not exist!"):
            processor.add_db_action(vectordb_action_config.dict(), user, bot)

    def test_add_vector_embedding_action_config_existing_name(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot'
        user = 'test_vector_user'
        action = 'test_vectordb_action_op_embedding_search'
        response = '0'
        query_type = 'embedding_search'
        payload_body = {
            "ids": [
                0
            ],
            "with_payload": True,
            "with_vector": True
        }
        payload = {'type': 'from_value', 'value': payload_body, 'query_type': query_type,}
        vectordb_action_config = DatabaseActionRequest(
            name=action,
            collection='test_add_vector_embedding_action_config_existing_name',
            payload=[payload],
            response=ActionResponseEvaluation(value=response)
        )
        with pytest.raises(AppException, match="Action exists"):
            processor.add_db_action(vectordb_action_config.dict(), user, bot)

    def test_add_vector_embedding_action_config_empty_payload_values(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot_empty_name'
        user = 'test_vector_user_empty_name'
        action = 'test_add_vectordb_action_config_empty_name'
        response = '0'
        query_type = 'embedding_search'
        payload_body = {
            "ids": [
                0
            ],
            "with_payload": True,
            "with_vector": True
        }
        payload = {'type': 'from_value', 'value': payload_body, 'query_type': query_type,}
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        CognitionSchema(
            metadata=[{"column_name": "age", "data_type": "int", "enable_search": True, "create_embeddings": True}],
            collection_name="test_add_vector_embedding_action_config_empty_payload_values",
            bot=bot, user=user).save()
        CognitionData(
            data={"age": 23},
            content_type="json",
            collection="test_add_vector_embedding_action_config_empty_payload_values",
            bot=bot, user=user).save()
        vectordb_action_config = DatabaseActionRequest(
            name=action,
            collection='test_add_vector_embedding_action_config_empty_payload_values',
            payload=[payload],
            response=ActionResponseEvaluation(value=response)
        )
        vectordb_action = vectordb_action_config.dict()
        vectordb_action['name'] = ''
        with pytest.raises(ValidationError, match="Action name cannot be empty"):
            processor.add_db_action(vectordb_action, user, bot)
        vectordb_action_config_two = DatabaseActionRequest(
            name=action,
            collection='test_add_vector_embedding_action_config_empty_payload_values',
            payload=[payload],
            response=ActionResponseEvaluation(value=response)
        )
        vectordb_action_two = vectordb_action_config_two.dict()
        vectordb_action_two['payload'][0]['type'] = ''
        with pytest.raises(ValidationError, match="payload type is required"):
            processor.add_db_action(vectordb_action_two, user, bot)

    def test_add_vector_embedding_action_config_empty_operation_values(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot_empty_operation_values'
        user = 'test_vector_user_empty_operation_values'
        action = 'test_add_vector_embedding_action_config_empty_operation_values'
        response = '0'
        query_type = 'payload_search'
        payload_body = {
            "ids": [
                0
            ],
            "with_payload": True,
            "with_vector": True
        }
        payload = {'type': 'from_value', 'value': payload_body, 'query_type': query_type,}
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        CognitionSchema(
            metadata=[{"column_name": "age", "data_type": "int", "enable_search": True, "create_embeddings": True}],
            collection_name="test_add_vector_embedding_action_config_empty_operation_values",
            bot=bot, user=user).save()
        CognitionData(
            data={"age": 23},
            content_type="json",
            collection="test_add_vector_embedding_action_config_empty_operation_values",
            bot=bot, user=user).save()
        vectordb_action_config = DatabaseActionRequest(
            name=action,
            collection='test_add_vector_embedding_action_config_empty_operation_values',
            payload=[payload],
            response=ActionResponseEvaluation(value=response)
        )
        vectordb_action = vectordb_action_config.dict()
        vectordb_action['name'] = ''
        with pytest.raises(ValidationError, match="Action name cannot be empty"):
            processor.add_db_action(vectordb_action, user, bot)
        vectordb_action_config_two = DatabaseActionRequest(
            name=action,
            collection='test_add_vector_embedding_action_config_empty_operation_values',
            payload=[payload],
            response=ActionResponseEvaluation(value=response)
        )
        vectordb_action_two = vectordb_action_config_two.dict()
        vectordb_action_two['payload'][0]['query_type'] = ''
        with pytest.raises(ValidationError, match="query type is required"):
            processor.add_db_action(vectordb_action_two, user, bot)

    def test_get_vector_embedding_action(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot_get'
        user = 'test_vector_user'
        action = 'test_get_vectordb_action'
        response = 'nupur.khare'

        query_type = 'embedding_search'
        payload = {'type': 'from_slot', 'value': 'email', 'query_type': query_type,}
        CognitionSchema(
            metadata=[{"column_name": "age", "data_type": "int", "enable_search": True, "create_embeddings": True}],
            collection_name="test_get_vector_embedding_action",
            bot=bot, user=user).save()
        CognitionData(
            data={"age": 23},
            content_type="json",
            collection="test_get_vector_embedding_action",
            bot=bot, user=user).save()
        DatabaseAction(
            name=action,
            collection='test_get_vector_embedding_action',
            payload=[payload],
            response=HttpActionResponse(value=response),
            set_slots=[SetSlotsFromResponse(name="email", value="${data.email}", evaluation_type="expression")],
            bot=bot,
            user=user
        ).save().to_mongo()
        actual = processor.get_db_action_config(bot=bot, action=action)
        assert actual is not None
        assert actual['name'] == action
        assert actual['payload'][0] == {'type': 'from_slot', 'value': 'email', 'query_type': 'embedding_search'}
        assert actual['collection'] == 'test_get_vector_embedding_action'
        assert actual['response'] == {'value': 'nupur.khare', 'dispatch': True, 'evaluation_type': 'expression',
                                      'dispatch_type': 'text'}
        assert actual['db_type'] == 'qdrant'
        assert actual['set_slots'] == [{'name': 'email', 'value': '${data.email}', 'evaluation_type': 'expression'}]

    def test_get_vector_embedding_action_does_not_exists(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot_get_action'
        user = 'test_vector_user'
        action = 'test_get_vectordb_action'
        response = 'nupur.khare'

        query_type = 'embedding_search'
        payload = {'type': 'from_slot', 'value': 'email', 'query_type': query_type,}
        DatabaseAction(
            name=action,
            collection='test_get_vector_embedding_action_does_not_exists',
            payload=[payload],
            response=HttpActionResponse(value=response),
            set_slots=[SetSlotsFromResponse(name="email", value="${data.email}", evaluation_type="expression")],
            bot=bot,
            user=user
        ).save().to_mongo()
        try:
            processor.get_db_action_config(bot=bot, action='embedding')
            assert False
        except AppException as e:
            assert str(e) == "Action does not exists!"

    def test_list_vector_embedding_action(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot'
        user = 'test_vector_user'
        actions = list(processor.list_db_actions(bot, True))
        assert len(actions) == 3

    def test_add_vector_embedding_action_with_utter(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot'
        user = 'test_vector_user'
        action = 'utter_test_vectordb_action_op_embedding_search'
        response = '0'
        query_type = 'embedding_search'
        payload_body = {
            "ids": [
                0
            ],
            "with_payload": True,
            "with_vector": True
        }
        payload = {'type': 'from_value', 'value': payload_body, 'query_type': query_type, }
        vectordb_action_config = DatabaseActionRequest(
            name=action,
            collection='test_add_vector_embedding_action_config_existing_name',
            payload=[payload],
            response=ActionResponseEvaluation(value=response)
        )
        with pytest.raises(AppException, match="Action name cannot start with utter_"):
            processor.add_db_action(vectordb_action_config.dict(), user, bot)

    def test_update_vector_embedding_action(self):
        processor = MongoProcessor()
        bot = 'test_update_vectordb_action_bot'
        user = 'test_update_vectordb_action_user'
        action = 'test_update_vectordb_action'
        response = '15'
        query_type = 'payload_search'
        payload_body = {
            "filter": {
                "should": [
                    {"key": "city", "match": {"value": "London"}},
                    {"key": "color", "match": {"value": "red"}}
                ]
            }
        }
        payload = {'type': 'from_value', 'value': payload_body, 'query_type': query_type,}
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        CognitionSchema(
            metadata=[{"column_name": "city", "data_type": "str", "enable_search": True, "create_embeddings": True},
                      {"column_name": "color", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            collection_name="test_update_vector_embedding_action",
            bot=bot, user=user).save()
        CognitionData(
            data={"city": "London", "color": "red"},
            content_type="json",
            collection="test_update_vector_embedding_action",
            bot=bot, user=user).save()
        vectordb_action_config = DatabaseActionRequest(
            name=action,
            collection='test_update_vector_embedding_action',
            payload=[payload],
            response=ActionResponseEvaluation(value=response)
        )
        processor.add_db_action(vectordb_action_config.dict(), user, bot)
        actual = DatabaseAction.objects(name=action, bot=bot, status=True).get()
        assert actual is not None
        assert actual['name'] == action
        assert actual['response']['value'] == '15'
        assert actual['payload'][0]['value'] == {'filter': {
            'should': [{'key': 'city', 'match': {'value': 'London'}}, {'key': 'color', 'match': {'value': 'red'}}]}}
        response_two = 'nimble'
        processor.add_slot({"name": "name", "type": "text", "initial_value": "nupur",
                            "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)
        payload_two = {'type': 'from_value', 'value': 'name', 'query_type': query_type}
        vectordb_action_config_updated = DatabaseActionRequest(
            name=action,
            collection='test_update_vector_embedding_action',
            payload=[payload_two],
            response=ActionResponseEvaluation(value=response_two),
            set_slots=[SetSlotsUsingActionResponse(name="name", value="${data.name}", evaluation_type="expression")]
        )
        processor.update_db_action(vectordb_action_config_updated.dict(), user, bot)
        actual_two = DatabaseAction.objects(name=action, bot=bot, status=True).get()
        assert actual_two is not None
        assert actual_two['name'] == action
        assert actual_two['response']['value'] == 'nimble'
        assert actual_two['payload'][0]['value'] == 'name'

    def test_update_vector_embedding_action_does_not_exists(self):
        processor = MongoProcessor()
        bot = 'test_update_vectordb_action_bot'
        user = 'test_update_vectordb_action_user'
        action = 'test_update_vectordb_action_does_not_exists'
        response = 'Digite'
        query_type = 'embedding_search'
        payload_body = {
            "ids": [
                0
            ],
            "with_payload": True,
            "with_vector": True
        }
        payload = {'type': 'from_value', 'value': payload_body, 'query_type': query_type,}
        vectordb_action_config = DatabaseActionRequest(
            name=action,
            collection='test_update_vector_embedding_action_does_not_exists',
            payload=[payload],
            response=ActionResponseEvaluation(value=response)
        )
        with pytest.raises(AppException,
                           match='Action with name "test_update_vectordb_action_does_not_exists" not found'):
            processor.update_db_action(vectordb_action_config.dict(), user, bot)

    def test_delete_vector_embedding_action_config(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot'
        user = 'test_vector_user'
        action = 'test_delete_vector_embedding_action_config'
        response = '0'
        query_type = 'embedding_search'
        payload_body = {
            "ids": [
                0
            ],
            "with_payload": True,
            "with_vector": True
        }
        payload = {'type': 'from_value', 'value': payload_body, 'query_type': query_type,}
        Actions(name=action, type=ActionType.database_action.value, bot=bot, user=user).save()
        DatabaseAction(
            name=action,
            collection='test_delete_vector_embedding_action_config',
            payload=[payload],
            response=HttpActionResponse(value=response),
            bot=bot,
            user=user
        ).save().to_mongo()
        processor.delete_action(action, user=user, bot=bot)
        try:
            DatabaseAction.objects(name=action, bot=bot, user=user, status=True).get(
                name__iexact=action)
            assert False
        except DoesNotExist:
            assert True

    def test_delete_vector_embedding_action_config_non_existing(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot'
        user = 'test_vector_user'
        action = 'test_delete_vector_embedding_action_config_non_existing'
        response = '0'
        query_type = 'embedding_search'
        payload_body = {
            "ids": [
                0
            ],
            "with_payload": True,
            "with_vector": True
        }
        payload = {'type': 'from_value', 'value': payload_body, 'query_type': query_type,}
        DatabaseAction(
            name=action,
            collection='test_delete_vector_embedding_action_config_non_existing',
            payload=[payload],
            response=HttpActionResponse(value=response),
            bot=bot,
            user=user
        ).save().to_mongo()

        try:
            processor.delete_action("test_delete_vector_embedding_action_config_non_existing_non_existing", user=user,
                                    bot=bot)
            assert False
        except AppException as e:
            assert str(e).__contains__(
                'Action with name "test_delete_vector_embedding_action_config_non_existing_non_existing" not found')

    def test_add_http_action_config_with_utter(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'utter_test_action'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        params = [HttpActionParameters(key="key", value="value", parameter_type="slot")]

        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=ActionResponseEvaluation(value=response),
            http_url=http_url,
            request_method=request_method,
            params_list=params
        )
        with pytest.raises(AppException, match="Action name cannot start with utter_"):
            processor.add_http_action_config(http_action_config.dict(), user, bot)

    def test_add_http_action_config(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_action'
        # file deepcode ignore HardcodedNonCryptoSecret: Random string for testing
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        http_params_list: List[HttpActionParameters] = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value")]
        header: List[HttpActionParameters] = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=ActionResponseEvaluation(value=response),
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list,
            headers=header
        )
        processor.add_http_action_config(http_action_config.dict(), user, bot)
        actual_http_action = HttpActionConfig.objects(action_name=action, bot=bot, user=user, status=True).get(
            action_name__iexact=action).to_mongo().to_dict()
        assert actual_http_action is not None
        assert actual_http_action['action_name'] == action
        assert actual_http_action['http_url'] == http_url
        assert actual_http_action['response'] == {"value": response, "dispatch": True, "evaluation_type": "expression",
                                                  "dispatch_type": "text"}
        assert actual_http_action['request_method'] == request_method
        assert actual_http_action['params_list'] is not None
        assert actual_http_action['params_list'][0]['key'] == "param1"
        assert actual_http_action['params_list'][0]['value'] == "param1"
        assert actual_http_action['params_list'][0]['parameter_type'] == "slot"
        assert actual_http_action['params_list'][1]['key'] == "param2"
        assert actual_http_action['params_list'][1]['value'] == "value2"
        assert actual_http_action['params_list'][1]['parameter_type'] == "value"
        assert actual_http_action['headers'][0]['key'] == "param3"
        assert actual_http_action['headers'][0]['value'] == "param1"
        assert actual_http_action['headers'][0]['parameter_type'] == "slot"
        assert actual_http_action['headers'][1]['key'] == "param4"
        assert actual_http_action['headers'][1]['value'] == "value2"
        assert actual_http_action['headers'][1]['parameter_type'] == "value"
        assert Utility.is_exist(Actions, raise_error=False, name__iexact=action, bot=bot)

    def test_add_http_action_config_no_response(self):
        processor = MongoProcessor()
        bot = 'test_bot_2'
        http_url = 'http://www.google.com'
        action = 'test_add_http_action_config_no_response'
        user = 'test_user'
        request_method = 'GET'
        http_params_list: List[HttpActionParameters] = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value")]
        header: List[HttpActionParameters] = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=ActionResponseEvaluation(value=None, dispatch=False, evaluation_type="script"),
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list,
            headers=header,
            set_slots=[SetSlotsUsingActionResponse(name="bot", value="${data.key}", evaluation_type="script"),
                       SetSlotsUsingActionResponse(name="email", value="${data.email}", evaluation_type="expression")]
        )
        processor.add_http_action_config(http_action_config.dict(), user, bot)
        actual_http_action = HttpActionConfig.objects(action_name=action, bot=bot, user=user, status=True).get(
            action_name__iexact=action).to_mongo().to_dict()
        actual_http_action.pop('_id')
        actual_http_action.pop("timestamp")
        actual_http_action = json.loads(json.dumps(actual_http_action))
        assert actual_http_action is not None
        assert actual_http_action == {'action_name': 'test_add_http_action_config_no_response',
                                      'http_url': 'http://www.google.com',
                                      'request_method': 'GET', 'content_type': 'json', 'params_list': [
                {'_cls': 'HttpActionRequestBody', 'key': 'param1', 'value': 'param1', 'parameter_type': 'slot',
                 'encrypt': False},
                {'_cls': 'HttpActionRequestBody', 'key': 'param2', 'value': 'value2', 'parameter_type': 'value',
                 'encrypt': False}], 'headers': [
                {'_cls': 'HttpActionRequestBody', 'key': 'param3', 'value': 'param1', 'parameter_type': 'slot',
                 'encrypt': False},
                {'_cls': 'HttpActionRequestBody', 'key': 'param4', 'value': 'value2', 'parameter_type': 'value',
                 'encrypt': False}],
                                      'response': {'dispatch': False, 'evaluation_type': 'script'
                                          , "dispatch_type": "text"}, 'set_slots': [
                {'name': 'bot', 'value': '${data.key}', 'evaluation_type': 'script'},
                {'name': 'email', 'value': '${data.email}', 'evaluation_type': 'expression'}], 'bot': 'test_bot_2',
                                      'user': 'test_user', 'status': True}
        assert Utility.is_exist(Actions, raise_error=False, name__iexact=action, bot=bot)

    def test_add_http_action_config_complete_data(self):
        processor = MongoProcessor()
        bot = 'test_bot_1'
        http_url = 'http://www.google.com'
        action = 'test_add_http_action_config_complete_data'
        user = 'test_user'
        request_method = 'GET'
        http_params_list: List[HttpActionParameters] = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value", encrypt=True)]
        header: List[HttpActionParameters] = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value", encrypt=True)]
        http_action_config = HttpActionConfigRequest(
            content_type=HttpContentType.urlencoded_form_data.value,
            action_name=action,
            response=ActionResponseEvaluation(value="${RESPONSE}", dispatch=True, evaluation_type="expression"),
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list,
            headers=header,
            set_slots=[SetSlotsUsingActionResponse(name="bot", value="${data.key}", evaluation_type="script"),
                       SetSlotsUsingActionResponse(name="email", value="${data.email}", evaluation_type="expression")]
        )
        processor.add_http_action_config(http_action_config.dict(), user, bot)
        config = processor.get_http_action_config(bot, action)
        config.pop("timestamp")
        config = json.loads(json.dumps(config))
        assert config == {'action_name': 'test_add_http_action_config_complete_data',
                          'http_url': 'http://www.google.com', 'request_method': 'GET',
                          'content_type': 'application/x-www-form-urlencoded',
                          'params_list': [
                              {'key': 'param1', 'value': 'param1', 'parameter_type': 'slot', 'encrypt': False},
                              {'key': 'param2', 'value': 'value2', 'parameter_type': 'value', 'encrypt': True}],
                          'headers': [{'key': 'param3', 'value': 'param1', 'parameter_type': 'slot', 'encrypt': False},
                                      {'key': 'param4', 'value': 'value2', 'parameter_type': 'value', 'encrypt': True}],
                          'response': {'value': '${RESPONSE}', 'dispatch': True, 'evaluation_type': 'expression',
                                       "dispatch_type": "text"},
                          'set_slots': [{'name': 'bot', 'value': '${data.key}', 'evaluation_type': 'script'},
                                        {'name': 'email', 'value': '${data.email}', 'evaluation_type': 'expression'}],
                          'bot': 'test_bot_1', 'user': 'test_user', 'status': True}
        assert Utility.is_exist(Actions, raise_error=False, name__iexact=action, bot=bot)

    def test_add_http_action_config_missing_values(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_action_missing_values'
        # file deepcode ignore HardcodedNonCryptoSecret: Random string for testing
        auth_token = "bearer dhdshghfhzxfgadfhdhdhshdshsdfhsdhsdhnxngfgxngf"
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        http_params_list: List[HttpActionParameters] = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            auth_token=auth_token,
            action_name=action,
            response=ActionResponseEvaluation(value=response, dispatch_type=DispatchType.json.value),
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list
        )
        http_dict = http_action_config.dict()
        http_dict['action_name'] = ''
        with pytest.raises(ValidationError, match="Action name cannot be empty"):
            processor.add_http_action_config(http_dict, user, bot)
        http_dict['action_name'] = action
        http_dict['response']['dispatch_type'] = 'invalid_dispatch_type'
        with pytest.raises(ValidationError, match="Invalid dispatch_type"):
            processor.add_http_action_config(http_dict, user, bot)
        http_dict['response']['dispatch_type'] = DispatchType.json.value
        http_dict['http_url'] = None
        with pytest.raises(ValidationError, match="URL cannot be empty"):
            processor.add_http_action_config(http_dict, user, bot)
        http_dict['http_url'] = "www.google.com"
        with pytest.raises(ValidationError, match="URL is malformed"):
            processor.add_http_action_config(http_dict, user, bot)
        http_dict['http_url'] = http_url
        http_dict['request_method'] = "XYZ"
        with pytest.raises(ValidationError, match="Invalid HTTP method"):
            processor.add_http_action_config(http_dict, user, bot)
        http_dict['request_method'] = "GET"
        http_dict['params_list'][0]['key'] = None
        with pytest.raises(ValidationError, match="key in http action parameters cannot be empty"):
            processor.add_http_action_config(http_dict, user, bot)
        http_dict['params_list'][0]['value'] = None
        http_dict['params_list'][0]['key'] = "param1"
        with pytest.raises(ValidationError, match="Provide name of the slot as value"):
            processor.add_http_action_config(http_dict, user, bot)
        http_dict['params_list'][0]['value'] = "bot"
        http_dict['params_list'][0]['key'] = "param1"
        http_dict['response']['dispatch'] = True
        http_dict['response']['value'] = "  "
        with pytest.raises(ValidationError, match="response is required for dispatch"):
            processor.add_http_action_config(http_dict, user, bot)
        http_dict['response']['value'] = "Action executed"
        http_dict['params_list'].append(
            {"key": "Access_key", "value": "  ", "parameter_type": "key_vault", "encrypt": False})
        with pytest.raises(ValidationError, match="Provide key from key vault as value"):
            processor.add_http_action_config(http_dict, user, bot)

    def test_list_http_action(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        actions = processor.list_http_actions(bot)
        assert len(actions) == 1

    def test_list_http_action_names(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        actions = processor.list_http_action_names(bot)
        assert len(actions) == 1

    def test_list_http_action_names_empty(self):
        processor = MongoProcessor()
        bot = 'test_bot1'
        actions = processor.list_http_action_names(bot)
        assert len(actions) == 0

    def test_add_http_action_config_existing(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_add_http_action_config_existing'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        params = [HttpActionParameters(key="key", value="value", parameter_type="slot")]

        HttpActionConfig(
            action_name=action,
            response=HttpActionResponse(value=response),
            http_url=http_url,
            request_method=request_method,
            bot=bot,
            user=user
        ).save().id.__str__()

        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=ActionResponseEvaluation(value=response),
            http_url=http_url,
            request_method=request_method,
            params_list=params
        )
        try:
            processor.add_http_action_config(http_action_config.dict(), user, bot)
            assert False
        except AppException as ex:
            assert str(ex).__contains__("Action exists")

    def test_add_http_action_config_existing_name(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_action'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        params = [HttpActionParameters(key="key", value="value", parameter_type="slot")]

        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=ActionResponseEvaluation(value=response),
            http_url=http_url,
            request_method=request_method,
            params_list=params
        )
        with pytest.raises(AppException, match="Action exists"):
            processor.add_http_action_config(http_action_config.dict(), user, bot)

    def test_delete_http_action_config(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_delete_http_action_config'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        Actions(name=action, type=ActionType.http_action.value, bot=bot, user=user).save()
        HttpActionConfig(
            action_name=action,
            response=HttpActionResponse(value=response),
            http_url=http_url,
            request_method=request_method,
            bot=bot,
            user=user
        ).save().to_mongo()
        processor.delete_action(action, user=user, bot=bot)
        try:
            HttpActionConfig.objects(action_name=action, bot=bot, user=user, status=True).get(
                action_name__iexact=action)
            assert False
        except DoesNotExist:
            assert True

    def test_delete_http_action_config_non_existing(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        action = 'test_delete_http_action_config_non_existing'
        user = 'test_user'
        http_url = 'http://www.google.com'
        response = "json"
        request_method = 'GET'
        HttpActionConfig(
            action_name=action,
            response=HttpActionResponse(value=response),
            http_url=http_url,
            request_method=request_method,
            bot=bot,
            user=user
        ).save().to_mongo()
        try:
            processor.delete_action("test_delete_http_action_config_non_existing_non_existing", user=user, bot=bot)
            assert False
        except AppException as e:
            assert str(e).__contains__(
                'Action with name "test_delete_http_action_config_non_existing_non_existing" not found')

    def test_get_http_action_config(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_get_http_action_config1'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        HttpActionConfig(
            action_name=action,
            response=HttpActionResponse(value=response),
            http_url=http_url,
            request_method=request_method,
            bot=bot,
            user=user
        ).save().to_mongo()

        actual_test_user1 = processor.get_http_action_config(bot=bot, action_name=action)
        assert actual_test_user1 is not None
        assert actual_test_user1['action_name'] == action
        assert actual_test_user1['content_type'] == 'application/json'
        assert actual_test_user1['response'] == {'dispatch': True, 'evaluation_type': 'expression', 'value': 'json',
                                                 "dispatch_type": "text"}
        assert actual_test_user1['http_url'] == http_url
        assert actual_test_user1['request_method'] == request_method

        http_url1 = 'http://www.google.com'
        action1 = 'test_get_http_action_config'
        user1 = 'test_user1'
        response1 = ""
        request_method1 = 'POST'
        HttpActionConfig(
            action_name=action1,
            response=HttpActionResponse(value=response1, dispatch=False),
            http_url=http_url1,
            request_method=request_method1,
            bot=bot,
            user=user1
        ).save().to_mongo()

        actual_test_user2 = processor.get_http_action_config(bot=bot, action_name=action)
        assert actual_test_user2 is not None
        assert actual_test_user2['action_name'] == action
        assert actual_test_user2['response'] == {'dispatch': True, 'evaluation_type': 'expression', 'value': 'json',
                                                 "dispatch_type": "text"}
        assert actual_test_user2['http_url'] == http_url
        assert actual_test_user2['request_method'] == request_method

        http_url1 = 'http://www.google.com'
        action1 = 'test_get_http_action_config'
        user1 = 'test_user1'
        request_method1 = 'POST'
        HttpActionConfig(
            action_name=action1,
            response=HttpActionResponse(dispatch=False),
            http_url=http_url1,
            request_method=request_method1,
            bot=bot,
            user=user1
        ).save().to_mongo()

        actual_test_user2 = processor.get_http_action_config(bot=bot, action_name=action)
        assert actual_test_user2 is not None
        assert actual_test_user2['action_name'] == action
        assert actual_test_user2['response'] == {'dispatch': True, 'evaluation_type': 'expression', 'value': "json",
                                                 "dispatch_type": "text"}
        assert actual_test_user2['http_url'] == http_url
        assert actual_test_user2['request_method'] == request_method

    def test_get_http_action_config_non_existing(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_action'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        HttpActionConfig(
            action_name=action,
            response=HttpActionResponse(value=response),
            http_url=http_url,
            request_method=request_method,
            bot=bot,
            user=user
        ).save().to_mongo()

        try:
            processor.get_http_action_config(bot=bot, action_name="action")
            assert False
        except AppException as e:
            assert str(e) == "No HTTP action found for bot test_bot and action action"

    def test_add_http_action_config_with_dynamic_params(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_add_http_action_config_with_dynamic_params'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        dynamic_params = \
            "{\"sender_id\": \"${sender_id}\", \"user_message\": \"${user_message}\", \"intent\": \"${intent}\"}"
        dispatch_type = "json"
        header: List[HttpActionParameters] = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=ActionResponseEvaluation(value=response, dispatch_type=dispatch_type),
            http_url=http_url,
            request_method=request_method,
            dynamic_params=dynamic_params,
            headers=header
        )
        processor.add_http_action_config(http_action_config.dict(), user, bot)
        actual_http_action = HttpActionConfig.objects(action_name=action, bot=bot, user=user, status=True).get(
            action_name__iexact=action).to_mongo().to_dict()
        assert actual_http_action is not None
        assert actual_http_action['action_name'] == action
        assert actual_http_action['http_url'] == http_url
        assert actual_http_action['response'] == {"value": response, "dispatch": True, "evaluation_type": "expression",
                                                  "dispatch_type": "json"}
        assert actual_http_action['request_method'] == request_method
        assert actual_http_action['params_list'] == []
        assert actual_http_action['dynamic_params'] == dynamic_params
        assert actual_http_action['headers'][0]['key'] == "param3"
        assert actual_http_action['headers'][0]['value'] == "param1"
        assert actual_http_action['headers'][0]['parameter_type'] == "slot"
        assert actual_http_action['headers'][1]['key'] == "param4"
        assert actual_http_action['headers'][1]['value'] == "value2"
        assert actual_http_action['headers'][1]['parameter_type'] == "value"
        assert Utility.is_exist(Actions, raise_error=False, name__iexact=action, bot=bot)

    def test_update_http_config_with_dynamic_params(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_update_http_config_with_dynamic_params'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        dispatch_type = 'json'
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            content_type=HttpContentType.application_json.value,
            response=ActionResponseEvaluation(value=response, evaluation_type="script"),
            http_url=http_url,
            request_method=request_method,
            set_slots=[SetSlotsUsingActionResponse(name="bot", value="${data.key}", evaluation_type="script"),
                       SetSlotsUsingActionResponse(name="email", value="${data.email}", evaluation_type="expression")]
        )
        http_config_id = processor.add_http_action_config(http_action_config.dict(), user, bot)
        assert http_config_id is not None
        http_url = 'http://www.alphabet.com'
        response = "string"
        request_method = 'POST'
        dynamic_params = \
            "{\"sender_id\": \"${sender_id}\", \"user_message\": \"${user_message}\", \"intent\": \"${intent}\"}"
        dispatch_type = "text"
        header = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            content_type=HttpContentType.urlencoded_form_data.value,
            response=ActionResponseEvaluation(value=response, dispatch_type=dispatch_type),
            http_url=http_url,
            request_method=request_method,
            dynamic_params=dynamic_params,
            headers=header,
            set_slots=[SetSlotsUsingActionResponse(name="bot", value="${data.key}", evaluation_type="script")]
        )
        processor.update_http_config(http_action_config.dict(), user, bot)

        actual_http_action = HttpActionConfig.objects(action_name=action, bot=bot, user=user, status=True).get(
            action_name__iexact=action).to_mongo().to_dict()
        assert actual_http_action is not None
        assert actual_http_action['action_name'] == action
        assert actual_http_action['http_url'] == http_url
        assert actual_http_action['response'] == {"value": response, "dispatch": True, "evaluation_type": "expression",
                                                  "dispatch_type": "text"}
        assert actual_http_action['request_method'] == request_method
        assert actual_http_action['params_list'] == []
        assert actual_http_action['dynamic_params'] == dynamic_params
        assert actual_http_action['headers'][0]['key'] == "param3"
        assert actual_http_action['headers'][0]['value'] == "param1"
        assert actual_http_action['headers'][0]['parameter_type'] == "slot"
        assert actual_http_action['headers'][1]['key'] == "param4"
        assert actual_http_action['headers'][1]['value'] == "value2"
        assert actual_http_action['headers'][1]['parameter_type'] == "value"
        assert Utility.is_exist(Actions, raise_error=False, name__iexact=action, bot=bot)

    def test_update_http_config(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_update_http_config'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        http_params_list: List[HttpActionParameters] = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value", encrypt=True)]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            content_type=HttpContentType.application_json.value,
            response=ActionResponseEvaluation(value=response, evaluation_type="script"),
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list,
            set_slots=[SetSlotsUsingActionResponse(name="bot", value="${data.key}", evaluation_type="script"),
                       SetSlotsUsingActionResponse(name="email", value="${data.email}", evaluation_type="expression")]
        )
        http_config_id = processor.add_http_action_config(http_action_config.dict(), user, bot)
        assert http_config_id is not None
        http_url = 'http://www.alphabet.com'
        response = "string"
        request_method = 'POST'
        http_params_list = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value", encrypt=True),
            HttpActionParameters(key="param5", parameter_type="sender_id"),
            HttpActionParameters(key="param6", parameter_type="user_message"),
            HttpActionParameters(key="param7", parameter_type="chat_log"),
            HttpActionParameters(key="param8", parameter_type="intent")]
        header = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value", encrypt=True),
            HttpActionParameters(key="param3", parameter_type="sender_id"),
            HttpActionParameters(key="param4", parameter_type="user_message"),
            HttpActionParameters(key="param5", parameter_type="chat_log"),
            HttpActionParameters(key="param6", parameter_type="intent")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            content_type=HttpContentType.urlencoded_form_data.value,
            response=ActionResponseEvaluation(value=response),
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list,
            headers=header,
            set_slots=[SetSlotsUsingActionResponse(name="bot", value="${data.key}", evaluation_type="script")]
        )
        processor.update_http_config(http_action_config.dict(), user, bot)

        config = processor.get_http_action_config(bot, action)
        config.pop("timestamp")
        config = json.loads(json.dumps(config))
        assert config == {'action_name': 'test_update_http_config', 'http_url': 'http://www.alphabet.com',
                          'request_method': 'POST', 'content_type': 'application/x-www-form-urlencoded',
                          'params_list': [
                              {'key': 'param3', 'value': 'param1', 'parameter_type': 'slot', 'encrypt': False},
                              {'key': 'param4', 'value': 'value2', 'parameter_type': 'value', 'encrypt': True},
                              {'key': 'param5', 'value': '', 'parameter_type': 'sender_id', 'encrypt': False},
                              {'key': 'param6', 'value': '', 'parameter_type': 'user_message', 'encrypt': False},
                              {'key': 'param7', 'value': '', 'parameter_type': 'chat_log', 'encrypt': False},
                              {'key': 'param8', 'value': '', 'parameter_type': 'intent', 'encrypt': False}],
                          'headers': [{'key': 'param1', 'value': 'param1', 'parameter_type': 'slot', 'encrypt': False},
                                      {'key': 'param2', 'value': 'value2', 'parameter_type': 'value', 'encrypt': True},
                                      {'key': 'param3', 'value': '', 'parameter_type': 'sender_id', 'encrypt': False},
                                      {'key': 'param4', 'value': '', 'parameter_type': 'user_message',
                                       'encrypt': False},
                                      {'key': 'param5', 'value': '', 'parameter_type': 'chat_log', 'encrypt': False},
                                      {'key': 'param6', 'value': '', 'parameter_type': 'intent', 'encrypt': False}],
                          'response': {'value': 'string', 'dispatch': True, 'evaluation_type': 'expression',
                                       "dispatch_type": "text"},
                          'set_slots': [{'name': 'bot', 'value': '${data.key}', 'evaluation_type': 'script'}],
                          'bot': 'test_bot', 'user': 'test_user', 'status': True}

    def test_update_http_config_invalid_action(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_update_http_config_invalid_action'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        http_params_list: List[HttpActionParameters] = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=ActionResponseEvaluation(value=response),
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list
        )
        http_config_id = processor.add_http_action_config(http_action_config.dict(), user, bot)
        assert http_config_id is not None
        bot = 'test_bot'
        http_url = 'http://www.alphabet.com'
        action = 'test_update_http_config_invalid'
        user = 'test_user'
        response = "string"
        request_method = 'POST'
        http_params_list = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=ActionResponseEvaluation(value=response),
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list
        )
        try:
            processor.update_http_config(http_action_config.dict(), user, bot)
        except AppException as e:
            assert str(e) == 'No HTTP action found for bot test_bot and action test_update_http_config_invalid'

    def test_add_complex_story_without_http_action(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        story_dict = {'name': "story without action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.add_complex_story(story_dict, "test_without_http", "testUser")
        story = Stories.objects(block_name="story without action", bot="test_without_http").get()
        assert len(story.events) == 5
        actions = processor.list_actions("test_without_http")
        assert actions == {
            'utterances': [], 'http_action': [], 'slot_set_action': [], 'form_validation_action': [],
            'email_action': [], 'google_search_action': [], 'jira_action': [], 'zendesk_action': [],
            'pipedrive_leads_action': [], 'hubspot_forms_action': [], 'two_stage_fallback': [],
            'kairon_bot_response': [], 'razorpay_action': [], 'prompt_action': [], 'actions': [],
            'database_action': [], 'pyscript_action': [], 'web_search_action': [], 'live_agent_action': [],
            'callback_action': [], 'schedule_action': [],
        }

    def test_add_complex_story_with_action(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "action_check", "type": "ACTION"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        story_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.add_complex_story(story_dict, "test_with_action", "testUser")
        story = Stories.objects(block_name="story with action", bot="test_with_action").get()
        assert len(story.events) == 6
        actions = processor.list_actions("test_with_action")
        assert actions == {
            'actions': ['action_check'], 'utterances': [], 'http_action': [], 'slot_set_action': [],
            'form_validation_action': [], 'email_action': [], 'google_search_action': [], 'jira_action': [],
            'zendesk_action': [], 'pipedrive_leads_action': [], 'hubspot_forms_action': [], 'two_stage_fallback': [],
            'kairon_bot_response': [], 'razorpay_action': [], 'prompt_action': [], 'database_action': [],
            'pyscript_action': [], 'web_search_action': [], 'live_agent_action': [], 'callback_action': [], 'schedule_action': [],
        }

    def test_add_complex_story(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        story_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        pytest.story_id_two = processor.add_complex_story(story_dict, "tests", "testUser")
        story = Stories.objects(block_name="story with action", bot="tests").get()
        assert len(story.events) == 6
        actions = processor.list_actions("tests")
        assert not DeepDiff(actions, {'actions': [], 'zendesk_action': [], 'pipedrive_leads_action': [],
                                      'hubspot_forms_action': [],
                                      'http_action': ['my_http_action'], 'google_search_action': [], 'jira_action': [],
                                      'two_stage_fallback': [],
                                      'slot_set_action': [], 'email_action': [], 'form_validation_action': [],
                                      'kairon_bot_response': [],
                                      'razorpay_action': [], 'prompt_action': ['gpt_llm_faq'],
                                      'database_action': [], 'pyscript_action': [], 'web_search_action': [], 'live_agent_action': [],
                                      'callback_action': [], 'schedule_action': [],
                                      'utterances': ['utter_greet',
                                                     'utter_cheer_up',
                                                     'utter_did_that_help',
                                                     'utter_happy',
                                                     'utter_goodbye',
                                                     'utter_iamabot',
                                                     'utter_feedback',
                                                     'utter_good_feedback',
                                                     'utter_bad_feedback',
                                                     'utter_default',
                                                     'utter_please_rephrase', 'utter_custom', 'utter_query',
                                                     'utter_more_queries']}, ignore_order=True)

    def test_add_complex_story_with_stop_flow_action(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_goodbye", "type": "BOT"},
            {"name": "utter_goodbye", "type": "BOT"},
            {"name": "stop", "type": "STOP_FLOW_ACTION"}
        ]
        story_dict = {'name': "story with stop flow action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        pytest.story_id_three = processor.add_complex_story(story_dict, "tests", "testUser")
        story = Stories.objects(block_name="story with stop flow action", bot="tests").get()
        assert len(story.events) == 4
        assert story is not None
        if story:
            stop_action_event = story.events[-1]
            assert stop_action_event.name == "action_listen"
            assert stop_action_event.type == "action"

    def test_add_multiflow_story_with_stop_flow_action(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": [
                 {"name": "stop_flow", "type": "STOP_FLOW_ACTION", "node_id": "7",
                  "component_id": "63gm5BzYuhC1bc6yzysEnN65"}]
             },
            {"step": {"name": "stop_flow", "type": "STOP_FLOW_ACTION", "node_id": "7",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN65"},
             "connections": None
             },
        ]
        story_dict = {'name': "multiflow story with stop flow action", 'steps': steps, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, "test", "TestUser")
        story = MultiflowStories.objects(block_name="multiflow story with stop flow action", bot="test").get()
        assert len(story.events) == 7
        stop_flow_step = story.events[6]['step']
        assert stop_flow_step['name'] == "stop_flow"
        assert stop_flow_step['type'] == "STOP_FLOW_ACTION"

    def test_add_duplicate_complex_story(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        with pytest.raises(Exception):
            story_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.add_complex_story(story_dict, "tests", "testUser")

    def test_add_duplicate_case_insensitive_complex_story(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        with pytest.raises(Exception):
            story_dict = {'name': "Story with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.add_complex_story(story_dict, "tests", "testUser")

    def test_add_none_complex_story_name(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            story_dict = {'name': None, 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.add_complex_story(story_dict, "tests", "testUser")

    def test_add_empty_complex_story_name(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"}
        ]
        with pytest.raises(AppException):
            story_dict = {'name': "", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.add_complex_story(story_dict, "tests", "testUser")

    def test_add_blank_complex_story_name(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"}
        ]
        with pytest.raises(AppException):
            story_dict = {'name': " ", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.add_complex_story(story_dict, "tests", "testUser")

    def test_add_empty_complex_story_event(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            story_dict = {'name': "empty path", 'steps': [], 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.add_complex_story(story_dict, "tests", "testUser")

    def test_add_duplicate_complex_story_using_events(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        with pytest.raises(Exception):
            story_dict = {'name': "story duplicate using events", 'steps': steps, 'type': 'STORY',
                          'template_type': 'CUSTOM'}
            processor.add_complex_story(story_dict, "tests", "testUser")

    def test_add_complex_story_with_invalid_event(self):
        processor = MongoProcessor()
        steps = [
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="First event should be an user"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="user event should be followed by action"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "mood_sad", "type": "INTENT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="Found 2 consecutive user events"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_multiflow_story(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]

        story_dict = {'name': "story", 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, "test", "TestUser")
        story = MultiflowStories.objects(block_name="story", bot="test").get()
        assert len(story.events) == 6

    def test_add_multiflow_story_with_slot(self):
        processor = MongoProcessor()
        story_name = "multiflow story with slot"
        bot = "test_slot"
        user = "test_user"
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "mood", "type": "SLOT", "value": "Happy", "node_id": "3",
                  "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "food", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "food", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_food", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_food", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "mood", "type": "SLOT", "value": "Happy", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        pytest.story_id = processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = MultiflowStories.objects(block_name=story_name, bot=bot).get()
        assert len(multiflow_story.events) == 6
        stories = list(processor.get_multiflow_stories("test_slot"))
        assert stories[0]['type'] == "MULTIFLOW"
        assert len(stories[0]['steps']) == 6
        updated_steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "mood", "type": "SLOT", "value": "Happy", "node_id": "3",
                  "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "food", "type": "SLOT", "value": "Indian", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "food", "type": "SLOT", "value": "Indian", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_food", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_food", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "mood", "type": "SLOT", "value": "Happy", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        updated_story_dict = {'name': story_name, 'steps': updated_steps, 'type': 'MULTIFLOW',
                              'template_type': 'CUSTOM'}
        processor.update_multiflow_story(pytest.story_id, updated_story_dict, bot)
        updated_multiflow_story = MultiflowStories.objects(block_name=story_name, bot=bot).get()
        assert len(updated_multiflow_story.events) == 6
        stories = list(processor.get_multiflow_stories("test_slot"))
        assert stories[0]['type'] == "MULTIFLOW"
        assert len(stories[0]['steps']) == 6
        load_story = processor.load_linear_flows_from_multiflow_stories(bot)
        assert load_story[0].story_steps[0].events[2].key == 'food'
        assert load_story[0].story_steps[0].events[2].value == 'Indian'
        assert load_story[0].story_steps[1].events[2].key == 'mood'
        assert load_story[0].story_steps[1].events[2].value == 'Happy'

    def test_add_multiflow_story_with_slot_value_int(self):
        processor = MongoProcessor()
        story_name = "multiflow story with slot int"
        bot = "test_slot_int"
        user = "test_user"
        steps = [
            {"step": {"name": "greeting", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_greeting", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greeting", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "age", "type": "SLOT", "value": 23, "node_id": "3",
                  "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foody", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foody", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_foody", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_foody", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_age", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "age", "type": "SLOT", "value": 23, "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_age", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = MultiflowStories.objects(block_name=story_name, bot=bot).get()
        assert len(multiflow_story.events) == 6
        stories = list(processor.get_multiflow_stories("test_slot_int"))
        assert stories[0]['type'] == "MULTIFLOW"
        assert len(stories[0]['steps']) == 6

    def test_add_multiflow_story_with_slot_value_bool(self):
        processor = MongoProcessor()
        story_name = "multiflow story with slot bool"
        bot = "test_slot_bool"
        user = "test_user"
        steps = [
            {"step": {"name": "greeting", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_greeting", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greeting", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "mood", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foody", "type": "SLOT", "value": True, "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foody", "type": "SLOT", "value": True, "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_foody", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_foody", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "mood", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = MultiflowStories.objects(block_name=story_name, bot=bot).get()
        assert len(multiflow_story.events) == 6
        stories = list(processor.get_multiflow_stories("test_slot_bool"))
        assert stories[0]['type'] == "MULTIFLOW"
        assert len(stories[0]['steps']) == 6

    def test_add_multiflow_story_with_slot_value_None(self):
        processor = MongoProcessor()
        story_name = "Multiflow None"
        bot = "test_slot_none"
        user = "test_user"
        steps = [
            {"step": {"name": "greeting", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_greeting", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greeting", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "mood", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "hobbies", "type": "SLOT", "value": None, "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "hobbies", "type": "SLOT", "value": None, "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_hobbies", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_hobbies", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "mood", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = MultiflowStories.objects(bot=bot).get()
        assert len(multiflow_story.events) == 6
        stories = list(processor.get_multiflow_stories("test_slot_none"))
        assert stories[0]['type'] == "MULTIFLOW"
        assert len(stories[0]['steps']) == 6

    def test_add_multiflow_story_with_slot_value_invalid(self):
        processor = MongoProcessor()
        story_name = "multiflow story with slot invalid"
        bot = "test_slot_invalid"
        user = "test_user"
        steps = [
            {"step": {"name": "greeting", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_greeting", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greeting", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "mood", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "games", "type": "SLOT", "value": {"1": "cricket"}, "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "games", "type": "SLOT", "value": {"1": "cricket"}, "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_games", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_games", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "mood", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError,
                           match="slot values in multiflow story must be either None or of type int, str or boolean"):
            processor.add_multiflow_story(story_dict, bot, user)

    def test_add_multiflow_story_with_slot_value_invalid_type(self):
        story_name = "multiflow story with slot invalid"
        bot = "test_slot_invalid"
        user = "test_user"
        steps = [
            {"step": {"name": "greeting", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_greeting", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greeting", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "mood", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "games", "type": "SLOT", "value": {"1": "cricket"}, "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "games", "type": "SLOT", "value": {"1": "cricket"}, "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_games", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_games", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "mood", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        events = [MultiflowStoryEvents(**step) for step in steps]
        with pytest.raises(ValidationError, match="slot values must be either None or of type int, str or boolean"):
            MultiflowStories(block_name="multiflow story with slot invalid", bot=bot, user=user, events=events).save()

    def test_add_multiflow_story_with_invalid_events(self):
        processor = MongoProcessor()
        story_name = "multiflow story with invalid events"
        bot = "test_slot_invalid"
        user = "test_user"
        steps = [
            {"step": {"name": "hello", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_hello", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_hello", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "mood", "type": "INTENT", "value": "Good", "node_id": "3",
                  "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "games", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "games", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_games", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_games", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "mood", "type": "INTENT", "value": "Good", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="Value is allowed only for slot events in multiflow story"):
            processor.add_multiflow_story(story_dict, bot, user)

    def test_add_multiflow_story_with_value_for_invalid_event(self):
        processor = MongoProcessor()
        story_name = "multiflow story with value for invalid events"
        bot = "test_slot_invalid"
        user = "test_user"
        steps = [
            {"step": {"name": "hello", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_hello", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_hello", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "mood", "type": "INTENT", "value": "Good", "node_id": "3",
                  "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "games", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "games", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_games", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_games", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "mood", "type": "INTENT", "value": "Good", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        events = [MultiflowStoryEvents(**step) for step in steps]
        with pytest.raises(ValidationError, match="Value is allowed only for slot events"):
            MultiflowStories(block_name="multiflow story with value for invalid events", bot=bot, user=user,
                             events=events).save()

    def test_add_multiflow_story_with_path_type_as_STORY(self):
        processor = MongoProcessor()
        story_name = "multiflow_story_STORY"
        bot = "test_path_story"
        user = "test_user_path_story"
        steps = [
            {"step": {"name": "ask", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_ask", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_ask", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "mood", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "food", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "food", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_food", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_food", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "mood", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6', "flow_type": 'STORY'}, {"node_id": "5", "flow_type": 'STORY'}]
        story_dict = {'name': story_name, 'steps': steps, "metadata": metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = MultiflowStories.objects(bot=bot).get()
        assert len(multiflow_story.events) == 6
        assert len(multiflow_story.metadata) == 2

    def test_add_multiflow_story_with_path_type_as_RULE(self):
        processor = MongoProcessor()
        story_name = "multiflow story with path as RULE"
        bot = "test_path_rule"
        user = "test_user"
        steps = [
            {"step": {"name": "asking", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_asking", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_asking", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "moody", "type": "HTTP_ACTION", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foody_act", "type": "HTTP_ACTION", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foody_act", "type": "HTTP_ACTION", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_foody", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_foody", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_moody", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "moody", "type": "HTTP_ACTION", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_moody", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6', "flow_type": 'RULE'}, {"node_id": "5", "flow_type": 'RULE'}]
        story_dict = {'name': story_name, 'steps': steps, "metadata": metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = MultiflowStories.objects(bot=bot).get()
        assert len(multiflow_story.events) == 6
        assert len(multiflow_story.metadata) == 2

    def test_add_multiflow_story_with_multiple_user_events_RULE(self):
        processor = MongoProcessor()
        story_name = "test_add_multiflow_story_with_multiple_user_events_RULE"
        bot = "test_path_rule"
        user = "test_user"
        steps = [
            {"step": {"name": "wish", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "moody", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foody_act", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foody_act", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_foody", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_foody", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_moody", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "moody", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_moody", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6', "flow_type": 'RULE'}, {"node_id": "5", "flow_type": 'STORY'}]
        story_dict = {'name': story_name, 'steps': steps, "metadata": metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        with pytest.raises(AppException, match="Path tagged as RULE can have only one intent!"):
            processor.add_multiflow_story(story_dict, bot, user)

    def test_add_multiflow_story_with_no_path_type(self):
        processor = MongoProcessor()
        story_name = "multiflow story with no path type"
        bot = "test_no_path_type"
        user = "test_user"
        steps = [
            {"step": {"name": "welcome", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_welcome", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_welcome", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "coffee", "type": "HTTP_ACTION", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "tea", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "tea", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_tea", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_tea", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_coffee", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "coffee", "type": "HTTP_ACTION", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_coffee", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6'}, {"node_id": "5"}]
        story_dict = {'name': story_name, 'steps': steps, "metadata": metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = MultiflowStories.objects(bot=bot).get()
        assert len(multiflow_story.events) == 6
        assert multiflow_story.metadata[0]['flow_type'] == 'STORY'
        assert multiflow_story.metadata[0]['flow_type'] == 'STORY'

    def test_add_multiflow_story_with_leaf_node_slot(self):
        processor = MongoProcessor()
        story_name = "multiflow_story_with_leaf_node_slot"
        bot = "test_story_with_leaf_node_slot"
        user = "test_user"
        steps = [
            {"step": {"name": "weathery", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_weathery", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_weathery", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "sunny", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "rainy", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "sunny", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_sunny", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_sunny", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "umbrella", "type": "SLOT", "value": 'Yes', "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "rainy", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "umbrella", "type": "SLOT", "value": 'Yes', "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6', "flow_type": "RULE"}, {"node_id": "5", "flow_type": "STORY"}]
        story_dict = {'name': story_name, 'steps': steps, "metadata": metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        with pytest.raises(AppException, match="Slots cannot be leaf nodes!"):
            processor.add_multiflow_story(story_dict, bot, user)

    def test_load_multiflow_stories(self):
        processor = MongoProcessor()
        story_name_one = "greeting story"
        story_name_two = "farmer story"
        story_name_three = "shopping story"
        bot = "load_linear_flows_from_multiflow_stories"
        user = "test_user"
        steps_one = [
            {"step": {"name": "welcome", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_welcome", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_welcome", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "coffee", "type": "HTTP_ACTION", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "tea", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "tea", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_tea", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_tea", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_coffee", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "coffee", "type": "HTTP_ACTION", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_coffee", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        steps_two = [
            {"step": {"name": "farmer", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_farmer", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_farmer", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "rice", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "wheat", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "wheat", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_wheat", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_wheat", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_rice", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "rice", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_rice", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        steps_three = [
            {"step": {"name": "shopping", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_shopping", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_shopping", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "clothes", "type": "HTTP_ACTION", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "handbags", "type": "HTTP_ACTION", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "handbags", "type": "HTTP_ACTION", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_handbags", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_handbags", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_clothes", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "clothes", "type": "HTTP_ACTION", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_clothes", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata_one = [{"node_id": '6', "flow_type": 'RULE'}, {"node_id": "5", "flow_type": 'STORY'}]
        metadata_two = [{"node_id": '6', "flow_type": 'STORY'}, {"node_id": "5", "flow_type": 'STORY'}]
        metadata_three = [{"node_id": '6', "flow_type": 'RULE'}, {"node_id": "5", "flow_type": 'RULE'}]

        story_dict_one = {'name': story_name_one, 'steps': steps_one, "metadata": metadata_one, 'type': 'MULTIFLOW',
                          'template_type': 'CUSTOM'}
        story_dict_two = {'name': story_name_two, 'steps': steps_two, "metadata": metadata_two,
                          'type': 'MULTIFLOW',
                          'template_type': 'CUSTOM'}
        story_dict_three = {'name': story_name_three, 'steps': steps_three, "metadata": metadata_three,
                            'type': 'MULTIFLOW',
                            'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict_one, bot, user)
        processor.add_multiflow_story(story_dict_two, bot, user)
        processor.add_multiflow_story(story_dict_three, bot, user)
        multiflow_story = processor.load_linear_flows_from_multiflow_stories(bot)
        assert multiflow_story[0].story_steps[0].block_name == 'greeting story_1'
        assert multiflow_story[1].story_steps[0].block_name == 'greeting story_2'
        assert multiflow_story[0].story_steps[1].block_name == 'farmer story_1'
        assert multiflow_story[0].story_steps[2].block_name == 'farmer story_2'
        assert multiflow_story[1].story_steps[1].block_name == 'shopping story_1'
        assert multiflow_story[1].story_steps[2].block_name == 'shopping story_2'
        assert multiflow_story[1].story_steps[0].events[0].action_name == '...'
        assert multiflow_story[1].story_steps[1].events[0].action_name == '...'
        assert multiflow_story[1].story_steps[2].events[0].action_name == '...'

    def test_add_multiflow_story_with_path_type_for_invalid_node(self):
        processor = MongoProcessor()
        story_name = "multiflow story with path for invalid node"
        bot = "test_invalid_node_path"
        user = "test_user"
        steps = [
            {"step": {"name": "weather", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_weather", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_weather", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "sunny", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "rainy", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "sunny", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_sunny", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_sunny", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_rainy", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "rainy", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_rainy", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '2', "flow_type": "RULE"}, {"node_id": "5", "flow_type": "STORY"}]
        story_dict = {'name': story_name, 'steps': steps, "metadata": metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="Only leaf nodes can be tagged with a flow"):
            processor.add_multiflow_story(story_dict, bot, user)

    def test_add_multiflow_story_same_action_intent_name(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1",
                      "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [{"name": "utter_greet", "type": "BOT", "node_id": "2",
                              "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "3",
                              "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                             {"name": "goodbye", "type": "INTENT", "node_id": "4",
                              "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [{"name": "goodbye", "type": "EMAIL_ACTION", "node_id": "5",
                              "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "goodbye", "type": "EMAIL_ACTION", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "633xnjCuP4iNZfEq5D7jyI9A",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             }
        ]

        story_dict = {'name': "story with same action name as intent", 'steps': steps, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, "test", "TestUser")
        story = MultiflowStories.objects(block_name="story with same action name as intent", bot="test").get()
        assert len(story.events) == 6

    def test_add_multiflow_story_with_same_events(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]

        story_dict = {'name': "story with same flow events", 'steps': steps, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        with pytest.raises(AppException, match="Story flow already exists!"):
            processor.add_multiflow_story(story_dict, "test", "TestUser")

    def test_add_multiflow_story_with_multiple_actions(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "63sKhFlHTZCgTyY6aCi34T6P"},
             "connections": [
                 {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63ybbEJli191Ey3ek2XML6Po"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63ybbEJli191Ey3ek2XML6Po"},
             "connections": [
                 {"name": "utter_qoute", "type": "BOT", "node_id": "3", "component_id": "63LamdXLIvKT4A1Lo8Nrlgso"},
                 {"name": "utter_thought", "type": "BOT", "node_id": "4", "component_id": "63jwAHaBHS7qMWZiGTOgX2V1"}]
             },
            {"step": {"name": "utter_thought", "type": "BOT", "node_id": "4",
                      "component_id": "63jwAHaBHS7qMWZiGTOgX2V1"},
             "connections": [
                 {"name": "more_queries", "type": "INTENT", "node_id": "5", "component_id": "63kn8FkXZajTdGwrSbOgVnpg"}]
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "5",
                      "component_id": "63kn8FkXZajTdGwrSbOgVnpg"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                              "component_id": "63ovTDWUJ7gP5IlhhRNmc327"}]
             },
            {"step": {"name": "utter_qoute", "type": "BOT", "node_id": "3", "component_id": "63LamdXLIvKT4A1Lo8Nrlgso"},
             "connections": [
                 {"name": "goodbye", "type": "INTENT", "node_id": "7", "component_id": "63DVHaMnngGY70EUgG9ATwVF"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "7", "component_id": "63DVHaMnngGY70EUgG9ATwVF"},
             "connections": [
                 {"name": "utter_goodbye", "type": "BOT", "node_id": "8", "component_id": "632hGiC1QFwtD48CH5VWXOjH"}]
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                      "component_id": "63ovTDWUJ7gP5IlhhRNmc327"},
             "connections": None
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "8",
                      "component_id": "632hGiC1QFwtD48CH5VWXOjH"},
             "connections": None
             }
        ]

        story_dict = {'name': "story with multiple actions", 'steps': steps, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, "test", "TestUser")
        story = MultiflowStories.objects(block_name="story with multiple actions", bot="test").get()
        assert len(story.events) == 8

    def test_add_multiflow_story_with_cycle(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "ppooakak"},
             "connections": [{"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ppooakak"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ppooakak"},
             "connections": [{"name": "utter_qoute", "type": "BOT", "node_id": "3", "component_id": "ppooakak"},
                             {"name": "utter_thought", "type": "BOT", "node_id": "4", "component_id": "ppooakak"}]
             },
            {"step": {"name": "utter_thought", "type": "BOT", "node_id": "4", "component_id": "ppooakak"},
             "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "5", "component_id": "ppooakak"}]
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "5", "component_id": "ppooakak"},
             "connections": [{"name": "goodbye", "type": "INTENT", "node_id": "6", "component_id": "ppooakak"}]
             },
            {"step": {"name": "utter_qoute", "type": "BOT", "node_id": "3", "component_id": "ppooakak"},
             "connections": [{"name": "goodbye", "type": "INTENT", "node_id": "6", "component_id": "ppooakak"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "6", "component_id": "ppooakak"},
             "connections": [{"name": "utter_qoute", "type": "BOT", "node_id": "3", "component_id": "ppooakak"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "6", "component_id": "ppooakak"},
             "connections": None
             }
        ]

        with pytest.raises(AppException, match="Story cannot contain cycle!"):
            story_dict = {'name': "story with cycle", 'steps': steps, 'type': 'MULTIFLOW',
                          'template_type': 'CUSTOM'}
            processor.add_multiflow_story(story_dict, "test", "TestUser")

    def test_add_multiflow_story_no_multiple_action_for_intent(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "heyyy", "type": "INTENT", "node_id": "1", "component_id": "ppooakak"},
             "connections": [{"name": "utter_heyyy", "type": "BOT", "node_id": "2", "component_id": "ppooakak"},
                             {"name": "utter_greet", "type": "BOT", "node_id": "3", "component_id": "ppooakak"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "3", "component_id": "ppooakak"},
             "connections": [{"name": "more_queriesss", "type": "INTENT", "node_id": "4", "component_id": "ppooakak"},
                             {"name": "goodbyeee", "type": "INTENT", "node_id": "5", "component_id": "ppooakak"}]
             },
            {"step": {"name": "goodbyeee", "type": "INTENT", "node_id": "5", "component_id": "ppooakak"},
             "connections": [{"name": "utter_goodbyeee", "type": "BOT", "node_id": "6", "component_id": "ppooakak"}]
             },
            {"step": {"name": "utter_goodbyeee", "type": "BOT", "node_id": "6", "component_id": "ppooakak"},
             "connections": None
             },
            {"step": {"name": "utter_more_queriesss", "type": "BOT", "node_id": "7", "component_id": "ppooakak"},
             "connections": None
             },
            {"step": {"name": "more_queriesss", "type": "INTENT", "node_id": "4", "component_id": "ppooakak"},
             "connections": [
                 {"name": "utter_more_queriesss", "type": "BOT", "node_id": "7", "component_id": "ppooakak"}]
             },
            {"step": {"name": "utter_heyyy", "type": "BOT", "node_id": "2", "component_id": "ppooakak"},
             "connections": None
             }
        ]

        with pytest.raises(AppException, match="Intent can only have one connection of action type or slot type"):
            story_dict = {'name': "story with multiple action for an intent", 'steps': steps, 'type': 'MULTIFLOW',
                          'template_type': 'CUSTOM'}
            processor.add_multiflow_story(story_dict, "test", "TestUser")

    def test_add_multiflow_story_with_connected_nodes(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "63ue2YkCdcVmnU0L7Q8wCjnc"},
             "connections": [
                 {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63NSzOE45TM6VxMTkak6C5Oy"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63NSzOE45TM6VxMTkak6C5Oy"},
             "connections": [
                 {"name": "thought", "type": "INTENT", "node_id": "3", "component_id": "63qydua5wtsuI3Dr0Q4gAtlj"},
                 {"name": "mood", "type": "INTENT", "node_id": "4", "component_id": "63ejBpfbp5XXvmgbkfYdWt8t"}]
             },
            {"step": {"name": "mood", "type": "INTENT", "node_id": "4", "component_id": "63ejBpfbp5XXvmgbkfYdWt8t"},
             "connections": [
                 {"name": "utter_mood", "type": "BOT", "node_id": "5", "component_id": "63Mcq10uhqwcrP8Pq29eqQYa"}]
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "5", "component_id": "63Mcq10uhqwcrP8Pq29eqQYa"},
             "connections": [
                 {"name": "utter_thought", "type": "BOT", "node_id": "6", "component_id": "63CYvgxUsX0aeLYV4WdfIJF2"}]
             },
            {"step": {"name": "utter_thought", "type": "BOT", "node_id": "6",
                      "component_id": "63CYvgxUsX0aeLYV4WdfIJF2"},
             "connections": None
             },
            {"step": {"name": "thought", "type": "INTENT", "node_id": "3", "component_id": "63qydua5wtsuI3Dr0Q4gAtlj"},
             "connections": [
                 {"name": "utter_thought", "type": "BOT", "node_id": "6", "component_id": "63CYvgxUsX0aeLYV4WdfIJF2"}]
             }
        ]

        story_dict = {'name': "story with connected nodes", 'steps': steps, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        pytest.multiflow_story_id = processor.add_multiflow_story(story_dict, "test", "TestUser")
        story = MultiflowStories.objects(block_name="story with connected nodes", bot="test").get()
        assert len(story.events) == 6

    def test_add_none_multiflow_story_name(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "ksos09"},
             "connections": [{"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ksos09"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ksos09"},
             "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "ksos09"},
                             {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "ksos09"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "ksos09"},
             "connections": [{"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "ksos09"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "ksos09"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "ksos09"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "ksos09"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "ksos09"}]
             }
        ]
        with pytest.raises(AppException, match="Story name cannot be empty or blank spaces"):
            story_dict = {'name': None, 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
            processor.add_multiflow_story(story_dict, "tests", "testUser")

    def test_add_multiflow_story_same_source(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "ksos09"},
             "connections": [{"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ksos09"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ksos09"},
             "connections": None
             },
            {"step": {"name": "mood", "type": "INTENT", "node_id": "3", "component_id": "ksos09"},
             "connections": [{"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ksos09"}]
             },
        ]

        with pytest.raises(AppException, match="Story cannot have multiple sources!"):
            story_dict = {'name': 'story with multiple source node', 'steps': steps, 'type': 'MULTIFLOW',
                          'template_type': 'CUSTOM'}
            processor.add_multiflow_story(story_dict, "tests", "testUser")

    def test_add_multiflow_story_connected_steps(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "ksos09"},
             "connections": [{"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ksos09"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ksos09"},
             "connections": None
             },
            {"step": {"name": "mood", "type": "INTENT", "node_id": "3", "component_id": "ksos09"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "4", "component_id": "ksos09"}]
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "4", "component_id": "ksos09"},
             "connections": None
             },
        ]

        with pytest.raises(AppException, match="All steps must be connected!"):
            story_dict = {'name': 'story with no connected steps', 'steps': steps, 'type': 'MULTIFLOW',
                          'template_type': 'CUSTOM'}
            processor.add_multiflow_story(story_dict, "tests", "testUser")

    def test_add_empty_multiflow_story_name(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "ksos09"},
             "connections": [{"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ksos09"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ksos09"},
             "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "ksos09"},
                             {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "ksos09"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "ksos09"},
             "connections": [{"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "ksos09"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "ksos09"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "ksos09"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "ksos09"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "ksos09"}]
             }
        ]
        with pytest.raises(AppException, match="Story name cannot be empty or blank spaces"):
            story_dict = {'name': "", 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
            processor.add_multiflow_story(story_dict, "tests", "testUser")

    def test_add_blank_multiflow_story_name(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "ksos09"},
             "connections": [{"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ksos09"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ksos09"},
             "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "ksos09"},
                             {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "ksos09"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "ksos09"},
             "connections": [{"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "ksos09"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "ksos09"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "ksos09"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "ksos09"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "ksos09"}]
             }
        ]
        with pytest.raises(AppException, match="Story name cannot be empty or blank spaces"):
            story_dict = {'name': " ", 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
            processor.add_multiflow_story(story_dict, "tests", "testUser")

    def test_add_empty_multiflow_story_event(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match="steps are required"):
            story_dict = {'name': "empty path", 'steps': [], 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
            processor.add_multiflow_story(story_dict, "test", "TestUser")

    def test_update_multiflow_story(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "63TARMJ08PO7uSpktNcGIY9l"},
             "connections": [
                 {"name": "utter_time", "type": "BOT", "node_id": "2", "component_id": "63GU3Xjvf2wYX1XBKXzZkuzK"}]
             },
            {"step": {"name": "utter_time", "type": "BOT", "node_id": "2", "component_id": "63GU3Xjvf2wYX1XBKXzZkuzK"},
             "connections": [
                 {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "63YbD6G7rrqVrAFt3N1IaXRC"},
                 {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "63gso6SSgHYX7vLF6ghdq0Zy"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "63gso6SSgHYX7vLF6ghdq0Zy"},
             "connections": [
                 {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "63tmj2qy4zQX2tflE4Pbhby9"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5",
                      "component_id": "63tmj2qy4zQX2tflE4Pbhby9"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                      "component_id": "63Ff9XE3qlHN4UKH6jCsaTC2"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3",
                      "component_id": "63YbD6G7rrqVrAFt3N1IaXRC"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                              "component_id": "63Ff9XE3qlHN4UKH6jCsaTC2"}]
             }
        ]
        story_dict = {'name': "updated_story", 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        processor.update_multiflow_story(pytest.multiflow_story_id, story_dict, "test")
        story = MultiflowStories.objects(block_name="updated_story", bot="test").get()
        assert story.events[0]['connections'][0]['name'] == "utter_time"
        # print(story.events[1].name)
        # assert story.events[1].name == "utter_nonsense"

    def test_update_multiflow_story_with_same_events(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "63TARMJ08PO7uSpktNcGIY9l"},
             "connections": [
                 {"name": "utter_time", "type": "BOT", "node_id": "2", "component_id": "63GU3Xjvf2wYX1XBKXzZkuzK"}]
             },
            {"step": {"name": "utter_time", "type": "BOT", "node_id": "2", "component_id": "63GU3Xjvf2wYX1XBKXzZkuzK"},
             "connections": [
                 {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "63YbD6G7rrqVrAFt3N1IaXRC"},
                 {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "63gso6SSgHYX7vLF6ghdq0Zy"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "63gso6SSgHYX7vLF6ghdq0Zy"},
             "connections": [
                 {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "63tmj2qy4zQX2tflE4Pbhby9"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5",
                      "component_id": "63tmj2qy4zQX2tflE4Pbhby9"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                      "component_id": "63Ff9XE3qlHN4UKH6jCsaTC2"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3",
                      "component_id": "63YbD6G7rrqVrAFt3N1IaXRC"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                              "component_id": "63Ff9XE3qlHN4UKH6jCsaTC2"}]
             }
        ]

        story_dict = {'name': "story update with same flow events", 'steps': steps, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.update_multiflow_story(pytest.multiflow_story_id, story_dict, "test")

    def test_update_multiflow_story_with_same_events_with_different_story_id(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1",
                      "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [{"name": "utter_greet", "type": "BOT", "node_id": "2",
                              "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "3",
                              "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                             {"name": "goodbye", "type": "INTENT", "node_id": "4",
                              "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [{"name": "utter_goodbye", "type": "BOT", "node_id": "5",
                              "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        story_dict = {'name': "story with same flow events",
                      'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        with pytest.raises(AppException, match="Story flow already exists!"):
            processor.update_multiflow_story(pytest.multiflow_story_id, story_dict, "test")

    def test_update_non_existing_multiflow_story(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greeted", "type": "INTENT", "node_id": "1", "component_id": "NKUPKJ"},
             "connections": [{"name": "utter_timed", "type": "BOT", "node_id": "2", "component_id": "NKUPKJ"}]
             },
            {"step": {"name": "utter_timed", "type": "BOT", "node_id": "2", "component_id": "NKUPKJ"},
             "connections": [{"name": "some_more_queries", "type": "INTENT", "node_id": "3", "component_id": "NKUPKJ"},
                             {"name": "saying_goodbye", "type": "INTENT", "node_id": "4", "component_id": "NKUPKJ"}]
             },
            {"step": {"name": "saying_goodbye", "type": "INTENT", "node_id": "4", "component_id": "NKUPKJ"},
             "connections": [{"name": "utter_saying_goodbye", "type": "BOT", "node_id": "5", "component_id": "NKUPKJ"}]
             },
            {"step": {"name": "utter_saying_goodbye", "type": "BOT", "node_id": "5", "component_id": "NKUPKJ"},
             "connections": None
             },
            {"step": {"name": "utter_some_more_queries", "type": "BOT", "node_id": "6", "component_id": "NKUPKJ"},
             "connections": None
             },
            {"step": {"name": "some_more_queries", "type": "INTENT", "node_id": "3", "component_id": "NKUPKJ"},
             "connections": [
                 {"name": "utter_some_more_queries", "type": "BOT", "node_id": "6", "component_id": "NKUPKJ"}]
             }
        ]
        with pytest.raises(AppException, match="Flow does not exists"):
            story_dict = {'name': "non existing story conditional", 'steps': steps, 'type': 'MULTIFLOW',
                          'template_type': 'CUSTOM'}
            processor.update_multiflow_story("5e564fbcdcf0d5fad89e3acd", story_dict, "test")

    def test_update_multiflow_story_with_invalid_event(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "BOT", "node_id": "1", "component_id": "NKUPKJ"},
             "connections": [{"name": "utter_time", "type": "BOT", "node_id": "2", "component_id": "NKUPKJ"}]
             },
            {"step": {"name": "utter_time", "type": "BOT", "node_id": "2", "component_id": "NKUPKJ"},
             "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "NKUPKJ"},
                             {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "NKUPKJ"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "NKUPKJ"},
             "connections": [{"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "NKUPKJ"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "NKUPKJ"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "NKUPKJ"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "NKUPKJ"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "NKUPKJ"}]
             }
        ]
        story_dict = {'name': "story", 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        with pytest.raises(AppException, match="First step should be an intent"):
            processor.update_multiflow_story(pytest.multiflow_story_id, story_dict, "test")

        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "NKUPKJ"},
             "connections": [{"name": "utter_time", "type": "INTENT", "node_id": "2", "component_id": "NKUPKJ"}]
             },
            {"step": {"name": "utter_time", "type": "INTENT", "node_id": "2", "component_id": "NKUPKJ"},
             "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "NKUPKJ"},
                             {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "NKUPKJ"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "NKUPKJ"},
             "connections": [{"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "NKUPKJ"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "NKUPKJ"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "NKUPKJ"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "NKUPKJ"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "4", "component_id": "NKUPKJ"}]
             }
        ]
        rule_dict = {'name': "story", 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        with pytest.raises(AppException, match="Intent should be followed by an Action or Slot type event"):
            processor.update_multiflow_story(pytest.multiflow_story_id, rule_dict, "test")

    def test_update_multiflow_story_name(self):
        processor = MongoProcessor()
        events = [
            {"step": {"name": "greet", "type": "BOT", "node_id": "1", "component_id": "NKUPKJ"},
             "connections": [{"name": "utter_greeting", "type": "BOT", "node_id": "2", "component_id": "NKUPKJ"}]
             },
            {"step": {"name": "utter_time", "type": "BOT", "node_id": "2", "component_id": "NKUPKJ"},
             "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "NKUPKJ"},
                             {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "NKUPKJ"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "NKUPKJ"},
             "connections": [{"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "NKUPKJ"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "NKUPKJ"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "NKUPKJ"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "NKUPKJ"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "NKUPKJ"}]
             }
        ]
        with pytest.raises(AppException, match='Story name cannot be empty or blank spaces'):
            story_dict = {'name': None, 'steps': events, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
            processor.update_multiflow_story(pytest.multiflow_story_id, story_dict, "tests")

    def test_update_empty_multiflow_story_name(self):
        processor = MongoProcessor()
        events = [
            {"step": {"name": "greet", "type": "BOT", "node_id": "1", "component_id": "MkkfnA"},
             "connections": [{"name": "utter_time", "type": "BOT", "node_id": "2", "component_id": "MkkfnA"}]
             },
            {"step": {"name": "utter_time", "type": "BOT", "node_id": "2", "component_id": "MkkfnA"},
             "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "MkkfnA"},
                             {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "MkkfnA"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "MkkfnA"},
             "connections": [{"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "MkkfnA"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "MkkfnA"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "MkkfnA"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "MkkfnA"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "MkkfnA"}]
             }
        ]
        with pytest.raises(AppException, match='Story name cannot be empty or blank spaces'):
            story_dict = {'name': "", 'steps': events, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
            processor.update_multiflow_story(pytest.multiflow_story_id, story_dict, "tests")

    def test_update_blank_multiflow_story_name(self):
        processor = MongoProcessor()
        events = [
            {"step": {"name": "greet", "type": "BOT", "node_id": "1", "component_id": "MkkfnA"},
             "connections": [{"name": "utter_time", "type": "BOT", "node_id": "2", "component_id": "MkkfnA"}]
             },
            {"step": {"name": "utter_time", "type": "BOT", "node_id": "2", "component_id": "MkkfnA"},
             "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "MkkfnA"},
                             {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "MkkfnA"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "MkkfnA"},
             "connections": [{"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "MkkfnA"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "MkkfnA"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "MkkfnA"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "MkkfnA"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "MkkfnA"}]
             }
        ]
        with pytest.raises(AppException, match='Story name cannot be empty or blank spaces'):
            story_dict = {'name': " ", 'steps': events, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
            processor.update_multiflow_story(pytest.multiflow_story_id, story_dict, "tests")

    def test_update_empty_multiflow_story_event(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match='steps are required'):
            story_dict = {'name': "empty path", 'steps': [], 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
            processor.update_multiflow_story(pytest.multiflow_story_id, story_dict, "tests")

    def test_delete_multiflow_story(self):
        processor = MongoProcessor()
        processor.delete_complex_story(pytest.multiflow_story_id, "MULTIFLOW", "test", "TestUser")

    def test_case_delete_multiflow_story(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "63K8PA5su49O7HQBDmSrgJXz"},
             "connections": [
                 {"name": "utter_hi", "type": "BOT", "node_id": "2", "component_id": "63OgU8uyVaj0649DWx5VOSAk"}]
             },
            {"step": {"name": "utter_hi", "type": "BOT", "node_id": "2", "component_id": "63OgU8uyVaj0649DWx5VOSAk"},
             "connections": [
                 {"name": "status", "type": "INTENT", "node_id": "3", "component_id": "63KWJCwd8MUGVpNQWlKWhiTa"},
                 {"name": "id", "type": "INTENT", "node_id": "4", "component_id": "63aLcDfR8mIfWaiVSUwNQLa6"}]
             },
            {"step": {"name": "id", "type": "INTENT", "node_id": "4", "component_id": "63aLcDfR8mIfWaiVSUwNQLa6"},
             "connections": [
                 {"name": "utter_id", "type": "BOT", "node_id": "5", "component_id": "636lABcKF5Y6hoRvYOC4xPbv"}]
             },
            {"step": {"name": "utter_id", "type": "BOT", "node_id": "5", "component_id": "636lABcKF5Y6hoRvYOC4xPbv"},
             "connections": None
             },
            {"step": {"name": "utter_status", "type": "BOT", "node_id": "6",
                      "component_id": "63sQZwlPiuydd8eVgIQwAmXw"},
             "connections": None
             },
            {"step": {"name": "status", "type": "INTENT", "node_id": "3", "component_id": "63KWJCwd8MUGVpNQWlKWhiTa"},
             "connections": [
                 {"name": "utter_status", "type": "BOT", "node_id": "6", "component_id": "63sQZwlPiuydd8eVgIQwAmXw"}]
             }
        ]
        story_dict = {"name": "a story", 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        story_id = processor.add_multiflow_story(story_dict, "test", "TestUser")
        processor.delete_complex_story(story_id, "MULTIFLOW", "test", "TestUser")

    def test_update_complex_story(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        story_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.update_complex_story(pytest.story_id_two, story_dict, "tests", "testUser")
        story = Stories.objects(block_name="story with action", bot="tests").get()
        assert story.events[1].name == "utter_nonsense"

    def test_update_complex_story_same_events(self):
        def test_update_complex_story(self):
            processor = MongoProcessor()
            steps = [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_nonsense", "type": "BOT"},
                {"name": "utter_cheer_up", "type": "BOT"},
                {"name": "mood_great", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
                {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
            ]
            story_dict = {'name': "story with same events", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
            with pytest.raises(AppException, match="FLow already exists!"):
                processor.update_complex_story(pytest.story_id_two, story_dict, "tests", "testUser")

    def test_add_complex_story_with_same_events(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        story_dict = {'name': "story with same events", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(AppException, match="Flow already exists!"):
            processor.add_complex_story(story_dict, "tests", "testUser")

    def test_update_complex_story_with_same_events_with_same_story_id(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        story_dict = {'name': "story with same events", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.update_complex_story(pytest.story_id_two, story_dict, "tests", "testUser")

    def test_case_insensitive_update_complex_story(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"},
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        story_dict = {'name': "STory with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.update_complex_story(pytest.story_id_two, story_dict, "tests", "testUser")
        story = Stories.objects(block_name="story with action", bot="tests").get()
        assert story.events[1].name == "utter_nonsense"

    def test_update_non_existing_complex_story(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"},
        ]
        with pytest.raises(AppException, match="Flow does not exists"):
            story_dict = {'name': "non existing story", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.update_complex_story('5e564fbcdcf0d5fad89e3acd', story_dict, "tests", "testUser")

    def test_update_complex_story_with_invalid_event(self):
        processor = MongoProcessor()
        steps = [
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="First event should be an user"):
            processor.update_complex_story(pytest.story_id_two, rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
        ]
        rule_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="user event should be followed by action"):
            processor.update_complex_story(pytest.story_id_two, rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "mood_sad", "type": "INTENT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="Found 2 consecutive user events"):
            processor.update_complex_story(pytest.story_id_two, rule_dict, "tests", "testUser")

    def test_update_complex_story_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"}
        ]
        with pytest.raises(AppException):
            story_dict = {'name': None, 'steps': events, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.update_complex_story(pytest.story_id, story_dict, "tests", "testUser")

    def test_update_empty_complex_story_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"}
        ]
        with pytest.raises(AppException):
            story_dict = {'name': "", 'steps': events, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.update_complex_story(pytest.story_id, story_dict, "tests", "testUser")

    def test_update_blank_complex_story_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"}
        ]
        with pytest.raises(AppException):
            story_dict = {'name': " ", 'steps': events, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.update_complex_story(pytest.story_id, story_dict, "tests", "testUser")

    def test_update_empty_complex_story_event(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            story_dict = {'name': "empty path", 'steps': [], 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.update_complex_story(pytest.story_id, story_dict, "tests", "testUser")

    def test_list_actions(self):
        processor = MongoProcessor()
        processor.add_action("reset_slot", "test_upload_and_save", "test_user")
        actions = processor.list_actions("test_upload_and_save")
        assert not DeepDiff(actions, {
            'actions': ['reset_slot'], 'google_search_action': [], 'jira_action': [], 'pipedrive_leads_action': [],
            'http_action': ['action_performanceUser1000@digite.com'], 'zendesk_action': [], 'slot_set_action': [],
            'hubspot_forms_action': [], 'two_stage_fallback': [], 'kairon_bot_response': [], 'razorpay_action': [],
            'email_action': [], 'form_validation_action': [], 'prompt_action': [], 'database_action': [],
            'pyscript_action': [], 'web_search_action': [], 'live_agent_action': [], 'callback_action': [], 'schedule_action': [],
            'utterances': ['utter_offer_help', 'utter_query', 'utter_goodbye', 'utter_feedback', 'utter_default',
                           'utter_please_rephrase'], 'web_search_action': []}, ignore_order=True)

    def test_delete_non_existing_complex_story(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match="Flow does not exists"):
            processor.delete_complex_story("5e564fbcdcf0d5fad89e3acd", "STORY", "tests", "testUser")

    def test_delete_empty_complex_story(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.delete_complex_story('5e564fbcdcf0d5fad89e3acd', "STORY", "tests", "testUser")

    def test_case_insensitive_delete_complex_story(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"},
        ]
        story_dict = {"name": "story2", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        story_id = processor.add_complex_story(story_dict, "tests", "testUser")
        processor.delete_complex_story(story_id, "STORY", "tests", "testUser")

    def test_delete_complex_story(self):
        processor = MongoProcessor()
        processor.delete_complex_story(pytest.story_id_two, "STORY", "tests", "testUser")

    def test_get_utterance_from_intent_non_existing(self):
        processor = MongoProcessor()
        user = "test_user"
        story = "new_story"
        action = story
        bot = "bot"
        intent = "greet_you"
        story_event = [StoryEvents(name=intent, type="user"),
                       StoryEvents(name="bot", type="slot", value=bot),
                       StoryEvents(name="http_action_config", type="slot", value=action),
                       StoryEvents(name="kairon_http_action", type="action")]
        cust = ResponseCustom(custom={"key": "value"})
        text = ResponseText(text="hello")

        Responses(
            name=intent,
            text=text,
            custom=cust,
            bot=bot,
            user=user
        ).save(validate=False).to_mongo()
        Stories(
            block_name=story,
            bot=bot,
            user=user,
            events=story_event
        ).save(validate=False).to_mongo()
        HttpActionConfig(
            action_name=action,
            response=HttpActionResponse(value="", dispatch=False),
            http_url="http://www.google.com",
            request_method="GET",
            bot=bot,
            user=user
        ).save().to_mongo()
        actual_action = processor.get_utterance_from_intent(intent="intent", bot=bot)
        assert actual_action[0] is None
        assert actual_action[1] is None

    def test_add_and_delete_non_integration_intent_by_integration_user(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        with pytest.raises(Exception):
            processor.delete_intent("TestingDelGreeting", "tests", "testUser1", is_integration=True,
                                    )

    def test_add_and_delete_integration_intent_by_same_integration_user(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting1", "tests", "testUser", is_integration=True)
        processor.delete_intent("TestingDelGreeting1", "tests", "testUser", is_integration=True,
                                )

    def test_add_and_delete_integration_intent_by_different_integration_user(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting2", "tests", "testUser", is_integration=True)
        processor.delete_intent("TestingDelGreeting2", "tests", "testUser2", is_integration=True,
                                )

    def test_add_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        rule_dict = {'name': "rule with action", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
        pytest.story_id = processor.add_complex_story(rule_dict, "tests", "testUser")
        story = Rules.objects(block_name="rule with action", bot="tests").get()
        assert len(story.events) == 4
        assert story.events[0].name == "..."
        assert story.events[0].type == "action"
        actions = processor.list_actions("tests")
        assert not DeepDiff(actions, {
            'actions': [], 'zendesk_action': [], 'hubspot_forms_action': [], 'two_stage_fallback': [],
            'http_action': ['my_http_action'], 'google_search_action': [], 'pipedrive_leads_action': [], 'kairon_bot_response': [],
            'razorpay_action': [], 'prompt_action': ['gpt_llm_faq'],
            'slot_set_action': [], 'email_action': [], 'form_validation_action': [], 'jira_action': [],
            'database_action': [], 'pyscript_action': [], 'web_search_action': [], 'live_agent_action': [],
            'callback_action': [], 'schedule_action': [],
            'utterances': ['utter_greet',
                           'utter_cheer_up',
                           'utter_did_that_help',
                           'utter_happy',
                           'utter_goodbye',
                           'utter_iamabot',
                           'utter_feedback',
                           'utter_good_feedback',
                           'utter_bad_feedback',
                           'utter_default',
                           'utter_please_rephrase', 'utter_custom', 'utter_query', 'utter_more_queries']},
                            ignore_order=True)

    def test_add_duplicate_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        with pytest.raises(Exception):
            rule_dict = {'name': "rule with action", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_rule_invalid_type(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        with pytest.raises(Exception):
            rule_dict = {'name': "rule with action", 'steps': steps, 'type': 'TEST', 'template_type': 'CUSTOM'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_duplicate_case_insensitive_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        with pytest.raises(Exception):
            rule_dict = {'name': "RUle with action", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_none_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': None, 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_empty_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': "", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_blank_rule_name(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': " ", 'steps': steps, 'type': 'rule', 'template_type': 'RULE'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_empty_rule_event(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            rule_dict = {'name': "empty path", 'steps': [], 'type': 'RULE', 'template_type': 'RULE'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_rule_with_multiple_intents(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "rule with multiple intents", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
        with pytest.raises(ValidationError,
                           match="Found rules 'rule with multiple intents' that contain more than user event.\nPlease use stories for this case"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_rule_with_invalid_event(self):
        processor = MongoProcessor()
        steps = [
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
        with pytest.raises(ValidationError, match="First event should be an user or conversation_start action"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
        with pytest.raises(ValidationError, match="user event should be followed by action"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "mood_sad", "type": "INTENT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
        with pytest.raises(ValidationError, match="Found 2 consecutive user events"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_update_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        rule_dict = {'name': "rule with action", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
        processor.update_complex_story(pytest.story_id, rule_dict, "tests", "testUser")
        rule = Rules.objects(block_name="rule with action", bot="tests").get()
        assert rule.events[2].name == "utter_nonsense"
        assert rule.events[0].name == "..."
        assert rule.events[0].type == "action"

    def test_case_insensitive_update_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        rule_dict = {'name': "RUle with action", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
        processor.update_complex_story(pytest.story_id, rule_dict, "tests", "testUser")
        rule = Rules.objects(block_name="rule with action", bot="tests").get()
        assert rule.events[4].name == "utter_greet"

    def test_update_non_existing_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        with pytest.raises(Exception):
            rule_dict = {'name': "non existing story", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
            processor.update_complex_story('non existing story_id', rule_dict, "tests", "testUser")

    def test_update_rule_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': None, 'steps': events, 'type': 'RULE', 'template_type': 'RULE'}
            processor.update_complex_story(pytest.story_id, rule_dict, "tests", "testUser")

    def test_fetch_stories_with_rules(self):
        processor = MongoProcessor()
        data = list(processor.get_stories("tests"))
        assert all(item['type'] in ['STORY', 'RULE'] for item in data)
        assert len(data) == 10

    def test_update_empty_rule_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': "", 'steps': events, 'type': 'RULE', 'template_type': 'RULE'}
            processor.update_complex_story(pytest.story_id, rule_dict, "tests", "testUser")

    def test_update_blank_rule_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': " ", 'steps': events, 'type': 'RULE', 'template_type': 'RULE'}
            processor.update_complex_story(pytest.story_id, rule_dict, "tests", "testUser")

    def test_update_empty_rule_event(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            rule_dict = {'name': "empty path", 'steps': [], 'type': 'RULE', 'template_type': 'RULE'}
            processor.update_complex_story(pytest.story_id, rule_dict, "tests", "testUser")

    def test_update_rule_invalid_type(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': "rule with action", 'steps': steps, 'type': 'TEST', 'template_type': 'RULE'}
            processor.update_complex_story(pytest.story_id, rule_dict, "tests", "testUser")

    def test_delete_non_existing_rule(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match="Flow does not exists"):
            processor.delete_complex_story("5e564fbcdcf0d5fad89e3acd", "RULE", "tests", "testUser")

    def test_update_rules_with_multiple_intents(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"}
        ]
        with pytest.raises(ValidationError,
                           match="Found rules 'rule with action' that contain more than user event.\nPlease use stories for this case"):
            rule_dict = {'name': "rule with action", 'steps': events, 'type': 'RULE', 'template_type': 'RULE'}
            processor.update_complex_story(pytest.story_id, rule_dict, "tests", "testUser")

    def test_update_rules_with_invalid_type(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "USER"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"}
        ]
        with pytest.raises(AppException, match="Invalid event type!"):
            rule_dict = {'name': "rule with action", 'steps': events, 'type': 'RULE', 'template_type': 'RULE'}
            processor.update_complex_story(pytest.story_id, rule_dict, "tests", "testUser")

    def test_delete_empty_rule(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.delete_complex_story('5e564fbcdcf0d5fad89e3acd', "RULE", "tests", "testUser")

    def test_case_insensitive_delete_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"},
        ]
        rule_dict = {"name": "rule2", 'steps': steps, 'type': 'RULE'}
        story_id = processor.add_complex_story(rule_dict, "tests", "testUser")
        processor.delete_complex_story(story_id, "RULE", "tests", "testUser")

    def test_update_rule_with_invalid_event(self):
        processor = MongoProcessor()
        steps = [
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'RULE'}
        with pytest.raises(ValidationError, match="First event should be an user"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'RULE'}
        with pytest.raises(ValidationError, match="user event should be followed by action"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "mood_sad", "type": "INTENT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'RULE'}
        with pytest.raises(ValidationError, match="Found 2 consecutive user events"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_delete_rule(self):
        processor = MongoProcessor()
        processor.delete_complex_story(pytest.story_id, "RULE", "tests", "testUser")

    def test_delete_rule_invalid_type(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match="Invalid type"):
            processor.delete_complex_story(pytest.story_id, "TEST", "tests", "testUser")

    def test_add_email_action(self):
        processor = MongoProcessor()
        email_config = {"action_name": "email_config",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": None,
                        "smtp_password": {'value': "test"},
                        "from_email": {"value": "from_email", "parameter_type": "slot"},
                        "to_email": {"value": ["test@test.com", "test1@test.com"], "parameter_type": "value"},
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "tls": False
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            assert processor.add_email_action(email_config, "TEST", "tests") is not None

    def test_add_email_action_with_custom_text(self):
        processor = MongoProcessor()
        email_config = {"action_name": "email_config_with_custom_text",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": None,
                        "smtp_password": {'value': "test"},
                        "from_email": {"value": "from_email", "parameter_type": "slot"},
                        "to_email": {"value": ["test@test.com", "test1@test.com"], "parameter_type": "value"},
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "tls": False,
                        "custom_text": {"value": "Hello from kairon!"}
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            assert processor.add_email_action(email_config, "TEST", "tests") is not None

    def test_add_email_action_with_story(self):
        processor = MongoProcessor()
        bot = 'TEST'
        user = 'tests'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "email_config", "type": "EMAIL_ACTION"},
        ]
        story_dict = {'name': "story with email action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with email action", bot=bot,
                                events__name='email_config', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == "story with email action"]
        assert story_with_form[0]['steps'] == [
            {'name': 'greet', 'type': 'INTENT'},
            {'name': 'email_config', 'type': 'EMAIL_ACTION'},
        ]
        processor.delete_complex_story(story_id, 'STORY', bot, user)

    def test_add_email_action_validation_error(self):
        processor = MongoProcessor()
        email_config = {"action_name": "email_config1",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": None,
                        "smtp_password": {'value': "test"},
                        "from_email": {"value": "from_email", "parameter_type": "slot"},
                        "to_email": {"value": ["test@test.com", "test1@test.com"], "parameter_type": "value"},
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "tls": False
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            mock_smtp.return_value = Exception()
            with pytest.raises(ValidationError, match="Invalid SMTP url"):
                processor.add_email_action(email_config, "TEST", "tests")

        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            temp = email_config['action_name']
            email_config['action_name'] = ""
            with pytest.raises(ValidationError, match="Action name cannot be empty"):
                processor.add_email_action(email_config, "TEST", "tests")
            email_config['action_name'] = temp

            temp = email_config['smtp_url']
            email_config['smtp_url'] = ""
            with pytest.raises(ValidationError, match="URL cannot be empty"):
                processor.add_email_action(email_config, "TEST", "tests")
            email_config['smtp_url'] = temp

            temp = email_config['from_email']
            email_config['from_email'] = {"value": "test@test", "parameter_type": "value"}
            with pytest.raises(ValidationError, match="Invalid From or To email address"):
                processor.add_email_action(email_config, "TEST", "tests")

            email_config['from_email'] = {"value": "", "parameter_type": "slot"}
            with pytest.raises(ValidationError, match="Provide name of the slot as value"):
                processor.add_email_action(email_config, "TEST", "tests")
            email_config['from_email'] = temp

            temp = email_config['to_email']
            email_config['to_email'] = {"value": "test@test", "parameter_type": "value"}
            with pytest.raises(ValidationError, match="Provide list of emails as value"):
                processor.add_email_action(email_config, "TEST", "tests")

            email_config['to_email'] = {"value": ["test@test"], "parameter_type": "value"}
            with pytest.raises(ValidationError, match="Invalid From or To email address"):
                processor.add_email_action(email_config, "TEST", "tests")

            email_config['to_email'] = {"value": "", "parameter_type": "slot"}
            with pytest.raises(ValidationError, match="Provide name of the slot as value"):
                processor.add_email_action(email_config, "TEST", "tests")

            email_config['to_email'] = temp

            email_config["custom_text"] = {"value": "custom_text_slot", "parameter_type": "sender_id"}
            with pytest.raises(ValidationError, match="custom_text can only be of type value or slot!"):
                processor.add_email_action(email_config, "TEST", "tests")

    def test_add_email_action_duplicate(self):
        processor = MongoProcessor()
        email_config = {"action_name": "email_config",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": None,
                        "smtp_password": {'value': "test"},
                        "from_email": {"value": "from_email", "parameter_type": "slot"},
                        "to_email": {"value": ["test@test.com", "test1@test.com"], "parameter_type": "value"},
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "tls": False
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            with pytest.raises(AppException, match="Action exists!"):
                processor.add_email_action(email_config, "TEST", "tests")

    def test_add_email_action_existing_name(self):
        processor = MongoProcessor()
        email_config = {"action_name": "test_action",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": None,
                        "smtp_password": {'value': "test"},
                        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
                        "to_email": {"value": "to_email", "parameter_type": "slot"},
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "tls": False
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            with pytest.raises(AppException, match="Action exists!"):
                processor.add_email_action(email_config, "test_bot", "tests")

    def test_edit_email_action(self):
        processor = MongoProcessor()
        email_config = {"action_name": "email_config",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": None,
                        "smtp_password": {'value': "test"},
                        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
                        "to_email": {"value": "to_email", "parameter_type": "slot"},
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "tls": False
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            assert processor.edit_email_action(email_config, "TEST", "tests") is None

        email_config["custom_text"] = {"value": "custom_text_slot", "parameter_type": "slot"}
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            assert processor.edit_email_action(email_config, "TEST", "tests") is None

    def test_edit_email_action_validation_error(self):
        processor = MongoProcessor()
        email_config = {"action_name": "email_config",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": None,
                        "smtp_password": {'value': "test"},
                        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
                        "to_email": {"value": "to_email", "parameter_type": "slot"},
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "tls": False
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            mock_smtp.return_value = Exception()
            with pytest.raises(ValidationError, match="Invalid SMTP url"):
                processor.edit_email_action(email_config, "TEST", "tests")

        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            temp = email_config['action_name']
            email_config['action_name'] = ""
            with pytest.raises(AppException, match='Action with name "" not found'):
                processor.edit_email_action(email_config, "TEST", "tests")
            email_config['action_name'] = temp

            temp = email_config['smtp_url']
            email_config['smtp_url'] = ""
            with pytest.raises(ValidationError, match="URL cannot be empty"):
                processor.edit_email_action(email_config, "TEST", "tests")
            email_config['smtp_url'] = temp

            temp = email_config['from_email']
            email_config['from_email'] = {"value": "test@demo", "parameter_type": "value"}
            with pytest.raises(ValidationError, match="Invalid From or To email address"):
                processor.edit_email_action(email_config, "TEST", "tests")

            email_config['from_email'] = {"value": "", "parameter_type": "slot"}
            with pytest.raises(ValidationError, match="Provide name of the slot as value"):
                processor.edit_email_action(email_config, "TEST", "tests")
            email_config['from_email'] = temp

            temp = email_config['to_email']
            email_config['to_email'] = {"value": "test@test", "parameter_type": "value"}
            with pytest.raises(ValidationError, match="Provide list of emails as value"):
                processor.edit_email_action(email_config, "TEST", "tests")

            email_config['to_email'] = {"value": ["test@test"], "parameter_type": "value"}
            with pytest.raises(ValidationError, match="Invalid From or To email address"):
                processor.edit_email_action(email_config, "TEST", "tests")

            email_config['to_email'] = {"value": "", "parameter_type": "slot"}
            with pytest.raises(ValidationError, match="Provide name of the slot as value"):
                processor.edit_email_action(email_config, "TEST", "tests")
            email_config['to_email'] = temp

    def test_edit_email_action_does_not_exist(self):
        processor = MongoProcessor()
        email_config = {"action_name": "email_config1",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": None,
                        "smtp_password": {'value': "test"},
                        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
                        "to_email": {"value": "to_email", "parameter_type": "slot"},
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "tls": False
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            with pytest.raises(AppException, match='Action with name "email_config1" not found'):
                processor.edit_email_action(email_config, "TEST", "tests")

    def test_list_email_actions(self):
        processor = MongoProcessor()
        assert len(list(processor.list_email_action("TEST"))) == 2

    def test_list_email_actions_with_default_value(self):
        processor = MongoProcessor()
        email_actions = list(processor.list_email_action("TEST"))
        email_actions[0].pop('_id')
        assert email_actions[0]['action_name'] == 'email_config'
        assert email_actions[0]['smtp_url'] == 'test.test.com'
        assert email_actions[0]['smtp_port'] == 25

    def test_list_email_actions_with_false(self):
        processor = MongoProcessor()
        email_actions = list(processor.list_email_action("TEST", False))
        assert email_actions[0].get('_id') is None
        assert email_actions[0]['action_name'] == 'email_config'
        assert email_actions[0]['smtp_url'] == 'test.test.com'
        assert email_actions[0]['smtp_port'] == 25

    def test_add_google_search_action(self, monkeypatch):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'google_custom_search',
            'api_key': {'value': '12345678'},
            'search_engine_id': 'asdfg:123456', "dispatch_response": False, "set_slot": "google_search_result",
            'failure_response': 'I have failed to process your request',
            'website': 'https://www.google.com',
        }
        assert processor.add_google_search_action(action, bot, user)
        assert Actions.objects(name='google_custom_search', status=True, bot=bot).get()
        assert GoogleSearchAction.objects(name='google_custom_search', status=True, bot=bot).get()

        def __mock_get_slots(*args, **kwargs):
            return "some_mock_value"

        monkeypatch.setattr(BaseQuerySet, "get", __mock_get_slots)
        with pytest.raises(AppException, match=re.escape("Slot is attached to action: ['google_custom_search']")):
            processor.delete_slot("google_search_result", bot, user)

    def test_add_google_search_action_with_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "google_custom_search", "type": "GOOGLE_SEARCH_ACTION"},
        ]
        story_dict = {'name': "story with google action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with google action", bot=bot,
                                events__name='google_custom_search', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'story with google action']
        assert story_with_form[0]['steps'] == [
            {'name': 'greet', 'type': 'INTENT'},
            {'name': 'google_custom_search', 'type': 'GOOGLE_SEARCH_ACTION'},
        ]
        processor.delete_complex_story(story_id, 'STORY', bot, user)

    def test_add_google_search_action_duplicate(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'google_custom_search',
            'api_key': {'value': '12345678'},
            'search_engine_id': 'asdfg:123456',
            'failure_response': 'I have failed to process your request',
        }
        with pytest.raises(AppException, match='Action exists!'):
            processor.add_google_search_action(action, bot, user)
        assert Actions.objects(name='google_custom_search', status=True, bot=bot).get()
        assert GoogleSearchAction.objects(name='google_custom_search', status=True, bot=bot).get()

    def test_add_google_search_action_existing_name(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        action = {
            'name': 'test_action',
            'api_key': {'value': '12345678'},
            'search_engine_id': 'asdfg:123456',
            'failure_response': 'I have failed to process your request',
        }
        with pytest.raises(AppException, match='Action exists!'):
            processor.add_google_search_action(action, bot, user)
        assert Actions.objects(name='test_action', status=True, bot=bot).get()

    def test_list_google_search_action_masked(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.list_google_search_actions(bot))
        actions[0].pop('_id')
        assert actions[1]['name'] == 'google_custom_search'
        assert actions[1]['api_key'] == {'_cls': 'CustomActionRequestParameters', 'encrypt': False, 'key': 'api_key',
                                         'parameter_type': 'value', 'value': '12345678'}
        assert actions[1]['search_engine_id'] == 'asdfg:123456'
        assert actions[1]['failure_response'] == 'I have failed to process your request'
        assert actions[1]['website'] == 'https://www.google.com'
        assert actions[1]['num_results'] == 1
        assert not actions[1]['dispatch_response']
        assert actions[1]['set_slot'] == "google_search_result"

    def test_edit_google_search_action_not_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'custom_search',
            'api_key': {'value': '12345678'},
            'search_engine_id': 'asdfg:123456',
            'failure_response': 'I have failed to process your request',
        }
        with pytest.raises(AppException, match='Google search action with name "custom_search" not found'):
            processor.edit_google_search_action(action, bot, user)
        assert Actions.objects(name='google_custom_search', status=True, bot=bot).get()
        assert GoogleSearchAction.objects(name='google_custom_search', status=True, bot=bot).get()

    def test_edit_google_search_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'google_custom_search',
            'api_key': {'value': '1234567889'},
            'search_engine_id': 'asdfg:12345689',
            'failure_response': 'Failed to perform search',
            'website': 'https://nimblework.com',
        }
        assert not processor.edit_google_search_action(action, bot, user)
        assert Actions.objects(name='google_custom_search', status=True, bot=bot).get()
        assert GoogleSearchAction.objects(name='google_custom_search', status=True, bot=bot).get()

    def test_list_google_search_action(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.list_google_search_actions(bot, False))
        assert actions[1].get('_id') is None
        assert actions[1]['name'] == 'google_custom_search'
        assert actions[1]['api_key'] == {'_cls': 'CustomActionRequestParameters', 'encrypt': False, 'key': 'api_key',
                                         'parameter_type': 'value', 'value': '1234567889'}
        assert actions[1]['search_engine_id'] == 'asdfg:12345689'
        assert actions[1]['failure_response'] == 'Failed to perform search'
        assert actions[1]['website'] == 'https://nimblework.com'
        assert actions[1]['num_results'] == 1
        assert actions[1]['dispatch_response']
        assert not actions[1].get('set_slot')

    def test_delete_google_search_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        processor.delete_action('google_custom_search', bot, user)
        with pytest.raises(DoesNotExist):
            Actions.objects(name='google_custom_search', status=True, bot=bot).get()
        with pytest.raises(DoesNotExist):
            GoogleSearchAction.objects(name='google_custom_search', status=True, bot=bot).get()

    def test_add_web_search_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        slot_name = "public_search_result"
        action = {
            'name': 'public_custom_search',
            "dispatch_response": False, "set_slot": "public_search_result",
            'failure_response': 'I have failed to process your request',
            'website': 'https://www.google.com',
        }
        slot = {"name": slot_name, "type": "any", "initial_value": None, "influence_conversation": True}
        processor.add_slot(slot_value=slot, bot=bot, user=user)
        assert processor.add_web_search_action(action, bot, user)
        assert Actions.objects(name='public_custom_search', status=True, bot=bot).get()
        assert WebSearchAction.objects(name='public_custom_search', status=True, bot=bot).get()
        with pytest.raises(AppException,
                           match=re.escape("Slot is attached to action: ['public_custom_search']")):
            processor.delete_slot("public_search_result", bot, user)

    def test_add_web_search_action_with_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "public_custom_search", "type": "WEB_SEARCH_ACTION"},
        ]
        story_dict = {'name': "story with web search action", 'steps': steps, 'type': 'STORY',
                      'template_type': 'CUSTOM'}
        story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with web search action", bot=bot,
                                events__name='public_custom_search', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form_web = [s for s in stories if s['name'] == 'story with web search action']
        assert story_with_form_web[0]['steps'] == [
            {'name': 'greet', 'type': 'INTENT'},
            {'name': 'public_custom_search', 'type': 'WEB_SEARCH_ACTION'},
        ]
        processor.delete_complex_story(story_id, 'STORY', bot, user)

    def test_add_web_search_action_with_empty_name(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': ' ',
            "dispatch_response": False, "set_slot": "",
            'failure_response': 'I have failed to process your request',
            'website': 'https://www.google.com',
        }
        with pytest.raises(ValidationError, match="Action name cannot be empty"):
            processor.add_web_search_action(action, bot, user)

    def test_add_web_search_action_with_invalid_top_n(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'public_search_action_with_invalid_top_n',
            "dispatch_response": False, "set_slot": "", 'topn': 0,
            'failure_response': 'I have failed to process your request',
            'website': 'https://www.google.com',
        }
        with pytest.raises(ValidationError, match="topn must be greater than or equal to 1!"):
            processor.add_web_search_action(action, bot, user)

    def test_add_web_search_action_duplicate(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'public_custom_search',
            "dispatch_response": False, "set_slot": "public_search_result",
            'failure_response': 'I have failed to process your request',
            'website': 'https://www.google.com',
        }
        with pytest.raises(AppException, match='Action exists!'):
            processor.add_web_search_action(action, bot, user)
        assert Actions.objects(name='public_custom_search', status=True, bot=bot).get()
        assert WebSearchAction.objects(name='public_custom_search', status=True, bot=bot).get()

    def test_list_web_search_action_masked(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.list_web_search_actions(bot))
        actions[0].pop('_id')
        assert actions[0]['name'] == 'public_custom_search'
        assert actions[0]['failure_response'] == 'I have failed to process your request'
        assert actions[0]['website'] == 'https://www.google.com'
        assert actions[0]['topn'] == 1
        assert not actions[0]['dispatch_response']
        assert actions[0]['set_slot'] == "public_search_result"

    def test_edit_web_search_action_not_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'custom_search',
            'failure_response': 'I have failed to process your request',
        }
        with pytest.raises(AppException, match='Public search action with name "custom_search" not found'):
            processor.edit_web_search_action(action, bot, user)
        assert Actions.objects(name='public_custom_search', status=True, bot=bot).get()
        assert WebSearchAction.objects(name='public_custom_search', status=True, bot=bot).get()

    def test_edit_web_search_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'public_custom_search',
            "dispatch_response": False, "set_slot": "public_search_result",
            'failure_response': 'Failed to perform public search',
            'website': 'https://nimblework.com',
        }
        assert not processor.edit_web_search_action(action, bot, user)
        assert Actions.objects(name='public_custom_search', status=True, bot=bot).get()
        assert WebSearchAction.objects(name='public_custom_search', status=True, bot=bot).get()

    def test_list_web_search_action(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.list_web_search_actions(bot, False))
        assert actions[0].get('_id') is None
        assert actions[0]['name'] == 'public_custom_search'
        assert actions[0]['failure_response'] == 'Failed to perform public search'
        assert actions[0]['website'] == 'https://nimblework.com'
        assert actions[0]['topn'] == 1
        assert not actions[0]['dispatch_response']
        assert actions[0].get('set_slot')

    def test_delete_web_search_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        processor.delete_action('public_custom_search', bot, user)
        with pytest.raises(DoesNotExist):
            Actions.objects(name='public_custom_search', status=True, bot=bot).get()
        with pytest.raises(DoesNotExist):
            WebSearchAction.objects(name='public_custom_search', status=True, bot=bot).get()

    def test_add_hubspot_forms_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'action_hubspot_forms',
            'portal_id': '12345678',
            'form_guid': 'asdfg:123456',
            'fields': [
                {"key": 'email', 'value': 'email_slot', 'parameter_type': 'slot'},
                {"key": 'firstname', 'value': 'firstname_slot', 'parameter_type': 'slot'}
            ],
            'response': 'Form submitted'
        }
        assert processor.add_hubspot_forms_action(action, bot, user)
        assert Actions.objects(name='action_hubspot_forms', status=True, bot=bot).get()
        assert HubspotFormsAction.objects(name='action_hubspot_forms', status=True, bot=bot).get()

    def test_add_hubspot_forms_action_with_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "action_hubspot_forms", "type": "HUBSPOT_FORMS_ACTION"},
        ]
        story_dict = {'name': "story with hubspot form action", 'steps': steps, 'type': 'STORY',
                      'template_type': 'CUSTOM'}
        story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with hubspot form action", bot=bot,
                                events__name='action_hubspot_forms', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'story with hubspot form action']
        assert story_with_form[0]['steps'] == [
            {'name': 'greet', 'type': 'INTENT'},
            {'name': 'action_hubspot_forms', 'type': 'HUBSPOT_FORMS_ACTION'},
        ]
        processor.delete_complex_story(story_id, 'STORY', bot, user)

    def test_add_hubspot_forms_action_duplicate(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'action_hubspot_forms',
            'portal_id': '12345678',
            'form_guid': 'asdfg:123456',
            'fields': [
                {"key": 'email', 'value': 'email_slot', 'parameter_type': 'slot'},
                {"key": 'firstname', 'value': 'firstname_slot', 'parameter_type': 'slot'}
            ]
        }
        with pytest.raises(AppException, match='Action exists!'):
            processor.add_hubspot_forms_action(action, bot, user)
        assert Actions.objects(name='action_hubspot_forms', status=True, bot=bot).get()
        assert HubspotFormsAction.objects(name='action_hubspot_forms', status=True, bot=bot).get()

    def test_add_hubspot_forms_action_existing_name(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        action = {
            'name': 'test_action',
            'portal_id': '12345678',
            'form_guid': 'asdfg:123456',
            'fields': [
                {"key": 'email', 'value': 'email_slot', 'parameter_type': 'slot'},
                {"key": 'firstname', 'value': 'firstname_slot', 'parameter_type': 'slot'}
            ]
        }
        with pytest.raises(AppException, match='Action exists!'):
            processor.add_hubspot_forms_action(action, bot, user)
        assert Actions.objects(name='test_action', status=True, bot=bot).get()

    def test_edit_hubspot_forms_action_not_exists(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        action = {
            'name': 'test_action',
            'portal_id': '12345678',
            'form_guid': 'asdfg:123456',
            'fields': [
                {"key": 'email', 'value': 'email_slot', 'parameter_type': 'slot'},
                {"key": 'firstname', 'value': 'firstname_slot', 'parameter_type': 'slot'}
            ]
        }
        with pytest.raises(AppException, match=f'Action with name "{action.get("name")}" not found'):
            processor.edit_hubspot_forms_action(action, bot, user)

    def test_edit_hubspot_forms_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'action_hubspot_forms',
            'portal_id': '123456785787',
            'form_guid': 'asdfg:12345678787',
            'fields': [
                {"key": 'email', 'value': 'email_slot', 'parameter_type': 'slot'},
                {"key": 'fullname', 'value': 'fullname_slot', 'parameter_type': 'slot'},
                {"key": 'company', 'value': 'digite', 'parameter_type': 'value'},
                {"key": 'phone', 'value': 'phone_slot', 'parameter_type': 'slot'}
            ],
            'response': 'Hubspot Form submitted'
        }
        assert not processor.edit_hubspot_forms_action(action, bot, user)
        assert Actions.objects(name='action_hubspot_forms', status=True, bot=bot).get()
        assert HubspotFormsAction.objects(name='action_hubspot_forms', status=True, bot=bot).get()

    def test_list_hubspot_forms_action(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.list_hubspot_forms_actions(bot))
        assert actions[0]['name'] == 'action_hubspot_forms'
        assert actions[0]['portal_id'] == '123456785787'
        assert actions[0]['form_guid'] == 'asdfg:12345678787'
        assert actions[0]['fields'] == [
            {'_cls': 'HttpActionRequestBody', 'key': 'email', 'value': 'email_slot', 'parameter_type': 'slot',
             'encrypt': False},
            {'_cls': 'HttpActionRequestBody', 'key': 'fullname', 'value': 'fullname_slot', 'parameter_type': 'slot',
             'encrypt': False},
            {'_cls': 'HttpActionRequestBody', 'key': 'company', 'value': 'digite', 'parameter_type': 'value',
             'encrypt': False},
            {'_cls': 'HttpActionRequestBody', 'key': 'phone', 'value': 'phone_slot', 'parameter_type': 'slot',
             'encrypt': False}]
        assert actions[0]['response'] == 'Hubspot Form submitted'

    def test_list_hubspot_forms_action_with_false(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.list_hubspot_forms_actions(bot, False))
        assert actions[0].get('_id') is None
        assert actions[0]['name'] == 'action_hubspot_forms'
        assert actions[0]['portal_id'] == '123456785787'
        assert actions[0]['form_guid'] == 'asdfg:12345678787'
        assert actions[0]['fields'] == [
            {'_cls': 'HttpActionRequestBody', 'key': 'email', 'value': 'email_slot', 'parameter_type': 'slot',
             'encrypt': False},
            {'_cls': 'HttpActionRequestBody', 'key': 'fullname', 'value': 'fullname_slot', 'parameter_type': 'slot',
             'encrypt': False},
            {'_cls': 'HttpActionRequestBody', 'key': 'company', 'value': 'digite', 'parameter_type': 'value',
             'encrypt': False},
            {'_cls': 'HttpActionRequestBody', 'key': 'phone', 'value': 'phone_slot', 'parameter_type': 'slot',
             'encrypt': False}]
        assert actions[0]['response'] == 'Hubspot Form submitted'

    def test_delete_hubspot_forms_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        processor.delete_action('action_hubspot_forms', bot, user)
        with pytest.raises(DoesNotExist):
            Actions.objects(name='action_hubspot_forms', status=True, bot=bot).get()
        with pytest.raises(DoesNotExist):
            HubspotFormsAction.objects(name='action_hubspot_forms', status=True, bot=bot).get()

    def test_add_hubspot_forms_action_reserved_keyword(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        action = {
            'name': KAIRON_TWO_STAGE_FALLBACK,
            'portal_id': '12345678',
            'form_guid': 'asdfg:123456',
            'fields': [
                {"key": 'email', 'value': 'email_slot', 'parameter_type': 'slot'},
                {"key": 'firstname', 'value': 'firstname_slot', 'parameter_type': 'slot'}
            ]
        }
        with pytest.raises(AppException, match=f"{KAIRON_TWO_STAGE_FALLBACK} is a reserved keyword"):
            processor.add_hubspot_forms_action(action, bot, user)

    def test_list_all_actions(self):
        bot = 'test_bot'
        user = 'test_user'
        action = "test_list_all_action_pyscript_action"
        script = "bot_response='hello world'"
        processor = MongoProcessor()
        pyscript_config = PyscriptActionRequest(
            name=action,
            source_code=script,
            dispatch_response=False,
        )
        action_id = processor.add_pyscript_action(pyscript_config.dict(), user, bot)

        action = {
            'name': 'test_list_all_action_google_action',
            'api_key': {'value': '12345678'},
            'search_engine_id': 'asdfg:123456', "dispatch_response": False, "set_slot": "google_search_result",
            'failure_response': 'I have failed to process your request',
            'website': 'https://www.google.com',
        }
        action_id = processor.add_google_search_action(action, bot, user)

        actions_list = list(processor.list_all_actions(bot=bot))
        assert actions_list[-1]['name'] == 'test_list_all_action_google_action'
        assert actions_list[-2]['name'] == 'test_list_all_action_pyscript_action'


    def test_add_custom_2_stage_fallback_action_validation_error(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        request = {"trigger_rules": None, "text_recommendations": None}
        with pytest.raises(ValidationError):
            processor.add_two_stage_fallback_action(request, bot, user)

    def test_add_custom_2_stage_fallback_action_recommendations_only(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        request = {"fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                                       " Or else please rephrase your question.",
                   "trigger_rules": None,
                   "text_recommendations": {"count": 3, "use_intent_ranking": True}}
        processor.add_two_stage_fallback_action(request, bot, user)
        assert Actions.objects(name=KAIRON_TWO_STAGE_FALLBACK, bot=bot).get()
        config = list(processor.get_two_stage_fallback_action_config(bot, KAIRON_TWO_STAGE_FALLBACK))
        assert config[0].get("timestamp") is None
        config[0].pop("_id")
        assert config == [{'name': 'kairon_two_stage_fallback',
                           'text_recommendations': {"count": 3, "use_intent_ranking": True}, 'trigger_rules': [],
                           "fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                                               " Or else please rephrase your question."}]

    def test_add_custom_2_stage_fallback_action_with_false(self):
        processor = MongoProcessor()
        bot = 'test'
        assert Actions.objects(name=KAIRON_TWO_STAGE_FALLBACK, bot=bot).get()
        config = list(processor.get_two_stage_fallback_action_config(bot, KAIRON_TWO_STAGE_FALLBACK, False))
        assert config[0].get("timestamp") is None
        assert config[0].get("_id") is None
        assert config == [{'name': 'kairon_two_stage_fallback',
                           'text_recommendations': {"count": 3, "use_intent_ranking": True}, 'trigger_rules': [],
                           "fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                                               " Or else please rephrase your question."}]

    def test_add_custom_2_stage_fallback_action_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        request = {"trigger_rules": None, "text_recommendations": {"count": 3}}
        with pytest.raises(AppException, match="Action exists!"):
            processor.add_two_stage_fallback_action(request, bot, user)

    def test_add_custom_2_stage_fallback_action_rules_not_found(self):
        processor = MongoProcessor()
        bot = 'test_add_custom_2_stage_fallback_action_rules_not_found'
        user = 'test_user'
        request = {"trigger_rules": [{"text": "Mail me", "payload": "send_mail"},
                                     {"text": "Contact me", "payload": "call"}]}
        with pytest.raises(AppException, match=r"Intent {.+} do not exist in the bot"):
            processor.add_two_stage_fallback_action(request, bot, user)

    def test_add_custom_2_stage_fallback_action_rules_only(self):
        processor = MongoProcessor()
        bot = 'test_add_custom_2_stage_fallback_action_rules_only'
        user = 'test_user'
        request = {"fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                                       " Or else please rephrase your question.",
                   "trigger_rules": [{"text": "Mail me", "payload": "greet"},
                                     {"text": "Contact me", "payload": "call"}]}
        processor.add_intent("greet", bot, user, False)
        processor.add_intent("call", bot, user, False)
        processor.add_two_stage_fallback_action(request, bot, user)
        assert Actions.objects(name=KAIRON_TWO_STAGE_FALLBACK, bot=bot).get()
        config = list(processor.get_two_stage_fallback_action_config(bot, KAIRON_TWO_STAGE_FALLBACK))
        assert config[0].get("timestamp") is None
        config[0].pop("_id")
        assert config == [{'name': 'kairon_two_stage_fallback',
                           'trigger_rules': [{'text': 'Mail me', 'payload': 'greet', 'is_dynamic_msg': False},
                                             {'text': 'Contact me', 'payload': 'call', 'is_dynamic_msg': False}],
                           "fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                                               " Or else please rephrase your question."}]

    def test_add_custom_2_stage_fallback_action_with_user_message(self):
        processor = MongoProcessor()
        bot = 'test_add_custom_2_stage_fallback_action_with_static_user_message'
        user = 'test_user'
        request = {"fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                                       " Or else please rephrase your question.",
                   "trigger_rules": [
                       {"text": "Mail me", "payload": "greet", "message": "my payload", "is_dynamic_msg": True},
                       {"text": "Contact me", "payload": "call", "message": None, "is_dynamic_msg": False}]}
        processor.add_intent("greet", bot, user, False)
        processor.add_intent("call", bot, user, False)
        processor.add_two_stage_fallback_action(request, bot, user)
        assert Actions.objects(name=KAIRON_TWO_STAGE_FALLBACK, bot=bot).get()
        config = list(processor.get_two_stage_fallback_action_config(bot, KAIRON_TWO_STAGE_FALLBACK))
        assert config[0].get("timestamp") is None
        config[0].pop("_id")
        assert config == [{'name': 'kairon_two_stage_fallback', 'trigger_rules': [
            {'text': 'Mail me', 'payload': 'greet', 'message': 'my payload', 'is_dynamic_msg': True},
            {'text': 'Contact me', 'payload': 'call', 'is_dynamic_msg': False}],
                           "fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                                               " Or else please rephrase your question."}]

    def test_edit_custom_2_stage_fallback_action_not_found(self):
        processor = MongoProcessor()
        bot = 'test_edit_custom_2_stage_fallback_action_not_found'
        user = 'test_user'
        request = {"trigger_rules": None, "text_recommendations": {"count": 3}}
        with pytest.raises(AppException, match=f'Action with name "{KAIRON_TWO_STAGE_FALLBACK}" not found'):
            processor.edit_two_stage_fallback_action(request, bot, user)

    def test_get_2_stage_fallback_action_not_found(self):
        processor = MongoProcessor()
        bot = 'test_edit_custom_2_stage_fallback_action_not_found'
        assert list(processor.get_two_stage_fallback_action_config(bot)) == []

    def test_edit_custom_2_stage_fallback_action_recommendations_only(self):
        processor = MongoProcessor()
        bot = 'test_add_custom_2_stage_fallback_action_rules_only'
        user = 'test_user'
        request = {"fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                                       " Or else please rephrase your question.", "trigger_rules": None,
                   "text_recommendations": {"count": 3}}
        processor.edit_two_stage_fallback_action(request, bot, user)
        assert Actions.objects(name=KAIRON_TWO_STAGE_FALLBACK, bot=bot).get()
        config = list(processor.get_two_stage_fallback_action_config(bot, KAIRON_TWO_STAGE_FALLBACK))
        assert config[0].get("timestamp") is None
        config[0].pop("_id")
        assert config == [{'name': 'kairon_two_stage_fallback',
                           'text_recommendations': {"count": 3, "use_intent_ranking": False},
                           'trigger_rules': [],
                           "fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                                               " Or else please rephrase your question."}]

    def test_edit_custom_2_stage_fallback_action_rules_only(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        request = {"fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                                       " Or else please rephrase your question.",
                   "trigger_rules": [
                       {"text": "Mail me", "payload": "send_mail", 'message': 'my payload', 'is_dynamic_msg': False},
                       {"text": "Contact me", "payload": "call", "is_dynamic_msg": True}]}
        processor.add_intent("send_mail", bot, user, False)
        processor.add_intent("call", bot, user, False)
        processor.edit_two_stage_fallback_action(request, bot, user)
        assert Actions.objects(name=KAIRON_TWO_STAGE_FALLBACK, bot=bot).get()
        config = list(processor.get_two_stage_fallback_action_config(bot, KAIRON_TWO_STAGE_FALLBACK))
        assert config[0].get("timestamp") is None
        config[0].pop("_id")
        assert config == [{'name': 'kairon_two_stage_fallback', 'trigger_rules': [
            {'text': 'Mail me', 'payload': 'send_mail', 'message': 'my payload', 'is_dynamic_msg': False},
            {'text': 'Contact me', 'payload': 'call', 'is_dynamic_msg': True}],
                           "fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                                               " Or else please rephrase your question."}]

    def test_edit_custom_2_stage_fallback_action_rules_not_found(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        request = {"trigger_rules": [{"text": "DM me", "payload": "send_dm"}]}

        with pytest.raises(AppException, match=f"Intent {set(['send_dm'])} do not exist in the bot"):
            processor.edit_two_stage_fallback_action(request, bot, user)

    def test_delete_2_stage_fallback_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        processor.delete_complex_story(pytest.two_stage_fallback_story_id, "RULE", bot, user)
        processor.delete_action(KAIRON_TWO_STAGE_FALLBACK, bot, user)
        with pytest.raises(DoesNotExist):
            Actions.objects(name=KAIRON_TWO_STAGE_FALLBACK, status=True, bot=bot).get()

    def test_create_kairon_faq_action_rule(self):
        processor = MongoProcessor()
        bot = 'test_create_kairon_faq_action_rule'
        user = 'test_user'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "kairon_faq_action", "type": "PROMPT_ACTION"}
        ]
        request = {'name': steps[1]["name"],
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        processor.add_prompt_action(request, bot, user)

        story_dict = {'name': "activate kairon faq action", 'steps': steps, 'type': 'RULE', 'template_type': 'CUSTOM'}
        pytest.two_stage_fallback_story_id = processor.add_complex_story(story_dict, bot, user)
        rule = Rules.objects(block_name="activate kairon faq action", bot=bot,
                             events__name="kairon_faq_action", status=True).get()
        assert rule.to_mongo().to_dict()['events'] == [{'name': '...', 'type': 'action'},
                                                       {'name': 'greet', 'type': 'user'},
                                                       {'name': "kairon_faq_action", 'type': 'action'}]
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == "activate kairon faq action"]
        assert story_with_form[0]['steps'] == [
            {"name": "greet", "type": "INTENT"},
            {"name": "kairon_faq_action", "type": "PROMPT_ACTION"}
        ]

    def test_add_secret(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        key = "AWS_KEY"
        value = "123456789-0dfghjk"
        id = processor.add_secret(key, value, bot, user)
        assert not Utility.check_empty_string(id)
        key_value = KeyVault.objects().get(id=id)
        assert key_value.key == key
        assert value == Utility.decrypt_message(key_value.value)

    def test_add_secret_already_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        key = "AWS_KEY"
        value = "123456789-0dfghjk"
        with pytest.raises(AppException, match="Key exists!"):
            processor.add_secret(key, value, bot, user)

    def test_add_secret_empty_value(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        key = "GOOGLE_KEY"
        value = None
        with pytest.raises(ValidationError):
            processor.add_secret(key, value, bot, user)

        key = None
        value = "sdfghj567"
        with pytest.raises(ValidationError):
            processor.add_secret(key, value, bot, user)

    def test_get_secret_after_addition(self):
        processor = MongoProcessor()
        bot = 'test'
        key = "AWS_KEY"
        assert processor.get_secret(key, bot) == "123456789-0dfghjk"

    def test_list_keys(self):
        processor = MongoProcessor()
        bot = 'test'
        assert ["AWS_KEY"] == processor.list_secrets(bot)

    def test_update_secret(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        key = "AWS_KEY"
        value = "123456789-0dfghjkdfghj"
        id = processor.update_secret(key, value, bot, user)
        assert not Utility.check_empty_string(id)
        key_value = KeyVault.objects().get(id=id)
        assert key_value.key == key
        assert value == Utility.decrypt_message(key_value.value)

    def test_update_secret_not_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        key = "GCP_KEY"
        value = "123456789-0dfghjkdfghj"
        with pytest.raises(AppException, match=f"key '{key}' does not exists!"):
            processor.update_secret(key, value, bot, user)

    def test_update_secret_empty_value(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        key = "AWS_KEY"
        value = None
        with pytest.raises(ValidationError):
            processor.update_secret(key, value, bot, user)

    def test_get_secret_after_update(self):
        processor = MongoProcessor()
        bot = 'test'
        key = "AWS_KEY"
        assert "123456789-0dfghjkdfghj" == processor.get_secret(key, bot)

    def test_delete_secret(self):
        processor = MongoProcessor()
        bot = 'test'
        key = "AWS_KEY"
        processor.delete_secret(key, bot, user="test")
        with pytest.raises(DoesNotExist):
            KeyVault.objects(key=key, bot=bot).get()

    def test_delete_secret_not_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        key = "GCPKEY"
        with pytest.raises(AppException, match=f"key '{key}' does not exists!"):
            processor.delete_secret(key, bot, user="test")

    def test_get_secret_not_found(self):
        processor = MongoProcessor()
        bot = 'test'
        key = "GOOGLE_KEY"
        with pytest.raises(AppException, match=f"key '{key}' does not exists!"):
            processor.get_secret(key, bot)

    def test_get_secret_no_error(self):
        processor = MongoProcessor()
        bot = 'test'
        key = "GOOGLE_KEY"
        assert None is processor.get_secret(key, bot, False)

    def test_list_keys_empty(self):
        processor = MongoProcessor()
        bot = 'test'
        assert [] == processor.list_secrets(bot)

    def test_delete_secret_attached_to_http_action(self):
        bot = 'test'
        key = "GCPKEY"
        user = "user"
        value = "123456789-0dfghjk"
        processor = MongoProcessor()
        processor.add_secret(key, value, bot, user)
        http_params_list = [HttpActionRequestBody(key="param1", value="param1", parameter_type="slot"),
                            HttpActionRequestBody(key="param2", value=key, parameter_type="key_vault")]
        HttpActionConfig(
            action_name="test_delete_secret_attached_to_http_action",
            response=HttpActionResponse(value="action executed!"),
            http_url="http://kairon.digite.com/get/all",
            request_method="POST",
            params_list=http_params_list,
            bot=bot,
            user=user
        ).save()
        with pytest.raises(AppException, match=re.escape(
                "Key is attached to action: ['test_delete_secret_attached_to_http_action']")):
            processor.delete_secret(key, bot, user="test")

        action = HttpActionConfig.objects(action_name="test_delete_secret_attached_to_http_action", bot=bot).get()
        action.params_list = []
        action.headers = http_params_list
        action.save()
        with pytest.raises(AppException, match=re.escape(
                "Key is attached to action: ['test_delete_secret_attached_to_http_action']")):
            processor.delete_secret(key, bot, user=user)

        action = HttpActionConfig.objects(action_name="test_delete_secret_attached_to_http_action", bot=bot).get()
        action.params_list = []
        action.headers = [HttpActionRequestBody(key="param1", value="param1", parameter_type="key_vault"),
                          HttpActionRequestBody(key="param2", value=key, parameter_type="value")]
        action.save()
        processor.delete_secret(key, bot, user=user)
        with pytest.raises(DoesNotExist):
            KeyVault.objects(key=key, bot=bot).get()

    def test_delete_secret_attached_to_email_action(self):
        bot = 'test'
        key = "KUBKEY"
        user = "user"
        value = "1526473-nxndj"
        processor = MongoProcessor()
        processor.add_secret(key, value, bot, user)
        smtp_userid_list = CustomActionRequestParameters(key="smtp_userid", value=key, parameter_type="key_vault")
        email_config = {"action_name": "test_delete_secret_attached_to_email_action",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": smtp_userid_list,
                        "smtp_password": {'value': "test"},
                        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
                        "to_email": {"value": "to_email", "parameter_type": "slot"},
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "tls": False
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True):
            processor.add_email_action(email_config, bot, user)
        with pytest.raises(AppException, match=re.escape(
                "Key is attached to action: ['test_delete_secret_attached_to_email_action']")):
            processor.delete_secret(key, bot, user="test")

        action = EmailActionConfig.objects(action_name="test_delete_secret_attached_to_email_action", bot=bot).get()
        action.smtp_userid = None
        action.smtp_password = smtp_userid_list
        with patch("kairon.shared.utils.SMTP", autospec=True):
            action.save()
        with pytest.raises(AppException, match=re.escape(
                "Key is attached to action: ['test_delete_secret_attached_to_email_action']")):
            processor.delete_secret(key, bot, user=user)

        action = EmailActionConfig.objects(action_name="test_delete_secret_attached_to_email_action", bot=bot).get()
        action.smtp_userid = None
        action.smtp_password = CustomActionRequestParameters(key="param2", value="param2", parameter_type="key_vault")
        with patch("kairon.shared.utils.SMTP", autospec=True):
            action.save()
        processor.delete_secret(key, bot, user=user)
        with pytest.raises(DoesNotExist):
            KeyVault.objects(key=key, bot=bot).get()

    def test_delete_secret_attached_to_google_action(self):
        processor = MongoProcessor()
        key = 'AZKEY'
        bot = 'test'
        user = 'test_user'
        value = '7362-jdnsn'
        processor.add_secret(key, value, bot, user)
        api_key_value = {'key': "api_key", 'value': key, 'parameter_type': "key_vault"}
        action = {
            'name': 'test_delete_secret_attached_to_google_action',
            'api_key': api_key_value,
            'search_engine_id': 'asdfg:123456',
            'failure_response': 'I have failed to process your request',
        }
        processor.add_google_search_action(action, bot, user)
        with pytest.raises(AppException, match=re.escape(
                "Key is attached to action: ['test_delete_secret_attached_to_google_action']")):
            processor.delete_secret(key, bot, user=user)

        action = GoogleSearchAction.objects(name="test_delete_secret_attached_to_google_action", bot=bot).get()
        action.api_key = CustomActionRequestParameters(key="param2", value="param2", parameter_type="key_vault")
        action.save()
        processor.delete_secret(key, bot, user=user)
        with pytest.raises(DoesNotExist):
            KeyVault.objects(key=key, bot=bot).get()

    def test_delete_secret_attached_to_jira_action(self):
        processor = MongoProcessor()
        key = 'QSKEY'
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        value = '7039-hffi'
        processor.add_secret(key, value, bot, user)
        api_token_value = {'key': "api_token", 'value': key, 'parameter_type': "key_vault"}
        action = {
            'name': 'test_delete_secret_attached_to_jira_action', 'url': url, 'user_name': 'test@digite.com',
            'api_token': api_token_value, 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
            'response': 'We have logged a ticket'
        }

        def _mock_validation(*args, **kwargs):
            return None

        with patch('kairon.shared.actions.data_objects.JiraAction.validate', new=_mock_validation):
            processor.add_jira_action(action, bot, user)
        with pytest.raises(AppException, match=re.escape(
                "Key is attached to action: ['test_delete_secret_attached_to_jira_action']")):
            processor.delete_secret(key, bot, user=user)

        action = JiraAction.objects(name="test_delete_secret_attached_to_jira_action", bot=bot).get()
        action.api_token = CustomActionRequestParameters(key="param2", value="param2", parameter_type="key_vault")
        with patch('kairon.shared.actions.data_objects.JiraAction.validate', new=_mock_validation):
            action.save()
        processor.delete_secret(key, bot, user=user)
        with pytest.raises(DoesNotExist):
            KeyVault.objects(key=key, bot=bot).get()

    def test_delete_secret_attached_to_zendesk_action(self):
        processor = MongoProcessor()
        key = 'ABKEY'
        bot = 'test'
        user = 'test'
        value = '4327-hssw'
        processor.add_secret(key, value, bot, user)
        api_token_value = {'key': "api_token", 'value': key, 'parameter_type': "key_vault"}
        action = {'name': 'test_delete_secret_attached_to_zendesk_action', 'subdomain': 'digite751',
                  'api_token': api_token_value, 'subject': 'new ticket', 'user_name': 'udit.pandey@digite.com',
                  'response': 'ticket filed'}

        def _mock_validation(*args, **kwargs):
            return None

        with patch('kairon.shared.actions.data_objects.ZendeskAction.validate', new=_mock_validation):
            processor.add_zendesk_action(action, bot, user)
        with pytest.raises(AppException, match=re.escape(
                "Key is attached to action: ['test_delete_secret_attached_to_zendesk_action']")):
            processor.delete_secret(key, bot, user=user)

        action = ZendeskAction.objects(name="test_delete_secret_attached_to_zendesk_action", bot=bot).get()
        action.api_token = CustomActionRequestParameters(key="param2", value="param2", parameter_type="key_vault")
        with patch('kairon.shared.actions.data_objects.ZendeskAction.validate', new=_mock_validation):
            action.save()
        processor.delete_secret(key, bot, user=user)
        with pytest.raises(DoesNotExist):
            KeyVault.objects(key=key, bot=bot).get()

    def test_delete_secret_attached_to_pipedrivelead_action(self):
        processor = MongoProcessor()
        key = 'NKKEY'
        bot = 'test'
        user = 'test_user'
        value = '1518-hshw'
        processor.add_secret(key, value, bot, user)
        api_token_value = {'key': "api_token", 'value': key, 'parameter_type': "key_vault"}
        action = {
            'name': 'test_delete_secret_attached_to_pipedrivelead_action',
            'domain': 'https://digite751.pipedrive.com/',
            'api_token': api_token_value,
            'title': 'new lead',
            'response': 'I have failed to create lead for you',
            'metadata': {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
        }

        def _mock_validation(*args, **kwargs):
            return None

        with patch('kairon.shared.actions.data_objects.PipedriveLeadsAction.validate', new=_mock_validation):
            processor.add_pipedrive_action(action, bot, user)
        with pytest.raises(AppException, match=re.escape(
                "Key is attached to action: ['test_delete_secret_attached_to_pipedrivelead_action']")):
            processor.delete_secret(key, bot, user=user)

        action = PipedriveLeadsAction.objects(name="test_delete_secret_attached_to_pipedrivelead_action", bot=bot).get()
        action.api_token = CustomActionRequestParameters(key="param2", value="param2", parameter_type="key_vault")
        with patch('kairon.shared.actions.data_objects.PipedriveLeadsAction.validate', new=_mock_validation):
            action.save()
        processor.delete_secret(key, bot, user=user)
        with pytest.raises(DoesNotExist):
            KeyVault.objects(key=key, bot=bot).get()

    def test_delete_secret_attached_to_hubspot_action(self):
        processor = MongoProcessor()
        key = 'VPKEY'
        bot = 'test'
        user = 'test_user'
        value = '7728-abcg'
        processor.add_secret(key, value, bot, user)
        fields_list = [HttpActionRequestBody(key="param1", value="param1", parameter_type="slot"),
                       HttpActionRequestBody(key="param2", value=key, parameter_type="key_vault")]
        action = {
            'name': 'test_delete_secret_attached_to_hubspot_action',
            'portal_id': '12345678',
            'form_guid': 'asdfg:123456',
            'fields': fields_list,
            'response': 'Form submitted'
        }

        def _mock_validation(*args, **kwargs):
            return None

        with patch('kairon.shared.actions.data_objects.HubspotFormsAction.validate', new=_mock_validation):
            processor.add_hubspot_forms_action(action, bot, user)
        with pytest.raises(AppException, match=re.escape(
                "Key is attached to action: ['test_delete_secret_attached_to_hubspot_action']")):
            processor.delete_secret(key, bot, user=user)

        action = HubspotFormsAction.objects(name="test_delete_secret_attached_to_hubspot_action", bot=bot).get()
        action.fields = [HttpActionRequestBody(key="param1", value="param1", parameter_type="key_vault"),
                         HttpActionRequestBody(key="param2", value=key, parameter_type="value")]
        with patch('kairon.shared.actions.data_objects.HubspotFormsAction.validate', new=_mock_validation):
            action.save()
        processor.delete_secret(key, bot, user=user)
        with pytest.raises(DoesNotExist):
            KeyVault.objects(key=key, bot=bot).get()

    def test_get_logs(self):
        till_date = datetime.utcnow().date()
        bot = "test_get_logs"
        user = "testUser2"
        start_time = datetime.utcnow() - timedelta(days=1)
        end_time = datetime.utcnow() + timedelta(days=1)
        processor = MongoProcessor()

        ModelProcessor.set_training_status(bot, user, "Done")
        ModelProcessor.set_training_status(bot, user, "Done")
        log_two = processor.get_logs(bot, "model_training", start_time, end_time)
        assert len(log_two) == 2
        ActionServerLogs(intent="intent2", action="http_action", sender="sender_id",
                         url="http://kairon-api.digite.com/api/bot",
                         request_params={}, api_response="Response", bot_response="Bot Response", bot=bot,
                         status="FAILURE").save()
        ActionServerLogs(intent="intent1", action="http_action", sender="sender_id",
                         request_params={}, api_response="Response", bot_response="Bot Response",
                         bot=bot).save()
        log_three = processor.get_logs(bot, "action_logs", start_time, end_time)
        assert len(log_three) == 2
        DataImporterLogProcessor.add_log(bot, user, is_data_uploaded=False, event_status="Completed")
        DataImporterLogProcessor.add_log(bot, user, is_data_uploaded=False, event_status="Completed")
        log_four = processor.get_logs(bot, "data_importer", start_time, end_time)
        assert len(log_four) == 2
        HistoryDeletionLogProcessor.add_log(bot, user, till_date, status='Completed')
        HistoryDeletionLogProcessor.add_log(bot, user, till_date, status='Completed')
        log_five = processor.get_logs(bot, "history_deletion", start_time, end_time)
        assert len(log_five) == 2
        MultilingualLogProcessor.add_log(source_bot=bot, user=user, event_status="Completed")
        MultilingualLogProcessor.add_log(source_bot=bot, user=user, event_status="Completed")
        log_six = processor.get_logs(bot, "multilingual", start_time, end_time)
        assert len(log_six) == 2
        ModelTestingLogProcessor.log_test_result(bot, user,
                                                 stories_result={},
                                                 nlu_result={},
                                                 event_status='Completed')
        ModelTestingLogProcessor.log_test_result(bot, user,
                                                 stories_result={},
                                                 nlu_result={},
                                                 event_status='Completed')
        log_seven = processor.get_logs(bot, "model_testing", start_time, end_time)
        assert len(log_seven) == 2
        log_eight = processor.get_logs(bot, "audit_logs", start_time, end_time)
        assert len(log_eight) == 6

    def test_delete_audit_logs(self):
        processor = MongoProcessor()
        start_time = datetime.utcnow()
        init_time = start_time - timedelta(days=1000)
        logs = processor.get_logs("test", "audit_logs", init_time, start_time)
        num_logs = len(logs)
        AuditLogData(
            attributes=[{"key": "bot", "value": "test"}], user="test", timestamp=start_time,
            action=AuditlogActions.SAVE.value,
            entity="ModelTraining"
        ).save()
        AuditLogData(
            attributes=[{"key": "bot", "value": "test"}], user="test", timestamp=start_time - timedelta(days=366),
            action=AuditlogActions.SAVE.value,
            entity="ModelTraining"
        ).save()
        AuditLogData(
            attributes=[{"key": "bot", "value": "test"}], user="test", timestamp=start_time - timedelta(days=480),
            action=AuditlogActions.SAVE.value,
            entity="ModelTraining"
        ).save()
        logs = processor.get_logs("test", "audit_logs", init_time, start_time)
        assert len(logs) == num_logs + 3
        processor.delete_audit_logs()
        logs = processor.get_logs("test", "audit_logs", init_time, start_time)
        assert len(logs) == num_logs + 1

    def test_save_faq_csv(self):
        processor = MongoProcessor()
        bot = 'tests'
        user = 'tester'
        file = UploadFile(filename="upload.csv", file=open("./tests/testing_data/upload_faq/upload.csv", "rb"))
        df = Utility.read_faq(file)
        component_count, error_summary = processor.save_faq(bot, user, df)
        assert component_count == {'intents': 0, 'utterances': 5, 'stories': 0, 'rules': 0, 'training_examples': 5,
                                   'domain': {'intents': 0, 'utterances': 0}}
        assert error_summary == {'intents': [], 'utterances': ['Utterance text cannot be empty or blank spaces'],
                                 'training_examples': ['Training Example cannot be empty or blank spaces:    ']}

    def test_save_faq_xlsx(self):
        processor = MongoProcessor()
        bot = 'test_faq'
        user = 'tester'
        file = UploadFile(filename="upload.xlsx", file=open("./tests/testing_data/upload_faq/upload.xlsx", "rb"))
        df = Utility.read_faq(file)
        component_count, error_summary = processor.save_faq(bot, user, df)
        assert component_count == {'intents': 0, 'utterances': 5, 'stories': 0, 'rules': 0, 'training_examples': 5,
                                   'domain': {'intents': 0, 'utterances': 0}}
        assert error_summary == {'intents': [], 'utterances': ['Utterance text cannot be empty or blank spaces',
                                                               'Utterance already exists!'],
                                 'training_examples': ['Training Example cannot be empty or blank spaces: ']}

    def test_save_faq_delete_data(self):
        processor = MongoProcessor()
        bot = 'test_save_faq_delete_data'
        user = 'tester'

        def __mock_exception(*args, **kwargs):
            raise Exception("Failed to add story")

        df = pd.DataFrame([{"questions": "what is digite?", "answer": "IT company"}])
        with patch("kairon.shared.data.processor.MongoProcessor.add_complex_story") as mock_failure:
            mock_failure.side_effect = __mock_exception
            component_count, error_summary = processor.save_faq(bot, user, df)
        assert component_count == {'intents': 0, 'utterances': 1, 'stories': 0, 'rules': 0, 'training_examples': 1,
                                   'domain': {'intents': 0, 'utterances': 0}}
        assert error_summary == {'intents': [], 'utterances': ['Failed to add story'], 'training_examples': []}

    def test_validate_faq_training_file(self, monkeypatch):
        processor = MongoProcessor()
        bot = 'tests_faq'
        utterance = "test_delete_utterance"
        user = 'testUser'
        file = UploadFile(filename="validate.csv", file=open("./tests/testing_data/upload_faq/validate.csv", "rb"))
        df = Utility.read_faq(file)
        processor.add_response({"text": "I am good here!!"}, utterance, bot, user)
        training_examples_expected = {'hi': 'greet', 'hello': 'greet', 'ok': 'affirm', 'no': 'deny'}

        def _mongo_aggregation(*args, **kwargs):
            return training_examples_expected

        monkeypatch.setattr(MongoProcessor, 'get_training_examples_as_dict', _mongo_aggregation)
        error_summary, component_count = DataUtility.validate_faq_training_data(bot, df)
        assert len(error_summary['utterances']) == 3
        assert len(error_summary['training_examples']) == 4
        assert component_count == {'intents': 0, 'utterances': 8, 'stories': 0, 'rules': 0, 'training_examples': 10,
                                   'domain': {'intents': 0, 'utterances': 0}}

    def test_validate_faq_training_file_empty(self):
        bot = 'tests'
        df = pd.DataFrame()
        with pytest.raises(AppException, match="No data found!"):
            DataUtility.validate_faq_training_data(bot, df)

    def test_delete_all_faq(self, monkeypatch):
        processor = MongoProcessor()
        utterances_query_counter = 0
        intents_query_counter = 0
        first_list = ['Hi', 'Hey', 'hello']
        second_list = ['unhappy', 'sad']
        var = ['good morning', 'morning']
        first_steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        first_rule_dict = {'name': "first rule", 'steps': first_steps, 'type': 'RULE', 'template_type': 'Q&A'}
        second_steps = [
            {"name": "sad", "type": "INTENT"},
            {"name": "utter_sad", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        second_rule_dict = {'name': "second rule", 'steps': second_steps, 'type': 'RULE', 'template_type': 'Q&A'}

        list(processor.add_training_example(first_list, 'greet', 'test', 'test_user', False))
        list(processor.add_training_example(second_list, 'sad', 'test', 'test_user', False))
        list(processor.add_training_example(var, 'message', 'test', 'test_user', False))
        processor.add_text_response('I am good', 'utter_greet', 'test', 'test_user')
        processor.add_text_response('I am sad', 'utter_sad', 'test', 'test_user')
        processor.add_text_response('What are your questions?', 'utter_ask', 'test', 'test_user')
        processor.add_complex_story(first_rule_dict, 'test', 'test_user')
        processor.add_complex_story(second_rule_dict, 'test', 'test_user')

        def _mock_aggregation(*args, **kwargs):
            nonlocal utterances_query_counter, intents_query_counter

            get_intents_pipelines = [
                {'$unwind': {'path': '$events'}},
                {'$match': {'events.type': 'user'}},
                {'$group': {'_id': None, 'intents': {'$push': '$events.name'}}},
                {"$project": {'_id': 0, 'intents': 1}}
            ]
            get_utterances_pipelines = [
                {'$unwind': {'path': '$events'}},
                {'$match': {'events.type': 'action', 'events.name': {'$regex': '^utter_'}}},
                {'$group': {'_id': None, 'utterances': {'$push': '$events.name'}}},
                {"$project": {'_id': 0, 'utterances': 1}}
            ]
            print(args[1])
            print(args[0]._mongo_query)
            if args[0]._collection_obj.name == 'stories':
                print("stories")
                yield {'intents': [], 'utterances': []}
            elif args[1] == get_intents_pipelines and intents_query_counter == 0:
                intents_query_counter += 1
                print("intents")
                yield {'intents': ['greet', 'sad']}
            elif args[1] == get_utterances_pipelines and utterances_query_counter == 0:
                utterances_query_counter += 1
                print("utterances")
                yield {'utterances': ['utter_greet', 'utter_sad']}
            else:
                print("else")
                yield {'intents': [], 'utterances': []}

        monkeypatch.setattr(BaseQuerySet, 'aggregate', _mock_aggregation)
        processor.delete_all_faq('test')
        assert not Utility.is_exist(TrainingExamples, raise_error=False, intent='greet', bot='test')
        assert not Utility.is_exist(TrainingExamples, raise_error=False, intent='sad', bot='test')
        assert not Utility.is_exist(Intents, raise_error=False, name='greet', bot='test')
        assert not Utility.is_exist(Intents, raise_error=False, name='sad', bot='test')
        assert not Utility.is_exist(Utterances, raise_error=False, name='utter_greet', bot='test')
        assert not Utility.is_exist(Utterances, raise_error=False, name='utter_sad', bot='test')
        assert not Utility.is_exist(Responses, raise_error=False, name='utter_greet', bot='test')
        assert not Utility.is_exist(Responses, raise_error=False, name='utter_sad', bot='test')
        assert not Utility.is_exist(Rules, raise_error=False, block_name='first rule', bot='test')
        assert not Utility.is_exist(Rules, raise_error=False, block_name='second rule', bot='test')
        assert Utility.is_exist(TrainingExamples, raise_error=False, intent='message', bot='test')
        assert Utility.is_exist(Intents, raise_error=False, name='message', bot='test')
        assert Utility.is_exist(Utterances, raise_error=False, name='utter_ask', bot='test')
        assert Utility.is_exist(Responses, raise_error=False, name='utter_ask', bot='test')

    def test_save_payload_metadata(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        settings = BotSettings.objects(bot=bot).get()
        settings.llm_settings = LLMSettings(enable_faq=True)
        settings.cognition_collections_limit = 5
        settings.save()
        schema = {
            "metadata": [
                {"column_name": "details", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "Details_collection",
            "bot": bot,
            "user": user
        }
        pytest.schema_id = processor.save_cognition_schema(schema, user, bot)

        cognition_schema = CognitionSchema.objects(bot=bot, id=pytest.schema_id).get()
        assert cognition_schema['collection_name'] == 'details_collection'
        assert cognition_schema['metadata'][0]['column_name'] == 'details'
        assert cognition_schema['metadata'][0]['data_type'] == "str"

        payload = {
            "data": {"details": "Pune"},
            "collection": "Details_collection",
            "content_type": "json"}
        processor.save_cognition_data(payload, user, bot)
        pytest.cognition_id = processor.save_cognition_data(payload, user, bot)

        cognition_data = CognitionData.objects(bot=bot, id=pytest.cognition_id).get()
        assert cognition_data['data'] == {"details": "Pune"}
        assert cognition_data['collection'] == 'details_collection'
        assert cognition_data['content_type'] == CognitionDataType.json.value

        schema_one = {
            "metadata": [
                {"column_name": "metadata_one", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "metadata_one",
            "bot": bot,
            "user": user
        }
        pytest.schema_id_one = processor.save_cognition_schema(schema_one, user, bot)

        schema_two = {
            "metadata": [
                {"column_name": "metadata_two", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "metadata_two",
            "bot": bot,
            "user": user
        }
        pytest.schema_id_two = processor.save_cognition_schema(schema_two, user, bot)

        schema_three = {
            "metadata": [
                {"column_name": "metadata_three", "data_type": "str", "enable_search": True,
                 "create_embeddings": True}],
            "collection_name": "metadata_three",
            "bot": bot,
            "user": user
        }
        with pytest.raises(AppException, match="Collection limit exceeded!"):
            processor.save_cognition_schema(schema_three, user, bot)
        processor.delete_cognition_schema(pytest.schema_id_one, bot, user=user)
        processor.delete_cognition_schema(pytest.schema_id_two, bot, user=user)
        schema_four = {
            "metadata": [
                {"column_name": "details", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "details_collection",
            "bot": bot,
            "user": user
        }
        with pytest.raises(AppException, match="Collection already exists!"):
            processor.save_cognition_schema(schema, user, bot)

        data = list(processor.list_cognition_schema(bot))

        # Fetch all schema IDs
        schema_ids = [schema['_id'] for schema in processor.list_cognition_schema(bot)]

        # Fetch all collection names
        collection_names = [schema['collection_name'] for schema in processor.list_cognition_schema(bot)]

        # Delete all collection except the last one
        for collection_name in collection_names[:-1]:
            for data in CognitionData.objects(bot=bot, collection=collection_name):
                data.delete()

        # Delete all schema except the last one
        for schema_id in schema_ids[:-1]:
            processor.delete_cognition_schema(schema_id, bot, user=user)

        data = list(processor.list_cognition_schema(bot))
        settings = BotSettings.objects(bot=bot).get()
        settings.llm_settings = LLMSettings(enable_faq=False)
        settings.save()

    def test_save_payload_metadata_column_limit_exceeded(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        schema = {
            "metadata": [
                {"column_name": "tech", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "age", "data_type": "int", "enable_search": True, "create_embeddings": False},
                {"column_name": "color", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "name", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "gender", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "experience", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            "collection_name": "test_save_payload_metadata_column_limit_exceeded",
            "bot": bot,
            "user": user
        }
        with pytest.raises(AppException, match="Column limit exceeded for collection!"):
            processor.save_cognition_schema(schema, user, bot)

    def test_save_payload_metadata_same_columns(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        schema = {
            "metadata": [
                {"column_name": "tech", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "tech", "data_type": "int", "enable_search": True, "create_embeddings": False}],
            "collection_name": "details_collect",
            "bot": bot,
            "user": user
        }
        with pytest.raises(AppException, match="Columns cannot be same in the schema!"):
            processor.save_cognition_schema(schema, user, bot)

    def test_save_payload_metadata_column_name_empty(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        schema = {
            "metadata": [{"column_name": "", "data_type": "int", "enable_search": True,
                          "create_embeddings": True}],
            "collection_name": "column_name_empty",
            "bot": bot,
            "user": user}
        with pytest.raises(ValidationError, match="Column name cannot be empty"):
            CognitionSchema(**schema).save()

    def test_save_payload_metadata_data_type_invalid(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        schema = {
            "metadata": [{"column_name": "name", "data_type": "bool", "enable_search": True,
                          "create_embeddings": True}],
            "collection_name": "test_save_payload_metadata_data_type_invalid",
            "bot": bot,
            "user": user
        }
        with pytest.raises(ValidationError, match="Only str,int and float data types are supported"):
            CognitionSchema(**schema).save()

    def test_get_payload_metadata(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        data = list(processor.list_cognition_schema(bot))
        print(data)
        assert data[0]
        assert data[0]['_id']
        assert data[0]['metadata'][0] == {'column_name': 'details', 'data_type': 'str', 'enable_search': True,
                                          'create_embeddings': True}
        assert data[0]['collection_name'] == 'details_collection'

    def test_delete_payload_metadata(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        processor.delete_cognition_schema(pytest.schema_id, bot, user=user)

    def test_delete_cognition_schema_with_data(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        schema = {
            "metadata": [
                {"column_name": "employee", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "details_collection_with_data",
            "bot": bot,
            "user": user
        }

        schema_id = processor.save_cognition_schema(schema, user, bot)

        CognitionData(collection=schema['collection_name'], bot=bot, user=user, data={"employee": "John Doe"}, content_type="json",).save()
        CognitionData(collection=schema['collection_name'], bot=bot, user=user, data={"employee": "Jane Smith"}, content_type="json",).save()

        assert CognitionData.objects(collection=schema['collection_name'], bot=bot).count() == 2

        processor.delete_cognition_schema(schema_id, bot, user=user)

        assert CognitionData.objects(collection=schema['collection_name'], bot=bot).count() == 0

    def test_save_payload_metadata_and_delete_with_no_cognition_data(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        schema = {
            "metadata": [
                {"column_name": "employee", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "details_collection",
            "bot": bot,
            "user": user
        }
        pytest.schema_id_final = processor.save_cognition_schema(schema, user, bot)
        processor.delete_cognition_schema(pytest.schema_id_final, bot, user=user)

    def test_delete_payload_metadata_does_not_exists(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        with pytest.raises(AppException, match="Schema does not exists!"):
            processor.delete_cognition_schema("507f191e050c19729de760ea", bot, user=user)

    def test_get_payload_metadata_not_exists(self):
        processor = CognitionDataProcessor()
        bot = 'testing'
        assert list(processor.list_cognition_schema(bot)) == []

    def test_delete_schema_attached_to_prompt_action(self):
        processor = CognitionDataProcessor()
        processor_two = MongoProcessor()
        bot = 'test'
        user = 'testUser'
        settings = BotSettings.objects(bot=bot).get()
        settings.llm_settings = LLMSettings(enable_faq=True)
        settings.save()
        schema = {
            "metadata": None,
            "collection_name": "Python",
            "bot": bot,
            "user": user
        }
        pytest.delete_schema_id = processor.save_cognition_schema(schema, user, bot)
        request = {'name': 'test_delete_schema_attached_to_prompt_action',
                   'user_question': {'type': 'from_slot', 'value': 'prompt_question'},
                   'llm_prompts': [
                       {'name': 'System Prompt',
                        'data': 'You are a personal assistant. Answer question based on the context below.',
                        'type': 'system', 'source': 'static', 'is_enabled': True},
                       {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True},
                       {'name': 'Query Prompt', 'data': "What kind of language is python?",
                        'instructions': 'Rephrase the query.',
                        'type': 'query', 'source': 'static', 'is_enabled': False},
                       {'name': 'Similarity Prompt', "data": "python",
                        'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                        'type': 'user', 'source': 'bot_content',
                        'is_enabled': True}
                   ],
                   'instructions': ['Answer in a short manner.', 'Keep it simple.'],
                   "set_slots": [{"name": "gpt_result", "value": "${data}", "evaluation_type": "expression"},
                                 {"name": "gpt_result_type", "value": "${data.type}", "evaluation_type": "script"}],
                   "dispatch_response": False
                   }
        processor_two.add_prompt_action(request, bot, user)
        with pytest.raises(AppException,
                           match='Cannot remove collection python linked to action "test_delete_schema_attached_to_prompt_action"!'):
            processor.delete_cognition_schema(pytest.delete_schema_id, bot, user=user)
        processor_two.delete_action('test_delete_schema_attached_to_prompt_action', bot, user)
        processor.delete_cognition_schema(pytest.delete_schema_id, bot, user=user)

    def test_save_content_with_gpt_feature_disabled(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        settings = BotSettings.objects(bot=bot).get()
        settings.llm_settings = LLMSettings(enable_faq=False)
        settings.save()
        collection = "Bot"
        content = 'A bot, short for robot, is a program or software application designed to automate certain tasks or ' \
                  'perform specific functions, usually in an automated or semi-automated manner. Bots can be programmed' \
                  ' to perform a wide range of tasks, from simple tasks like answering basic questions or sending ' \
                  'automated messages to complex tasks like performing data analysis, playing games, or even controlling ' \
                  'physical machines.'
        payload = {
            "data": content,
            "content_type": "text",
            "collection": collection}
        with pytest.raises(AppException, match="Faq feature is disabled for the bot! Please contact support."):
            processor.save_cognition_data(payload, user, bot)

        settings = BotSettings.objects(bot=bot).get()
        settings.llm_settings = LLMSettings(enable_faq=True)
        settings.save()

    def test_save_content_atleast_ten_words(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        collection = 'Bot'
        content = 'A bot, short for robot, is a program.'
        payload = {
            "data": content,
            "content_type": "text",
            "collection": collection}
        with pytest.raises(AppException, match="Content should contain atleast 10 words."):
            processor.save_cognition_data(payload, user, bot)

    def test_save_content_collection_does_not_exist(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        collection = 'Bot'
        content = 'A bot, short for robot, is a program. Bots can be programmed to perform a wide range of tasks.'
        payload = {
            "data": content,
            "content_type": "text",
            "collection": collection}
        with pytest.raises(AppException, match="Collection does not exist!"):
            processor.save_cognition_data(payload, user, bot)

    def test_save_content_text_with_metadata_invalid(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        collection = "test_save_content_text_with_metadata_invalid"
        content = 'A large language model is a type of artificial intelligence system designed to understand and generate human language.'
        payload = {
            "data": content,
            "content_type": "text",
            "collection": collection}
        metadata = {
            "metadata": [
                {"column_name": "LLM", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": collection,
            "bot": bot,
            "user": user
        }
        processor.save_cognition_schema(metadata, user, bot)
        with pytest.raises(AppException, match="Text content type does not have schema!"):
            processor.save_cognition_data(payload, user, bot)

    def test_save_content(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        collection = "Bot"
        content = 'A bot, short for robot, is a program or software application designed to automate certain tasks or ' \
                  'perform specific functions, usually in an automated or semi-automated manner. Bots can be programmed' \
                  ' to perform a wide range of tasks, from simple tasks like answering basic questions or sending ' \
                  'automated messages to complex tasks like performing data analysis, playing games, or even controlling ' \
                  'physical machines.'
        payload = {
            "data": content,
            "content_type": "text",
            "collection": collection}
        metadata = {
            "metadata": None,
            "collection_name": collection,
            "bot": bot,
            "user": user
        }
        pytest.save_content_collection = processor.save_cognition_schema(metadata, user, bot)
        pytest.content_id = processor.save_cognition_data(payload, user, bot)
        content_id = '5349b4ddd2791d08c09890f3'
        with pytest.raises(AppException, match="Payload data already exists!"):
            processor.update_cognition_data(content_id, payload, user, bot)

    def test_update_content_atleast_ten_words(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        collection = 'Bot'
        content = 'Bots are commonly used in various industries.'
        payload = {
            "data": content,
            "content_type": "text",
            "collection": collection}
        with pytest.raises(AppException, match="Content should contain atleast 10 words."):
            processor.update_cognition_data(pytest.content_id, payload, user, bot)

    def test_update_content_collection_does_not_exists(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        collection = 'test_update_content_collection_does_not_exists'
        content = 'LLMs can be used for a wide range of applications, including chatbots, language translation, content generation, sentiment analysis, and many other natural language processing tasks. '
        payload = {
            "data": content,
            "content_type": "text",
            "collection": collection}
        with pytest.raises(AppException, match="Collection does not exist!"):
            processor.update_cognition_data(pytest.content_id, payload, user, bot)

    def test_update_content(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        collection = 'Bot'
        content = 'Bots are commonly used in various industries, such as e-commerce, customer service, gaming, ' \
                  'and social media. Some bots are designed to interact with humans in a conversational manner and are ' \
                  'called chatbots or virtual assistants.'
        payload = {
            "data": content,
            "content_type": "text",
            "collection": collection}
        processor.update_cognition_data(pytest.content_id, payload, user, bot)

    def test_update_content_not_found(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        content_id = '5349b4ddd2781d08c09890f3'
        collection = 'Bot'
        content = 'MongoDB is a source-available cross-platform document-oriented database program. ' \
                  'Classified as a NoSQL database program, MongoDB uses JSON-like documents with optional schemas. ' \
                  'MongoDB is developed by MongoDB Inc. and licensed under the Server Side Public License which is ' \
                  'deemed non-free by several distributions.'
        payload = {
            "data": content,
            "content_type": "text",
            "collection": collection}
        with pytest.raises(AppException, match="Payload with given id not found!"):
            processor.update_cognition_data(content_id, payload, user, bot)

    def test_delete_content(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        processor.delete_cognition_data(pytest.content_id, bot, user=user)

    def test_delete_content_does_not_exists(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        with pytest.raises(AppException, match="Payload does not exists!"):
            processor.delete_cognition_data("507f191e810c19729de860ea", bot)

    @patch("kairon.shared.cognition.processor.CognitionDataProcessor.list_cognition_data", autospec=True)
    def test_list_cognition_data_not_exists(self, mock_list_cognition_data):
        def _list_cognition_data(*args, **kwargs):
            return []

        mock_list_cognition_data.return_value = _list_cognition_data()
        kwargs = {}
        processor = CognitionDataProcessor()
        bot = 'test'
        assert list(processor.list_cognition_data(bot, **kwargs)) == []

    @patch("kairon.shared.cognition.processor.CognitionDataProcessor.list_cognition_data", autospec=True)
    @patch("kairon.shared.cognition.processor.CognitionDataProcessor.get_cognition_data", autospec=True)
    def test_list_cognition_data(self, mock_get_cognition_data, mock_list_cognition_data):
        cognition_data = [{'vector_id': 1,
                           'row_id': '65266ff16f0190ca4fd09898',
                           'data': 'Unit testing is a software testing technique in which individual units or components of a software application are tested in isolation to ensure that each unit functions as expected. ',
                           'content_type': 'text',
                           'collection': 'bot', 'user': 'testUser', 'bot': 'test'}]
        row_count = 1

        def _list_cognition_data(*args, **kwargs):
            return cognition_data

        mock_list_cognition_data.return_value = _list_cognition_data()

        def _get_cognition_data(*args, **kwargs):
            return cognition_data, row_count

        mock_get_cognition_data.return_value = _get_cognition_data()
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        content = 'Unit testing is a software testing technique in which individual units or components of a software ' \
                  'application are tested in isolation to ensure that each unit functions as expected. '
        payload = {
            "data": content,
            "content_type": "text",
            "collection": "Bot"}
        pytest.content_id_unit = processor.save_cognition_data(payload, user, bot)
        kwargs = {'collection': 'bot', 'data': 'Unit testing'}
        data = list(processor.list_cognition_data(bot, **kwargs))
        print(data)
        assert data[0][
                   'data'] == 'Unit testing is a software testing technique in which individual units or components of a ' \
                              'software application are tested in isolation to ensure that each unit functions as expected. '
        assert data[0]['row_id']
        assert data[0]['collection'] == 'bot'
        kwargs = {'collection': 'Bot', 'data': 'Unit testing'}
        log, count = processor.get_cognition_data(bot, **kwargs)
        assert log[0][
                   'data'] == 'Unit testing is a software testing technique in which individual units or components of a ' \
                              'software application are tested in isolation to ensure that each unit functions as expected. '
        assert log[0]['row_id']
        assert log[0]['collection'] == 'bot'
        assert count == 1
        kwargs = {}
        actual = list(processor.list_cognition_data(bot, **kwargs))
        print(actual)
        assert actual[0][
                   'data'] == 'Unit testing is a software testing technique in which individual units or components of a ' \
                              'software application are tested in isolation to ensure that each unit functions as expected. '
        assert actual[0]['row_id']
        assert actual[0]['collection'] == 'bot'
        cognition_data, row_count = processor.get_cognition_data(bot, **kwargs)
        assert cognition_data[0][
                   'data'] == 'Unit testing is a software testing technique in which individual units or components of a ' \
                              'software application are tested in isolation to ensure that each unit functions as expected. '
        assert cognition_data[0]['row_id']
        assert cognition_data[0]['collection'] == 'bot'
        assert row_count == 1

    def test_delete_content_for_action(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        processor.delete_cognition_data(pytest.content_id_unit, bot, user=user)

    def test_delete_payload_content_collection(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        processor.delete_cognition_schema(pytest.save_content_collection, bot, user=user)

    def test_save_payload_content_with_gpt_feature_disabled(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        payload = {
            "data": {"name": "Sita", "engineer": "yes"},
            "content_type": "json",
            "collection": "test_save_payload_content_with_gpt_feature_disabled",
            "bot": bot,
            "user": user
        }
        settings = BotSettings.objects(bot=bot).get()
        settings.llm_settings = LLMSettings(enable_faq=False)
        settings.save()
        with pytest.raises(AppException, match="Faq feature is disabled for the bot! Please contact support."):
            processor.save_cognition_data(payload, user, bot)

        settings = BotSettings.objects(bot=bot).get()
        settings.llm_settings = LLMSettings(enable_faq=True)
        settings.save()

    def test_save_payload_content_collection_does_not_exists(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        payload = {
            "data": {"name": "Nupur", "city": "Pune"},
            "collection": "test_save_payload_content_collection_does_not_exists",
            "content_type": "json"}
        with pytest.raises(AppException, match="Collection does not exist!"):
            processor.save_cognition_data(payload, user, bot)

    def test_save_payload_content(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        metadata = {
            "metadata": [
                {"column_name": "name", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "city", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "test_save_payload_content",
            "bot": bot,
            "user": user
        }
        processor.save_cognition_schema(metadata, user, bot)

        payload = {
            "data": {"name": "Nupur", "city": "Pune"},
            "collection": "test_save_payload_content",
            "content_type": "json"}
        pytest.payload_id = processor.save_cognition_data(payload, user, bot)
        payload_id = '64b0f2e66707e9282a13f6cd'
        with pytest.raises(AppException, match="Payload data already exists!"):
            processor.update_cognition_data(payload_id, payload, user, bot)

    def test_save_payload_content_metadata_does_not_exists(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        payload = {
            "data": {"number": 15, "group": "a"},
            "collection": "test_save_payload_content",
            "content_type": "json"}
        with pytest.raises(AppException, match="Columns do not exist in the schema!"):
            processor.save_cognition_data(payload, user, bot)

    def test_save_payload_content_invalid_data_type(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        metadata = {
            "metadata": [
                {"column_name": "number", "data_type": "int", "enable_search": True, "create_embeddings": True}],
            "collection_name": "test_save_payload_content_invalid_data_type",
            "bot": bot,
            "user": user
        }
        processor.save_cognition_schema(metadata, user, bot)
        payload = {
            "data": {"number": "Twenty-three"},
            "content_type": "json",
            "collection": "test_save_payload_content_invalid_data_type"}
        with pytest.raises(AppException, match="Invalid data type!"):
            processor.save_cognition_data(payload, user, bot)

    def test_save_payload_content_data_empty(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        payload = {
            "data": {},
            "content_type": "json",
            "bot": bot,
            "user": user
        }
        with pytest.raises(ValidationError, match="data cannot be empty"):
            CognitionData(**payload).save()

    def test_update_payload_content_not_found(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        payload_id = '5349b4ddd2719d08c09890f3'
        payload = {
            "data": {"city": "Pune", "color": "red"},
            "content_type": "json",
            "bot": bot,
            "user": user
        }
        with pytest.raises(AppException, match="Payload with given id not found!"):
            processor.update_cognition_data(payload_id, payload, user, bot)

    def test_save_payload_content_type_text_data_json_invalid(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        payload = {
            "data": {'color': 'red'},
            "content_type": "text",
            "bot": bot,
            "user": user
        }
        with pytest.raises(ValidationError, match="content type and type of data do not match!"):
            CognitionData(**payload).save()

    def test_update_payload_content_collection_does_not_exists(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        payload = {
            "data": {"city": "Pune", "color": "red"},
            "content_type": "json",
            "collection": "test_update_payload_content_collection_does_not_exists",
            "bot": bot,
            "user": user
        }
        with pytest.raises(AppException, match="Collection does not exist!"):
            processor.update_cognition_data(pytest.payload_id, payload, user, bot)

    def test_update_payload_content(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        payload = {
            "data": {"name": "Digite", "city": "Mumbai"},
            "content_type": "json",
            "collection": "test_save_payload_content",
            "bot": bot,
            "user": user
        }
        processor.update_cognition_data(pytest.payload_id, payload, user, bot)

    def test_get_payload_content(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        kwargs = {'collection': 'test_save_payload_content'}
        data, row_count = list(processor.get_cognition_data(bot, **kwargs))
        print(data)
        assert row_count == 1
        assert data[0][
                   'data'] == {"name": "Digite", "city": "Mumbai"}
        assert data[0]['row_id']
        assert data[0]['collection'] == 'test_save_payload_content'

    def test_delete_payload_content(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        processor.delete_cognition_data(pytest.payload_id, bot, user=user)

    def test_delete_payload_content_does_not_exists(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        with pytest.raises(AppException, match="Payload does not exists!"):
            processor.delete_cognition_data("507f191e050c19729de860ea", bot)

    def test_get_payload_content_not_exists(self):
        processor = CognitionDataProcessor()
        bot = 'testing'
        assert list(processor.list_cognition_data(bot)) == []


class TestAgentProcessor:

    def test_get_agent(self, monkeypatch):
        from kairon.chat.agent_processor import AgentProcessor

        def mongo_store(*args, **kwargs):
            return None

        monkeypatch.setattr(Utility, "get_local_mongo_store", mongo_store)
        agent = AgentProcessor.get_agent("tests")
        assert isinstance(agent, Agent)

    def test_get_agent_from_cache(self):
        from kairon.chat.agent_processor import AgentProcessor

        agent = AgentProcessor.get_agent("tests")
        assert isinstance(agent, Agent)

    def test_get_agent_from_cache_does_not_exists(self):
        from kairon.chat.agent_processor import AgentProcessor

        with pytest.raises(AppException):
            agent = AgentProcessor.get_agent("test")
            assert isinstance(agent, Agent)


class TestModelProcessor:

    @pytest.fixture(autouse=True, scope='class')
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection())
        yield None
        Utility.environment['notifications']['enable'] = False

    @pytest.fixture
    def test_set_training_status_inprogress(self):
        ModelProcessor.set_training_status("tests", "testUser", "Inprogress")
        model_training = ModelTraining.objects(bot="tests", status="Inprogress")
        return model_training

    def test_set_training_status_Done(self, test_set_training_status_inprogress):
        assert test_set_training_status_inprogress.__len__() == 1
        assert test_set_training_status_inprogress.first().bot == "tests"
        assert test_set_training_status_inprogress.first().user == "testUser"
        assert test_set_training_status_inprogress.first().status == "Inprogress"
        assert test_set_training_status_inprogress.first().model_config == MongoProcessor().load_config("tests")
        training_status_inprogress_id = test_set_training_status_inprogress.first().id

        ModelProcessor.set_training_status(bot="tests",
                                           user="testUser",
                                           status="Done",
                                           model_path="model_path"
                                           )
        model_training = ModelTraining.objects(bot="tests", status="Done")
        ids = [model.id for model in model_training]
        index = ids.index(training_status_inprogress_id)
        assert model_training.count() == 5
        assert training_status_inprogress_id in ids
        assert model_training[index].bot == "tests"
        assert model_training[index].user == "testUser"
        assert model_training[index].status == "Done"
        assert model_training[index].model_path == "model_path"
        assert ModelTraining.objects(bot="tests", status="Inprogress").__len__() == 0

    def test_set_training_status_Fail(self, test_set_training_status_inprogress):
        assert test_set_training_status_inprogress.__len__() == 1
        assert test_set_training_status_inprogress.first().bot == "tests"
        assert test_set_training_status_inprogress.first().user == "testUser"
        assert test_set_training_status_inprogress.first().status == "Inprogress"
        training_status_inprogress_id = test_set_training_status_inprogress.first().id

        ModelProcessor.set_training_status(bot="tests",
                                           user="testUser",
                                           status="Fail",
                                           model_path=None,
                                           exception="exception occurred while training model."
                                           )
        model_training = ModelTraining.objects(bot="tests", status="Fail")

        assert model_training.__len__() == 1
        assert model_training.first().id == training_status_inprogress_id
        assert model_training.first().bot == "tests"
        assert model_training.first().user == "testUser"
        assert model_training.first().status == "Fail"
        assert model_training.first().model_path is None
        assert model_training.first().exception == "exception occurred while training model."
        assert ModelTraining.objects(bot="tests", status="Inprogress").__len__() == 0

    def test_is_training_inprogress_False(self):
        actual_response = ModelProcessor.is_training_inprogress("tests")
        assert actual_response is False

    def test_is_training_inprogress_with_aborted(self):
        ModelProcessor.set_training_status("testbot", "testuser", "Aborted")
        model_training = ModelTraining.objects(bot="testbot", status="Aborted")
        actual_response = ModelProcessor.is_training_inprogress("tests", False)
        assert actual_response is False

    def test_is_training_inprogress_True(self, test_set_training_status_inprogress):
        assert test_set_training_status_inprogress.__len__() == 1
        assert test_set_training_status_inprogress.first().bot == "tests"
        assert test_set_training_status_inprogress.first().user == "testUser"
        assert test_set_training_status_inprogress.first().status == "Inprogress"

        actual_response = ModelProcessor.is_training_inprogress("tests", False)
        assert actual_response is True

    def test_is_training_inprogress_exception(self, test_set_training_status_inprogress):
        with pytest.raises(AppException) as exp:
            assert ModelProcessor.is_training_inprogress("tests")

        assert str(exp.value) == "Previous model training in progress."

    def test_is_daily_training_limit_exceeded_False(self, monkeypatch):
        bot = 'tests'
        bot_settings = BotSettings.objects(bot=bot).get()
        bot_settings.training_limit_per_day = 8
        bot_settings.save()
        actual_response = ModelProcessor.is_daily_training_limit_exceeded(bot)
        assert actual_response is False

    def test_is_daily_training_limit_exceeded_True(self, monkeypatch):
        bot = 'tests'
        bot_settings = BotSettings.objects(bot=bot).get()
        bot_settings.training_limit_per_day = 0
        bot_settings.save()
        actual_response = ModelProcessor.is_daily_training_limit_exceeded(bot, False)
        assert actual_response is True

    def test_is_daily_training_limit_exceeded_exception(self, monkeypatch):
        bot = 'tests'
        bot_settings = BotSettings.objects(bot=bot).get()
        bot_settings.training_limit_per_day = 0
        bot_settings.save()
        with pytest.raises(AppException) as exp:
            assert ModelProcessor.is_daily_training_limit_exceeded(bot)

        assert str(exp.value) == "Daily model training limit exceeded."

    @patch("kairon.chat.agent.agent.KaironAgent.load", autospec=True)
    def test_start_training_load_model_fail(self, mock_agent, monkeypatch):
        def mongo_store(*args, **kwargs):
            return None

        monkeypatch.setattr(Utility, "get_local_mongo_store", mongo_store)
        mock_agent.side_effect = Exception("Failed to load the model for the bot.")
        start_training("tests", "testUser")
        model_training = ModelTraining.objects(bot="tests", status="Fail")
        assert model_training.__len__() == 2
        assert model_training[1].exception in str("Failed to load the model for the bot.")

    def test_train_model_for_bot(self):
        model = train_model_for_bot("tests")
        created_model_file = os.path.basename(model)
        tar_files = glob.glob('models/tests/*.tar.gz')
        actual_model_file = os.path.basename(tar_files[0])
        folder = os.path.join("models/tests", '*.tar.gz')

        assert model
        assert len(list(glob.glob(folder))) == 1
        assert actual_model_file == created_model_file

    def test_get_training_history(self):
        actual_response = ModelProcessor.get_training_history("tests")
        assert actual_response

    def test_save_auditlog_event_config_without_eventurl(self):
        bot = "tests"
        user = "testuser"
        data = {}
        with pytest.raises(ValidationError, match='Event url can not be empty'):
            MongoProcessor.save_auditlog_event_config(bot=bot, user=user, data=data)

    def test_save_auditlog_event_config_without_headers(self):
        bot = "tests"
        user = "testuser"
        data = {"ws_url": "http://localhost:5000/event_url"}
        MongoProcessor.save_auditlog_event_config(bot=bot, user=user, data=data)
        result = MongoProcessor.get_auditlog_event_config(bot)
        assert result.get("ws_url") == data.get("ws_url")
        headers = json.loads(result.get("headers"))
        assert headers == {}

    @responses.activate
    def test_save_auditlog_event_config(self):
        bot = "tests"
        user = "testuser"
        data = {"ws_url": "http://localhost:5000/event_url",
                "headers": {'Autharization': '123456789'},
                "method": "GET"}
        responses.add(
            responses.GET,
            "http://localhost:5000/event_url",
            status=200,
            json='{"message": "success"}'
        )
        MongoProcessor.save_auditlog_event_config(bot=bot, user=user, data=data)
        result = MongoProcessor.get_auditlog_event_config(bot)
        assert result.get("ws_url") == data.get("ws_url")
        headers = json.loads(result.get("headers"))
        assert len(headers.keys()) == 1
        assert result.get("method") == "GET"

    def test_auditlog_for_chat_client_config(self):
        auditlog_data = list(AuditLogData.objects(attributes=[{"key": "bot", "value": "test"}], user='testUser',
                                                  entity='ChatClientConfig').order_by('-timestamp'))
        assert len(auditlog_data) > 0
        assert auditlog_data[0] is not None
        assert auditlog_data[0].attributes[0]["value"] == "test"
        assert auditlog_data[0].user == "testUser"
        assert auditlog_data[0].entity == "ChatClientConfig"

    def test_auditlog_for_intent(self):
        auditlog_data = list(
            AuditLogData.objects(attributes=[{"key": "bot", "value": "tests"}], user='testUser', action='save',
                                 entity='Intents').order_by('-timestamp'))
        assert len(auditlog_data) > 0
        assert auditlog_data is not None
        assert auditlog_data[0].attributes[0]["value"] == "tests"
        assert auditlog_data[0].user == "testUser"
        assert auditlog_data[0].entity == "Intents"

        auditlog_data = list(
            AuditLogData.objects(attributes=[{"key": "bot", "value": "tests"}], user='testUser', action='delete',
                                 entity='Intents').order_by('-timestamp'))
        # No hard delete supported for intents
        assert len(auditlog_data) == 8

    def test_get_auditlog_for_invalid_bot(self):
        bot = "invalid"
        page_size = 100
        auditlog_data, row_cnt = MongoProcessor.get_auditlog_for_bot(bot, page_size=page_size)
        assert auditlog_data == []

    def test_get_auditlog_for_bot_top_n_default(self):
        bot = "test"
        page_size = 100
        auditlog_data, row_cnt = MongoProcessor.get_auditlog_for_bot(bot, page_size=page_size)
        assert len(auditlog_data) > 90

    def test_get_auditlog_for_bot_date_range(self):
        bot = "test"
        from_date = datetime.utcnow().date() - timedelta(days=1)
        to_date = datetime.utcnow().date()
        page_size = 100
        auditlog_data, row_cnt = MongoProcessor.get_auditlog_for_bot(bot, from_date=from_date, to_date=to_date,
                                                                     page_size=page_size)
        assert len(auditlog_data) > 90

    def test_get_auditlog_for_bot_top_50(self):
        bot = "test"
        from_date = datetime.utcnow().date() - timedelta(days=1)
        to_date = datetime.utcnow().date()
        page_size = 50
        auditlog_data, row_cnt = MongoProcessor.get_auditlog_for_bot(bot, from_date=from_date, to_date=to_date,
                                                                     page_size=page_size)
        assert len(auditlog_data) == 50

    def test_get_auditlog_from_date_to_date_none(self):
        bot = "test"
        from_date = None
        to_date = None
        page_size = 50
        auditlog_data, row_cnt = MongoProcessor.get_auditlog_for_bot(bot, from_date=from_date, to_date=to_date,
                                                                     page_size=page_size)
        assert len(auditlog_data) == 50

    def test_edit_training_example_empty_or_blank(self):
        processor = MongoProcessor()
        examples = list(processor.get_training_examples("greet", "tests"))
        with pytest.raises(AppException, match="Training Example cannot be empty or blank spaces"):
            processor.edit_training_example(examples[0]["_id"], example="", intent="greet", bot="tests",
                                            user="testUser")

    def test_add_custom_form_attached_does_not_exist(self):
        processor = MongoProcessor()
        jsondata = {"type": "section",
                    "text": {
                        "text": "Make a bet on when the world will end:",
                        "type": "mrkdwn",
                        "accessory": {"type": "datepicker",
                                      "initial_date": "2019-05-21",
                                      "placeholder": {"type": "plain_text",
                                                      "text": "Select a date"}}}}
        with pytest.raises(AppException, match="Form 'unknown' does not exists"):
            assert processor.add_custom_response(jsondata, "utter_custom", "tests", "testUser", "unknown")

    def test_get_model_testing_accuracy(self):
        account = {
            "account": "test_accuarcy",
            "email": "divya.veeravelly@digite.com",
            "first_name": "test_first",
            "last_name": "test_last",
            "password": SecretStr("Quailink@46"),
        }

        loop = asyncio.new_event_loop()
        user_detail, mail, link = loop.run_until_complete(AccountProcessor.account_setup(account_setup=account))

        pytest.account = user_detail['account']
        bot1 = AccountProcessor.add_bot("bot_1", 1, "divya.veeravelly@digite.com", False)
        bot2 = AccountProcessor.add_bot("bot_2", 1, "divya.veeravelly@digite.com", False)
        u1 = ModelTestingLogs()
        u1.data = {"intent_evaluation": {"accuracy": 0.6424565337899992}}
        u1.type = 'nlu'
        u1.bot = bot1["_id"].__str__()
        u1.user = "divya"
        u1.save()

        u2 = ModelTestingLogs()
        u2.data = {"intent_evaluation": {"accuracy": 0.9875645647434565}}
        u2.type = 'nlu'
        u2.bot = bot2["_id"].__str__()
        u2.user = "divya"
        u2.save()
        result = AccountProcessor.get_model_testing_accuracy_of_all_accessible_bots(1, "divya.veeravelli@digite.com")
        assert result[bot1["_id"].__str__()] == 0.6424565337899992
        assert result[bot2["_id"].__str__()] == 0.9875645647434565

    def test_get_model_testing_accuracy_field_not_exists(self):
        account = {
            "account": "test_accuarcy_log",
            "email": "abcd@xyz.com",
            "first_name": "test_first_1",
            "last_name": "test_last_1",
            "password": SecretStr("Quailink@46"),
        }

        loop = asyncio.new_event_loop()
        user_detail, mail, link = loop.run_until_complete(AccountProcessor.account_setup(account_setup=account))

        pytest.account = user_detail['account']
        bot3 = AccountProcessor.add_bot("bot_3", 2, "abcd@xyz.com", False)
        bot4 = AccountProcessor.add_bot("bot_4", 2, "abcd@xyz.com", False)

        u1 = ModelTestingLogs()
        u1.data = {"intent_evaluation": {}}
        u1.type = 'nlu'
        u1.bot = bot3["_id"].__str__()
        u1.user = "divya"
        u1.save()

        u2 = ModelTestingLogs()
        u2.data = {"intent_evaluation": {}}
        u2.type = 'nlu'
        u2.bot = bot4["_id"].__str__()
        u2.user = "divya"
        u2.save()
        result = AccountProcessor.get_model_testing_accuracy_of_all_accessible_bots(2, "abcd@xyz.com")
        assert result[bot3["_id"].__str__()] is None
        assert result[bot4["_id"].__str__()] is None

    def test_get_model_testing_accuracy_mutliple_logs(self):
        account = {
            "account": "test_accuarcy_logs",
            "email": "wxyz@abcd.com",
            "first_name": "test_first_2",
            "last_name": "test_last_2",
            "password": SecretStr("abcdefg@123"),
        }

        loop = asyncio.new_event_loop()
        user_detail, mail, link = loop.run_until_complete(AccountProcessor.account_setup(account_setup=account))

        pytest.account = user_detail['account']
        bot_a = AccountProcessor.add_bot("bot_a", 3, "wxyz@abcd.com", False)
        bot_c = AccountProcessor.add_bot("bot_c", 3, "wxyz@abcd.com", False)

        u1 = ModelTestingLogs()
        u1.type = "nlu"
        u1.user = "wxyz@abcd.com"
        u1.data = {"intent_evaluation": {}}
        u1.bot = bot_a["_id"].__str__()
        u1.save()

        u3 = ModelTestingLogs()
        u3.type = "nlu"
        u3.user = "wxyz@abcd.com"
        u3.bot = bot_a["_id"].__str__()
        u3.data = {"intent_evaluation": {"accuracy": 0.9424565337899992}}
        u3.save()

        u2 = ModelTestingLogs()
        u2.type = "nlu"
        u2.user = "wxyz@abcd.com"
        u2.bot = bot_a["_id"].__str__()
        u2.data = {"intent_evaluation": {}}
        u2.save()

        u4 = ModelTestingLogs()
        u4.type = "nlu"
        u4.user = "wxyz@abcd.com"
        u4.data = {"intent_evaluation": {"accuracy": 0.8424565337899992}}
        u4.bot = bot_c["_id"].__str__()
        u4.save()

        u5 = ModelTestingLogs()
        u5.type = "nlu"
        u5.user = "wxyz@abcd.com"
        u5.bot = bot_c["_id"].__str__()
        u5.data = {"intent_evaluation": {"accuracy": None}}
        u5.save()

        u6 = ModelTestingLogs()
        u6.type = "nlu"
        u6.user = "wxyz@abcd.com"
        u6.bot = bot_c["_id"].__str__()
        u6.data = {"intent_evaluation": {}}
        u6.save()

        result = AccountProcessor.get_model_testing_accuracy_of_all_accessible_bots(3, "wxyz@abcd.com")
        assert result[bot_a["_id"].__str__()] == 0.9424565337899992
        assert result[bot_c["_id"].__str__()] == 0.8424565337899992

    def test_auditlog_for_data_with_encrypted_field(self):
        start_time = datetime.utcnow() - timedelta(days=1)
        end_time = datetime.utcnow() + timedelta(days=1)

        processor = MongoProcessor()
        bot = 'secret'
        user = 'secret_user'
        key = "auditlog"
        value = "secret-value"
        processor.add_secret(key, value, bot, user)

        config = {
            "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K",
            "slack_signing_secret": "79f036b9894eef17c064213b90d1042b",
            "client_id": "3396830255712.3396861654876869879",
            "client_secret": "cf92180a7634d90bf42a217408376878"
        }
        connector_type = "slack"
        meta_config = {}

        Channels(bot=bot, user=user, connector_type=connector_type, config=config, meta_config=meta_config).save()

        auditlog_data = processor.get_logs("secret", "audit_logs", start_time, end_time)
        assert auditlog_data[0]["attributes"][0]["value"] == bot
        assert auditlog_data[0]["entity"] == "Channels"
        assert auditlog_data[0]["data"]["config"] != config

        assert auditlog_data[2]["attributes"][0]["value"] == bot
        assert auditlog_data[2]["entity"] == "KeyVault"
        assert auditlog_data[2]["data"]["value"] != value

    def test_add_schedule_action(self):
        bot = "testbot"
        user = "testuser"
        expected_data = {
            "name": "test_schedule_action",
            "schedule_time": {"value": "2024-08-06T09:00:00.000+0530", "parameter_type": "value"},
            "timezone": None,
            "schedule_action": "test_pyscript",
            "response_text": "action scheduled",
            "params_list": [
                {
                    "key": "param_key",
                    "value": "param_1",
                    "parameter_type": "value",
                }
            ],
            "dispatch_bot_response": True
        }

        processor = MongoProcessor()
        processor.add_schedule_action(expected_data, bot, user)

        actual_data = list(processor.list_schedule_action(bot))
        assert expected_data.get("name") == actual_data[0]["name"]
        for data in actual_data:
            data.pop("_id")
        assert actual_data == [
            {
                'name': 'test_schedule_action',
                'schedule_time': {'value': '2024-08-06T09:00:00.000+0530', 'parameter_type': 'value'},
                'timezone': 'UTC',
                'schedule_action': 'test_pyscript',
                'response_text': 'action scheduled',
                'params_list': [
                    {
                        '_cls': 'CustomActionRequestParameters',
                        'key': 'param_key',
                        'encrypt': False,
                        'value': 'param_1',
                        'parameter_type': 'value'
                    }
                ],
                'dispatch_bot_response': True
            }
        ]

    def test_add_schedule_action_duplicate(self):
        bot = "testbot"
        user = "testuser"
        expected_data = {
            "name": "test_schedule_action",
            "schedule_time": {"value": "2024-08-06T09:00:00.000+0530", "parameter_type": "value"},
            "timezone": None,
            "schedule_action": "test_pyscript",
            "response_text": "action scheduled",
            "params_list": [],
            "dispatch_bot_response": True
        }

        processor = MongoProcessor()
        with pytest.raises(AppException, match="Action exists!"):
            processor.add_schedule_action(expected_data, bot, user)

    def test_add_schedule_action_with_empty_name(self):
        bot = "testbot"
        user = "testuser"
        expected_data = {
            "name": "",
            "schedule_time": {"value": "2024-08-06T09:00:00.000+0530", "parameter_type": "value"},
            "timezone": None,
            "schedule_action": "test_pyscript",
            "response_text": "action scheduled",
            "params_list": [],
            "dispatch_bot_response": True
        }

        processor = MongoProcessor()
        with pytest.raises(Exception, match="Schedule action name can not be empty"):
            scheduled_acition = ScheduleActionRequest(**expected_data)
            processor.add_schedule_action(scheduled_acition, bot, user)

    def test_add_schedule_action_with_no_schedule_action(self):
        bot = "testbot"
        user = "testuser"
        expected_data = {
            "name": "test_schedule_action",
            "schedule_time": {"value": "2024-08-06T09:00:00.000+0530", "parameter_type": "value"},
            "timezone": None,
            "schedule_action": None,
            "response_text": "action scheduled",
            "params_list": [],
            "dispatch_bot_response": True
        }

        processor = MongoProcessor()
        with pytest.raises(Exception, match="Schedule action can not be empty, it is needed to execute on schedule time"):
            scheduled_acition = ScheduleActionRequest(**expected_data)
            processor.add_schedule_action(scheduled_acition.dict(), bot, user)

    def test_update_schedule_action_schedule_time(self):
        bot = "testbot"
        user = "testuser"
        expected_data = {
            "name": "test_schedule_action",
            "schedule_time": {"value": "2024-08-07T09:00:00.000+0530", "parameter_type": "value"},
            "timezone": None,
            "schedule_action": "test_pyscript",
            "response_text": "action scheduled",
            "params_list": [],
            "dispatch_bot_response": True
        }

        processor = MongoProcessor()
        processor.update_schedule_action(expected_data, bot, user)
        actual_data = list(processor.list_schedule_action(bot))
        assert expected_data.get("schedule_time").get("value") == actual_data[0]["schedule_time"]["value"]

    def test_update_schedule_action_scheduled_action(self):
        bot = "testbot"
        user = "testuser"
        expected_data = {
            "name": "test_schedule_action",
            "schedule_time": {"value": "2024-08-06T09:00:00.000+0530", "parameter_type": "value"},
            "timezone": None,
            "schedule_action": "test_pyscript_new",
            "response_text": "action scheduled",
            "params_list": [],
            "dispatch_bot_response": True
        }

        processor = MongoProcessor()
        processor.update_schedule_action(expected_data, bot, user)

        actual_data = list(processor.list_schedule_action(bot))
        assert expected_data.get("name") == actual_data[0]["name"]
        assert expected_data.get("schedule_action") == actual_data[0]["schedule_action"]

    def test_update_schedule_action_params_list(self):
        bot = "testbot"
        user = "testuser"
        expected_data = {
            "name": "test_schedule_action",
            "schedule_time": {"value": "2024-08-06T09:00:00.000+0530", "parameter_type": "value"},
            "timezone": None,
            "schedule_action": "test_pyscript_new",
            "response_text": "action scheduled",
            "params_list": [
                {
                    "key": "updated_key",
                    "value": "param_2",
                    "parameter_type": "value",
                }
            ],
            "dispatch_bot_response": True
        }

        processor = MongoProcessor()
        processor.update_schedule_action(expected_data, bot, user)

        actual_data = list(processor.list_schedule_action(bot))
        assert expected_data.get("name") == actual_data[0]["name"]
        assert expected_data.get("schedule_action") == actual_data[0]["schedule_action"]
        for data in actual_data:
            data.pop("_id")
        assert actual_data == [
            {
                'name': 'test_schedule_action',
                'schedule_time': {'value': '2024-08-06T09:00:00.000+0530', 'parameter_type': 'value'},
                'timezone': 'UTC',
                'schedule_action': 'test_pyscript_new',
                'response_text': 'action scheduled',
                'params_list': [
                    {
                        '_cls': 'CustomActionRequestParameters',
                        'key': 'updated_key',
                        'encrypt': False,
                        'value': 'param_2',
                        'parameter_type': 'value'
                    }
                ],
                'dispatch_bot_response': True
            }
        ]

    def test_update_schedule_action_schedule_time_param_type(self):
        bot = "testbot"
        user = "testuser"
        expected_data = {
            "name": "test_schedule_action",
            "schedule_time": {"value": "delivery_time", "parameter_type": "slot"},
            "timezone": None,
            "schedule_action": "test_pyscript",
            "response_text": "action scheduled",
            "params_list": [],
            "dispatch_bot_response": True
        }

        processor = MongoProcessor()
        processor.update_schedule_action(expected_data, bot, user)
        actual_data = list(processor.list_schedule_action(bot))
        assert "slot" == actual_data[0]["schedule_time"]["parameter_type"]
        assert "delivery_time" == actual_data[0]["schedule_time"]["value"]

    def test_get_schedule_action_by_name(self):
        name = "test_schedule_action"
        bot = "testbot"
        user = "testuser"
        processor = MongoProcessor()
        action = processor.get_schedule_action(bot, name)
        assert action is not None

    def test_get_schedule_action_by_name_not_exists(self):
        name = "test_schedule_action_not_exisits"
        bot = "testbot"
        user = "testuser"
        processor = MongoProcessor()
        action = processor.get_schedule_action(bot, name)
        assert action is None

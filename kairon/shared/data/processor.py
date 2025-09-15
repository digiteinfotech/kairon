import csv
import itertools
import re
import shutil

import ujson as json
import os
import uuid
from collections import ChainMap
from copy import deepcopy
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from typing import Text, Dict, List, Any, Optional
from urllib.parse import urljoin

from bson import ObjectId
from loguru import logger

import networkx as nx
import yaml
from fastapi import File, HTTPException
from loguru import logger as logging
from mongoengine import Document
from mongoengine.errors import DoesNotExist
from mongoengine.errors import NotUniqueError
from mongoengine.queryset.visitor import Q
from pandas import DataFrame
from pydantic import ValidationError, create_model
from rasa.shared.constants import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_DATA_PATH,
    DEFAULT_DOMAIN_PATH,
    INTENT_MESSAGE_PREFIX,
    DEFAULT_NLU_FALLBACK_INTENT_NAME,
)
from rasa.shared.core.constants import (
    RULE_SNIPPET_ACTION_NAME,
    DEFAULT_INTENTS,
    DEFAULT_SLOT_NAMES,
    MAPPING_TYPE,
    SlotMappingType, ACTION_LISTEN_NAME,
)
from rasa.shared.core.domain import SessionConfig
from rasa.shared.core.events import ActionExecuted, UserUttered, ActiveLoop
from rasa.shared.core.events import SlotSet
from rasa.shared.core.slots import CategoricalSlot, FloatSlot
from rasa.shared.core.training_data.story_writer.yaml_story_writer import (
    YAMLStoryWriter,
)
from rasa.shared.core.training_data.structures import Checkpoint, RuleStep
from rasa.shared.core.training_data.structures import STORY_START
from rasa.shared.core.training_data.structures import StoryGraph, StoryStep
from rasa.shared.importers.rasa import Domain
from rasa.shared.nlu.constants import TEXT
from rasa.shared.nlu.training_data.message import Message
from rasa.shared.nlu.training_data.training_data import TrainingData
from rasa.shared.utils.io import read_config_file
from werkzeug.utils import secure_filename

from kairon.api import models
from kairon.exceptions import AppException
from kairon.shared.actions.data_objects import (
    HttpActionConfig,
    HttpActionRequestBody,
    ActionServerLogs,
    Actions,
    SlotSetAction,
    FormValidationAction,
    EmailActionConfig,
    GoogleSearchAction,
    JiraAction,
    ZendeskAction,
    PipedriveLeadsAction,
    SetSlots,
    HubspotFormsAction,
    HttpActionResponse,
    SetSlotsFromResponse,
    CustomActionRequestParameters,
    KaironTwoStageFallbackAction,
    QuickReplies,
    RazorpayAction,
    PromptAction,
    LlmPrompt,
    FormSlotSet,
    DatabaseAction,
    DbQuery,
    PyscriptActionConfig,
    WebSearchAction,
    UserQuestion, CustomActionParameters,
    LiveAgentActionConfig, CallbackActionConfig, ScheduleAction, CustomActionDynamicParameters, ScheduleActionType,
    ParallelActionConfig,
)
from kairon.shared.actions.models import (
    ActionType,
    HttpRequestContentType,
    ActionParameterType,
    DbQueryValueType,
)
from kairon.shared.data.audit.data_objects import AuditLogData
from kairon.shared.importer.processor import DataImporterLogProcessor
from kairon.shared.metering.constants import MetricType
from kairon.shared.metering.metering_processor import MeteringProcessor
from kairon.shared.models import (
    StoryEventType,
    TemplateType,
    StoryStepType,
    HttpContentType,
    StoryType,
    LlmPromptSource, CognitionDataType, FlowTagType,
)
from kairon.shared.plugins.factory import PluginFactory
from kairon.shared.utils import Utility, StoryValidator
from .collection_processor import DataProcessor
from .constant import (
    DOMAIN,
    SESSION_CONFIG,
    STORY_EVENT,
    REGEX_FEATURES,
    LOOKUP_TABLE,
    TRAINING_EXAMPLE,
    RESPONSE,
    ENTITY,
    SLOTS,
    UTTERANCE_TYPE,
    CUSTOM_ACTIONS,
    REQUIREMENTS,
    EVENT_STATUS,
    COMPONENT_COUNT,
    SLOT_TYPE,
    DEFAULT_NLU_FALLBACK_RULE,
    DEFAULT_NLU_FALLBACK_RESPONSE,
    DEFAULT_ACTION_FALLBACK_RESPONSE,
    ENDPOINT_TYPE,
    TOKEN_TYPE,
    KAIRON_TWO_STAGE_FALLBACK,
    DEFAULT_NLU_FALLBACK_UTTERANCE_NAME,
    ACCESS_ROLES,
    LogType,
    DEMO_REQUEST_STATUS, RE_VALID_NAME, LogTypes, STATUSES,
)
from .data_objects import (
    Responses,
    SessionConfigs,
    Configs,
    Endpoints,
    Entities,
    EntitySynonyms,
    TrainingExamples,
    Stories,
    Intents,
    Forms,
    LookupTables,
    RegexFeatures,
    Entity,
    EndPointBot,
    EndPointAction,
    EndPointHistory,
    Slots,
    StoryEvents,
    ModelDeployment,
    Rules,
    Utterances, BotSettings, ChatClientConfig, SlotMapping, KeyVault, EventConfig,
    MultiflowStories, MultiflowStoryEvents, MultiFlowStoryMetadata,
    Synonyms, Lookup, Analytics, ModelTraining, ConversationsHistoryDeleteLogs, DemoRequestLogs
)
from .action_serializer import ActionSerializer
from .data_validation import DataValidation
from .model_data_imporer import KRasaFileImporter, CustomRuleStep
from .utils import DataUtility
from ..callback.data_objects import CallbackConfig, CallbackLog, CallbackResponseType
from ..chat.broadcast.data_objects import MessageBroadcastLogs
from ..cognition.data_objects import CognitionSchema, CognitionData, ColumnMetadata
from ..constants import KaironSystemSlots, PluginTypes, EventClass, EXCLUDED_INTENTS, UploadHandlerClass
from ..content_importer.content_processor import ContentImporterLogProcessor
from ..custom_widgets.data_objects import CustomWidgets
from ..importer.data_objects import ValidationLogs
from ..live_agent.live_agent import LiveAgentHandler
from ..log_system.base import BaseLogHandler
from ..log_system.factory import LogHandlerFactory
from ..multilingual.data_objects import BotReplicationLogs
from ..test.data_objects import ModelTestingLogs
from ..upload_handler.upload_handler_log_processor import UploadHandlerLogProcessor


class MongoProcessor:
    """
    Class contains logic for saves, updates and deletes bot data in mongo database
    """

    async def upload_and_save(
            self,
            nlu: File,
            domain: File,
            stories: File,
            config: File,
            rules: File,
            http_action: File,
            multiflow_stories: File,
            bot_content: File,
            bot: Text,
            user: Text,
            overwrite: bool = True,
    ):
        """
        loads the training data into database

        :param nlu: nlu data
        :param domain: domain data
        :param stories: stories data
        :param rules: rules data
        :param http_action: http_actions data
        :param config: config data
        :param multiflow_stories: multiflow_stories data
        :param bot_content: bot_content data
        :param bot: bot id
        :param user: user id
        :param overwrite: whether to append or overwrite, default is overwite
        :return: None
        """
        training_file_loc = await DataUtility.save_training_files(
            nlu, domain, config, stories, rules, http_action, multiflow_stories, bot_content
        )
        await self.save_from_path(training_file_loc["root"], bot, overwrite, user)
        Utility.delete_directory(training_file_loc["root"])

    def download_files(self, bot: Text, user: Text, download_multiflow: bool = False):
        """
        create zip file containing download data

        :param bot: bot id
        :param user: user id
        :param download_multiflow: flag to download multiflow stories.
        :return: zip file path
        """
        nlu = self.load_nlu(bot)
        domain = self.load_domain(bot)
        stories = self.load_stories(bot)
        config = self.load_config(bot)
        chat_client_config = self.load_chat_client_config(bot, user)
        rules = self.get_rules_for_download(bot)
        if download_multiflow:
            multiflow_stories = self.load_linear_flows_from_multiflow_stories(bot)
            stories = stories.merge(multiflow_stories[0])
            rules = rules.merge(multiflow_stories[1])
        multiflow_stories = self.load_multiflow_stories_yaml(bot)
        bot_content = self.load_bot_content(bot)
        actions, other_collections = ActionSerializer.serialize(bot)
        return Utility.create_zip_file(
            nlu,
            domain,
            stories,
            config,
            bot,
            rules,
            actions,
            multiflow_stories,
            chat_client_config,
            bot_content,
            other_collections,
        )

    @staticmethod
    def get_slot_mapped_actions(bot: Text, slot: Text):
        """
        fetches list of Actions mapped to slot

        :return: list of action names
        """
        action_names = {}
        actions, _ = ActionSerializer.serialize(bot)

        action_lookup = {
            ActionType.http_action.value: MongoProcessor.is_slot_in_http_config,
            ActionType.slot_set_action.value: MongoProcessor.is_slot_in_slot_set_action_config,
            ActionType.email_action.value: MongoProcessor.is_slot_in_email_action_config,
            ActionType.google_search_action.value: MongoProcessor.is_slot_in_google_search_action_config,
            ActionType.zendesk_action.value: MongoProcessor.is_slot_in_zendesk_action_config,
            ActionType.jira_action.value: MongoProcessor.is_slot_in_jira_action_config,
            ActionType.pipedrive_leads_action.value: MongoProcessor.is_slot_in_pipedrive_leads_action_config,
            ActionType.prompt_action.value: MongoProcessor.is_slot_in_prompt_action_config,
            ActionType.web_search_action.value: MongoProcessor.is_slot_in_web_search_action_config,
            ActionType.razorpay_action.value: MongoProcessor.is_slot_in_razorpay_action_config,
            ActionType.pyscript_action.value: MongoProcessor.is_slot_in_pyscript_action_config,
            ActionType.database_action.value: MongoProcessor.is_slot_in_database_action_config,
            ActionType.callback_action.value: MongoProcessor.is_slot_in_callback_action_config,
            ActionType.schedule_action.value: MongoProcessor.is_slot_in_schedule_action_config,
        }
        actions_to_exclude = [ActionType.form_validation_action.value,
                              ActionType.live_agent_action.value,
                              ActionType.hubspot_forms_action.value,
                              ActionType.two_stage_fallback.value,
                              ActionType.parallel_action.value]
        for key, value in actions.items():
            if key in actions_to_exclude:
                continue
            fun = action_lookup[key]
            names = []
            for config in value:
                if fun(config, slot):
                    names.append(ActionSerializer.get_item_name(config))
            action_names.update({key: names})

        return action_names

    @staticmethod
    def is_slot_in_schedule_action_config(config: dict, slot: Text):
        if MongoProcessor.is_slot_in_field(config.get('schedule_time', {}), slot):
            return True

        params_list = config.get('params_list', [])
        for param in params_list:
            if MongoProcessor.is_slot_in_field(param, slot):
                return True

        return False

    @staticmethod
    def is_slot_in_callback_action_config(config: dict, slot: Text):
        if config.get('dynamic_url_slot_name') == slot:
            return True

        return False

    @staticmethod
    def is_slot_in_database_action_config(config: dict, slot: Text):
        payload = config.get('payload', [])
        for item in payload:
            if item.get('type') == 'from_slot' and item.get('value') == slot:
                return True

        set_slots = config.get('set_slots', [])
        for set_slot in set_slots:
            if set_slot.get('name') == slot:
                return True

        return False

    @staticmethod
    def is_slot_in_pyscript_action_config(config: dict, slot: Text):
        import re

        source_code = config.get('source_code', '')
        slot_pattern = re.compile(r'slot\[\s*[\'\"]{}[\'\"]\s*\]'.format(re.escape(slot)))
        slots_dict_pattern = re.compile(r'slots\s*=\s*\{{.*[\'\"]{}[\'\"]\s*:'.format(re.escape(slot)))

        if slot_pattern.search(source_code) or slots_dict_pattern.search(source_code):
            return True

        return False

    @staticmethod
    def is_slot_in_razorpay_action_config(config: dict, slot: Text):
        fields_to_check = ['api_key', 'api_secret', 'amount', 'currency', 'username', 'email', 'contact']

        for field in fields_to_check:
            if MongoProcessor.is_slot_in_field(config.get(field, {}), slot):
                return True

        notes = config.get('notes', [])
        for note in notes:
            if MongoProcessor.is_slot_in_field(note, slot):
                return True

        return False

    @staticmethod
    def is_slot_in_web_search_action_config(config: dict, slot: Text):
        set_slot = config.get("set_slot")
        if set_slot == slot:
            return True

        return False

    @staticmethod
    def is_slot_in_prompt_action_config(config: dict, slot: Text):
        user_question = config.get("user_question", {})
        if user_question.get('type') == "from_slot" and user_question.get('value') == slot:
            return True

        llm_prompts = config.get("llm_prompts", [])
        for prompt in llm_prompts:
            if prompt.get('source') == "slot" and prompt.get('data') == slot:
                return True

        set_slots = config.get("set_slots", [])
        for set_slot in set_slots:
            if set_slot.get('name') == slot:
                return True

        return False

    @staticmethod
    def is_slot_in_jira_action_config(config: dict, slot: Text):
        api_token = config.get("api_token", {})
        return MongoProcessor.is_slot_in_field(api_token, slot)

    @staticmethod
    def is_slot_in_pipedrive_leads_action_config(config: dict, slot: Text):
        api_token = config.get("api_token", {})
        metadata = config.get("metadata", {})

        if MongoProcessor.is_slot_in_field(api_token, slot):
            return True

        for value in metadata.values():
            if value == slot:
                return True

        return False

    @staticmethod
    def is_slot_in_google_search_action_config(config: dict, slot: Text):
        api_key = config.get("api_key", {})

        if MongoProcessor.is_slot_in_field(api_key, slot):
            return True

        if config.get("set_slot") == slot:
            return True

        return False

    @staticmethod
    def is_slot_in_slot_set_action_config(config: dict, slot: Text):
        set_slots = config.get("set_slots", [])
        for set_slot in set_slots:
            if set_slot.get('name') == slot:
                return True
        return False

    @staticmethod
    def is_slot_in_email_action_config(config: dict, slot: Text):
        smtp_userid = config.get("smtp_userid", {})
        smtp_password = config.get("smtp_password", {})
        from_email = config.get("from_email", {})
        to_email = config.get("to_email", {})
        custom_text = config.get("custom_text", {})

        return (
                MongoProcessor.is_slot_in_field(smtp_userid, slot) or
                MongoProcessor.is_slot_in_field(smtp_password, slot) or
                MongoProcessor.is_slot_in_field(from_email, slot) or
                MongoProcessor.is_slot_in_field(to_email, slot) or
                MongoProcessor.is_slot_in_field(custom_text, slot)
        )

    @staticmethod
    def is_slot_in_http_config(config: dict, slot: Text):
        headers = config.get("headers", [])
        params_list = config.get("params_list", [])
        set_slots = config.get("set_slots", [])

        for header in headers:
            if MongoProcessor.is_slot_in_field(header, slot):
                return True

        for param in params_list:
            if MongoProcessor.is_slot_in_field(param, slot):
                return True

        for set_slot in set_slots:
            if set_slot.get('name') == slot:
                return True

        return False

    @staticmethod
    def is_slot_in_zendesk_action_config(config: dict, slot: Text):
        api_token = config.get("api_token", {})
        return MongoProcessor.is_slot_in_field(api_token, slot)

    @staticmethod
    def is_slot_in_field(field: dict, slot: Text):
        return field.get('parameter_type') == "slot" and field.get('value') == slot

    async def apply_template(self, template: Text, bot: Text, user: Text):
        """
        apply use-case template

        :param template: use-case template name
        :param bot: bot id
        :param user: user id

        :return: None
        :raises: raise AppException
        """
        use_case_path = os.path.join("./template/use-cases", secure_filename(template))
        user = "sysadmin" if template else user
        if os.path.exists(use_case_path):
            await self.save_from_path(path=use_case_path, bot=bot, user=user)
        else:
            raise AppException("Invalid template!")

    async def save_from_path(
            self, path: Text, bot: Text, overwrite: bool = True, user="default"
    ):
        """
        saves training data file

        :param path: data directory path
        :param bot: bot id
        :param overwrite: append or overwrite, default is overwrite
        :param user: user id
        :return: None
        """
        from kairon.importer.validator.file_validator import TrainingDataValidator

        try:
            domain_path = os.path.join(path, DEFAULT_DOMAIN_PATH)
            training_data_path = os.path.join(path, DEFAULT_DATA_PATH)
            config_path = os.path.join(path, DEFAULT_CONFIG_PATH)
            actions_yml = os.path.join(path, "actions.yml")
            multiflow_stories_yml = os.path.join(path, "multiflow_stories.yml")
            bot_content_yml = os.path.join(path, "bot_content.yml")
            other_collections_yml = os.path.join(path, "other_collections.yml")
            importer = KRasaFileImporter.load_from_config(
                config_path=config_path,
                domain_path=domain_path,
                training_data_paths=training_data_path,
            )
            domain = importer.get_domain()
            story_graph = importer.get_stories()
            config = importer.get_config()
            nlu = importer.get_nlu_data(config.get("language"))
            actions = Utility.read_yaml(actions_yml)
            multiflow_stories = (
                Utility.read_yaml(multiflow_stories_yml)
                if multiflow_stories_yml
                else None
            )
            bot_content = (
                Utility.read_yaml(bot_content_yml)
                if bot_content_yml
                else None
            )
            other_collections = (
                Utility.read_yaml(other_collections_yml)
                if other_collections_yml
                else None
            )

            ActionSerializer.validate(bot, actions, other_collections)


            self.save_training_data(
                bot,
                user,
                config,
                domain,
                story_graph,
                nlu,
                actions,
                multiflow_stories,
                bot_content,
                other_collections=other_collections,
                overwrite=overwrite,
                what=REQUIREMENTS.copy() - {"chat_client_config"},
            )
        except Exception as e:
            logging.info(e)
            raise AppException(e)

    def save_training_data(
            self,
            bot: Text,
            user: Text,
            config: dict = None,
            domain: Domain = None,
            story_graph: StoryGraph = None,
            nlu: TrainingData = None,
            actions: dict = None,
            multiflow_stories: dict = None,
            bot_content: list = None,
            chat_client_config: dict = None,
            other_collections: dict = None,
            overwrite: bool = False,
            what: set = REQUIREMENTS.copy(),
            default_fallback_data: bool = False
    ):
        """
            Save various components of the bot's training data to the database. Components can include the bot's domain,
            stories, NLU data, actions, configuration, multiflow stories, bot content, and chat client configuration.

            Args:
                bot (Text): The unique identifier of the bot.
                user (Text): The identifier of the user making the request.
                config (dict, optional): Configuration settings for the bot.
                domain (Domain, optional): The domain data for the bot, defining intents, entities, slots, and actions.
                story_graph (StoryGraph, optional): Graph representation of the bot's stories and rules.
                nlu (TrainingData, optional): NLU training data for the bot, including intents, entities, and examples.
                actions (dict, optional): Action data for the bot, containing details of custom actions.
                multiflow_stories (dict, optional): Multi-step story flows used in complex conversations.
                bot_content (list, optional): Additional content for the bot, such as FAQs or responses.
                chat_client_config (dict, optional): Configuration settings specific to the chat client.
                other_collections (dict, optional): Other related data collections for extended functionalities.
                overwrite (bool, optional): If True, existing data will be overwritten; otherwise, new data is appended.
                what (set, optional): A set of data types to save, e.g., {"domain", "stories", "nlu"}.
                default_fallback_data (bool, optional): If True, default fallback data is included.

            Behavior:
                - Deletes the specified existing data if `overwrite` is True.
                - Saves each specified component in `what` to the database, invoking relevant helper functions for each data type.

            Raises:
                Exception: Raises exceptions if saving any component fails.

            """
        if overwrite:
            self.delete_bot_data(bot, user, what)

        if "actions" in what:
            #self.save_integrated_actions(actions, bot, user)
            ActionSerializer.deserialize(bot, user, actions, other_collections, overwrite)
        if "domain" in what:
            self.save_domain(domain, bot, user)
        if "stories" in what:
            self.save_stories(story_graph.story_steps, bot, user)
        if "nlu" in what:
            self.save_nlu(nlu, bot, user)
        if "rules" in what:
            self.save_rules(story_graph.story_steps, bot, user)
        if "config" in what:
            self.add_or_overwrite_config(config, bot, user, default_fallback_data)
        if "chat_client_config" in what:
            self.save_chat_client_config(chat_client_config, bot, user)
        if "multiflow_stories" in what:
            self.save_multiflow_stories(multiflow_stories, bot, user)
        if "bot_content" in what:
            self.save_bot_content(bot_content, bot, user)

    def apply_config(self, template: Text, bot: Text, user: Text):
        """
        apply config template

        :param template: template name
        :param bot: bot id
        :param user: user id
        :return: None
        :raises: AppException
        """
        config_path = os.path.join(
            "./template/config", secure_filename(template) + ".yml"
        )
        if os.path.exists(config_path):
            self.save_config(read_config_file(config_path), bot=bot, user=user)
        else:
            raise AppException("Invalid config!")

    def load_multiflow_stories_yaml(self, bot: Text):
        multiflow = (
            MultiflowStories.objects(bot=bot, status=True)
            .exclude("id", "bot", "user", "timestamp", "status")
            .to_json()
        )
        multiflow = json.loads(multiflow)
        return {"multiflow_story": multiflow}

    def load_bot_content(self, bot: Text):
        doc = BotSettings.objects(bot=bot).get().to_mongo().to_dict()
        bot_content = []
        if doc['llm_settings'].get('enable_faq'):
            bot_content = self.__prepare_cognition_data_for_bot(bot)
        return bot_content

    def __prepare_cognition_data_for_bot(self, bot: Text) -> List[Dict[str, Any]]:
        """
        Aggregate cognition data for a specific bot.
        This function queries the cognition schema database to get collections and metadata
        for a particular bot, and then queries the cognition data database to fetch content_type
        and data field values for each collection. It returns the aggregated data in the form
        of a list of dictionaries, where each dictionary contains collection, type, metadata,
        and data fields.
        :param bot: The ID of the bot for which to aggregate data.
        :return: A list of dictionaries containing aggregated data for the bot.
        """
        schema_results = CognitionSchema.objects(bot=bot).only("collection_name", "metadata")

        formatted_result = []
        for schema_result in schema_results:
            collection_name = schema_result.collection_name
            metadata = [{"column_name": meta.column_name,
                         "data_type": meta.data_type,
                         "enable_search": meta.enable_search,
                         "create_embeddings": meta.create_embeddings}
                        for meta in schema_result.metadata]

            if not metadata:
                type_value = "text"
            else:
                type_value = "json"

            collection_data = {
                "collection": collection_name,
                "type": type_value,
                "metadata": metadata,
                "data": []
            }

            data_results = CognitionData.objects(bot=bot, collection=collection_name).only("content_type", "data")
            entries = [d.data for d in data_results]
            if type_value == "json":
                entries = MongoProcessor.data_format_correction_cognition_data(entries, metadata)
            collection_data["data"] = entries

            formatted_result.append(collection_data)

        data_results_no_collection = CognitionData.objects(bot=bot, collection=None).only("content_type", "data")
        default_collection_data = {
            "collection": "Default",
            "type": "text",
            "metadata": [],
            "data": []
        }
        for data_result in data_results_no_collection:
            default_collection_data["data"].append(data_result.data)

        formatted_result.append(default_collection_data)

        return formatted_result

    def get_config_templates(self):
        """
        fetches list of available config template

        :return: config template list
        """
        files = Utility.list_files("./template/config")
        return [
            {"name": Path(file).stem, "config": read_config_file(file)}
            for file in files
        ]

    def delete_bot_data(self, bot: Text, user: Text, what=REQUIREMENTS.copy()):
        """
        deletes bot data

        :param bot: bot id
        :param user: user id
        :param what: training data that should be deleted
        :return: None
        """
        if "domain" in what:
            self.delete_domain(bot, user)
        if "stories" in what:
            self.delete_stories(bot, user)
        if "nlu" in what:
            self.delete_nlu(bot, user)
        if "config" in what:
            self.delete_config(bot, user)
        if "rules" in what:
            self.delete_rules(bot, user)
        if "actions" in what:
            self.delete_bot_actions(bot, user)
        if "multiflow_stories" in what:
            self.delete_multiflow_stories(bot, user)
        if "bot_content" in what:
            self.delete_bot_content(bot, user)

    def save_nlu(self, nlu: TrainingData, bot: Text, user: Text):
        """
        saves training examples

        :param nlu: nly data
        :param bot: bot id
        :param user: user id
        :return: None
        """
        self.__save_training_examples(nlu.training_examples, bot, user)
        self.__save_entity_synonyms(nlu.entity_synonyms, bot, user)
        self.__save_lookup_tables(nlu.lookup_tables, bot, user)
        self.__save_regex_features(nlu.regex_features, bot, user)

    def delete_nlu(self, bot: Text, user: Text):
        """
        soft deletes nlu data

        :param bot: bot id
        :param user: user id
        :return: None
        """
        Utility.hard_delete_document(
            [TrainingExamples, EntitySynonyms, LookupTables, RegexFeatures], bot=bot, user=user
        )

    def load_nlu(self, bot: Text) -> TrainingData:
        """
        loads nlu data for training

        :param bot: bot id
        :return: TrainingData object
        """
        training_examples = self.__prepare_training_examples(bot)
        entity_synonyms = self.__prepare_training_synonyms(bot)
        lookup_tables = self.__prepare_training_lookup_tables(bot)
        regex_features = self.__prepare_training_regex_features(bot)
        return TrainingData(
            training_examples=training_examples,
            entity_synonyms=entity_synonyms,
            lookup_tables=lookup_tables,
            regex_features=regex_features,
        )

    def save_domain(self, domain: Domain, bot: Text, user: Text):
        """
        saves domain data

        :param domain: domain data
        :param bot: bot id
        :param user: user id
        :return: None
        """
        self.__save_intents(domain.intent_properties, bot, user)
        self.__save_domain_entities(domain.entities, bot, user)
        actions = list(
            filter(
                lambda actions: not actions.startswith("utter_"), domain.user_actions
            )
        )
        # self.verify_actions_presence(actions, bot, user)
        self.__save_responses(domain.responses, bot, user)
        self.save_utterances(domain.responses.keys(), bot, user)
        self.__save_slots(domain.slots, bot, user)
        self.__save_forms(domain.forms, bot, user)
        self.__save_session_config(domain.session_config, bot, user)
        self.__save_slot_mapping(domain.slots, bot, user)

    def delete_domain(self, bot: Text, user: Text):
        """
        soft deletes domain data

        :param bot: bot id
        :param user: user id
        :return: None
        """
        Utility.hard_delete_document(
            [
                Intents,
                Entities,
                Forms,
                FormValidationAction,
                Responses,
                Slots,
                SlotMapping,
                Utterances,
            ],
            bot=bot,
            user=user
        )
        Utility.hard_delete_document([Actions], bot=bot, type=None, user=user)

    def load_domain(self, bot: Text, story_graphs: list[StoryGraph] = None ) -> Domain:
        """
        loads domain data for training

        :param bot: bot id
        :param story_graphs (optional)
        :return: dict of Domain objects
        """
        intent_properties = self.__prepare_training_intents_and_properties(bot)

        domain_dict = {
            DOMAIN.INTENTS.value: intent_properties,
            DOMAIN.ACTIONS.value: self.__prepare_training_actions(bot, story_graphs),
            DOMAIN.SLOTS.value: self.__prepare_training_slots(bot),
            DOMAIN.SESSION_CONFIG.value: self.__prepare_training_session_config(bot),
            DOMAIN.RESPONSES.value: self.__prepare_training_responses(bot),
            DOMAIN.FORMS.value: self.__prepare_training_forms(bot),
            DOMAIN.ENTITIES.value: self.__prepare_training_domain_entities(bot),
        }
        return Domain.from_dict(domain_dict)

    def save_stories(self, story_steps: List[StoryStep], bot: Text, user: Text):
        """
        saves stories data

        :param story_steps: stories data
        :param bot: bot id
        :param user: user id
        :return: None
        """
        self.__save_stories(story_steps, bot, user)

    def delete_stories(self, bot: Text, user: Text):
        """
        soft deletes stories

        :param bot: bot id
        :param user: user id
        :return: None
        """
        Utility.hard_delete_document([Stories], bot=bot, user=user)

    def load_stories(self, bot: Text) -> StoryGraph:
        """
        loads multiflow stories for training.
        Each multiflow story is divided into linear stories and segregated into either story or rule.

        :param bot: bot id
        :return: StoryGraph
        """
        return self.__prepare_training_story(bot)

    def delete_multiflow_stories(self, bot: Text, user: Text):
        """
        soft deletes stories
        :param bot: bot id
        :param user: user id
        :return: None
        """
        Utility.hard_delete_document([MultiflowStories], bot=bot, user=user)

    def delete_bot_content(self, bot: Text, user: Text):
        """
        soft deletes stories
        :param bot: bot id
        :param user: user id
        :return: None
        """
        Utility.hard_delete_document([CognitionSchema], bot=bot, user=user)
        Utility.hard_delete_document([CognitionData], bot=bot, user=user)

    def save_multiflow_stories(self, multiflow_stories: dict, bot: Text, user: Text):
        """
        saves multiflow stories data
        :param multiflow_stories: multiflow stories data
        :param bot: bot id
        :param user: user id
        :return: None
        """
        if multiflow_stories and multiflow_stories.get("multiflow_story"):
            self.__save_multiflow_stories(
                multiflow_stories["multiflow_story"], bot, user
            )

    def __save_cognition_schema(self, bot_content: list, bot: Text, user: Text):
        for data_item in bot_content:
            if data_item['collection'] != 'Default':
                existing_schema = CognitionSchema.objects(bot=bot, collection_name=data_item['collection']).first()
                if not existing_schema:
                    cognition_schema = CognitionSchema(
                        metadata=[ColumnMetadata(**md) for md in data_item['metadata']],
                        collection_name=data_item['collection'],
                        user=user,
                        bot=bot,
                        timestamp=datetime.utcnow()
                    )
                    cognition_schema.save()

    def __save_cognition_data(self, bot_content: list, bot: Text, user: Text):
        for data_item in bot_content:

            collection_name = data_item['collection']
            if collection_name == 'Default':
                collection_name = None

            if data_item['type'] == 'text':
                for text_data in data_item['data']:
                    cognition_data = CognitionData(
                        data=text_data,
                        content_type='text',
                        collection=collection_name,
                        user=user,
                        bot=bot
                    )
                    cognition_data.save()
            elif data_item['type'] == 'json':
                data_entries = data_item['data']
                metadata = data_item['metadata']
                data_entries = MongoProcessor.data_format_correction_cognition_data(data_entries, metadata)
                for json_data in data_entries:
                    cognition_data = CognitionData(
                        data=json_data,
                        content_type='json',
                        collection=collection_name,
                        user=user,
                        bot=bot
                    )
                    cognition_data.save()

    @staticmethod
    def data_format_correction_cognition_data(data_entries, metadata):
        convs = {
            m['column_name']: (
                int if m['data_type'] == 'int' else
                float if m['data_type'] == 'float' else
                str if m['data_type'] == 'str' else
                None
            )
            for m in metadata
        }
        return [
            {
                **e,
                **{
                    cname: (
                        convs[cname](e[cname][0] if isinstance(e[cname], list) and e[cname] else e[cname])
                        if e[cname] is not None and convs[cname] is not None else e[cname]
                    )
                    for cname in convs
                }
            }
            for e in data_entries
        ]

    def save_bot_content(self, bot_content: list, bot: Text, user: Text):
        """
        saves bot content data
        :param bot_content: bot content data
        :param bot: bot id
        :param user: user id
        :return: None
        """
        if bot_content:
            self.__save_cognition_schema(bot_content, bot, user)
            self.__save_cognition_data(bot_content, bot, user)

    def load_linear_flows_from_multiflow_stories(
            self, bot: Text
    ) -> (StoryGraph, StoryGraph):
        """
        loads multiflow stories for training.
        Each multiflow story is divided into linear stories and segregated into either story or rule.

        :param bot: bot id
        :return: Tuple with 2 StoryGraph objects, one each for Stories and Rules.
        """
        return self.__prepare_training_multiflow_story(bot)

    def __save_training_examples(self, training_examples, bot: Text, user: Text):
        if training_examples:
            new_examples = list(
                self.__extract_training_examples(training_examples, bot, user)
            )
            if new_examples:
                TrainingExamples.objects.insert(new_examples)

    def check_training_example_exists(self, text: Text, bot: Text):
        try:
            training_example = (
                TrainingExamples.objects(bot=bot, text=text, status=True)
                .get()
                .to_mongo()
                .to_dict()
            )
            data = {"is_exists": True, "intent": training_example["intent"]}
        except DoesNotExist as e:
            logging.info(e)
            data = {"is_exists": False, "intent": None}
        return data

    def __extract_entities(self, entities):
        for entity in entities:
            entity_data = Entity(
                start=entity[ENTITY.START.value],
                end=entity[ENTITY.END.value],
                value=entity[ENTITY.VALUE.value],
                entity=entity[ENTITY.ENTITY.value],
            )
            entity_data.clean()
            yield entity_data

    def __extract_training_examples(self, training_examples, bot: Text, user: Text):
        saved_training_examples, _ = self.get_all_training_examples(bot)
        for training_example in training_examples:
            if (
                    "text" in training_example.data
                    and str(training_example.data["text"]).lower()
                    not in saved_training_examples
            ):
                training_data = TrainingExamples()
                training_data.intent = str(
                    training_example.data[TRAINING_EXAMPLE.INTENT.value]
                )
                training_data.text = training_example.data["text"]
                training_data.bot = bot
                training_data.user = user
                if "entities" in training_example.data:
                    training_data.entities = list(
                        self.__extract_entities(
                            training_example.data[TRAINING_EXAMPLE.ENTITIES.value]
                        )
                    )
                training_data.clean()
                yield training_data

    def __fetch_all_synonyms_value(self, bot: Text):
        synonyms = list(
            EntitySynonyms.objects(bot=bot, status=True).values_list("value")
        )
        return synonyms

    def __fetch_all_synonyms_name(self, bot: Text):
        synonyms = list(Synonyms.objects(bot=bot, status=True).values_list("name"))
        return synonyms

    def __extract_synonyms(self, synonyms, bot: Text, user: Text):
        saved_synonyms = self.__fetch_all_synonyms_value(bot)
        saved_synonym_names = self.__fetch_all_synonyms_name(bot)
        for key, value in synonyms.items():
            if value not in saved_synonym_names:
                self.add_synonym(value, bot, user)
                saved_synonym_names.append(value)
            if key not in saved_synonyms:
                new_synonym = EntitySynonyms(bot=bot, name=value, value=key, user=user)
                new_synonym.clean()
                yield new_synonym

    def __save_entity_synonyms(self, entity_synonyms, bot: Text, user: Text):
        if entity_synonyms:
            new_synonyms = list(self.__extract_synonyms(entity_synonyms, bot, user))
            if new_synonyms:
                EntitySynonyms.objects.insert(new_synonyms)

    def fetch_synonyms(self, bot: Text, status=True):
        """
        fetches entity synonyms

        :param bot: bot id
        :param status: active or inactive, default is active
        :return: yield name, value
        """
        synonyms = Synonyms.objects(bot=bot, status=status)
        for synonym in synonyms:
            yield {"_id": synonym.id.__str__(), "synonym": synonym.name}

    def fetch_synonyms_values(self, bot: Text, status=True):
        """
        fetches entity synonyms

        :param bot: bot id
        :param status: active or inactive, default is active
        :return: yield name, value
        """
        entitySynonyms = EntitySynonyms.objects(bot=bot, status=status)
        for entitySynonym in entitySynonyms:
            yield {
                "_id": entitySynonym.id.__str__(),
                "synonym": entitySynonym.name,
                "value": entitySynonym.value,
            }

    def __prepare_training_synonyms(self, bot: Text):
        synonyms = list(self.fetch_synonyms_values(bot))
        training_synonyms = {}
        for synonym in synonyms:
            training_synonyms[synonym["value"]] = synonym["synonym"]
        return training_synonyms

    def __prepare_entities(self, entities):
        for entity in entities:
            yield entity.to_mongo().to_dict()

    def fetch_training_examples(self, bot: Text, status=True):
        """
        fetches training examples

        :param bot: bot id
        :param status: active or inactive, default is active
        :return: Message List
        """
        trainingExamples = TrainingExamples.objects(bot=bot, status=status)
        for trainingExample in trainingExamples:
            message = Message()
            message.data = {
                TRAINING_EXAMPLE.INTENT.value: trainingExample.intent,
                TEXT: trainingExample.text,
            }
            if trainingExample.entities:
                message.data[TRAINING_EXAMPLE.ENTITIES.value] = list(
                    self.__prepare_entities(trainingExample.entities)
                )
            yield message

    def __prepare_training_examples(self, bot: Text):
        return list(self.fetch_training_examples(bot))

    def __fetch_all_lookups(self, bot: Text):
        lookup_tables = list(Lookup.objects(bot=bot, status=True).values_list("name"))

        return lookup_tables

    def __fetch_all_lookup_values(self, bot: Text):
        lookup_tables = list(
            LookupTables.objects(bot=bot, status=True).values_list("value")
        )

        return lookup_tables

    def __extract_lookup_tables(self, lookup_tables, bot: Text, user: Text):
        saved_lookup = self.__fetch_all_lookup_values(bot)
        saved_lookup_names = self.__fetch_all_lookups(bot)
        for lookup_table in lookup_tables:
            name = lookup_table[LOOKUP_TABLE.NAME.value]
            if name not in saved_lookup_names:
                self.add_lookup(name, bot, user)
                saved_lookup_names.append(name)
            for element in lookup_table[LOOKUP_TABLE.ELEMENTS.value]:
                if element not in saved_lookup:
                    new_lookup = LookupTables(
                        name=name, value=element, bot=bot, user=user
                    )
                    new_lookup.clean()
                    yield new_lookup

    def __save_lookup_tables(self, lookup_tables, bot: Text, user: Text):
        if lookup_tables:
            new_lookup = list(self.__extract_lookup_tables(lookup_tables, bot, user))
            if new_lookup:
                LookupTables.objects.insert(new_lookup)

    def fetch_lookup_tables(self, bot: Text, status=True):
        """
        fetches lookup table

        :param bot: bot id
        :param status: user id
        :return: yield dict of lookup tables
        """
        lookup_tables = LookupTables.objects(bot=bot, status=status).aggregate(
            [{"$group": {"_id": "$name", "elements": {"$push": "$value"}}}]
        )
        for lookup_table in lookup_tables:
            yield {
                LOOKUP_TABLE.NAME.value: lookup_table["_id"],
                LOOKUP_TABLE.ELEMENTS.value: lookup_table["elements"],
            }

    def __prepare_training_lookup_tables(self, bot: Text):
        return list(self.fetch_lookup_tables(bot))

    def __fetch_all_regex_patterns(self, bot: Text):
        regex_patterns = list(
            RegexFeatures.objects(bot=bot, status=True).values_list("pattern")
        )
        return regex_patterns

    def __extract_regex_features(self, regex_features, bot: Text, user: Text):
        saved_regex_patterns = self.__fetch_all_regex_patterns(bot)
        for regex_feature in regex_features:
            if regex_feature["pattern"] not in saved_regex_patterns:
                regex_data = RegexFeatures(**regex_feature)
                regex_data.bot = bot
                regex_data.user = user
                regex_data.clean()
                yield regex_data

    def __save_regex_features(self, regex_features, bot: Text, user: Text):
        if regex_features:
            new_regex_patterns = list(
                self.__extract_regex_features(regex_features, bot, user)
            )
            if new_regex_patterns:
                RegexFeatures.objects.insert(new_regex_patterns)

    def fetch_regex_features(self, bot: Text, status=True):
        """
        fetches regular expression for entities

        :param bot: bot id
        :param status: active or inactive, default is active
        :return: yield dict of regular expression
        """
        regex_features = RegexFeatures.objects(bot=bot, status=status)
        for regex_feature in regex_features:
            yield {
                REGEX_FEATURES.NAME.value: regex_feature["name"],
                REGEX_FEATURES.PATTERN.value: regex_feature["pattern"],
            }

    def __prepare_training_regex_features(self, bot: Text):
        return list(self.fetch_regex_features(bot))

    def __extract_intents(self, intents, bot: Text, user: Text):
        """
        If intents does not have use_entities flag set in the domain.yml, then
        use_entities is assumed to be True by rasa.
        """
        saved_intents = self.__prepare_training_intents(bot)
        for intent in intents:
            if intent.strip().lower() not in saved_intents and intent.strip().lower() not in EXCLUDED_INTENTS:
                entities = intents[intent].get("used_entities")
                use_entities = True if entities else False
                new_intent = Intents(
                    name=intent, bot=bot, user=user, use_entities=use_entities
                )
                new_intent.clean()
                yield new_intent

    def __save_intents(self, intents, bot: Text, user: Text):
        if intents:
            new_intents = list(self.__extract_intents(intents, bot, user))
            if new_intents:
                Intents.objects.insert(new_intents)

    def fetch_intents(self, bot: Text, status=True):
        """
        fetches intents

        :param bot: bot id
        :param status: active or inactive, default is active
        :return: List of intents
        """
        intents = Intents.objects(bot=bot, status=status).values_list("name")
        return list(intents)

    def __prepare_training_intents(self, bot: Text):
        intents = self.fetch_intents(bot)
        return intents

    def __prepare_training_intents_and_properties(self, bot: Text):
        intent_properties = []
        use_entities_true = {DOMAIN.USE_ENTITIES_KEY.value: True}
        use_entities_false = {DOMAIN.USE_ENTITIES_KEY.value: False}
        for intent in Intents.objects(bot=bot, status=True):
            intent_property = {}
            used_entities = intent["use_entities"]
            intent_property[intent["name"]] = (
                use_entities_true.copy() if used_entities else use_entities_false.copy()
            )
            intent_properties.append(intent_property)
        return intent_properties

    def __extract_domain_entities(self, entities: List[str], bot: Text, user: Text):
        saved_entities = self.__prepare_training_domain_entities(bot=bot)
        for entity in entities:
            if entity.strip().lower() not in saved_entities:
                new_entity = Entities(name=entity, bot=bot, user=user)
                new_entity.clean()
                yield new_entity

    def __save_domain_entities(self, entities: List[str], bot: Text, user: Text):
        if entities:
            new_entities = list(self.__extract_domain_entities(entities, bot, user))
            if new_entities:
                Entities.objects.insert(new_entities)

    def fetch_domain_entities(self, bot: Text, status=True):
        """
        fetches domain entities

        :param bot: bot id
        :param status: active or inactive, default is active
        :return: list of entities
        """
        entities = Entities.objects(bot=bot, status=status).values_list("name")
        return list(entities)

    def __prepare_training_domain_entities(self, bot: Text):
        entities = self.fetch_domain_entities(bot)
        return entities

    def __extract_forms(self, forms, bot: Text, user: Text):
        saved_forms = list(self.fetch_forms(bot, status=True) or [])
        saved_form_names = {
            key for name_mapping in saved_forms for key in name_mapping.keys()
        }
        for form, mappings in forms.items():
            if form not in saved_form_names:
                yield self.__save_form_logic(
                    form, mappings.get("required_slots") or {}, bot, user
                )

    def __save_form_logic(self, name, slots, bot, user):
        if Utility.is_exist(
                Actions, raise_error=False, name=f"validate_{name}", bot=bot, status=True
        ):
            try:
                form_validation_action = Actions.objects(
                    name__iexact=f"validate_{name}", bot=bot, status=True
                ).get()
                form_validation_action.type = ActionType.form_validation_action.value
                form_validation_action.save()
            except Exception as e:
                print(e)


        self.__check_for_form_and_action_existance(bot, name)
        form = Forms(name=name, required_slots=slots, bot=bot, user=user)
        form.clean()
        return form

    def __save_slot_mapping(self, slots, bot, user):
        slots_name_list = self.__fetch_slot_names(bot)
        existing_slot_mappings = SlotMapping.objects(bot=bot, status=True).values_list(
            "slot"
        )
        mapping_to_save = []
        for slot in slots:
            items = vars(slot)
            slot_name = items["name"]
            slot_mapping = items["mappings"]
            if slot_mapping and slot_name in slots_name_list:
                if slot_name not in existing_slot_mappings:
                    for mapping in slot_mapping:
                        form_name = None
                        if mapping.get("conditions"):
                            form_name = mapping["conditions"][0]["active_loop"]
                        mapping_to_save.append(
                            SlotMapping(
                                slot=slot_name, mapping=mapping, bot=bot, user=user, form_name=form_name
                            )
                        )
        if mapping_to_save:
            SlotMapping.objects.insert(mapping_to_save)

    def __save_forms(self, forms, bot: Text, user: Text):
        if forms:
            new_forms = list(self.__extract_forms(forms, bot, user))
            if new_forms:
                Forms.objects.insert(new_forms)

    def fetch_forms(self, bot: Text, status=True):
        """
        fetches form

        :param bot: bot id
        :param status: active or inactive, default is active
        :return: list of forms
        """
        forms = Forms.objects(bot=bot, status=status)
        for form in forms:
            yield {form.name: {"required_slots": form.required_slots}}

    def __prepare_training_forms(self, bot: Text):
        forms = list(self.fetch_forms(bot))
        return dict(ChainMap(*forms))

    def __extract_actions(self, actions, bot: Text, user: Text):
        saved_actions = self.__prepare_training_actions(bot)
        for action in actions:
            if action.strip().lower() not in saved_actions:
                self.__check_for_form_and_action_existance(bot, action)
                new_action = Actions(name=action, bot=bot, user=user)
                new_action.clean()
                yield new_action

    def __check_for_form_and_action_existance(self, bot: Text, name: Text, action_type: Optional[ActionType] = None):
        if action_type == ActionType.form_validation_action.value:
            return
        Utility.is_exist(Actions,
                         raise_error=True,
                         exp_message=f"Action with the name '{name}' already exists",
                         name=name, bot=bot, status=True)
        Utility.is_exist(Forms,
                         raise_error=True,
                         exp_message=f"Form with the name '{name}' already exists",
                         name=name, bot=bot, status=True)

    # def verify_actions_presence(self, actions: list[str], bot: str, user: str):
    #     if actions:
    #         found_names = Actions.objects(name__in=actions, bot=bot, user=user).values_list('name')
    #         for action in actions:
    #             if action not in found_names:
    #                 raise AppException(f"Action [{action}] not present in actions.yml")

    def __save_actions(self, actions, bot: Text, user: Text):
        if actions:
            new_actions = list(self.__extract_actions(actions, bot, user))
            if new_actions:
                Actions.objects.insert(new_actions)

    def fetch_actions(self, bot: Text, status=True):
        """
        fetches actions

        :param bot: bot id
        :param status: user id
        :return: list of actions
        """
        actions = Actions.objects(bot=bot, status=status).values_list("name")
        actions_list = list(actions)

        for story in Stories.objects(bot=bot, status=status):
            for event in story.events:
                if event.name == 'action_listen':
                    if 'action_listen' not in actions_list:
                        actions_list.append('action_listen')

        for story in MultiflowStories.objects(bot=bot, status=status):
            for event in story.events:
                if event.step.name == 'stop_flow_action' and 'stop_flow_action' not in actions_list:
                    actions_list.append('stop_flow_action')

        return actions_list

    def __prepare_training_actions(self, bot: Text, story_graphs: list[StoryGraph] = None)-> list[str]:
        actions = self.fetch_actions(bot)
        if not story_graphs:
            return actions

        validate_actions = [action for action in actions if action.startswith("validate_")]
        required_actions =MongoProcessor.extract_action_names_from_story_graph(story_graphs)
        return [action for action in actions if action in required_actions] + validate_actions


    @staticmethod
    def extract_action_names_from_story_graph(story_graphs: list[StoryGraph]) -> list:
        action_names = set()
        for story_graph in story_graphs:
            for step in story_graph.story_steps:
                for event in step.events:
                    if isinstance(event, ActionExecuted):
                        action_names.add(event.action_name)
        return list(action_names)

    def __extract_session_config(
            self, session_config: SessionConfig, bot: Text, user: Text
    ):
        return SessionConfigs(
            sesssionExpirationTime=session_config.session_expiration_time,
            carryOverSlots=session_config.carry_over_slots,
            bot=bot,
            user=user,
        )

    def __save_session_config(
            self, session_config: SessionConfig, bot: Text, user: Text
    ):
        try:
            if session_config:
                try:
                    session = SessionConfigs.objects().get(bot=bot)
                    session.session_expiration_time = (
                        session_config.session_expiration_time
                    )
                    session.carryOverSlots = True
                    session.user = user
                except DoesNotExist:
                    session = self.__extract_session_config(session_config, bot, user)
                session.save()

        except NotUniqueError as e:
            logging.info(e)
            raise AppException("Session Config already exists for the bot")
        except Exception as e:
            logging.info(e)
            raise AppException("Internal Server Error")

    def fetch_session_config(self, bot: Text):
        """
        fetches session config

        :param bot: bot id
        :return: SessionConfigs object
        """
        try:
            session_config = SessionConfigs.objects().get(bot=bot)
        except DoesNotExist as e:
            logging.info(e)
            session_config = None
        return session_config

    def __prepare_training_session_config(self, bot: Text):
        session_config = self.fetch_session_config(bot)
        if session_config:
            return {
                SESSION_CONFIG.SESSION_EXPIRATION_TIME.value: session_config.sesssionExpirationTime,
                SESSION_CONFIG.CARRY_OVER_SLOTS.value: session_config.carryOverSlots,
            }
        else:
            default_session = SessionConfig.default()
            return {
                SESSION_CONFIG.SESSION_EXPIRATION_TIME.value: default_session.session_expiration_time,
                SESSION_CONFIG.CARRY_OVER_SLOTS.value: default_session.carry_over_slots,
            }

    def __extract_response_value(self, values: List[Dict], key, bot: Text, user: Text):
        saved_responses = self.fetch_list_of_response(bot)
        for value in values:
            if value not in saved_responses:
                response = Responses()
                response.name = key.strip()
                response.bot = bot
                response.user = user
                r_type, r_object = DataUtility.prepare_response(value)
                if RESPONSE.Text.value == r_type:
                    response.text = r_object
                elif RESPONSE.CUSTOM.value == r_type:
                    response.custom = r_object
                response.clean()
                yield response

    def __extract_response(self, responses, bot: Text, user: Text):
        responses_result = []
        for key, values in responses.items():
            responses_to_saved = list(
                self.__extract_response_value(values, key, bot, user)
            )
            responses_result.extend(responses_to_saved)
        return responses_result

    def __save_responses(self, responses, bot: Text, user: Text):
        if responses:
            new_responses = self.__extract_response(responses, bot, user)
            if new_responses:
                Responses.objects.insert(new_responses)

    def save_utterances(self, utterances, bot: Text, user: Text):
        if utterances:
            new_utterances = []
            existing_utterances = Utterances.objects(bot=bot, status=True).values_list(
                "name"
            )
            for utterance in utterances:
                if utterance.strip().lower() not in existing_utterances:
                    new_utter = Utterances(name=utterance, bot=bot, user=user)
                    new_utter.clean()
                    new_utterances.append(new_utter)
            if new_utterances:
                Utterances.objects.insert(new_utterances)

    def __prepare_response_Text(self, texts: List[Dict]):
        for text in texts:
            yield text

    def fetch_responses(self, bot: Text, status=True):
        """
        fetches utterances

        :param bot: bot id
        :param status: active or inactive, default is True
        :return: yield bot utterances
        """
        responses = Responses.objects(bot=bot, status=status).aggregate(
            [
                {
                    "$group": {
                        "_id": "$name",
                        "texts": {"$push": "$text"},
                        "customs": {"$push": "$custom"},
                    }
                }
            ]
        )
        for response in responses:
            key = response["_id"]
            value = list(self.__prepare_response_Text(response["texts"]))
            if response["customs"]:
                value.extend(response["customs"])
            yield {key: value}

    def __prepare_training_responses(self, bot: Text):
        responses = dict(ChainMap(*list(self.fetch_responses(bot))))
        return responses

    def __fetch_slot_names(self, bot: Text):
        saved_slots = list(Slots.objects(bot=bot, status=True).values_list("name"))
        return saved_slots

    def __extract_slots(self, slots, bot: Text, user: Text):
        """
        If influence_conversation flag is not present for a slot, then it is assumed to be
        set to false by rasa.
        """
        slots_name_list = self.__fetch_slot_names(bot)
        slots_name_list.extend(list(DEFAULT_SLOT_NAMES))
        entities = self.__prepare_training_domain_entities(bot=bot)
        for slot in slots:
            items = vars(deepcopy(slot))
            if items["name"].strip().lower() not in slots_name_list:
                if items["name"].strip().lower() not in entities:
                    self.add_entity(items["name"], bot, user, False)
                items["type"] = slot.type_name
                items["value_reset_delay"] = items["_value_reset_delay"]
                items.pop("_value_reset_delay")
                items["bot"] = bot
                items["user"] = user
                items.pop("_value")
                items.pop("mappings")
                new_slot = Slots._from_son(items)
                new_slot.clean()
                yield new_slot

    def __save_slots(self, slots, bot: Text, user: Text):
        self.add_system_required_slots(bot, user)
        if slots:
            new_slots = list(self.__extract_slots(slots, bot, user))
            if new_slots:
                Slots.objects.insert(new_slots)

    def add_system_required_slots(self, bot: Text, user: Text):
        non_conversational_slots = {
            KaironSystemSlots.kairon_action_response.value, KaironSystemSlots.bot.value,
            KaironSystemSlots.order.value, KaironSystemSlots.flow_reply.value,
            KaironSystemSlots.http_status_code.value, KaironSystemSlots.payment.value
        }
        for slot in [s for s in KaironSystemSlots if s.value in non_conversational_slots]:
            initial_value = None
            if slot.value == KaironSystemSlots.bot.value:
                initial_value = bot

            self.add_slot(
                {
                    "name": slot,
                    "type": "any",
                    "initial_value": initial_value,
                    "influence_conversation": False,
                },
                bot,
                user,
                raise_exception_if_exists=False,
                is_default = True
            )

        for slot in [s for s in KaironSystemSlots if s.value not in non_conversational_slots]:
            slot_type = SLOT_TYPE.LIST.value if slot == KaironSystemSlots.media_ids.value else "text"
            self.add_slot(
                {
                    "name": slot,
                    "type": slot_type,
                    "initial_value": None,
                    "influence_conversation": True,
                },
                bot,
                user,
                raise_exception_if_exists=False,
                is_default=True
            )

    def fetch_slots(self, bot: Text, status=True):
        """
        fetches slots

        :param bot: bot id
        :param status: active or inactive, default is active
        :return: list of slots
        """
        slots = Slots.objects(bot=bot, status=status)
        return list(slots)

    def __prepare_training_slots(self, bot: Text):
        slots = self.fetch_slots(bot)
        slots_mapping = dict(ChainMap(*list(self.__prepare_slot_mappings(bot))))
        results = []
        for slot in slots:
            key = slot.name
            if slot.type == FloatSlot.type_name:
                value = {
                    SLOTS.INITIAL_VALUE.value: slot.initial_value,
                    SLOTS.VALUE_RESET_DELAY.value: slot.value_reset_delay,
                    SLOTS.MIN_VALUE.value: slot.min_value,
                    SLOTS.MAX_VALUE.value: slot.max_value,
                }
            elif slot.type == CategoricalSlot.type_name:
                value = {
                    SLOTS.INITIAL_VALUE.value: slot.initial_value,
                    SLOTS.VALUE_RESET_DELAY.value: slot.value_reset_delay,
                    SLOTS.VALUES.value: slot.values,
                }
            else:
                value = {
                    SLOTS.INITIAL_VALUE.value: slot.initial_value,
                    SLOTS.VALUE_RESET_DELAY.value: slot.value_reset_delay,
                }
            value[SLOTS.TYPE.value] = slot.type
            value["influence_conversation"] = slot.influence_conversation
            value["mappings"] = self.__prepare_autofill(slots_mapping.get(key, []), key)
            results.append({key: value})
        return dict(ChainMap(*results))

    def __prepare_autofill(self, mappings: list, slot_name: str):
        auto_fill = False
        new_mappings = mappings.copy()
        for mapping in new_mappings:
            if (
                    mapping.get(MAPPING_TYPE) == SlotMappingType.FROM_ENTITY.value
                    and mapping.get("entity") == slot_name
            ):
                auto_fill = True
                break

        if not auto_fill:
            new_mappings.append(
                {MAPPING_TYPE: SlotMappingType.FROM_ENTITY.value, "entity": slot_name}
            )
        return new_mappings

    def __extract_story_events(self, events):
        for event in events:
            if isinstance(event, UserUttered):
                entities = [
                    Entity(
                        start=entity.get("start"),
                        end=entity.get("end"),
                        value=entity.get("value"),
                        entity=entity.get("entity"),
                    )
                    for entity in event.entities
                ]
                story_event = StoryEvents(
                    type=event.type_name, name=event.intent_name, entities=entities
                )
                story_event.clean()
                yield story_event
            elif isinstance(event, ActionExecuted):
                story_event = StoryEvents(type=event.type_name, name=event.action_name)
                story_event.clean()
                yield story_event
            elif isinstance(event, ActiveLoop):
                if event.name == None:
                    story_event = StoryEvents(type=event.type_name, name=event.name)
                    story_event.clean()
                    yield story_event
            elif isinstance(event, SlotSet):
                story_event = StoryEvents(
                    type=event.type_name, name=event.key, value=event.value
                )
                story_event.clean()
                yield story_event

    def __fetch_story_block_names(self, bot: Text):
        saved_stories = list(
            Stories.objects(bot=bot, status=True).values_list("block_name")
        )
        return saved_stories

    def __extract_story_step(self, story_steps, bot: Text, user: Text):
        saved_stories = self.__fetch_story_block_names(bot)
        for story_step in story_steps:
            if (
                    not isinstance(story_step, RuleStep)
                    and story_step.block_name.strip().lower() not in saved_stories
            ):
                story_events = list(self.__extract_story_events(story_step.events))
                template_type = DataUtility.get_template_type(story_step)
                story = Stories(
                    block_name=story_step.block_name,
                    start_checkpoints=[
                        start_checkpoint.name
                        for start_checkpoint in story_step.start_checkpoints
                    ],
                    end_checkpoints=[
                        end_checkpoint.name
                        for end_checkpoint in story_step.end_checkpoints
                    ],
                    events=story_events,
                    template_type=template_type,
                )
                story.bot = bot
                story.user = user
                story.clean()
                yield story

    def __save_stories(self, story_steps, bot: Text, user: Text):
        if story_steps:
            new_stories = list(self.__extract_story_step(story_steps, bot, user))
            if new_stories:
                Stories.objects.insert(new_stories)

    def __prepare_training_story_events(self, events, timestamp, bot):
        for event in events:
            if event.type == UserUttered.type_name:
                entities = []
                if event.entities:
                    entities = [
                        {
                            "start": entity["start"],
                            "end": entity["end"],
                            "value": entity["value"],
                            "entity": entity["entity"],
                        }
                        for entity in event.entities
                    ]

                intent = {
                    STORY_EVENT.NAME.value: event.name,
                    STORY_EVENT.CONFIDENCE.value: 1.0,
                }
                parse_data = {
                    "text": INTENT_MESSAGE_PREFIX + event.name,
                    "intent": intent,
                    "intent_ranking": [intent],
                    "entities": entities,
                }
                yield UserUttered(
                    text=event.name,
                    intent=intent,
                    entities=entities,
                    parse_data=parse_data,
                    timestamp=timestamp,
                )
            elif event.type == ActionExecuted.type_name:
                yield ActionExecuted(action_name=event.name, timestamp=timestamp)
            elif event.type == ActiveLoop.type_name:
                yield ActiveLoop(name=event.name, timestamp=timestamp)
            elif event.type == SlotSet.type_name:
                yield SlotSet(key=event.name, value=event.value, timestamp=timestamp)

    def __retrieve_existing_components(self, bot):
        component_dict = {
            StoryStepType.intent.value: dict(
                Intents.objects(bot=bot, status=True).values_list("name", "id")
            ),
            StoryStepType.slot.value: dict(
                Slots.objects(bot=bot, status=True).values_list("name", "id")
            ),
            StoryStepType.bot.value: dict(
                Utterances.objects(bot=bot, status=True).values_list("name", "id")
            ),
            StoryStepType.http_action.value: dict(
                HttpActionConfig.objects(bot=bot, status=True).values_list(
                    "action_name", "id"
                )
            ),
            StoryStepType.email_action.value: dict(
                EmailActionConfig.objects(bot=bot, status=True).values_list(
                    "action_name", "id"
                )
            ),
            StoryStepType.google_search_action.value: dict(
                GoogleSearchAction.objects(bot=bot, status=True).values_list(
                    "name", "id"
                )
            ),
            StoryStepType.slot_set_action.value: dict(
                SlotSetAction.objects(bot=bot, status=True).values_list("name", "id")
            ),
            StoryStepType.jira_action.value: dict(
                JiraAction.objects(bot=bot, status=True).values_list("name", "id")
            ),
            StoryStepType.form_action.value: dict(
                FormValidationAction.objects(bot=bot, status=True).values_list(
                    "name", "id"
                )
            ),
            StoryStepType.zendesk_action.value: dict(
                ZendeskAction.objects(bot=bot, status=True).values_list("name", "id")
            ),
            StoryStepType.pipedrive_leads_action.value: dict(
                PipedriveLeadsAction.objects(bot=bot, status=True).values_list(
                    "name", "id"
                )
            ),
            StoryStepType.hubspot_forms_action.value: dict(
                HubspotFormsAction.objects(bot=bot, status=True).values_list(
                    "name", "id"
                )
            ),
            StoryStepType.two_stage_fallback_action.value: dict(
                KaironTwoStageFallbackAction.objects(bot=bot, status=True).values_list(
                    "name", "id"
                )
            ),
            StoryStepType.razorpay_action.value: dict(
                RazorpayAction.objects(bot=bot, status=True).values_list("name", "id")
            ),
            StoryStepType.prompt_action.value: dict(
                PromptAction.objects(bot=bot, status=True).values_list("name", "id")
            ),
            StoryStepType.web_search_action.value: dict(
                WebSearchAction.objects(bot=bot, status=True).values_list("name", "id")
            ),
            StoryStepType.live_agent_action.value: dict(
                LiveAgentActionConfig.objects(bot=bot, status=True).values_list(
                    "name", "id"
                )
            ),
            StoryStepType.callback_action.value: dict(
                CallbackActionConfig.objects(bot=bot, status=True).values_list(
                    "name", "id"
                )
            ),
        }
        return component_dict

    def __updated_events(self, bot, events, existing_components):
        for event in events:
            step = event["step"]
            connections = event.get("connections", [])
            step_type = step.get("type")
            step_name_lower = step.get("name").lower()

            step["component_id"] = (
                existing_components.get(step_type, {}).get(step_name_lower).__str__()
            )
            if connections:
                for connection in connections:
                    connection_name_lower = connection["name"].lower()
                    connection["component_id"] = (
                        existing_components.get(connection["type"], {})
                        .get(connection_name_lower)
                        .__str__()
                    )
        return events

    def __fetch_multiflow_story_block_names(self, bot: Text):
        multiflow_stories = list(
            MultiflowStories.objects(bot=bot, status=True).values_list("block_name")
        )
        return multiflow_stories

    def __extract_multiflow_story_step(self, multiflow_stories, bot: Text, user: Text):
        existing_multiflow_stories = self.__fetch_multiflow_story_block_names(bot)
        existing_stories = self.__fetch_story_block_names(bot)
        existing_rules = self.fetch_rule_block_names(bot)
        existing_flows = set(
            existing_multiflow_stories + existing_stories + existing_rules
        )
        existing_components = self.__retrieve_existing_components(bot)
        for story in multiflow_stories:
            if story["block_name"].strip().lower() not in existing_flows:
                story["events"] = self.__updated_events(
                    bot, story["events"], existing_components
                )
                multiflow_story = MultiflowStories(**story)
                multiflow_story.bot = bot
                multiflow_story.user = user
                multiflow_story.flow_tags = story.get("flow_tags", [FlowTagType.chatbot_flow.value])
                multiflow_story.clean()
                yield multiflow_story

    def __save_multiflow_stories(self, multiflow_stories, bot: Text, user: Text):
        new_multiflow_stories = list(
            self.__extract_multiflow_story_step(multiflow_stories, bot, user)
        )
        if new_multiflow_stories:
            MultiflowStories.objects.insert(new_multiflow_stories)

    def __prepare_training_multiflow_story_events(self, events, metadata, timestamp):
        roots = []
        leaves = []
        leaves_node_id = set()
        paths = []
        events = StoryValidator.get_graph(events)
        metadata = (
            {item["node_id"]: item["flow_type"] for item in metadata}
            if metadata
            else {}
        )
        for node in events.nodes:
            if events.in_degree(node) == 0:
                roots.append(node)
            elif events.out_degree(node) == 0:
                leaves_node_id.add(node.node_id)
                leaves.append(node)

        for root in roots:
            for leaf in leaves:
                for path in nx.all_simple_paths(events, root, leaf):
                    paths.append(path)
        for path in paths:
            flow_type = "STORY"
            story_events = []
            for event in path:
                if event.node_id in leaves_node_id and metadata:
                    flow_type = metadata.get(event.node_id, StoryType.story.value)
                if event.step_type == StoryStepType.intent.value:
                    intent = {
                        STORY_EVENT.NAME.value: event.name,
                        STORY_EVENT.CONFIDENCE.value: 1.0,
                    }
                    parse_data = {
                        "text": INTENT_MESSAGE_PREFIX + event.name,
                        "intent": intent,
                        "intent_ranking": [intent],
                        "entities": [],
                    }
                    story_events.append(
                        UserUttered(
                            text=event.name,
                            intent=intent,
                            parse_data=parse_data,
                            timestamp=timestamp,
                            entities=[],
                        )
                    )
                elif event.step_type == StoryStepType.slot.value:
                    story_events.append(
                        SlotSet(key=event.name, value=event.value, timestamp=timestamp)
                    )
                elif event.step_type == StoryStepType.stop_flow_action.value:
                    story_events.append(
                        ActionExecuted(action_name=ACTION_LISTEN_NAME, timestamp=timestamp)
                    )
                else:
                    story_events.append(
                        ActionExecuted(action_name=event.name, timestamp=timestamp)
                    )
            if flow_type == StoryType.rule.value:
                story_events.insert(
                    0,
                    ActionExecuted(
                        action_name=RULE_SNIPPET_ACTION_NAME, timestamp=timestamp
                    ),
                )
            yield story_events, flow_type

    def fetch_multiflow_stories(self, bot: Text, status=True):
        """
        fetches stories
        :param bot: bot id
        :param status: active or inactive, default is active
        :return: list of stories
        """
        return list(MultiflowStories.objects(bot=bot, status=status))

    def fetch_stories(self, bot: Text, status=True):
        """
        fetches stories

        :param bot: bot id
        :param status: active or inactive, default is active
        :return: list of stories
        """
        return list(Stories.objects(bot=bot, status=status))

    def __prepare_training_story_step(self, bot: Text):
        for story in Stories.objects(bot=bot, status=True):
            story_events = list(
                self.__prepare_training_story_events(
                    story.events, datetime.now().timestamp(), bot
                )
            )
            yield StoryStep(
                block_name=story.block_name,
                events=story_events,
                start_checkpoints=[
                    Checkpoint(start_checkpoint)
                    for start_checkpoint in story.start_checkpoints
                ],
                end_checkpoints=[
                    Checkpoint(end_checkpoints)
                    for end_checkpoints in story.end_checkpoints
                ],
            )

    def __prepare_training_multiflow_story_step(self, bot: Text):
        flows = {StoryType.story.value: StoryStep, StoryType.rule.value: RuleStep}
        for story in MultiflowStories.objects(bot=bot, status=True):
            if FlowTagType.chatbot_flow.value not in story.flow_tags:
                continue
            events = story.to_mongo().to_dict()["events"]
            metadata = (
                story.to_mongo().to_dict()["metadata"] if story["metadata"] else {}
            )
            stories = list(
                self.__prepare_training_multiflow_story_events(
                    events, metadata, datetime.now().timestamp()
                )
            )
            count = 1
            for story_events, flow_type in stories:
                block_name = f"{story.block_name}_{count}"
                yield flows[flow_type](
                    block_name=block_name,
                    events=story_events,
                    start_checkpoints=[
                        Checkpoint(start_checkpoint)
                        for start_checkpoint in story.start_checkpoints
                    ],
                    end_checkpoints=[
                        Checkpoint(end_checkpoints)
                        for end_checkpoints in story.end_checkpoints
                    ],
                )
                count += 1

    def __prepare_training_story(self, bot: Text):
        return StoryGraph(list(self.__prepare_training_story_step(bot)))

    def __prepare_training_multiflow_story(self, bot: Text):
        from rasa.shared.core.training_data.structures import RuleStep

        rule_steps = []
        story_steps = []
        for flow in list(self.__prepare_training_multiflow_story_step(bot)):
            if isinstance(flow, RuleStep):
                rule_steps.append(flow)
            else:
                story_steps.append(flow)
        return StoryGraph(story_steps), StoryGraph(rule_steps)

    def save_config(self, configs: dict, bot: Text, user: Text):
        """
        saves bot configuration

        :param configs: configuration
        :param bot: bot id
        :param user: user id
        :return: config unique id
        """
        from kairon.importer.validator.file_validator import TrainingDataValidator

        try:
            config_errors = TrainingDataValidator.validate_rasa_config(configs)
            if config_errors:
                raise AppException(config_errors[0])
            return self.add_or_overwrite_config(configs, bot, user)
        except Exception as e:
            logging.info(e)
            raise AppException(e)

    def add_or_overwrite_config(self, configs: dict, bot: Text, user: Text, default_fallback_data: bool = False):
        """
        saves bot configuration

        :param configs: configuration
        :param bot: bot id
        :param user: user id
        :param default_fallback_data: If True, default fallback data is included
        :return: config unique id
        """
        for custom_component in Utility.environment["model"]["pipeline"]["custom"]:
            self.__insert_bot_id(configs, bot, custom_component)
        self.add_default_fallback_config(configs, bot, user, default_fallback_data)
        try:
            config_obj = Configs.objects().get(bot=bot)
        except DoesNotExist:
            config_obj = Configs()

        config_obj.bot = bot
        config_obj.user = user
        config_obj.pipeline = configs["pipeline"]
        config_obj.language = configs["language"]
        config_obj.policies = configs["policies"]

        return config_obj.save().id.__str__()

    def __insert_bot_id(self, config_obj: dict, bot: Text, component_name: Text):
        gpt_classifier = next(
            (comp for comp in config_obj["pipeline"] if comp["name"] == component_name),
            None,
        )
        if gpt_classifier:
            gpt_classifier["bot_id"] = bot

    def save_component_properties(self, configs: dict, bot: Text, user: Text):
        """
        Set properties (epoch and fallback) in the bot pipeline and policies configurations

        :param configs: nlu fallback threshold, action fallback threshold and fallback action, epochs for policies.
        :param bot: bot id
        :param user: user id
        :return: config unique id
        """
        nlu_confidence_threshold = configs.get("nlu_confidence_threshold")
        action_fallback_threshold = configs.get("action_fallback_threshold")
        action_fallback = configs.get("action_fallback")
        nlu_epochs = configs.get("nlu_epochs")
        response_epochs = configs.get("response_epochs")
        ted_epochs = configs.get("ted_epochs")
        max_history = configs.get("ted_epochs") if "max_history" in configs else 5

        if (
                not nlu_epochs
                and not response_epochs
                and not ted_epochs
                and not nlu_confidence_threshold
                and not action_fallback
        ):
            raise AppException("At least one field is required")

        present_config = self.load_config(bot)
        if nlu_confidence_threshold:
            fallback_classifier_idx = next(
                (
                    idx
                    for idx, comp in enumerate(present_config["pipeline"])
                    if comp["name"] == "FallbackClassifier"
                ),
                None,
            )
            if fallback_classifier_idx:
                del present_config["pipeline"][fallback_classifier_idx]
            diet_classifier_idx = next(
                (
                    idx
                    for idx, comp in enumerate(present_config["pipeline"])
                    if comp["name"] == "DIETClassifier"
                ),
                None,
            )
            fallback = {
                "name": "FallbackClassifier",
                "threshold": nlu_confidence_threshold,
            }
            present_config["pipeline"].insert(diet_classifier_idx + 1, fallback)
            rule_policy = next(
                (
                    comp
                    for comp in present_config["policies"]
                    if "RulePolicy" in comp["name"]
                ),
                {},
            )

            if not rule_policy:
                present_config["policies"].append(rule_policy)
            rule_policy["name"] = "RulePolicy"

        if action_fallback:
            action_fallback_threshold = (
                action_fallback_threshold if action_fallback_threshold else 0.3
            )
            if action_fallback == "action_default_fallback":
                utterance_exists = Utility.is_exist(
                    Responses,
                    raise_error=False,
                    bot=bot,
                    status=True,
                    name__iexact="utter_default",
                )
                if not utterance_exists:
                    raise AppException("Utterance utter_default not defined")
            else:
                utterance_exists = Utility.is_exist(
                    Responses,
                    raise_error=False,
                    bot=bot,
                    status=True,
                    name__iexact=action_fallback,
                )
                if not (
                        utterance_exists
                        or Utility.is_exist(
                    Actions,
                    raise_error=False,
                    bot=bot,
                    status=True,
                    name__iexact=action_fallback,
                )
                ):
                    raise AppException(
                        f"Action fallback {action_fallback} does not exists"
                    )
            fallback = next(
                (
                    comp
                    for comp in present_config["policies"]
                    if "RulePolicy" in comp["name"]
                ),
                {},
            )

            if not fallback:
                present_config["policies"].append(fallback)
            fallback["name"] = "RulePolicy"
            fallback["core_fallback_action_name"] = action_fallback
            fallback["core_fallback_threshold"] = action_fallback_threshold
            fallback["max_history"] = max_history

        nlu_fallback = next(
            (
                comp
                for comp in present_config["pipeline"]
                if comp["name"] == "FallbackClassifier"
            ),
            {},
        )
        action_fallback = next(
            (
                comp
                for comp in present_config["policies"]
                if "RulePolicy" in comp["name"]
            ),
            {},
        )
        if nlu_fallback.get("threshold") and action_fallback.get(
                "core_fallback_threshold"
        ):
            if nlu_fallback["threshold"] < action_fallback["core_fallback_threshold"]:
                raise AppException(
                    "Action fallback threshold should always be smaller than nlu fallback threshold"
                )

        Utility.add_or_update_epoch(present_config, configs)
        self.save_config(present_config, bot, user)

    def list_epoch_and_fallback_config(self, bot: Text):
        config = self.load_config(bot)
        selected_config = {}
        nlu_fallback = next(
            (
                comp
                for comp in config["pipeline"]
                if comp["name"] == "FallbackClassifier"
            ),
            {},
        )
        action_fallback = next(
            (comp for comp in config["policies"] if "RulePolicy" in comp["name"]), {}
        )
        ted_policy = next(
            (comp for comp in config["policies"] if comp["name"] == "TEDPolicy"), {}
        )
        diet_classifier = next(
            (comp for comp in config["pipeline"] if comp["name"] == "DIETClassifier"),
            {},
        )
        response_selector = next(
            (comp for comp in config["pipeline"] if comp["name"] == "ResponseSelector"),
            {},
        )
        selected_config["nlu_confidence_threshold"] = (
            nlu_fallback.get("threshold") if nlu_fallback.get("threshold") else None
        )
        selected_config["action_fallback"] = action_fallback.get(
            "core_fallback_action_name"
        )
        selected_config["action_fallback_threshold"] = (
            action_fallback.get("core_fallback_threshold")
            if action_fallback.get("core_fallback_threshold")
            else None
        )
        selected_config["ted_epochs"] = ted_policy.get("epochs")
        selected_config["nlu_epochs"] = diet_classifier.get("epochs")
        selected_config["response_epochs"] = response_selector.get("epochs")
        return selected_config

    def delete_config(self, bot: Text, user: Text):
        """
        soft deletes bot training configuration

        :param bot: bot id
        :param user: user id
        :return: None
        """
        Utility.hard_delete_document([Configs], bot=bot, user=user)

    def fetch_configs(self, bot: Text):
        """
        fetches bot training configuration is exist otherwise load default

        :param bot: bot id
        :return: dict
        """
        try:
            configs = Configs.objects().get(bot=bot)
        except DoesNotExist as e:
            logging.info(e)
            configs = Configs._from_son(
                read_config_file(
                    Utility.environment["model"]["train"][
                        "default_model_training_config_path"
                    ]
                )
            )
        return configs

    def load_config(self, bot: Text):
        """
        loads bot training configuration for training

        :param bot: bot id
        :return: dict
        """
        configs = self.fetch_configs(bot)
        config_dict = configs.to_mongo().to_dict()
        return {
            key: config_dict[key]
            for key in config_dict
            if key not in ["bot", "user", "timestamp", "status", "_id"]
        }

    def load_chat_client_config(self, bot: Text, user: Text):
        """
        loads chat client configuration for training

        :param bot: bot id
        :param user: user id
        :return: dict
        """
        config = self.get_chat_client_config(bot, user)
        config_dict = config.to_mongo().to_dict()
        config_dict["config"].pop("headers", None)
        config_dict["config"].pop("multilingual", None)
        config_dict.pop("_id", None)
        config_dict.pop("bot", None)
        config_dict.pop("status", None)
        config_dict.pop("user", None)
        config_dict.pop("timestamp", None)
        return config_dict

    def add_training_data(
            self,
            training_data: List[models.TrainingData],
            bot: Text,
            user: Text,
            is_integration: bool,
    ):
        """
        adds a list of intents

        :param intents: intents list to be added
        :param bot: bot id
        :param user: user id
        :param is_integration: integration status
        :return: intent id
        """
        overall_response = [{}]
        training_data_added = {}
        for data in training_data:
            status = {}
            try:
                intent_id = self.add_intent(
                    text=data.intent, bot=bot, user=user, is_integration=is_integration
                )
                status[data.intent] = intent_id
            except AppException as e:
                status[data.intent] = str(e)

            story_name = "path_" + data.intent
            utterance = "utter_" + data.intent
            events = [
                {"name": data.intent, "type": StoryStepType.intent.value},
                {"name": utterance, "type": StoryStepType.bot.value},
            ]
            try:
                doc_id = self.add_complex_story(
                    story={
                        "name": story_name,
                        "steps": events,
                        "type": "STORY",
                        "template_type": TemplateType.CUSTOM.value,
                    },
                    bot=bot,
                    user=user,
                )
                status["story"] = doc_id
            except AppException as e:
                status["story"] = str(e)
            try:
                status_message = list(
                    self.add_training_example(
                        data.training_examples, data.intent, bot, user, is_integration
                    )
                )
                status["training_examples"] = status_message
                training_examples = []
                for training_data_add_status in status_message:
                    if training_data_add_status["_id"]:
                        training_examples.append(training_data_add_status["text"])
                training_data_added[data.intent] = training_examples
            except AppException as e:
                status["training_examples"] = str(e)

            try:
                utterance_id = self.add_text_response(
                    data.response, utterance, bot, user
                )
                status["responses"] = utterance_id
            except AppException as e:
                status["responses"] = str(e)
            overall_response.append(status)
        return overall_response, training_data_added

    def add_intent(self, text: Text, bot: Text, user: Text, is_integration: bool):
        """
        adds new intent

        :param text: intent name
        :param bot: bot id
        :param user: user id
        :param is_integration: integration status
        :return: intent id
        """
        if Utility.check_empty_string(text):
            raise AppException("Intent Name cannot be empty or blank spaces")

        if text and Utility.special_match(text):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        Utility.is_exist(
            Intents,
            exp_message="Intent already exists!",
            name__iexact=text.strip(),
            bot=bot,
            status=True,
        )
        saved = (
            Intents(name=text, bot=bot, user=user, is_integration=is_integration)
            .save()
            .to_mongo()
            .to_dict()
        )
        return saved["_id"].__str__()

    def get_intents(self, bot: Text):
        """
        fetches list of intent

        :param bot: bot id
        :return: intent list
        """
        intents = Intents.objects(bot=bot, status=True).order_by("-timestamp")
        return list(self.__prepare_document_list(intents, "name"))

    def add_training_example(
            self,
            examples: List[Text],
            intent: Text,
            bot: Text,
            user: Text,
            is_integration: bool,
    ):
        """
        adds training examples for bot

        :param examples: list of training example
        :param intent: intent name
        :param bot: bot id
        :param user: user id
        :param is_integration: integration status
        :return: list training examples id
        """
        if Utility.check_empty_string(intent):
            raise AppException("Intent cannot be empty or blank spaces")
        if not Utility.is_exist(
                Intents, raise_error=False, name__iexact=intent, bot=bot, status=True
        ):
            self.add_intent(intent, bot, user, is_integration)

        for example in examples:
            try:
                if Utility.check_empty_string(example):
                    raise AppException(
                        "Training Example cannot be empty or blank spaces"
                    )
                text, entities = DataUtility.extract_text_and_entities(example.strip())
                intent_for_example = Utility.retrieve_field_values(
                    TrainingExamples,
                    field=TrainingExamples.intent.name,
                    text__iexact=text,
                    bot=bot,
                    status=True,
                )
                if intent_for_example:
                    yield {
                        "text": example,
                        "message": f"Training Example exists in intent: {intent_for_example}",
                        "_id": None,
                    }
                else:
                    if entities:
                        new_entities = self.save_entities_and_add_slots(
                            entities, bot, user
                        )
                    else:
                        new_entities = None

                    training_example = TrainingExamples(
                        intent=intent,
                        text=text,
                        entities=new_entities,
                        bot=bot,
                        user=user,
                    )

                    saved = training_example.save().to_mongo().to_dict()
                    new_entities_as_dict = []
                    if new_entities:
                        new_entities_as_dict = [
                            json.loads(e.to_json()) for e in new_entities
                        ]
                    yield {
                        "text": DataUtility.prepare_nlu_text(
                            text, new_entities_as_dict
                        ),
                        "_id": saved["_id"].__str__(),
                        "message": "Training Example added",
                    }
            except Exception as e:
                yield {"text": example, "_id": None, "message": str(e)}

    def add_or_move_training_example(
            self, examples: List[Text], intent: Text, bot: Text, user: Text
    ):
        """
        Moves list of training examples to existing intent.
        If training examples does not exists, then it is added to the specified intent.

        :param examples: list of training example
        :param intent: intent name
        :param bot: bot id
        :param user: user id
        :return: list training examples id
        """
        if not Utility.is_exist(
                Intents, raise_error=False, name__iexact=intent, bot=bot, status=True
        ):
            raise AppException("Intent does not exists")

        for example in examples:
            if Utility.check_empty_string(example):
                yield {
                    "text": example,
                    "_id": None,
                    "message": "Training Example cannot be empty or blank spaces",
                }
                continue

            text, entities = DataUtility.extract_text_and_entities(example.strip())
            new_entities_as_dict = []
            try:
                training_example = TrainingExamples.objects(
                    text__iexact=text, bot=bot, status=True
                ).get()
                training_example.intent = intent
                message = "Training Example moved"
                if training_example.entities:
                    new_entities_as_dict = [
                        json.loads(e.to_json()) for e in training_example.entities
                    ]
            except DoesNotExist:
                if entities:
                    new_entities = self.save_entities_and_add_slots(entities, bot, user)
                    new_entities_as_dict = [
                        json.loads(e.to_json()) for e in new_entities
                    ]
                else:
                    new_entities = None
                training_example = TrainingExamples(
                    intent=intent, text=text, entities=new_entities, bot=bot, user=user
                )
                message = "Training Example added"
            saved = training_example.save().to_mongo().to_dict()

            yield {
                "text": DataUtility.prepare_nlu_text(text, new_entities_as_dict),
                "_id": saved["_id"].__str__(),
                "message": message,
            }

    def save_entities_and_add_slots(self, entities, bot: Text, user: Text):
        ext_entity = [ent["entity"] for ent in entities]
        self.__save_domain_entities(ext_entity, bot=bot, user=user)
        self.__add_slots_from_entities(ext_entity, bot, user)
        new_entities = list(self.__extract_entities(entities))
        return new_entities

    def edit_training_example(
            self, id: Text, example: Text, intent: Text, bot: Text, user: Text
    ):
        """
        update training example

        :param id: training example id
        :param example: new training example
        :param intent: intent name
        :param bot: bot id
        :param user: user id
        :return: None
        """
        try:
            if Utility.check_empty_string(example):
                raise AppException("Training Example cannot be empty or blank spaces")
            text, entities = DataUtility.extract_text_and_entities(example.strip())
            intent_for_example = Utility.retrieve_field_values(
                TrainingExamples,
                field=TrainingExamples.intent.name,
                text__iexact=text,
                entities=entities,
                bot=bot,
                status=True,
            )
            if intent_for_example:
                raise AppException(
                    f"Training Example exists in intent: {intent_for_example}"
                )
            training_example = TrainingExamples.objects(bot=bot, intent=intent).get(
                id=id
            )
            training_example.user = user
            training_example.text = text
            if entities:
                training_example.entities = list(self.__extract_entities(entities))
            else:
                training_example.entities = None
            training_example.timestamp = datetime.utcnow()
            training_example.save()
        except DoesNotExist:
            raise AppException("Invalid training example!")

    def search_training_examples(self, search: Text, bot: Text, limit: int = 5):
        """
        search the training examples

        :param search: search text
        :param bot: bot id
        :param limit: number of search results
        :return: yields tuple of intent name, training example
        """
        results = (
            TrainingExamples.objects(bot=bot, status=True)
            .search_text(search)
            .order_by("$text_score")
            .limit(limit)
        )
        for result in results:
            yield {"intent": result.intent, "text": result.text}

    def get_intents_and_training_examples(self, bot: Text):
        """
        Gets all the intents and associated training examples

        :param bot: bot id
        :return: intents and list of training examples against them
        """
        intents_and_training_examples_dict = {}
        intents = self.get_intents(bot)
        intents_and_training_examples = list(
            TrainingExamples.objects(bot=bot, status=True).aggregate(
                [
                    {
                        "$group": {
                            "_id": "$intent",
                            "training_examples": {
                                "$push": {
                                    "text": "$text",
                                    "entities": {"$ifNull": ["$entities", None]},
                                    "_id": {"$toString": "$_id"},
                                }
                            },
                        }
                    },
                    {"$project": {"_id": 0, "intent": "$_id", "training_examples": 1}},
                ]
            )
        )
        for data in intents_and_training_examples:
            intents_and_training_examples_dict[data["intent"]] = data[
                "training_examples"
            ]

        for intent in intents:
            if not intents_and_training_examples_dict.get(intent["name"]):
                intents_and_training_examples_dict[intent["name"]] = None
        return intents_and_training_examples_dict

    def get_training_examples(self, intent: Text, bot: Text):
        """
        fetches training examples

        :param intent: intent name
        :param bot: bot id
        :return: yields training examples
        """
        training_examples = TrainingExamples.objects(
            bot=bot, intent__iexact=intent, status=True
        ).order_by("-timestamp")
        for training_example in training_examples:
            example = training_example.to_mongo().to_dict()
            entities = example["entities"] if "entities" in example else None
            yield {
                "_id": example["_id"].__str__(),
                "text": DataUtility.prepare_nlu_text(example["text"], entities),
            }

    def get_all_training_examples(self, bot: Text):
        """
        fetches list of all training examples

        :param bot: bot id
        :return: text list, id list
        """
        training_examples = list(
            TrainingExamples.objects(bot=bot, status=True).aggregate(
                [
                    {
                        "$group": {
                            "_id": "$bot",
                            "text": {"$push": {"$toLower": "$text"}},
                            "id": {"$push": {"$toString": "$_id"}},
                        }
                    }
                ]
            )
        )

        if training_examples:
            return training_examples[0]["text"], training_examples[0]["id"]
        else:
            return [], []

    @staticmethod
    def get_training_examples_as_dict(bot: Text):
        """
        fetches training examples and intent as a dict

        :param bot: bot id
        :return: list of dict<training_example, intent>
        """
        training_examples = list(
            TrainingExamples.objects(bot=bot, status=True).aggregate(
                [
                    {
                        "$replaceRoot": {
                            "newRoot": {
                                "$arrayToObject": [[{"k": "$text", "v": "$intent"}]]
                            }
                        }
                    },
                    {"$addFields": {"bot": bot}},
                    {
                        "$group": {
                            "_id": "$bot",
                            "training_examples": {"$mergeObjects": "$$ROOT"},
                        }
                    },
                    {"$unset": "training_examples.bot"},
                    {"$project": {"_id": 0, "training_examples": 1}},
                ]
            )
        )
        if training_examples:
            training_examples = training_examples[0].get("training_examples", {})
        else:
            training_examples = {}
        return training_examples

    def remove_document(
            self, document: Document, id: Text, bot: Text, user: Text, **kwargs
    ):
        """
        soft delete the document

        :param document: mongoengine document
        :param id: document id
        :param bot: bot id
        :param user: user id
        :return: None
        """
        try:
            doc = document.objects(bot=bot, **kwargs).get(id=id)
            doc.status = False
            doc.user = user
            doc.timestamp = datetime.utcnow()
            doc.save(validate=False)
        except DoesNotExist as e:
            logging.info(e)
            raise AppException("Unable to remove document")
        except Exception as e:
            logging.info(e)
            raise AppException("Unable to remove document")

    def __prepare_document_list(self, documents: List[Document], field: Text):
        for document in documents:
            doc_dict = document.to_mongo().to_dict()
            yield {"_id": doc_dict["_id"].__str__(), field: doc_dict[field]}

    def add_entity(
            self, name: Text, bot: Text, user: Text, raise_exc_if_exists: bool = True
    ):
        """
        adds an entity

        :param name: entity name
        :param bot: bot id
        :param user: user id
        :param raise_exc_if_exists: raise exception if entity exists
        :return: entity id
        """
        if Utility.check_empty_string(name):
            raise AppException("Entity Name cannot be empty or blank spaces")
        if not Utility.is_exist(
                Entities,
                raise_error=raise_exc_if_exists,
                exp_message="Entity already exists!",
                name__iexact=name.strip(),
                bot=bot,
                status=True,
        ):
            entity = Entities(name=name, bot=bot, user=user).save().to_mongo().to_dict()
            return entity["_id"].__str__()

    def delete_entity(
            self, name: Text, bot: Text, user: Text, raise_exc_if_not_exists: bool = True
    ):
        """
        Deletes an entity.

        :param name: entity name
        :param bot: bot id
        :param user: user
        :param raise_exc_if_not_exists: raise exception if entity does not exists
        """
        try:
            entity = Entities.objects(name=name, bot=bot, status=True).get()
            Utility.delete_documents(entity, user)
        except DoesNotExist:
            if raise_exc_if_not_exists:
                raise AppException("Entity not found")

    def get_entities(self, bot: Text):
        """
        fetches list of registered entities

        :param bot: bot id
        :return: list of entities
        """
        entities = Entities.objects(bot=bot, status=True)
        return list(self.__prepare_document_list(entities, "name"))

    def add_action(
            self,
            name: Text,
            bot: Text,
            user: Text,
            raise_exception=True,
            action_type: ActionType = None,
    ):
        """
        adds action
        :param name: action name
        :param bot: bot id
        :param user: user id
        :param raise_exception: default is True to raise exception if Entity already exists
        :param action_type: one of http_action or slot_set_action
        :return: action id
        """
        if Utility.check_empty_string(name):
            raise AppException("Action name cannot be empty or blank spaces")

        self.__check_for_form_and_action_existance(bot, name, action_type)

        if not name.startswith("utter_") and not Utility.is_exist(
                Actions,
                raise_error=raise_exception,
                exp_message="Action exists!",
                name__iexact=name,
                bot=bot,
                status=True,
        ):
            action = (
                Actions(name=name, type=action_type, bot=bot, user=user)
                .save()
                .to_mongo()
                .to_dict()
            )
            return action["_id"].__str__()
        else:
            return None

    def get_actions(self, bot: Text):
        """
        fetches actions

        :param bot: bot id
        :return: list of actions
        """
        actions = Actions.objects(bot=bot, status=True)
        return list(self.__prepare_document_list(actions, "name"))

    def __add_slots_from_entities(self, entities: List[Text], bot: Text, user: Text):
        slot_name_list = self.__fetch_slot_names(bot)
        slots = []
        for entity in entities:
            if entity.strip().lower() not in slot_name_list:
                slot = Slots(name=entity, type="text", bot=bot, user=user)
                slot.clean()
                slots.append(slot)

        if slots:
            Slots.objects.insert(slots)

    def add_text_response(
            self,
            utterance: Text,
            name: Text,
            bot: Text,
            user: Text,
            form_attached: str = None,
    ):
        """
        saves bot text utterance
        :param utterance: text utterance
        :param name: utterance name
        :param bot: bot id
        :param user: user id
        :param form_attached: form for which this utterance was created
        :return: bot utterance id
        """
        if Utility.check_empty_string(utterance):
            raise AppException("Utterance text cannot be empty or blank spaces")
        if Utility.check_empty_string(name):
            raise AppException("Utterance name cannot be empty or blank spaces")
        if form_attached and not Utility.is_exist(
                Forms, raise_error=False, name=form_attached, bot=bot, status=True
        ):
            raise AppException(f"Form '{form_attached}' does not exists")
        return self.add_response(
            utterances={"text": utterance},
            name=name,
            bot=bot,
            user=user,
            form_attached=form_attached,
        )

    def add_custom_response(
            self,
            utterance: Dict,
            name: Text,
            bot: Text,
            user: Text,
            form_attached: str = None,
    ):
        """
        saves bot json utterance
        :param utterance: text utterance
        :param name: utterance name
        :param bot: bot id
        :param user: user id
        :param form_attached: form for which this utterance was created
        :return: json utterance id
        """
        if not (isinstance(utterance, dict) and utterance):
            raise AppException("Utterance must be dict type and must not be empty")
        if Utility.check_empty_string(name):
            raise AppException("Utterance name cannot be empty or blank spaces")
        if form_attached and not Utility.is_exist(
                Forms, raise_error=False, name=form_attached, bot=bot, status=True
        ):
            raise AppException(f"Form '{form_attached}' does not exists")
        return self.add_response(
            utterances={"custom": utterance},
            name=name,
            bot=bot,
            user=user,
            form_attached=form_attached,
        )

    def add_response(
            self,
            utterances: Dict,
            name: Text,
            bot: Text,
            user: Text,
            form_attached: str = None,
    ):
        """
        save bot utterance

        :param utterances: utterance value
        :param name: utterance name
        :param bot: bot id
        :param user: user id
        :param form_attached: form name in case utterance is attached to form
        :return: bot utterance id
        """
        self.__check_response_existence(
            response=utterances, bot=bot, exp_message="Utterance already exists!"
        )
        response = list(
            self.__extract_response_value(
                values=[utterances], key=name, bot=bot, user=user
            )
        )[0]
        value = response.save().to_mongo().to_dict()
        self.add_utterance_name(
            name=name, bot=bot, user=user, form_attached=form_attached
        )
        return value["_id"].__str__()

    def edit_text_response(
            self, id: Text, utterance: Text, name: Text, bot: Text, user: Text
    ):
        """
        update the text bot utterance

        :param id: utterance id against which the utterance is updated
        :param utterance: text utterance value
        :param name: utterance name
        :param bot: bot id
        :param user: user id
        :return: None
        :raises: DoesNotExist: if utterance does not exist
        """
        self.edit_response(id, {"text": utterance}, name, bot, user)

    def edit_custom_response(
            self, id: Text, utterance: Dict, name: Text, bot: Text, user: Text
    ):
        """
        update the json bot utterance

        :param id: utterance id against which the utterance is updated
        :param utterance: json utterance value
        :param name: utterance name
        :param bot: bot id
        :param user: user id
        :return: None
        :raises: DoesNotExist: if utterance does not exist
        """
        self.edit_response(id, {"custom": utterance}, name, bot, user)

    def edit_response(
            self, id: Text, utterances: Dict, name: Text, bot: Text, user: Text
    ):
        """
        update the bot utterance

        :param id: utterance id against which the utterance is updated
        :param utterances: utterance value
        :param name: utterance name
        :param bot: bot id
        :param user: user id
        :return: None
        :raises: AppException
        """
        try:
            self.__check_response_existence(
                response=utterances, bot=bot, exp_message="Utterance already exists!"
            )
            response = Responses.objects(bot=bot, name=name).get(id=id)
            r_type, r_object = DataUtility.prepare_response(utterances)
            if RESPONSE.Text.value == r_type:
                response.text = r_object
                response.custom = None
            elif RESPONSE.CUSTOM.value == r_type:
                response.custom = r_object
                response.text = None
            response.user = user
            response.timestamp = datetime.utcnow()
            response.save()
        except DoesNotExist:
            raise AppException("Utterance does not exist!")

    def get_response(self, name: Text, bot: Text):
        """
        fetch all the utterances

        :param name: utterance name
        :param bot: bot id
        :return: yields the utterances
        """
        values = Responses.objects(bot=bot, status=True, name__iexact=name).order_by(
            "-timestamp"
        )
        for value in values:
            val = None
            resp_type = None
            if value.text:
                val = list(
                    self.__prepare_response_Text([value.text.to_mongo().to_dict()])
                )[0]
                resp_type = "text"
            elif value.custom:
                val = value.custom.to_mongo().to_dict()
                resp_type = "json"
            yield {"_id": value.id.__str__(), "value": val, "type": resp_type}

    def fetch_list_of_response(self, bot: Text):
        saved_responses = list(
            Responses.objects(bot=bot, status=True).aggregate(
                [
                    {
                        "$group": {
                            "_id": "$name",
                            "texts": {"$push": "$text"},
                            "customs": {"$push": "$custom"},
                        }
                    }
                ]
            )
        )

        saved_items = list(
            itertools.chain.from_iterable(
                [items["texts"] + items["customs"] for items in saved_responses]
            )
        )

        return saved_items

    def get_all_responses(self, bot: Text):
        responses = list(
            Responses.objects(bot=bot, status=True)
            .order_by("-timestamp")
            .aggregate(
                [
                    {
                        "$group": {
                            "_id": "$name",
                            "texts": {"$push": "$text"},
                            "customs": {"$push": "$custom"},
                        }
                    },
                    {"$project": {"_id": 0, "name": "$_id", "texts": 1, "customs": 1}},
                ]
            )
        )
        return responses

    def __check_response_existence(
            self, response: Dict, bot: Text, exp_message: Text = None, raise_error=True
    ):
        saved_items = self.fetch_list_of_response(bot)

        if response in saved_items:
            if raise_error:
                if Utility.check_empty_string(exp_message):
                    raise AppException("Exception message cannot be empty")
                raise AppException(exp_message)
            else:
                return True
        else:
            if not raise_error:
                return False

    def __complex_story_prepare_steps(self, steps: List[Dict], flowtype, bot, user):
        """
        convert kairon story events to rasa story events
        :param steps: list of story steps
        :return: rasa story events list
        """

        events = []
        if steps and flowtype == "RULE":
            if (
                    steps[0]["name"] != RULE_SNIPPET_ACTION_NAME
                    and steps[0]["type"] != ActionExecuted.type_name
            ):
                events.append(
                    StoryEvents(
                        name=RULE_SNIPPET_ACTION_NAME, type=ActionExecuted.type_name
                    )
                )
        action_step_types = {s_type.value for s_type in StoryStepType}.difference(
            {
                StoryStepType.intent.value,
                StoryStepType.slot.value,
                StoryStepType.stop_flow_action.value,
                StoryStepType.form_start.value,
                StoryStepType.form_end.value,
            }
        )
        for step in steps:
            if step["type"] == StoryStepType.intent.value:
                events.append(
                    StoryEvents(
                        name=step["name"].strip().lower(), type=UserUttered.type_name
                    )
                )
            elif step["type"] == StoryStepType.slot.value:
                events.append(
                    StoryEvents(
                        name=step["name"].strip().lower(),
                        type=SlotSet.type_name,
                        value=step.get("value"),
                    )
                )
            elif step["type"] == StoryStepType.stop_flow_action.value:
                events.append(
                    StoryEvents(
                        name=ACTION_LISTEN_NAME, type=ActionExecuted.type_name
                    )
                )
            elif step["type"] in action_step_types:
                Utility.is_exist(
                    Utterances,
                    f'utterance "{step["name"]}" is attached to a form',
                    bot=bot,
                    name__iexact=step["name"],
                    form_attached__ne=None,
                )
                events.append(
                    StoryEvents(
                        name=step["name"].strip().lower(), type=ActionExecuted.type_name
                    )
                )
                if step["type"] == StoryStepType.action.value:
                    self.add_action(step["name"], bot, user, raise_exception=False)
            elif step["type"] == StoryStepType.form_start.value:
                events.append(
                    StoryEvents(
                        name=step["name"].strip().lower(), type=ActiveLoop.type_name
                    )
                )
            elif step["type"] == StoryStepType.form_end.value:
                events.append(StoryEvents(name=None, type=ActiveLoop.type_name))
            else:
                raise AppException("Invalid event type!")
        return events

    def add_complex_story(self, story: Dict, bot: Text, user: Text):
        """
        save story in mongodb

        :param story: story steps list
        :param bot: bot id
        :param user: user id
        :return: story id
        :raises: AppException: Story already exist!

        """
        name = story["name"]
        steps = story["steps"]
        flowtype = story["type"]
        flow_tags = story.get("flow_tags")
        if Utility.check_empty_string(name):
            raise AppException("path name cannot be empty or blank spaces")

        if not Utility.special_match(name, RE_VALID_NAME):
            raise AppException("Story name can only contain letters, numbers, hyphens (-), and underscores (_)")


        if not steps:
            raise AppException("steps are required")

        template_type = story.get("template_type")
        if not template_type:
            template_type = DataUtility.get_template_type(story)

        if flowtype == "STORY":
            data_class = Stories
            data_object = Stories()
            exception_message_name = "Story"
        elif flowtype == "RULE":
            data_class = Rules
            data_object = Rules()
            if flow_tags:
                data_object.flow_tags = flow_tags
            exception_message_name = "Rule"
        else:
            raise AppException("Invalid type")
        Utility.is_exist(
            data_class,
            bot=bot,
            status=True,
            block_name__iexact=name,
            exp_message=f"{exception_message_name} with the name already exists",
        )
        events = self.__complex_story_prepare_steps(steps, flowtype, bot, user)
        Utility.is_exist_query(
            data_class,
            query=(Q(bot=bot) & Q(status=True))
                  & (Q(block_name__iexact=name) | Q(events=events)),
            exp_message="Flow already exists!",
        )

        data_object.block_name = name
        data_object.events = events
        data_object.bot = bot
        data_object.user = user
        data_object.start_checkpoints = [STORY_START]
        data_object.template_type = template_type

        id = data_object.save().id.__str__()

        self.add_slot(
            {
                "name": "bot",
                "type": "any",
                "initial_value": bot,
                "influence_conversation": False,
            },
            bot,
            user,
            raise_exception_if_exists=False,
            is_default=True
        )

        return id

    def add_multiflow_story(self, story: Dict, bot: Text, user: Text):
        """
        save conditional story in mongodb

        :param story: story steps list
        :param bot: bot id
        :param user: user id
        :return: story id
        :raises: AppException: Story already exist!

        """

        name = story["name"]
        steps = story["steps"]
        metadata = story.get("metadata")
        flow_tags = story.get("flow_tags")

        if Utility.check_empty_string(name):
            raise AppException("Story name cannot be empty or blank spaces")

        if not Utility.special_match(name, RE_VALID_NAME):
            raise AppException("Story name can only contain letters, numbers, hyphens (-), and underscores (_)")


        if not steps:
            raise AppException("steps are required")
        Utility.is_exist(
            MultiflowStories,
            bot=bot,
            status=True,
            block_name__iexact=name,
            exp_message="Multiflow Story with the name already exists",
        )
        StoryValidator.validate_steps(steps, metadata)
        events = [MultiflowStoryEvents(**step) for step in steps]
        path_metadata = [MultiFlowStoryMetadata(**path) for path in metadata or []]
        Utility.is_exist_query(
            MultiflowStories,
            query=(Q(bot=bot) & Q(status=True))
                  & (Q(block_name__iexact=name) | Q(events=events)),
            exp_message="Story flow already exists!",
        )

        story_obj = MultiflowStories()
        story_obj.block_name = name
        story_obj.events = events
        story_obj.metadata = path_metadata
        story_obj.bot = bot
        story_obj.user = user
        story_obj.start_checkpoints = [STORY_START]
        if flow_tags:
            story_obj.flow_tags = flow_tags

        id = story_obj.save().id.__str__()

        self.add_slot(
            {
                "name": "bot",
                "type": "any",
                "initial_value": bot,
                "influence_conversation": False,
            },
            bot,
            user,
            raise_exception_if_exists=False,
            is_default=True
        )

        return id

    def update_complex_story(self, story_id: Text, story: Dict, bot: Text, user: Text):
        """
        Updates story in mongodb

        :param story_id: story id
        :param story: dict contains name, steps and type for either rules or story
        :param bot: bot id
        :param user: user id
        :return: story id
        :raises: AppException: Story already exist!

        """
        name = story["name"]
        steps = story["steps"]
        flowtype = story["type"]
        flow_tags = story.get("flow_tags")

        if Utility.check_empty_string(name):
            raise AppException("path name cannot be empty or blank spaces")

        if not Utility.special_match(name, RE_VALID_NAME):
            raise AppException("Story name can only contain letters, numbers, hyphens (-), and underscores (_)")

        if not steps:
            raise AppException("steps are required")

        if flowtype == "STORY":
            data_class = Stories
            exception_message_name = "Story"
        elif flowtype == "RULE":
            data_class = Rules
            exception_message_name = "Rule"
        else:
            raise AppException("Invalid type")
        Utility.is_exist(
            data_class,
            bot=bot,
            status=True,
            block_name__iexact=name,
            id__ne=story_id,
            exp_message=f"{exception_message_name} with the name already exists",
        )
        try:
            data_object = data_class.objects(bot=bot, status=True, id=story_id).get()
        except DoesNotExist:
            raise AppException("Flow does not exists")

        events = self.__complex_story_prepare_steps(steps, flowtype, bot, user)
        data_object["events"] = events
        Utility.is_exist_query(
            data_class,
            query=(
                    Q(id__ne=story_id)
                    & Q(bot=bot)
                    & Q(status=True)
                    & Q(events=data_object["events"])
            ),
            exp_message="Flow already exists!",
        )
        data_object["block_name"] = name
        if flow_tags and flowtype == "RULE":
            data_object["flow_tags"] = flow_tags
        story_id = data_object.save().id.__str__()
        return story_id

    def update_multiflow_story(self, story_id: Text, story: Dict, bot: Text):
        """
        Updates story in mongodb

        :param story_id: story id
        :param story: dict contains name, steps and type for either rules or story
        :param bot: bot id
        :param user: user id
        :return: story id
        :raises: AppException: Story already exist!

        """
        name = story["name"]
        steps = story["steps"]
        metadata = story.get("metadata")
        flow_tags = story.get("flow_tags")


        if Utility.check_empty_string(name):
            raise AppException("Story name cannot be empty or blank spaces")

        if not Utility.special_match(name, RE_VALID_NAME):
            raise AppException("Story name can only contain letters, numbers, hyphens (-), and underscores (_)")

        if not steps:
            raise AppException("steps are required")
        StoryValidator.validate_steps(steps, metadata)
        Utility.is_exist(
            MultiflowStories,
            bot=bot,
            status=True,
            block_name__iexact=name,
            id__ne=story_id,
            exp_message="Multiflow Story with the name already exists",
        )
        events = [MultiflowStoryEvents(**step) for step in steps]
        path_metadata = [MultiFlowStoryMetadata(**path) for path in metadata or []]
        Utility.is_exist_query(
            MultiflowStories,
            query=(Q(id__ne=story_id) & Q(bot=bot) & Q(status=True) & Q(events=events)),
            exp_message="Story flow already exists!",
        )

        try:
            story_obj = MultiflowStories.objects(
                bot=bot, status=True, id=story_id
            ).get()
            story_obj.events = events
            story_obj.metadata = path_metadata
            story_obj.block_name = name
            if flow_tags:
                story_obj.flow_tags = flow_tags
            story_id = story_obj.save().id.__str__()
            return story_id
        except DoesNotExist:
            raise AppException("Flow does not exists")

    def delete_complex_story(self, story_id: str, type: Text, bot: Text, user: Text):
        """
        Soft deletes complex story.
        :param story_id: Story id
        :param type: Flow Type
        :param user: user id
        :param bot: bot id
        :return:
        """

        if type == StoryType.story.value:
            data_class = Stories
        elif type == StoryType.rule.value:
            data_class = Rules
        elif type == StoryType.multiflow_story.value:
            data_class = MultiflowStories
        else:
            raise AppException("Invalid type")
        try:
            document = data_class.objects(bot=bot, status=True).get(id=story_id)
            Utility.delete_documents(document, user)
        except DoesNotExist:
            raise AppException("Flow does not exists")

    def get_all_stories(self, bot: Text):
        standard_stories = list(self.get_stories(bot=bot))
        multiflow_stories = list(self.get_multiflow_stories(bot=bot))
        return standard_stories + multiflow_stories

    def get_stories(self, bot: Text):
        """
        fetches stories

        :param bot: bot is
        :return: yield dict
        """

        http_actions = self.list_http_action_names(bot)
        reset_slot_actions = set(SlotSetAction.objects(bot=bot, status=True).values_list('name'))
        google_search_actions = set(GoogleSearchAction.objects(bot=bot, status=True).values_list('name'))
        jira_actions = set(JiraAction.objects(bot=bot, status=True).values_list('name'))
        zendesk_actions = set(ZendeskAction.objects(bot=bot, status=True).values_list('name'))
        pipedrive_leads_actions = set(PipedriveLeadsAction.objects(bot=bot, status=True).values_list('name'))
        hubspot_forms_actions = set(HubspotFormsAction.objects(bot=bot, status=True).values_list('name'))
        pyscript_actions = set(PyscriptActionConfig.objects(bot=bot, status=True).values_list('name'))
        razorpay_actions = set(RazorpayAction.objects(bot=bot, status=True).values_list('name'))
        email_actions = set(EmailActionConfig.objects(bot=bot, status=True).values_list('action_name'))
        prompt_actions = set(PromptAction.objects(bot=bot, status=True).values_list('name'))
        database_actions = set(DatabaseAction.objects(bot=bot, status=True).values_list('name'))
        web_search_actions = set(WebSearchAction.objects(bot=bot, status=True).values_list('name'))
        callback_actions = set(CallbackActionConfig.objects(bot=bot, status=True).values_list('name'))
        schedule_action = set(ScheduleAction.objects(bot=bot, status=True).values_list('name'))
        parallel_actions = set(ParallelActionConfig.objects(bot=bot, status=True).values_list('name'))
        forms = set(Forms.objects(bot=bot, status=True).values_list('name'))
        data_list = list(Stories.objects(bot=bot, status=True))
        data_list.extend(list(Rules.objects(bot=bot, status=True)))
        for value in data_list:
            final_data = {}
            item = value.to_mongo().to_dict()
            block_name = item.pop("block_name")
            events = item.pop("events")
            final_data["_id"] = item["_id"].__str__()
            final_data["template_type"] = item.pop("template_type")
            if isinstance(value, Stories):
                final_data["type"] = StoryType.story.value
            elif isinstance(value, Rules):
                final_data["type"] = StoryType.rule.value
                final_data['flow_tags'] = item.get('flow_tags', [])
            else:
                continue
            steps = []
            for event in events:
                step = {}
                if (
                        isinstance(value, Rules)
                        and event.get("name") == RULE_SNIPPET_ACTION_NAME
                        and event["type"] == ActionExecuted.type_name
                ):
                    continue
                if event["type"] == UserUttered.type_name:
                    step["name"] = event["name"]
                    step["type"] = StoryStepType.intent.value
                elif event["type"] == SlotSet.type_name:
                    step["name"] = event["name"]
                    step["type"] = StoryStepType.slot.value
                    step["value"] = event.get("value")
                elif event["type"] == ActionExecuted.type_name:
                    step["name"] = event["name"]
                    if event["name"] in http_actions:
                        step["type"] = StoryStepType.http_action.value
                    elif event["name"] in reset_slot_actions:
                        step["type"] = StoryStepType.slot_set_action.value
                    elif event["name"] in google_search_actions:
                        step["type"] = StoryStepType.google_search_action.value
                    elif event["name"] in jira_actions:
                        step["type"] = StoryStepType.jira_action.value
                    elif event["name"] in email_actions:
                        step["type"] = StoryStepType.email_action.value
                    elif event["name"] in forms:
                        step["type"] = StoryStepType.form_action.value
                    elif event["name"] in zendesk_actions:
                        step["type"] = StoryStepType.zendesk_action.value
                    elif event["name"] in pipedrive_leads_actions:
                        step["type"] = StoryStepType.pipedrive_leads_action.value
                    elif event["name"] in hubspot_forms_actions:
                        step["type"] = StoryStepType.hubspot_forms_action.value
                    elif event["name"] in razorpay_actions:
                        step["type"] = StoryStepType.razorpay_action.value
                    elif event["name"] in pyscript_actions:
                        step["type"] = StoryStepType.pyscript_action.value
                    elif event["name"] == KAIRON_TWO_STAGE_FALLBACK:
                        step["type"] = StoryStepType.two_stage_fallback_action.value
                    elif event["name"] in prompt_actions:
                        step["type"] = StoryStepType.prompt_action.value
                    elif event["name"] in database_actions:
                        step['type'] = StoryStepType.database_action.value
                    elif event['name'] in web_search_actions:
                        step["type"] = StoryStepType.web_search_action.value
                    elif event['name'] == 'live_agent_action':
                        step["type"] = StoryStepType.live_agent_action.value
                    elif event['name'] in callback_actions:
                        step["type"] = StoryStepType.callback_action.value
                    elif event['name'] in parallel_actions:
                        step["type"] = StoryStepType.parallel_action.value
                    elif event['name'] in schedule_action:
                        step["type"] = StoryStepType.schedule_action.value
                    elif event['name'] == 'action_listen':
                        step["type"] = StoryStepType.stop_flow_action.value
                        step["name"] = 'stop_flow_action'
                    elif str(event["name"]).startswith("utter_"):
                        step["type"] = StoryStepType.bot.value
                    else:
                        step["type"] = StoryStepType.action.value
                elif event["type"] == ActiveLoop.type_name:
                    step["type"] = StoryStepType.form_end.value
                    if not Utility.check_empty_string(event.get("name")):
                        step["name"] = event["name"]
                        step["type"] = StoryStepType.form_start.value
                if step:
                    steps.append(step)

            final_data["name"] = block_name
            final_data["steps"] = steps
            yield final_data

    def get_multiflow_stories(self, bot: Text):
        """
        fetches stories

        :param bot: bot id
        :return: yield dict
        """
        multiflow = list(MultiflowStories.objects(bot=bot, status=True))
        for value in multiflow:
            final_data = {}
            item = value.to_mongo().to_dict()
            block_name = item.pop("block_name")
            events = item.pop("events")
            final_data["metadata"] = item.get("metadata", [])
            final_data["type"] = StoryType.multiflow_story.value
            final_data["_id"] = item["_id"].__str__()
            final_data["name"] = block_name
            final_data["steps"] = events
            final_data['flow_tags'] = item.get('flow_tags', [])
            yield final_data

    def get_utterance_from_intent(self, intent: Text, bot: Text):
        """
        fetches the utterance name by searching intent name in stories

        :param intent: intent name
        :param bot: bot id
        :return: utterance name
        """
        if Utility.check_empty_string(intent):
            raise AppException("Intent cannot be empty or blank spaces")

        responses = Responses.objects(bot=bot, status=True).distinct(field="name")
        actions = HttpActionConfig.objects(bot=bot, status=True).distinct(
            field="action_name"
        )
        story = Stories.objects(bot=bot, status=True, events__name__iexact=intent)
        if story:
            events = story[0].events
            search = False
            http_action_for_story = None
            for i in range(len(events)):
                event = events[i]
                if event.type == "user":
                    if str(event.name).lower() == intent.lower():
                        search = True
                    else:
                        search = False
                if (
                        search
                        and event.type == StoryEventType.action
                        and event.name in responses
                ):
                    return event.name, UTTERANCE_TYPE.BOT
                elif (
                        search
                        and event.type == StoryEventType.action
                        and event.name == CUSTOM_ACTIONS.HTTP_ACTION_NAME
                ):
                    if http_action_for_story in actions:
                        return http_action_for_story, UTTERANCE_TYPE.HTTP
                elif search and event.type == StoryEventType.action:
                    return event.name, event.type
                if search and event.name == CUSTOM_ACTIONS.HTTP_ACTION_CONFIG:
                    http_action_for_story = event.value
        return None, None

    def add_session_config(
            self,
            bot: Text,
            user: Text,
            id: Text = None,
            sesssionExpirationTime: int = 60,
            carryOverSlots: bool = True,
    ):
        """
        save or update session config

        :param bot: bot id
        :param user: user id
        :param id: session config id
        :param sesssionExpirationTime: session expiration time, default is 60
        :param carryOverSlots: caary over slots, default is True
        :return:
        """
        if not Utility.check_empty_string(id):
            session_config = SessionConfigs.objects().get(id=id)
            session_config.sesssionExpirationTime = sesssionExpirationTime
            session_config.carryOverSlots = carryOverSlots
        else:
            if SessionConfigs.objects(bot=bot):
                raise AppException("Session config already exists!")
            session_config = SessionConfigs(
                sesssionExpirationTime=sesssionExpirationTime,
                carryOverSlots=carryOverSlots,
                bot=bot,
                user=user,
            )

        return session_config.save().id.__str__()

    def get_session_config(self, bot: Text):
        """
        fetches session configuration

        :param bot: bot id
        :return: dict of session configuration
        """
        session_config = SessionConfigs.objects().get(bot=bot).to_mongo().to_dict()
        return {
            "_id": session_config["_id"].__str__(),
            "sesssionExpirationTime": session_config["sesssionExpirationTime"],
            "carryOverSlots": session_config["carryOverSlots"],
        }

    def add_endpoints(self, endpoint_config: Dict, bot: Text, user: Text):
        """
        saves endpoint configurations

        :param endpoint_config: endpoint configurations
        :param bot: bot id
        :param user: user id
        :return: endpoint id
        """
        try:
            endpoint = Endpoints.objects().get(bot=bot)
        except DoesNotExist:
            if Endpoints.objects(bot=bot):
                raise AppException("Endpoint Configuration already exists!")
            endpoint = Endpoints()

        if endpoint_config.get("bot_endpoint"):
            endpoint.bot_endpoint = EndPointBot(**endpoint_config.get("bot_endpoint"))

        if endpoint_config.get("action_endpoint"):
            endpoint.action_endpoint = EndPointAction(
                **endpoint_config.get("action_endpoint")
            )

        if endpoint_config.get(ENDPOINT_TYPE.HISTORY_ENDPOINT.value):
            token = endpoint_config[ENDPOINT_TYPE.HISTORY_ENDPOINT.value].get("token")
            if not Utility.check_empty_string(token):
                if len(token) < 8:
                    raise AppException("token must contain at least 8 characters")
                if " " in token:
                    raise AppException("token cannot contain spaces")
                encrypted_token = Utility.encrypt_message(token)
                endpoint_config[ENDPOINT_TYPE.HISTORY_ENDPOINT.value][
                    "token"
                ] = encrypted_token
            endpoint.history_endpoint = EndPointHistory(
                **endpoint_config.get(ENDPOINT_TYPE.HISTORY_ENDPOINT.value)
            )

        endpoint.bot = bot
        endpoint.user = user
        return endpoint.save().id.__str__()

    def delete_endpoint(self, bot: Text, endpoint_type: ENDPOINT_TYPE):
        """
        delete endpoint configuration

        :param bot: bot id
        :param endpoint_type: Type of endpoint
        :return:
        """
        if not endpoint_type:
            raise AppException("endpoint_type is required for deletion")
        try:
            current_endpoint_config = Endpoints.objects().get(bot=bot)
            if current_endpoint_config.__getitem__(endpoint_type):
                current_endpoint_config.__setitem__(endpoint_type, None)
                current_endpoint_config.save()
            else:
                raise AppException("Endpoint not configured")
        except DoesNotExist as e:
            logging.info(e)
            raise AppException("No Endpoint configured")

    def get_history_server_endpoint(self, bot):
        endpoint_config = None
        try:
            endpoint_config = self.get_endpoints(bot)
        except AppException:
            pass
        if endpoint_config and endpoint_config.get(
                ENDPOINT_TYPE.HISTORY_ENDPOINT.value
        ):
            history_endpoint = endpoint_config.get(ENDPOINT_TYPE.HISTORY_ENDPOINT.value)
            history_endpoint["type"] = "user"
        elif Utility.environment["history_server"].get("url"):
            history_endpoint = {
                "url": Utility.environment["history_server"]["url"],
                "token": Utility.environment["history_server"].get("token"),
                "type": "kairon",
            }
        else:
            raise AppException("No history server endpoint configured")
        return history_endpoint

    def get_endpoints(
            self, bot: Text, raise_exception=True, mask_characters: bool = False
    ):
        """
        fetches endpoint configuration

        :param bot: bot id
        :param mask_characters: masks last 3 characters of the history server token if True
        :param raise_exception: wether to raise an exception, default is True
        :return: endpoint configuration
        """
        try:
            endpoint = Endpoints.objects().get(bot=bot).to_mongo().to_dict()
            endpoint.pop("bot")
            endpoint.pop("user")
            endpoint.pop("timestamp")
            endpoint["_id"] = endpoint["_id"].__str__()

            if endpoint.get(ENDPOINT_TYPE.HISTORY_ENDPOINT.value):
                token = endpoint[ENDPOINT_TYPE.HISTORY_ENDPOINT.value].get("token")
                if not Utility.check_empty_string(token):
                    decrypted_token = Utility.decrypt_message(token)
                    if mask_characters:
                        decrypted_token = decrypted_token[:-3] + "***"
                    endpoint[ENDPOINT_TYPE.HISTORY_ENDPOINT.value][
                        "token"
                    ] = decrypted_token

            return endpoint
        except DoesNotExist as e:
            logging.info(e)
            if raise_exception:
                raise AppException("Endpoint Configuration does not exists!")
            else:
                return {}

    def add_model_deployment_history(
            self, bot: Text, user: Text, model: Text, url: Text, status: Text
    ):
        """
        saves model deployment history

        :param bot: bot id
        :param user: user id
        :param model: model path
        :param url: deployment url
        :param status: deploument status
        :return: model deployment id
        """
        return (
            ModelDeployment(bot=bot, user=user, model=model, url=url, status=status)
            .save()
            .to_mongo()
            .to_dict()
            .get("_id")
            .__str__()
        )

    def get_model_deployment_history(self, bot: Text):
        """
        fetches model deployment history

        :param bot: bot id
        :return: list of model deployment history
        """
        model_deployments = ModelDeployment.objects(bot=bot).order_by("-timestamp")

        for deployment in model_deployments:
            value = deployment.to_mongo().to_dict()
            value.pop("bot")
            value.pop("_id")
            yield value

    def deploy_model(self, bot: Text, user: Text):
        """
        deploy the model to the particular url

        :param bot: bot id
        :param user: user id
        :return: deployment response
        :raises: Exception
        """
        endpoint = {}
        model = None
        try:
            endpoint = self.get_endpoints(bot, raise_exception=False)
            response, model = Utility.deploy_model(endpoint, bot)
        except Exception as e:
            response = str(e)

        self.add_model_deployment_history(
            bot=bot,
            user=user,
            model=model,
            url=(
                endpoint.get("bot_endpoint").get("url")
                if endpoint.get("bot_endpoint")
                else None
            ),
            status=response,
        )
        return response

    def delete_intent(
            self,
            intent: Text,
            bot: Text,
            user: Text,
            is_integration: bool,
    ):
        """
        deletes intent including dependencies

        :param intent: intent name
        :param bot: bot id
        :param user: user id
        :param is_integration: integration status
        :param delete_dependencies: if True deletes training example, stories and responses
        that are associated with intent, default is True
        :return: None
        :raises: AppException
        """
        if Utility.check_empty_string(intent):
            raise AssertionError("Intent Name cannot be empty or blank spaces")

        try:
            # status to be filtered as Invalid Intent should not be fetched
            intent_obj = Intents.objects(bot=bot, status=True).get(name__iexact=intent)
            MongoProcessor.get_attached_flows(bot, intent, "user")
        except DoesNotExist as custEx:
            logging.info(custEx)
            raise AppException(
                "Invalid IntentName: Unable to remove document: " + str(custEx)
            )

        if is_integration:
            if not intent_obj.is_integration:
                raise AppException(
                    "This intent cannot be deleted by an integration user"
                )

        try:
            Utility.hard_delete_document(
                [TrainingExamples], bot=bot, intent__iexact=intent, user=user
            )
            Utility.delete_documents(intent_obj, user)
        except Exception as ex:
            logging.info(ex)
            raise AppException("Unable to remove document" + str(ex))

    def delete_utterance(self, utterance: str, bot: str, validate_form: bool = True, user: str = None):
        if not (utterance and utterance.strip()):
            raise AppException("Utterance cannot be empty or spaces")
        try:
            utterance = Utterances.objects(
                name__iexact=utterance, bot=bot, status=True
            ).get()
            utterance_name = utterance.name

            if validate_form and not Utility.check_empty_string(
                    utterance.form_attached
            ):
                raise AppException(
                    f"Utterance cannot be deleted as it is linked to form: {utterance.form_attached}"
                )

            MongoProcessor.get_attached_flows(bot, utterance_name, "action")
            Utility.hard_delete_document([Responses], bot=bot, name=utterance_name, user=user)
            Utility.delete_documents(utterance, user)
        except DoesNotExist as e:
            logging.info(e)
            raise AppException("Utterance does not exists")

    def delete_response(self, utterance_id: str, bot: str, user: str = None):
        if not (utterance_id and utterance_id.strip()):
            raise AppException("Response Id cannot be empty or spaces")
        try:
            response = Responses.objects(bot=bot, status=True).get(id=utterance_id)
            utterance_name = response["name"]
            story = MongoProcessor.get_attached_flows(
                bot, utterance_name, "action", False
            )
            responses = list(
                Responses.objects(bot=bot, status=True, name__iexact=utterance_name)
            )

            if story and len(responses) <= 1:
                raise AppException(
                    "At least one response is required for utterance linked to story"
                )
            if len(responses) <= 1:
                self.delete_utterance_name(name=utterance_name, bot=bot, raise_exc=True, user=user)
            Utility.delete_documents(response, user)
        except DoesNotExist as e:
            raise AppException(e)

    def update_http_config(self, request_data: Dict, user: str, bot: str):
        """
        Updates Http configuration.
        :param request_data: Dict containing configuration to be modified
        :param user: user id
        :param bot: bot id
        :return: Http configuration id for updated Http action config
        """
        if request_data.get("action_name") and Utility.special_match(request_data.get("action_name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        if not Utility.is_exist(
                HttpActionConfig,
                raise_error=False,
                action_name__iexact=request_data["action_name"],
                bot=bot,
                status=True,
        ):
            raise AppException(
                "No HTTP action found for bot "
                + bot
                + " and action "
                + request_data["action_name"]
            )
        for http_action in HttpActionConfig.objects(
                bot=bot, action_name=request_data["action_name"], status=True
        ):
            content_type = {
                HttpContentType.application_json: HttpRequestContentType.json.value,
                HttpContentType.urlencoded_form_data: HttpRequestContentType.data.value,
            }[request_data["content_type"]]
            response = (
                HttpActionResponse(**request_data.get("response", {}))
                .to_mongo()
                .to_dict()
            )
            params_list = [
                HttpActionRequestBody(**param)
                for param in request_data.get("params_list") or []
            ]
            headers = [
                HttpActionRequestBody(**param)
                for param in request_data.get("headers") or []
            ]
            set_slots = [
                SetSlotsFromResponse(**slot).to_mongo().to_dict()
                for slot in request_data.get("set_slots")
            ]
            http_action.http_url = request_data["http_url"]
            http_action.request_method = request_data["request_method"]
            http_action.dynamic_params = request_data.get("dynamic_params")
            http_action.content_type = content_type
            http_action.params_list = params_list
            http_action.headers = headers
            http_action.response = HttpActionResponse(**request_data.get("response", {}))
            http_action.set_slots = set_slots
            http_action.user = user
            http_action.timestamp = datetime.utcnow()
            http_action.save()

            return http_action.id.__str__()

    def add_http_action_config(self, http_action_config: Dict, user: str, bot: str):
        """
        Adds a new Http action.
        :param http_action_config: dict object containing configuration for the Http action
        :param user: user id
        :param bot: bot id
        :return: Http configuration id for saved Http action config
        """
        if http_action_config.get("action_name") and Utility.special_match(http_action_config.get("action_name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        Utility.is_valid_action_name(
            http_action_config.get("action_name"), bot, HttpActionConfig
        )
        http_action_params = [
            HttpActionRequestBody(**param)
            for param in http_action_config.get("params_list") or []
        ]
        headers = [
            HttpActionRequestBody(**param)
            for param in http_action_config.get("headers") or []
        ]
        content_type = {
            HttpContentType.application_json: HttpRequestContentType.json.value,
            HttpContentType.urlencoded_form_data: HttpRequestContentType.data.value,
        }[http_action_config["content_type"]]
        set_slots = [
            SetSlotsFromResponse(**slot) for slot in http_action_config.get("set_slots")
        ]
        doc_id = (
            HttpActionConfig(
                action_name=http_action_config["action_name"],
                content_type=content_type,
                http_url=http_action_config["http_url"],
                request_method=http_action_config["request_method"],
                dynamic_params=http_action_config.get("dynamic_params"),
                params_list=http_action_params,
                headers=headers,
                response=HttpActionResponse(**http_action_config.get("response", {})),
                set_slots=set_slots,
                bot=bot,
                user=user,
            )
            .save()
            .id.__str__()
        )
        self.add_action(
            http_action_config["action_name"],
            bot,
            user,
            action_type=ActionType.http_action.value,
            raise_exception=False,
        )
        return doc_id

    def get_http_action_config(self, bot: str, action_name: str):
        """
        Fetches Http action config from collection.
        :param bot: bot id
        :param user: user id
        :param action_name: action name
        :return: HttpActionConfig object containing configuration for the Http action.
        """
        try:
            http_config_dict = (
                HttpActionConfig.objects()
                .get(bot=bot, action_name=action_name, status=True)
                .to_mongo()
                .to_dict()
            )
            del http_config_dict["_id"]
            for param in http_config_dict.get("headers", []):
                Utility.decrypt_action_parameter(param)
                param.pop("_cls")

            for param in http_config_dict.get("params_list", []):
                Utility.decrypt_action_parameter(param)
                param.pop("_cls")

            http_config_dict["content_type"] = {
                HttpRequestContentType.json.value: HttpContentType.application_json.value,
                HttpContentType.application_json.value: HttpContentType.application_json.value,
                HttpRequestContentType.data.value: HttpContentType.urlencoded_form_data.value,
                HttpContentType.urlencoded_form_data.value: HttpContentType.urlencoded_form_data.value,
            }[http_config_dict["content_type"]]
            return http_config_dict
        except DoesNotExist as ex:
            logging.info(ex)
            raise AppException(
                "No HTTP action found for bot " + bot + " and action " + action_name
            )

    def list_http_actions(self, bot: str):
        """
        Fetches all Http actions from collection.
        :param bot: bot id
        :param user: user id
        :return: List of Http actions.
        """
        actions = HttpActionConfig.objects(bot=bot, status=True)
        return list(self.__prepare_document_list(actions, "action_name"))

    def add_pyscript_action(self, pyscript_config: Dict, user: str, bot: str):
        """
        Adds a new PyscriptActionConfig action.
        :param pyscript_config: dict object containing configuration for the Http action
        :param user: user id
        :param bot: bot id
        :return: Pyscript configuration id for saved Pyscript action config
        """
        if pyscript_config.get("name") and Utility.special_match(pyscript_config.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        Utility.is_valid_action_name(
            pyscript_config.get("name"), bot, PyscriptActionConfig
        )
        if compile_error := DataValidation.validate_python_script_compile_time(pyscript_config["source_code"]):
            raise AppException(f"source code syntax error: {compile_error}")
        action_id = (
            PyscriptActionConfig(
                name=pyscript_config["name"],
                source_code=pyscript_config["source_code"],
                dispatch_response=pyscript_config["dispatch_response"],
                bot=bot,
                user=user,
            )
            .save()
            .id.__str__()
        )
        self.add_action(
            pyscript_config["name"],
            bot,
            user,
            action_type=ActionType.pyscript_action.value,
            raise_exception=False,
        )
        return action_id

    def update_pyscript_action(self, request_data: Dict, user: str, bot: str):
        """
        Updates Pyscript configuration.
        :param request_data: Dict containing configuration to be modified
        :param user: user id
        :param bot: bot id
        :return: Pyscript configuration id for updated Pyscript action config
        """
        if request_data.get("name") and Utility.special_match(request_data.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        if not Utility.is_exist(
                PyscriptActionConfig,
                raise_error=False,
                name=request_data.get("name"),
                bot=bot,
                status=True,
        ):
            raise AppException(
                f'Action with name "{request_data.get("name")}" not found'
            )
        if compile_error := DataValidation.validate_python_script_compile_time(request_data["source_code"]):
            raise AppException(f"source code syntax error: {compile_error}")
        action = PyscriptActionConfig.objects(
            name=request_data.get("name"), bot=bot, status=True
        ).get()

        action.source_code = request_data["source_code"]
        action.dispatch_response = request_data["dispatch_response"]
        action.user = user
        action.timestamp = datetime.utcnow()
        action.save()

        return action.id.__str__()

    def list_pyscript_actions(self, bot: str, with_doc_id: bool = True):
        """
        Fetches all Pyscript actions from collection
        :param bot: bot id
        :param with_doc_id: return document id along with action configuration if True
        :return: List of Pyscript actions.
        """
        for action in PyscriptActionConfig.objects(bot=bot, status=True):
            action = action.to_mongo().to_dict()
            if with_doc_id:
                action["_id"] = action["_id"].__str__()
            else:
                action.pop("_id")
            action.pop("user")
            action.pop("bot")
            action.pop("status")
            action.pop("timestamp")
            yield action

    def update_db_action(self, request_data: Dict, user: str, bot: str):
        """
        Updates VectorDb configuration.
        :param request_data: Dict containing configuration to be modified
        :param user: user id
        :param bot: bot id
        :return: VectorDb configuration id for updated VectorDb action config
        """
        if request_data.get("name") and Utility.special_match(request_data.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        if not Utility.is_exist(
                DatabaseAction,
                raise_error=False,
                name=request_data.get("name"),
                bot=bot,
                status=True,
        ):
            raise AppException(
                f'Action with name "{request_data.get("name")}" not found'
            )
        self.__validate_payload(request_data.get("payload"), bot)
        if not Utility.is_exist(CognitionSchema, bot=bot, collection_name__iexact=request_data.get('collection'),
                                raise_error=False):
            raise AppException('Collection does not exist!')
        action = DatabaseAction.objects(
            name=request_data.get("name"), bot=bot, status=True
        ).get()
        action.collection = request_data['collection']
        action.payload = [DbQuery(**item) for item in request_data["payload"]]
        action.response = HttpActionResponse(**request_data.get("response", {}))
        action.set_slots = [
            SetSlotsFromResponse(**slot).to_mongo().to_dict()
            for slot in request_data.get("set_slots")
        ]
        action.user = user
        action.timestamp = datetime.utcnow()
        action_id = action.save().id.__str__()
        return action_id

    def add_db_action(self, vector_db_action_config: Dict, user: str, bot: str):
        """
        Adds a new VectorDb action.
        :param vector_db_action_config: dict object containing configuration for the Http action
        :param user: user id
        :param bot: bot id
        :return: Http configuration id for saved Http action config
        """
        if vector_db_action_config.get("name") and Utility.special_match(vector_db_action_config.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        self.__validate_payload(vector_db_action_config.get("payload"), bot)
        Utility.is_valid_action_name(
            vector_db_action_config.get("name"), bot, DatabaseAction
        )
        if not Utility.is_exist(CognitionSchema, bot=bot,
                                collection_name__iexact=vector_db_action_config.get('collection'),
                                raise_error=False):
            raise AppException('Collection does not exist!')
        set_slots = [
            SetSlotsFromResponse(**slot)
            for slot in vector_db_action_config.get("set_slots")
        ]
        action_id = (
            DatabaseAction(
                name=vector_db_action_config["name"],
                collection=vector_db_action_config['collection'],
                payload=vector_db_action_config.get("payload"),
                response=HttpActionResponse(
                    **vector_db_action_config.get("response", {})
                ),
                set_slots=set_slots,
                bot=bot,
                user=user,
            )
            .save()
            .id.__str__()
        )
        self.add_action(
            vector_db_action_config["name"],
            bot,
            user,
            action_type=ActionType.database_action.value,
            raise_exception=False,
        )
        return action_id

    def __validate_payload(self, payload, bot: Text):
        for item in payload:
            if item.get("type") == DbQueryValueType.from_slot.value:
                slot = item.get("value")
                if not Utility.is_exist(
                        Slots, raise_error=False, name=slot, bot=bot, status=True
                ):
                    raise AppException(f"Slot with name {slot} not found!")

    def get_db_action_config(self, bot: str, action: str):
        """
        Fetches VectorDb action config from collection.
        :param bot: bot id
        :param action: action name
        :return: DatabaseAction object containing configuration for the Http action.
        """
        try:
            vector_embedding_config_dict = DatabaseAction.objects(
                bot=bot, name=action, status=True
            ).get()
            vector_embedding_config = vector_embedding_config_dict.to_mongo().to_dict()
            vector_embedding_config["_id"] = vector_embedding_config["_id"].__str__()
            return vector_embedding_config
        except DoesNotExist as ex:
            logging.info(ex)
            raise AppException("Action does not exists!")

    def list_db_actions(self, bot: str, with_doc_id: bool = True):
        """
        Fetches all VectorDb actions from collection
        :param bot: bot id
        :param with_doc_id: return document id along with action configuration if True
        :return: List of VectorDb actions.
        """
        for action in DatabaseAction.objects(bot=bot, status=True):
            action = action.to_mongo().to_dict()
            if with_doc_id:
                action["_id"] = action["_id"].__str__()
            else:
                action.pop("_id")
            action.pop("user")
            action.pop("bot")
            action.pop("status")
            action.pop("timestamp")
            yield action

    def list_live_agent_actions(self, bot: str, with_doc_id: bool = True):
        """
        Fetches all LiveAgentActionConfig actions from collection
        :param bot: bot id
        :param with_doc_id: return document id along with action configuration if True
        :return: List of VectorDb actions.
        """
        for action in LiveAgentActionConfig.objects(bot=bot, status=True):
            action = action.to_mongo().to_dict()
            if with_doc_id:
                action["_id"] = action["_id"].__str__()
            else:
                action.pop("_id")
            action.pop("user")
            action.pop("bot")
            action.pop("status")
            action.pop("timestamp")
            yield action

    def list_actions(self, bot: Text):
        all_actions = list(
            Actions.objects(bot=bot, status=True).aggregate(
                [
                    {
                        "$group": {
                            "_id": {"$ifNull": ["$type", "actions"]},
                            "actions": {"$addToSet": "$name"},
                        }
                    }
                ]
            )
        )
        all_actions = {action["_id"]: action["actions"] for action in all_actions}
        all_actions["utterances"] = list(
            Utterances.objects(bot=bot, status=True).values_list("name")
        )
        action_types = [a_type.value for a_type in ActionType]
        action_types.append("actions")
        for a_type in action_types:
            if a_type not in all_actions.keys():
                all_actions[a_type] = []
        if all_actions.get("actions"):
            actions = all_actions["actions"]
            actions = [
                action for action in actions if not str(action).startswith("utter_")
            ]
            all_actions["actions"] = actions
        return all_actions

    def list_http_action_names(self, bot: Text):
        actions = list(
            HttpActionConfig.objects(bot=bot, status=True).values_list("action_name")
        )
        return actions

    def add_google_search_action(self, action_config: dict, bot: Text, user: Text):
        """
        Add a new google search action

        :param action_config: google search action configuration
        :param bot: bot id
        :param user: user id
        :return: doc id
        """
        if action_config.get("name") and Utility.special_match(action_config.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        Utility.is_valid_action_name(action_config.get("name"), bot, GoogleSearchAction)
        if action_config.get("search_term"):
            action_config["search_term"]['key'] = 'search_term'
        action = (
            GoogleSearchAction(
                name=action_config["name"],
                api_key=CustomActionRequestParameters(**action_config["api_key"]),
                search_engine_id=action_config["search_engine_id"],
                search_term= CustomActionRequestParameters(**action_config["search_term"]) if action_config.get("search_term") else None,
                website=action_config.get("website"),
                failure_response=action_config.get("failure_response"),
                num_results=action_config.get("num_results"),
                dispatch_response=action_config.get("dispatch_response", True),
                set_slot=action_config.get("set_slot"),
                bot=bot,
                user=user,
            )
            .save()
            .id.__str__()
        )
        self.add_action(
            action_config["name"],
            bot,
            user,
            action_type=ActionType.google_search_action.value,
            raise_exception=False,
        )
        return action

    def edit_google_search_action(self, action_config: dict, bot: Text, user: Text):
        """
        Update google search action with new values.
        :param action_config: google search action configuration
        :param bot: bot id
        :param user: user id
        :return: None
        """
        if action_config.get("name") and Utility.special_match(action_config.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        if not Utility.is_exist(
                GoogleSearchAction,
                raise_error=False,
                name=action_config.get("name"),
                bot=bot,
                status=True,
        ):
            raise AppException(
                f'Google search action with name "{action_config.get("name")}" not found'
            )
        action = GoogleSearchAction.objects(
            name=action_config.get("name"), bot=bot, status=True
        ).get()
        if action_config.get('search_term'):
            action_config['search_term']['key'] = 'search_term'

        action.api_key = CustomActionRequestParameters(**action_config["api_key"])
        action.search_term = CustomActionRequestParameters(**action_config["search_term"]) if action_config.get("search_term") else None
        action.search_engine_id = action_config["search_engine_id"]
        action.website = action_config.get("website")
        action.failure_response = action_config.get("failure_response")
        action.num_results = action_config.get("num_results")
        action.dispatch_response = action_config.get("dispatch_response", True)
        action.set_slot = action_config.get("set_slot")
        action.user = user
        action.timestamp = datetime.utcnow()
        action.save()

    def list_google_search_actions(self, bot: Text, with_doc_id: bool = True):
        """
        List google search actions
        :param bot: bot id
        :param with_doc_id: return document id along with action configuration if True
        """
        for action in GoogleSearchAction.objects(bot=bot, status=True):
            action = action.to_mongo().to_dict()
            if with_doc_id:
                action["_id"] = action["_id"].__str__()
            else:
                action.pop("_id")
            action.pop("user")
            action.pop("bot")
            action.pop("timestamp")
            action.pop("status")
            yield action

    def add_web_search_action(self, action_config: dict, bot: Text, user: Text):
        """
        Add a new public search action

        :param action_config: public search action configuration
        :param bot: bot id
        :param user: user id
        :return: doc id
        """
        Utility.is_valid_action_name(action_config.get("name"), bot, WebSearchAction)
        action = (
            WebSearchAction(
                name=action_config["name"],
                website=action_config.get("website", None),
                failure_response=action_config.get("failure_response"),
                topn=action_config.get("topn"),
                dispatch_response=action_config.get("dispatch_response", True),
                set_slot=action_config.get("set_slot"),
                bot=bot,
                user=user,
            )
            .save()
            .id.__str__()
        )
        self.add_action(
            action_config["name"],
            bot,
            user,
            action_type=ActionType.web_search_action.value,
            raise_exception=False,
        )
        return action

    def edit_web_search_action(self, action_config: dict, bot: Text, user: Text):
        """
        Update public search action with new values.
        :param action_config: public search action configuration
        :param bot: bot id
        :param user: user id
        :return: None
        """
        if not Utility.is_exist(
                WebSearchAction,
                raise_error=False,
                name=action_config.get("name"),
                bot=bot,
                status=True,
        ):
            raise AppException(
                f'Public search action with name "{action_config.get("name")}" not found'
            )
        action = WebSearchAction.objects(
            name=action_config.get("name"), bot=bot, status=True
        ).get()
        action.website = action_config.get("website", None)
        action.failure_response = action_config.get("failure_response")
        action.topn = action_config.get("topn")
        action.dispatch_response = action_config.get("dispatch_response", True)
        action.set_slot = action_config.get("set_slot")
        action.user = user
        action.timestamp = datetime.utcnow()
        action.save()

    def list_web_search_actions(self, bot: Text, with_doc_id: bool = True):
        """
        List public search actions
        :param bot: bot id
        :param with_doc_id: return document id along with action configuration if True
        """
        for action in WebSearchAction.objects(bot=bot, status=True):
            action = action.to_mongo().to_dict()
            if with_doc_id:
                action["_id"] = action["_id"].__str__()
            else:
                action.pop("_id")
            action.pop("user")
            action.pop("bot")
            action.pop("timestamp")
            action.pop("status")
            yield action

    def list_all_actions(self, bot: str, with_doc_id: bool = True):
        """
        Fetches all actions from the collection
        :param bot: bot id
        :param with_doc_id: return document id along with action configuration if True
        :return: List of actions.
        """
        for action in Actions.objects(bot=bot, status=True):
            action = action.to_mongo().to_dict()
            if with_doc_id:
                action["_id"] = str(action["_id"])
            else:
                action.pop("_id")
            action.pop("user")
            action.pop("bot")
            action.pop("status")
            action.pop("timestamp")
            yield action

    def list_existing_actions_for_parallel_action(self, bot: str, with_doc_id: bool = True):
        """
        Fetches actions filtered by predefined action types from the collection.
        :param bot: bot id
        :param with_doc_id: return document id along with action configuration if True
        :return: List of filtered actions.
        """
        action_types = [
            ActionType.http_action,
            ActionType.email_action,
            ActionType.jira_action,
            ActionType.zendesk_action,
            ActionType.pipedrive_leads_action,
            ActionType.hubspot_forms_action,
            ActionType.prompt_action,
            ActionType.pyscript_action,
            ActionType.database_action,
            ActionType.callback_action,
            ActionType.schedule_action
        ]

        query = {"bot": bot, "status": True, "type": {"$in": [action.value for action in action_types]}}

        for action in Actions.objects(**query):
            action = action.to_mongo().to_dict()
            if with_doc_id:
                action["_id"] = str(action["_id"])
            else:
                action.pop("_id")
            action.pop("user")
            action.pop("bot")
            action.pop("status")
            action.pop("timestamp")
            yield action

    def add_slot(self, slot_value: Dict, bot: str, user: str, raise_exception_if_exists=True, is_default = False):
        """
        Adds slot if it doesn't exist, updates slot if it exists
        :param slot_value: slot data dict
        :param bot: bot id
        :param user: user id
        :param raise_exception_if_exists: set True to add new slot, False to update slot
        :return: slot id
        """

        if Utility.check_empty_string(slot_value.get("name")):
            raise AppException("Slot Name cannot be empty or blank spaces")

        if slot_value.get("name") and Utility.special_match(slot_value.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        if slot_value.get("type") not in [item for item in SLOT_TYPE]:
            raise AppException("Invalid slot type.")

        Utility.validate_slot_initial_value_and_values(slot_value)

        try:
            slot = Slots.objects(
                name__iexact=slot_value.get("name"), bot=bot, status=True
            ).get()
            if raise_exception_if_exists:
                raise AppException("Slot already exists!")
        except DoesNotExist:
            slot = Slots()
            slot.name = slot_value.get("name")

        slot.type = slot_value.get("type")
        slot.initial_value = slot_value.get("initial_value")
        slot.influence_conversation = slot_value.get("influence_conversation")

        if slot_value.get("type") == CategoricalSlot.type_name:
            slot.values = slot_value.get("values")
        elif slot_value.get("type") == FloatSlot.type_name:
            slot.max_value = slot_value.get("max_value")
            slot.min_value = slot_value.get("min_value")

        slot.is_default = is_default
        slot.user = user
        slot.bot = bot
        slot_id = slot.save().id.__str__()
        self.add_entity(slot_value.get("name"), bot, user, False)
        return slot_id

    def delete_slot(self, slot_name: Text, bot: Text, user: Text):
        """
        deletes slots
        :param slot_name: slot name
        :param bot: bot id
        :param user: user id
        :return: AppException
        """

        try:
            if slot_name.lower() in {s.value for s in KaironSystemSlots}:
                raise AppException("Default kAIron slot deletion not allowed")
            if self.get_row_count(SlotMapping, bot, slot=slot_name, status=True) > 0:
                raise AppException("Cannot delete slot without removing its mappings!")
            slot = Slots.objects(name__iexact=slot_name, bot=bot, status=True).get()
            forms_with_slot = Forms.objects(
                bot=bot, status=True, required_slots__in=[slot_name]
            )
            action_with_slot = GoogleSearchAction.objects(
                bot=bot, status=True, set_slot=slot_name
            )
            web_search_action_with_slot = WebSearchAction.objects(
                bot=bot, status=True, set_slot=slot_name
            )
            stories = Stories.objects(
                bot=bot,
                status=True,
                events__name=slot_name,
                events__type__=SlotSet.type_name,
            )
            training_examples = TrainingExamples.objects(
                bot=bot, status=True, entities__entity=slot_name
            )
            multi_stories = MultiflowStories.objects(
                bot=bot,
                status=True,
                events__connections__type__=StoryStepType.slot,
                events__connections__name=slot_name,
            )

            if len(forms_with_slot) > 0:
                raise AppException(
                    f'Slot is attached to form: {[form["name"] for form in forms_with_slot]}'
                )
            elif len(action_with_slot) > 0:
                raise AppException(
                    f'Slot is attached to action: {[action["name"] for action in action_with_slot]}'
                )
            elif len(web_search_action_with_slot) > 0:
                raise AppException(
                    f'Slot is attached to action: {[action["name"] for action in web_search_action_with_slot]}'
                )
            elif len(stories) > 0:
                raise AppException(
                    f'Slot is attached to story: {[story["block_name"] for story in stories]}'
                )
            elif len(training_examples) > 0:
                raise AppException(
                    f'Slot is attached to Example: {[example["intent"] for example in training_examples]}'
                )
            elif len(multi_stories) > 0:
                raise AppException(
                    f'Slot is attached to multi-flow story: {[story["block_name"] for story in multi_stories]}'
                )
            Utility.delete_documents(slot, user)
            self.delete_entity(slot_name, bot, user, False)
        except DoesNotExist as custEx:
            logging.info(custEx)
            raise AppException("Slot does not exist.")

    @staticmethod
    def abort_current_event(bot: Text, user: Text, event_type: EventClass):
        """
        sets event status to aborted if there is any event in progress or enqueued

        :param bot: bot id
        :param user: user id
        :param event_type: type of the event
        :return: None
        :raises: AppException
        """
        events_dict = {
            EventClass.model_training: ModelTraining,
            EventClass.model_testing: ModelTestingLogs,
            EventClass.delete_history: ConversationsHistoryDeleteLogs,
            EventClass.data_importer: ValidationLogs,
            EventClass.multilingual: BotReplicationLogs,
            EventClass.faq_importer: ValidationLogs,
            EventClass.message_broadcast: MessageBroadcastLogs
        }
        status_field = "status" if event_type in {EventClass.model_training,
                                                  EventClass.delete_history,
                                                  EventClass.data_generator} else "event_status"
        event_data_object = events_dict.get(event_type)
        if event_data_object:
            try:
                filter_params = {'bot': bot, f'{status_field}__in': [EVENT_STATUS.ENQUEUED.value]}

                event_object = event_data_object.objects.get(**filter_params)
                update_params = {f'set__{status_field}': EVENT_STATUS.ABORTED.value}
                event_object.update(**update_params)
                event = event_object.save().to_mongo().to_dict()
                event_id = event["_id"].__str__()
                payload = {'bot': bot, 'user': user, 'event_id': event_id}
                Utility.request_event_server(event_type, payload)
            except DoesNotExist:
                raise AppException(f"No Enqueued {event_type} present for this bot.")

    @staticmethod
    def get_row_count(document: Document, bot: str, **kwargs):
        """
        Gets the count of rows in a document for a particular bot.
        :param document: Mongoengine document for which count is to be given
        :param bot: bot id
        :return: Count of rows
        """
        if document.__name__ != "AuditLogData":
            kwargs['bot'] = bot
        return document.objects(**kwargs).count()

    @staticmethod
    def get_action_server_logs(bot: str, start_idx: int = 0, page_size: int = 10):
        """
        Fetches all action server logs from collection.
        :param bot: bot id
        :param start_idx: start index in collection
        :param page_size: number of rows
        :return: List of Http actions.
        """
        query = {
            "bot": bot,
            "trigger_info.trigger_id": ""
        }

        for log in (
                ActionServerLogs.objects(__raw__=query)
                        .order_by("-timestamp")
                        .skip(start_idx)
                        .limit(page_size)
        ):
            log = log.to_mongo().to_dict()
            log.pop("bot")
            log["_id"] = str(log["_id"])
            yield log

    def __extract_rules(self, story_steps, bot: str, user: str):
        saved_rules = self.fetch_rule_block_names(bot)

        for story_step in story_steps:
            if (
                    (isinstance(story_step, CustomRuleStep) or isinstance(story_step, RuleStep))
                    and story_step.block_name.strip().lower() not in saved_rules
            ):
                rule = self.__extract_rule_events(story_step, bot, user)
                yield rule


    def __extract_rule_events(self, rule_step: CustomRuleStep | RuleStep, bot: str, user: str):
        rule_events = list(self.__extract_story_events(rule_step.events))
        template_type = DataUtility.get_template_type(rule_step)
        condition_events_indices = []
        flow_tags = [FlowTagType.chatbot_flow.value]
        if hasattr(rule_step, "condition_events_indices"):
            condition_events_indices = list(rule_step.condition_events_indices)
        if hasattr(rule_step, "flow_tags"):
            flow_tags = rule_step.flow_tags
        rule = Rules(
            block_name=rule_step.block_name,
            condition_events_indices=condition_events_indices,
            start_checkpoints=[
                start_checkpoint.name
                for start_checkpoint in rule_step.start_checkpoints
            ],
            end_checkpoints=[
                end_checkpoint.name for end_checkpoint in rule_step.end_checkpoints
            ],
            events=rule_events,
            template_type=template_type,
            bot=bot,
            user=user,
            flow_tags=flow_tags
        )
        rule.clean()
        return rule

    @staticmethod
    def fetch_rule_block_names(bot: Text):
        saved_stories = list(
            Rules.objects(bot=bot, status=True).values_list("block_name")
        )
        return saved_stories

    def save_rules(self, story_steps, bot: Text, user: Text):
        if story_steps:
            new_rules = list(self.__extract_rules(story_steps, bot, user))
            if new_rules:
                Rules.objects.insert(new_rules)

    def delete_rules(self, bot: Text, user: Text):
        """
        soft deletes rules

        :param bot: bot id
        :param user: user id
        :return: None
        """
        Utility.hard_delete_document([Rules], bot=bot, user=user)

    def delete_bot_actions(self, bot: Text, user: Text):
        """
        Deletes all type of actions created in bot.

        :param bot: bot id
        :param user: user id
        :return: None
        """
        Utility.hard_delete_document([
            HttpActionConfig, SlotSetAction, FormValidationAction, EmailActionConfig, GoogleSearchAction, JiraAction,
            ZendeskAction, PipedriveLeadsAction, HubspotFormsAction, KaironTwoStageFallbackAction, PromptAction,
            PyscriptActionConfig, RazorpayAction, DatabaseAction
        ], bot=bot, user=user)
        Utility.hard_delete_document([Actions], bot=bot, type__ne=None, user=user)

    def __get_rules(self, bot: Text):
        for rule in Rules.objects(bot=bot, status=True, flow_tags__in=[FlowTagType.chatbot_flow.value]):
            rule_events = list(
                self.__prepare_training_story_events(
                    rule.events, datetime.now().timestamp(), bot
                )
            )

            yield RuleStep(
                block_name=rule.block_name,
                condition_events_indices=set(rule.condition_events_indices),
                events=rule_events,
                start_checkpoints=[
                    Checkpoint(start_checkpoint)
                    for start_checkpoint in rule.start_checkpoints
                ],
                end_checkpoints=[
                    Checkpoint(end_checkpoints)
                    for end_checkpoints in rule.end_checkpoints
                ],
            )

    def get_rules_for_training(self, bot: Text) -> StoryGraph:
        return StoryGraph(list(self.__get_rules(bot)))

    def get_rules_for_download(self, bot: Text) ->StoryGraph:
        rule_steps = []
        for rule in Rules.objects(bot=bot, status=True):
            rule_events = list(
                self.__prepare_training_story_events(
                    rule.events, datetime.now().timestamp(), bot
                )
            )

            rule_step =  CustomRuleStep(
                flow_tags= rule.flow_tags,
                block_name=rule.block_name,
                condition_events_indices=set(rule.condition_events_indices),
                events=rule_events,
                start_checkpoints=[
                    Checkpoint(start_checkpoint)
                    for start_checkpoint in rule.start_checkpoints
                ],
                end_checkpoints=[
                    Checkpoint(end_checkpoints)
                    for end_checkpoints in rule.end_checkpoints
                ],
            )

            rule_steps.append(rule_step)

        return StoryGraph(rule_steps)

    def save_integrated_actions(self, actions: dict, bot: Text, user: Text):
        """
        Saves different actions config data
        :param actions: action configurations of different types
        :param bot: bot id
        :param user: user id
        :return: None
        """

        if not actions:
            return
        document_types = {
            ActionType.http_action.value: HttpActionConfig,
            ActionType.two_stage_fallback.value: KaironTwoStageFallbackAction,
            ActionType.email_action.value: EmailActionConfig,
            ActionType.zendesk_action.value: ZendeskAction,
            ActionType.jira_action.value: JiraAction,
            ActionType.form_validation_action.value: FormValidationAction,
            ActionType.slot_set_action.value: SlotSetAction,
            ActionType.google_search_action.value: GoogleSearchAction,
            ActionType.pipedrive_leads_action.value: PipedriveLeadsAction,
            ActionType.prompt_action.value: PromptAction,
            ActionType.web_search_action.value: WebSearchAction,
            ActionType.razorpay_action.value: RazorpayAction,
            ActionType.pyscript_action.value: PyscriptActionConfig,
            ActionType.database_action.value: DatabaseAction,
            ActionType.live_agent_action.value: LiveAgentActionConfig,
        }
        saved_actions = set(
            Actions.objects(bot=bot, status=True, type__ne=None).values_list("name")
        )
        for action_type, actions_list in actions.items():
            for action in actions_list:
                action_name = action.get("name") or action.get("action_name")
                action_name = action_name.lower()
                if document_types.get(action_type) and action_name not in saved_actions:
                    action["bot"] = bot
                    action["user"] = user
                    document_types[action_type](**action).save()
                    self.add_action(
                        action_name,
                        bot,
                        user,
                        action_type=action_type,
                        raise_exception=False,
                    )

    def load_action_configurations(self, bot: Text):
        """
        loads configurations of all types of actions from the database
        :param bot: bot id
        :return: dict of action configurations of all types.
        """
        action_config = {}
        action_config.update(self.load_http_action(bot))
        action_config.update(self.load_jira_action(bot))
        action_config.update(self.load_email_action(bot))
        action_config.update(self.load_zendesk_action(bot))
        action_config.update(self.load_form_validation_action(bot))
        action_config.update(self.load_slot_set_action(bot))
        action_config.update(self.load_google_search_action(bot))
        action_config.update(self.load_pipedrive_leads_action(bot))
        action_config.update(self.load_two_stage_fallback_action_config(bot))
        action_config.update(self.load_prompt_action(bot))
        action_config.update(self.load_razorpay_action(bot))
        action_config.update(self.load_pyscript_action(bot))
        action_config.update(self.load_database_action(bot))
        action_config.update(self.load_live_agent_action(bot))
        return action_config

    def load_http_action(self, bot: Text):
        """
        loads the http actions from the database
        :param bot: bot id
        :return: dict
        """
        http_actions = []
        for action in HttpActionConfig.objects(bot=bot, status=True):
            action = action.to_mongo().to_dict()
            config = {
                "action_name": action["action_name"],
                "response": action["response"],
                "http_url": action["http_url"],
                "request_method": action["request_method"],
                "content_type": action["content_type"],
            }
            for header in action.get("headers") or []:
                parameter_type = header.get("parameter_type")
                value = header["value"]
                if (
                        parameter_type == ActionParameterType.value.value
                        and not Utility.check_empty_string(value)
                        and header.get("encrypt") is True
                ):
                    header["value"] = Utility.decrypt_message(header["value"])

            for param in action.get("params_list") or []:
                parameter_type = param.get("parameter_type")
                value = param["value"]
                if (
                        parameter_type == ActionParameterType.value.value
                        and not Utility.check_empty_string(value)
                        and param.get("encrypt") is True
                ):
                    param["value"] = Utility.decrypt_message(param["value"])

            if action.get('headers'):
                config['headers'] = action['headers']
            if action.get('params_list'):
                config['params_list'] = action['params_list']
            if action.get('set_slots'):
                config['set_slots'] = action['set_slots']
            if action.get('dynamic_params'):
                config['dynamic_params'] = action['dynamic_params']
            http_actions.append(config)
        return {ActionType.http_action.value: http_actions}

    def load_email_action(self, bot: Text):
        """
        Loads email actions from the database
        :param bot: bot id
        :return: dict
        """
        return {ActionType.email_action.value: list(self.list_email_action(bot, False))}

    def load_jira_action(self, bot: Text):
        """
        Loads JIRA actions from the database
        :param bot: bot id
        :return: dict
        """
        return {ActionType.jira_action.value: list(self.list_jira_actions(bot, False))}

    def load_google_search_action(self, bot: Text):
        """
        Loads Google search action from the database
        :param bot: bot id
        :return: dict
        """
        return {
            ActionType.google_search_action.value: list(
                self.list_google_search_actions(bot, False)
            )
        }

    def load_zendesk_action(self, bot: Text):
        """
        Loads Zendesk actions from the database
        :param bot: bot id
        :return: dict
        """
        return {
            ActionType.zendesk_action.value: list(self.list_zendesk_actions(bot, False))
        }

    def load_slot_set_action(self, bot: Text):
        """
        Loads Slot set actions from the database
        :param bot: bot id
        :return: dict
        """
        return {
            ActionType.slot_set_action.value: list(
                self.list_slot_set_actions(bot, False)
            )
        }

    def load_pipedrive_leads_action(self, bot: Text):
        """
        Loads Pipedrive leads actions from the database
        :param bot: bot id
        :return: dict
        """
        return {
            ActionType.pipedrive_leads_action.value: list(
                self.list_pipedrive_actions(bot, False)
            )
        }

    def load_two_stage_fallback_action_config(self, bot: Text):
        """
        Loads Two Stage Fallback actions from the database
        :param bot: bot id
        :return: dict
        """
        return {
            ActionType.two_stage_fallback.value: list(
                self.get_two_stage_fallback_action_config(
                    bot, KAIRON_TWO_STAGE_FALLBACK, False
                )
            )
        }

    def load_form_validation_action(self, bot: Text):
        """
        Loads Form validation actions from the database
        :param bot: bot id
        :return: dict
        """
        return {
            ActionType.form_validation_action.value: list(
                self.list_form_validation_actions(bot)
            )
        }

    def load_prompt_action(self, bot: Text):
        """
        Loads Prompt actions from the database
        :param bot: bot id
        :return: dict
        """
        return {
            ActionType.prompt_action.value: list(self.get_prompt_action(bot, False))
        }

    def load_razorpay_action(self, bot: Text):
        """
        Loads Razorpay actions from the database
        :param bot: bot id
        :return: dict
        """
        return {ActionType.razorpay_action.value: list(self.get_razorpay_action_config(bot, False))}

    def load_pyscript_action(self, bot: Text):
        """
        Loads Pyscript actions from the database
        :param bot: bot id
        :return: dict
        """
        return {ActionType.pyscript_action.value: list(self.list_pyscript_actions(bot, False))}

    def load_database_action(self, bot: Text):
        """
        Loads Database actions from the database
        :param bot: bot id
        :return: dict
        """
        return {ActionType.database_action.value: list(self.list_db_actions(bot, False))}

    def load_live_agent_action(self, bot: Text):
        """
        Loads live agent actions from the database
        :param bot: bot id
        :return: dict
        """
        return {ActionType.live_agent_action.value: list(self.list_live_agent_actions(bot, False))}


    @staticmethod
    def get_existing_slots(bot: Text):
        """
        fetches exisitng slots

        :param bot: bot id
        :param status: active or inactive, default is active
        :return: list of slots
        """
        for slot in Slots.objects(bot=bot, status=True):
            slot = slot.to_mongo().to_dict()
            slot.pop("bot")
            slot.pop("user")
            slot.pop("_id")
            slot.pop("timestamp")
            slot.pop("status")
            yield slot

    async def validate_and_log(self, bot: Text, user: Text, training_files, overwrite):
        (
            files_received,
            is_event_data,
            non_event_validation_summary,
        ) = await self.validate_and_prepare_data(bot, user, training_files, overwrite)
        DataImporterLogProcessor.add_log(
            bot, user, is_data_uploaded=True, files_received=list(files_received)
        )
        if not is_event_data:
            status = STATUSES.FAIL.value
            summary = non_event_validation_summary["summary"]
            component_count = non_event_validation_summary["component_count"]
            if not non_event_validation_summary["validation_failed"]:
                status = STATUSES.SUCCESS.value
            DataImporterLogProcessor.update_summary(
                bot,
                user,
                component_count,
                summary,
                status=status,
                event_status=EVENT_STATUS.COMPLETED.value,
            )

        return is_event_data

    async def validate_and_prepare_data(
            self, bot: Text, user: Text, training_files: List, overwrite: bool
    ):
        """
        Saves training data (zip, file or files) and validates whether at least one
        training file exists in the received set of files. If some training files are
        missing then, it prepares the rest of the data from database.
        In case only http actions are received, then it is validated and saved.
        Finally, a list of files received are returned.
        """
        non_event_validation_summary = None
        bot_data_home_dir = await DataUtility.save_uploaded_data(bot, training_files)
        files_to_prepare = DataUtility.validate_and_get_requirements(
            bot_data_home_dir, True
        )
        files_received = REQUIREMENTS - files_to_prepare
        is_event_data = False

        if files_received.difference({"config", "actions", "chat_client_config"}):
            is_event_data = True
        else:
            non_event_validation_summary = self.save_data_without_event(
                bot_data_home_dir, bot, user, overwrite
            )
        return files_received, is_event_data, non_event_validation_summary

    def save_data_without_event(
            self, data_home_dir: Text, bot: Text, user: Text, overwrite: bool
    ):
        """
        Saves http actions and config file.
        """
        from kairon.importer.validator.file_validator import TrainingDataValidator

        actions = None
        config = None
        chat_client_config = None
        validation_failed = False
        error_summary = {}
        component_count = COMPONENT_COUNT.copy()
        actions_path = os.path.join(data_home_dir, "actions.yml")
        config_path = os.path.join(data_home_dir, "config.yml")
        chat_client_config_path = os.path.join(data_home_dir, "chat_client_config.yml")
        if os.path.exists(actions_path):
            actions = Utility.read_yaml(actions_path)
            (
                is_successful,
                error_summary,
                actions_count,
            ) = ActionSerializer.validate(bot, actions, {})
            validation_failed = not is_successful
            component_count.update(actions_count)
        if os.path.exists(config_path):
            config = Utility.read_yaml(config_path)
            errors = TrainingDataValidator.validate_rasa_config(config)
            error_summary["config"] = errors
        if os.path.exists(chat_client_config_path):
            chat_client_config = Utility.read_yaml(chat_client_config_path)
            chat_client_config = chat_client_config["config"]

        if not validation_failed and not error_summary.get("config"):
            files_to_save = set()
            if actions and set(actions.keys()).intersection(
                    {a_type.value for a_type in ActionType}
            ):
                files_to_save.add("actions")
            if config:
                files_to_save.add("config")
            if chat_client_config:
                files_to_save.add("chat_client_config")
            self.save_training_data(
                bot,
                user,
                actions=actions,
                config=config,
                overwrite=overwrite,
                what=files_to_save,
                chat_client_config=chat_client_config,
            )
        else:
            validation_failed = True
        return {
            "summary": error_summary,
            "component_count": component_count,
            "validation_failed": validation_failed,
        }

    def prepare_training_data_for_validation(
            self, bot: Text, bot_data_home_dir: str = None, which: set = REQUIREMENTS.copy()
    ):
        """
        Writes training data into files and makes them available for validation.
        @param bot: bot id.
        @param bot_data_home_dir: location where data needs to be written
        @param which: which training data is to be written
        @return:
        """

        stories_graphs = []

        if not bot_data_home_dir:
            bot_data_home_dir = os.path.join("training_data", bot, str(uuid.uuid4()))
        data_path = os.path.join(bot_data_home_dir, DEFAULT_DATA_PATH)
        Utility.make_dirs(data_path)

        if "nlu" in which:
            nlu_path = os.path.join(data_path, "nlu.yml")
            nlu = self.load_nlu(bot)
            nlu_as_str = nlu.nlu_as_yaml().encode()
            Utility.write_to_file(nlu_path, nlu_as_str)

        if "stories" in which:
            stories_path = os.path.join(data_path, "stories.yml")
            stories = self.load_stories(bot)
            stories_graphs.append(stories)
            YAMLStoryWriter().dump(stories_path, stories.story_steps)

        if "config" in which:
            config_path = os.path.join(bot_data_home_dir, DEFAULT_CONFIG_PATH)
            config = self.load_config(bot)
            config_as_str = yaml.dump(config).encode()
            Utility.write_to_file(config_path, config_as_str)

        if "rules" in which:
            rules_path = os.path.join(data_path, "rules.yml")
            rules = self.get_rules_for_training(bot)
            stories_graphs.append(rules)
            YAMLStoryWriter().dump(rules_path, rules.story_steps)

        if "domain" in which:
            domain_path = os.path.join(bot_data_home_dir, DEFAULT_DOMAIN_PATH)
            domain = self.load_domain(bot, stories_graphs)
            if isinstance(domain, Domain):
                domain_as_str = domain.as_yaml().encode()
                Utility.write_to_file(domain_path, domain_as_str)
            elif isinstance(domain, Dict):
                yaml.safe_dump(domain, open(domain_path, "w"))


    def add_default_fallback_config(self, config_obj: dict, bot: Text, user: Text, default_fallback_data: bool = False):
        idx = next(
            (
                idx
                for idx, comp in enumerate(config_obj["policies"])
                if comp["name"] == "FallbackPolicy"
            ),
            None,
        )
        if idx:
            del config_obj["policies"][idx]
        rule_policy = next(
            (comp for comp in config_obj["policies"] if "RulePolicy" in comp["name"]),
            {},
        )

        if not rule_policy:
            config_obj["policies"].append(rule_policy)
        rule_policy["name"] = "RulePolicy"

        if not rule_policy.get("core_fallback_action_name"):
            rule_policy["core_fallback_action_name"] = "action_default_fallback"
        if not rule_policy.get("core_fallback_threshold"):
            rule_policy["core_fallback_threshold"] = 0.3
        if not rule_policy.get("max_history"):
            rule_policy["max_history"] = 5
        property_idx = next(
            (
                idx
                for idx, comp in enumerate(config_obj["pipeline"])
                if comp["name"] == "FallbackClassifier"
            ),
            None,
        )
        if not property_idx:
            property_idx = next(
                (
                    idx
                    for idx, comp in enumerate(config_obj["pipeline"])
                    if comp["name"] == "DIETClassifier"
                ),
                None,
            )
            if property_idx:
                fallback = {"name": "FallbackClassifier", "threshold": 0.7}
                config_obj["pipeline"].insert(property_idx + 1, fallback)

        if not default_fallback_data:
            self.add_default_fallback_data(bot, user, True, True)

    def add_default_fallback_data(
            self,
            bot: Text,
            user: Text,
            nlu_fallback: bool = True,
            action_fallback: bool = True,
    ):
        if nlu_fallback:
            if not Utility.is_exist(
                    Responses,
                    raise_error=False,
                    bot=bot,
                    status=True,
                    name__iexact="utter_please_rephrase",
            ):
                self.add_text_response(
                    DEFAULT_NLU_FALLBACK_RESPONSE, "utter_please_rephrase", bot, user
                )
            steps = [
                {"name": RULE_SNIPPET_ACTION_NAME, "type": StoryStepType.bot.value},
                {
                    "name": DEFAULT_NLU_FALLBACK_INTENT_NAME,
                    "type": StoryStepType.intent.value,
                },
                {"name": "utter_please_rephrase", "type": StoryStepType.bot.value},
            ]
            rule = {"name": DEFAULT_NLU_FALLBACK_RULE, "steps": steps, "type": "RULE"}
            try:
                self.add_complex_story(rule, bot, user)
            except AppException as e:
                logging.info(str(e))

        if action_fallback:
            if not Utility.is_exist(
                    Responses,
                    raise_error=False,
                    bot=bot,
                    status=True,
                    name__iexact=DEFAULT_NLU_FALLBACK_UTTERANCE_NAME,
            ):
                self.add_text_response(
                    DEFAULT_ACTION_FALLBACK_RESPONSE,
                    DEFAULT_NLU_FALLBACK_UTTERANCE_NAME,
                    bot,
                    user,
                )

    def add_default_training_data(self, bot: Text, user: Text):
        data = Utility.read_yaml("template/use-cases/GPT-FAQ/data/nlu.yml")
        utterance = Utility.read_yaml("template/use-cases/GPT-FAQ/domain.yml")

        self.add_intent("bye", bot, user, is_integration=False)
        examples_bye = next(
            intent["examples"] for intent in data["nlu"] if intent["intent"] == "bye"
        )
        list(
            self.add_training_example(
                examples_bye, "bye", bot, user, is_integration=False
            )
        )
        utter_bye_exmp = utterance["responses"]["utter_bye"]
        utter_bye = [item["text"] for item in utter_bye_exmp]
        if not Utility.is_exist(
                Responses, raise_error=False, bot=bot, status=True, name__iexact="utter_bye"
        ):
            for text in utter_bye:
                self.add_text_response(text, "utter_bye", bot, user)
        steps_goodbye = [
            {"name": "bye", "type": "INTENT"},
            {"name": "utter_bye", "type": "BOT"},
        ]
        rule_bye = {"name": "Bye", "steps": steps_goodbye, "type": "RULE"}
        self.add_complex_story(rule_bye, bot, user)

        self.add_intent("greet", bot, user, is_integration=False)
        examples_greet = next(
            intent["examples"] for intent in data["nlu"] if intent["intent"] == "greet"
        )
        list(
            self.add_training_example(
                examples_greet, "greet", bot, user, is_integration=False
            )
        )
        utter_greet_exmp = utterance["responses"]["utter_greet"]
        utter_greet = [item["text"] for item in utter_greet_exmp]
        if not Utility.is_exist(
                Responses,
                raise_error=False,
                bot=bot,
                status=True,
                name__iexact="utter_greet",
        ):
            for text in utter_greet:
                self.add_text_response(text, "utter_greet", bot, user)
        steps_greet = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        rule_greet = {"name": "Greet", "steps": steps_greet, "type": "RULE"}
        self.add_complex_story(rule_greet, bot, user)

    def add_synonym(self, synonym_name: Text, bot, user):
        """
        add a synonym
        :param synonym_name: name of synonym
        :param bot: bot Id
        :param user: user Id
        """
        if not Utility.check_empty_string(synonym_name) and Utility.special_match(synonym_name):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        Utility.is_exist(
            Synonyms,
            raise_error=True,
            exp_message="Synonym already exists!",
            status=True,
            bot=bot,
            name__iexact=synonym_name,
        )
        synonym = Synonyms()
        synonym.name = synonym_name
        synonym.user = user
        synonym.bot = bot
        return synonym.save().id.__str__()

    def add_synonym_value(self, value: Text, synonym_name: Text, bot, user):
        """
        add a synonym value
        :param value: synonym value
        :param synonym_name: synonym_name
        :param bot: bot Id
        :user user: user Id
        """
        Utility.is_exist(
            Synonyms,
            raise_error=False,
            exp_message="Synonym does not exist!",
            name__iexact=synonym_name,
            bot=bot,
            status=True,
        )

        synonym = list(
            EntitySynonyms.objects(
                name__exact=synonym_name, bot=bot, status=True, value__exact=value
            )
        )
        if len(synonym):
            raise AppException("Synonym value already exists")
        entity_synonym = EntitySynonyms()
        entity_synonym.name = synonym_name
        entity_synonym.value = value
        entity_synonym.user = user
        entity_synonym.bot = bot
        return entity_synonym.save().id.__str__()

    def add_synonym_values(self, synonyms_dict: Dict, bot, user):
        """
        add values for a synonym
        :param synonyms_dict: dict for synonym and values
        :param bot: bot ID
        :param user: user ID
        """
        if Utility.check_empty_string(synonyms_dict.get("name")):
            raise AppException("Synonym name cannot be an empty!")
        if not synonyms_dict.get("value"):
            raise AppException("Synonym value cannot be an empty!")

        synonym_exist = Utility.is_exist(
            Synonyms,
            raise_error=False,
            name__iexact=synonyms_dict.get("name"),
            bot=bot,
            status=True,
        )
        if not synonym_exist:
            raise AppException("Synonym does not exist!")

        empty_element = any(
            [Utility.check_empty_string(elem) for elem in synonyms_dict.get("value")]
        )
        if empty_element:
            raise AppException("Synonym value cannot be an empty!")
        synonym = list(
            EntitySynonyms.objects(
                name__iexact=synonyms_dict["name"], bot=bot, status=True
            )
        )
        value_list = set(item.value for item in synonym)
        check = any(item in value_list for item in synonyms_dict.get("value"))
        if check:
            raise AppException("Synonym value already exists")
        added_values = []
        for val in synonyms_dict.get("value"):
            entity_synonym = EntitySynonyms()
            entity_synonym.name = synonyms_dict["name"]
            entity_synonym.value = val
            entity_synonym.user = user
            entity_synonym.bot = bot
            id = entity_synonym.save().id.__str__()
            added_values.append({"_id": id, "value": val})
        return added_values

    def edit_synonym(
            self, value_id: Text, value: Text, name: Text, bot: Text, user: Text
    ):
        """
        update the synonym value
        :param value_id: value id against which the synonym is updated
        :param value: synonym value
        :param name: synonym name
        :param bot: bot id
        :param user: user id
        :return: None
        :raises: AppException
        """
        if not Utility.check_empty_string(name) and Utility.special_match(name):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        values = list(
            EntitySynonyms.objects(
                name__iexact=name, value__exact=value, bot=bot, status=True
            )
        )
        if values:
            raise AppException("Synonym value already exists")
        try:
            val = EntitySynonyms.objects(bot=bot, status=True, name__exact=name).get(
                id=value_id
            )
            val.value = value
            val.user = user
            val.timestamp = datetime.utcnow()
            val.save()
        except DoesNotExist:
            raise AppException("Synonym value does not exist!")

    def delete_synonym(self, id: str, bot: str, user: str = None):
        """
        delete the synonym and its values
        :param id: synonym id
        :param bot: bot id
        :param user: user id
        """
        try:
            synonym = Synonyms.objects(bot=bot, status=True).get(id=id)
            Utility.hard_delete_document(
                [EntitySynonyms], bot=bot, status=True, name__iexact=synonym.name, user=user
            )
            Utility.delete_documents(synonym, user)
        except DoesNotExist as e:
            raise AppException(e)

    def delete_synonym_value(self, synonym_name: str, value_id: str, bot: str, user: str = None):
        """
        delete particular synonym value
        :param synonym_name: name of synonym
        :param value_id: value id
        :param bot: bot_id
        """
        if not (synonym_name and synonym_name.strip()):
            raise AppException("Synonym cannot be empty or spaces")
        try:
            synonym_value = EntitySynonyms.objects(
                bot=bot, status=True, name__exact=synonym_name
            ).get(id=value_id)
            Utility.delete_documents(synonym_value, user)
        except DoesNotExist as e:
            raise AppException(e)

    def get_synonym_values(self, name: Text, bot: Text):
        """
        fetch all the synonym values
        :param name: synonym name
        :param bot: bot id
        :return: yields the values
        """
        values = EntitySynonyms.objects(
            bot=bot, status=True, name__iexact=name
        ).order_by("-timestamp")
        for value in values:
            yield {
                "_id": value.id.__str__(),
                "value": value.value,
                "synonym": value.name,
            }

    def add_utterance_name(
            self,
            name: Text,
            bot: Text,
            user: Text,
            form_attached: str = None,
            raise_error_if_exists: bool = False,
    ):
        if Utility.check_empty_string(name):
            raise AppException("Name cannot be empty")

        if name and Utility.special_match(name):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        try:
            Utterances.objects(bot=bot, status=True, name__iexact=name).get()
            if raise_error_if_exists:
                raise AppException("Utterance exists")
        except DoesNotExist as e:
            logging.info(e)
            Utterances(
                name=name, form_attached=form_attached, bot=bot, user=user
            ).save()

    def get_utterances(self, bot: Text):
        utterances = Utterances.objects(bot=bot, status=True).order_by("-timestamp")
        for utterance in utterances:
            utterance = utterance.to_mongo().to_dict()
            utterance["_id"] = utterance["_id"].__str__()
            utterance.pop("status")
            utterance.pop("timestamp")
            utterance.pop("bot")
            utterance.pop("user")
            yield utterance

    def delete_utterance_name(self, name: Text, bot: Text, raise_exc: bool = False, user: str = None):
        try:
            utterance = Utterances.objects(
                name__iexact=name, bot=bot, status=True
            ).get()
            if not Utility.check_empty_string(utterance.form_attached):
                if raise_exc:
                    raise AppException(
                        f"Utterance cannot be deleted as it is linked to form: {utterance.form_attached}"
                    )
            else:
                Utility.delete_documents(utterance, user)
        except DoesNotExist as e:
            logging.info(e)
            if raise_exc:
                raise AppException("Utterance not found")

    def get_training_data_count(self, bot: Text):
        intents_count = list(
            Intents.objects(bot=bot, status=True, name__nin=DEFAULT_INTENTS).aggregate(
                [
                    {
                        "$lookup": {
                            "from": "training_examples",
                            "let": {"bot_id": bot, "name": "$name"},
                            "pipeline": [
                                {"$match": {"bot": bot, "status": True}},
                                {
                                    "$match": {
                                        "$expr": {
                                            "$and": [{"$eq": ["$intent", "$$name"]}]
                                        }
                                    }
                                },
                                {"$count": "count"},
                            ],
                            "as": "intents_count",
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "name": 1,
                            "count": {"$first": "$intents_count.count"},
                        }
                    },
                ]
            )
        )

        utterances_count = list(
            Utterances.objects(bot=bot, status=True).aggregate(
                [
                    {
                        "$lookup": {
                            "from": "responses",
                            "let": {"bot_id": bot, "utterance": "$name"},
                            "pipeline": [
                                {"$match": {"bot": bot, "status": True}},
                                {
                                    "$match": {
                                        "$expr": {
                                            "$and": [{"$eq": ["$name", "$$utterance"]}]
                                        }
                                    }
                                },
                                {"$count": "count"},
                            ],
                            "as": "responses_count",
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "name": 1,
                            "count": {"$first": "$responses_count.count"},
                        }
                    },
                ]
            )
        )

        return {"intents": intents_count, "utterances": utterances_count}

    @staticmethod
    def get_bot_settings(bot: Text, user: Text):
        try:
            settings = BotSettings.objects(bot=bot, status=True).get()
        except DoesNotExist as e:
            logging.info(e)
            settings = BotSettings(bot=bot, user=user).save()
        return settings

    @staticmethod
    def add_demo_request(**kwargs):
        first_name = kwargs.get("first_name")
        last_name = kwargs.get("last_name")

        if not Utility.special_match(first_name, search=re.compile(r"^[a-zA-Z0-9 _]+$").search):
            raise AppException("First name can only contain letters, numbers, spaces and underscores.")

        if not Utility.special_match(last_name, search=re.compile(r"^[a-zA-Z0-9 _]+$").search):
            raise AppException("Last name can only contain letters, numbers, spaces and underscores.")
        try:
            logs = DemoRequestLogs(
                first_name=kwargs.get("first_name"),
                last_name=kwargs.get("last_name"),
                email=kwargs.get("email"),
                phone=kwargs.get("phone", None),
                message=kwargs.get("message", None),
                status=kwargs.get("status", DEMO_REQUEST_STATUS.REQUEST_RECEIVED.value),
                recaptcha_response=kwargs.get("recaptcha_response", None),
            ).save()
        except Exception as e:
            logging.error(str(e))

    @staticmethod
    def edit_bot_settings(bot_settings: dict, bot: Text, user: Text):
        """
        Update bot settings with new values.
        :param bot_settings: bot settings values
        :param bot: bot id
        :param user: user id
        :return: None
        """
        if not Utility.is_exist(BotSettings, raise_error=False, bot=bot, status=True):
            raise AppException(f"Bot Settings for the bot not found")

        settings = BotSettings.objects(bot=bot, status=True).get()
        analytics = Analytics(**bot_settings.get("analytics"))
        settings.update(
            set__analytics=analytics, set__user=user, set__timestamp=datetime.utcnow()
        )

    @staticmethod
    def enable_llm_faq(bot: Text, user: Text):
        bot_settings = MongoProcessor.get_bot_settings(bot, user)
        bot_settings.llm_settings.enable_faq = True
        bot_settings.save()

    def save_chat_client_config(self, config: dict, bot: Text, user: Text):
        from kairon.shared.account.processor import AccountProcessor

        client_config = self.get_chat_client_config(bot, user)
        white_listed_domain = (
            ["*"] if not config.__contains__("whitelist") else config.pop("whitelist")
        )
        if client_config.config.get("headers"):
            client_config.config["headers"].pop("authorization", None)

        if config.get("multilingual") and config["multilingual"].get("bots"):
            accessible_bots = AccountProcessor.get_accessible_multilingual_bots(
                bot, user
            )
            enabled_bots = list(
                filter(
                    lambda bot_info: bot_info.get("is_enabled"),
                    config["multilingual"]["bots"],
                )
            )
            enabled_bots = set(map(lambda bot_info: bot_info["id"], enabled_bots))
            if not enabled_bots:
                raise AppException("At least one bot should be enabled!")
            for bot_info in accessible_bots:
                bot_info["is_enabled"] = (
                    True if bot_info["id"] in enabled_bots else False
                )
            client_config.config["multilingual"]["bots"] = accessible_bots

        client_config.config = config
        client_config.user = user
        client_config.white_listed_domain = white_listed_domain
        client_config.save()

    def get_chat_client_config_url(self, bot: Text, user: Text, **kwargs):
        from kairon.shared.auth import Authentication

        request = kwargs.get("request")
        account = kwargs.get("account")
        bot_account = kwargs.get("bot_account")
        ip_info = Utility.get_client_ip(request)
        geo_location = (
                PluginFactory.get_instance(PluginTypes.ip_info.value).execute(ip=ip_info)
                or {}
        )
        data = {"ip_info": ip_info, "geo_location": geo_location}
        MeteringProcessor.add_metrics(bot, account, MetricType.user_metrics, **data)
        MeteringProcessor.add_metrics(bot, bot_account, MetricType.user_metrics, **data)
        access_token, _ = Authentication.generate_integration_token(
            bot,
            user,
            ACCESS_ROLES.TESTER.value,
            access_limit=["/api/bot/.+/chat/client/config$"],
            token_type=TOKEN_TYPE.DYNAMIC.value,
            expiry=1440
        )
        url = urljoin(
            Utility.environment["model"]["agent"].get("url"),
            f"/api/bot/{bot}/chat/client/config/",
        )
        url = urljoin(url, access_token)
        return url

    def get_client_config_using_uid(self, bot: Text, token_claims: Dict):
        config = self.get_chat_client_config(
            bot, token_claims["sub"], is_client_live=True
        )
        return config.to_mongo().to_dict()

    def get_chat_client_config(
            self, bot: Text, user: Text, is_client_live: bool = False
    ):
        from kairon.shared.auth import Authentication
        from kairon.shared.account.processor import AccountProcessor

        AccountProcessor.get_bot_and_validate_status(bot)
        bot_settings = self.get_bot_settings(bot, user)
        try:
            client_config = ChatClientConfig.objects(bot=bot, status=True).get()
            client_config.config["whitelist"] = client_config.white_listed_domain
        except DoesNotExist as e:
            logging.info(e)
            config = Utility.load_json_file(
                "./template/chat-client/default-config.json"
            )
            client_config = ChatClientConfig(config=config, bot=bot, user=user)
        if not client_config.config.get('headers'):
            client_config.config['headers'] = {}
        if not client_config.config['headers'].get('X-USER'):
            client_config.config['headers']['X-USER'] = user
        client_config.config['api_server_host_url'] = Utility.environment['app']['server_url']
        client_config.config['nudge_server_url'] = Utility.environment['nudge']['server_url']
        client_config.config['live_agent_socket_url'] = Utility.environment['live_agent']['live_agent_socket_url']
        client_config.config['live_agent_enabled'] = LiveAgentHandler.is_live_agent_service_available(bot)
        token, refresh_token = Authentication.generate_integration_token(
            bot,
            user,
            expiry=bot_settings.chat_token_expiry,
            access_limit=[
                "/api/bot/.+/chat",
                "/api/bot/.+/agent/live/.+",
                "/api/bot/.+/conversation",
                "/api/bot/.+/metric/user/logs/user_metrics",
            ],
            token_type=TOKEN_TYPE.DYNAMIC.value,
        )
        iat = datetime.now(tz=timezone.utc).replace(microsecond=0).replace(second=0)
        access_token_expiry = iat + timedelta(minutes=bot_settings.chat_token_expiry)
        access_token_expiry = access_token_expiry.timestamp()
        refresh_token_expiry = iat + timedelta(
            minutes=bot_settings.refresh_token_expiry
        )
        refresh_token_expiry = refresh_token_expiry.timestamp()
        client_config.config["headers"]["authorization"] = {}
        client_config.config["headers"]["authorization"]["access_token"] = token
        client_config.config["headers"]["authorization"]["token_type"] = "Bearer"
        client_config.config["headers"]["authorization"][
            "refresh_token"
        ] = f"{refresh_token}"
        client_config.config["headers"]["authorization"][
            "access_token_ttl"
        ] = bot_settings.chat_token_expiry
        client_config.config["headers"]["authorization"][
            "refresh_token_ttl"
        ] = bot_settings.refresh_token_expiry
        client_config.config["headers"]["authorization"][
            "access_token_expiry"
        ] = access_token_expiry
        client_config.config["headers"]["authorization"][
            "refresh_token_expiry"
        ] = refresh_token_expiry
        client_config.config["chat_server_base_url"] = Utility.environment["model"][
            "agent"
        ]["url"]
        if client_config.config.get("multilingual") and client_config.config[
            "multilingual"
        ].get("enable"):
            accessible_bots = AccountProcessor.get_accessible_multilingual_bots(
                bot, user
            )
            enabled_bots = {}
            if client_config.config["multilingual"].get("bots"):
                enabled_bots = list(
                    filter(
                        lambda bot_info: bot_info.get("is_enabled"),
                        client_config.config["multilingual"]["bots"],
                    )
                )
                enabled_bots = set(map(lambda bot_info: bot_info["id"], enabled_bots))
            if is_client_live and bot not in enabled_bots:
                raise AppException("Bot is disabled. Please use a valid bot.")
            client_config.config["multilingual"]["bots"] = []
            for bot_info in accessible_bots:
                bot_info["is_enabled"] = (
                    True if bot_info["id"] in enabled_bots else False
                )
                if bot_info["is_enabled"] or not is_client_live:
                    token, _ = Authentication.generate_integration_token(
                        bot_info["id"],
                        user,
                        expiry=bot_settings.chat_token_expiry,
                        access_limit=[
                            "/api/bot/.+/chat",
                            "/api/bot/.+/agent/live/.+",
                            "/api/bot/.+/conversation",
                            "/api/bot/.+/metric/user/logs/{log_type}",
                        ],
                        token_type=TOKEN_TYPE.DYNAMIC.value,
                    )
                    bot_info["authorization"] = f"Bearer {token}"
                    client_config.config["multilingual"]["bots"].append(bot_info)

        return client_config

    def add_regex(self, regex_dict: Dict, bot, user):
        if Utility.check_empty_string(
                regex_dict.get("name")
        ) or Utility.check_empty_string(regex_dict.get("pattern")):
            raise AppException("Regex name and pattern cannot be empty or blank spaces")

        if regex_dict.get("name") and Utility.special_match(regex_dict.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        try:
            RegexFeatures.objects(
                name__iexact=regex_dict.get("name"), bot=bot, status=True
            ).get()
            raise AppException("Regex name already exists!")
        except DoesNotExist:
            regex = RegexFeatures()
            regex.name = regex_dict.get("name")
            regex.pattern = regex_dict.get("pattern")
            regex.bot = bot
            regex.user = user
            regex_id = regex.save().id.__str__()
            return regex_id

    def edit_regex(self, regex_dict: Dict, bot, user):
        if Utility.check_empty_string(
                regex_dict.get("name")
        ) or Utility.check_empty_string(regex_dict.get("pattern")):
            raise AppException("Regex name and pattern cannot be empty or blank spaces")

        if regex_dict.get("name") and Utility.special_match(regex_dict.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        try:
            regex = RegexFeatures.objects(
                name__iexact=regex_dict.get("name"), bot=bot, status=True
            ).get()
            regex.pattern = regex_dict.get("pattern")
            regex.user = user
            regex.timestamp = datetime.utcnow()
            regex.save()
        except DoesNotExist:
            raise AppException("Regex name does not exist!")

    def delete_regex(self, regex_name: Text, bot: Text, user: Text):
        """
        deletes regex pattern
        :param regex_name: regex name
        :param user: user id
        :param bot: bot id
        :return: AppException
        """

        try:
            regex = RegexFeatures.objects(
                name__iexact=regex_name, bot=bot, status=True
            ).get()
            Utility.delete_documents(regex, user)
        except DoesNotExist:
            raise AppException("Regex name does not exist.")

    def add_lookup(self, lookup_name, bot, user):
        """
        add a lookup table
        :param lookup_name: name of the lookup
        :param bot: bot id
        :param user: user id
        """
        if not Utility.check_empty_string(lookup_name) and Utility.special_match(lookup_name):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        Utility.is_exist(
            Lookup,
            raise_error=True,
            exp_message="Lookup already exists!",
            status=True,
            bot=bot,
            name__iexact=lookup_name,
        )
        lookup = Lookup()
        lookup.name = lookup_name
        lookup.user = user
        lookup.bot = bot
        lookup.save()
        return lookup.id.__str__()

    def add_lookup_value(self, lookup_name, lookup_value, bot, user):
        """
        add a lookup value
        :param lookup_name: name of the lookup
        :param lookup_value: value of the lookup
        :param bot: bot id
        :param user: user id
        """
        if not Utility.check_empty_string(lookup_name) and Utility.special_match(lookup_name):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        lookup_exist = Utility.is_exist(
            Lookup, raise_error=False, name__iexact=lookup_name, bot=bot, status=True
        )
        if not lookup_exist:
            raise AppException("Lookup does not exists")
        Utility.is_exist(
            LookupTables,
            raise_error=True,
            exp_message="Lookup value already exists",
            value__exact=lookup_value,
            bot=bot,
            status=True,
        )
        lookup_table = LookupTables()
        lookup_table.name = lookup_name
        lookup_table.value = lookup_value
        lookup_table.user = user
        lookup_table.bot = bot
        lookup_table.save()
        return lookup_table.id.__str__()

    def add_lookup_values(self, lookup_dict: Dict, bot, user):
        """
        add values for a lookup
        :param lookup_dict: lookup and its values
        :param bot: bot ID
        :param user: user ID
        """
        if Utility.check_empty_string(lookup_dict.get("name")):
            raise AppException("Lookup cannot be an empty string")
        if not lookup_dict.get("value"):
            raise AppException("Lookup value cannot be an empty string")

        lookup_exist = Utility.is_exist(
            Lookup,
            raise_error=False,
            name__iexact=lookup_dict.get("name"),
            bot=bot,
            status=True,
        )
        if not lookup_exist:
            raise AppException("Lookup does not exists")

        empty_element = any(
            [Utility.check_empty_string(elem) for elem in lookup_dict.get("value")]
        )
        if empty_element:
            raise AppException("Lookup value cannot be an empty string")
        lookup = list(
            LookupTables.objects(name__iexact=lookup_dict["name"], bot=bot, status=True)
        )
        value_list = set(item.value for item in lookup)
        check = any(item in value_list for item in lookup_dict.get("value"))
        if check:
            raise AppException("Lookup value already exists")
        added_values = []
        for val in lookup_dict.get("value"):
            lookup_table = LookupTables()
            lookup_table.name = lookup_dict["name"]
            lookup_table.value = val
            lookup_table.user = user
            lookup_table.bot = bot
            lookup_table.save()
            id = lookup_table.id.__str__()
            added_values.append({"_id": id, "value": val})
        return added_values

    def get_lookups(self, bot: Text):
        """
        fetch all the lookup table name
        :param name: table name
        :param bot: bot id
        :return: yields the values
        """
        lookups = Lookup.objects(bot=bot, status=True).order_by("-timestamp")
        for lookup in lookups:
            yield {"_id": lookup.id.__str__(), "lookup": lookup.name}

    def get_lookup_values(self, name: Text, bot: Text):
        """
        fetch all the lookup table values
        :param name: table name
        :param bot: bot id
        :return: yields the values
        """
        values = LookupTables.objects(bot=bot, status=True, name__iexact=name).order_by(
            "-timestamp"
        )
        for value in values:
            yield {
                "_id": value.id.__str__(),
                "value": value.value,
                "lookup": value.name,
            }

    def edit_lookup_value(
            self, lookup_id: Text, value: Text, name: Text, bot: Text, user: Text
    ):
        """
        update the lookup table value
        :param id: value id against which the lookup table is updated
        :param value: table value
        :param name: lookup table name
        :param bot: bot id
        :param user: user id
        :return: None
        :raises: AppException
        """
        if not Utility.check_empty_string(name) and Utility.special_match(name):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        lookup_exist = Utility.is_exist(
            Lookup, raise_error=False, name__iexact=name, bot=bot, status=True
        )
        if not lookup_exist:
            raise AppException("Lookup does not exists")

        lookup = list(LookupTables.objects(name__iexact=name, bot=bot, status=True))
        value_list = set(item.value for item in lookup)
        if value in value_list:
            raise AppException("Lookup value already exists")
        try:
            val = LookupTables.objects(bot=bot, status=True, name__iexact=name).get(
                id=lookup_id
            )
            val.value = value
            val.user = user
            val.timestamp = datetime.utcnow()
            val.save()
        except DoesNotExist:
            raise AppException("Lookup value does not exist!")

    def delete_lookup(self, lookup_id: str, bot: str, user: str = None):
        """
        delete lookup and its value
        :param lookup_id: lookup ID
        :param bot: bot id
        """
        if not (lookup_id and lookup_id.strip()):
            raise AppException("Lookup Id cannot be empty or spaces")
        try:
            lookup = Lookup.objects(bot=bot, status=True).get(id=lookup_id)
            Utility.hard_delete_document(
                [LookupTables], bot=bot, name__exact=lookup.name
            )
            Utility.delete_documents(lookup, user)
        except DoesNotExist:
            raise AppException("Invalid lookup!")

    def delete_lookup_value(self, lookup_value_id: str, lookup_name: str, bot: str, user: str = None):
        """
        delete a lookup value
        :param lookup_value_id: value ID
        :param lookup_name: lookup name
        :param bot: bot ID
        """
        if not (lookup_value_id and lookup_value_id.strip()):
            raise AppException("Lookup value Id cannot be empty or spaces")
        try:
            lookup_value = LookupTables.objects(
                bot=bot, status=True, name__iexact=lookup_name
            ).get(id=lookup_value_id)
            Utility.delete_documents(lookup_value, user)
        except DoesNotExist as e:
            raise AppException(e)

    def __add_or_update_form_validations(
            self, name: Text, path: list, bot: Text, user: Text
    ):
        existing_slot_validations = FormValidationAction.objects(
            name=name, bot=bot, status=True
        )
        existing_validations = {
            validation.slot for validation in list(existing_slot_validations)
        }
        slots_required_for_form = {slots_to_fill["slot"] for slots_to_fill in path}

        for slots_to_fill in path:
            slot = slots_to_fill.get("slot")
            slot_set = slots_to_fill.get("slot_set", {})
            validation_semantic = slots_to_fill.get("validation_semantic")
            if slot in existing_validations:
                validation = existing_slot_validations.get(slot=slot)
                validation.validation_semantic = validation_semantic
                validation.valid_response = slots_to_fill.get("valid_response")
                validation.invalid_response = slots_to_fill.get("invalid_response")
                validation.is_required = slots_to_fill.get("is_required")
                validation.slot_set.type = slot_set.get("type")
                validation.slot_set.value = slot_set.get("value")
                validation.user = user
                validation.timestamp = datetime.utcnow()
                validation.save()
            else:
                FormValidationAction(
                    name=name,
                    slot=slot,
                    validation_semantic=validation_semantic,
                    bot=bot,
                    user=user,
                    valid_response=slots_to_fill.get("valid_response"),
                    invalid_response=slots_to_fill.get("invalid_response"),
                    is_required=slots_to_fill.get("is_required"),
                    slot_set=FormSlotSet(**slot_set),
                ).save()

        slot_validations_to_delete = existing_validations.difference(
            slots_required_for_form
        )
        for slot in slot_validations_to_delete:
            validation = existing_slot_validations.get(slot=slot)
            validation.delete()

    def __add_form_responses(
            self, responses: list, utterance_name: Text, form: Text, bot: Text, user: Text
    ):
        for resp in responses:
            self.add_response(
                utterances={"text": resp.strip()},
                name=utterance_name,
                form_attached=form,
                bot=bot,
                user=user,
            )

    def __validate_slots_attached_to_form(self, required_slots: set, bot: Text):
        any_slots = set(
            Slots.objects(bot=bot, type="any", status=True, name__in=required_slots).values_list(
                "name"
            )
        )
        if any_slots:
            raise AppException(
                f"form will not accept any type slots: {any_slots}"
            )

        existing_slots = set(
            Slots.objects(bot=bot, status=True, name__in=required_slots).values_list(
                "name"
            )
        )
        existing_slot_mappings = SlotMapping.objects(
            bot=bot, status=True, slot__in=required_slots
        ).values_list("slot")
        if required_slots.difference(existing_slots).__len__() > 0:
            raise AppException(
                f"slots not exists: {required_slots.difference(existing_slots)}"
            )
        if required_slots.difference(existing_slot_mappings).__len__() > 0:
            raise AppException(
                f"Mapping is required for slot: {required_slots.difference(existing_slot_mappings)}"
            )

    def add_form(self, name: str, path: list, bot: Text, user: Text):
        if Utility.check_empty_string(name):
            raise AppException("Form name cannot be empty or spaces")

        self.__check_for_form_and_action_existance(bot, name)

        Utility.is_exist(
            Forms,
            f'Form with name "{name}" exists',
            name__iexact=name,
            bot=bot,
            status=True,
        )
        Utility.is_valid_action_name(name, bot, Forms)
        required_slots = [
            slots_to_fill["slot"]
            for slots_to_fill in path
            if not Utility.check_empty_string(slots_to_fill["slot"])
        ]
        self.__validate_slots_attached_to_form(set(required_slots), bot)
        for slots_to_fill in path:
            self.__add_form_responses(
                slots_to_fill["ask_questions"],
                utterance_name=f'utter_ask_{name}_{slots_to_fill["slot"]}',
                form=name,
                bot=bot,
                user=user,
            )
        form_id = (
            Forms(name=name, required_slots=required_slots, bot=bot, user=user)
            .save()
            .id.__str__()
        )
        self.__add_or_update_form_validations(f"validate_{name}", path, bot, user)
        self.add_action(
            f"validate_{name}",
            bot,
            user,
            action_type=ActionType.form_validation_action.value,
        )
        return form_id

    @staticmethod
    def list_forms(bot: Text):
        for form in Forms.objects(bot=bot, status=True):
            form = form.to_mongo().to_dict()
            form["_id"] = form["_id"].__str__()
            form.pop("bot")
            form.pop("user")
            form.pop("status")
            yield form

    def get_form(self, form_id: Text, bot: Text):
        try:
            form = (
                Forms.objects(id=form_id, bot=bot, status=True)
                .get()
                .to_mongo()
                .to_dict()
            )
            name = form["name"]
            form["_id"] = form["_id"].__str__()
            form_validations = FormValidationAction.objects(
                name=f"validate_{name}", bot=bot, status=True
            )
            slots_with_validations = {
                validation.slot for validation in form_validations
            }
            slot_mapping = []
            for slot in form.get("required_slots") or []:
                utterance = list(
                    self.get_response(name=f"utter_ask_{name}_{slot}", bot=bot)
                )
                mapping = {
                    "slot": slot,
                    "ask_questions": utterance,
                    "validation": None,
                    "valid_response": None,
                    "invalid_response": None,
                    "slot_set": {},
                }
                if slot in slots_with_validations:
                    validations = form_validations.get(slot=slot).to_mongo().to_dict()
                    mapping["validation_semantic"] = validations.get(
                        "validation_semantic"
                    )
                    mapping["valid_response"] = validations.get("valid_response")
                    mapping["invalid_response"] = validations.get("invalid_response")
                    mapping["is_required"] = validations.get("is_required")
                    mapping["slot_set"]["type"] = validations["slot_set"].get("type")
                    mapping["slot_set"]["value"] = validations["slot_set"].get("value")
                slot_mapping.append(mapping)
            form["settings"] = slot_mapping
            return form
        except DoesNotExist as e:
            logging.info(str(e))
            raise AppException("Form does not exists")

    def edit_form(self, name: str, path: list, bot: Text, user: Text):
        try:
            form = Forms.objects(name=name, bot=bot, status=True).get()
            slots_required_for_form = [slots_to_fill["slot"] for slots_to_fill in path]
            self.__validate_slots_attached_to_form(set(slots_required_for_form), bot)
            existing_slots_for_form = set(form.required_slots)
            slots_to_remove = existing_slots_for_form.difference(
                set(slots_required_for_form)
            )
            new_slots_to_add = set(slots_required_for_form).difference(
                existing_slots_for_form
            )

            for slot in slots_to_remove:
                try:
                    self.delete_utterance(f"utter_ask_{name}_{slot}", bot, False, user=user)
                except AppException:
                    pass

            for slots_to_fill in path:
                slot_name = slots_to_fill["slot"]
                if slot_name in new_slots_to_add:
                    self.__add_form_responses(
                        slots_to_fill["ask_questions"],
                        utterance_name=f"utter_ask_{name}_{slot_name}",
                        form=name,
                        bot=bot,
                        user=user,
                    )
            form.required_slots = slots_required_for_form
            form.user = user
            form.timestamp = datetime.utcnow()
            form.save()
            self.__add_or_update_form_validations(f"validate_{name}", path, bot, user)
        except DoesNotExist:
            raise AppException("Form does not exists")

    def delete_form(self, name: Text, bot: Text, user: Text):
        try:
            form = Forms.objects(name=name, bot=bot, status=True).get()
            MongoProcessor.get_attached_flows(bot, name, "action")
            for slot in form.required_slots:
                try:
                    utterance_name = f"utter_ask_{name}_{slot}"
                    self.delete_utterance(utterance_name, bot, False, user=user)
                except Exception as e:
                    logging.info(str(e))
            Utility.delete_documents(form, user)
            if Utility.is_exist(
                    FormValidationAction,
                    raise_error=False,
                    name__iexact=f"validate_{name}",
                    bot=bot,
                    status=True,
            ):
                self.delete_action(f"validate_{name}", bot, user)
        except DoesNotExist:
            raise AppException(f'Form "{name}" does not exists')

    def add_or_update_slot_mapping(self, mapping: dict, bot: Text, user: Text):
        """
        Add/update slot mappings.

        :param mapping: slot mapping request
        :param bot: bot id
        :param user: user id
        :return: document id of the mapping
        """
        try:
            if not Utility.is_exist(
                    Slots, raise_error=False, name=mapping["slot"], bot=bot, status=True
            ):
                raise AppException(f'Slot with name \'{mapping["slot"]}\' not found')
            slot_mapping = SlotMapping.objects(
                slot=mapping["slot"], bot=bot, status=True
            ).get()
        except DoesNotExist:
            slot_mapping = SlotMapping(slot=mapping["slot"], bot=bot)
        slot_mapping.mapping = mapping["mapping"]
        if mapping["mapping"].get("conditions"):
            slot_mapping.form_name = mapping["mapping"]["condition"][0]["active_loop"]
        slot_mapping.user = user
        slot_mapping.timestamp = datetime.utcnow()
        return slot_mapping.save().id.__str__()

    def add_slot_mapping(self, mapping: dict, bot: Text, user: Text):
        """
        Add slot mapping.

        :param mapping: slot mapping request
        :param bot: bot id
        :param user: user id
        :return: document id of the mapping
        """
        if not Utility.is_exist(
                Slots, raise_error=False, name=mapping["slot"], bot=bot, status=True
        ):
            raise AppException(f'Slot with name "{mapping["slot"]}" not found')
        form_name = None
        if mapping["mapping"].get("conditions"):
            form_name = mapping["mapping"]["conditions"][0]["active_loop"]

        slot_mapping = SlotMapping.objects(
            slot=mapping["slot"], bot=bot, user=user, status=True, mapping=mapping["mapping"]
        ).first()
        if slot_mapping:
            raise AppException(f'Slot mapping already exists for slot: {mapping["slot"]}')

        slot_mapping = SlotMapping(
            slot=mapping["slot"],
            mapping=mapping["mapping"],
            bot=bot,
            user=user,
            form_name=form_name,
        )

        return slot_mapping.save().id.__str__()

    def update_slot_mapping(self, mapping: dict, slot_mapping_id: str):
        """
        Update slot mapping.

        :param mapping: slot mapping request
        :param slot_mapping_id: document id of the mapping
        """
        try:
            slot_mapping = SlotMapping.objects(id=slot_mapping_id, status=True).get()
            slot_mapping.mapping = mapping["mapping"]
            if mapping["mapping"].get("conditions"):
                slot_mapping.form_name = mapping["mapping"]["conditions"][0]["active_loop"]
            slot_mapping.timestamp = datetime.utcnow()
            slot_mapping.save()
        except Exception as e:
            raise AppException(e)


    def __prepare_slot_mappings(self, bot: Text):
        """
        Fetches existing slot mappings.

        :param bot: bot id
        :return: list of slot mappings for training
        """
        mappings = self.get_slot_mappings(bot)
        for mapping in mappings:
            yield {mapping["slot"]: mapping["mapping"]}

    def get_slot_mappings(self, bot: Text, form: Text = None, include_id=False):
        """
        Fetches existing slot mappings.

        :param bot: bot id
        :param form: retrieve slot mappings for a particular form
        :return: list of slot mappings
        """
        filter = {"bot": bot, "status": True}
        if form:
            filter["form_name"] = form
        pipeline = [{"$match": filter}]
        if include_id:
            pipeline.append({"$addFields": {"mapping._id": {"$toString": "$_id"}}})

        pipeline.extend([
            {"$group": {"_id": "$slot", "mapping": {"$push": "$mapping"}}},
            {"$project": {"_id": 0, "slot": "$_id", "mapping": "$mapping"}}
        ])

        return SlotMapping.objects.aggregate(pipeline)

    def delete_slot_mapping(self, name: Text, bot: Text, user: Text):
        """
        Delete slot mapping.

        :param name: Name of slot for which mapping exists.
        :param bot: bot id
        :param user: user id
        :return: document id of the mapping
        """
        try:
            forms_with_slot = Forms.objects(
                bot=bot, status=True, required_slots__in=[name]
            )
            if len(forms_with_slot) > 0:
                raise AppException(
                    f'Slot mapping is required for form: {[form["name"] for form in forms_with_slot]}'
                )
            slot_mappings = SlotMapping.objects(slot=name, bot=bot, status=True)
            if len(slot_mappings) == 0:
                raise DoesNotExist
            slot_mappings.delete()
        except DoesNotExist:
            raise AppException(f"No slot mapping exists for slot: {name}")

    def delete_singular_slot_mapping(self, slot_mapping_id: Text):
        """
        Delete slot mapping.

        :param slot_mapping_id: document id of the mapping
        :return: None
        """
        try:
            slot_mapping = SlotMapping.objects(id=slot_mapping_id, status=True).get()
            slot_mapping.delete()
        except DoesNotExist:
            raise AppException("No slot mapping exists")

    def add_slot_set_action(self, action: dict, bot: Text, user: Text):
        set_slots = []
        if Utility.check_empty_string(action.get("name")):
            raise AppException("name cannot be empty or spaces")
        if action.get("name") and Utility.special_match(action.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        Utility.is_valid_action_name(action.get("name"), bot, SlotSetAction)
        for slot in action["set_slots"]:
            if Utility.check_empty_string(slot.get("name")):
                raise AppException("slot name cannot be empty or spaces")
            if not Utility.is_exist(
                    Slots, raise_error=False, name=slot["name"], bot=bot, status=True
            ):
                raise AppException(f'Slot with name "{slot["name"]}" not found')
            set_slots.append(SetSlots(**slot))
        SlotSetAction(
            name=action["name"], set_slots=set_slots, bot=bot, user=user
        ).save()
        self.add_action(
            action["name"], bot, user, action_type=ActionType.slot_set_action.value
        )

    @staticmethod
    def list_slot_set_actions(bot: Text, with_doc_id: bool = True):
        if with_doc_id:
            actions = (
                SlotSetAction.objects(bot=bot, status=True)
                .exclude("bot", "user", "timestamp", "status")
                .to_json()
            )
            actions = json.loads(actions)
            slot_set_actions = [
                {**action, "_id": action["_id"]["$oid"].__str__()} for action in actions
            ]
        else:
            actions = (
                SlotSetAction.objects(bot=bot, status=True)
                .exclude("id", "bot", "user", "timestamp", "status")
                .to_json()
            )
            slot_set_actions = json.loads(actions)
        return slot_set_actions

    @staticmethod
    def edit_slot_set_action(action: dict, bot: Text, user: Text):
        if action.get("name") and Utility.special_match(action.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        set_slots = []
        try:
            for slot in action["set_slots"]:
                if Utility.check_empty_string(slot.get("name")):
                    raise AppException("slot name cannot be empty or spaces")
                if not Utility.is_exist(
                        Slots, raise_error=False, name=slot["name"], bot=bot, status=True
                ):
                    raise AppException(f'Slot with name "{slot["name"]}" not found')
                set_slots.append(SetSlots(**slot))
            slot_set_action = SlotSetAction.objects(
                name=action.get("name"), bot=bot, status=True
            ).get()
            slot_set_action.set_slots = set_slots
            slot_set_action.user = user
            slot_set_action.timestamp = datetime.utcnow()
            slot_set_action.save()
        except DoesNotExist:
            raise AppException(
                f'Slot setting action with name "{action.get("name")}" not found'
            )

    def delete_action(self, name: Text, bot: Text, user: Text):
        """
        soft delete an action
        :param name: action name
        :param bot: bot id
        :param user: user id
        :return:
        """
        try:
            action = Actions.objects(name=name, bot=bot, status=True).get()

            MongoProcessor.get_attached_flows(bot, name, "action")
            MongoProcessor.check_action_usage_in_parallel_actions(bot, name)

            Utility.is_exist(
                PromptAction,
                bot=bot,
                llm_prompts__source=LlmPromptSource.action.value,
                llm_prompts__data=name,
                exp_message=f"Action with name {name} is attached with PromptAction!",
            )

            if action.type == ActionType.slot_set_action.value:
                Utility.hard_delete_document(
                    [SlotSetAction],
                    name__iexact=name,
                    bot=bot,
                    user=user
                )
            elif action.type == ActionType.form_validation_action.value:
                Utility.hard_delete_document(
                    [FormValidationAction],
                    name__iexact=name,
                    bot=bot,
                    user=user
                )
            elif action.type == ActionType.email_action.value:
                Utility.hard_delete_document(
                    [EmailActionConfig],
                    action_name__iexact=name,
                    bot=bot,
                    user=user
                )
            elif action.type == ActionType.google_search_action.value:
                Utility.hard_delete_document(
                    [GoogleSearchAction],
                    name__iexact=name,
                    bot=bot,
                    user=user
                )
            elif action.type == ActionType.jira_action.value:
                Utility.hard_delete_document(
                    [JiraAction],
                    name__iexact=name,
                    bot=bot,
                    user=user
                )
            elif action.type == ActionType.http_action.value:
                Utility.hard_delete_document(
                    [HttpActionConfig], action_name__iexact=name, bot=bot,
                    user=user
                )
            elif action.type == ActionType.zendesk_action.value:
                Utility.hard_delete_document(
                    [ZendeskAction], name__iexact=name, bot=bot,
                    user=user
                )
            elif action.type == ActionType.pipedrive_leads_action.value:
                Utility.hard_delete_document(
                    [PipedriveLeadsAction], name__iexact=name, bot=bot,
                    user=user
                )
            elif action.type == ActionType.hubspot_forms_action.value:
                Utility.hard_delete_document(
                    [HubspotFormsAction], name__iexact=name, bot=bot,
                    user=user
                )
            elif action.type == ActionType.two_stage_fallback.value:
                Utility.hard_delete_document(
                    [KaironTwoStageFallbackAction], name__iexact=name, bot=bot,
                    user=user
                )
            elif action.type == ActionType.razorpay_action.value:
                Utility.hard_delete_document(
                    [RazorpayAction], name__iexact=name, bot=bot,
                    user=user
                )
            elif action.type == ActionType.database_action.value:
                Utility.hard_delete_document(
                    [DatabaseAction], name__iexact=name, bot=bot,
                    user=user
                )
            elif action.type == ActionType.web_search_action.value:
                Utility.hard_delete_document(
                    [WebSearchAction], name__iexact=name, bot=bot,
                    user=user
                )
            elif action.type == ActionType.prompt_action.value:
                Utility.hard_delete_document([PromptAction], name__iexact=name, bot=bot, user=user)
            elif action.type == ActionType.pyscript_action.value:
                Utility.hard_delete_document(
                    [PyscriptActionConfig], name__iexact=name, bot=bot,
                    user=user
                )
            elif action.type == ActionType.schedule_action.value:
                Utility.hard_delete_document(
                    [ScheduleAction], name__iexact=name, bot=bot
                )
            elif action.type == ActionType.parallel_action.value:
                Utility.hard_delete_document(
                    [ParallelActionConfig], name__iexact=name, bot=bot
                )
            action.delete()
        except DoesNotExist:
            raise AppException(f'Action with name "{name}" not found')

    @staticmethod
    def check_action_usage_in_parallel_actions(bot: Text, name: Text):
        parallel_actions_using_action = ParallelActionConfig.objects(bot=bot, status=True, actions=name)
        if parallel_actions_using_action:
            parallel_action_names = [parallel_action.name for parallel_action in parallel_actions_using_action]
            raise AppException(
                f"Action '{name}' cannot be deleted because it is used in parallel actions: {parallel_action_names}"
            )

    def add_email_action(self, action: Dict, bot: str, user: str):
        """
        add a new Email Action
        :param action: email action configuration
        :param bot: bot id
        :param user: user id
        :return: doc id
        """
        action["bot"] = bot
        action["user"] = user
        if action.get("action_name") and Utility.special_match(action.get("action_name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        Utility.is_valid_action_name(action.get("action_name"), bot, EmailActionConfig)
        email = EmailActionConfig(**action).save().id.__str__()
        self.add_action(
            action["action_name"],
            bot,
            user,
            action_type=ActionType.email_action.value,
            raise_exception=False,
        )
        return email

    def edit_email_action(self, action: dict, bot: Text, user: Text):
        """
        update an Email Action
        :param action: email action configuration
        :param bot: bot id
        :param user: user id
        :return: None
        """
        if action.get("action_name") and Utility.special_match(action.get("action_name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        if not Utility.is_exist(
                EmailActionConfig,
                raise_error=False,
                action_name=action.get("action_name"),
                bot=bot,
                status=True,
        ):
            raise AppException(
                f'Action with name "{action.get("action_name")}" not found'
            )
        email_action = EmailActionConfig.objects(
            action_name=action.get("action_name"), bot=bot, status=True
        ).get()
        email_action.smtp_url = action["smtp_url"]
        email_action.smtp_port = action["smtp_port"]
        email_action.smtp_userid = (
            CustomActionRequestParameters(**action["smtp_userid"])
            if action.get("smtp_userid")
            else None
        )
        email_action.smtp_password = CustomActionRequestParameters(
            **action["smtp_password"]
        )
        email_action.custom_text = (
            CustomActionRequestParameters(**action["custom_text"])
            if action.get("custom_text")
            else None
        )
        email_action.from_email = CustomActionRequestParameters(**action['from_email']) if action.get('from_email') else None
        email_action.subject = action["subject"]
        email_action.to_email = CustomActionParameters(**action['to_email']) if action.get('to_email') else None
        email_action.response = action["response"]
        email_action.dispatch_bot_response = action["dispatch_bot_response"]
        email_action.tls = action["tls"]
        email_action.user = user
        email_action.timestamp = datetime.utcnow()
        email_action.save()

    def list_email_action(self, bot: Text, with_doc_id: bool = True):
        """
        List Email Action
        :param bot: bot id
        :param with_doc_id: return document id along with action configuration if True
        """
        for action in EmailActionConfig.objects(bot=bot, status=True):
            action = action.to_mongo().to_dict()
            if with_doc_id:
                action["_id"] = action["_id"].__str__()
            else:
                action.pop("_id")
            action.pop("user")
            action.pop("bot")
            action.pop("timestamp")
            action.pop("status")
            yield action

    def add_jira_action(self, action: Dict, bot: str, user: str):
        """
        Add a new Jira Action
        :param action: Jira action configuration
        :param bot: bot id
        :param user: user id
        :return: doc id
        """
        action["bot"] = bot
        action["user"] = user
        if action.get("name") and Utility.special_match(action.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        Utility.is_valid_action_name(action.get("name"), bot, JiraAction)
        jira_action = JiraAction(**action).save().id.__str__()
        self.add_action(
            action["name"],
            bot,
            user,
            action_type=ActionType.jira_action.value,
            raise_exception=False,
        )
        return jira_action

    def edit_jira_action(self, action: dict, bot: Text, user: Text):
        """
        Update a Jira Action
        :param action: Jira action configuration
        :param bot: bot id
        :param user: user id
        :return: None
        """
        if action.get("name") and Utility.special_match(action.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        if not Utility.is_exist(
                JiraAction, raise_error=False, name=action.get("name"), bot=bot, status=True
        ):
            raise AppException(f'Action with name "{action.get("name")}" not found')
        jira_action = JiraAction.objects(
            name=action.get("name"), bot=bot, status=True
        ).get()
        jira_action.url = action["url"]
        jira_action.user_name = action["user_name"]
        jira_action.api_token = CustomActionRequestParameters(**action["api_token"])
        jira_action.project_key = action["project_key"]
        jira_action.issue_type = action["issue_type"]
        jira_action.parent_key = action["parent_key"]
        jira_action.summary = action["summary"]
        jira_action.response = action["response"]
        jira_action.user = user
        jira_action.timestamp = datetime.utcnow()
        jira_action.save()

    def list_form_validation_actions(self, bot: Text):
        for action in FormValidationAction.objects(bot=bot, status=True):
            action = action.to_mongo().to_dict()
            action.pop("_id")
            action.pop("bot")
            action.pop("user")
            action.pop("timestamp")
            action.pop("status")
            yield action

    def list_jira_actions(self, bot: Text, with_doc_id: bool = True):
        """
        List Email Action
        :param bot: bot id
        :param with_doc_id: return document id along with action configuration if True
        """
        for action in JiraAction.objects(bot=bot, status=True):
            action = action.to_mongo().to_dict()
            if with_doc_id:
                action["_id"] = action["_id"].__str__()
            else:
                action.pop("_id")
            action.pop("user")
            action.pop("bot")
            action.pop("status")
            action.pop("timestamp")
            yield action

    def add_zendesk_action(self, action: Dict, bot: str, user: str):
        """
        Add a new Zendesk Action
        :param action: Zendesk action configuration
        :param bot: bot id
        :param user: user id
        :return: doc id
        """
        action["bot"] = bot
        action["user"] = user
        if action.get("name") and Utility.special_match(action.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        Utility.is_valid_action_name(action.get("name"), bot, ZendeskAction)
        zendesk_action = ZendeskAction(**action).save().id.__str__()
        self.add_action(
            action["name"],
            bot,
            user,
            action_type=ActionType.zendesk_action.value,
            raise_exception=False,
        )
        return zendesk_action

    def edit_zendesk_action(self, action: dict, bot: Text, user: Text):
        """
        Update a Zendesk Action
        :param action: Zendesk action configuration
        :param bot: bot id
        :param user: user id
        :return: None
        """
        if action.get("name") and Utility.special_match(action.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        if not Utility.is_exist(
                ZendeskAction,
                raise_error=False,
                name=action.get("name"),
                bot=bot,
                status=True,
        ):
            raise AppException(f'Action with name "{action.get("name")}" not found')
        zendesk_action = ZendeskAction.objects(
            name=action.get("name"), bot=bot, status=True
        ).get()
        zendesk_action.subdomain = action["subdomain"]
        zendesk_action.user_name = action["user_name"]
        zendesk_action.api_token = CustomActionRequestParameters(**action["api_token"])
        zendesk_action.subject = action["subject"]
        zendesk_action.response = action["response"]
        zendesk_action.user = user
        zendesk_action.timestamp = datetime.utcnow()
        zendesk_action.save()

    def list_zendesk_actions(self, bot: Text, with_doc_id: bool = True):
        """
        List Zendesk Action
        :param bot: bot id
        :param with_doc_id: return document id along with action configuration if True
        """
        for action in ZendeskAction.objects(bot=bot, status=True):
            action = action.to_mongo().to_dict()
            if with_doc_id:
                action["_id"] = action["_id"].__str__()
            else:
                action.pop("_id")
            action.pop("user")
            action.pop("bot")
            action.pop("status")
            action.pop("timestamp")
            yield action

    def add_pipedrive_action(self, action: Dict, bot: str, user: str):
        """
        Add a new Pipedrive Action
        :param action: Pipedrive action configuration
        :param bot: bot id
        :param user: user id
        :return: doc id
        """
        action["bot"] = bot
        action["user"] = user
        if action.get("name") and Utility.special_match(action.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        Utility.is_valid_action_name(action.get("name"), bot, PipedriveLeadsAction)
        pipedrive_action = PipedriveLeadsAction(**action).save().id.__str__()
        self.add_action(
            action["name"],
            bot,
            user,
            action_type=ActionType.pipedrive_leads_action.value,
            raise_exception=False,
        )
        return pipedrive_action

    def edit_pipedrive_action(self, action: dict, bot: Text, user: Text):
        """
        Update a Pipedrive Action
        :param action: Pipedrive action configuration
        :param bot: bot id
        :param user: user id
        :return: None
        """
        if action.get("name") and Utility.special_match(action.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        if not Utility.is_exist(
                PipedriveLeadsAction,
                raise_error=False,
                name=action.get("name"),
                bot=bot,
                status=True,
        ):
            raise AppException(f'Action with name "{action.get("name")}" not found')
        pipedrive_action = PipedriveLeadsAction.objects(
            name=action.get("name"), bot=bot, status=True
        ).get()
        pipedrive_action.domain = action["domain"]
        pipedrive_action.api_token = CustomActionRequestParameters(
            **action["api_token"]
        )
        pipedrive_action.title = action["title"]
        pipedrive_action.response = action["response"]
        pipedrive_action.metadata = action["metadata"]
        pipedrive_action.user = user
        pipedrive_action.timestamp = datetime.utcnow()
        pipedrive_action.save()

    def list_pipedrive_actions(self, bot: Text, with_doc_id: bool = True):
        """
        List Pipedrive Action
        :param bot: bot id
        :param with_doc_id: return document id along with action configuration if True
        """
        for action in PipedriveLeadsAction.objects(bot=bot, status=True):
            action = action.to_mongo().to_dict()
            if with_doc_id:
                action["_id"] = action["_id"].__str__()
            else:
                action.pop("_id")
            action.pop("user")
            action.pop("bot")
            action.pop("status")
            action.pop("timestamp")
            yield action

    def add_hubspot_forms_action(self, action: Dict, bot: str, user: str):
        """
        Add a new Hubspot forms Action
        :param action: Hubspot action configuration
        :param bot: bot id
        :param user: user id
        :return: doc id
        """
        action["bot"] = bot
        action["user"] = user
        if action.get("name") and Utility.special_match(action.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        Utility.is_valid_action_name(action.get("name"), bot, HubspotFormsAction)
        hubspot_action = HubspotFormsAction(**action).save().id.__str__()
        self.add_action(
            action["name"],
            bot,
            user,
            action_type=ActionType.hubspot_forms_action.value,
            raise_exception=False,
        )
        return hubspot_action

    def edit_hubspot_forms_action(self, action: dict, bot: Text, user: Text):
        """
        Update a Hubspot forms Action
        :param action: Hubspot forms action configuration
        :param bot: bot id
        :param user: user id
        :return: None
        """
        if action.get("name") and Utility.special_match(action.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        if not Utility.is_exist(
                HubspotFormsAction,
                raise_error=False,
                name=action.get("name"),
                bot=bot,
                status=True,
        ):
            raise AppException(f'Action with name "{action.get("name")}" not found')
        hubspot_forms_action = HubspotFormsAction.objects(
            name=action.get("name"), bot=bot, status=True
        ).get()
        hubspot_forms_action.portal_id = action["portal_id"]
        hubspot_forms_action.form_guid = action["form_guid"]
        hubspot_forms_action.response = action["response"]
        hubspot_forms_action.fields = action["fields"]
        hubspot_forms_action.user = user
        hubspot_forms_action.timestamp = datetime.utcnow()
        hubspot_forms_action.save()

    def list_hubspot_forms_actions(self, bot: Text, with_doc_id: bool = True):
        """
        List Hubspot forms Action
        :param bot: bot id
        :param with_doc_id: return document id along with action configuration if True
        """
        for action in HubspotFormsAction.objects(bot=bot, status=True):
            action = action.to_mongo().to_dict()
            if with_doc_id:
                action["_id"] = action["_id"].__str__()
            else:
                action.pop("_id")
            action.pop("user")
            action.pop("bot")
            action.pop("status")
            yield action

    @staticmethod
    def get_attached_flows(
            bot: Text, event_name: Text, event_type: Text, raise_error: bool = True
    ):
        stories_with_event = list(
            Stories.objects(
                bot=bot,
                status=True,
                events__name__iexact=event_name,
                events__type__exact=event_type,
            )
        )
        rules_with_event = list(
            Rules.objects(
                bot=bot,
                status=True,
                events__name__iexact=event_name,
                events__type__exact=event_type,
            )
        )
        stories_with_event.extend(rules_with_event)
        if stories_with_event and raise_error:
            if event_type == "user":
                event_type = "intent"
            raise AppException(
                f'Cannot remove {event_type} "{event_name}" linked to flow "{stories_with_event[0].block_name}"'
            )
        return stories_with_event

    @staticmethod
    def add_secret(key: Text, value: Text, bot: Text, user: Text):
        """
        Add secret key, value to vault.

        :param key: key to be added
        :param value: value to be added
        :param bot: bot id
        :param user: user id
        """
        Utility.is_exist(KeyVault, "Key exists!", key=key, bot=bot)
        return KeyVault(key=key, value=value, bot=bot, user=user).save().id.__str__()

    @staticmethod
    def get_secret(key: Text, bot: Text, raise_err: bool = True):
        """
        Get secret value for key from key vault.

        :param key: key to be added
        :param raise_err: raise error if key does not exists
        :param bot: bot id
        """
        from ..actions.utils import ActionUtility

        return ActionUtility.get_secret_from_key_vault(key, bot, raise_err)

    @staticmethod
    def update_secret(key: Text, value: Text, bot: Text, user: Text):
        """
        Update secret value for a key to key vault.

        :param key: key to be added
        :param value: value to be added
        :param bot: bot id
        :param user: user id
        """
        if not Utility.is_exist(KeyVault, raise_error=False, key=key, bot=bot):
            raise AppException(f"key '{key}' does not exists!")
        key_value = KeyVault.objects(key=key, bot=bot).get()
        key_value.value = value
        key_value.user = user
        key_value.save()
        return key_value.id.__str__()

    @staticmethod
    def list_secrets(bot: Text):
        """
        List secret keys for bot.

        :param bot: bot id
        """
        keys = list(KeyVault.objects(bot=bot).values_list("key"))
        return keys

    @staticmethod
    def delete_secret(key: Text, bot: Text, **kwargs):
        """
        Delete secret for bot.

        :param key: key to be added
        :param bot: bot id
        """
        if not Utility.is_exist(KeyVault, raise_error=False, key=key, bot=bot):
            raise AppException(f"key '{key}' does not exists!")
        custom_widgets = list(
            CustomWidgets.objects(
                __raw__={
                    "bot": bot,
                    "$or": [
                        {
                            "headers": {
                                "$elemMatch": {
                                    "parameter_type": ActionParameterType.key_vault.value,
                                    "value": key,
                                }
                            }
                        },
                        {
                            "request_parameters": {
                                "$elemMatch": {
                                    "parameter_type": ActionParameterType.key_vault.value,
                                    "value": key,
                                }
                            }
                        },
                    ],
                }
            ).values_list("name")
        )

        http_action = list(
            HttpActionConfig.objects(
                __raw__={
                    "bot": bot,
                    "status": True,
                    "$or": [
                        {
                            "headers": {
                                "$elemMatch": {
                                    "parameter_type": ActionParameterType.key_vault.value,
                                    "value": key,
                                }
                            }
                        },
                        {
                            "params_list": {
                                "$elemMatch": {
                                    "parameter_type": ActionParameterType.key_vault.value,
                                    "value": key,
                                }
                            }
                        },
                    ],
                }
            ).values_list("action_name")
        )

        email_action = list(
            EmailActionConfig.objects(
                (
                        (
                                Q(
                                    smtp_userid__parameter_type=ActionParameterType.key_vault.value
                                )
                                & Q(smtp_userid__value=key)
                        )
                        | (
                                Q(
                                    smtp_password__parameter_type=ActionParameterType.key_vault.value
                                )
                                & Q(smtp_password__value=key)
                        )
                ),
                bot=bot,
                status=True,
            ).values_list("action_name")
        )

        google_action = list(
            GoogleSearchAction.objects(
                (
                        Q(api_key__parameter_type=ActionParameterType.key_vault.value)
                        & Q(api_key__value=key)
                ),
                bot=bot,
                status=True,
            ).values_list("name")
        )

        action_list = []
        for action_class in [JiraAction, ZendeskAction, PipedriveLeadsAction]:
            attached_action = list(
                action_class.objects(
                    (
                            Q(api_token__parameter_type=ActionParameterType.key_vault.value)
                            & Q(api_token__value=key)
                    ),
                    bot=bot,
                    status=True,
                ).values_list("name")
            )
            action_list.extend(attached_action)

        hubspot_action = list(
            HubspotFormsAction.objects(
                __raw__={
                    "bot": bot,
                    "status": True,
                    "fields": {
                        "$elemMatch": {
                            "parameter_type": ActionParameterType.key_vault.value,
                            "value": key,
                        }
                    },
                }
            ).values_list("name")
        )

        razorpay_actions = list(
            RazorpayAction.objects(
                (
                        (
                                Q(api_key__parameter_type=ActionParameterType.key_vault.value)
                                & Q(api_key__value=key)
                        )
                        | (
                                Q(
                                    api_secret__parameter_type=ActionParameterType.key_vault.value
                                )
                                & Q(api_secret__value=key)
                        )
                        | (
                                Q(amount__parameter_type=ActionParameterType.key_vault.value)
                                & Q(amount__value=key)
                        )
                        | (
                                Q(currency__parameter_type=ActionParameterType.key_vault.value)
                                & Q(currency__value=key)
                        )
                        | (
                                Q(username__parameter_type=ActionParameterType.key_vault.value)
                                & Q(username__value=key)
                        )
                        | (
                                Q(email__parameter_type=ActionParameterType.key_vault.value)
                                & Q(email__value=key)
                        )
                        | (
                                Q(contact__parameter_type=ActionParameterType.key_vault.value)
                                & Q(contact__value=key)
                        )
                ),
                bot=bot,
                status=True,
            ).values_list("name")
        )

        actions = (
                http_action
                + email_action
                + google_action
                + action_list
                + hubspot_action
                + razorpay_actions
        )

        if len(actions):
            raise AppException(f"Key is attached to action: {actions}")

        if len(custom_widgets):
            raise AppException(f"Key is attached to custom widget: {custom_widgets}")
        kv = KeyVault.objects(key=key, bot=bot).get()
        Utility.delete_documents(kv, kwargs.get("user"))

    def add_two_stage_fallback_action(self, request_data: dict, bot: Text, user: Text):
        """
        Add 2 stage fallback config.

        :param request_data: request config for fallback action
        :param bot: bot id
        :param user: user
        """
        Utility.is_exist(
            Actions,
            exp_message="Action exists!",
            name__iexact=KAIRON_TWO_STAGE_FALLBACK,
            bot=bot,
            status=True,
        )
        Utility.is_exist(
            KaironTwoStageFallbackAction,
            exp_message="Action exists!",
            name__iexact=KAIRON_TWO_STAGE_FALLBACK,
            bot=bot,
            status=True,
        )
        trigger_rules = [
            rule["payload"] for rule in request_data.get("trigger_rules") or []
        ]
        intent_present = self.fetch_intents(bot)
        if trigger_rules and set(trigger_rules).difference(set(intent_present)):
            raise AppException(
                f"Intent {set(trigger_rules).difference(set(intent_present))} do not exist in the bot"
            )
        request_data["bot"] = bot
        request_data["user"] = user
        request_data["name"] = KAIRON_TWO_STAGE_FALLBACK
        KaironTwoStageFallbackAction(**request_data).save()
        self.add_action(
            KAIRON_TWO_STAGE_FALLBACK,
            bot,
            user,
            raise_exception=False,
            action_type=ActionType.two_stage_fallback,
        )

    def edit_two_stage_fallback_action(self, request_data: dict, bot: Text, user: Text):
        """
        Edit 2 stage fallback config.

        :param request_data: request config for fallback action
        :param bot: bot id
        :param user: user
        :param name: action name
        """
        if not Utility.is_exist(
                KaironTwoStageFallbackAction,
                raise_error=False,
                name=KAIRON_TWO_STAGE_FALLBACK,
                bot=bot,
                status=True,
        ):
            raise AppException(
                f'Action with name "{KAIRON_TWO_STAGE_FALLBACK}" not found'
            )
        trigger_rules = [
            rule["payload"] for rule in request_data.get("trigger_rules") or []
        ]
        intent_present = self.fetch_intents(bot)
        if trigger_rules and set(trigger_rules).difference(set(intent_present)):
            raise AppException(
                f"Intent {set(trigger_rules).difference(set(intent_present))} do not exist in the bot"
            )
        action = KaironTwoStageFallbackAction.objects(
            name=KAIRON_TWO_STAGE_FALLBACK, bot=bot
        ).get()
        action.trigger_rules = [
            QuickReplies(**rule) for rule in request_data.get("trigger_rules") or []
        ]
        action.text_recommendations = request_data.get("text_recommendations")
        action.fallback_message = request_data.get("fallback_message")
        action.user = user
        action.save()

    def get_two_stage_fallback_action_config(
            self,
            bot: Text,
            name: Text = KAIRON_TWO_STAGE_FALLBACK,
            with_doc_id: bool = True,
    ):
        """
        Retrieve 2 stage fallback config.

        :param bot: bot id
        :param name: action name
        :param with_doc_id: return document id along with action configuration if True
        """
        for action in KaironTwoStageFallbackAction.objects(
                name=name, bot=bot, status=True
        ):
            action = action.to_mongo().to_dict()
            if with_doc_id:
                action["_id"] = action["_id"].__str__()
            else:
                action.pop("_id")
            action.pop("timestamp")
            action.pop("status")
            action.pop("bot")
            action.pop("user")
            yield action

    def add_prompt_action(self, request_data: dict, bot: Text, user: Text):
        """
        Add prompt(Kairon FAQ) Action

        :param request_data: request config for kairon faq action
        :param bot: bot id
        :param user: user
        """
        bot_settings = self.get_bot_settings(bot=bot, user=user)
        if not bot_settings["llm_settings"]["enable_faq"]:
            raise AppException(
                "Faq feature is disabled for the bot! Please contact support."
            )

        if request_data.get("name") and Utility.special_match(request_data.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        self.__validate_llm_prompts(request_data.get("llm_prompts", []), bot)
        Utility.is_valid_action_name(request_data.get("name"), bot, PromptAction)
        request_data["bot"] = bot
        request_data["user"] = user
        prompt_action = PromptAction(**request_data)
        prompt_action_id = prompt_action.save().id.__str__()
        self.add_action(
            request_data["name"],
            bot,
            user,
            action_type=ActionType.prompt_action.value,
            raise_exception=False,
        )
        return prompt_action_id

    def __validate_llm_prompts(self, llm_prompts, bot: Text):
        for prompt in llm_prompts:
            if prompt["source"] == "slot":
                if not Utility.is_exist(
                        Slots, raise_error=False, name=prompt["data"], bot=bot, status=True
                ):
                    raise AppException(f'Slot with name {prompt["data"]} not found!')
            if prompt["source"] == "action":
                if not (
                        Utility.is_exist(
                            HttpActionConfig,
                            raise_error=False,
                            action_name=prompt["data"],
                            bot=bot,
                            status=True,
                        )
                        or Utility.is_exist(
                    GoogleSearchAction,
                    raise_error=False,
                    name=prompt["data"],
                    bot=bot,
                    status=True,
                )
                ):
                    raise AppException(f'Action with name {prompt["data"]} not found!')

            if prompt["source"] == "crud":
                collections_list = DataProcessor.get_all_collections(bot)
                existing_collections = {item['collection_name'] for item in collections_list}
                missing_collections = [col for col in prompt.get('crud_config').get("collections",[]) if col not in existing_collections]

                if missing_collections:
                    raise AppException(f'Collections not found: {missing_collections}')

    def edit_prompt_action(
            self, prompt_action_id: str, request_data: dict, bot: Text, user: Text
    ):
        """
        Edit prompt(Kairon FAQ) Action

        :param prompt_action_id: action id
        :param request_data: request config for kairon faq action
        :param bot: bot id
        :param user: user
        """
        if request_data.get("name") and Utility.special_match(request_data.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        if not Utility.is_exist(
                PromptAction, id=prompt_action_id, raise_error=False, bot=bot, status=True
        ):
            raise AppException("Action not found")
        self.__validate_llm_prompts(request_data.get("llm_prompts", []), bot)
        action = PromptAction.objects(id=prompt_action_id, bot=bot, status=True).get()
        action.name = request_data.get("name")
        action.failure_message = request_data.get("failure_message")
        action.user_question = UserQuestion(**request_data.get("user_question"))
        action.num_bot_responses = request_data.get("num_bot_responses", 5)
        action.hyperparameters = request_data.get("hyperparameters")
        action.llm_type = request_data.get("llm_type")
        action.llm_prompts = [
            LlmPrompt(**prompt) for prompt in request_data.get("llm_prompts", [])
        ]
        action.instructions = request_data.get("instructions", [])
        action.set_slots = request_data.get("set_slots", [])
        action.dispatch_response = request_data.get("dispatch_response", True)
        action.timestamp = datetime.utcnow()
        action.process_media=request_data.get("process_media", False)
        action.user = user
        action.save()

    def get_prompt_action(self, bot: Text, with_doc_id: bool = True):
        """
        fetches prompt(Kairon FAQ) Action

        :param bot: bot id
        :param with_doc_id: action id
        :return: yield dict
        """
        actions = []
        for action in PromptAction.objects(bot=bot, status=True):
            action = action.to_mongo().to_dict()
            if with_doc_id:
                action["_id"] = action["_id"].__str__()
            else:
                action.pop("_id")
            action.pop("timestamp")
            action.pop("bot")
            action.pop("user")
            actions.append(action)
        return actions

    @staticmethod
    def save_auditlog_event_config(bot, user, data):
        headers = {} if data.get("headers") is None else data.get("headers")
        try:
            event_config = EventConfig.objects(bot=bot).get()
            event_config.update(
                set__ws_url=data.get("ws_url"),
                set__headers=Utility.encrypt_message(json.dumps(headers)),
                set__method=data.get("method"),
            )
        except DoesNotExist:
            event_config = EventConfig(
                bot=bot,
                user=user,
                ws_url=data.get("ws_url"),
                headers=headers,
                method=data.get("method"),
            )
            event_config.save()

    @staticmethod
    def get_auditlog_event_config(bot):
        try:
            event_config_data = EventConfig.objects(bot=bot).get()
            event_config = event_config_data.to_mongo().to_dict()
            event_config.pop("_id")
            event_config.pop("timestamp")
            event_config["headers"] = Utility.decrypt_message(event_config_data.headers)
        except DoesNotExist:
            event_config = {}
        return event_config

    @staticmethod
    def get_auditlog_for_bot(bot, from_date=None, to_date=None, start_idx: int = 0, page_size: int = 10):
        processor = MongoProcessor()
        if not from_date:
            from_date = datetime.utcnow().date()
        if not to_date:
            to_date = from_date + timedelta(days=1)
        to_date = to_date + timedelta(days=1)
        data_filter = {"attributes__key": 'bot', "attributes__value": bot, "timestamp__gte": from_date,
                       "timestamp__lte": to_date}
        auditlog_data = AuditLogData.objects(**data_filter).skip(start_idx).limit(page_size).exclude('id').order_by(
            '-timestamp').to_json()
        row_cnt = processor.get_row_count(AuditLogData, bot, **data_filter)
        return json.loads(auditlog_data), row_cnt

    def get_logs(
            self, bot: Text, logtype: str, start_time: datetime, end_time: datetime
    ):
        """
        create zip file containing download data

        :param bot: bot id
        :param logtype: log type
        :param start_time: start time
        :param end_time: end time
        :return: zip file path
        """
        from .data_objects import ModelTraining, ConversationsHistoryDeleteLogs
        from kairon.shared.test.data_objects import ModelTestingLogs
        from kairon.shared.multilingual.data_objects import BotReplicationLogs
        from kairon.shared.importer.data_objects import ValidationLogs

        logs = {
            LogType.model_training.value: ModelTraining,
            LogType.model_testing.value: ModelTestingLogs,
            LogType.action_logs.value: ActionServerLogs,
            LogType.audit_logs.value: AuditLogData,
            LogType.data_importer.value: ValidationLogs,
            LogType.history_deletion.value: ConversationsHistoryDeleteLogs,
            LogType.multilingual.value: BotReplicationLogs,
        }
        if logtype == LogType.action_logs.value:
            filter_query = {
                "bot": bot,
                "timestamp__gte": start_time,
                "timestamp__lte": end_time,
            }
            query = logs[logtype].objects(**filter_query).to_json()
        elif logtype == LogType.audit_logs.value:
            filter_query = {
                "attributes__key": "bot",
                "attributes__value": bot,
                "timestamp__gte": start_time,
                "timestamp__lte": end_time,
            }
            query = (
                logs[logtype].objects(**filter_query).order_by("-timestamp").to_json()
            )
        else:
            filter_query = {
                "bot": bot,
                "start_timestamp__gte": start_time,
                "start_timestamp__lte": end_time,
            }
            query = logs[logtype].objects(**filter_query).to_json()
        value = json.loads(query)
        return value

    def delete_audit_logs(self):
        retention_period = Utility.environment["events"]["audit_logs"]["retention"]
        overdue_time = datetime.utcnow() - timedelta(days=retention_period)
        AuditLogData.objects(timestamp__lte=overdue_time).delete()

    def flatten_qna(self, bot: Text, start_idx=0, page_size=10, fetch_all=False):
        """
        Returns Q&As having intent name, utterance name, training examples,
        responses in flattened form.
        :param bot: bot id
        :param start_idx: start index of the page
        :param page_size: size of the page
        :param fetch_all: removes paginated result if True
        """
        query = (
            Rules.objects(bot=bot, status=True, template_type=TemplateType.QNA.value)
            .skip(start_idx)
            .limit(page_size)
        )
        if fetch_all:
            query = Rules.objects(
                bot=bot, status=True, template_type=TemplateType.QNA.value
            )
        for qna in query.aggregate(
                {
                    "$addFields": {
                        "story": "$block_name",
                        "intent": {"$arrayElemAt": ["$events", 1]},
                        "action": {"$arrayElemAt": ["$events", 2]},
                    }
                },
                {
                    "$project": {
                        "_id": {"$toString": "$_id"},
                        "story": 1,
                        "intent": "$intent.name",
                        "utterance": "$action.name",
                    }
                },
                {
                    "$lookup": {
                        "from": "training_examples",
                        "as": "training_examples",
                        "let": {"intent_name": "$intent"},
                        "pipeline": [
                            {
                                "$match": {
                                    "$expr": {
                                        "$and": [
                                            {"$eq": ["$intent", "$$intent_name"]},
                                            {"$eq": ["$status", True]},
                                            {"$eq": ["$bot", bot]},
                                        ]
                                    }
                                }
                            },
                            {
                                "$project": {
                                    "_id": {"$toString": "$_id"},
                                    "text": 1,
                                    "entities": 1,
                                }
                            },
                        ],
                    }
                },
                {
                    "$lookup": {
                        "from": "responses",
                        "as": "responses",
                        "let": {"utterance_name": "$utterance"},
                        "pipeline": [
                            {
                                "$match": {
                                    "$expr": {
                                        "$and": [
                                            {"$eq": ["$name", "$$utterance_name"]},
                                            {"$eq": ["$status", True]},
                                            {"$eq": ["$bot", bot]},
                                        ]
                                    }
                                }
                            },
                            {
                                "$project": {
                                    "_id": {"$toString": "$_id"},
                                    "text": 1,
                                    "custom": 1,
                                }
                            },
                        ],
                    }
                },
        ):
            training_examples = []
            for t_example in qna.get("training_examples") or []:
                entities = t_example.get("entities") or []
                text = DataUtility.prepare_nlu_text(t_example["text"], entities)
                training_examples.append({"text": text, "_id": t_example["_id"]})
            qna["training_examples"] = training_examples
            yield qna

    def save_faq(self, bot: Text, user: Text, df: DataFrame):
        import re
        from kairon.shared.augmentation.utils import AugmentationUtils

        error_summary = {"intents": [], "utterances": [], "training_examples": []}
        component_count = {
            "intents": 0,
            "utterances": 0,
            "stories": 0,
            "rules": 0,
            "training_examples": 0,
            "domain": {"intents": 0, "utterances": 0},
        }
        for index, row in df.iterrows():
            is_intent_added = False
            is_response_added = False
            training_example_errors = None
            component_count["utterances"] = component_count["utterances"] + 1
            key_tokens = AugmentationUtils.get_keywords(row["questions"])
            if key_tokens:
                key_tokens = key_tokens[0][0]
            else:
                key_tokens = row["questions"].split("\n")[0]
            intent = key_tokens.replace(" ", "_") + "_" + str(index)
            intent = re.sub(r"[^a-zA-Z0-9_]", "_", intent) if Utility.special_match(intent) else intent
            examples = row["questions"].split("\n")
            component_count["training_examples"] = component_count[
                                                       "training_examples"
                                                   ] + len(examples)
            action = f"utter_{intent}"
            steps = [
                {"name": RULE_SNIPPET_ACTION_NAME, "type": StoryStepType.bot.value},
                {"name": intent, "type": StoryStepType.intent.value},
                {"name": action, "type": StoryStepType.bot.value},
            ]
            rule = {
                "name": intent,
                "steps": steps,
                "type": "RULE",
                "template_type": TemplateType.QNA.value,
            }
            try:
                training_example_errors = list(
                    self.add_training_example(examples, intent, bot, user, False)
                )
                is_intent_added = True
                self.add_text_response(row["answer"], action, bot, user)
                is_response_added = True
                self.add_complex_story(rule, bot, user)
            except Exception as e:
                logging.info(e)
                training_example_errors = [
                    f"{a['message']}: {a['text']}"
                    for a in training_example_errors
                    if a["_id"] is None
                ]
                error_summary["training_examples"].extend(training_example_errors)
                if is_intent_added:
                    error_summary["utterances"].append(str(e))
                    self.delete_intent(intent, bot, user, False)
                if is_response_added:
                    self.delete_utterance(action, bot, user=user)
        return component_count, error_summary

    def delete_all_faq(self, bot: Text):
        get_intents_pipelines = [
            {"$unwind": {"path": "$events"}},
            {"$match": {"events.type": "user"}},
            {"$group": {"_id": None, "intents": {"$push": "$events.name"}}},
            {"$project": {"_id": 0, "intents": 1}},
        ]
        get_utterances_pipelines = [
            {"$unwind": {"path": "$events"}},
            {"$match": {"events.type": "action", "events.name": {"$regex": "^utter_"}}},
            {"$group": {"_id": None, "utterances": {"$push": "$events.name"}}},
            {"$project": {"_id": 0, "utterances": 1}},
        ]
        qna_intents = list(
            Rules.objects(
                bot=bot, status=True, template_type=TemplateType.QNA.value
            ).aggregate(get_intents_pipelines)
        )
        qna_intents = set(qna_intents[0].get("intents")) if qna_intents else set()
        story_intents = list(
            Stories.objects(bot=bot, status=True).aggregate(get_intents_pipelines)
        )
        story_intents = set(story_intents[0].get("intents")) if story_intents else set()
        custom_rule_intents = list(
            Rules.objects(
                bot=bot, status=True, template_type=TemplateType.CUSTOM.value
            ).aggregate(get_intents_pipelines)
        )
        custom_rule_intents = (
            set(custom_rule_intents[0].get("intents")) if custom_rule_intents else set()
        )
        delete_intents = qna_intents - story_intents - custom_rule_intents

        qna_utterances = list(
            Rules.objects(
                bot=bot, status=True, template_type=TemplateType.QNA.value
            ).aggregate(get_utterances_pipelines)
        )
        qna_utterances = (
            set(qna_utterances[0].get("utterances")) if qna_utterances else set()
        )
        custom_rule_utterances = list(
            Rules.objects(
                bot=bot, status=True, template_type=TemplateType.CUSTOM.value
            ).aggregate(get_utterances_pipelines)
        )
        custom_rule_utterances = (
            set(custom_rule_utterances[0].get("utterances"))
            if custom_rule_utterances
            else set()
        )
        story_utterances = list(
            Stories.objects(bot=bot, status=True).aggregate(get_utterances_pipelines)
        )
        story_utterances = (
            set(story_utterances[0].get("utterances")) if story_utterances else set()
        )
        delete_utterances = qna_utterances - story_utterances - custom_rule_utterances

        Utility.hard_delete_document([TrainingExamples], bot, intent__in=delete_intents)
        Utility.hard_delete_document([Intents], bot, name__in=delete_intents)
        Utility.hard_delete_document(
            [Utterances, Responses], bot, name__in=delete_utterances
        )
        Utility.hard_delete_document([Rules], bot, template_type=TemplateType.QNA.value)

    def add_razorpay_action(self, request_data: dict, bot: Text, user: Text):
        """
        Add razorpay config.

        :param request_data: request config for razorpay action
        :param bot: bot id
        :param user: user
        """
        if request_data.get("name") and Utility.special_match(request_data.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        Utility.is_exist(
            Actions,
            exp_message="Action exists!",
            name__iexact=request_data.get("name"),
            bot=bot,
            status=True,
        )
        Utility.is_exist(
            RazorpayAction,
            exp_message="Action exists!",
            name__iexact=request_data.get("name"),
            bot=bot,
            status=True,
        )
        request_data["bot"] = bot
        request_data["user"] = user
        action_id = RazorpayAction(**request_data).save().id.__str__()
        self.add_action(
            request_data["name"],
            bot,
            user,
            raise_exception=False,
            action_type=ActionType.razorpay_action,
        )
        return action_id

    def edit_razorpay_action(self, request_data: dict, bot: Text, user: Text):
        """
        Edit razorpay config.

        :param request_data: request config for razorpay action
        :param bot: bot id
        :param user: user
        :param name: action name
        """
        if request_data.get("name") and Utility.special_match(request_data.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        if not Utility.is_exist(
                RazorpayAction,
                raise_error=False,
                name=request_data.get("name"),
                bot=bot,
                status=True,
        ):
            raise AppException(
                f'Action with name "{request_data.get("name")}" not found'
            )
        action = RazorpayAction.objects(name=request_data.get("name"), bot=bot).get()
        action.api_key = CustomActionRequestParameters(**request_data.get("api_key"))
        action.api_secret = CustomActionRequestParameters(
            **request_data.get("api_secret")
        )
        action.amount = CustomActionRequestParameters(**request_data.get("amount"))
        action.currency = CustomActionRequestParameters(**request_data.get("currency"))
        action.username = (
            CustomActionRequestParameters(**request_data.get("username"))
            if request_data.get("username")
            else None
        )
        action.email = (
            CustomActionRequestParameters(**request_data.get("email"))
            if request_data.get("email")
            else None
        )
        action.contact = (
            CustomActionRequestParameters(**request_data.get("contact"))
            if request_data.get("contact")
            else None
        )
        notes = [
            CustomActionRequestParameters(**param)
            for param in request_data.get("notes") or []
        ]
        action.notes = notes
        action.user = user
        action.save()

    def get_razorpay_action_config(self, bot: Text, with_doc_id: bool = True):
        """
        Retrieve razorpay config.

        :param bot: bot id
        :param with_doc_id: return document id along with action configuration if True
        """
        for action in RazorpayAction.objects(bot=bot, status=True):
            action = action.to_mongo().to_dict()
            if with_doc_id:
                action["_id"] = action["_id"].__str__()
            else:
                action.pop("_id")
            action.pop("status")
            action.pop("bot")
            action.pop("user")

            yield action

    def get_live_agent(self, bot: Text):
        if not self.is_live_agent_enabled(bot, False):
            return []
        try:
            live_agent = LiveAgentActionConfig.objects(bot=bot, status=True).get()
            live_agent = live_agent.to_mongo().to_dict()
            live_agent.pop("_id")
            live_agent.pop("bot")
            live_agent.pop("user")
            live_agent.pop("status")
            live_agent.pop("timestamp")
            return live_agent
        except Exception as e:
            logger.warning(f"Live agent action config doesn't exist. {repr(e)}")
            return []

    def enable_live_agent(self, request_data: dict, bot: Text, user: Text):
        if not self.is_live_agent_enabled(bot, False):
            raise AppException("Live agent service is not available for the bot")
        action_name = "live_agent_action"
        enabled = False
        if not Utility.is_exist(
                Actions,
                name__iexact=action_name,
                type=ActionType.live_agent_action.value,
                bot=bot,
                status=True,
                raise_error=False
        ):
            self.add_action(
                action_name,
                bot,
                user,
                raise_exception=False,
                action_type=ActionType.live_agent_action.value,
            )
            enabled = True
        if not Utility.is_exist(LiveAgentActionConfig, raise_error=False, bot=bot, user=user):
            live_agent = LiveAgentActionConfig(**request_data, bot=bot, user=user, status=True)
            live_agent.save()
        return enabled

    def edit_live_agent(self, request_data: dict, bot: Text, user: Text):
        if not self.is_live_agent_enabled(bot, False):
            raise AppException("Live agent service is not available for the bot")

        live_agent = LiveAgentActionConfig.objects(bot=bot).update(
            **{'set__' + k: v for k, v in request_data.items()}
        )
        if not live_agent:
            raise AppException("Live agent not enabled for the bot")

    def disable_live_agent(self, bot: Text, user: str = None):
        Utility.hard_delete_document([Actions], bot, name__iexact="live_agent_action")
        Utility.hard_delete_document([LiveAgentActionConfig], bot=bot, user=user)

    def is_live_agent_enabled(self, bot: Text, check_in_utils: bool = True):
        bot_setting = BotSettings.objects(bot=bot).get().to_mongo().to_dict()
        if not bot_setting.get("live_agent_enabled"):
            return False
        if not check_in_utils:
            return True
        return Utility.is_exist(LiveAgentActionConfig, raise_error=False, bot=bot, status=True)

    def add_callback(self, request_data: dict, bot: Text):
        """
        Add callback config.

        :param request_data: request config for callback
        :param bot: bot id
        """
        name = request_data.get("name")
        pyscript_code = request_data.get("pyscript_code")
        execution_mode = request_data.get("execution_mode")
        shorten_token = request_data.get("shorten_token")
        standalone = request_data.get("standalone")
        expire_in = request_data.get("expire_in")
        standalone_id_path = request_data.get("standalone_id_path")
        response_type = request_data.get("response_type", CallbackResponseType.KAIRON_JSON.value)
        if standalone and not standalone_id_path:
            raise AppException("Standalone id path is required!")
        if compile_error := DataValidation.validate_python_script_compile_time(pyscript_code):
            raise AppException(f"source code syntax error: {compile_error}")
        config = CallbackConfig.create_entry(bot,
                                             name,
                                             pyscript_code,
                                             execution_mode,
                                             expire_in,
                                             shorten_token,
                                             standalone,
                                             standalone_id_path,
                                             response_type)
        config.pop('_id')
        return config

    def edit_callback(self, request_data: dict, bot: Text):
        """
        Edit callback config.

        :param request_data: request config for callback
        :param bot: bot id
        """
        name = request_data.get("name")
        request_data.pop('name')
        if pyscript_code := request_data.get('pyscript_code'):
            if compile_error := DataValidation.validate_python_script_compile_time(pyscript_code):
                raise AppException(f"source code syntax error: {compile_error}")
        config = CallbackConfig.edit(bot, name, **request_data)
        config.pop('_id')
        return config

    def delete_callback(self, bot: str, name: str):
        """
        Delete callback config.
        :param bot: bot id
        :param name: callback name
        """
        CallbackConfig.delete_entry(bot, name)

    def get_all_callback_names(self, bot: Text):
        """
        Retrieve all callback names.

        :param bot: bot id
        :return: list of callback names
        """
        return CallbackConfig.get_all_names(bot)

    def get_callback(self, bot: Text, name: Text):
        return CallbackConfig.get_entry(bot, name)

    def add_callback_action(self, request_data: dict, bot: Text, user: Text):
        """
        Add async callback action config.

        :param request_data: request config for async callback action
        :param bot: bot id
        :param user: user
        """
        name = request_data.get("name")
        callback_name = request_data.get("callback_name")
        metadata_list = request_data.get("metadata_list", [])
        request_data["bot"] = bot
        request_data["user"] = user
        request_data["metadata_list"] = metadata_list
        request_data['status'] = True

        if request_data.get("name") and Utility.special_match(request_data.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        Utility.is_exist(
            Actions,
            exp_message="Action exists!",
            name__iexact=name,
            bot=bot,
            status=True,
        )
        Utility.is_exist(
            CallbackActionConfig,
            exp_message="Action exists!",
            name__iexact=name,
            bot=bot,
            status=True,
        )
        callback_present = Utility.is_exist(
            CallbackConfig,
            name__iexact=callback_name,
            bot=bot,
            raise_error=False
        )
        if not callback_present:
            raise AppException(f"Callback with name '{callback_name}' not found!")

        new_action = CallbackActionConfig(**request_data).save()
        self.add_action(
            request_data["name"],
            bot,
            user,
            raise_exception=False,
            action_type=ActionType.callback_action,
        )
        new_action = new_action.to_mongo().to_dict()
        new_action.pop('_id')
        return new_action

    def edit_callback_action(self, request_data: dict, bot: Text, user: Text):
        """
        Add async callback action config.

        :param request_data: request config for async callback action
        :param bot: bot id
        :param user: user
        """
        name = request_data.get("name")
        if not name:
            raise AppException("Action name is required!")

        if name and Utility.special_match(name):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        request_data.pop('name')

        callback_name = request_data.get("callback_name")
        if callback_name:
            callback_present = Utility.is_exist(
                CallbackConfig,
                name__iexact=callback_name,
                bot=bot,
                raise_error=False
            )
            if not callback_present:
                raise AppException(f"Callback with name '{callback_name}' not found!")

        update_query = {}
        for key, value in request_data.items():
            if key == 'metadata_list':
                value = [HttpActionRequestBody(**param)for param in value] or []

            update_query[f"set__{key}"] = value
        if not update_query.keys():
            raise AppException("No change in data to update")
        callback_action = CallbackActionConfig.objects(
            bot=bot, name=name
        ).update(**update_query)
        if not callback_action:
            raise AppException("Async callback action not found")

    @staticmethod
    def get_callback_action(bot: Text, name: Text):
        """
        Retrieve async callback action config.

        :param bot: bot id
        :param name: action name
        """
        async_callback_action = CallbackActionConfig.objects(
            bot=bot, name=name
        ).get()
        if not async_callback_action:
            raise AppException("Async callback action not found")

        async_callback_action = async_callback_action.to_mongo().to_dict()
        async_callback_action.pop("_id")
        async_callback_action.pop("bot")
        async_callback_action.pop("user")
        async_callback_action.pop("status")
        async_callback_action.pop("timestamp")
        return async_callback_action

    def delete_callback_action(self, bot: Text, name: Text):
        """
        Delete async callback action config.

        :param bot: bot id
        :param name: action name
        """
        Utility.hard_delete_document([Actions], bot, name__iexact=name)
        Utility.hard_delete_document([CallbackActionConfig], bot=bot, name__iexact=name)

    def add_schedule_action(self, request_data: dict, bot: Text, user: Text):
        """
        Add Schedule Action
        :param request_data: data object for schedule action
        :param bot: bot id
        :param user: user
        """
        if request_data.get("name") and Utility.special_match(request_data.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        Utility.is_exist(
            Actions,
            exp_message="Action exists!",
            name__iexact=request_data.get("name"),
            bot=bot,
            status=True,
        )
        Utility.is_exist(
            ScheduleAction,
            exp_message="Action exists!",
            name__iexact=request_data.get("name"),
            bot=bot,
            status=True,
        )

        request_data["bot"] = bot
        request_data["user"] = user
        action_id = ScheduleAction(**request_data).save().id.__str__()
        self.add_action(
            request_data["name"],
            bot,
            user,
            raise_exception=False,
            action_type=ActionType.schedule_action,
        )
        return action_id

    def update_schedule_action(self, request_data: dict, bot: Text, user: Text):
        """
        Update Schedule Action
        :param request_data: data object for schedule action
        :param bot: bot id
        :param user: user who edit/update this
        """
        if request_data.get("name") and Utility.special_match(request_data.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        if not Utility.is_exist(
                ScheduleAction,
                raise_error=False,
                name__iexact=request_data["name"],
                bot=bot,
                status=True,
        ):
            raise AppException(
                "No schedule action found for this bot with this name "
                + bot
                + " and action "
                + request_data["name"]
            )
        params_list = [
            CustomActionRequestParameters(**param)
            for param in request_data.get("params_list") or []
        ]

        schedule_action = ScheduleAction.objects(bot=bot, name=request_data["name"], status=True).get()
        schedule_action.name = request_data.get("name")
        schedule_action.user = user
        schedule_action.timezone = request_data.get("timezone")
        schedule_action.response_text = request_data.get("response_text")
        schedule_action.schedule_time = CustomActionDynamicParameters(**request_data.get("schedule_time"))
        schedule_action.params_list = params_list
        schedule_action.schedule_action = request_data.get("schedule_action")
        schedule_action.dispatch_bot_response = request_data.get("dispatch_response", True)
        schedule_action.status = request_data.get("status", True)
        schedule_action.schedule_action_type = request_data.get("schedule_action_type", ScheduleActionType.PYSCRIPT.value)
        schedule_action.save()
        return schedule_action.id.__str__()

    def list_schedule_action(self, bot: Text, with_doc_id: bool = True):
        """
        List Schedule Action
        :param bot: bot id
        :param with_doc_id: return document id along with action configuration if True
        """
        for action in ScheduleAction.objects(bot=bot, status=True):
            action = action.to_mongo().to_dict()
            if with_doc_id:
                action["_id"] = action["_id"].__str__()
            else:
                action.pop("_id")
            action.pop("user")
            action.pop("bot")
            action.pop("timestamp")
            action.pop("status")
            yield action

    def get_schedule_action(self, bot: Text, name: str, with_doc_id: bool = True):
        """
        Get Schedule Action by name
        :param bot: bot id
        :param name: Name of action
        :param with_doc_id: return document id along with action configuration if True
        """
        action = ScheduleAction.objects(bot=bot, name=name, status=True)
        if action:
            action = action.get().to_mongo().to_dict()
            if with_doc_id:
                action["_id"] = action["_id"].__str__()
            else:
                action.pop("_id")
            action.pop("user")
            action.pop("bot")
            action.pop("timestamp")
            action.pop("status")
            return action

    def get_all_callback_actions(self, bot: Text):
        """
        Retrieve all async callback action config.
        """
        async_callback_actions = CallbackActionConfig.objects(bot=bot, status=True)
        if not async_callback_actions:
            return []

        action_dict_list = []
        for action in async_callback_actions:
            action = action.to_mongo().to_dict()
            action.pop("_id")
            action.pop("bot")
            action.pop("user")
            action.pop("status")
            action_dict_list.append(action)
        return action_dict_list

    def get_callback_service_log(self, bot: str,
                                 channel: Optional[None] = None,
                                 name: Optional[str] = None,
                                 sender_id: Optional[str] = None,
                                 identifier: Optional[str] = None,
                                 start: Optional[int] = 0,
                                 limit: Optional[int] = 100):
        """
        Retrieve callback service logs.
        """
        query = {"bot": bot}
        if name:
            query["callback_name"] = name
        if sender_id:
            query["sender_id"] = sender_id
        if channel:
            query["channel"] = channel
        if identifier:
            query["identifier"] = identifier

        logs, total_count = CallbackLog.get_logs(query, start, limit)
        return logs, total_count

    def validate_schema_and_log(self, bot: Text, user: Text, doc_content: File, table_name: Text):
        """
        Validates the schema of the document content (e.g., CSV) against the required table schema and logs the results.

        :param bot: The bot ID
        :param user: The user ID
        :param doc_content: The content of the document being uploaded
        :param table_name: The name of the table to validate against
        :return: True if the schema is valid, else False
        """
        error_message =  self.save_and_validate(bot, user, doc_content, table_name)
        ContentImporterLogProcessor.add_log(
            bot, user, table = table_name.lower(), is_data_uploaded=True, file_received=doc_content.filename
        )
        if error_message:
            ContentImporterLogProcessor.add_log(
                bot,
                user,
                status=STATUSES.FAIL.value,
                event_status=EVENT_STATUS.COMPLETED.value,
                validation_errors= error_message
            )
            return False
        return True

    def save_and_validate(self, bot: Text, user: Text, doc_content: File, table_name: Text):
        """
        Saves the training file and performs validation.

        :param bot: The bot ID
        :param doc_content: The file to be saved and validated
        :param table_name: table name
        :return: The saved file path and an error message if validation fails
        """
        valid_csv_types = ["text/csv"]
        error_message = {}

        if doc_content.content_type not in valid_csv_types and not doc_content.filename.lower().endswith('.csv'):
            error_message[
                'File type error'] = f"Invalid file type: {doc_content.content_type}. Please upload a CSV file."
            return error_message

        content_dir = os.path.join('doc_content_upload_records', bot)
        Utility.make_dirs(content_dir)
        file_path = os.path.join(content_dir, doc_content.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(doc_content.file, buffer)

        doc_content.file.seek(0)
        csv_reader = csv.reader(doc_content.file.read().decode('utf-8').splitlines())
        actual_headers = [header.lower() for header in next(csv_reader) if header.lower() != 'kairon_error_description']
        column_dict = MongoProcessor().get_column_datatype_dict(bot, table_name)
        expected_headers = [header.lower() for header in list(column_dict.keys())]

        missing_columns = set(expected_headers) - set(actual_headers)
        extra_columns = set(actual_headers) - set(expected_headers)

        if actual_headers != expected_headers or missing_columns or extra_columns:
            if actual_headers != expected_headers:
                error_message['Header mismatch'] = f"Expected headers {expected_headers} but found {actual_headers}."
            if missing_columns:
                error_message['Missing columns'] = f"{missing_columns}."
            if extra_columns:
                error_message['Extra columns'] = f"{extra_columns}."

        return error_message

    def file_upload_validate_schema_and_log(self, bot: Text, user: Text, file_content: File):
        """
        Validates the schema of the document content (e.g., CSV) against the required table schema and logs the results.

        :param bot: The bot ID
        :param user: The user ID
        :param file_content: The content of the file being uploaded
        :param type: The Class type of the file to validate against
        :return: True if the schema is valid, else False
        """
        UploadHandlerLogProcessor.add_log(
            bot=bot,
            user=user,
            file_name=file_content.filename,
            event_status=EVENT_STATUS.VALIDATING.value
        )

        self.file_handler_save_and_validate(bot, user, file_content)

        return True

    def file_handler_save_and_validate(self, bot: Text, user: Text, file_content: File):
        """
        Saves the training file and performs validation.

        :param bot: The bot ID
        :param file_content: The file to be saved and validated
        :return: A dictionary of error messages if validation fails
        """
        content_dir = os.path.join('file_content_upload_records', bot)
        Utility.make_dirs(content_dir)
        file_path = os.path.join(content_dir, file_content.filename)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file_content.file, buffer)

        file_content.file.seek(0)

    @staticmethod
    def validate_file_type(file_content):
        valid_csv_types = ["text/csv"]
        if file_content.content_type not in valid_csv_types and not file_content.filename.lower().endswith('.csv'):
            raise AppException(f"Invalid file type: {file_content.content_type}. Please upload a CSV file.")

    def get_column_datatype_dict(self, bot, table_name):
        from ..cognition.processor import CognitionDataProcessor
        cognition_processor = CognitionDataProcessor()
        schemas = list(cognition_processor.list_cognition_schema(bot))
        table_metadata = next((schema['metadata'] for schema in schemas if schema['collection_name'] == table_name.lower()),
                              None)
        if not table_metadata:
            logger.info(f"Schema for table '{table_name}' not found.")

        column_datatype_dict = {column['column_name']: column['data_type'] for column in table_metadata}

        return column_datatype_dict

    def validate_doc_content(self, column_dict: dict, doc_content: List[dict]):
        """
        Validates the document content against the expected column data types.

        :param column_dict: A dictionary where keys are column names and values are expected data types.
        :param doc_content: A list of dictionaries representing the CSV data.
        :return: A summary dictionary containing validation results.
        """

        def get_pydantic_type(data_type: str):
            if data_type == 'str':
                return (str, ...)
            elif data_type == 'int':
                return (int, ...)
            elif data_type == 'float':
                return (float, ...)
            else:
                raise ValueError(f"Unsupported data type: {data_type}")

        model_fields = {
            column_name: get_pydantic_type(data_type)
            for column_name, data_type in column_dict.items()
        }

        DynamicModel = create_model('DynamicModel', **model_fields)

        summary = {}

        for i, row in enumerate(doc_content):
            try:
                model_instance = DynamicModel(**row)
            except ValidationError as e:
                error_details = []
                for error in e.errors():
                    column_name = error['loc'][0]
                    input_value = row.get(column_name)
                    status = "Required Field is Empty" if input_value == "" else "Invalid DataType"
                    error_details.append({
                        "column_name": column_name,
                        "input": input_value,
                        "status": status
                    })
                summary[f"Row {i + 2}"] = error_details

        return summary


    def save_doc_content(self, bot: Text, user: Text, doc_content, table_name: Text, overwrite: bool = False):

        from ..cognition.processor import CognitionDataProcessor
        cognition_processor = CognitionDataProcessor()

        schema = CognitionSchema.objects(bot=bot, collection_name=table_name).first()

        metadata_map = {meta['column_name']: meta['data_type'] for meta in schema.metadata}

        if overwrite:
            cognition_processor.delete_all_cognition_data_by_collection(table_name.lower(), bot)

        for row in reversed(doc_content):
            for column, value in row.items():
                if column in metadata_map:
                    data_type = metadata_map[column]
                    try:
                        if data_type == 'int':
                            row[column] = int(value) if value else None
                        elif data_type == 'float':
                            row[column] = float(value) if value else None
                    except (ValueError, TypeError):
                        raise ValueError(
                            f"Error converting column '{column}' with value '{value}' to type '{data_type}'")

            payload = {
                'collection': table_name,
                'content_type': CognitionDataType.json.value,
                'data': row
            }

            payload_id = cognition_processor.save_cognition_data(payload, user, bot)


    @staticmethod
    def get_error_report_file_path(bot: str, event_id: str) -> str:
        """
        Constructs the file path for the error report based on bot and event_id.
        Ensures the path is safe and within the allowed directory.
        """
        if not event_id.isalnum():
            raise HTTPException(status_code=400, detail="Invalid event ID")

        base_dir = os.path.join('content_upload_summary', bot)

        file_name = f'failed_rows_with_errors_{event_id}.csv'
        file_path = os.path.join(base_dir, file_name)

        if not os.path.exists(file_path) or not file_path.startswith(base_dir):
            raise HTTPException(status_code=404, detail="Error Report not found")

        return file_path

    @staticmethod
    def get_flows_by_tag(bot: str, tag: str):
        data = {
            'rule': [],
            'multiflow': []
        }

        rules = Rules.objects(bot=bot, flow_tags__in=[tag])
        for rule in rules:
            data['rule'].append(rule.block_name)

        multiflows = MultiflowStories.objects(bot=bot, flow_tags__in=[tag])
        for multiflow in multiflows:
            data['multiflow'].append(multiflow.block_name)

        return data

    def add_parallel_action(self, request_data: dict, bot: Text, user: Text):
        """
        Add Parallel Action
        :param request_data: data object for parallel action
        :param bot: bot id
        :param user: user
        """
        if request_data.get("name") and Utility.special_match(request_data.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        Utility.is_exist(
            Actions,
            exp_message="Action exists!",
            name__iexact=request_data.get("name"),
            bot=bot,
            status=True,
        )
        Utility.is_exist(
            ParallelActionConfig,
            exp_message="Action exists!",
            name__iexact=request_data.get("name"),
            bot=bot,
            status=True,
        )

        settings = BotSettings.objects(bot=bot, status=True).first()

        if len(request_data.get("actions")) > settings.max_actions_per_parallel_action:
            raise AppException(
                f"Maximum {settings.max_actions_per_parallel_action} actions are allowed in a parallel action."
            )

        for action in request_data.get("actions"):
            if not Actions.objects(name__iexact=action, bot=bot, status=True).first():
                raise AppException(f"Action with name {action} does not exist!")


        request_data["bot"] = bot
        request_data["user"] = user
        action_id = ParallelActionConfig(**request_data).save().id.__str__()
        self.add_action(
            request_data["name"],
            bot,
            user,
            raise_exception=False,
            action_type=ActionType.parallel_action,
        )
        return action_id


    def update_parallel_action(self, request_data: dict, bot: Text, user: Text):
        """
        Update Parallel Action
        :param request_data: data object for parallel action
        :param bot: bot id
        :param user: user who edit/update this
        """
        if request_data.get("name") and Utility.special_match(request_data.get("name")):
            raise AppException("Invalid name! Only letters, numbers, and underscores (_) are allowed.")

        if not Utility.is_exist(
                ParallelActionConfig,
                raise_error=False,
                name__iexact=request_data["name"],
                bot=bot,
                status=True,
        ):
            parallel_action_name = request_data["name"]
            raise AppException(f"Parallel Action with name '{parallel_action_name}' not found!")

        settings = BotSettings.objects(bot=bot, status=True).first()
        if len(request_data.get("actions")) > settings.max_actions_per_parallel_action:
            raise AppException(
                f"Maximum {settings.max_actions_per_parallel_action} actions are allowed in a parallel action."
            )

        for action in request_data.get("actions"):
            if not Actions.objects(name__iexact=action, bot=bot, status=True).first():
                raise AppException(f"Action with name {action} does not exist!")

        parallel_action = ParallelActionConfig.objects(bot=bot, name=request_data["name"], status=True).get()
        parallel_action.response_text = request_data.get("response_text")
        parallel_action.actions = request_data.get("actions")
        parallel_action.dispatch_response_text = request_data.get("dispatch_response_text")
        parallel_action.user = user
        parallel_action.timestamp = datetime.utcnow()
        parallel_action.save()
        return parallel_action.id.__str__()

    def list_parallel_action(self, bot: Text, with_doc_id: bool = True):
        """
        List Parallel Action
        :param bot: bot id
        :param with_doc_id: return document id along with action configuration if True
        """
        for action in ParallelActionConfig.objects(bot=bot, status=True):
            action = action.to_mongo().to_dict()
            if with_doc_id:
                action["_id"] = action["_id"].__str__()
            else:
                action.pop("_id")
            action.pop("user")
            action.pop("bot")
            action.pop("timestamp")
            action.pop("status")
            yield action

    def fetch_action_logs_for_parallel_action(self, trigger_id: str, bot: str) -> List[dict]:
        """
        Helper to fetch ActionServerLogs for all actions in a given parallel action.

        :param name: Name of the parallel action
        :param bot: Bot ID
        :return: List of ActionServerLogs as dicts
        """
        logs = list(
            ActionServerLogs
            .objects(trigger_info__trigger_id=trigger_id, bot=bot)
            .order_by("-timestamp")
            .as_pymongo()
        )
        if not logs:
            raise AppException("Logs for Actions in Parallel Action not found")

        for log in logs:
            if "_id" in log and isinstance(log["_id"], ObjectId):
                log["_id"] = str(log["_id"])

        return logs

    @staticmethod
    def prepare_log_query_params(request, bot_account: str) -> Dict[str, Any]:
        raw_params = dict(request.query_params)
        query_params = {}

        for key, value in raw_params.items():
            if key in {"start_idx", "page_size"}:
                query_params[key] = int(value)
            elif key in {"from_date", "to_date"}:
                query_params[key] = date.fromisoformat(value)
            else:
                query_params[key] = value

        query_params["bot_account"] = bot_account
        return query_params

    @staticmethod
    def get_metadata_for_any_log_type(bot: Text):
        return Utility.system_metadata.get("logs", {})

    @staticmethod
    def get_logs_for_any_type(
            bot: Text,
            log_type: str,
            start_idx: int = 0,
            page_size: int = 10,
            **kwargs):

        return BaseLogHandler.get_logs(
            bot = bot,
            log_type = log_type,
            start_idx = start_idx,
            page_size = page_size,
            **kwargs
        )

    @staticmethod
    def get_logs_for_search_query(
            bot: Text,
            log_type: str,
            start_idx: int = 0,
            page_size: int = 10,
            **kwargs):
        return BaseLogHandler.get_logs_search_result(
            bot = bot,
            log_type = log_type,
            start_idx = start_idx,
            page_size = page_size,
            **kwargs
        )

    @staticmethod
    def get_field_ids_for_log_type(log_type):
        logs_metadata = Utility.system_metadata.get("logs", {})
        return {col["id"] for col in logs_metadata.get(log_type, []) if "id" in col}

    @staticmethod
    def sanitize_query_filter(log_type: str, request) -> dict:
        """
        Sanitize and validate query parameters for the given log type.
        """
        doc_type = BaseLogHandler._get_doc_type(log_type)
        if doc_type is None:
            raise ValueError(f"Unsupported log type: {log_type}")

        raw_params = dict(request.query_params)
        valid_fields = MongoProcessor.get_field_ids_for_log_type(log_type)
        sanitized = {}
        if raw_params:
            if raw_params.get("from_date"):
                from_date = raw_params.pop("from_date")
                try:
                    sanitized["from_date"] = date.fromisoformat(from_date)
                except ValueError:
                    raise AppException(f"Invalid date format for 'from_date': '{from_date}'. Use YYYY-MM-DD.")
            if raw_params.get("to_date"):
                to_date = raw_params.pop("to_date")
                try:
                    sanitized["to_date"] = date.fromisoformat(to_date)
                except ValueError:
                    raise AppException(f"Invalid date format for 'to_date': '{to_date}'. Use YYYY-MM-DD.")
            if "from_date" in sanitized and "to_date" in sanitized and sanitized["from_date"] > sanitized["to_date"]:
                raise AppException("'from date' should be less than or equal to 'to date'")

        for k, v in raw_params.items():
            if k in {"start_idx", "page_size"}:
                if not v.isdigit():
                    raise AppException(f"'{k}' must be a valid integer.")
                sanitized[k] = int(v)
            else:
                if Utility.check_empty_string(k):
                    raise AppException("Search key cannot be empty or blank.")

                if k not in valid_fields:
                    raise AppException(f"Invalid query key: '{k}' for log_type: '{log_type}'")

                if Utility.check_empty_string(v):
                    raise AppException(f"Search value for key '{k}' cannot be empty or blank.")

                sanitized[k] = v
        return sanitized
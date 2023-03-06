import itertools
import json
import os
import uuid
import networkx as nx
from collections import ChainMap
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Text, Dict, List
from urllib.parse import urljoin

from pandas import DataFrame
from rasa.shared.core.constants import RULE_SNIPPET_ACTION_NAME, DEFAULT_INTENTS, REQUESTED_SLOT, \
    DEFAULT_KNOWLEDGE_BASE_ACTION, SESSION_START_METADATA_SLOT
import yaml
from fastapi import File
from loguru import logger as logging
from mongoengine import Document
from mongoengine.errors import DoesNotExist
from mongoengine.errors import NotUniqueError
from mongoengine.queryset.visitor import Q
from rasa.shared.constants import DEFAULT_CONFIG_PATH, DEFAULT_DATA_PATH, DEFAULT_DOMAIN_PATH, INTENT_MESSAGE_PREFIX
from rasa.shared.core.domain import InvalidDomain
from rasa.shared.core.domain import SessionConfig
from rasa.shared.core.events import ActionExecuted, UserUttered, ActiveLoop
from rasa.shared.core.events import SlotSet
from rasa.shared.core.slots import CategoricalSlot, FloatSlot
from rasa.shared.core.training_data.story_writer.yaml_story_writer import YAMLStoryWriter
from rasa.shared.core.training_data.structures import Checkpoint, RuleStep
from rasa.shared.core.training_data.structures import STORY_START
from rasa.shared.core.training_data.structures import StoryGraph, StoryStep
from rasa.shared.importers.rasa import Domain
from rasa.shared.importers.rasa import RasaFileImporter
from rasa.shared.nlu.constants import TEXT
from rasa.shared.nlu.training_data.message import Message
from rasa.shared.nlu.training_data.training_data import TrainingData
from rasa.shared.utils.io import read_config_file

from kairon.api import models
from kairon.exceptions import AppException
from kairon.shared.importer.processor import DataImporterLogProcessor
from kairon.shared.actions.data_objects import HttpActionConfig, HttpActionRequestBody, ActionServerLogs, Actions, \
    SlotSetAction, FormValidationAction, EmailActionConfig, GoogleSearchAction, JiraAction, ZendeskAction, \
    PipedriveLeadsAction, SetSlots, HubspotFormsAction, HttpActionResponse, SetSlotsFromResponse, \
    CustomActionRequestParameters, KaironTwoStageFallbackAction, QuickReplies, RazorpayAction
from kairon.shared.actions.models import KAIRON_ACTION_RESPONSE_SLOT, ActionType, BOT_ID_SLOT, HttpRequestContentType, \
    ActionParameterType
from kairon.shared.models import StoryEventType, TemplateType, StoryStepType, HttpContentType, StoryType
from kairon.shared.utils import Utility, StoryValidator
from .base_data import AuditLogData
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
    UTTERANCE_TYPE, CUSTOM_ACTIONS, REQUIREMENTS, EVENT_STATUS, COMPONENT_COUNT, SLOT_TYPE,
    DEFAULT_NLU_FALLBACK_RULE, DEFAULT_NLU_FALLBACK_RESPONSE, DEFAULT_ACTION_FALLBACK_RESPONSE, ENDPOINT_TYPE,
    TOKEN_TYPE, KAIRON_TWO_STAGE_FALLBACK, DEFAULT_NLU_FALLBACK_UTTERANCE_NAME, ACCESS_ROLES, LogType, GPT_LLM_FAQ,
    DEFAULT_LLM_FALLBACK_RULE
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
    Utterances, BotSettings, ChatClientConfig, SlotMapping, KeyVault, EventConfig, TrainingDataGenerator,
    MultiflowStories, MultiflowStoryEvents, BotContent
)
from .utils import DataUtility
from werkzeug.utils import secure_filename


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
        :param bot: bot id
        :param user: user id
        :param overwrite: whether to append or overwrite, default is overwite
        :return: None
        """
        training_file_loc = await DataUtility.save_training_files(nlu, domain, config, stories, rules, http_action)
        await self.save_from_path(training_file_loc['root'], bot, overwrite, user)
        Utility.delete_directory(training_file_loc['root'])

    def download_files(self, bot: Text):
        """
        create zip file containing download data

        :param bot: bot id
        :return: zip file path
        """
        nlu = self.load_nlu(bot)
        domain = self.load_domain(bot)
        stories = self.load_stories(bot)
        config = self.load_config(bot)
        rules = self.get_rules_for_training(bot)
        actions = self.load_action_configurations(bot)
        return Utility.create_zip_file(nlu, domain, stories, config, bot, rules, actions)

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
            actions_yml = os.path.join(path, 'actions.yml')
            importer = RasaFileImporter.load_from_config(config_path=config_path,
                                                         domain_path=domain_path,
                                                         training_data_paths=training_data_path)
            domain = await importer.get_domain()
            story_graph = await importer.get_stories()
            config = await importer.get_config()
            nlu = await importer.get_nlu_data(config.get('language'))
            actions = Utility.read_yaml(actions_yml)
            TrainingDataValidator.validate_custom_actions(actions)

            self.save_training_data(bot, user, config, domain, story_graph, nlu, actions, overwrite,
                                    REQUIREMENTS.copy())
        except Exception as e:
            logging.exception(e)
            raise AppException(e)

    def save_training_data(self, bot: Text, user: Text, config: dict = None, domain: Domain = None,
                           story_graph: StoryGraph = None, nlu: TrainingData = None, actions: dict = None,
                           overwrite: bool = False, what: set = REQUIREMENTS.copy()):
        if overwrite:
            self.delete_bot_data(bot, user, what)

        if 'actions' in what:
            self.save_integrated_actions(actions, bot, user)
        if 'domain' in what:
            self.save_domain(domain, bot, user)
        if 'stories' in what:
            self.save_stories(story_graph.story_steps, bot, user)
        if 'nlu' in what:
            self.save_nlu(nlu, bot, user)
        if 'rules' in what:
            self.save_rules(story_graph.story_steps, bot, user)
        if 'config' in what:
            self.add_or_overwrite_config(config, bot, user)

    def apply_config(self, template: Text, bot: Text, user: Text):
        """
        apply config template

        :param template: template name
        :param bot: bot id
        :param user: user id
        :return: None
        :raises: AppException
        """
        config_path = os.path.join("./template/config", secure_filename(template) + ".yml")
        if os.path.exists(config_path):
            self.save_config(read_config_file(config_path), bot=bot, user=user)
        else:
            raise AppException("Invalid config!")

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
        if 'domain' in what:
            self.delete_domain(bot, user)
        if 'stories' in what:
            self.delete_stories(bot, user)
        if 'nlu' in what:
            self.delete_nlu(bot, user)
        if 'config' in what:
            self.delete_config(bot, user)
        if 'rules' in what:
            self.delete_rules(bot, user)
        if 'actions' in what:
            self.delete_bot_actions(bot, user)

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
            [TrainingExamples, EntitySynonyms, LookupTables, RegexFeatures], bot=bot
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
        actions = list(filter(lambda actions: not actions.startswith('utter_'), domain.user_actions))
        self.__save_actions(actions, bot, user)
        self.__save_responses(domain.templates, bot, user)
        self.save_utterances(domain.templates.keys(), bot, user)
        self.__save_slots(domain.slots, bot, user)
        self.__save_forms(domain.forms, bot, user)
        self.__save_session_config(domain.session_config, bot, user)

    def delete_domain(self, bot: Text, user: Text):
        """
        soft deletes domain data

        :param bot: bot id
        :param user: user id
        :return: None
        """
        Utility.hard_delete_document([
            Intents, Entities, Forms, FormValidationAction, Responses, Slots, SlotMapping, Utterances
        ], bot=bot)
        Utility.hard_delete_document([Actions], bot=bot, type=None)

    def load_domain(self, bot: Text) -> Domain:
        """
        loads domain data for training

        :param bot: bot id
        :return: dict of Domain objects
        """
        intent_properties = self.__prepare_training_intents_and_properties(bot)

        domain_dict = {
            DOMAIN.INTENTS.value: intent_properties,
            DOMAIN.ACTIONS.value: self.__prepare_training_actions(bot),
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
        Utility.hard_delete_document([Stories], bot=bot)

    def load_stories(self, bot: Text) -> StoryGraph:
        """
        loads stories for training

        :param bot: bot id
        :return: StoryGraph
        """
        return self.__prepare_training_story(bot)

    def load_multiflow_stories(self, bot: Text) -> StoryGraph:
        """
        loads stories for training

        :param bot: bot id
        :return: StoryGraph
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
            training_example = TrainingExamples.objects(bot=bot, text=text, status=True).get().to_mongo().to_dict()
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
            if 'text' in training_example.data and str(training_example.data['text']).lower() not in saved_training_examples:
                training_data = TrainingExamples()
                training_data.intent = str(training_example.data[TRAINING_EXAMPLE.INTENT.value])
                training_data.text = training_example.data['text']
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
            EntitySynonyms.objects(bot=bot, status=True).values_list('value')
        )
        return synonyms

    def __extract_synonyms(self, synonyms, bot: Text, user: Text):
        saved_synonyms = self.__fetch_all_synonyms_value(bot)
        for key, value in synonyms.items():
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
        entitySynonyms = EntitySynonyms.objects(bot=bot, status=status)
        for entitySynonym in entitySynonyms:
            yield {entitySynonym.value: entitySynonym.name}

    def __prepare_training_synonyms(self, bot: Text):
        synonyms = list(self.fetch_synonyms(bot))
        return dict(ChainMap(*synonyms))

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
            message.data = {TRAINING_EXAMPLE.INTENT.value: trainingExample.intent, TEXT: trainingExample.text}
            if trainingExample.entities:
                message.data[TRAINING_EXAMPLE.ENTITIES.value] = list(
                    self.__prepare_entities(trainingExample.entities)
                )
            yield message

    def __prepare_training_examples(self, bot: Text):
        return list(self.fetch_training_examples(bot))

    def __fetch_all_lookup_values(self, bot: Text):
        lookup_tables = list(
            LookupTables.objects(bot=bot, status=True).values_list('value')
        )

        return lookup_tables

    def __extract_lookup_tables(self, lookup_tables, bot: Text, user: Text):
        saved_lookup = self.__fetch_all_lookup_values(bot)
        for lookup_table in lookup_tables:
            name = lookup_table[LOOKUP_TABLE.NAME.value]
            for element in lookup_table[LOOKUP_TABLE.ELEMENTS.value]:
                if element not in saved_lookup:
                    new_lookup = LookupTables(name=name, value=element, bot=bot, user=user)
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
            RegexFeatures.objects(bot=bot, status=True).values_list('pattern')
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
            if intent.strip().lower() not in saved_intents:
                entities = intents[intent].get('used_entities')
                use_entities = True if entities else False
                new_intent = Intents(name=intent, bot=bot, user=user, use_entities=use_entities)
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
        intents = Intents.objects(bot=bot, status=status).values_list('name')
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
            used_entities = intent['use_entities']
            intent_property[intent['name']] = use_entities_true.copy() if used_entities else use_entities_false.copy()
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
        entities = Entities.objects(bot=bot, status=status).values_list('name')
        return list(entities)

    def __prepare_training_domain_entities(self, bot: Text):
        entities = self.fetch_domain_entities(bot)
        return entities

    def __extract_forms(self, forms, bot: Text, user: Text):
        saved_forms = list(self.fetch_forms(bot, status=True) or [])
        saved_form_names = {key for name_mapping in saved_forms for key in name_mapping.keys()}
        for form, mappings in forms.items():
            if form not in saved_form_names:
                yield self.__save_form_logic(form, mappings.get('required_slots') or {}, bot, user)

    def __save_form_logic(self, name, mapping, bot, user):
        required_slots = []
        existing_slot_mappings = SlotMapping.objects(bot=bot, status=True).values_list('slot')
        existing_slots = Slots.objects(bot=bot, status=True).values_list('name')
        for slot_name, slot_mapping in mapping.items():
            if slot_name not in existing_slots:
                self.add_slot({"name": slot_name, "type": "any", 'auto_fill': True, 'mapping': slot_mapping},
                              bot, user,
                              raise_exception_if_exists=False)
            if slot_name not in existing_slot_mappings:
                SlotMapping(slot=slot_name, mapping=slot_mapping, bot=bot, user=user).save()
            required_slots.append(slot_name)
        if Utility.is_exist(Actions, raise_error=False, name=f'validate_{name}', bot=bot, status=True):
            form_validation_action = Actions.objects(name=f'validate_{name}', bot=bot, status=True).get()
            form_validation_action.type = ActionType.form_validation_action.value
            form_validation_action.save()
        form = Forms(name=name, required_slots=required_slots, bot=bot, user=user)
        form.clean()
        return form

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
            slot_mapping = {}
            for slot in form.required_slots:
                saved_slot_mapping = SlotMapping.objects(slot=slot, bot=bot, status=True).get()
                slot_mapping.update({slot: saved_slot_mapping.mapping})
            yield {form.name: slot_mapping}

    def __prepare_training_forms(self, bot: Text):
        forms = list(self.fetch_forms(bot))
        form_dict = {}
        for form in forms:
            for name, mapping in form.items():
                form_dict[name] = mapping
        return form_dict

    def __extract_actions(self, actions, bot: Text, user: Text):
        saved_actions = self.__prepare_training_actions(bot)
        for action in actions:
            if action.strip().lower() not in saved_actions:
                new_action = Actions(name=action, bot=bot, user=user)
                new_action.clean()
                yield new_action

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
        actions = Actions.objects(bot=bot, status=status).values_list('name')
        return list(actions)

    def __prepare_training_actions(self, bot: Text):
        actions = self.fetch_actions(bot)
        return actions

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
            logging.exception(e)
            raise AppException("Session Config already exists for the bot")
        except Exception as e:
            logging.exception(e)
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
            existing_utterances = Utterances.objects(bot=bot, status=True).values_list('name')
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
        saved_slots = list(
            Slots.objects(bot=bot, status=True).values_list('name')
        )
        return saved_slots

    def __extract_slots(self, slots, bot: Text, user: Text):
        """
        If influence_conversation flag is not present for a slot, then it is assumed to be
        set to false by rasa.
        """
        slots_name_list = self.__fetch_slot_names(bot)
        slots_name_list.extend([REQUESTED_SLOT.lower(),
                                DEFAULT_KNOWLEDGE_BASE_ACTION.lower(),
                                SESSION_START_METADATA_SLOT.lower()])
        for slot in slots:
            items = vars(slot)
            if items["name"].strip().lower() not in slots_name_list:
                items["type"] = slot.type_name
                items["value_reset_delay"] = items["_value_reset_delay"]
                items.pop("_value_reset_delay")
                items["bot"] = bot
                items["user"] = user
                items.pop("_value")
                new_slot = Slots._from_son(items)
                new_slot.clean()
                yield new_slot

    def __save_slots(self, slots, bot: Text, user: Text):
        if slots:
            new_slots = list(self.__extract_slots(slots, bot, user))
            if new_slots:
                Slots.objects.insert(new_slots)
        self.add_system_required_slots(bot, user)

    def add_system_required_slots(self, bot: Text, user: Text):
        self.add_slot({
            "name": BOT_ID_SLOT, "type": "any", "initial_value": bot, "auto_fill": False,
            "influence_conversation": False}, bot, user, raise_exception_if_exists=False
        )
        self.add_slot({
            "name": KAIRON_ACTION_RESPONSE_SLOT, "type": "any", "auto_fill": False, "initial_value": None,
            "influence_conversation": False}, bot, user, raise_exception_if_exists=False
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
        results = []
        for slot in slots:
            key = slot.name
            if slot.type == FloatSlot.type_name:
                value = {
                    SLOTS.INITIAL_VALUE.value: slot.initial_value,
                    SLOTS.VALUE_RESET_DELAY.value: slot.value_reset_delay,
                    SLOTS.AUTO_FILL.value: slot.auto_fill,
                    SLOTS.MIN_VALUE.value: slot.min_value,
                    SLOTS.MAX_VALUE.value: slot.max_value,
                }
            elif slot.type == CategoricalSlot.type_name:
                value = {
                    SLOTS.INITIAL_VALUE.value: slot.initial_value,
                    SLOTS.VALUE_RESET_DELAY.value: slot.value_reset_delay,
                    SLOTS.AUTO_FILL.value: slot.auto_fill,
                    SLOTS.VALUES.value: slot.values,
                }
            else:
                value = {
                    SLOTS.INITIAL_VALUE.value: slot.initial_value,
                    SLOTS.VALUE_RESET_DELAY.value: slot.value_reset_delay,
                    SLOTS.AUTO_FILL.value: slot.auto_fill,
                }
            value[SLOTS.TYPE.value] = slot.type
            value['influence_conversation'] = slot.influence_conversation
            results.append({key: value})
        return dict(ChainMap(*results))

    def __extract_story_events(self, events):
        for event in events:
            if isinstance(event, UserUttered):
                entities = [Entity(
                    start=entity.get('start'),
                    end=entity.get('end'),
                    value=entity.get('value'),
                    entity=entity.get('entity')) for entity in event.entities]
                story_event = StoryEvents(type=event.type_name, name=event.intent_name, entities=entities)
                story_event.clean()
                yield story_event
            elif isinstance(event, ActionExecuted):
                story_event = StoryEvents(type=event.type_name, name=event.action_name)
                story_event.clean()
                yield story_event
            elif isinstance(event, ActiveLoop):
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
            Stories.objects(bot=bot, status=True).values_list('block_name')
        )
        return saved_stories

    def __extract_story_step(self, story_steps, bot: Text, user: Text):
        saved_stories = self.__fetch_story_block_names(bot)
        for story_step in story_steps:
            if not isinstance(story_step, RuleStep) and story_step.block_name.strip().lower() not in saved_stories:
                story_events = list(self.__extract_story_events(story_step.events))
                template_type = DataUtility.get_template_type(story_events)
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
                    template_type=template_type
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

    def __prepare_training_story_events(self, events, timestamp):
        for event in events:
            if event.type == UserUttered.type_name:
                entities = []
                if event.entities:
                    entities = [{"start": entity['start'],
                                 "end": entity['end'],
                                 "value": entity['value'],
                                 "entity": entity['entity']} for entity in event.entities]

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

    def __prepare_training_multiflow_story_events(self, events, timestamp):
        roots = []
        leaves = []
        paths = []
        events = StoryValidator.get_graph(events)
        for node in events.nodes:
            if events.in_degree(node) == 0:
                roots.append(node)
            elif events.out_degree(node) == 0:
                leaves.append(node)

        for root in roots:
            for leaf in leaves:
                for path in nx.all_simple_paths(events, root, leaf):
                    paths.append(path)
        for path in paths:
            for event in path:
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
                    yield UserUttered(
                        text=event.name,
                        intent=intent,
                        parse_data=parse_data,
                        timestamp=timestamp,
                        entities=[],
                    )
                else:
                    yield ActionExecuted(action_name=event.name, timestamp=timestamp)

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
                    story.events, datetime.now().timestamp()
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
        for story in MultiflowStories.objects(bot=bot, status=True):
            events = story.to_mongo().to_dict()['events']
            story_events = list(
                self.__prepare_training_multiflow_story_events(
                    events, datetime.now().timestamp()
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

    def __prepare_training_story(self, bot: Text):
        return StoryGraph(list(self.__prepare_training_story_step(bot)))

    def __prepare_training_multiflow_story(self, bot: Text):
        return StoryGraph(list(self.__prepare_training_multiflow_story_step(bot)))

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
            logging.exception(e)
            raise AppException(e)

    def add_or_overwrite_config(self, configs: dict, bot: Text, user: Text):
        """
        saves bot configuration

        :param configs: configuration
        :param bot: bot id
        :param user: user id
        :return: config unique id
        """
        try:
            config_obj = Configs.objects().get(bot=bot)
            config_obj.pipeline = configs["pipeline"]
            config_obj.language = configs["language"]
            config_obj.policies = configs["policies"]
        except DoesNotExist:
            configs["bot"] = bot
            configs["user"] = user
            config_obj = Configs._from_son(configs)
        self.add_default_fallback_config(config_obj, bot, user)
        return config_obj.save().to_mongo().to_dict()["_id"].__str__()

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

        if not nlu_epochs and not response_epochs and not ted_epochs and not nlu_confidence_threshold and not action_fallback:
            raise AppException("At least one field is required")

        present_config = self.load_config(bot)
        if nlu_confidence_threshold:
            fallback_classifier_idx = next(
                (idx for idx, comp in enumerate(present_config['pipeline']) if comp["name"] == "FallbackClassifier"),
                None)
            if fallback_classifier_idx:
                del present_config['pipeline'][fallback_classifier_idx]
            diet_classifier_idx = next(
                (idx for idx, comp in enumerate(present_config['pipeline']) if comp["name"] == "DIETClassifier"), None)
            fallback = {'name': 'FallbackClassifier', 'threshold': nlu_confidence_threshold}
            present_config['pipeline'].insert(diet_classifier_idx + 1, fallback)
            rule_policy = next((comp for comp in present_config['policies'] if comp["name"] == "RulePolicy"), {})
            if not rule_policy:
                rule_policy['name'] = 'RulePolicy'
                present_config['policies'].append(rule_policy)

        if action_fallback:
            action_fallback_threshold = action_fallback_threshold if action_fallback_threshold else 0.3
            if action_fallback == 'action_default_fallback':
                utterance_exists = Utility.is_exist(Responses, raise_error=False, bot=bot, status=True,
                                                    name__iexact='utter_default')
                if not utterance_exists:
                    raise AppException("Utterance utter_default not defined")
            else:
                utterance_exists = Utility.is_exist(Responses, raise_error=False, bot=bot, status=True,
                                                    name__iexact=action_fallback)
                if not (utterance_exists or
                        Utility.is_exist(Actions, raise_error=False, bot=bot, status=True,
                                         name__iexact=action_fallback)):
                    raise AppException(f"Action fallback {action_fallback} does not exists")
            fallback = next((comp for comp in present_config['policies'] if comp["name"] == "RulePolicy"), {})
            if not fallback:
                fallback['name'] = 'RulePolicy'
                present_config['policies'].append(fallback)
            fallback['core_fallback_action_name'] = action_fallback
            fallback['core_fallback_threshold'] = action_fallback_threshold

        nlu_fallback = next((comp for comp in present_config['pipeline'] if comp["name"] == "FallbackClassifier"), {})
        action_fallback = next((comp for comp in present_config['policies'] if comp["name"] == "RulePolicy"), {})
        if nlu_fallback.get('threshold') and action_fallback.get('core_fallback_threshold'):
            if nlu_fallback['threshold'] < action_fallback['core_fallback_threshold']:
                raise AppException('Action fallback threshold should always be smaller than nlu fallback threshold')

        Utility.add_or_update_epoch(present_config, configs)
        self.save_config(present_config, bot, user)

    def list_epoch_and_fallback_config(self, bot: Text):
        config = self.load_config(bot)
        selected_config = {}
        nlu_fallback = next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), {})
        action_fallback = next((comp for comp in config['policies'] if comp["name"] == "RulePolicy"), {})
        ted_policy = next((comp for comp in config['policies'] if comp["name"] == "TEDPolicy"), {})
        diet_classifier = next((comp for comp in config['pipeline'] if comp["name"] == "DIETClassifier"), {})
        response_selector = next((comp for comp in config['pipeline'] if comp["name"] == "ResponseSelector"), {})
        selected_config['nlu_confidence_threshold'] = nlu_fallback.get('threshold') if nlu_fallback.get(
            'threshold') else None
        selected_config['action_fallback'] = action_fallback.get('core_fallback_action_name')
        selected_config['action_fallback_threshold'] = action_fallback.get(
            'core_fallback_threshold') if action_fallback.get('core_fallback_threshold') else None
        selected_config['ted_epochs'] = ted_policy.get('epochs')
        selected_config['nlu_epochs'] = diet_classifier.get('epochs')
        selected_config['response_epochs'] = response_selector.get('epochs')
        return selected_config

    def delete_config(self, bot: Text, user: Text):
        """
        soft deletes bot training configuration

        :param bot: bot id
        :param user: user id
        :return: None
        """
        Utility.hard_delete_document([Configs], bot=bot)

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
                read_config_file(Utility.environment["model"]["train"]["default_model_training_config_path"])
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
            if key in ["language", "pipeline", "policies"]
        }

    def add_training_data(self, training_data: List[models.TrainingData], bot: Text, user: Text, is_integration: bool):
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
                    text=data.intent,
                    bot=bot,
                    user=user,
                    is_integration=is_integration
                )
                status[data.intent] = intent_id
            except AppException as e:
                status[data.intent] = str(e)

            story_name = "path_" + data.intent
            utterance = "utter_" + data.intent
            events = [
                {"name": data.intent, "type": "INTENT"},
                {"name": utterance, "type": "BOT"}]
            try:
                doc_id = self.add_complex_story(
                    story={'name': story_name, 'steps': events, 'type': 'STORY',
                           'template_type': TemplateType.CUSTOM.value},
                    bot=bot,
                    user=user
                )
                status['story'] = doc_id
            except AppException as e:
                status['story'] = str(e)
            try:
                status_message = list(
                    self.add_training_example(
                        data.training_examples, data.intent, bot, user,
                        is_integration)
                )
                status['training_examples'] = status_message
                training_examples = []
                for training_data_add_status in status_message:
                    if training_data_add_status['_id']:
                        training_examples.append(training_data_add_status['text'])
                training_data_added[data.intent] = training_examples
            except AppException as e:
                status['training_examples'] = str(e)

            try:
                utterance_id = self.add_text_response(
                    data.response, utterance, bot, user
                )
                status['responses'] = utterance_id
            except AppException as e:
                status['responses'] = str(e)
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

        Utility.is_exist(
            Intents,
            exp_message="Intent already exists!",
            name__iexact=text.strip(),
            bot=bot,
            status=True,
        )
        saved = Intents(name=text, bot=bot, user=user,
                        is_integration=is_integration).save().to_mongo().to_dict()
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
            self, examples: List[Text], intent: Text, bot: Text, user: Text, is_integration: bool
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
                intent_for_example = Utility.retrieve_field_values(TrainingExamples,
                                                                   field=TrainingExamples.intent.name,
                                                                   text__iexact=text, bot=bot, status=True)
                if intent_for_example:
                    yield {
                        "text": example,
                        "message": f'Training Example exists in intent: {intent_for_example}',
                        "_id": None,
                    }
                else:
                    if entities:
                        new_entities = self.save_entities_and_add_slots(entities, bot, user)
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
                        new_entities_as_dict = [json.loads(e.to_json()) for e in new_entities]
                    yield {
                        "text": DataUtility.prepare_nlu_text(text, new_entities_as_dict),
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
            raise AppException('Intent does not exists')

        for example in examples:
            if Utility.check_empty_string(example):
                yield {"text": example, "_id": None, "message": "Training Example cannot be empty or blank spaces"}
                continue

            text, entities = DataUtility.extract_text_and_entities(example.strip())
            new_entities_as_dict = []
            try:
                training_example = TrainingExamples.objects(text__iexact=text, bot=bot, status=True).get()
                training_example.intent = intent
                message = "Training Example moved"
                if training_example.entities:
                    new_entities_as_dict = [json.loads(e.to_json()) for e in training_example.entities]
            except DoesNotExist:
                if entities:
                    new_entities = self.save_entities_and_add_slots(entities, bot, user)
                    new_entities_as_dict = [json.loads(e.to_json()) for e in new_entities]
                else:
                    new_entities = None
                training_example = TrainingExamples(
                    intent=intent,
                    text=text,
                    entities=new_entities,
                    bot=bot,
                    user=user
                )
                message = "Training Example added"
            saved = training_example.save().to_mongo().to_dict()

            yield {
                "text": DataUtility.prepare_nlu_text(text, new_entities_as_dict),
                "_id": saved["_id"].__str__(),
                "message": message
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
            intent_for_example = Utility.retrieve_field_values(TrainingExamples,
                                                               field=TrainingExamples.intent.name, text__iexact=text,
                                                               entities=entities, bot=bot, status=True)
            if intent_for_example:
                raise AppException(f'Training Example exists in intent: {intent_for_example}')
            training_example = TrainingExamples.objects(bot=bot, intent=intent).get(
                id=id
            )
            training_example.user = user
            training_example.text = text
            if entities:
                training_example.entities = list(self.__extract_entities(entities))
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
                                    "_id": {"$toString": "$_id"}
                                }
                            }
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "intent": "$_id",
                            "training_examples": 1
                        }
                    }
                ]
            )
        )
        for data in intents_and_training_examples:
            intents_and_training_examples_dict[data['intent']] = data['training_examples']

        for intent in intents:
            if not intents_and_training_examples_dict.get(intent['name']):
                intents_and_training_examples_dict[intent['name']] = None
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
            TrainingExamples.objects(bot=bot, status=True).aggregate([
                {"$replaceRoot": {"newRoot": {"$arrayToObject": [[{'k': "$text", 'v': "$intent"}]]}}},
                {'$addFields': {'bot': bot}},
                {'$group': {'_id': '$bot', 'training_examples': {'$mergeObjects': '$$ROOT'}}},
                {'$unset': 'training_examples.bot'},
                {'$project': {'_id': 0, 'training_examples': 1}}])
        )
        if training_examples:
            training_examples = training_examples[0].get('training_examples', {})
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
            logging.exception(e)
            raise AppException("Unable to remove document")
        except Exception as e:
            logging.exception(e)
            raise AppException("Unable to remove document")

    def __prepare_document_list(self, documents: List[Document], field: Text):
        for document in documents:
            doc_dict = document.to_mongo().to_dict()
            yield {"_id": doc_dict["_id"].__str__(), field: doc_dict[field]}

    def add_entity(self, name: Text, bot: Text, user: Text, raise_exc_if_exists: bool = True):
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

    def delete_entity(self, name: Text, bot: Text, user: Text, raise_exc_if_not_exists: bool = True):
        """
        Deletes an entity.

        :param name: entity name
        :param bot: bot id
        :param user: user
        :param raise_exc_if_not_exists: raise exception if entity does not exists
        """
        try:
            entity = Entities.objects(name=name, bot=bot, status=True).get()
            entity.status = False
            entity.user = user
            entity.save()
        except DoesNotExist:
            if raise_exc_if_not_exists:
                raise AppException('Entity not found')

    def get_entities(self, bot: Text):
        """
        fetches list of registered entities

        :param bot: bot id
        :return: list of entities
        """
        entities = Entities.objects(bot=bot, status=True)
        return list(self.__prepare_document_list(entities, "name"))

    def add_action(self, name: Text, bot: Text, user: Text, raise_exception=True, action_type: ActionType = None):
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

        if not name.startswith('utter_') and not Utility.is_exist(
                Actions,
                raise_error=raise_exception,
                exp_message="Action exists!",
                name__iexact=name,
                bot=bot,
                status=True):
            action = (
                Actions(name=name, type=action_type, bot=bot, user=user).save().to_mongo().to_dict()
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

    def add_text_response(self, utterance: Text, name: Text, bot: Text, user: Text, form_attached: str = None):
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
        if form_attached and not Utility.is_exist(Forms, raise_error=False, name=form_attached, bot=bot, status=True):
            raise AppException(f"Form '{form_attached}' does not exists")
        return self.add_response(
            utterances={"text": utterance}, name=name, bot=bot, user=user, form_attached=form_attached
        )

    def add_custom_response(self, utterance: Dict, name: Text, bot: Text, user: Text, form_attached: str = None):
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
        if form_attached and not Utility.is_exist(Forms, raise_error=False, name=form_attached, bot=bot, status=True):
            raise AppException(f"Form '{form_attached}' does not exists")
        return self.add_response(
            utterances={"custom": utterance}, name=name, bot=bot, user=user, form_attached=form_attached
        )

    def add_response(self, utterances: Dict, name: Text, bot: Text, user: Text, form_attached: str = None):
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
        self.add_utterance_name(name=name, bot=bot, user=user, form_attached=form_attached)
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
            Responses.objects(bot=bot, status=True).order_by("-timestamp").aggregate(
                [
                    {
                        "$group": {
                            "_id": "$name",
                            "texts": {"$push": "$text"},
                            "customs": {"$push": "$custom"},
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "name": "$_id",
                            "texts": 1,
                            "customs": 1
                        }
                    }
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
            if steps[0]['name'] != RULE_SNIPPET_ACTION_NAME and steps[0]['type'] != ActionExecuted.type_name:
                events.append(StoryEvents(
                    name=RULE_SNIPPET_ACTION_NAME,
                    type=ActionExecuted.type_name))
        action_step_types = {s_type.value for s_type in StoryStepType}.difference({
            StoryStepType.intent.value, StoryStepType.form_start.value, StoryStepType.form_end.value
        })
        for step in steps:
            if step['type'] == StoryStepType.intent.value:
                events.append(StoryEvents(
                    name=step['name'].strip().lower(),
                    type=UserUttered.type_name))
            elif step['type'] in action_step_types:
                Utility.is_exist(Utterances,
                                 f'utterance "{step["name"]}" is attached to a form',
                                 bot=bot, name__iexact=step['name'], form_attached__ne=None)
                events.append(StoryEvents(
                    name=step['name'].strip().lower(),
                    type=ActionExecuted.type_name))
                if step['type'] == StoryStepType.action.value:
                    self.add_action(step['name'], bot, user, raise_exception=False)
            elif step['type'] == StoryStepType.form_start.value:
                events.append(StoryEvents(
                    name=step['name'].strip().lower(),
                    type=ActiveLoop.type_name))
            elif step['type'] == StoryStepType.form_end.value:
                events.append(StoryEvents(
                    name=None,
                    type=ActiveLoop.type_name))
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
        name = story['name']
        steps = story['steps']
        flowtype = story['type']
        if Utility.check_empty_string(name):
            raise AppException("path name cannot be empty or blank spaces")

        if not steps:
            raise AppException("steps are required")

        template_type = story.get('template_type')
        if not template_type:
            template_type = DataUtility.get_template_type(story)

        if flowtype == "STORY":
            data_class = Stories
            data_object = Stories()
            exception_message_name = "Story"
        elif flowtype == 'RULE':
            data_class = Rules
            data_object = Rules()
            exception_message_name = "Rule"
        else:
            raise AppException("Invalid type")
        Utility.is_exist(data_class,
                         bot=bot, status=True, block_name__iexact=name,
                         exp_message=f"{exception_message_name} with the name already exists")
        events = self.__complex_story_prepare_steps(steps, flowtype, bot, user)
        Utility.is_exist_query(data_class,
                               query=(Q(bot=bot) & Q(status=True)) & (Q(block_name__iexact=name) | Q(events=events)),
                               exp_message="Flow already exists!")

        data_object.block_name = name
        data_object.events = events
        data_object.bot = bot
        data_object.user = user
        data_object.start_checkpoints = [STORY_START]
        data_object.template_type = template_type

        id = (
            data_object.save().to_mongo().to_dict()["_id"].__str__()
        )

        self.add_slot({"name": "bot", "type": "any", "initial_value": bot, "influence_conversation": False}, bot, user,
                      raise_exception_if_exists=False)

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

        name = story['name']
        steps = story['steps']

        if Utility.check_empty_string(name):
            raise AppException("Story name cannot be empty or blank spaces")

        if not steps:
            raise AppException("steps are required")
        Utility.is_exist(MultiflowStories,
                         bot=bot, status=True, block_name__iexact=name,
                         exp_message="Multiflow Story with the name already exists")
        StoryValidator.validate_steps(steps)
        events = [MultiflowStoryEvents(**step) for step in steps]
        Utility.is_exist_query(MultiflowStories,
                               query=(Q(bot=bot) & Q(status=True)) & (Q(block_name__iexact=name) | Q(events=events)),
                               exp_message="Story flow already exists!")

        story_obj = MultiflowStories()
        story_obj.block_name = name
        story_obj.events = events
        story_obj.bot = bot
        story_obj.user = user
        story_obj.start_checkpoints = [STORY_START]

        id = (
            story_obj.save().to_mongo().to_dict()["_id"].__str__()
        )

        self.add_slot({"name": "bot", "type": "any", "initial_value": bot, "influence_conversation": False}, bot, user,
                      raise_exception_if_exists=False)

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
        name = story['name']
        steps = story['steps']
        flowtype = story['type']
        if Utility.check_empty_string(name):
            raise AppException("path name cannot be empty or blank spaces")

        if not steps:
            raise AppException("steps are required")

        if flowtype == 'STORY':
            data_class = Stories
            exception_message_name = "Story"
        elif flowtype == 'RULE':
            data_class = Rules
            exception_message_name = "Rule"
        else:
            raise AppException("Invalid type")
        Utility.is_exist(data_class,
                         bot=bot, status=True, block_name__iexact=name, id__ne=story_id,
                         exp_message=f"{exception_message_name} with the name already exists")
        try:
            data_object = data_class.objects(bot=bot, status=True, id=story_id).get()
        except DoesNotExist:
            raise AppException("Flow does not exists")

        events = self.__complex_story_prepare_steps(steps, flowtype, bot, user)
        data_object['events'] = events
        Utility.is_exist_query(
            data_class,
            query=(Q(id__ne=story_id) & Q(bot=bot) & Q(status=True) & Q(events=data_object['events'])),
            exp_message="Flow already exists!"
        )
        data_object['block_name'] = name
        story_id = (
            data_object.save().to_mongo().to_dict()["_id"].__str__()
        )
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
        name = story['name']
        steps = story['steps']
        if Utility.check_empty_string(name):
            raise AppException("Story name cannot be empty or blank spaces")

        if not steps:
            raise AppException("steps are required")
        StoryValidator.validate_steps(steps)
        Utility.is_exist(MultiflowStories,
                         bot=bot, status=True, block_name__iexact=name, id__ne=story_id,
                         exp_message="Multiflow Story with the name already exists")
        events = [MultiflowStoryEvents(**step) for step in steps]
        Utility.is_exist_query(MultiflowStories,
                               query=(Q(id__ne=story_id) & Q(bot=bot) & Q(status=True) & Q(events=events)),
                               exp_message="Story flow already exists!")

        try:
            story_obj = MultiflowStories.objects(bot=bot, status=True, id=story_id).get()
            story_obj.events = events
            story_obj.block_name = name
            story_id = (
                story_obj.save().to_mongo().to_dict()["_id"].__str__()
            )
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
            data_class.objects(bot=bot, status=True, id=story_id).get()
        except DoesNotExist:
            raise AppException("Flow does not exists")
        Utility.delete_document(
            [data_class], bot=bot, user=user, id=story_id
        )

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
        razorpay_actions = set(RazorpayAction.objects(bot=bot, status=True).values_list('name'))
        email_actions = set(EmailActionConfig.objects(bot=bot, status=True).values_list('action_name'))
        forms = set(Forms.objects(bot=bot, status=True).values_list('name'))
        data_list = list(Stories.objects(bot=bot, status=True))
        data_list.extend(list(Rules.objects(bot=bot, status=True)))
        for value in data_list:
            final_data = {}
            item = value.to_mongo().to_dict()
            block_name = item.pop("block_name")
            events = item.pop("events")
            final_data["_id"] = item["_id"].__str__()
            final_data['template_type'] = item.pop("template_type")
            if isinstance(value, Stories):
                final_data['type'] = StoryType.story.value
            elif isinstance(value, Rules):
                final_data['type'] = StoryType.rule.value
            else:
                continue
            steps = []
            for event in events:
                step = {}
                if isinstance(value, Rules) and event.get('name') == RULE_SNIPPET_ACTION_NAME and event['type'] == ActionExecuted.type_name:
                    continue
                if event['type'] == UserUttered.type_name:
                    step['name'] = event['name']
                    step['type'] = StoryStepType.intent.value
                elif event['type'] == ActionExecuted.type_name:
                    step['name'] = event['name']
                    if event['name'] in http_actions:
                        step['type'] = StoryStepType.http_action.value
                    elif event['name'] in reset_slot_actions:
                        step['type'] = StoryStepType.slot_set_action.value
                    elif event['name'] in google_search_actions:
                        step['type'] = StoryStepType.google_search_action.value
                    elif event['name'] in jira_actions:
                        step['type'] = StoryStepType.jira_action.value
                    elif event['name'] in email_actions:
                        step['type'] = StoryStepType.email_action.value
                    elif event['name'] in forms:
                        step['type'] = StoryStepType.form_action.value
                    elif event['name'] in zendesk_actions:
                        step['type'] = StoryStepType.zendesk_action.value
                    elif event['name'] in pipedrive_leads_actions:
                        step['type'] = StoryStepType.pipedrive_leads_action.value
                    elif event['name'] in hubspot_forms_actions:
                        step['type'] = StoryStepType.hubspot_forms_action.value
                    elif event["name"] in razorpay_actions:
                        step['type'] = StoryStepType.razorpay_action.value
                    elif event['name'] == KAIRON_TWO_STAGE_FALLBACK:
                        step['type'] = StoryStepType.two_stage_fallback_action.value
                    elif str(event['name']).startswith("utter_"):
                        step['type'] = StoryStepType.bot.value
                    else:
                        step['type'] = StoryStepType.action.value
                elif event['type'] == ActiveLoop.type_name:
                    step['type'] = StoryStepType.form_end.value
                    if not Utility.check_empty_string(event.get('name')):
                        step['name'] = event['name']
                        step['type'] = StoryStepType.form_start.value
                if step:
                    steps.append(step)

            final_data['name'] = block_name
            final_data['steps'] = steps
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
            final_data['type'] = StoryType.multiflow_story.value
            final_data["_id"] = item["_id"].__str__()
            final_data['name'] = block_name
            final_data['steps'] = events
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
        actions = HttpActionConfig.objects(bot=bot, status=True).distinct(field="action_name")
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
                if search and event.type == StoryEventType.action and event.name in responses:
                    return event.name, UTTERANCE_TYPE.BOT
                elif search and event.type == StoryEventType.action and event.name == CUSTOM_ACTIONS.HTTP_ACTION_NAME:
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

        return session_config.save().to_mongo().to_dict()["_id"].__str__()

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
            token = endpoint_config[ENDPOINT_TYPE.HISTORY_ENDPOINT.value].get('token')
            if not Utility.check_empty_string(token):
                if len(token) < 8:
                    raise AppException('token must contain at least 8 characters')
                if ' ' in token:
                    raise AppException('token cannot contain spaces')
                encrypted_token = Utility.encrypt_message(token)
                endpoint_config[ENDPOINT_TYPE.HISTORY_ENDPOINT.value]['token'] = encrypted_token
            endpoint.history_endpoint = EndPointHistory(
                **endpoint_config.get(ENDPOINT_TYPE.HISTORY_ENDPOINT.value)
            )

        endpoint.bot = bot
        endpoint.user = user
        return endpoint.save().to_mongo().to_dict()["_id"].__str__()

    def delete_endpoint(self, bot: Text, endpoint_type: ENDPOINT_TYPE):
        """
        delete endpoint configuration

        :param bot: bot id
        :param endpoint_type: Type of endpoint
        :return:
        """
        if not endpoint_type:
            raise AppException('endpoint_type is required for deletion')
        try:
            current_endpoint_config = Endpoints.objects().get(bot=bot)
            if current_endpoint_config.__getitem__(endpoint_type):
                current_endpoint_config.__setitem__(endpoint_type, None)
                current_endpoint_config.save()
            else:
                raise AppException("Endpoint not configured")
        except DoesNotExist as e:
            logging.exception(e)
            raise AppException("No Endpoint configured")

    def get_history_server_endpoint(self, bot):
        endpoint_config = None
        try:
            endpoint_config = self.get_endpoints(bot)
        except AppException:
            pass
        if endpoint_config and endpoint_config.get(ENDPOINT_TYPE.HISTORY_ENDPOINT.value):
            history_endpoint = endpoint_config.get(ENDPOINT_TYPE.HISTORY_ENDPOINT.value)
            history_endpoint['type'] = 'user'
        elif Utility.environment['history_server'].get('url'):
            history_endpoint = {'url': Utility.environment['history_server']['url'],
                                'token': Utility.environment['history_server'].get('token'), 'type': 'kairon'}
        else:
            raise AppException('No history server endpoint configured')
        return history_endpoint

    def get_endpoints(self, bot: Text, raise_exception=True, mask_characters: bool = False):
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
                token = endpoint[ENDPOINT_TYPE.HISTORY_ENDPOINT.value].get('token')
                if not Utility.check_empty_string(token):
                    decrypted_token = Utility.decrypt_message(token)
                    if mask_characters:
                        decrypted_token = decrypted_token[:-3] + '***'
                    endpoint[ENDPOINT_TYPE.HISTORY_ENDPOINT.value]['token'] = decrypted_token

            return endpoint
        except DoesNotExist as e:
            logging.exception(e)
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
            self, intent: Text, bot: Text, user: Text, is_integration: bool, delete_dependencies=True
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
            MongoProcessor.get_attached_flows(bot, intent, 'user')
        except DoesNotExist as custEx:
            logging.exception(custEx)
            raise AppException(
                "Invalid IntentName: Unable to remove document: " + str(custEx)
            )

        if is_integration:
            if not intent_obj.is_integration:
                raise AppException("This intent cannot be deleted by an integration user")

        try:
            intent_obj.user = user
            intent_obj.status = False
            intent_obj.timestamp = datetime.utcnow()
            intent_obj.save(validate=False)

            if delete_dependencies:
                Utility.delete_document(
                    [TrainingExamples], bot=bot, user=user, intent__iexact=intent
                )
        except Exception as ex:
            logging.exception(ex)
            raise AppException("Unable to remove document" + str(ex))

    def delete_utterance(self, utterance_name: str, bot: str, validate_has_form: bool = True):
        if not (utterance_name and utterance_name.strip()):
            raise AppException("Utterance cannot be empty or spaces")
        try:
            responses = list(Responses.objects(name=utterance_name, bot=bot, status=True))
            if not responses:
                if Utility.is_exist(Utterances, raise_error=False, bot=bot, status=True, name__iexact=utterance_name):
                    self.delete_utterance_name(name=utterance_name, bot=bot, validate_has_form=validate_has_form,
                                               raise_exc=True)
                    return
                raise DoesNotExist("Utterance does not exists")
            MongoProcessor.get_attached_flows(bot, utterance_name, 'action')
            self.delete_utterance_name(name=utterance_name, bot=bot, validate_has_form=validate_has_form, raise_exc=True)
            for response in responses:
                response.status = False
                response.save()
        except DoesNotExist as e:
            raise AppException(e)

    def delete_response(self, utterance_id: str, bot: str, user: str):
        if not (utterance_id and utterance_id.strip()):
            raise AppException("Utterance Id cannot be empty or spaces")
        try:
            response = Responses.objects(bot=bot, status=True).get(id=utterance_id)
            if response is None:
                raise DoesNotExist()
            utterance_name = response['name']
            story = MongoProcessor.get_attached_flows(bot, utterance_name, 'action', False)
            responses = list(Responses.objects(bot=bot, status=True, name__iexact=utterance_name))

            if story and len(responses) <= 1:
                raise AppException("At least one response is required for utterance linked to story")
            if len(responses) <= 1:
                self.delete_utterance_name(name=utterance_name, bot=bot, validate_has_form=True, raise_exc=True)
            self.remove_document(Responses, utterance_id, bot, user)
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
        if not Utility.is_exist(
                HttpActionConfig, raise_error=False, action_name__iexact=request_data['action_name'], bot=bot,
                status=True
        ):
            raise AppException("No HTTP action found for bot " + bot + " and action " + request_data['action_name'])
        for http_action in HttpActionConfig.objects(bot=bot, action_name=request_data['action_name'], status=True):
            content_type = {
                HttpContentType.application_json: HttpRequestContentType.json.value,
                HttpContentType.urlencoded_form_data: HttpRequestContentType.data.value
            }[request_data['content_type']]
            response = HttpActionResponse(**request_data.get('response', {})).to_mongo().to_dict()
            params_list = Utility.build_http_request_data_object(request_data.get('params_list', []))
            headers = Utility.build_http_request_data_object(request_data.get('headers', []))
            set_slots = [SetSlotsFromResponse(**slot).to_mongo().to_dict() for slot in
                         request_data.get('set_slots')]
            http_action.update(
                set__http_url=request_data['http_url'], set__request_method=request_data['request_method'],
                set__content_type=content_type, set__params_list=params_list, set__headers=headers,
                set__response=response, set__set_slots=set_slots, set__user=user, set__timestamp=datetime.utcnow()
            )
            return http_action.to_mongo().to_dict()["_id"].__str__()

    def add_http_action_config(self, http_action_config: Dict, user: str, bot: str):
        """
        Adds a new Http action.
        :param http_action_config: dict object containing configuration for the Http action
        :param user: user id
        :param bot: bot id
        :return: Http configuration id for saved Http action config
        """
        Utility.is_valid_action_name(http_action_config.get("action_name"), bot, HttpActionConfig)
        http_action_params = [HttpActionRequestBody(**param) for param in http_action_config.get("params_list") or []]
        headers = [HttpActionRequestBody(**param) for param in http_action_config.get("headers") or []]
        content_type = {
            HttpContentType.application_json: HttpRequestContentType.json.value,
            HttpContentType.urlencoded_form_data: HttpRequestContentType.data.value
        }[http_action_config['content_type']]
        set_slots = [SetSlotsFromResponse(**slot) for slot in http_action_config.get('set_slots')]
        doc_id = HttpActionConfig(
            action_name=http_action_config['action_name'],
            content_type=content_type,
            http_url=http_action_config['http_url'],
            request_method=http_action_config['request_method'],
            params_list=http_action_params,
            headers=headers,
            response=HttpActionResponse(**http_action_config.get('response', {})),
            set_slots=set_slots,
            bot=bot,
            user=user
        ).save().to_mongo().to_dict()["_id"].__str__()
        self.add_action(http_action_config['action_name'], bot, user, action_type=ActionType.http_action.value,
                        raise_exception=False)
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
            http_config_dict = HttpActionConfig.objects().get(bot=bot, action_name=action_name,
                                                              status=True).to_mongo().to_dict()
            del http_config_dict['_id']
            for param in http_config_dict.get('headers', []):
                Utility.decrypt_action_parameter(param)
                param.pop('_cls')

            for param in http_config_dict.get('params_list', []):
                Utility.decrypt_action_parameter(param)
                param.pop('_cls')

            http_config_dict['content_type'] = {
                HttpRequestContentType.json.value: HttpContentType.application_json.value,
                HttpRequestContentType.data.value: HttpContentType.urlencoded_form_data.value
            }[http_config_dict['content_type']]
            return http_config_dict
        except DoesNotExist as ex:
            logging.exception(ex)
            raise AppException("No HTTP action found for bot " + bot + " and action " + action_name)

    def list_http_actions(self, bot: str):
        """
        Fetches all Http actions from collection.
        :param bot: bot id
        :param user: user id
        :return: List of Http actions.
        """
        actions = HttpActionConfig.objects(bot=bot, status=True)
        return list(self.__prepare_document_list(actions, "action_name"))

    def list_actions(self, bot: Text):
        all_actions = list(Actions.objects(bot=bot, status=True).aggregate([
            {
                '$group': {
                    '_id': {
                        '$ifNull': [
                            '$type', 'actions'
                        ]
                    },
                    'actions': {
                        '$addToSet': '$name'
                    }
                }
            }
        ]))
        all_actions = {action["_id"]: action["actions"] for action in all_actions}
        all_actions["utterances"] = list(Utterances.objects(bot=bot, status=True).values_list('name'))
        action_types = [a_type.value for a_type in ActionType]
        action_types.append("actions")
        for a_type in action_types:
            if a_type not in all_actions.keys():
                all_actions[a_type] = []
        if all_actions.get("actions"):
            actions = all_actions["actions"]
            actions = [action for action in actions if not str(action).startswith("utter_")]
            all_actions["actions"] = actions
        return all_actions

    def list_http_action_names(self, bot: Text):
        actions = list(HttpActionConfig.objects(bot=bot, status=True).values_list('action_name'))
        return actions

    def add_google_search_action(self, action_config: dict, bot: Text, user: Text):
        """
        Add a new google search action

        :param action_config: google search action configuration
        :param bot: bot id
        :param user: user id
        :return: doc id
        """
        Utility.is_valid_action_name(action_config.get("name"), bot, GoogleSearchAction)
        action = GoogleSearchAction(
            name=action_config['name'],
            api_key=CustomActionRequestParameters(**action_config['api_key']),
            search_engine_id=action_config['search_engine_id'],
            failure_response=action_config.get('failure_response'),
            num_results=action_config.get('num_results'),
            bot=bot,
            user=user,
        ).save().to_mongo().to_dict()["_id"].__str__()
        self.add_action(
            action_config['name'], bot, user, action_type=ActionType.google_search_action.value,
            raise_exception=False
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
        if not Utility.is_exist(GoogleSearchAction, raise_error=False, name=action_config.get('name'), bot=bot, status=True):
            raise AppException(f'Google search action with name "{action_config.get("name")}" not found')
        action = GoogleSearchAction.objects(name=action_config.get('name'), bot=bot, status=True).get()
        action.api_key = CustomActionRequestParameters(**action_config['api_key'])
        action.search_engine_id = action_config['search_engine_id']
        action.failure_response = action_config.get('failure_response')
        action.num_results = action_config.get('num_results')
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
                action['_id'] = action['_id'].__str__()
            else:
                action.pop('_id')
            action.pop('user')
            action.pop('bot')
            action.pop('timestamp')
            action.pop('status')
            yield action

    def add_slot(self, slot_value: Dict, bot, user, raise_exception_if_exists=True):
        """
        Adds slot if it doesn't exist, updates slot if it exists
        :param slot_value: slot data dict
        :param bot: bot id
        :param user: user id
        :param raise_exception_if_exists: set True to add new slot, False to update slot
        :return: slot id
        """

        if Utility.check_empty_string(slot_value.get('name')):
            raise AppException("Slot Name cannot be empty or blank spaces")

        if slot_value.get('type') not in [item for item in SLOT_TYPE]:
            raise AppException("Invalid slot type.")

        try:
            slot = Slots.objects(name__iexact=slot_value.get('name'), bot=bot, status=True).get()
            if raise_exception_if_exists:
                raise AppException("Slot already exists!")
        except DoesNotExist:
            slot = Slots()
            slot.name = slot_value.get('name')

        slot.type = slot_value.get('type')
        slot.initial_value = slot_value.get('initial_value')
        slot.influence_conversation = slot_value.get('influence_conversation')
        slot.auto_fill = slot_value.get('auto_fill')

        if slot_value.get('type') == CategoricalSlot.type_name:
            slot.values = slot_value.get('values')
        elif slot_value.get('type') == FloatSlot.type_name:
            slot.max_value = slot_value.get('max_value')
            slot.min_value = slot_value.get('min_value')

        slot.user = user
        slot.bot = bot
        slot_id = slot.save().to_mongo().to_dict()['_id'].__str__()
        self.add_entity(slot_value.get('name'), bot, user, False)
        return slot_id

    def delete_slot(
            self, slot_name: Text, bot: Text, user: Text
    ):
        """
        deletes slots
        :param slot_name: slot name
        :param bot: bot id
        :param user: user id
        :return: AppException
        """

        try:
            if slot_name in {BOT_ID_SLOT, BOT_ID_SLOT.lower(), KAIRON_ACTION_RESPONSE_SLOT, KAIRON_ACTION_RESPONSE_SLOT.lower()}:
                raise AppException('Default kAIron slot deletion not allowed')
            slot = Slots.objects(name__iexact=slot_name, bot=bot, status=True).get()
            forms_with_slot = Forms.objects(bot=bot, status=True, required_slots__contains=slot_name)
            if len(forms_with_slot) > 0:
                raise AppException(f'Slot is attached to form: {[form["name"] for form in forms_with_slot]}')
            slot.status = False
            slot.user = user
            slot.save()
            self.delete_entity(slot_name, bot, user, False)
        except DoesNotExist as custEx:
            logging.exception(custEx)
            raise AppException(
                "Slot does not exist."
            )

    @staticmethod
    def get_row_count(document: Document, bot: str, **kwargs):
        """
        Gets the count of rows in a document for a particular bot.
        :param document: Mongoengine document for which count is to be given
        :param bot: bot id
        :return: Count of rows
        """
        kwargs.update({"bot": bot})
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
        for log in ActionServerLogs.objects(bot=bot).order_by("-timestamp").skip(start_idx).limit(page_size):
            log = log.to_mongo().to_dict()
            log.pop("bot")
            log.pop("_id")
            yield log

    def __extract_rules(self, story_steps, bot: Text, user: Text):
        saved_rules = self.fetch_rule_block_names(bot)

        for story_step in story_steps:
            if isinstance(story_step, RuleStep) and story_step.block_name.strip().lower() not in saved_rules:
                rule = self.__extract_rule_events(story_step, bot, user)
                yield rule

    def __extract_rule_events(self, rule_step, bot: Text, user: Text):
        rule_events = list(self.__extract_story_events(rule_step.events))
        template_type = DataUtility.get_template_type(rule_events)
        rule = Rules(
            block_name=rule_step.block_name,
            condition_events_indices=list(rule_step.condition_events_indices),
            start_checkpoints=[
                start_checkpoint.name
                for start_checkpoint in rule_step.start_checkpoints
            ],
            end_checkpoints=[
                end_checkpoint.name
                for end_checkpoint in rule_step.end_checkpoints
            ],
            events=rule_events,
            template_type=template_type,
            bot=bot,
            user=user
        )
        rule.clean()
        return rule

    @staticmethod
    def fetch_rule_block_names(bot: Text):
        saved_stories = list(
            Rules.objects(bot=bot, status=True).values_list('block_name')
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
        Utility.hard_delete_document([Rules], bot=bot)

    def delete_bot_actions(self, bot: Text, user: Text):
        """
        Deletes all type of actions created in bot.

        :param bot: bot id
        :param user: user id
        :return: None
        """
        Utility.hard_delete_document([
            HttpActionConfig, SlotSetAction, FormValidationAction, EmailActionConfig, GoogleSearchAction, JiraAction,
            ZendeskAction, PipedriveLeadsAction, HubspotFormsAction, KaironTwoStageFallbackAction
        ], bot=bot)
        Utility.hard_delete_document([Actions], bot=bot, type__ne=None)

    def __get_rules(self, bot: Text):
        for rule in Rules.objects(bot=bot, status=True):
            rule_events = list(
                self.__prepare_training_story_events(
                    rule.events, datetime.now().timestamp()
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

    def get_rules_for_training(self, bot: Text):
        return StoryGraph(list(self.__get_rules(bot)))

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
            ActionType.email_action.value: EmailActionConfig, ActionType.zendesk_action.value: ZendeskAction,
            ActionType.jira_action.value: JiraAction, ActionType.form_validation_action.value: FormValidationAction,
            ActionType.slot_set_action.value: SlotSetAction, ActionType.google_search_action.value: GoogleSearchAction,
            ActionType.pipedrive_leads_action.value: PipedriveLeadsAction
        }
        saved_actions = set(Actions.objects(bot=bot, status=True, type__ne=None).values_list('name'))
        for action_type, actions_list in actions.items():
            for action in actions_list:
                action_name = action.get('name') or action.get('action_name')
                action_name = action_name.lower()
                if document_types.get(action_type) and action_name not in saved_actions:
                    action['bot'] = bot
                    action['user'] = user
                    document_types[action_type](**action).save()
                    self.add_action(action_name, bot, user, action_type=action_type, raise_exception=False)

    def load_action_configurations(self, bot: Text):
        """
        loads configurations of all types of actions from the database
        :param bot: bot id
        :return: dict of action configuations of all types.
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
                "action_name": action["action_name"], "response": action["response"], "http_url": action["http_url"],
                "request_method": action["request_method"], "content_type": action["content_type"]
            }
            for header in action.get('headers') or []:
                parameter_type = header.get("parameter_type")
                value = header['value']
                if parameter_type == ActionParameterType.value.value and not Utility.check_empty_string(value) and header.get('encrypt') is True:
                    header['value'] = Utility.decrypt_message(header['value'])

            for param in action.get('params_list') or []:
                parameter_type = param.get("parameter_type")
                value = param['value']
                if parameter_type == ActionParameterType.value.value and not Utility.check_empty_string(value) and param.get('encrypt') is True:
                    param['value'] = Utility.decrypt_message(param['value'])

            if action.get('headers'):
                config['headers'] = action['headers']
            if action.get('params_list'):
                config['params_list'] = action['params_list']
            if action.get('set_slots'):
                config['set_slots'] = action['set_slots']
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
        return {ActionType.google_search_action.value: list(self.list_google_search_actions(bot, False))}

    def load_zendesk_action(self, bot: Text):
        """
        Loads Zendesk actions from the database
        :param bot: bot id
        :return: dict
        """
        return {ActionType.zendesk_action.value: list(self.list_zendesk_actions(bot, False))}

    def load_slot_set_action(self, bot: Text):
        """
        Loads Slot set actions from the database
        :param bot: bot id
        :return: dict
        """
        return {ActionType.slot_set_action.value: list(self.list_slot_set_actions(bot, False))}

    def load_pipedrive_leads_action(self, bot: Text):
        """
        Loads Pipedrive leads actions from the database
        :param bot: bot id
        :return: dict
        """
        return {ActionType.pipedrive_leads_action.value: list(self.list_pipedrive_actions(bot, False))}

    def load_form_validation_action(self, bot: Text):
        """
        Loads Form validation actions from the database
        :param bot: bot id
        :return: dict
        """
        return {ActionType.form_validation_action.value: list(self.list_form_validation_actions(bot))}

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
        files_received, is_event_data, non_event_validation_summary = await self.validate_and_prepare_data(bot,
                                                                                                           user,
                                                                                                           training_files,
                                                                                                           overwrite)
        DataImporterLogProcessor.add_log(bot, user, is_data_uploaded=True, files_received=list(files_received))
        if not is_event_data:
            status = 'Failure'
            summary = non_event_validation_summary['summary']
            component_count = non_event_validation_summary['component_count']
            if not non_event_validation_summary['validation_failed']:
                status = 'Success'
            DataImporterLogProcessor.update_summary(bot, user, component_count, summary, status=status,
                                                    event_status=EVENT_STATUS.COMPLETED.value)

        return is_event_data

    async def validate_and_prepare_data(self, bot: Text, user: Text, training_files: List, overwrite: bool):
        """
        Saves training data (zip, file or files) and validates whether at least one
        training file exists in the received set of files. If some training files are
        missing then, it prepares the rest of the data from database.
        In case only http actions are received, then it is validated and saved.
        Finally, a list of files received are returned.
        """
        non_event_validation_summary = None
        bot_data_home_dir = await DataUtility.save_uploaded_data(bot, training_files)
        files_to_prepare = DataUtility.validate_and_get_requirements(bot_data_home_dir, True)
        files_received = REQUIREMENTS - files_to_prepare
        is_event_data = False

        if files_received.difference({'config', 'actions'}):
            is_event_data = True
        else:
            non_event_validation_summary = self.save_data_without_event(bot_data_home_dir, bot, user, overwrite)
        return files_received, is_event_data, non_event_validation_summary

    def save_data_without_event(self, data_home_dir: Text, bot: Text, user: Text, overwrite: bool):
        """
        Saves http actions and config file.
        """
        from kairon.importer.validator.file_validator import TrainingDataValidator

        actions = None
        config = None
        validation_failed = False
        error_summary = {}
        component_count = COMPONENT_COUNT.copy()
        actions_path = os.path.join(data_home_dir, 'actions.yml')
        config_path = os.path.join(data_home_dir, 'config.yml')
        if os.path.exists(actions_path):
            actions = Utility.read_yaml(actions_path)
            validation_failed, error_summary, actions_count = TrainingDataValidator.validate_custom_actions(actions)
            component_count.update(actions_count)
        if os.path.exists(config_path):
            config = Utility.read_yaml(config_path)
            errors = TrainingDataValidator.validate_rasa_config(config)
            error_summary['config'] = errors

        if not validation_failed and not error_summary.get('config'):
            files_to_save = set()
            if actions and set(actions.keys()).intersection({a_type.value for a_type in ActionType}):
                files_to_save.add('actions')
            if config:
                files_to_save.add('config')
            self.save_training_data(bot, user, actions=actions, config=config, overwrite=overwrite, what=files_to_save)
        else:
            validation_failed = True
        return {'summary': error_summary, 'component_count': component_count, 'validation_failed': validation_failed}

    def prepare_training_data_for_validation(self, bot: Text, bot_data_home_dir: str = None,
                                             which: set = REQUIREMENTS.copy()):
        """
        Writes training data into files and makes them available for validation.
        @param bot: bot id.
        @param bot_data_home_dir: location where data needs to be written
        @param which: which training data is to be written
        @return:
        """
        if not bot_data_home_dir:
            bot_data_home_dir = os.path.join('training_data', bot, str(uuid.uuid4()))
        data_path = os.path.join(bot_data_home_dir, DEFAULT_DATA_PATH)
        Utility.make_dirs(data_path)

        if 'nlu' in which:
            nlu_path = os.path.join(data_path, "nlu.yml")
            nlu = self.load_nlu(bot)
            nlu_as_str = nlu.nlu_as_yaml().encode()
            Utility.write_to_file(nlu_path, nlu_as_str)

        if 'domain' in which:
            domain_path = os.path.join(bot_data_home_dir, DEFAULT_DOMAIN_PATH)
            domain = self.load_domain(bot)
            if isinstance(domain, Domain):
                domain_as_str = domain.as_yaml().encode()
                Utility.write_to_file(domain_path, domain_as_str)
            elif isinstance(domain, Dict):
                yaml.safe_dump(domain, open(domain_path, "w"))

        if 'stories' in which:
            stories_path = os.path.join(data_path, "stories.yml")
            stories = self.load_stories(bot)
            YAMLStoryWriter().dump(stories_path, stories.story_steps)

        if 'config' in which:
            config_path = os.path.join(bot_data_home_dir, DEFAULT_CONFIG_PATH)
            config = self.load_config(bot)
            config_as_str = yaml.dump(config).encode()
            Utility.write_to_file(config_path, config_as_str)

        if 'rules' in which:
            rules_path = os.path.join(data_path, "rules.yml")
            rules = self.get_rules_for_training(bot)
            YAMLStoryWriter().dump(rules_path, rules.story_steps)

    def add_default_fallback_config(self, config_obj: dict, bot: Text, user: Text):
        idx = next((idx for idx, comp in enumerate(config_obj["policies"]) if comp['name'] == 'FallbackPolicy'), None)
        if idx:
            del config_obj["policies"][idx]
        rule_policy = next((comp for comp in config_obj["policies"] if comp['name'] == 'RulePolicy'), {})
        if not rule_policy:
            rule_policy['name'] = 'RulePolicy'
            config_obj["policies"].append(rule_policy)
        if not rule_policy.get('core_fallback_action_name'):
            rule_policy['core_fallback_action_name'] = 'action_default_fallback'
        if not rule_policy.get('core_fallback_threshold'):
            rule_policy['core_fallback_threshold'] = 0.3
            self.add_default_fallback_data(bot, user, False, True)

        property_idx = next(
            (idx for idx, comp in enumerate(config_obj['pipeline']) if comp["name"] == "FallbackClassifier"), None)
        if not property_idx:
            property_idx = next(
                (idx for idx, comp in enumerate(config_obj['pipeline']) if comp["name"] == "DIETClassifier"))
            fallback = {'name': 'FallbackClassifier', 'threshold': 0.7}
            config_obj['pipeline'].insert(property_idx + 1, fallback)
            self.add_default_fallback_data(bot, user, True, False)

    @staticmethod
    def fetch_nlu_fallback_action(bot: Text):
        action = None
        event = StoryEvents(name='nlu_fallback', type="user")
        try:
            rule = Rules.objects(bot=bot, status=True, events__match=event).get()
            for event in rule.events:
                if 'action' == event.type and event.name != RULE_SNIPPET_ACTION_NAME:
                    action = event.name
                    break
        except DoesNotExist as e:
            logging.error(e)
        return action

    def add_default_fallback_data(self, bot: Text, user: Text, nlu_fallback: bool = True, action_fallback: bool = True):
        if nlu_fallback:
            if not Utility.is_exist(Responses, raise_error=False, bot=bot, status=True,
                                    name__iexact='utter_please_rephrase'):
                self.add_text_response(DEFAULT_NLU_FALLBACK_RESPONSE, 'utter_please_rephrase', bot, user)
            steps = [
                {"name": "...", "type": "BOT"},
                {"name": "nlu_fallback", "type": "INTENT"},
                {"name": "utter_please_rephrase", "type": "BOT"}
            ]
            rule = {'name': DEFAULT_NLU_FALLBACK_RULE, 'steps': steps, 'type': 'RULE'}
            try:
                self.add_complex_story(rule, bot, user)
            except AppException as e:
                logging.error(str(e))

        if action_fallback:
            if not Utility.is_exist(Responses, raise_error=False, bot=bot, status=True, name__iexact=DEFAULT_NLU_FALLBACK_UTTERANCE_NAME):
                self.add_text_response(DEFAULT_ACTION_FALLBACK_RESPONSE, DEFAULT_NLU_FALLBACK_UTTERANCE_NAME, bot, user)

    def add_synonym(self, synonyms_dict: Dict, bot, user):
        if Utility.check_empty_string(synonyms_dict.get('name')):
            raise AppException("Synonym name cannot be an empty string")
        if not synonyms_dict.get('value'):
            raise AppException("Synonym value cannot be an empty string")
        empty_element = any([Utility.check_empty_string(elem) for elem in synonyms_dict.get('value')])
        if empty_element:
            raise AppException("Synonym value cannot be an empty string")
        synonym = list(EntitySynonyms.objects(name__iexact=synonyms_dict['name'], bot=bot, status=True))
        value_list = set(item.value for item in synonym)
        check = any(item in value_list for item in synonyms_dict.get('value'))
        if check:
            raise AppException("Synonym value already exists")
        for val in synonyms_dict.get('value'):
            entity_synonym = EntitySynonyms()
            entity_synonym.name = synonyms_dict['name']
            entity_synonym.value = val
            entity_synonym.user = user
            entity_synonym.bot = bot
            entity_synonym.save().to_mongo().to_dict()['_id'].__str__()

    def edit_synonym(
            self, synonym_id: Text, value: Text, name: Text, bot: Text, user: Text
    ):
        """
        update the synonym value
        :param id: value id against which the synonym is updated
        :param value: synonym value
        :param name: synonym name
        :param bot: bot id
        :param user: user id
        :return: None
        :raises: AppException
        """
        synonym = list(EntitySynonyms.objects(name__iexact=name, bot=bot, status=True))
        value_list = set(item.value for item in synonym)
        if value in value_list:
            raise AppException("Synonym value already exists")
        try:
            val = EntitySynonyms.objects(bot=bot, name__iexact=name).get(id=synonym_id)
            val.value = value
            val.user = user
            val.timestamp = datetime.utcnow()
            val.save()
        except DoesNotExist:
            raise AppException("Synonym value does not exist!")

    def delete_synonym(self, synonym_name: str, bot: str, user: str):
        if not (synonym_name and synonym_name.strip()):
            raise AppException("Synonym cannot be empty or spaces")
        values = list(EntitySynonyms.objects(name__iexact=synonym_name, bot=bot, user=user, status=True))
        if not values:
            raise AppException("Synonym does not exist")
        for value in values:
            value.status = False
            value.timestamp = datetime.utcnow()
            value.save()

    def delete_synonym_value(self, synonym_id: str, bot: str, user: str):
        if not (synonym_id and synonym_id.strip()):
            raise AppException("Synonym Id cannot be empty or spaces")
        try:
            EntitySynonyms.objects(bot=bot, status=True).get(id=synonym_id)
            self.remove_document(EntitySynonyms, synonym_id, bot, user)
        except DoesNotExist as e:
            raise AppException(e)

    def get_synonym_values(self, name: Text, bot: Text):
        """
        fetch all the synonym values
        :param name: synonym name
        :param bot: bot id
        :return: yields the values
        """
        values = EntitySynonyms.objects(bot=bot, status=True, name__iexact=name).order_by(
            "-timestamp"
        )
        for value in values:
            yield {"_id": value.id.__str__(), "value": value.value}

    def add_utterance_name(self, name: Text, bot: Text, user: Text, form_attached: str = None,
                           raise_error_if_exists: bool = False):
        if Utility.check_empty_string(name):
            raise AppException('Name cannot be empty')
        try:
            Utterances.objects(bot=bot, status=True, name__iexact=name).get()
            if raise_error_if_exists:
                raise AppException('Utterance exists')
        except DoesNotExist as e:
            logging.exception(e)
            Utterances(name=name, form_attached=form_attached, bot=bot, user=user).save()

    def get_utterances(self, bot: Text):
        utterances = Utterances.objects(bot=bot, status=True)
        for utterance in utterances:
            utterance = utterance.to_mongo().to_dict()
            utterance['_id'] = utterance['_id'].__str__()
            utterance.pop('status')
            utterance.pop('timestamp')
            utterance.pop('bot')
            utterance.pop('user')
            yield utterance

    def delete_utterance_name(self, name: Text, bot: Text, validate_has_form: bool = False, raise_exc: bool = False):
        try:
            utterance = Utterances.objects(name__iexact=name, bot=bot, status=True).get()
            if validate_has_form and not Utility.check_empty_string(utterance.form_attached):
                if raise_exc:
                    raise AppException(f'At least one question is required for utterance linked to form: {utterance.form_attached}')
            else:
                utterance.status = False
                utterance.save()
        except DoesNotExist as e:
            logging.exception(e)
            if raise_exc:
                raise AppException('Utterance not found')

    def get_training_data_count(self, bot: Text):
        intents_count = list(Intents.objects(bot=bot, status=True, name__nin=DEFAULT_INTENTS).aggregate(
            [{'$lookup': {'from': 'training_examples',
                          'let': {'bot_id': bot, 'name': '$name'},
                          'pipeline': [{'$match': {'bot': bot, 'status': True}},
                                       {'$match': {'$expr': {'$and': [{'$eq': ['$intent', '$$name']}]}}},
                                       {'$count': 'count'}], 'as': 'intents_count'}},
             {'$project': {'_id': 0, 'name': 1, 'count': {'$first': '$intents_count.count'}}}]))

        utterances_count = list(Utterances.objects(bot=bot, status=True).aggregate(
            [{'$lookup': {'from': 'responses',
                          'let': {'bot_id': bot, 'utterance': '$name'},
                          'pipeline': [{'$match': {'bot': bot, 'status': True}},
                                       {'$match': {'$expr': {'$and': [{'$eq': ['$name', '$$utterance']}]}}},
                                       {'$count': 'count'}], 'as': 'responses_count'}},
             {'$project': {'_id': 0, 'name': 1, 'count': {'$first': '$responses_count.count'}}}]))

        return {'intents': intents_count, 'utterances': utterances_count}

    @staticmethod
    def get_bot_settings(bot: Text, user: Text):
        try:
            settings = BotSettings.objects(bot=bot, status=True).get()
        except DoesNotExist as e:
            logging.error(e)
            settings = BotSettings(bot=bot, user=user).save()
        return settings

    def add_rule_for_kairon_faq_action(self, bot: Text, user: Text):
        search_event = StoryEvents(name='nlu_fallback', type="user")
        events = [
            StoryEvents(name=RULE_SNIPPET_ACTION_NAME, type=ActionExecuted.type_name),
            StoryEvents(name="nlu_fallback", type=UserUttered.type_name),
            StoryEvents(name=GPT_LLM_FAQ, type=ActionExecuted.type_name)
        ]
        try:
            rule = Rules.objects(bot=bot, status=True, events__match=search_event).first()
            if not rule:
                raise DoesNotExist('Rule with nlu_fallback event not found')
            rule.events = events
            rule.save()
        except DoesNotExist as e:
            logging.exception(e)
            Rules(block_name=DEFAULT_LLM_FALLBACK_RULE, bot=bot, user=user, start_checkpoints=[STORY_START], events=events).save()

    def save_chat_client_config(self, config: dict, bot: Text, user: Text):
        from kairon.shared.account.processor import AccountProcessor

        client_config = self.get_chat_client_config(bot, user)
        white_listed_domain = ["*"] if not config.__contains__("whitelist") else config.pop("whitelist")
        if client_config.config.get('headers'):
            client_config.config['headers'].pop('authorization', None)

        if config.get('multilingual') and config['multilingual'].get('bots'):
            accessible_bots = AccountProcessor.get_accessible_multilingual_bots(bot, user)
            enabled_bots = list(filter(lambda bot_info: bot_info.get("is_enabled"), config['multilingual']['bots']))
            enabled_bots = set(map(lambda bot_info: bot_info["id"], enabled_bots))
            if not enabled_bots:
                raise AppException("At least one bot should be enabled!")
            for bot_info in accessible_bots:
                bot_info["is_enabled"] = True if bot_info["id"] in enabled_bots else False
            client_config.config['multilingual']['bots'] = accessible_bots

        client_config.config = config
        client_config.user = user
        client_config.white_listed_domain = white_listed_domain
        client_config.save()

    def get_chat_client_config_url(self, bot: Text, user: Text):
        from kairon.shared.auth import Authentication

        access_token, _ = Authentication.generate_integration_token(
            bot, user, ACCESS_ROLES.TESTER.value,
            access_limit=['/api/bot/.+/chat/client/config$'], token_type=TOKEN_TYPE.DYNAMIC.value
        )
        url = urljoin(Utility.environment['app']['server_url'], f'/api/bot/{bot}/chat/client/config/')
        url = urljoin(url, access_token)
        return url

    def get_client_config_using_uid(self, bot: str, uid: str):
        decoded_uid = Utility.validate_bot_specific_token(bot, uid)
        config = self.get_chat_client_config(bot, decoded_uid["sub"], is_client_live=True)
        return config.to_mongo().to_dict()

    def get_chat_client_config(self, bot: Text, user: Text, is_client_live: bool = False):
        from kairon.shared.auth import Authentication
        from kairon.shared.account.processor import AccountProcessor

        AccountProcessor.get_bot_and_validate_status(bot)
        bot_settings = self.get_bot_settings(bot, user)
        try:
            client_config = ChatClientConfig.objects(bot=bot, status=True).get()
            client_config.config['whitelist'] = client_config.white_listed_domain
        except DoesNotExist as e:
            logging.error(e)
            config = Utility.load_json_file("./template/chat-client/default-config.json")
            client_config = ChatClientConfig(config=config, bot=bot, user=user)
        if not client_config.config.get('headers'):
            client_config.config['headers'] = {}
        if not client_config.config['headers'].get('X-USER'):
            client_config.config['headers']['X-USER'] = user
        client_config.config['api_server_host_url'] = Utility.environment['app']['server_url']
        token, refresh_token = Authentication.generate_integration_token(
            bot, user, expiry=bot_settings.chat_token_expiry,
            access_limit=[
                '/api/bot/.+/chat', '/api/bot/.+/agent/live/.+', '/api/bot/.+/conversation',
                '/api/bot/.+/metric/user/logs/user_metrics'
            ],
            token_type=TOKEN_TYPE.DYNAMIC.value
        )
        iat = datetime.now(tz=timezone.utc).replace(microsecond=0).replace(second=0)
        access_token_expiry = iat + timedelta(minutes=bot_settings.chat_token_expiry)
        access_token_expiry = access_token_expiry.timestamp()
        refresh_token_expiry = iat + timedelta(minutes=bot_settings.refresh_token_expiry)
        refresh_token_expiry = refresh_token_expiry.timestamp()
        client_config.config['headers']['authorization'] = {}
        client_config.config['headers']['authorization']['access_token'] = token
        client_config.config['headers']['authorization']['token_type'] = 'Bearer'
        client_config.config['headers']['authorization']['refresh_token'] = f'{refresh_token}'
        client_config.config['headers']['authorization']['access_token_ttl'] = bot_settings.chat_token_expiry
        client_config.config['headers']['authorization']['refresh_token_ttl'] = bot_settings.refresh_token_expiry
        client_config.config['headers']['authorization']['access_token_expiry'] = access_token_expiry
        client_config.config['headers']['authorization']['refresh_token_expiry'] = refresh_token_expiry
        client_config.config['chat_server_base_url'] = Utility.environment['model']['agent']['url']
        if client_config.config.get("multilingual") and client_config.config['multilingual'].get('enable'):
            accessible_bots = AccountProcessor.get_accessible_multilingual_bots(bot, user)
            enabled_bots = {}
            if client_config.config['multilingual'].get('bots'):
                enabled_bots = list(filter(lambda bot_info: bot_info.get("is_enabled"), client_config.config['multilingual']['bots']))
                enabled_bots = set(map(lambda bot_info: bot_info["id"], enabled_bots))
            if is_client_live and bot not in enabled_bots:
                raise AppException("Bot is disabled. Please use a valid bot.")
            client_config.config['multilingual']['bots'] = []
            for bot_info in accessible_bots:
                bot_info["is_enabled"] = True if bot_info["id"] in enabled_bots else False
                if bot_info["is_enabled"] or not is_client_live:
                    token, _ = Authentication.generate_integration_token(
                        bot_info["id"], user, expiry=bot_settings.chat_token_expiry,
                        access_limit=[
                            '/api/bot/.+/chat', '/api/bot/.+/agent/live/.+', '/api/bot/.+/conversation',
                            '/api/bot/.+/metric/user/logs/{log_type}'
                        ],
                        token_type=TOKEN_TYPE.DYNAMIC.value
                    )
                    bot_info['authorization'] = f'Bearer {token}'
                    client_config.config['multilingual']['bots'].append(bot_info)

        return client_config

    def add_regex(self, regex_dict: Dict, bot, user):
        if Utility.check_empty_string(regex_dict.get('name')) or Utility.check_empty_string(regex_dict.get('pattern')):
            raise AppException("Regex name and pattern cannot be empty or blank spaces")
        try:
            RegexFeatures.objects(name__iexact=regex_dict.get('name'), bot=bot, status=True).get()
            raise AppException("Regex name already exists!")
        except DoesNotExist:
            regex = RegexFeatures()
            regex.name = regex_dict.get('name')
            regex.pattern = regex_dict.get('pattern')
            regex.bot = bot
            regex.user = user
            regex_id = regex.save().to_mongo().to_dict()['_id'].__str__()
            return regex_id

    def edit_regex(self, regex_dict: Dict, bot, user):
        if Utility.check_empty_string(regex_dict.get('name')) or Utility.check_empty_string(regex_dict.get('pattern')):
            raise AppException("Regex name and pattern cannot be empty or blank spaces")
        try:
            regex = RegexFeatures.objects(name__iexact=regex_dict.get('name'), bot=bot, status=True).get()
            regex.pattern = regex_dict.get("pattern")
            regex.user = user
            regex.timestamp = datetime.utcnow()
            regex.save()
        except DoesNotExist:
            raise AppException("Regex name does not exist!")

    def delete_regex(
            self, regex_name: Text, bot: Text, user: Text
    ):
        """
        deletes regex pattern
        :param regex_name: regex name
        :param user: user id
        :param bot: bot id
        :return: AppException
        """

        try:
            regex = RegexFeatures.objects(name__iexact=regex_name, bot=bot, status=True).get()
            regex.status = False
            regex.user = user
            regex.timestamp = datetime.utcnow()
            regex.save()
        except DoesNotExist:
            raise AppException("Regex name does not exist.")

    def add_lookup(self, lookup_dict: Dict, bot, user):
        if Utility.check_empty_string(lookup_dict.get('name')):
            raise AppException("Lookup table name cannot be an empty string")
        if not lookup_dict.get('value'):
            raise AppException("Lookup Table value cannot be an empty string")
        empty_element = any([Utility.check_empty_string(elem) for elem in lookup_dict.get('value')])
        if empty_element:
            raise AppException("Lookup table value cannot be an empty string")
        lookup = list(LookupTables.objects(name__iexact=lookup_dict['name'], bot=bot, status=True))
        value_list = set(item.value for item in lookup)
        check = any(item in value_list for item in lookup_dict.get('value'))
        if check:
            raise AppException("Lookup table value already exists")
        for val in lookup_dict.get('value'):
            lookup_table = LookupTables()
            lookup_table.name = lookup_dict['name']
            lookup_table.value = val
            lookup_table.user = user
            lookup_table.bot = bot
            lookup_table.save().to_mongo().to_dict()['_id'].__str__()

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
            yield {"_id": value.id.__str__(), "value": value.value}

    def edit_lookup(
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
        lookup = list(LookupTables.objects(name__iexact=name, bot=bot, status=True))
        value_list = set(item.value for item in lookup)
        if value in value_list:
            raise AppException("Lookup table value already exists")
        try:
            val = LookupTables.objects(bot=bot, name__iexact=name).get(id=lookup_id)
            val.value = value
            val.user = user
            val.timestamp = datetime.utcnow()
            val.save()
        except DoesNotExist:
            raise AppException("Lookup table value does not exist!")

    def delete_lookup(self, lookup_name: str, bot: str, user: str):
        if not (lookup_name and lookup_name.strip()):
            raise AppException("Lookup table name cannot be empty or spaces")
        values = list(LookupTables.objects(name__iexact=lookup_name, bot=bot, user=user, status=True))
        if not values:
            raise AppException("Lookup table does not exist")
        for value in values:
            value.status = False
            value.timestamp = datetime.utcnow()
            value.save()

    def delete_lookup_value(self, lookup_id: str, bot: str, user: str):
        if not (lookup_id and lookup_id.strip()):
            raise AppException("Lookup Id cannot be empty or spaces")
        try:
            LookupTables.objects(bot=bot, status=True).get(id=lookup_id)
            self.remove_document(LookupTables, lookup_id, bot, user)
        except DoesNotExist as e:
            raise AppException(e)

    def __add_or_update_form_validations(self, name: Text, path: list, bot: Text, user: Text):
        existing_slot_validations = FormValidationAction.objects(name=name, bot=bot, status=True)
        existing_validations = {validation.slot for validation in list(existing_slot_validations)}
        slots_required_for_form = {slots_to_fill['slot'] for slots_to_fill in path}

        for slots_to_fill in path:
            slot = slots_to_fill.get('slot')
            validation_semantic = Utility.prepare_form_validation_semantic(slots_to_fill.get('validation'))
            if slot in existing_validations:
                validation = existing_slot_validations.get(slot=slot)
                validation.validation_semantic = validation_semantic
                validation.valid_response = slots_to_fill.get('valid_response')
                validation.invalid_response = slots_to_fill.get('invalid_response')
                validation.user = user
                validation.timestamp = datetime.utcnow()
                validation.save()
            else:
                FormValidationAction(name=name, slot=slot,
                                     validation_semantic=validation_semantic,
                                     bot=bot, user=user,
                                     valid_response=slots_to_fill.get('valid_response'),
                                     invalid_response=slots_to_fill.get('invalid_response')).save()

        slot_validations_to_delete = existing_validations.difference(slots_required_for_form)
        for slot in slot_validations_to_delete:
            validation = existing_slot_validations.get(slot=slot)
            validation.user = user
            validation.timestamp = datetime.utcnow()
            validation.status = False
            validation.save()

    def __add_form_responses(self, responses: list, utterance_name: Text, form: Text, bot: Text, user: Text):
        for resp in responses:
            self.add_response(utterances={"text": resp.strip()}, name=utterance_name, form_attached=form, bot=bot,
                              user=user)

    def __validate_slots_attached_to_form(self, required_slots: set, bot: Text):
        existing_slots = set(Slots.objects(bot=bot, status=True, name__in=required_slots).values_list('name'))
        existing_slot_mappings = SlotMapping.objects(bot=bot, status=True, slot__in=required_slots).values_list('slot')
        if required_slots.difference(existing_slots).__len__() > 0:
            raise AppException(f'slots not exists: {required_slots.difference(existing_slots)}')
        if required_slots.difference(existing_slot_mappings).__len__() > 0:
            raise AppException(f'Mapping is required for slot: {required_slots.difference(existing_slot_mappings)}')

    def add_form(self, name: str, path: list, bot: Text, user: Text):
        if Utility.check_empty_string(name):
            raise AppException('Form name cannot be empty or spaces')
        Utility.is_exist(Forms, f'Form with name "{name}" exists', name__iexact=name, bot=bot, status=True)
        Utility.is_valid_action_name(name, bot, Forms)
        required_slots = [slots_to_fill['slot'] for slots_to_fill in path if
                          not Utility.check_empty_string(slots_to_fill['slot'])]
        self.__validate_slots_attached_to_form(set(required_slots), bot)
        for slots_to_fill in path:
            self.__add_form_responses(slots_to_fill['ask_questions'],
                                      utterance_name=f'utter_ask_{name}_{slots_to_fill["slot"]}',
                                      form=name, bot=bot, user=user)
        form_id = Forms(name=name, required_slots=required_slots, bot=bot, user=user).save().to_mongo().to_dict()["_id"].__str__()
        self.__add_or_update_form_validations(f'validate_{name}', path, bot, user)
        self.add_action(f'validate_{name}', bot, user, action_type=ActionType.form_validation_action.value)
        return form_id

    @staticmethod
    def list_forms(bot: Text):
        for form in Forms.objects(bot=bot, status=True):
            form = form.to_mongo().to_dict()
            form['_id'] = form['_id'].__str__()
            form.pop('bot')
            form.pop('user')
            form.pop('status')
            yield form

    def get_form(self, form_id: Text, bot: Text):
        try:
            form = Forms.objects(id=form_id, bot=bot, status=True).get().to_mongo().to_dict()
            name = form['name']
            form['_id'] = form['_id'].__str__()
            form_validations = FormValidationAction.objects(name=f'validate_{name}', bot=bot, status=True)
            slots_with_validations = {validation.slot for validation in form_validations}
            slot_mapping = []
            for slot in form.get('required_slots') or []:
                utterance = list(self.get_response(name=f'utter_ask_{name}_{slot}', bot=bot))
                mapping = {'slot': slot, 'ask_questions': utterance, 'validation': None,
                           'valid_response': None, 'invalid_response': None}
                if slot in slots_with_validations:
                    validations = form_validations.get(slot=slot).to_mongo().to_dict()
                    mapping['validation'] = validations.get('validation_semantic')
                    mapping['valid_response'] = validations.get('valid_response')
                    mapping['invalid_response'] = validations.get('invalid_response')
                slot_mapping.append(mapping)
            form['settings'] = slot_mapping
            return form
        except DoesNotExist as e:
            logging.error(str(e))
            raise AppException('Form does not exists')

    def edit_form(self, name: str, path: list, bot: Text, user: Text):
        try:
            form = Forms.objects(name=name, bot=bot, status=True).get()
            slots_required_for_form = [slots_to_fill['slot'] for slots_to_fill in path]
            self.__validate_slots_attached_to_form(set(slots_required_for_form), bot)
            existing_slots_for_form = set(form.to_mongo().to_dict()['required_slots'])
            slots_to_remove = existing_slots_for_form.difference(set(slots_required_for_form))
            new_slots_to_add = set(slots_required_for_form).difference(existing_slots_for_form)

            for slot in slots_to_remove:
                try:
                    self.delete_utterance(f'utter_ask_{name}_{slot}', bot, False)
                except AppException:
                    pass

            for slots_to_fill in path:
                slot_name = slots_to_fill['slot']
                if slot_name in new_slots_to_add:
                    self.__add_form_responses(slots_to_fill['ask_questions'],
                                              utterance_name=f'utter_ask_{name}_{slot_name}',
                                              form=name, bot=bot, user=user)
            form.required_slots = slots_required_for_form
            form.user = user
            form.timestamp = datetime.utcnow()
            form.save()
            self.__add_or_update_form_validations(f'validate_{name}', path, bot, user)
        except DoesNotExist:
            raise AppException('Form does not exists')

    def delete_form(self, name: Text, bot: Text, user: Text):
        try:
            form = Forms.objects(name=name, bot=bot, status=True).get()
            MongoProcessor.get_attached_flows(bot, name, 'action')
            for slot in form.required_slots:
                try:
                    utterance_name = f'utter_ask_{name}_{slot}'
                    self.delete_utterance(utterance_name, bot, False)
                except Exception as e:
                    logging.error(str(e))
            form.status = False
            form.save()
            if Utility.is_exist(FormValidationAction, raise_error=False, name__iexact=f'validate_{name}', bot=bot,
                                status=True):
                self.delete_action(f'validate_{name}', bot, user)
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
            if not Utility.is_exist(Slots, raise_error=False, name=mapping['slot'], bot=bot, status=True):
                raise AppException(f'Slot with name \'{mapping["slot"]}\' not found')
            slot_mapping = SlotMapping.objects(slot=mapping['slot'], bot=bot, status=True).get()
        except DoesNotExist:
            slot_mapping = SlotMapping(slot=mapping['slot'], bot=bot)
        slot_mapping.mapping = mapping['mapping']
        slot_mapping.user = user
        slot_mapping.timestamp = datetime.utcnow()
        return slot_mapping.save().to_mongo().to_dict()['_id'].__str__()

    def get_slot_mappings(self, bot: Text):
        """
        Fetches existing slot mappings.

        :param bot: bot id
        :return: list of slot mappings
        """
        for slot_mapping in SlotMapping.objects(bot=bot, status=True):
            slot_mapping = slot_mapping.to_mongo().to_dict()
            slot_mapping.pop("bot")
            slot_mapping.pop("user")
            slot_mapping.pop("_id")
            slot_mapping.pop("timestamp")
            slot_mapping.pop("status")
            yield slot_mapping

    def delete_slot_mapping(self, name: Text, bot: Text, user: Text):
        """
        Delete slot mapping.

        :param name: Name of slot for which mapping exists.
        :param bot: bot id
        :param user: user id
        :return: document id of the mapping
        """
        try:
            slot_mapping = SlotMapping.objects(slot=name, bot=bot, status=True).get()
            forms_with_slot = Forms.objects(bot=bot, status=True, required_slots__contains=name)
            if len(forms_with_slot) > 0:
                raise AppException(f'Slot mapping is required for form: {[form["name"] for form in forms_with_slot]}')
            slot_mapping.user = user
            slot_mapping.timestamp = datetime.utcnow()
            slot_mapping.status = False
            slot_mapping.save()
        except DoesNotExist:
            raise AppException(f'No slot mapping exists for slot: {name}')

    def add_slot_set_action(self, action: dict, bot: Text, user: Text):
        set_slots = []
        if Utility.check_empty_string(action.get("name")):
            raise AppException('name cannot be empty or spaces')
        Utility.is_valid_action_name(action.get("name"), bot, SlotSetAction)
        for slot in action["set_slots"]:
            if Utility.check_empty_string(slot.get("name")):
                raise AppException('slot name cannot be empty or spaces')
            if not Utility.is_exist(Slots, raise_error=False, name=slot['name'], bot=bot, status=True):
                raise AppException(f'Slot with name "{slot["name"]}" not found')
            set_slots.append(SetSlots(**slot))
        SlotSetAction(name=action["name"], set_slots=set_slots, bot=bot, user=user).save()
        self.add_action(action["name"], bot, user, action_type=ActionType.slot_set_action.value)

    @staticmethod
    def list_slot_set_actions(bot: Text, with_doc_id: bool = True):
        if with_doc_id:
            actions = SlotSetAction.objects(bot=bot, status=True).exclude('bot', 'user', 'timestamp',
                                                                          'status').to_json()
        else:
            actions = SlotSetAction.objects(bot=bot, status=True).exclude('id', 'bot', 'user', 'timestamp',
                                                                          'status').to_json()
        return json.loads(actions)

    @staticmethod
    def edit_slot_set_action(action: dict, bot: Text, user: Text):
        set_slots = []
        try:
            for slot in action["set_slots"]:
                if Utility.check_empty_string(slot.get("name")):
                    raise AppException('slot name cannot be empty or spaces')
                if not Utility.is_exist(Slots, raise_error=False, name=slot['name'], bot=bot, status=True):
                    raise AppException(f'Slot with name "{slot["name"]}" not found')
                set_slots.append(SetSlots(**slot))
            slot_set_action = SlotSetAction.objects(name=action.get('name'), bot=bot, status=True).get()
            slot_set_action.set_slots = set_slots
            slot_set_action.user = user
            slot_set_action.timestamp = datetime.utcnow()
            slot_set_action.save()
        except DoesNotExist:
            raise AppException(f'Slot setting action with name "{action.get("name")}" not found')

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
            MongoProcessor.get_attached_flows(bot, name, 'action')
            if action.type == ActionType.slot_set_action.value:
                Utility.delete_document([SlotSetAction], name__iexact=name, bot=bot, user=user)
            elif action.type == ActionType.form_validation_action.value:
                Utility.delete_document([FormValidationAction], name__iexact=name, bot=bot, user=user)
            elif action.type == ActionType.email_action.value:
                Utility.delete_document([EmailActionConfig], action_name__iexact=name, bot=bot, user=user)
            elif action.type == ActionType.google_search_action.value:
                Utility.delete_document([GoogleSearchAction], name__iexact=name, bot=bot, user=user)
            elif action.type == ActionType.jira_action.value:
                Utility.delete_document([JiraAction], name__iexact=name, bot=bot, user=user)
            elif action.type == ActionType.http_action.value:
                Utility.delete_document([HttpActionConfig], action_name__iexact=name, bot=bot, user=user)
            elif action.type == ActionType.zendesk_action.value:
                Utility.delete_document([ZendeskAction], name__iexact=name, bot=bot, user=user)
            elif action.type == ActionType.pipedrive_leads_action.value:
                Utility.delete_document([PipedriveLeadsAction], name__iexact=name, bot=bot, user=user)
            elif action.type == ActionType.hubspot_forms_action.value:
                Utility.delete_document([HubspotFormsAction], name__iexact=name, bot=bot, user=user)
            elif action.type == ActionType.two_stage_fallback.value:
                Utility.delete_document([KaironTwoStageFallbackAction], name__iexact=name, bot=bot, user=user)
            elif action.type == ActionType.razorpay_action.value:
                Utility.delete_document([RazorpayAction], name__iexact=name, bot=bot, user=user)
            action.status = False
            action.user = user
            action.timestamp = datetime.utcnow()
            action.save()
        except DoesNotExist:
            raise AppException(f'Action with name "{name}" not found')

    def add_email_action(self, action: Dict, bot: str, user: str):
        """
        add a new Email Action
        :param action: email action configuration
        :param bot: bot id
        :param user: user id
        :return: doc id
        """
        action['bot'] = bot
        action['user'] = user
        Utility.is_valid_action_name(action.get("action_name"), bot, EmailActionConfig)
        email = EmailActionConfig(**action).save().to_mongo().to_dict()["_id"].__str__()
        self.add_action(action['action_name'], bot, user, action_type=ActionType.email_action.value,
                        raise_exception=False)
        return email

    def edit_email_action(self, action: dict, bot: Text, user: Text):
        """
        update an Email Action
        :param action: email action configuration
        :param bot: bot id
        :param user: user id
        :return: None
        """
        if not Utility.is_exist(EmailActionConfig, raise_error=False, action_name=action.get('action_name'), bot=bot, status=True):
            raise AppException(f'Action with name "{action.get("action_name")}" not found')
        email_action = EmailActionConfig.objects(action_name=action.get('action_name'), bot=bot, status=True).get()
        email_action.smtp_url = action['smtp_url']
        email_action.smtp_port = action['smtp_port']
        email_action.smtp_userid = CustomActionRequestParameters(**action['smtp_userid']) if action['smtp_userid'] else None
        email_action.smtp_password = CustomActionRequestParameters(**action['smtp_password'])
        email_action.from_email = action['from_email']
        email_action.subject = action['subject']
        email_action.to_email = action['to_email']
        email_action.response = action['response']
        email_action.tls = action['tls']
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
                action['_id'] = action['_id'].__str__()
            else:
                action.pop('_id')
            action.pop('user')
            action.pop('bot')
            action.pop('timestamp')
            action.pop('status')
            yield action

    def add_jira_action(self, action: Dict, bot: str, user: str):
        """
        Add a new Jira Action
        :param action: Jira action configuration
        :param bot: bot id
        :param user: user id
        :return: doc id
        """
        action['bot'] = bot
        action['user'] = user
        Utility.is_valid_action_name(action.get("name"), bot, JiraAction)
        jira_action = JiraAction(**action).save().to_mongo().to_dict()["_id"].__str__()
        self.add_action(
            action['name'], bot, user, action_type=ActionType.jira_action.value, raise_exception=False
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
        if not Utility.is_exist(JiraAction, raise_error=False, name=action.get('name'), bot=bot, status=True):
            raise AppException(f'Action with name "{action.get("name")}" not found')
        jira_action = JiraAction.objects(name=action.get('name'), bot=bot, status=True).get()
        jira_action.url = action['url']
        jira_action.user_name = action['user_name']
        jira_action.api_token = CustomActionRequestParameters(**action['api_token'])
        jira_action.project_key = action['project_key']
        jira_action.issue_type = action['issue_type']
        jira_action.parent_key = action['parent_key']
        jira_action.summary = action['summary']
        jira_action.response = action['response']
        jira_action.user = user
        jira_action.timestamp = datetime.utcnow()
        jira_action.save()

    def list_form_validation_actions(self, bot: Text):
        for action in FormValidationAction.objects(bot=bot, status=True):
            action = action.to_mongo().to_dict()
            action.pop('_id')
            action.pop('bot')
            action.pop('user')
            action.pop('timestamp')
            action.pop('status')
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
                action['_id'] = action['_id'].__str__()
            else:
                action.pop('_id')
            action.pop('user')
            action.pop('bot')
            action.pop('status')
            action.pop('timestamp')
            yield action

    def add_zendesk_action(self, action: Dict, bot: str, user: str):
        """
        Add a new Zendesk Action
        :param action: Zendesk action configuration
        :param bot: bot id
        :param user: user id
        :return: doc id
        """
        action['bot'] = bot
        action['user'] = user
        Utility.is_valid_action_name(action.get("name"), bot, ZendeskAction)
        zendesk_action = ZendeskAction(**action).save().to_mongo().to_dict()["_id"].__str__()
        self.add_action(
            action['name'], bot, user, action_type=ActionType.zendesk_action.value, raise_exception=False
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
        if not Utility.is_exist(ZendeskAction, raise_error=False, name=action.get('name'), bot=bot, status=True):
            raise AppException(f'Action with name "{action.get("name")}" not found')
        zendesk_action = ZendeskAction.objects(name=action.get('name'), bot=bot, status=True).get()
        zendesk_action.subdomain = action['subdomain']
        zendesk_action.user_name = action['user_name']
        zendesk_action.api_token = CustomActionRequestParameters(**action['api_token'])
        zendesk_action.subject = action['subject']
        zendesk_action.response = action['response']
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
                action['_id'] = action['_id'].__str__()
            else:
                action.pop('_id')
            action.pop('user')
            action.pop('bot')
            action.pop('status')
            action.pop('timestamp')
            yield action

    def add_pipedrive_action(self, action: Dict, bot: str, user: str):
        """
        Add a new Pipedrive Action
        :param action: Pipedrive action configuration
        :param bot: bot id
        :param user: user id
        :return: doc id
        """
        action['bot'] = bot
        action['user'] = user
        Utility.is_valid_action_name(action.get("name"), bot, PipedriveLeadsAction)
        pipedrive_action = PipedriveLeadsAction(**action).save().to_mongo().to_dict()["_id"].__str__()
        self.add_action(
            action['name'], bot, user, action_type=ActionType.pipedrive_leads_action.value, raise_exception=False
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
        if not Utility.is_exist(PipedriveLeadsAction, raise_error=False, name=action.get('name'), bot=bot, status=True):
            raise AppException(f'Action with name "{action.get("name")}" not found')
        pipedrive_action = PipedriveLeadsAction.objects(name=action.get('name'), bot=bot, status=True).get()
        pipedrive_action.domain = action['domain']
        pipedrive_action.api_token = CustomActionRequestParameters(**action['api_token'])
        pipedrive_action.title = action['title']
        pipedrive_action.response = action['response']
        pipedrive_action.metadata = action['metadata']
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
                action['_id'] = action['_id'].__str__()
            else:
                action.pop('_id')
            action.pop('user')
            action.pop('bot')
            action.pop('status')
            action.pop('timestamp')
            yield action
            
    def add_hubspot_forms_action(self, action: Dict, bot: str, user: str):
        """
        Add a new Hubspot forms Action
        :param action: Hubspot action configuration
        :param bot: bot id
        :param user: user id
        :return: doc id
        """
        action['bot'] = bot
        action['user'] = user
        Utility.is_valid_action_name(action.get("name"), bot, HubspotFormsAction)
        hubspot_action = HubspotFormsAction(**action).save().to_mongo().to_dict()["_id"].__str__()
        self.add_action(
            action['name'], bot, user, action_type=ActionType.hubspot_forms_action.value, raise_exception=False
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
        if not Utility.is_exist(HubspotFormsAction, raise_error=False, name=action.get('name'), bot=bot, status=True):
            raise AppException(f'Action with name "{action.get("name")}" not found')
        hubspot_forms_action = HubspotFormsAction.objects(name=action.get('name'), bot=bot, status=True).get()
        hubspot_forms_action.portal_id = action['portal_id']
        hubspot_forms_action.form_guid = action['form_guid']
        hubspot_forms_action.response = action['response']
        hubspot_forms_action.fields = action['fields']
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
                action['_id'] = action['_id'].__str__()
            else:
                action.pop('_id')
            action.pop('user')
            action.pop('bot')
            action.pop('status')
            yield action

    @staticmethod
    def get_attached_flows(bot: Text, event_name: Text, event_type: Text, raise_error: bool = True):
        stories_with_event = list(Stories.objects(bot=bot, status=True, events__name__iexact=event_name, events__type__exact=event_type))
        rules_with_event = list(Rules.objects(bot=bot, status=True, events__name__iexact=event_name, events__type__exact=event_type))
        stories_with_event.extend(rules_with_event)
        if stories_with_event and raise_error:
            if event_type == 'user':
                event_type = 'intent'
            raise AppException(f'Cannot remove {event_type} "{event_name}" linked to flow "{stories_with_event[0].block_name}"')
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
        return KeyVault(key=key, value=value, bot=bot, user=user).save().to_mongo().to_dict()["_id"].__str__()

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
        return key_value.to_mongo().to_dict()["_id"].__str__()

    @staticmethod
    def list_secrets(bot: Text):
        """
        List secret keys for bot.

        :param bot: bot id
        """
        keys = list(KeyVault.objects(bot=bot).values_list('key'))
        return keys

    @staticmethod
    def delete_secret(key: Text, bot: Text):
        """
        Delete secret for bot.

        :param key: key to be added
        :param bot: bot id
        """
        if not Utility.is_exist(KeyVault, raise_error=False, key=key, bot=bot):
            raise AppException(f"key '{key}' does not exists!")
        http_action = list(HttpActionConfig.objects(__raw__={
            "bot": bot, "status": True,
            "$or": [{"headers": {"$elemMatch": {"parameter_type": ActionParameterType.key_vault.value, "value": key}}},
                    {"params_list": {"$elemMatch": {"parameter_type": ActionParameterType.key_vault.value, "value": key}}}]
        }).values_list("action_name"))

        email_action = list(EmailActionConfig.objects((
            (Q(smtp_userid__parameter_type=ActionParameterType.key_vault.value) & Q(smtp_userid__value=key)) |
            (Q(smtp_password__parameter_type=ActionParameterType.key_vault.value) & Q(smtp_password__value=key))
        ), bot=bot, status=True).values_list("action_name"))

        google_action = list(GoogleSearchAction.objects((
            Q(api_key__parameter_type=ActionParameterType.key_vault.value) & Q(api_key__value=key)
        ), bot=bot, status=True).values_list("name"))

        action_list = []
        for action_class in [JiraAction, ZendeskAction, PipedriveLeadsAction]:
            attached_action = list(action_class.objects((
            Q(api_token__parameter_type=ActionParameterType.key_vault.value) & Q(api_token__value=key)
        ), bot=bot, status=True).values_list("name"))
            action_list.extend(attached_action)

        hubspot_action = list(HubspotFormsAction.objects(__raw__={
            "bot": bot, "status": True,
            "fields": {"$elemMatch": {"parameter_type": ActionParameterType.key_vault.value, "value": key}}
        }).values_list("name"))

        razorpay_actions = list(RazorpayAction.objects((
                (Q(api_key__parameter_type=ActionParameterType.key_vault.value) & Q(api_key__value=key)) |
                (Q(api_secret__parameter_type=ActionParameterType.key_vault.value) & Q(api_secret__value=key)) |
                (Q(amount__parameter_type=ActionParameterType.key_vault.value) & Q(amount__value=key)) |
                (Q(currency__parameter_type=ActionParameterType.key_vault.value) & Q(currency__value=key)) |
                (Q(username__parameter_type=ActionParameterType.key_vault.value) & Q(username__value=key)) |
                (Q(email__parameter_type=ActionParameterType.key_vault.value) & Q(email__value=key)) |
                (Q(contact__parameter_type=ActionParameterType.key_vault.value) & Q(contact__value=key))
        ), bot=bot, status=True).values_list("name"))

        actions = http_action + email_action + google_action + action_list + hubspot_action + razorpay_actions

        if len(actions):
            raise AppException(f"Key is attached to action: {actions}")
        KeyVault.objects(key=key, bot=bot).delete()

    def add_two_stage_fallback_action(
            self, request_data: dict, bot: Text, user: Text
    ):
        """
        Add 2 stage fallback config.

        :param request_data: request config for fallback action
        :param bot: bot id
        :param user: user
        """
        Utility.is_exist(
            Actions, exp_message="Action exists!", name__iexact=KAIRON_TWO_STAGE_FALLBACK, bot=bot, status=True
        )
        Utility.is_exist(
            KaironTwoStageFallbackAction, exp_message="Action exists!", name__iexact=KAIRON_TWO_STAGE_FALLBACK,
            bot=bot, status=True
        )
        trigger_rules = [rule['payload'] for rule in request_data.get('trigger_rules') or []]
        intent_present = self.fetch_intents(bot)
        if trigger_rules and set(trigger_rules).difference(set(intent_present)):
            raise AppException(f"Intent {set(trigger_rules).difference(set(intent_present))} do not exist in the bot")
        request_data['bot'] = bot
        request_data['user'] = user
        request_data['name'] = KAIRON_TWO_STAGE_FALLBACK
        KaironTwoStageFallbackAction(**request_data).save()
        self.add_action(
            KAIRON_TWO_STAGE_FALLBACK, bot, user, raise_exception=False, action_type=ActionType.two_stage_fallback
        )

    def edit_two_stage_fallback_action(
            self, request_data: dict, bot: Text, user: Text
    ):
        """
        Edit 2 stage fallback config.

        :param request_data: request config for fallback action
        :param bot: bot id
        :param user: user
        :param name: action name
        """
        if not Utility.is_exist(
                KaironTwoStageFallbackAction, raise_error=False, name=KAIRON_TWO_STAGE_FALLBACK, bot=bot, status=True
        ):
            raise AppException(f'Action with name "{KAIRON_TWO_STAGE_FALLBACK}" not found')
        trigger_rules = [rule['payload'] for rule in request_data.get('trigger_rules') or []]
        intent_present = self.fetch_intents(bot)
        if trigger_rules and set(trigger_rules).difference(set(intent_present)):
            raise AppException(f"Intent {set(trigger_rules).difference(set(intent_present))} do not exist in the bot")
        action = KaironTwoStageFallbackAction.objects(name=KAIRON_TWO_STAGE_FALLBACK, bot=bot).get()
        action.trigger_rules = [QuickReplies(**rule) for rule in request_data.get('trigger_rules') or []]
        action.text_recommendations = request_data.get('text_recommendations')
        action.fallback_message = request_data.get('fallback_message')
        action.user = user
        action.save()

    def get_two_stage_fallback_action_config(self, bot: Text, name: Text = KAIRON_TWO_STAGE_FALLBACK,
                                             with_doc_id: bool = True):
        """
        Retrieve 2 stage fallback config.

        :param bot: bot id
        :param name: action name
        :param with_doc_id: return document id along with action configuration if True
        """
        for action in KaironTwoStageFallbackAction.objects(name=name, bot=bot, status=True):
            action = action.to_mongo().to_dict()
            if with_doc_id:
                action['_id'] = action['_id'].__str__()
            else:
                action.pop('_id')
            action.pop('status')
            action.pop('bot')
            action.pop('user')
            yield action

    @staticmethod
    def save_auditlog_event_config(bot, user, data):
        headers = {} if data.get("headers") is None else data.get("headers")
        try:
            event_config = EventConfig.objects(bot=bot).get()
            event_config.update(set__ws_url=data.get("ws_url"),
                                set__headers=Utility.encrypt_message(json.dumps(headers)),
                                set__method=data.get("method"))
        except DoesNotExist:
            event_config = EventConfig(
                bot=bot,
                user=user,
                ws_url=data.get("ws_url"),
                headers=headers,
                method=data.get("method")
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
        if not from_date:
            from_date = datetime.utcnow().date()
        if not to_date:
            to_date = from_date + timedelta(days=1)
        to_date = to_date + timedelta(days=1)
        data_filter = {"bot": bot, "timestamp__gte": from_date, "timestamp__lte": to_date}
        auditlog_data = AuditLogData.objects(**data_filter).skip(start_idx).limit(page_size).exclude('id').to_json()
        return json.loads(auditlog_data)

    def get_logs(self, bot: Text, logtype: str, start_time: datetime, end_time: datetime):
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
                LogType.training_data_generator.value: TrainingDataGenerator,
                LogType.model_training.value: ModelTraining,
                LogType.model_testing.value: ModelTestingLogs,
                LogType.action_logs.value: ActionServerLogs,
                LogType.audit_logs.value: AuditLogData,
                LogType.data_importer.value: ValidationLogs,
                LogType.history_deletion.value: ConversationsHistoryDeleteLogs,
                LogType.multilingual.value: BotReplicationLogs
        }
        if logtype in {LogType.action_logs.value, LogType.audit_logs.value}:
            filter_query = {
                "bot": bot,
                "timestamp__gte": start_time,
                "timestamp__lte": end_time
            }
        else:
            filter_query = {
                "bot": bot,
                "start_timestamp__gte": start_time,
                "start_timestamp__lte": end_time
            }
        value = json.loads(logs[logtype].objects(**filter_query).to_json())
        return value
    
    def delete_audit_logs(self):
        retention_period = Utility.environment['events']['audit_logs']['retention']
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
        query = Rules.objects(bot=bot, status=True, template_type=TemplateType.QNA.value).skip(start_idx).limit(page_size)
        if fetch_all:
            query = Rules.objects(bot=bot, status=True, template_type=TemplateType.QNA.value)
        for qna in query.aggregate(
            {'$addFields': {'story': '$block_name', 'intent': {'$arrayElemAt': ['$events', 1]}, 'action': {'$arrayElemAt': ['$events', 2]}}},
            {'$project': {'_id': { "$toString": "$_id" }, 'story': 1, 'intent': '$intent.name', 'utterance': '$action.name'}},
            {'$lookup': {'from': 'training_examples', 'as': 'training_examples',
                         'let': {'intent_name': '$intent'},
                         'pipeline': [
                             {'$match': {'$expr': {'$and': [{'$eq': ['$intent', '$$intent_name']}, {'$eq': ['$status', True]}, {'$eq': ['$bot', bot]}]}}},
                             {'$project': {'_id': { "$toString": "$_id" }, 'text': 1, 'entities': 1}}
                         ]}},
            {'$lookup': {'from': 'responses', 'as': 'responses',
                         'let': {'utterance_name': '$utterance'},
                         'pipeline': [
                             {'$match': {'$expr': {'$and': [{'$eq': ['$name', '$$utterance_name']}, {'$eq': ['$status', True]}, {'$eq': ['$bot', bot]}]}}},
                             {"$project": {'_id': { "$toString": "$_id" }, "text": 1, "custom": 1}}
                         ]}}
        ):
            training_examples = []
            for t_example in qna.get('training_examples') or []:
                entities = t_example.get("entities") or []
                text = DataUtility.prepare_nlu_text(t_example["text"], entities)
                training_examples.append({"text": text, "_id": t_example['_id']})
            qna['training_examples'] = training_examples
            yield qna

    def save_faq(self, bot: Text, user: Text, df: DataFrame):
        from kairon.shared.augmentation.utils import AugmentationUtils

        error_summary = {'intents': [], 'utterances': [], 'training_examples': []}
        component_count = {'intents': 0, 'utterances': 0, 'stories': 0, 'rules': 0, 'training_examples': 0, 
                           'domain': {'intents': 0, 'utterances': 0}}
        for index, row in df.iterrows():
            is_intent_added = False
            is_response_added = False
            training_example_errors = None
            component_count['utterances'] = component_count['utterances'] + 1
            key_tokens = AugmentationUtils.get_keywords(row['questions'])
            if key_tokens:
                key_tokens = key_tokens[0][0]
            else:
                key_tokens = row['questions'].split('\n')[0]
            intent = key_tokens.replace(' ', '_') + "_" + str(index)
            examples = row['questions'].split("\n")
            component_count['training_examples'] = component_count['training_examples'] + len(examples)
            action = f"utter_{intent}"
            steps = [
                {"name": "...", "type": "BOT"},
                {"name": intent, "type": "INTENT"},
                {"name": action, "type": "BOT"}
            ]
            rule = {'name': intent, 'steps': steps, 'type': 'RULE', 'template_type': TemplateType.QNA.value}
            try:
                training_example_errors = list(self.add_training_example(examples, intent, bot, user, False))
                is_intent_added = True
                self.add_text_response(row['answer'], action, bot, user)
                is_response_added = True
                self.add_complex_story(rule, bot, user)
            except Exception as e:
                logging.exception(e)
                training_example_errors = [f"{a['message']}: {a['text']}" for a in training_example_errors if a["_id"] is None]
                error_summary['training_examples'].extend(training_example_errors)
                if is_intent_added:
                    error_summary['utterances'].append(str(e))
                    self.delete_intent(intent, bot, user, False)
                if is_response_added:
                    self.delete_utterance(action, bot)
        return component_count, error_summary

    def delete_all_faq(self, bot: Text):
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
        qna_intents = list(Rules.objects(bot=bot, status=True, template_type=TemplateType.QNA.value).aggregate(
            get_intents_pipelines
        ))
        qna_intents = set(qna_intents[0].get('intents')) if qna_intents else set()
        story_intents = list(Stories.objects(bot=bot, status=True).aggregate(
            get_intents_pipelines
        ))
        story_intents = set(story_intents[0].get('intents')) if story_intents else set()
        custom_rule_intents = list(Rules.objects(bot=bot, status=True, template_type=TemplateType.CUSTOM.value).aggregate(
            get_intents_pipelines
        ))
        custom_rule_intents = set(custom_rule_intents[0].get('intents')) if custom_rule_intents else set()
        delete_intents = qna_intents - story_intents - custom_rule_intents
        print(delete_intents)

        qna_utterances = list(Rules.objects(bot=bot, status=True, template_type=TemplateType.QNA.value).aggregate(
            get_utterances_pipelines
        ))
        qna_utterances = set(qna_utterances[0].get('utterances')) if qna_utterances else set()
        custom_rule_utterances = list(Rules.objects(bot=bot, status=True, template_type=TemplateType.CUSTOM.value).aggregate(
            get_utterances_pipelines
        ))
        custom_rule_utterances = set(custom_rule_utterances[0].get('utterances')) if custom_rule_utterances else set()
        story_utterances = list(Stories.objects(bot=bot, status=True).aggregate(
            get_utterances_pipelines
        ))
        story_utterances = set(story_utterances[0].get('utterances')) if story_utterances else set()
        delete_utterances = qna_utterances - story_utterances - custom_rule_utterances
        print(delete_utterances)

        Utility.hard_delete_document([TrainingExamples], bot, intent__in=delete_intents)
        Utility.hard_delete_document([Intents], bot, name__in=delete_intents)
        Utility.hard_delete_document([Utterances, Responses], bot, name__in=delete_utterances)
        Utility.hard_delete_document([Rules], bot, template_type=TemplateType.QNA.value)

    def add_razorpay_action(
            self, request_data: dict, bot: Text, user: Text
    ):
        """
        Add razorpay config.

        :param request_data: request config for razorpay action
        :param bot: bot id
        :param user: user
        """
        Utility.is_exist(
            Actions, exp_message="Action exists!", name__iexact=request_data.get('name'), bot=bot, status=True
        )
        Utility.is_exist(
            RazorpayAction, exp_message="Action exists!", name__iexact=request_data.get('name'), bot=bot, status=True
        )
        request_data["bot"] = bot
        request_data["user"] = user
        action_id = RazorpayAction(**request_data).save().to_mongo().to_dict()["_id"].__str__()
        self.add_action(
            request_data['name'], bot, user, raise_exception=False, action_type=ActionType.razorpay_action
        )
        return action_id

    def edit_razorpay_action(
            self, request_data: dict, bot: Text, user: Text
    ):
        """
        Edit razorpay config.

        :param request_data: request config for razorpay action
        :param bot: bot id
        :param user: user
        :param name: action name
        """
        if not Utility.is_exist(
                RazorpayAction, raise_error=False, name=request_data.get('name'), bot=bot, status=True
        ):
            raise AppException(f'Action with name "{request_data.get("name")}" not found')
        action = RazorpayAction.objects(name=request_data.get("name"), bot=bot).get()
        action.api_key = CustomActionRequestParameters(**request_data.get("api_key"))
        action.api_secret = CustomActionRequestParameters(**request_data.get("api_secret"))
        action.amount = CustomActionRequestParameters(**request_data.get("amount"))
        action.currency = CustomActionRequestParameters(**request_data.get("currency"))
        action.username = CustomActionRequestParameters(**request_data.get("username")) if request_data.get("username") else None
        action.email = CustomActionRequestParameters(**request_data.get("email")) if request_data.get("email") else None
        action.contact = CustomActionRequestParameters(**request_data.get("contact")) if request_data.get("contact") else None
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
                action['_id'] = action['_id'].__str__()
            else:
                action.pop('_id')
            action.pop('status')
            action.pop('bot')
            action.pop('user')

            yield action

    def save_content(self, content: Text, user: Text, bot: Text):
        if len(content.split()) < 10:
            raise AppException("Content should contain atleast 10 words.")

        content_obj = BotContent()
        content_obj.data = content
        content_obj.user = user
        content_obj.bot = bot
        id = (
            content_obj.save().to_mongo().to_dict()["_id"].__str__()
        )
        self.add_action(GPT_LLM_FAQ, bot, user, False, ActionType.kairon_faq_action.value)
        return id

    def update_content(self, content_id: str, content: Text, user: Text, bot: Text):
        if len(content.split()) < 10:
            raise AppException("Content should contain atleast 10 words.")

        Utility.is_exist(BotContent, bot=bot, id__ne=content_id, data=content,
                                exp_message="Text already exists!")

        try:
            content_obj = BotContent.objects(bot=bot, user=user, id=content_id).get()
            content_obj.data = content
            content_obj.user = user
            content_obj.timestamp = datetime.utcnow()
            content_obj.save()
        except DoesNotExist:
            raise AppException("Content with given id not found!")

    def delete_content(self, content_id: str, user: Text, bot: Text):
        try:
            content = BotContent.objects(bot=bot, id=content_id).get()
            content.delete()
            if self.get_row_count(BotContent, bot) <= 0:
                self.delete_action(GPT_LLM_FAQ, bot, user)
        except DoesNotExist:
            raise AppException("Text does not exists!")

    def get_content(self, bot: Text):
        """
        fetches content

        :param bot: bot id
        :return: yield dict
        """
        for value in BotContent.objects(bot=bot):
            final_data = {}
            item = value.to_mongo().to_dict()
            data = item.pop("data")
            final_data["_id"] = item["_id"].__str__()
            final_data['content'] = data
            yield final_data

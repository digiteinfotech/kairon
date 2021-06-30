import itertools
import os
from collections import ChainMap
from datetime import datetime
from pathlib import Path
from typing import Text, Dict, List

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

from kairon.exceptions import AppException
from kairon.utils import Utility
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
    UTTERANCE_TYPE, CUSTOM_ACTIONS, REQUIREMENTS, EVENT_STATUS, COMPONENT_COUNT,
    DEFAULT_NLU_FALLBACK_RULE, DEFAULT_NLU_FALLBACK_RESPONSE, DEFAULT_ACTION_FALLBACK_RESPONSE
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
    Actions,
    Intents,
    Forms,
    LookupTables,
    RegexFeatures,
    Entity,
    EndPointBot,
    EndPointAction,
    EndPointTracker,
    Slots,
    StoryEvents,
    ModelDeployment,
    Rules,
    Feedback
)
from ..api import models
from ..api.models import StoryEventType, HttpActionConfigRequest
from ..importer.processor import DataImporterLogProcessor
from ..importer.validator.file_validator import TrainingDataValidator
from ..shared.actions.data_objects import HttpActionConfig, HttpActionRequestBody, HttpActionLog
from ..shared.actions.models import KAIRON_ACTION_RESPONSE_SLOT


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
        training_file_loc = await Utility.save_training_files(nlu, domain, config, stories, rules, http_action)
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
        http_action = self.load_http_action(bot)
        return Utility.create_zip_file(nlu, domain, stories, config, bot, rules, http_action)

    async def apply_template(self, template: Text, bot: Text, user: Text):
        """
        apply use-case template

        :param template: use-case template name
        :param bot: bot id
        :param user: user id
        :return: None
        :raises: raise AppException
        """
        use_case_path = os.path.join("./template/use-cases", template)
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
        try:
            domain_path = os.path.join(path, DEFAULT_DOMAIN_PATH)
            training_data_path = os.path.join(path, DEFAULT_DATA_PATH)
            config_path = os.path.join(path, DEFAULT_CONFIG_PATH)
            http_actions_yml = os.path.join(path, 'http_action.yml')
            importer = RasaFileImporter.load_from_config(config_path=config_path,
                                        domain_path=domain_path,
                                        training_data_paths=training_data_path)
            domain = await importer.get_domain()
            story_graph = await importer.get_stories()
            config = await importer.get_config()
            nlu = await importer.get_nlu_data(config.get('language'))
            http_actions = Utility.read_yaml(http_actions_yml)
            TrainingDataValidator.validate_http_actions(http_actions)

            self.save_training_data(bot, user, config, domain, story_graph, nlu, http_actions, overwrite, REQUIREMENTS.copy())
        except InvalidDomain as e:
            logging.exception(e)
            raise AppException(
                """Failed to validate yaml file.
                            Please make sure the file is initial and all mandatory parameters are specified"""
            )
        except Exception as e:
            logging.exception(e)
            raise AppException(e)

    def save_training_data(self, bot: Text, user: Text, config: dict = None, domain: Domain = None,
                           story_graph: StoryGraph = None, nlu: TrainingData = None, http_actions: dict = None,
                           overwrite: bool = False, what: set = REQUIREMENTS.copy()):
        if overwrite:
            self.delete_bot_data(bot, user, what)

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
        if 'http_actions' in what:
            self.save_http_action(http_actions, bot, user)

    def apply_config(self, template: Text, bot: Text, user: Text):
        """
        apply config template

        :param template: template name
        :param bot: bot id
        :param user: user id
        :return: None
        :raises: AppException
        """
        config_path = os.path.join("./template/config", template + ".yml")
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
        if 'http_actions' in what:
            self.delete_http_action(bot, user)

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
            [TrainingExamples, EntitySynonyms, LookupTables, RegexFeatures], user=user, bot=bot
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
        self.__save_forms(domain.forms, bot, user)
        actions = list(filter(lambda actions: not actions.startswith('utter_') and actions not in domain.form_names, domain.user_actions))
        self.__save_actions(actions, bot, user)
        self.__save_responses(domain.templates, bot, user)
        self.__save_slots(domain.slots, bot, user)
        self.__save_session_config(domain.session_config, bot, user)

    def delete_domain(self, bot: Text, user: Text):
        """
        soft deletes domain data

        :param bot: bot id
        :param user: user id
        :return: None
        """
        Utility.hard_delete_document(
            [Intents, Entities, Forms, Actions, Responses, Slots], bot=bot, user=user
        )

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
        Utility.hard_delete_document([Stories], bot=bot, user=user)

    def load_stories(self, bot: Text) -> StoryGraph:
        """
        loads stories for training

        :param bot: bot id
        :return: StoryGraph
        """
        return self.__prepare_training_story(bot)

    def __save_training_examples(self, training_examples, bot: Text, user: Text):
        if training_examples:
            new_examples = list(
                self.__extract_training_examples(training_examples, bot, user)
            )
            if new_examples:
                TrainingExamples.objects.insert(new_examples)

    def __extract_entities(self, entities):
        for entity in entities:
            entity_data = Entity(
                start=entity[ENTITY.START.value],
                end=entity[ENTITY.END.value],
                value=entity[ENTITY.VALUE.value],
                entity=entity[ENTITY.ENTITY.value],
            )
            yield entity_data

    def __extract_training_examples(self, training_examples, bot: Text, user: Text):
        saved_training_examples, _ = self.get_all_training_examples(bot)
        for training_example in training_examples:
            if 'text' in training_example.data and str(training_example.data['text']).lower() not in saved_training_examples:
                training_data = TrainingExamples()
                training_data.intent = str(training_example.data[
                    TRAINING_EXAMPLE.INTENT.value
                ])
                training_data.text = training_example.data['text']
                training_data.bot = bot
                training_data.user = user
                if "entities" in training_example.data:
                    training_data.entities = list(
                        self.__extract_entities(
                            training_example.data[TRAINING_EXAMPLE.ENTITIES.value]
                        )
                    )
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
                yield EntitySynonyms(bot=bot, synonym=value, value=key, user=user)

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
            yield {entitySynonym.value: entitySynonym.synonym}

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
                    yield LookupTables(name=name, value=element, bot=bot, user=user)

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
            if intent not in saved_intents:
                entities = intents[intent].get('used_entities')
                use_entities = True if entities else False
                yield Intents(name=intent.strip(), bot=bot, user=user, use_entities=use_entities)

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
            if entity not in saved_entities:
                yield Entities(name=entity, bot=bot, user=user)

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

        saved_forms = list(self.fetch_forms(bot, status=True))

        for form, mappings in forms.items():
            form_object = self.__save_form_logic(form, mappings, saved_forms, bot, user)
            if form_object:
                yield form_object

    def __save_form_logic(self, name, mapping, saved_forms, bot, user):
        if {name: mapping} not in saved_forms:
            return Forms(name=name, mapping=mapping, bot=bot, user=user)
        return None

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
            yield {form.name: form.mapping}


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
            if action not in saved_actions:
                yield Actions(name=action, bot=bot, user=user)

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
        saved_responses = self.__fetch_list_of_response(bot)
        for value in values:
            if value not in saved_responses:
                response = Responses()
                response.name = key.strip()
                response.bot = bot
                response.user = user
                r_type, r_object = Utility.prepare_response(value)
                if RESPONSE.Text.value == r_type:
                    response.text = r_object
                elif RESPONSE.CUSTOM.value == r_type:
                    response.custom = r_object
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
        for slot in slots:
            items = vars(slot)
            if items["name"] not in slots_name_list:
                items["type"] = slot.type_name
                items["value_reset_delay"] = items["_value_reset_delay"]
                items.pop("_value_reset_delay")
                items["bot"] = bot
                items["user"] = user
                items.pop("value")
                yield Slots._from_son(items)

    def __save_slots(self, slots, bot: Text, user: Text):
        if slots:
            new_slots = list(self.__extract_slots(slots, bot, user))
            if new_slots:
                Slots.objects.insert(new_slots)
        self.add_slot({"name": "bot", "type": "any", "initial_value": bot, "influence_conversation": False}, bot, user,
                      raise_exception_if_exists=False)

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
                yield StoryEvents(type=event.type_name, name=event.intent_name, entities=entities)
            elif isinstance(event, ActionExecuted):
                yield StoryEvents(type=event.type_name, name=event.action_name)
            elif isinstance(event, ActiveLoop):
                yield StoryEvents(type=event.type_name, name=event.name)
            elif isinstance(event, SlotSet):
                yield StoryEvents(
                    type=event.type_name, name=event.key, value=event.value
                )

    def __fetch_story_block_names(self, bot: Text):
        saved_stories = list(
            Stories.objects(bot=bot, status=True).values_list('block_name')
        )
        return saved_stories

    def __extract_story_step(self, story_steps, bot: Text, user: Text):
        saved_stories = self.__fetch_story_block_names(bot)
        for story_step in story_steps:
            if not isinstance(story_step, RuleStep) and story_step.block_name not in saved_stories:
                story_events = list(self.__extract_story_events(story_step.events))
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
                )
                story.bot = bot
                story.user = user
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

    def __prepare_training_story(self, bot: Text):
        return StoryGraph(list(self.__prepare_training_story_step(bot)))

    def save_config(self, configs: dict, bot: Text, user: Text):
        """
        saves bot configuration

        :param configs: configuration
        :param bot: bot id
        :param user: user id
        :return: config unique id
        """
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
        action_fallback = configs.get("action_fallback")
        nlu_epochs = configs.get("nlu_epochs")
        response_epochs = configs.get("response_epochs")
        ted_epochs = configs.get("ted_epochs")

        if not nlu_epochs and not response_epochs and not ted_epochs and not nlu_confidence_threshold and not action_fallback:
            raise AppException("At least one field is required")

        present_config = self.load_config(bot)
        if nlu_confidence_threshold:
            nlu_confidence_threshold = nlu_confidence_threshold/100
            fallback_classifier_idx = next((idx for idx, comp in enumerate(present_config['pipeline']) if comp["name"] == "FallbackClassifier"), None)
            if fallback_classifier_idx:
                del present_config['pipeline'][fallback_classifier_idx]
            diet_classifier_idx = next((idx for idx, comp in enumerate(present_config['pipeline']) if comp["name"] == "DIETClassifier"), None)
            fallback = {'name': 'FallbackClassifier', 'threshold': nlu_confidence_threshold}
            present_config['pipeline'].insert(diet_classifier_idx + 1, fallback)
            rule_policy = next((comp for comp in present_config['policies'] if comp["name"] == "RulePolicy"), {})
            if not rule_policy:
                rule_policy['name'] = 'RulePolicy'
                present_config['policies'].append(rule_policy)

        if action_fallback:
            if action_fallback == 'action_default_fallback':
                utterance_exists = Utility.is_exist(Responses, raise_error=False, bot=bot, status=True,
                                                    name__iexact='utter_default')
                if not utterance_exists:
                    raise AppException("Utterance utter_default not defined")
            else:
                utterance_exists = Utility.is_exist(Responses, raise_error=False, bot=bot, status=True,
                                                    name__iexact=action_fallback)
                if not (utterance_exists or
                        Utility.is_exist(Actions, raise_error=False, bot=bot, status=True, name__iexact=action_fallback)):
                    raise AppException(f"Action fallback {action_fallback} does not exists")
            fallback = next((comp for comp in present_config['policies'] if comp["name"] == "RulePolicy"), {})
            if not fallback:
                fallback['name'] = 'RulePolicy'
                present_config['policies'].append(fallback)
            fallback['core_fallback_action_name'] = action_fallback
            fallback['core_fallback_threshold'] = 0.3

        Utility.add_or_update_epoch(present_config, configs)
        self.save_config(present_config, bot, user)

    def list_epoch_and_fallback_config(self, bot: Text):
        config = self.load_config(bot)
        selected_config = {}
        nlu_fallback = next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), {})
        action_fallback = next((comp for comp in config['policies'] if comp["name"] == "RulePolicy"), None)
        ted_policy = next((comp for comp in config['policies'] if comp["name"] == "TEDPolicy"), None)
        diet_classifier = next((comp for comp in config['pipeline'] if comp["name"] == "DIETClassifier"), None)
        response_selector = next((comp for comp in config['pipeline'] if comp["name"] == "ResponseSelector"), None)
        selected_config['nlu_confidence_threshold'] = nlu_fallback.get('threshold')
        selected_config['action_fallback'] = action_fallback.get('core_fallback_action_name')
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
                read_config_file("./template/config/default.yml")
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
                    text=data.intent.strip().lower(),
                    bot=bot,
                    user=user,
                    is_integration=is_integration
                )
                status[data.intent.strip().lower()] = intent_id
            except AppException as e:
                status[data.intent.strip().lower()] = str(e)

            story_name = "path_" + data.intent.strip().lower()
            utterance = "utter_" + data.intent.strip().lower()
            events = [
                {"name": data.intent.strip().lower(), "type": "INTENT"},
                {"name": utterance.strip().lower(), "type": "BOT"}]
            try:
                doc_id = self.add_complex_story(
                    story= {'name': story_name.lower(), 'steps': events, 'type': 'STORY'},
                    bot=bot,
                    user=user
                )
                status['story'] = doc_id
            except AppException as e:
                status['story'] = str(e)
            try:
                status_message = list(
                    self.add_training_example(
                        data.training_examples, data.intent.lower(), bot, user,
                        is_integration)
                )
                status['training_examples'] = status_message
                training_examples = []
                for training_data_add_status in status_message:
                    if training_data_add_status['_id']:
                        training_examples.append(training_data_add_status['text'])
                training_data_added[data.intent.strip().lower()] = training_examples
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
        saved = Intents(name=text.strip().lower(), bot=bot, user=user, is_integration=is_integration).save().to_mongo().to_dict()
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
                text, entities = Utility.extract_text_and_entities(example.strip())
                if Utility.is_exist(
                        TrainingExamples,
                        raise_error=False,
                        text__iexact=text,
                        bot=bot,
                        status=True,
                ):
                    yield {
                        "text": example,
                        "message": "Training Example already exists!",
                        "_id": None,
                    }
                else:
                    if entities:
                        ext_entity = [ent["entity"] for ent in entities]
                        self.__save_domain_entities(ext_entity, bot=bot, user=user)
                        self.__add_slots_from_entities(ext_entity, bot, user)
                        new_entities = list(self.__extract_entities(entities))
                    else:
                        new_entities = None

                    training_example = TrainingExamples(
                        intent=intent.strip().lower(),
                        text=text,
                        entities=new_entities,
                        bot=bot,
                        user=user,
                    )

                    saved = training_example.save().to_mongo().to_dict()
                    yield {
                        "text": example,
                        "_id": saved["_id"].__str__(),
                        "message": "Training Example added successfully!",
                    }
            except Exception as e:
                yield {"text": example, "_id": None, "message": str(e)}

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
            text, entities = Utility.extract_text_and_entities(example.strip())
            if Utility.is_exist(
                    TrainingExamples,
                    raise_error=False,
                    text__iexact=text,
                    bot=bot,
                    status=True,
            ):
                raise AppException("Training Example already exists!")
            training_example = TrainingExamples.objects(bot=bot, intent=intent.strip().lower()).get(
                id=id
            )
            training_example.user = user
            training_example.text = text
            if entities:
                training_example.entities = list(self.__extract_entities(entities))
            training_example.timestamp = datetime.utcnow()
            training_example.save()
        except DoesNotExist as e:
            raise AppException("Invalid training example!")

    def search_training_examples(self, search: Text, bot: Text):
        """
        search the training examples

        :param search: search text
        :param bot: bot id
        :return: yields tuple of intent name, training example
        """
        results = (
            TrainingExamples.objects(bot=bot, status=True)
                .search_text(search)
                .order_by("$text_score")
                .limit(5)
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
        print(intents_and_training_examples)
        for data in intents_and_training_examples:
            intents_and_training_examples_dict[data['intent']] = data['training_examples']

        print(intents_and_training_examples_dict)
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
                "text": Utility.prepare_nlu_text(example["text"], entities),
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

    def add_entity(self, name: Text, bot: Text, user: Text):
        """
        adds an entity

        :param name: entity name
        :param bot: bot id
        :param user: user id
        :return: entity id
        """
        if Utility.check_empty_string(name):
            raise AppException("Entity Name cannot be empty or blank spaces")
        Utility.is_exist(
            Entities,
            exp_message="Entity already exists!",
            name__iexact=name.strip(),
            bot=bot,
            status=True,
        )
        entity = (
            Entities(name=name.strip(), bot=bot, user=user).save().to_mongo().to_dict()
        )
        if not Utility.is_exist(
                Slots, raise_error=False, name__iexact=name, bot=bot, status=True
        ):
            Slots(name=name.strip(), type="text", bot=bot, user=user).save()
        return entity["_id"].__str__()

    def get_entities(self, bot: Text):
        """
        fetches list of registered entities

        :param bot: bot id
        :return: list of entities
        """
        entities = Entities.objects(bot=bot, status=True)
        return list(self.__prepare_document_list(entities, "name"))

    def add_action(self, name: Text, bot: Text, user: Text, raise_exception=True):
        """
        adds action
        :param name: action name
        :param bot: bot id
        :param user: user id
        :param raise_exception: default is True to raise exception if Entity already exists
        :return: action id
        """
        if Utility.check_empty_string(name):
            raise AppException("Action name cannot be empty or blank spaces")

        if not name.startswith('utter_') and not Utility.is_exist(
                                                Actions,
                                                raise_error=raise_exception,
                                                exp_message="Action exists!",
                                                name__iexact=name.strip(),
                                                bot=bot,
                                                status=True):
            action = (
                Actions(name=name.strip().lower(), bot=bot, user=user).save().to_mongo().to_dict()
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
        slots = [
            Slots(name=entity, type="text", bot=bot, user=user)
            for entity in entities
            if entity not in slot_name_list
        ]
        if slots:
            Slots.objects.insert(slots)

    def add_text_response(self, utterance: Text, name: Text, bot: Text, user: Text):
        """
        saves bot text utterance
        :param utterance: text utterance
        :param name: utterance name
        :param bot: bot id
        :param user: user id
        :return: bot utterance id
        """
        if Utility.check_empty_string(utterance):
            raise AppException("Utterance text cannot be empty or blank spaces")
        if Utility.check_empty_string(name):
            raise AppException("Utterance name cannot be empty or blank spaces")
        return self.add_response(
            utterances={"text": utterance.strip()}, name=name.strip().lower(), bot=bot, user=user
        )

    def add_response(self, utterances: Dict, name: Text, bot: Text, user: Text):
        """
        save bot utterance

        :param utterances: utterance value
        :param name: utterance name
        :param bot: bot id
        :param user: user id
        :return: bot utterance id
        """
        self.__check_response_existence(
            response=utterances, bot=bot, exp_message="Utterance already exists!"
        )
        response = list(
            self.__extract_response_value(
                values=[utterances], key=name.strip().lower(), bot=bot, user=user
            )
        )[0]
        value = response.save().to_mongo().to_dict()
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
        self.edit_response(id, {"text": utterance}, name.lower(), bot, user)

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
            response = Responses.objects(bot=bot, name=name.lower()).get(id=id)
            r_type, r_object = Utility.prepare_response(utterances)
            if RESPONSE.Text.value == r_type:
                response.text = r_object
                response.custom = None
            elif RESPONSE.CUSTOM.value == r_type:
                response.custom = r_object
                response.text = None
            response.user = user
            response.timestamp = datetime.utcnow()
            response.save()
        except DoesNotExist as e:
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
            if value.text:
                val = list(
                    self.__prepare_response_Text([value.text.to_mongo().to_dict()])
                )[0]
            elif value.custom:
                val = value.custom.to_mongo().to_dict()
            yield {"_id": value.id.__str__(), "value": val}

    def __fetch_list_of_response(self, bot: Text):
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
        saved_items = self.__fetch_list_of_response(bot)

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

    def __complex_story_prepare_steps(self, steps: List[Dict], bot, user):
        """
        convert kairon story events to rasa story events
        :param steps: list of story steps
        :return: rasa story events list
        """

        events = []
        for step in steps:
            if step['type'] == "INTENT":
                events.append(StoryEvents(
                    name=step['name'].strip().lower(),
                    type="user"))
            elif step['type'] in ["BOT", "HTTP_ACTION", "ACTION"]:
                events.append(StoryEvents(
                    name=step['name'].strip().lower(),
                    type="action"))
                if step['type']  == "ACTION":
                    self.add_action(step['name'], bot, user, raise_exception=False)
            else:
                raise AppException("Invalid event type!")
        return events

    def add_complex_story(self, story: Dict, bot: Text, user: Text):
        """
        save story in mongodb

        :param name: story name
        :param steps: story steps list
        :param bot: bot id
        :param user: user id
        :return: story id
        :raises: AppException: Story already exist!

        """
        name = story['name']
        steps = story['steps']
        type = story['type']
        if Utility.check_empty_string(name):
            raise AppException("path name cannot be empty or blank spaces")

        if not steps:
            raise AppException("steps are required")

        events = self.__complex_story_prepare_steps(steps, bot, user)

        data_class = None
        if type == "STORY":
            data_class = Stories
        elif type == 'RULE':
            data_class = Rules
        else:
            raise AppException("Invalid type")

        Utility.is_exist_query(data_class,
                               query=(Q(bot=bot) & Q(status=True)) & (Q(block_name__iexact=name) | Q(events=events)),
                               exp_message="FLow already exists!")

        data_object = data_class(
            block_name=name.strip().lower(),
            events=events,
            bot=bot,
            user=user,
            start_checkpoints=[STORY_START],
        )

        id = (
            data_object.save().to_mongo().to_dict()["_id"].__str__()
        )

        self.add_slot({"name": "bot", "type": "any", "initial_value": bot, "influence_conversation": False}, bot, user,
                      raise_exception_if_exists=False)

        return id

    def update_complex_story(self, story: Dict, bot: Text, user: Text):
        """
        Updates story in mongodb

        :param story: dict contains name, steps and type for either rules or story
        :param bot: bot id
        :param user: user id
        :return: story id
        :raises: AppException: Story already exist!

        """
        name = story['name']
        steps = story['steps']
        type = story['type']
        if Utility.check_empty_string(name):
            raise AppException("path name cannot be empty or blank spaces")

        if not steps:
            raise AppException("steps are required")

        if type == 'STORY':
            data_class = Stories
        elif type == 'RULE':
            data_class = Rules
        else:
            raise AppException("Invalid type")

        try:
            data_object = data_class.objects(bot=bot, status=True, block_name__iexact=name).get()
        except DoesNotExist:
            raise AppException("FLow does not exists")

        events = self.__complex_story_prepare_steps(steps, bot, user)
        data_object['events'] = events
        Utility.is_exist_query(data_class,
                               query=(Q(bot=bot) & Q(status=True) & Q(events=data_object['events'])),
                               exp_message="FLow already exists!")

        story_id = (
            data_object.save().to_mongo().to_dict()["_id"].__str__()
        )
        return story_id

    def delete_complex_story(self, name: str, type: Text, bot: Text, user: Text):
        """
        Soft deletes complex story.
        :param name: Flow name
        :param type: Flow Type
        :param user: user id
        :param bot: bot id
        :return:
        """

        data_class = None
        if type == 'STORY':
            data_class = Stories
        elif type == 'RULE':
            data_class = Rules
        else:
            raise AppException("Invalid type")
        try:
            data_class.objects(bot=bot, status=True, block_name__iexact=name).get()
        except DoesNotExist:
            raise AppException("Flow does not exists")
        Utility.delete_document(
            [data_class], bot=bot, user=user, block_name__iexact=name
        )

    def get_stories(self, bot: Text):
        """
        fetches stories 
        
        :param bot: bot is 
        :return: yield dict
        """

        http_actions = self.list_http_action_names(bot)
        data_list = list(Stories.objects(bot=bot, status=True))
        data_list.extend(list(Rules.objects(bot=bot, status=True)))
        for value in data_list:
            final_data = {}
            item = value.to_mongo().to_dict()
            block_name = item.pop("block_name")
            events = item.pop("events")
            final_data["_id"] = item["_id"].__str__()
            if isinstance(value, Stories):
                final_data['type'] = 'STORY'
            elif isinstance(value, Rules):
                final_data['type'] = 'RULE'
            else:
                continue
            steps = []
            for event in events:
                step = {}

                if event['type'] == 'user':
                    step['name'] = event['name']
                    step['type'] = 'INTENT'
                elif event['type'] == 'action':
                    step['name'] = event['name']
                    if event['name'] in http_actions:
                        step['type'] = 'HTTP_ACTION'
                    elif str(event['name']).startswith("utter_"):
                        step['type'] = 'BOT'
                    else:
                        step['type'] = 'ACTION'
                if step:
                    steps.append(step)

            final_data['name'] = block_name
            final_data['steps'] = steps
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

        if endpoint_config.get("tracker_endpoint"):
            endpoint.tracker_endpoint = EndPointTracker(
                **endpoint_config.get("tracker_endpoint")
            )

        endpoint.bot = bot
        endpoint.user = user
        return endpoint.save().to_mongo().to_dict()["_id"].__str__()

    def get_endpoints(self, bot: Text, raise_exception=True):
        """
        fetches endpoint configuration

        :param bot: bot id
        :param raise_exception: wether to raise an exception, default is True
        :return: endpoint configuration
        """
        try:
            endpoint = Endpoints.objects().get(bot=bot).to_mongo().to_dict()
            endpoint.pop("bot")
            endpoint.pop("user")
            endpoint.pop("timestamp")
            endpoint["_id"] = endpoint["_id"].__str__()
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
            intentObj = Intents.objects(bot=bot, status=True).get(name__iexact=intent)

        except DoesNotExist as custEx:
            logging.exception(custEx)
            raise AppException(
                "Invalid IntentName: Unable to remove document: " + str(custEx)
            )

        if is_integration:
            if not intentObj.is_integration:
                raise AppException("This intent cannot be deleted by an integration user")

        try:
            intentObj.user = user
            intentObj.status = False
            intentObj.timestamp = datetime.utcnow()
            intentObj.save(validate=False)

            if delete_dependencies:
                Utility.delete_document(
                    [TrainingExamples], bot=bot, user=user, intent__iexact=intent
                )
        except Exception as ex:
            logging.exception(ex)
            raise AppException("Unable to remove document" + str(ex))

    def delete_utterance(self, utterance_name: str, bot: str, user: str):
        if not (utterance_name and utterance_name.strip()):
            raise AppException("Utterance cannot be empty or spaces")
        try:
            responses = list(Responses.objects(name=utterance_name.strip().lower(), bot=bot, user=user, status=True))
            if not responses:
                raise DoesNotExist("Utterance does not exists")
            story = list(Stories.objects(bot=bot, status=True, events__name__iexact=utterance_name))
            if not story:
                for response in responses:
                    response.status = False
                    response.save()
            else:
                raise AppException("Cannot remove utterance linked to story")
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
            story = list(Stories.objects(bot=bot, status=True, events__name__iexact=utterance_name))
            responses = list(Responses.objects(bot=bot, status=True, name__iexact=utterance_name))

            if story and len(responses) <= 1:
                raise AppException("At least one response is required for utterance linked to story")
            self.remove_document(Responses, utterance_id, bot, user)
        except DoesNotExist as e:
            raise AppException(e)

    def update_http_config(self, request_data: HttpActionConfigRequest, user: str, bot: str):
        """
        Updates Http configuration.
        :param request_data: HttpActionConfigRequest object containing configuration to be modified
        :param user: user id
        :param bot: bot id
        :return: Http configuration id for updated Http action config
        """
        http_action = None
        try:
            http_action: HttpActionConfig = self.get_http_action_config(
                action_name=request_data.action_name, bot=bot)
            if http_action is None:
                raise AppException("No HTTP action found for bot " + bot + " and action " + request_data.action_name)
        except AppException as e:
            if str(e).__contains__("No HTTP action found for bot"):
                raise e

        http_params = [HttpActionRequestBody(key=param.key, value=param.value, parameter_type=param.parameter_type)
                       for param in request_data.http_params_list]
        http_action.request_method = request_data.request_method
        http_action.params_list = http_params
        http_action.http_url = request_data.http_url
        http_action.response = request_data.response
        http_action.auth_token = request_data.auth_token
        http_action.user = user
        http_action.status = True
        http_action.bot = bot
        http_action.timestamp = datetime.utcnow()
        http_config_id = http_action.save(validate=False).to_mongo().to_dict()["_id"].__str__()
        return http_config_id

    def add_http_action_config(self, http_action_config: Dict, user: str, bot: str):
        """
        Adds a new Http action.
        :param http_action_config: dict object containing configuration for the Http action
        :param user: user id
        :param bot: bot id
        :return: Http configuration id for saved Http action config
        """
        Utility.is_exist(HttpActionConfig, exp_message="Action exists",
                         action_name__iexact=http_action_config.get("action_name"), bot=bot,
                         status=True)
        http_action_params = [
            HttpActionRequestBody(
                key=param['key'],
                value=param['value'],
                parameter_type=param['parameter_type'])
            for param in http_action_config.get("http_params_list")]

        doc_id = HttpActionConfig(
            auth_token=http_action_config.get("auth_token"),
            action_name=http_action_config['action_name'].lower(),
            response=http_action_config['response'],
            http_url=http_action_config['http_url'],
            request_method=http_action_config['request_method'],
            params_list=http_action_params,
            bot=bot,
            user=user
        ).save().to_mongo().to_dict()["_id"].__str__()
        self.add_action(http_action_config['action_name'].lower(), bot, user, raise_exception=False)
        self.add_slot({"name": KAIRON_ACTION_RESPONSE_SLOT, "type": "any", "initial_value": None, "influence_conversation": False}, bot, user,
                      raise_exception_if_exists=False)
        return doc_id

    def delete_http_action_config(self, action: str, user: str, bot: str):
        """
        Soft deletes configuration for Http action.
        :param action: Http action to be deleted.
        :param user: user id
        :param bot: bot id
        :return:
        """
        is_exists = Utility.is_exist(HttpActionConfig, action_name__iexact=action, bot=bot, user=user,
                                     raise_error=False)
        if not is_exists:
            raise AppException("No HTTP action found for bot " + bot + " and action " + action)
        Utility.delete_document([HttpActionConfig], action_name__iexact=action, bot=bot, user=user)
        Utility.delete_document([Actions], name__iexact=action, bot=bot, user=user)

    def get_http_action_config(self, bot: str, action_name: str):
        """
        Fetches Http action config from collection.
        :param bot: bot id
        :param user: user id
        :param action_name: action name
        :return: HttpActionConfig object containing configuration for the Http action.
        """
        try:
            http_config_dict = HttpActionConfig.objects().get(bot=bot,
                                                              action_name=action_name, status=True)
        except DoesNotExist as ex:
            logging.exception(ex)
            raise AppException("No HTTP action found for bot " + bot + " and action " + action_name)
        except Exception as e:
            logging.exception(e)
            raise AppException(e)
        return http_config_dict

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
        actions = list(Actions.objects(bot=bot, status=True).values_list('name'))

        if actions:
            http_actions = self.list_http_action_names(bot)
            return [action for action in actions if not str(action).startswith("utter_") and action not in http_actions]
        else:
            return actions

    def list_http_action_names(self, bot: Text):
        actions = list(HttpActionConfig.objects(bot=bot, status=True).values_list('action_name'))
        return actions

    def add_slot(self, slot_value: Dict, bot, user, raise_exception_if_exists=True):
        try:
            slot = Slots.objects(name__iexact=slot_value['name'], bot=bot, status=True).get()
            if raise_exception_if_exists:
                raise AppException("Slot already exists!")
        except DoesNotExist:
            slot = Slots()
            slot.name = slot_value['name']

        slot.initial_value = slot_value.get('initial_value')
        slot.type = slot_value.get('type')
        slot.influence_conversation = slot_value.get('influence_conversation')
        slot.user = user
        slot.bot = bot
        slot_id = slot.save().to_mongo().to_dict()['_id'].__str__()
        return slot_id

    @staticmethod
    def get_row_count(document: Document, bot: str):
        """
        Gets the count of rows in a document for a particular bot.
        :param document: Mongoengine document for which count is to be given
        :param bot: bot id
        :return: Count of rows
        """
        return document.objects(bot=bot).count()

    @staticmethod
    def get_action_server_logs(bot: str, start_idx: int = 0, page_size: int = 10):
        """
        Fetches all action server logs from collection.
        :param bot: bot id
        :param start_idx: start index in collection
        :param page_size: number of rows
        :return: List of Http actions.
        """
        for log in HttpActionLog.objects(bot=bot).order_by("-timestamp").skip(start_idx).limit(page_size):
            log = log.to_mongo().to_dict()
            log.pop("bot")
            log.pop("_id")
            yield log

    def __extract_rules(self, story_steps, bot: Text, user: Text):
        saved_rules = self.fetch_rule_block_names(bot)

        for story_step in story_steps:
            if isinstance(story_step, RuleStep) and story_step.block_name not in saved_rules:
                rule = self.__extract_rule_events(story_step, bot, user)
                yield rule

    def __extract_rule_events(self, rule_step, bot: Text, user: Text):
        rule_events = list(self.__extract_story_events(rule_step.events))
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
            bot=bot,
            user=user
        )
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
        Utility.hard_delete_document([Rules], bot=bot, user=user)

    def delete_http_action(self, bot: Text, user: Text):
        """
        soft deletes http actions

        :param bot: bot id
        :param user: user id
        :return: None
        """
        Utility.hard_delete_document([HttpActionConfig], bot=bot, user=user)

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

    def save_http_action(self, http_action: dict, bot: Text, user: Text):
        """
        saves http actions data
        :param http_action: http actions
        :param bot: bot id
        :param user: user id
        :return: None
        """

        if not http_action or not http_action.get('http_actions'):
            return

        saved_http_actions = set([action['action_name'] for action in self.list_http_actions(bot)])

        actions_data = http_action['http_actions']
        for actions in actions_data:
            if actions['action_name'] not in saved_http_actions:
                action_name = str(actions['action_name']).lower()
                http_obj = HttpActionConfig()
                http_obj.bot = bot
                http_obj.user = user
                http_obj.action_name = action_name.strip()
                http_obj.http_url = actions['http_url']
                http_obj.response = actions['response']
                http_obj.request_method = actions['request_method']
                if actions.get('params_list'):
                    request_body_list = []
                    for parameters in actions['params_list']:
                        request_body = HttpActionRequestBody()
                        request_body.key = parameters.get('key')
                        request_body.value = parameters.get('value')
                        request_body.parameter_type = parameters.get('parameter_type')
                        request_body_list.append(request_body)
                    http_obj.params_list = request_body_list
                if actions.get('auth_token'):
                    http_obj.auth_token = actions['auth_token']
                http_obj.save()
                self.add_action(action_name, bot, user, raise_exception=False)

    def load_http_action(self, bot: Text):
        """
        loads the http actions from the database
        :param bot: bot id
        :return: dict
        """
        action_list = []
        for obj in HttpActionConfig.objects(bot=bot, status=True):
            item = obj.to_mongo().to_dict()
            http_dict = {"action_name": item["action_name"], "response": item["response"], "http_url": item["http_url"],
                         "request_method": item["request_method"]}
            if item.get('auth_token'):
                http_dict['auth_token'] = item['auth_token']
            if item.get('params_list'):
                http_dict['params_list'] = item['params_list']
            action_list.append(http_dict)
        http_action = {"http_actions": action_list} if action_list else {}
        return http_action

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

    @staticmethod
    def add_feedback(rating: float, bot: str, user: str, scale: float = 5.0, feedback: str = None):
        """
        Add user feedback.
        @param rating: user given rating.
        @param bot: bot id.
        @param user: Kairon username.
        @param scale: Scale on which rating is given. %.0 is the default value.
        @param feedback: feedback if any.
        @return:
        """
        Feedback(rating=rating, scale=scale, feedback=feedback, bot=bot, user=user).save()

    async def validate_and_log(self, bot: Text, user: Text, training_files, overwrite):
        DataImporterLogProcessor.is_limit_exceeded(bot)
        DataImporterLogProcessor.is_event_in_progress(bot)
        files_received, is_event_data, non_event_validation_summary = await self.validate_and_prepare_data(bot,
                                                                                                           user,
                                                                                                           training_files,
                                                                                                           overwrite)
        DataImporterLogProcessor.add_log(bot, user, is_data_uploaded=True, files_received=list(files_received))
        if not is_event_data:
            status = 'Failure'
            summary = non_event_validation_summary['summary']
            component_count = non_event_validation_summary['component_count']
            if not summary.get('http_actions') and not summary.get('config'):
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
        bot_data_home_dir = await Utility.save_uploaded_data(bot, training_files)
        files_to_prepare = Utility.validate_and_get_requirements(bot_data_home_dir, True)
        files_received = REQUIREMENTS - files_to_prepare
        is_event_data = False

        if files_received.difference({'config', 'http_actions'}):
            is_event_data = True
        else:
            non_event_validation_summary = self.save_data_without_event(bot_data_home_dir, bot, user, overwrite)
        return files_received, is_event_data, non_event_validation_summary

    def save_data_without_event(self, data_home_dir: Text, bot: Text, user: Text, overwrite: bool):
        """
        Saves http actions and config file.
        """
        http_actions = None
        config = None
        error_summary = {}
        component_count = COMPONENT_COUNT.copy()
        actions_path = os.path.join(data_home_dir, 'http_action.yml')
        config_path = os.path.join(data_home_dir, 'config.yml')
        if os.path.exists(actions_path):
            http_actions = Utility.read_yaml(actions_path)
            errors = TrainingDataValidator.validate_http_actions(http_actions)
            error_summary['http_actions'] = errors
        if os.path.exists(config_path):
            config = Utility.read_yaml(config_path)
            errors = TrainingDataValidator.validate_rasa_config(config)
            error_summary['config'] = errors

        if not error_summary.get('http_actions') and not error_summary.get('config'):
            files_to_save = set()
            if http_actions:
                files_to_save.add('http_actions')
                component_count['http_actions'] = len(http_actions.get('http_actions'))
            if config:
                files_to_save.add('config')
            self.save_training_data(bot, user, http_actions=http_actions, config=config,
                                    overwrite=overwrite, what=files_to_save)
        return {'summary': error_summary, 'component_count': component_count}

    def prepare_training_data_for_validation(self, bot: Text, bot_data_home_dir: str = None,
                                             which: set = REQUIREMENTS):
        """
        Writes training data into files and makes them available for validation.
        @param bot: bot id.
        @param bot_data_home_dir: location where data needs to be written
        @param which: which training data is to be written
        @return:
        """
        if not bot_data_home_dir:
            bot_data_home_dir = os.path.join('training_data', bot, str(datetime.utcnow()))
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

        property_idx = next((idx for idx, comp in enumerate(config_obj['pipeline']) if comp["name"] == "FallbackClassifier"), None)
        if not property_idx:
            property_idx = next((idx for idx, comp in enumerate(config_obj['pipeline']) if comp["name"] == "DIETClassifier"))
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
                if 'action' == event.type:
                    action = event.name
                    break
        except DoesNotExist as e:
            logging.error(e)
        return action

    def add_default_fallback_data(self, bot: Text, user: Text, nlu_fallback: bool = True, action_fallback: bool = True):
        if nlu_fallback:
            if not Utility.is_exist(Responses, raise_error=False, bot=bot, status=True, name__iexact='utter_please_rephrase'):
                self.add_text_response(DEFAULT_NLU_FALLBACK_RESPONSE, 'utter_please_rephrase', bot, user)
            steps = [
                {"name": "nlu_fallback", "type": "INTENT"},
                {"name": "utter_please_rephrase", "type": "BOT"}
            ]
            rule = {'name': DEFAULT_NLU_FALLBACK_RULE, 'steps': steps, 'type': 'RULE'}
            try:
                self.add_complex_story(rule, bot, user)
            except AppException as e:
                logging.error(str(e))

        if action_fallback:
            if not Utility.is_exist(Responses, raise_error=False, bot=bot, status=True, name__iexact='utter_default'):
                self.add_text_response(DEFAULT_ACTION_FALLBACK_RESPONSE, 'utter_default', bot, user)

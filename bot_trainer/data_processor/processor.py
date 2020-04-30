import asyncio
import itertools
import logging
import os
from collections import ChainMap

from mongoengine.errors import DoesNotExist
from mongoengine.errors import NotUniqueError
from rasa.constants import DEFAULT_CONFIG_PATH, DEFAULT_DATA_PATH, DEFAULT_DOMAIN_PATH
from rasa.core.domain import InvalidDomain
from rasa.core.domain import SessionConfig
from rasa.core.events import Form, ActionExecuted, UserUttered
from rasa.core.training.structures import Checkpoint
from rasa.core.training.structures import STORY_START
from rasa.core.training.structures import StoryGraph, StoryStep, SlotSet
from rasa.data import get_core_nlu_files
from rasa.importers import utils
from rasa.importers.rasa import Domain, StoryFileReader
from rasa.nlu.training_data import Message, TrainingData
from rasa.nlu.training_data.formats.markdown import MarkdownReader, ent_regex
from rasa.utils.io import read_config_file
from rasa.utils.endpoints import EndpointConfig

from .constant import *
from .data_objects import *
from .cache import InMemoryAgentCache
from rasa.train import DEFAULT_MODELS_PATH
from rasa.core.agent import Agent
import logging


class MongoProcessor:
    def save_from_path(self, path: Text, bot: Text, user="default"):
        try:
            story_files, nlu_files = get_core_nlu_files(
                os.path.join(path, DEFAULT_DATA_PATH)
            )
            nlu = utils.training_data_from_paths(nlu_files, "en")
            domain = Domain.from_file(os.path.join(path, DEFAULT_DOMAIN_PATH))
            domain.check_missing_templates()
            loop = asyncio.new_event_loop()
            story_steps = loop.run_until_complete(
                StoryFileReader.read_from_files(story_files, domain)
            )
            self.save_domain(domain, bot, user)
            self.save_stories(story_steps, bot, user)
            self.save_nlu(nlu, bot, user)
            self.__save_config(
                read_config_file(os.path.join(path, DEFAULT_CONFIG_PATH)), bot, user
            )
        except InvalidDomain as e:
            logging.info(e)
            raise AppException(
                """Failed to validate yaml file.
                            Please make sure the file is initial and all mandatory parameters are specified"""
            )
        except Exception as e:
            logging.info(e)
            raise AppException(e)

    def save_nlu(self, nlu: TrainingData, bot: Text, user: Text):
        self.__save_training_examples(nlu.training_examples, bot, user)
        self.__save_entity_synonyms(nlu.entity_synonyms, bot, user)
        self.__save_lookup_tables(nlu.lookup_tables, bot, user)
        self.__save_regex_features(nlu.regex_features, bot, user)

    def load_nlu(self, bot: Text) -> TrainingData:
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
        self.__save_intents(domain.intents, bot, user)
        self.__save_domain_entities(domain.entities, bot, user)
        self.__save_forms(domain.form_names, bot, user)
        self.__save_actions(domain.user_actions, bot, user)
        self.__save_responses(domain.templates, bot, user)
        self.__save_slots(domain.slots, bot, user)
        self.__save_session_config(domain.session_config, bot, user)

    def load_domain(self, bot: Text) -> Domain:
        domain_dict = {
            DOMAIN.INTENTS.value: self.__prepare_training_intents(bot),
            DOMAIN.ACTIONS.value: self.__prepare_training_actions(bot),
            DOMAIN.SLOTS.value: self.__prepare_training_slots(bot),
            DOMAIN.SESSION_CONFIG.value: self.__prepare_training_session_config(bot),
            DOMAIN.RESPONSES.value: self.__prepare_training_responses(bot),
            DOMAIN.FORMS.value: self.__prepare_training_forms(bot),
            DOMAIN.ENTITIES.value: self.__prepare_training_domain_entities(bot),
        }
        return Domain.from_dict(domain_dict)

    def save_stories(self, story_steps: Text, bot: Text, user: Text):
        self.__save_stories(story_steps, bot, user)

    def load_stories(self, bot: Text) -> StoryGraph:
        return self.__prepare_training_story(bot)

    def __save_training_examples(self, training_examples, bot: Text, user: Text):
        if training_examples:
            TrainingExamples.objects.insert(
                list(self.__extract_training_examples(training_examples, bot, user))
            )

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
        for training_example in training_examples:
            training_data = TrainingExamples()
            training_data.intent = training_example.data[TRAINING_EXAMPLE.INTENT.value]
            training_data.text = training_example.text
            training_data.bot = bot
            training_data.user = user
            if "entities" in training_example.data:
                training_data.entities = list(
                    self.__extract_entities(
                        training_example.data[TRAINING_EXAMPLE.ENTITIES.value]
                    )
                )
            yield training_data

    def __extract_synonyms(self, synonyms, bot: Text, user: Text):
        for key, value in synonyms.items():
            yield EntitySynonyms(bot=bot, synonym=value, value=key, user=user)

    def __save_entity_synonyms(self, entity_synonyms, bot: Text, user: Text):
        if entity_synonyms:
            EntitySynonyms.objects.insert(
                list(self.__extract_synonyms(entity_synonyms, bot, user))
            )

    def fetch_synonyms(self, bot: Text, status=True):
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
        trainingExamples = TrainingExamples.objects(bot=bot, status=status)
        for trainingExample in trainingExamples:
            message = Message(trainingExample.text)
            message.data = {TRAINING_EXAMPLE.INTENT.value: trainingExample.intent}
            if trainingExample.entities:
                message.data[TRAINING_EXAMPLE.ENTITIES.value] = list(
                    self.__prepare_entities(trainingExample.entities)
                )
            yield message

    def __prepare_training_examples(self, bot: Text):
        return list(self.fetch_training_examples(bot))

    def __extract_lookup_tables(self, lookup_tables, bot: Text, user: Text):
        for lookup_table in lookup_tables:
            name = lookup_table[LOOKUP_TABLE.NAME.value]
            for element in lookup_table[LOOKUP_TABLE.ELEMENTS.value]:
                yield LookupTables(name=name, value=element, bot=bot, user=user)

    def __save_lookup_tables(self, lookup_tables, bot: Text, user: Text):
        if lookup_tables:
            LookupTables.objects.insert(
                list(self.__extract_lookup_tables(lookup_tables, bot, user))
            )

    def fetch_lookup_tables(self, bot: Text, status=True):
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

    def __extract_regex_features(self, regex_features, bot: Text, user: Text):
        for regex_feature in regex_features:
            regex_data = RegexFeatures(**regex_feature)
            regex_data.bot = bot
            regex_data.user = user
            yield regex_data

    def __save_regex_features(self, regex_features, bot: Text, user: Text):
        if regex_features:
            RegexFeatures.objects.insert(
                list(self.__extract_regex_features(regex_features, bot, user))
            )

    def fetch_regex_features(self, bot: Text, status=True):
        regex_features = RegexFeatures.objects(bot=bot, status=status)
        for regex_feature in regex_features:
            yield {
                REGEX_FEATURES.NAME.value: regex_feature["name"],
                REGEX_FEATURES.PATTERN.value: regex_feature["pattern"],
            }

    def __prepare_training_regex_features(self, bot: Text):
        return list(self.fetch_regex_features(bot))

    def __extract_intents(self, intents, bot: Text, user: Text):
        saved_intents = self.__prepare_training_intents(bot)
        for intent in intents:
            if intent not in saved_intents:
                yield Intents(name=intent, bot=bot, user=user)

    def __save_intents(self, intents, bot: Text, user: Text):
        if intents:
            new_intents = list(self.__extract_intents(intents, bot, user))
            if new_intents:
                Intents.objects.insert(new_intents)

    def fetch_intents(self, bot: Text, status=True):
        intents = Intents.objects(bot=bot, status=status).aggregate(
            [{"$group": {"_id": "$bot", "intents": {"$push": "$name"}}}]
        )
        return list(intents)

    def __prepare_training_intents(self, bot: Text):
        intents = self.fetch_intents(bot)
        if intents:
            return intents[0]["intents"]
        else:
            return []

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
        entities = Entities.objects(bot=bot, status=status).aggregate(
            [{"$group": {"_id": "$bot", "entities": {"$push": "$name"}}}]
        )
        return list(entities)

    def __prepare_training_domain_entities(self, bot: Text):
        entities = self.fetch_domain_entities(bot)
        if entities:
            return entities[0]["entities"]
        else:
            return []

    def __extract_forms(self, forms, bot: Text, user: Text):
        saved_forms = self.__prepare_training_forms(bot)
        for form in forms:
            if form not in saved_forms:
                yield Forms(name=form, bot=bot, user=user)

    def __save_forms(self, forms, bot: Text, user: Text):
        if forms:
            new_forms = list(self.__extract_forms(forms, bot, user))
            if new_forms:
                Forms.objects.insert(new_forms)

    def fetch_forms(self, bot: Text, status=True):
        forms = Forms.objects(bot=bot, status=status).aggregate(
            [{"$group": {"_id": "$bot", "forms": {"$push": "$name"}}}]
        )
        return list(forms)

    def __prepare_training_forms(self, bot: Text):
        forms = self.fetch_forms(bot)
        if forms:
            return forms[0]["forms"]
        else:
            return []

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
        actions = Actions.objects(bot=bot, status=status).aggregate(
            [{"$group": {"_id": "$bot", "actions": {"$push": "$name"}}}]
        )
        return list(actions)

    def __prepare_training_actions(self, bot: Text):
        actions = self.fetch_actions(bot)
        if actions:
            return actions[0]["actions"]
        else:
            return []

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
                SessionConfigs.objects.insert(
                    self.__extract_session_config(session_config, bot, user)
                )
        except NotUniqueError as e:
            logging.info(e)
            raise AppException("Session Config already exists for the bot")
        except Exception as e:
            logging.info(e)
            raise AppException("Internal Server Error")

    def fetch_session_config(self, bot: Text):
        try:
            session_config = SessionConfigs.objects.get(bot=bot)
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

    def __extract_response_button(self, buttons):
        for button in buttons:
            yield ResponseButton._from_son(button)

    def __extract_response_value(self, values: List[Dict], key, bot: Text, user: Text):
        for value in values:
            response = Responses()
            response.name = key
            response.bot = bot
            response.user = user
            if RESPONSE.Text.value in value:
                response_text = ResponseText()
                response_text.text = value[RESPONSE.Text.value]
                if RESPONSE.IMAGE.value in value:
                    response_text.image = value[RESPONSE.IMAGE.value]
                if RESPONSE.CHANNEL.value in value:
                    response_text.channel = value["channel"]
                if RESPONSE.BUTTONS.value in value:
                    response_text.buttons = list(
                        self.__extract_response_button(value[RESPONSE.BUTTONS.value])
                    )
                response.text = response_text
            elif RESPONSE.CUSTOM.value in value:
                response.custom = ResponseCustom._from_son(
                    {RESPONSE.CUSTOM.value: value[RESPONSE.CUSTOM.value]}
                )
            yield response

    def __extract_response(self, responses, bot: Text, user: Text):
        responses_result = []
        for key, values in responses.items():
            responses_result.extend(
                list(self.__extract_response_value(values, key, bot, user))
            )
        return responses_result

    def __save_responses(self, responses, bot: Text, user: Text):
        if responses:
            Responses.objects.insert(self.__extract_response(responses, bot, user))

    def __prepare_response_Text(self, texts: List[Dict]):
        for text in texts:
            yield text

    def fetch_responses(self, bot: Text, status=True):
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
            Slots.objects(bot=bot).aggregate(
                [{"$group": {"_id": "$bot", "slots": {"$push": "$name"}}}]
            )
        )
        slots_list = []
        if saved_slots:
            slots_list = saved_slots[0]["slots"]
        return slots_list

    def __extract_slots(self, slots, bot: Text, user: Text):
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

    def fetch_slots(self, bot: Text, status=True):
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
                yield StoryEvents(type=event.type_name, name=event.text)
            elif isinstance(event, ActionExecuted):
                yield StoryEvents(type=event.type_name, name=event.action_name)
            elif isinstance(event, Form):
                yield StoryEvents(type=event.type_name, name=event.name)
            elif isinstance(event, SlotSet):
                yield StoryEvents(
                    type=event.type_name, name=event.key, value=event.value
                )

    def __extract_story_step(self, story_steps, bot: Text, user: Text):
        for story_step in story_steps:
            story_events = list(self.__extract_story_events(story_step.events))
            story = Stories(
                block_name=story_step.block_name,
                start_checkpoints=[
                    start_checkpoint.name
                    for start_checkpoint in story_step.start_checkpoints
                ],
                end_checkpoints=[
                    end_checkpoint.name for end_checkpoint in story_step.end_checkpoints
                ],
                events=story_events,
            )
            story.bot = bot
            story.user = user
            yield story

    def __save_stories(self, story_steps, bot: Text, user: Text):
        if story_steps:
            Stories.objects.insert(
                list(self.__extract_story_step(story_steps, bot, user))
            )

    def __prepare_training_story_events(self, events, timestamp):
        for event in events:
            if event.type == UserUttered.type_name:
                intent = {
                    STORY_EVENT.NAME.value: event.name,
                    STORY_EVENT.CONFIDENCE.value: 1.0,
                }
                yield UserUttered(text=event.name, intent=intent, timestamp=timestamp)
            elif event.type == ActionExecuted.type_name:
                yield ActionExecuted(action_name=event.name, timestamp=timestamp)
            elif event.type == Form.type_name:
                yield Form(name=event.name, timestamp=timestamp)
            elif event.type == SlotSet.type_name:
                yield SlotSet(key=event.name, value=event.value, timestamp=timestamp)

    def fetch_stories(self, bot: Text, status=True):
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

    def __save_config(self, config: dict, bot: Text, user: Text):
        config["bot"] = bot
        config["user"] = user
        Configs.objects.insert(Configs._from_son(config))

    def fetch_configs(self, bot: Text):
        try:
            configs = Configs.objects.get(bot=bot)
        except DoesNotExist as e:
            logging.info(e)
            configs = Configs._from_son(read_config_file("./template/config.yml"))
        return configs

    def load_config(self, bot: Text):
        configs = self.fetch_configs(bot)
        config_dict = configs.to_mongo().to_dict()
        return {
            key: config_dict[key]
            for key in config_dict
            if key in ["language", "pipeline", "policies"]
        }

    def add_intent(self, text: Text, bot: Text, user: Text):
        Utility.is_exist(
            Intents,
            query={"name": text, "bot": bot},
            exp_message="Intent already exists!",
        )
        saved = Intents(name=text, bot=bot, user=user).save().to_mongo().to_dict()
        return saved["_id"].__str__()

    def get_intents(self, bot: Text):
        intents = Intents.objects(bot=bot, status=True)
        return list(self.__prepare_document_list(intents, "name"))

    def add_training_example(
        self, examples: List[Text], intent: Text, bot: Text, user: Text
    ):
        if not Utility.is_exist(
            Intents, query={"name": intent, "bot": bot}, raise_error=False
        ):
            self.add_intent(intent, bot, user)
        for example in examples:
            if Utility.is_exist(
                TrainingExamples, query={"text": example, "bot": bot}, raise_error=False
            ):
                yield {
                    "text": example,
                    "message": "Training Example already exists!",
                    "_id": None,
                }
            else:
                training_example = TrainingExamples(
                    intent=intent, text=example, bot=bot, user=user
                )
                if not Utility.check_empty_string(example):
                    entities = MarkdownReader._find_entities_in_training_example(
                        example
                    )
                    if entities:
                        ext_entity = [ent["entity"] for ent in entities]
                        self.__save_domain_entities(ext_entity, bot=bot, user=user)
                        self.__add_slots_from_entities(ext_entity, bot, user)
                        training_example.text = re.sub(
                            ent_regex, lambda m: m.groupdict()["entity_text"], example
                        )
                        training_example.entities = list(
                            self.__extract_entities(entities)
                        )
                try:
                    saved = training_example.save().to_mongo().to_dict()
                    yield {
                        "text": example,
                        "_id": saved["_id"].__str__(),
                        "message": "Training Example added successfully!",
                    }
                except Exception as e:
                    yield {"text": example, "_id": None, "message": str(e)}

    def get_training_examples(self, intent: Text, bot: Text):
        training_examples = list(
            TrainingExamples.objects(bot=bot, intent=intent, status=True)
        )
        for training_example in training_examples:
            example = training_example.to_mongo().to_dict()
            entities = example["entities"] if "entities" in example else None
            yield {
                "_id": example["_id"].__str__(),
                "text": Utility.prepare_nlu_text(example["text"], entities),
            }

    def get_all_training_examples(self, bot: Text):
        training_examples = list(
            TrainingExamples.objects(bot=bot, status=True).aggregate(
                [{"$group": {"_id": "$bot", "text": {"$push": "$text"}}}]
            )
        )

        if training_examples:
            return training_examples[0]["text"]
        else:
            return []

    def remove_document(self, document: Document, id: Text, bot: Text, user: Text):
        try:
            doc = document.objects(bot=bot).get(id=id)
            doc.update(status=False, user=user)
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

    def add_entity(self, name: Text, bot: Text, user: Text):
        Utility.is_exist(
            Entities,
            query={"name": name, "bot": bot},
            exp_message="Entity already exists!",
        )
        Entities(name=name, bot=bot, user=user).save()
        if not Utility.is_exist(
            Slots, query={"name": name, "bot": bot}, raise_error=False
        ):
            Slots(name=name, type="text", bot=bot, user=user).save()

    def get_entities(self, bot: Text):
        entities = Entities.objects(bot=bot, status=True)
        return list(self.__prepare_document_list(entities, "name"))

    def add_action(self, name: Text, bot: Text, user: Text):
        Utility.is_exist(
            Actions,
            query={"name": name, "bot": bot},
            exp_message="Entity already exists!",
        )
        Actions(name=name, bot=bot, user=user).save()

    def get_actions(self, bot: Text):
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
        return self.add_response(
            utterances={"text": utterance}, name=name, bot=bot, user=user
        )

    def add_response(self, utterances: Dict, name: Text, bot: Text, user: Text):
        self.__check_response_existence(
            response=utterances, bot=bot, exp_message="Response already exists!"
        )
        response = list(
            self.__extract_response_value(
                values=[utterances], key=name, bot=bot, user=user
            )
        )[0]
        value = response.save().to_mongo().to_dict()
        if not Utility.is_exist(
            Actions, query={"name": name, "bot": bot}, raise_error=False
        ):
            Actions(name=name, bot=bot, user=user).save()
        return value["_id"].__str__()

    def get_response(self, name: Text, bot: Text):
        values = Responses.objects(bot=bot, status=True, name=name)
        for value in values:
            val = None
            if value.text:
                val = list(
                    self.__prepare_response_Text([value.text.to_mongo().to_dict()])
                )[0]
            elif value.custom:
                val = value.custom.to_mongo().to_dict()
            yield {"_id": value.id.__str__(), "value": val}

    def __check_response_existence(
        self, response: Dict, bot: Text, exp_message: Text = None, raise_error=True
    ):
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

    ## need to add the logic to add action, slots and forms if it does not exist
    def add_story(self, name: Text, events: List[Dict], bot: Text, user: Text):
        self.__check_event_existence(
            events, bot=bot, exp_message="Story already exists!"
        )
        return (
            Stories(
                block_name=name,
                events=events,
                bot=bot,
                user=user,
                start_checkpoints=[STORY_START],
            )
            .save()
            .to_mongo()
            .to_dict()["_id"]
            .__str__()
        )

    def __check_event_existence(
        self, events: List[Dict], bot: Text, exp_message: Text = None, raise_error=True
    ):
        saved_events = list(
            Stories.objects(bot=bot, status=True).aggregate(
                [{"$group": {"_id": "$name", "events": {"$push": "$events"}}}]
            )
        )

        saved_items = list(
            itertools.chain.from_iterable([items["events"] for items in saved_events])
        )

        if events in saved_items:
            if raise_error:
                if Utility.check_empty_string(exp_message):
                    raise AppException("Exception message cannot be empty")
                raise AppException(exp_message)
            else:
                return True
        else:
            if not raise_error:
                return False

    def get_stories(self, bot: Text):
        for value in Stories.objects(bot=bot, status=True):
            item = value.to_mongo().to_dict()
            item.pop("bot")
            item.pop("user")
            item.pop("timestamp")
            item.pop("status")
            item["_id"] = item["_id"].__str__()
            yield item

    def get_utterance_from_intent(self, intent: Text, bot: Text):
        responses = Responses.objects(bot=bot).distinct(field="name")
        story = Stories.objects(bot=bot, events__name=intent)
        if story:
            for event in story[0].events:
                if event.type == "action" and event.name in responses:
                    return event.name

    def add_session_config(
        self,
        bot: Text,
        user: Text,
        id: Text = None,
        sesssionExpirationTime: int = 60,
        carryOverSlots: bool = True,
    ):
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
        session_config = SessionConfigs.objects().get(bot=bot).to_mongo().to_dict()
        return {
            "_id": session_config["_id"].__str__(),
            "sesssionExpirationTime": session_config["sesssionExpirationTime"],
            "carryOverSlots": session_config["carryOverSlots"],
        }

    def add_endpoints(self, endpoint_config: Dict, bot: Text, user: Text):
        try:
            endpoint = Endpoints.objects().get(bot=bot)
        except DoesNotExist:
            if Endpoints.objects(bot=bot):
                raise AppException("Endpoint Configuration already exists!")
            endpoint = Endpoints()

        endpoint.bot_endpoint = (
            EndPointBot(**endpoint_config.get("bot_endpoint"))
            if endpoint_config.get("bot_endpoint")
            else None
        )
        endpoint.action_endpoint = (
            EndPointAction(**endpoint_config.get("action_endpoint"))
            if endpoint_config.get("action_endpoint")
            else None
        )
        endpoint.tracker_endpoint = (
            EndPointTracker(**endpoint_config.get("tracker_endpoint"))
            if endpoint_config.get("tracker_endpoint")
            else None
        )
        endpoint.bot = bot
        endpoint.user = user
        return endpoint.save().to_mongo().to_dict()["_id"].__str__()

    def get_endpoints(self, bot: Text, raise_exception=True):
        try:
            return Endpoints.objects().get(bot=bot).to_mongo().to_dict()
        except DoesNotExist as e:
            logging.info(e)
            if raise_exception:
                raise AppException("Endpoint Configuration does not exists!")


class AgentProcessor:
    mongo_processor = MongoProcessor()

    @staticmethod
    def get_agent(bot: Text) -> Agent:
        if not InMemoryAgentCache.is_exists(bot):
            AgentProcessor.reload(bot)
        return InMemoryAgentCache.get(bot)

    @staticmethod
    def reload(bot: Text):
        try:
            endpoint = AgentProcessor.mongo_processor.get_endpoints(
                bot, raise_exception=False
            )
            action_endpoint = (
                EndpointConfig(url=endpoint["action_endpoint"]["url"])
                if endpoint and endpoint.get("action_endpoint")
                else None
            )
            model_path = Utility.get_latest_file(
                os.path.join(DEFAULT_MODELS_PATH, bot)
            )
            agent = Agent.load(model_path, action_endpoint=action_endpoint)
            InMemoryAgentCache.set(bot, agent)
        except Exception as e:
            logging.info(e)
            raise AppException("Please train the bot first")

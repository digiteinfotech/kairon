import asyncio
from collections import ChainMap
from typing import Dict

from mongoengine.errors import DoesNotExist
from mongoengine.errors import NotUniqueError
from rasa.core import config
from rasa.core.domain import InvalidDomain
from rasa.core.domain import SessionConfig
from rasa.core.slots import TextSlot, UnfeaturizedSlot, BooleanSlot, ListSlot
from rasa.core.training.structures import StoryGraph, StoryStep
from rasa.importers import utils
from rasa.importers.rasa import Domain, StoryFileReader
from rasa.nlu.training_data import Message, TrainingData
from rasa.utils.io import read_config_file

from .data_objects import *


class MongoProcessor:


    def save_from_path(self, path: str, bot: str, account: int, user: str):
        try:
            nlu_path = path + "/data/nlu.md"
            story_path = path + "/data/stories.md"
            nlu = utils.training_data_from_paths([nlu_path], 'en')
            domain = Domain.from_file(path + '/domain.yml')
            loop = asyncio.new_event_loop()
            story_steps = loop.run_until_complete(StoryFileReader.read_from_file(story_path, domain))
            self.save_nlu(nlu, bot, account, user)
            self.save_domain(domain, bot, account, user)
            self.save_stories(story_steps, bot, account, user)
            self.__save_config(read_config_file(path + '/config.yml'))
        except InvalidDomain as e:
            raise Exception("Failed to validate yaml file. Please make sure the file is correct and all mandatory parameters are specified")
        except Exception as e:
            raise e

    def save_nlu(self, nlu: TrainingData, bot: str, account: int, user: str):
        self.__save_training_examples(nlu.training_examples, bot, account, user)
        self.__save_entity_synonyms(nlu.entity_synonyms, bot, account, user)
        self.__save_lookup_tables(nlu.lookup_tables, bot, account, user)
        self.__save_regex_features(nlu.regex_features, bot, account, user)

    def load_nlu(self, bot: str, account: int) -> TrainingData:
        training_examples = self.__prepare_training_examples(bot, account)
        entity_synonyms = self.__prepare_training_synonyms(bot, account)
        lookup_tables = self.__prepare_training_lookup_tables(bot, account)
        regex_features = self.__prepare_training_regex_features(bot, account)
        return TrainingData( training_examples= training_examples, entity_synonyms=entity_synonyms, lookup_tables= lookup_tables, regex_features= regex_features)

    def save_domain(self, domain: Domain, bot: str, account: int, user: str):
        self.__save_intents(domain.intents, bot, account, user)
        self.__save_domain_entities(domain.entities, bot, account, user)
        self.__save_forms(domain.form_names, bot, account, user)
        self.__save_actions(domain.user_actions, bot, account, user)
        self.__save_responses(domain.templates, bot, account, user)
        self.__save_slots(domain.slots, bot, account, user)

    def load_domain(self, bot: str, account: int) -> Domain:
        domain_dict = {
            'intents': self.__prepare_training_intents(bot, account),
            'actions': self.__prepare_training_actions(bot, account),
            'slots': self.__prepare_training_slots(bot, account),
            'session_config': self.__prepare_training_session_config(bot, account),
            'responses': self.__prepare_training_responses(bot, account),
            'forms': self.__prepare_training_forms(bot , account),
            'entities': self.__prepare_training_domain_entities(bot, account)
        }
        return Domain.from_dict(domain_dict)

    def save_stories(self, story_steps: str, bot: str, account: int, user: str):
        self.__save_stories(story_steps, bot, account, user)

    def load_stories(self, bot: str, account: int) -> StoryGraph:
        return self.__prepare_training_story(bot, account)

    def __save_training_examples(self, training_examples, bot: str, account: int, user: str):
        if training_examples :
            TrainingExamples.objects.insert(list(self.__extract_training_examples(training_examples, bot, account, user)))

    def __extract_entities(self, training_data):
        if "entities" in training_data:
            for entity in training_data['entities']:
                entity_data = Entity(start=entity['start'], end=entity['end'], value=entity['value'],
                                     entity=entity['entity'])
                yield entity_data

    def __extract_training_examples(self, training_examples, bot: str, account: int, user: str):
        for training_example in training_examples:
            training_data = TrainingExamples()
            training_data.intent = training_example.data['intent']
            training_data.text = training_example.text
            training_data.bot = bot
            training_data.account = account
            training_data.user = user
            training_data.entities = list(self.__extract_entities(training_example.data))
            yield training_data

    def __extract_synonyms(self, synonyms, bot: str, account: int, user: str):
        for key, value in synonyms.items():
            yield EntitySynonyms(bot=bot, account=account, synonym=value, value=key, user=user)

    def __save_entity_synonyms(self, entity_synonyms, bot: str, account: int, user: str):
        if entity_synonyms:
            EntitySynonyms.objects.insert(list(self.__extract_synonyms(entity_synonyms, bot, account, user)))

    def fetch_synonyms(self, bot: str, account: int, status = True):
        entitySynonyms = EntitySynonyms.objects(bot= bot, account= account, status= status)
        for entitySynonym in entitySynonyms:
            yield {entitySynonym.value: entitySynonym.synonym}

    def __prepare_training_synonyms(self, bot: str, account: int):
        synonyms = list(self.fetch_synonyms(bot, account))
        return dict(ChainMap(*synonyms))

    def __prepare_entities(self, entities):
        for entity in entities:
            yield entity.to_mongo().to_dict()

    def fetch_training_examples(self, bot: str, account: int, status = True):
        trainingExamples = TrainingExamples.objects(bot= bot, account= account, status= status)
        for trainingExample in trainingExamples:
            message = Message(trainingExample.text)
            message.data = {'intent': trainingExample.intent}
            if trainingExample.entities:
                message.data['entities'] = list(self.__prepare_entities(trainingExample.entities))
            yield message

    def __prepare_training_examples(self, bot: str, account: int):
        return list(self.fetch_training_examples(bot, account))

    def __extract_lookup_tables(self, lookup_tables, bot: str, account: int, user: str):
        for lookup_table in lookup_tables:
            name = lookup_table['name']
            for element in lookup_table['elements']:
                yield LookupTables(name=name, value=element, bot=bot, account=account, user=user)

    def __save_lookup_tables(self, lookup_tables, bot: str, account: int, user: str):
        if lookup_tables:
            LookupTables.objects.insert(list(self.__extract_lookup_tables(lookup_tables, bot, account, user)))

    def fetch_lookup_tables(self, bot: str, account: int, status = True):
        lookup_tables = LookupTables.objects(bot= bot, account= account, status= status).aggregate(
            [{"$group": {"_id": "$name", "elements": {"$push": "$value"}}}])
        for lookup_table in lookup_tables:
            yield {'name': lookup_table['_id'], 'elements': lookup_table['elements']}

    def __prepare_training_lookup_tables(self, bot: str, account: int):
        return list(self.fetch_lookup_tables(bot, account))

    def __extract_regex_features(self, regex_features, bot: str, account: int, user: str):
        for regex_feature in regex_features:
            regex_data = RegexFeatures(**regex_feature)
            regex_data.bot = bot
            regex_data.account = account
            regex_data.user = user
            yield regex_data

    def __save_regex_features(self, regex_features, bot: str, account: int, user: str):
        if regex_features:
            RegexFeatures.objects.insert(list(self.__extract_regex_features(regex_features, bot, account, user)))

    def fetch_regex_features(self, bot: str, account: int, status = True):
        regex_features = RegexFeatures.objects(bot= bot, account= account, status= status)
        for regex_feature in regex_features:
            yield {'name': regex_feature['name'], 'elements': regex_feature['pattern']}

    def __prepare_training_regex_features(self, bot: str, account: int):
        return list(self.fetch_regex_features(bot, account))

    def __extract_intents(self, intents, bot: str, account: int, user: str):
        for intent in intents:
            yield Intents(name=intent, bot=bot, account=account, user=user)

    def __save_intents(self, intents, bot: str, account: int, user: str):
        if intents:
            Intents.objects.insert(list(self.__extract_intents(intents, bot, account, user)))

    def fetch_intents(self, bot: str, account: int, status = True):
        intents = Intents.objects(bot= bot, account= account, status= status).aggregate(
            [{"$group": {"_id": ["$bot", "$account"], "intents": {"$push": "$name"}}}])
        return list(intents)

    def __prepare_training_intents(self, bot: str, account: int):
        intents = self.fetch_intents(bot, account)
        if intents:
            return intents[0]['intents']
        else:
            return []

    def __extract_domain_entities(self, entities, bot: str, account: int, user: str):
        for entity in entities:
            yield Entities(name=entity, bot=bot, account=account, user=user)

    def __save_domain_entities(self, entities, bot: str, account: int, user: str):
        if entities:
            Entities.objects.insert(list(self.__extract_domain_entities(entities, bot, account, user)))

    def fetch_domain_entities(self, bot: str, account: int, status = True):
        entities = Entities.objects(bot= bot, account= account, status= status).aggregate(
            [{"$group": {"_id": ["$bot", "$account"], "entities": {"$push": "$name"}}}])
        return list(entities)

    def __prepare_training_domain_entities(self, bot: str, account: int):
        entities = self.fetch_domain_entities(bot, account)
        if entities:
            return entities[0]['entities']
        else:
            return []

    def __extract_forms(self, forms, bot: str, account: int, user: str):
        for form in forms:
            yield Forms(name=form, bot=bot, account=account, user=user)

    def __save_forms(self, forms, bot: str, account: int, user: str):
        if forms:
            Forms.objects.insert(list(self.__extract_forms(forms, bot, account, user)))

    def fetch_forms(self, bot: str, account: int, status = True):
        forms = Forms.objects(bot= bot, account= account, status= status).aggregate(
            [{"$group": {"_id": ["$bot", "$account"], "forms": {"$push": "$name"}}}])
        return list(forms)

    def __prepare_training_forms(self, bot: str, account: int):
        forms = self.fetch_forms(bot, account)
        if forms:
            return forms[0]['forms']
        else:
            return []

    def __extract_actions(self, actions, bot: str, account: int, user: str):
        for action in actions:
            yield Actions(name=action, bot=bot, account=account, user=user)

    def __save_actions(self, actions, bot: str, account: int, user: str):
        if actions:
            Actions.objects.insert(list(self.__extract_actions(actions, bot, account, user)))

    def fetch_actions(self, bot: str, account: int, status = True):
        actions = Actions.objects(bot= bot, account= account, status= status).aggregate(
            [{"$group": {"_id": ["$bot", "$account"], "actions": {"$push": "$name"}}}])
        return list(actions)

    def __prepare_training_actions(self, bot: str, account: int):
        actions = self.fetch_actions(bot, account)
        if actions:
            return actions[0]['actions']
        else:
            return []

    def __extract_session_config(self, session_config: SessionConfig, bot: str, account: int, user: str):
        return SessionConfigs(sesssionExpirationTime=session_config.session_expiration_time,
                              carryOverSlots=session_config.carry_over_slots, bot=bot, account=account, user=user)

    def __save_session_config(self, session_config: SessionConfigs, bot: str, account: int, user: str):
        try:
            if session_config:
                SessionConfigs.objects.insert(self.__extract_session_config(session_config, bot, account, user))
        except NotUniqueError as e:
            raise Exception("Session Config already exist for the account")
        except Exception as e:
            raise Exception("Internal Server Error")

    def fetch_session_config(self, bot: str, account: int):
        try:
            session_config = SessionConfigs.objects.get(bot=bot, account=account)
        except DoesNotExist as e:
            session_config = None
        return session_config

    def __prepare_training_session_config(self, bot: str, account: int):
        session_config = self.fetch_session_config(bot, account)
        if session_config:
            return { 'session_expiration_time': session_config.sesssionExpirationTime,
                          'carry_over_slots': session_config.carryOverSlots }
        else:
            default_session = SessionConfig.default()
            return {'session_expiration_time': default_session.session_expiration_time,
             'carry_over_slots': default_session.carry_over_slots}

    def __extract_response_button(self, buttons):
        for button in buttons:
            yield ResponseButton._from_son(button)

    def __extract_response_value(self, values):
        texts = []
        customs = []
        for value in values:
            if 'text' in value:
                response_text = ResponseText(text=value['text'])
                if 'image' in value:
                    response_text.image = value['image']
                if 'channel' in value:
                    response_text.channel = value['channel']
                if 'button' in value:
                    response_text.buttons = list(self.__extract_response_button(value['buttons']))
                texts.append(response_text)
            elif 'custom' in value:
                customs.append(ResponseCustom._from_son(value['custom']))
        return (texts, customs)

    def __extract_response(self, responses, bot: str, account: int, user: str):
        for key, value in responses.items():
            response = Responses()
            texts, customs = self.__extract_response_value(value)
            response.name = key
            response.texts = texts
            response.customs = customs
            response.bot = bot
            response.account = account
            response.user = user
            yield response

    def __save_responses(self, responses, bot: str, account: int, user: str):
        if responses:
            Responses.objects.insert(list(self.__extract_response(responses, bot, account, user)))

    def fetch_responses(self, bot: str, account: int, status = True):
        responses = Responses.objects(bot=bot, account=account, status=status)
        for response in responses:
            key = response.name
            value = [text.to_mongo().to_dict() for text in response.texts]
            value.extend([custom.to_mongo().to_dict() for custom in response.customs])
            yield {key: value}

    def __prepare_training_responses(self, bot: str, account: int):
        return dict(ChainMap(*list(self.fetch_responses(bot, account))))

    def __extract_slots(self, slots, bot: str, account: int, user: str):
        for slot in slots:
            items = vars(slot)
            items['type'] = slot.type_name
            items['value_reset_delay'] = items['_value_reset_delay']
            items.pop('_value_reset_delay')
            items['bot'] = bot
            items['account'] = account
            items['user'] = user
            yield Slots._from_son(items)

    def __save_slots(self, slots, bot: str, account: int, user: str):
        if slots:
            Slots.objects.insert(list(self.__extract_slots(slots, bot, account, user)))

    def fetch_slots(self, bot: str, account: int, status = True):
        slots = Slots.objects(bot=bot, account=account, status=status)
        return list(slots)

    def __prepare_training_slots(self, bot: str, account: int):
        slots = self.fetch_slots(bot, account)
        results = []
        for slot in slots:
            if slot.type == FloatSlot.type_name:
                results.append(FloatSlot(name=slot.name, initial_value=slot.initial_value,
                                         value_reset_delay=slot.value_reset_delay, auto_fill=slot.auto_fill,
                                         min_value=slot.min_value, max_value=slot.max_value))
            elif slot.type == CategoricalSlot.type_name:
                results.append(CategoricalSlot(name=slot.name, initial_value=slot.initial_value,
                                               value_reset_delay=slot.value_reset_delay, auto_fill=slot.auto_fill,
                                               values=slot.values))
            elif slot.type == TextSlot.type_name:
                results.append(
                    TextSlot(name=slot.name, initial_value=slot.initial_value, value_reset_delay=slot.value_reset_delay,
                             auto_fill=slot.auto_fill))
            elif slot.type == BooleanSlot.type_name:
                results.append(BooleanSlot(name=slot.name, initial_value=slot.initial_value,
                                           value_reset_delay=slot.value_reset_delay, auto_fill=slot.auto_fill))
            elif slot.type == ListSlot.type_name:
                results.append(
                    ListSlot(name=slot.name, initial_value=slot.initial_value, value_reset_delay=slot.value_reset_delay,
                             auto_fill=slot.auto_fill))
            elif slot.type == UnfeaturizedSlot.type_name:
                results.append(UnfeaturizedSlot(name=slot.name, initial_value=slot.initial_value,
                                                value_reset_delay=slot.value_reset_delay, auto_fill=slot.auto_fill))
        return results

    def __extract_story_events(self, events):
        for event in events:
            if isinstance(event, UserUttered):
                yield StoryEvents(type=event.type_name, name=event.text)
            elif isinstance(event, ActionExecuted):
                yield StoryEvents(type=event.type_name, name=event.action_name)

    def __extract_story_step(self, story_steps, bot: str, account: int, user: str):
        for story_step in story_steps:
            story_events = list(self.__extract_story_events(story_step.events))
            story = Stories(block_name=story_step.block_name, events=story_events)
            story.bot = bot
            story.account = account
            story.user = user
            yield story

    def __save_stories(self, story_steps, bot: str, account: int, user: str):
        if story_steps:
            Stories.objects.insert(list(self.__extract_story_step(story_steps, bot, account, user)))

    def __prepare_training_story_events(self, events, timestamp):
        for event in events:
            if event.type == 'user':
                yield UserUttered(text=event.name, intent={'name': event.name, 'confidence': 1.0}, timestamp=timestamp)
            elif event.type == 'action':
                yield ActionExecuted(action_name=event.name, timestamp=timestamp)

    def fetch_stories(self, bot: str, account: int, status = True):
        return list(Stories.objects(bot=bot, account=account, status=status))

    def __prepare_training_story_step(self, bot: str, account: int):
        for story in Stories.objects(bot=bot, account=account, status=True):
            story_events = list(self.__prepare_training_story_events(story.events, datetime.now()))
            yield StoryStep(block_name=story.block_name, events=story_events)

    def __prepare_training_story(self, bot: str, account: int):
        return StoryGraph(list(self.__prepare_training_story_step(bot, account)))

    def __save_config(self, config: dict, bot: str, account: int, user: str):
        config['account'] = account
        config['bot'] = bot
        config['user'] = user
        Configs.objects.insert(Configs._from_son(config))

    def fetch_configs(self, bot: str, account: int):
        try:
            configs = Configs.objects.get(bot=bot, account=account)
        except DoesNotExist as e:
            configs = Configs._from_son(read_config_file('./template/config.yml'))
        return configs

    def load_config(self, bot: str, account: int):
        configs = self.fetch_configs(bot, account)
        return config.load(configs.to_mongo().to_dict())
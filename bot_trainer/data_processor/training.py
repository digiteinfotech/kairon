from .data_objects import TrainingExamples, Entity, EntitySynonyms, LookupTables, RegexFeatures
from collections import ChainMap
from rasa.nlu.training_data import Message, TrainingData
from rasa.importers import utils

class Processor:

    def save_nlu(self, file, bot, account, user):
        nlu = utils.training_data_from_paths([file], 'en')
        self.__save_training_examples(nlu.training_examples, bot, account, user)
        self.__save_entity_synonyms(nlu.entity_synonyms, bot, account, user)
        self.__save_lookup_tables(nlu.lookup_tables, bot, account, user)
        self.__save_regex_features(nlu.regex_features, bot, account, user)

    def load_nlu(self, bot, account):
        training_examples = self.__prepare_training_examples(bot, account)
        entity_synonyms = self.__prepare_synonyms(bot, account)
        lookup_tables = self.__prepare_lookup_tables(bot, account)
        regex_features = self.__prepare_regex_features(bot, account)
        return TrainingData( training_examples= training_examples, entity_synonyms=entity_synonyms, lookup_tables= lookup_tables, regex_features= regex_features)

    def __save_training_examples(self, training_examples, bot, account, user):
        TrainingExamples.objects.insert(list(self.__extract_training_examples(training_examples, bot, account, user)))

    def __extract_entities(self, training_data):
        if "entities" in training_data:
            for entity in training_data['entities']:
                entity_data = Entity(start=entity['start'], end=entity['end'], value=entity['value'],
                                     entity=entity['entity'])
                yield entity_data

    def __extract_training_examples(self, training_examples, bot, account, user):
        for training_example in training_examples:
            training_data = TrainingExamples()
            training_data.intent = training_example.data['intent']
            training_data.text = training_example.text
            training_data.bot = bot
            training_data.account = account
            training_data.user = user
            training_data.entities = list(self.__extract_entities(training_example.data))
            yield training_data

    def __extract_synonyms(self, synonyms, bot, account, user):
        for key, value in synonyms.items():
            yield EntitySynonyms(bot=bot, account=account, synonym=value, value=key, user=user)

    def __save_entity_synonyms(self, entity_synonyms, bot, account, user):
        EntitySynonyms.objects.insert(list(self.__extract_synonyms(entity_synonyms, bot, account, user)))

    def __fetch_synonyms(self, bot, account):
        entitySynonyms = EntitySynonyms.objects(bot=bot, account=account)
        for entitySynonym in entitySynonyms:
            yield {entitySynonym.value: entitySynonym.synonym}

    def __prepare_synonyms(self, bot, account):
        synonyms = list(self.__fetch_synonyms(bot, account))
        return dict(ChainMap(*synonyms))

    def __prepare_entities(self, entities):
        for entity in entities:
            yield entity.to_mongo().to_dict()

    def __fetch_training_examples(self, bot: str, account: int):
        trainingExamples = TrainingExamples.objects(bot=bot, account=account)
        for trainingExample in trainingExamples:
            message = Message(trainingExample.text)
            message.data = {'intent': trainingExample.intent}
            if trainingExample.entities:
                message.data['entities'] = list(self.__prepare_entities(trainingExample.entities))
            yield message

    def __prepare_training_examples(self, bot: str, account: int):
        return list(self.__fetch_training_examples(bot, account))

    def __extract_lookup_tables(self, lookup_tables, bot, account, user):
        for lookup_table in lookup_tables:
            name = lookup_table['name']
            for element in lookup_table['elements']:
                yield LookupTables(name=name, value=element, bot=bot, account=account, user=user)

    def __save_lookup_tables(self, lookup_tables, bot, account, user):
        LookupTables.objects.insert(list(self.__extract_lookup_tables(lookup_tables, bot, account, user)))

    def __fetch_lookup_tables(self, bot, account):
        lookup_tables = LookupTables.objects(bot=bot, account=account).aggregate(
            [{"$group": {"_id": "$name", "elements": {"$push": "$value"}}}])
        for lookup_table in lookup_tables:
            yield {'name': lookup_table['_id'], 'elements': lookup_table['elements']}

    def __prepare_lookup_tables(self, bot, account):
        return list(self.__fetch_lookup_tables(bot, account))

    def __extract_regex_features(self, regex_features, bot, account, user):
        for regex_feature in regex_features:
            regex_data = RegexFeatures(**regex_feature)
            regex_data.bot = bot
            regex_data.account = account
            regex_data.user = user
            yield regex_data

    def __save_regex_features(self, regex_features, bot, account, user):
        RegexFeatures.objects.insert(list(self.__extract_regex_features(regex_features, bot, account, user)))

    def __fetch_regex_features(self, bot, account):
        regex_features = RegexFeatures.objects(bot=bot, account=account)
        for regex_feature in regex_features:
            yield {'name': regex_feature['name'], 'elements': regex_feature['pattern']}

    def __prepare_regex_features(self, bot, account):
        return list(self.__fetch_regex_features(bot, account))
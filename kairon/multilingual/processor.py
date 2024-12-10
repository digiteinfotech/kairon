from kairon.shared.data.processor import MongoProcessor
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.actions.models import ActionType
from kairon.shared.multilingual.utils.translator import Translator
from rasa.shared.nlu.training_data.training_data import TrainingData
from rasa.shared.core.training_data.structures import StoryGraph
from rasa.shared.importers.rasa import Domain
from kairon.shared.account.data_objects import Bot
from loguru import logger
import re
from ..exceptions import AppException
from ..shared.data.action_serializer import ActionSerializer
from ..shared.data.utils import DataUtility


class MultilingualTranslator:

    """class contains logic for creating a bot by translating a base bot into another language"""

    def __init__(self, account: int, user: str):
        """
        init for Multilingual Processor
        :param account: account id
        :param user: username
        """
        self.mp = MongoProcessor()
        self.account = account
        self.user = user

    @staticmethod
    def __translate_domain(domain: Domain, s_lang: str, d_lang: str):
        """
        loads domain from base bot and translates it to source language
        :return: domain: translated domain file
        """

        # Unpack responses
        utter_list = []
        utter_save_list = []
        index = 0
        for key, response in domain.responses.items():
            utter_save = {'utter_name': key}
            for i, utter in enumerate(response):
                if utter.get('text'):
                    utter_save['text'] = utter['text']
                    utter_save['translated_index'] = index
                    utter_save['source_index'] = i
                    index += 1
                    utter_list.append(utter['text'])
                    utter_save_list.append(utter_save.copy())
        if utter_list:
            utter_translations = Translator.translate_text_bulk(text=utter_list, s_lang=s_lang, d_lang=d_lang)

            for utter_save in utter_save_list:
                domain.responses[utter_save['utter_name']][utter_save['source_index']]['text'] = str(utter_translations[utter_save['translated_index']])
        else:
            logger.info("Utterances empty.")

        return domain

    @staticmethod
    def __translate_training_data(training_data: TrainingData, s_lang: str, d_lang: str):
        """
        loads nlu from base bot and translates it to destination language
        :return: training_data: translated training data
        """

        # Unpack training examples
        examples_list = []
        for example in training_data.training_examples:
            text = example.data.get('text')
            if text:
                examples_list.append(text)

        if examples_list:
            examples_translations = Translator.translate_text_bulk(text=examples_list, s_lang=s_lang, d_lang=d_lang)

            # Assuming the list of training examples is always ordered
            for i, example in enumerate(training_data.training_examples):

                example.data['text'] = str(examples_translations[i])
                if example.data.get('entities'):
                    del example.data['entities']
        else:
            logger.info("Training examples empty.")

        return training_data

    @staticmethod
    def __translate_actions(action_config: dict, s_lang: str, d_lang: str):
        """
        loads action configurations and translates the responses to destination language
        :param s_lang: source language
        :param d_lang: destination language
        :return: actions: action config dictionary
        """

        def translate_responses(actions: list, field_names: list = None):
            if field_names is None:
                field_names = ['response']
            for field in field_names:
                if actions:
                    action_list = []
                    for action in actions:
                        action_list.append(action[field])

                    if action_list:
                        translated_action = Translator.translate_text_bulk(text=action_list,
                                                                           s_lang=s_lang, d_lang=d_lang)
                        for i, action in enumerate(actions):
                            action[field] = str(translated_action[i])

            return actions

        def translate_responses_for_http_actions(actions: list):
            if actions:
                action_list = []
                for action in actions:
                    action_list.append(action['response'].get('value'))

                if action_list:
                    translated_action = Translator.translate_text_bulk(text=action_list,
                                                                       s_lang=s_lang, d_lang=d_lang)
                    for i, action in enumerate(actions):
                        action['response']['value'] = str(translated_action[i])

            return actions
        if action_config.get(ActionType.http_action.value):
            action_config[ActionType.http_action.value] = translate_responses_for_http_actions(
            action_config[ActionType.http_action.value])
        if action_config.get(ActionType.email_action.value):
            action_config[ActionType.email_action.value] = translate_responses(action_config[ActionType.email_action.value])
        if action_config.get(ActionType.jira_action.value):
            action_config[ActionType.jira_action.value] = translate_responses(action_config[ActionType.jira_action.value])
        if action_config.get(ActionType.zendesk_action.value):
            action_config[ActionType.zendesk_action.value] = translate_responses(action_config[ActionType.zendesk_action.value])
        if action_config.get(ActionType.pipedrive_leads_action.value):
            action_config[ActionType.pipedrive_leads_action.value] = translate_responses(
            action_config[ActionType.pipedrive_leads_action.value])
        if action_config.get(ActionType.google_search_action.value):
            action_config[ActionType.google_search_action.value] = translate_responses(
                action_config[ActionType.google_search_action.value], ['failure_response'])
        if action_config.get(ActionType.form_validation_action.value):
            action_config[ActionType.form_validation_action.value] = translate_responses(
                action_config[ActionType.form_validation_action.value], ['valid_response', 'invalid_response'])

        return action_config

    def __save_bot_files(self, new_bot_id: str, nlu: TrainingData, domain: Domain, actions: dict, configs: dict,
                         stories: StoryGraph, rules: StoryGraph, other_collections: dict = None):
        """
        Saving translated bot files into new bot
        :param new_bot_id: id of new bot
        :param domain: translated domain
        :param nlu: translated nlu
        :return: None
        """
        self.mp.delete_domain(bot=new_bot_id, user=self.user)
        ActionSerializer.deserialize(bot=new_bot_id,
                                     user=self.user,
                                     actions = actions,
                                     other_collections_data=other_collections,
                                     overwrite=True)
        self.mp.save_domain(domain=domain, bot=new_bot_id, user=self.user)
        self.mp.save_nlu(nlu=nlu, bot=new_bot_id, user=self.user)
        self.mp.save_config(configs=configs, bot=new_bot_id, user=self.user)
        self.mp.save_stories(story_steps=stories, bot=new_bot_id, user=self.user)
        self.mp.save_rules(story_steps=rules, bot=new_bot_id, user=self.user)

    @staticmethod
    def __get_new_bot_name(base_bot_name: str, d_lang: str):
        name = base_bot_name+'_'+d_lang
        regex = re.compile(f"{name}.*")
        record_count = Bot.objects(name=regex).count()
        if record_count:
            name = name + '_' + str(record_count)

        return name

    def create_multilingual_bot(self, base_bot_id: str, base_bot_name: str, s_lang: str, d_lang: str,
                                translate_responses: bool = True, translate_actions: bool = False):
        """
        Function to translate the base bot files and create a new bot
        :param base_bot_id: id of base bot
        :param base_bot_name: name of base bot
        :param s_lang: language of base bot
        :param d_lang: language of translated bot
        :param translate_actions:
        :param translate_responses:
        :return: new_bot_id: bot id of translated bot
        """
        bot_created = False
        new_bot_id = None

        try:

            nlu = self.mp.load_nlu(bot=base_bot_id)
            domain = self.mp.load_domain(bot=base_bot_id)
            actions, other_collections = ActionSerializer.serialize(bot=base_bot_id)
            configs = self.mp.load_config(bot=base_bot_id)
            stories = self.mp.load_stories(bot=base_bot_id).story_steps
            rules = self.mp.get_rules_for_training(bot=base_bot_id).story_steps

            name = self.__get_new_bot_name(base_bot_name, d_lang)

            metadata = {
                'source_language': s_lang,
                'language': d_lang,
                'source_bot_id': base_bot_id
                }

            nlu = self.__translate_training_data(training_data=nlu, s_lang=s_lang, d_lang=d_lang)
            logger.info("Translated training data successfully.")

            if translate_responses:
                domain = self.__translate_domain(domain=domain, s_lang=s_lang, d_lang=d_lang)
                logger.info("Translated responses successfully.")

            if translate_actions:
                actions = self.__translate_actions(action_config=actions, s_lang=s_lang, d_lang=d_lang)
                logger.info("Translated actions successfully.")

            logger.info("Translated bot files successfully.")

            new_bot = AccountProcessor.add_bot(name=name, account=self.account, user=self.user, add_default_data=False, metadata=metadata)
            new_bot_id = new_bot['_id'].__str__()
            bot_created = True
            logger.info(f"Created new bot with bot_id: {str(new_bot_id)}")

            self.__save_bot_files(new_bot_id=new_bot_id, nlu=nlu, domain=domain, actions=actions, configs=configs,
                                  stories=stories, rules=rules, other_collections=other_collections)
            logger.info("Saved translated bot files successfully.")

        except Exception as e:
            if bot_created:
                AccountProcessor.delete_bot(bot=new_bot_id)
                logger.info(f"New bot deleted. Bot id: {str(new_bot_id)}")
            logger.exception(f"Could not create multilingual bot due to exception: {str(e)}")
            raise AppException(f"Could not create multilingual bot due to exception: {str(e)}")

        return new_bot_id

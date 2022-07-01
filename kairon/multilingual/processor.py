from kairon.shared.data.processor import MongoProcessor
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.actions.models import ActionType
from kairon.shared.multilingual.utils.translator import Translator
from rasa.shared.nlu.training_data.training_data import TrainingData
from rasa.shared.importers.rasa import Domain
from loguru import logger

from ..exceptions import AppException


class MultilingualProcessor:
    """
    class contains logic for creating a bot by translating a base bot into another language
    """

    def __init__(self, account: int, user: str):
        """
        :param account: account id
        :param user: username
        """
        self.mp = MongoProcessor()
        self.account = account
        self.user = user

    def __translate_domain(self, base_bot_id: str, s_lang: str, d_lang: str):
        """
        loads domain from base bot and translates it to source language
        :param base_bot_id: id of base bot
        :return: domain: translated domain file
        """
        domain = self.mp.load_domain(bot=base_bot_id)

        # Unpack responses
        utter_list = []
        utter_save_list = []
        index = 0
        for key, response in domain.responses.items():
            utter_save = {'utter_name': key}
            for i, utter in enumerate(response):
                if utter.get('text'):
                    utter_save['text'] = utter['text']
                    utter_save['index'] = index
                    utter_save['i'] = i
                    index += 1
                    utter_list.append(utter['text'])
                    utter_save_list.append(utter_save.copy())
        if utter_list:
            utter_translations = Translator.translate_text_bulk(text=utter_list, s_lang=s_lang, d_lang=d_lang)

            for utter_save in utter_save_list:
                domain.responses[utter_save['utter_name']][utter_save['i']]['text'] = str(utter_translations[utter_save['index']])
        else:
            logger.info("Utterances empty.")

        return domain

    def __translate_training_data(self, base_bot_id: str, s_lang: str, d_lang: str):
        """
        loads nlu from base bot and translates it to destination language
        :param base_bot_id: id of base bot
        :return: training_data: translated training data
        """
        training_data = self.mp.load_nlu(bot=base_bot_id)

        # Unpack training examples
        examples_list = []
        for example in training_data.training_examples:
            text = example.data.get('text')
            if text:
                examples_list.append(text)

        if examples_list:
            examples_translations = Translator.translate_text_bulk(text=examples_list, s_lang=s_lang, d_lang=d_lang)

            for i, example in enumerate(training_data.training_examples):
                example.data['text'] = str(examples_translations[i])
        else:
            logger.info("Training examples empty.")

        return training_data

    def __translate_actions(self, base_bot_id: str, s_lang: str, d_lang: str):
        """
        loads action configurations and translates the responses to destination language
        :param base_bot_id: id of base bot
        :param s_lang: source language
        :param d_lang: destination language
        :return: actions: action config dictionary
        """
        action_config = self.mp.load_action_configurations(bot=base_bot_id)

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

        action_config[ActionType.http_action] = translate_responses_for_http_actions(
            action_config[ActionType.http_action])
        action_config[ActionType.email_action] = translate_responses(action_config[ActionType.email_action])
        action_config[ActionType.jira_action] = translate_responses(action_config[ActionType.jira_action])
        action_config[ActionType.zendesk_action] = translate_responses(action_config[ActionType.zendesk_action])
        action_config[ActionType.pipedrive_leads_action] = translate_responses(
            action_config[ActionType.pipedrive_leads_action])
        action_config[ActionType.google_search_action] = translate_responses(
            action_config[ActionType.google_search_action], ['failure_response'])
        action_config[ActionType.form_validation_action] = translate_responses(
            action_config[ActionType.form_validation_action], ['valid_response', 'invalid_response'])

        return action_config

    def __save_bot_files(self, base_bot_id: str, new_bot_id: str, nlu: TrainingData,
                         domain: Domain = None, actions: dict = None):
        """
        Saving translated bot files into new bot
        :param base_bot_id: id of base bot
        :param new_bot_id: id of new bot
        :param domain: translated domain
        :param nlu: translated nlu
        :return: None
        """
        try:
            self.mp.delete_domain(bot=new_bot_id, user=self.user)
            if domain:
                self.mp.save_domain(domain=domain, bot=new_bot_id, user=self.user)
            else:
                self.mp.save_domain(domain=self.mp.load_domain(bot=base_bot_id), bot=new_bot_id, user=self.user)

            if actions:
                self.mp.save_integrated_actions(actions=actions, bot=new_bot_id, user=self.user)
            else:
                self.mp.save_integrated_actions(actions=self.mp.load_action_configurations(bot=base_bot_id),
                                                bot=new_bot_id, user=self.user)

            self.mp.save_nlu(nlu=nlu, bot=new_bot_id, user=self.user)
            self.mp.save_config(configs=self.mp.load_config(bot=base_bot_id), bot=new_bot_id, user=self.user)
            self.mp.save_stories(story_steps=self.mp.load_stories(bot=base_bot_id).story_steps,
                                 bot=new_bot_id, user=self.user)
            self.mp.save_rules(story_steps=self.mp.get_rules_for_training(bot=base_bot_id).story_steps,
                               bot=new_bot_id, user=self.user)
        except Exception as e:
            logger.exception(e)
            raise Exception(f"Saving bot files failed with exception: {str(e)}")

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
        domain = None
        actions = None

        try:
            name = base_bot_name+'_'+d_lang
            count = 0
            while AccountProcessor.check_bot_exists(name=name, account=self.account, raise_exception=False):
                count += 1
                name = base_bot_name+'_'+d_lang+'_'+str(count)

            metadata = {
                'source_language': s_lang,
                'language': d_lang,
                'source_bot_id': base_bot_id
                }

            new_bot = AccountProcessor.add_bot(name=name, account=self.account, user=self.user, metadata=metadata)
            new_bot_id = new_bot['_id'].__str__()
            bot_created = True
            logger.info(f"Created new bot with bot_id: {str(new_bot_id)}")

            nlu = self.__translate_training_data(base_bot_id=base_bot_id, s_lang=s_lang, d_lang=d_lang)
            logger.info("Translated training data successfully.")

            if translate_responses:
                domain = self.__translate_domain(base_bot_id=base_bot_id, s_lang=s_lang, d_lang=d_lang)
                logger.info("Translated responses successfully.")

            if translate_actions:
                actions = self.__translate_actions(base_bot_id=base_bot_id, s_lang=s_lang, d_lang=d_lang)
                logger.info("Translated actions successfully.")

            logger.info(f"Translated bot files successfully.")

            self.__save_bot_files(base_bot_id, new_bot_id, nlu, domain, actions)
            logger.info(f"Saved translated bot files successfully.")

        except Exception as e:
            if bot_created:
                AccountProcessor.delete_bot(bot=new_bot_id)
                logger.info(f"New bot deleted. Bot id: {str(new_bot_id)}")
            logger.exception(f"Could not create multilingual bot due to exception: {str(e)}")
            raise AppException(f"Could not create multilingual bot due to exception: {str(e)}")

        return new_bot_id

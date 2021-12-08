import os
import shutil
import tempfile
from itertools import chain
from typing import Text, List, Dict
import uuid
import requests
from fastapi import File
from fastapi.background import BackgroundTasks
from fastapi.security import OAuth2PasswordBearer
from loguru import logger
from mongoengine.errors import ValidationError
from rasa.shared.constants import DEFAULT_DATA_PATH
from rasa.shared.nlu.constants import TEXT
from rasa.shared.nlu.training_data import entities_parser
from rasa.shared.nlu.training_data.formats.markdown import MarkdownReader

from .constant import ALLOWED_NLU_FORMATS, ALLOWED_STORIES_FORMATS, \
    ALLOWED_DOMAIN_FORMATS, ALLOWED_CONFIG_FORMATS, EVENT_STATUS, ALLOWED_RULES_FORMATS, ALLOWED_HTTP_ACTIONS_FORMATS, \
    REQUIREMENTS
from .constant import RESPONSE
from .training_data_generation_processor import TrainingDataGenerationProcessor
from ...api.models import HttpActionParametersResponse, HttpActionConfigResponse
from ...exceptions import AppException
from ...shared.actions.data_objects import HttpActionConfig
from ...shared.models import StoryStepType
from ...shared.utils import Utility


class DataUtility:
    """Class contains logic for various utilities"""

    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
    oauth2_scheme_non_strict = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)
    markdown_reader = MarkdownReader()

    @staticmethod
    def prepare_nlu_text(example: Text, entities: List[Dict]):
        """
        combines plain text and entities into training example format

        :param example: training example plain text
        :param entities: list of entities
        :return: trianing example combine with enities
        """
        if not Utility.check_empty_string(example):
            if entities:
                from rasa.shared.nlu.training_data.formats.rasa_yaml import RasaYAMLWriter
                example = RasaYAMLWriter.generate_message({'text': example, "entities": entities})
        return example

    @staticmethod
    async def save_uploaded_data(bot: Text, training_files: [File]):
        if not training_files:
            raise AppException("No files received!")

        if training_files[0].filename.endswith('.zip'):
            bot_data_home_dir = await DataUtility.save_training_files_as_zip(bot, training_files[0])
        else:
            bot_data_home_dir = os.path.join('training_data', bot, str(uuid.uuid4()))
            data_path = os.path.join(bot_data_home_dir, DEFAULT_DATA_PATH)
            Utility.make_dirs(data_path)

            for file in training_files:
                if file.filename in ALLOWED_NLU_FORMATS.union(ALLOWED_STORIES_FORMATS).union(ALLOWED_RULES_FORMATS):
                    path = os.path.join(data_path, file.filename)
                    Utility.write_to_file(path, await file.read())
                elif file.filename in ALLOWED_CONFIG_FORMATS.union(ALLOWED_DOMAIN_FORMATS).union(
                        ALLOWED_HTTP_ACTIONS_FORMATS):
                    path = os.path.join(bot_data_home_dir, file.filename)
                    Utility.write_to_file(path, await file.read())

        return bot_data_home_dir

    @staticmethod
    async def save_training_files_as_zip(bot: Text, training_file: File):
        tmp_dir = tempfile.mkdtemp()
        try:
            zipped_file = os.path.join(tmp_dir, training_file.filename)
            Utility.write_to_file(zipped_file, await training_file.read())
            unzip_path = os.path.join('training_data', bot, str(uuid.uuid4()))
            shutil.unpack_archive(zipped_file, unzip_path, 'zip')
            return unzip_path
        except Exception as e:
            logger.error(e)
            raise AppException("Invalid zip")
        finally:
            Utility.delete_directory(tmp_dir)

    @staticmethod
    def validate_and_get_requirements(bot_data_home_dir: Text, delete_dir_on_exception: bool = False):
        """
        Checks whether at least one of the required files are present and
        finds other files required for validation during import.
        @param bot_data_home_dir: path where data exists
        @param delete_dir_on_exception: whether directory needs to be deleted in case of exception.
        """
        requirements = set()
        data_path = os.path.join(bot_data_home_dir, DEFAULT_DATA_PATH)

        if not os.path.exists(bot_data_home_dir):
            raise AppException("Bot data home directory not found")

        files_received = set(os.listdir(bot_data_home_dir))
        if os.path.exists(data_path):
            files_received = files_received.union(os.listdir(data_path))

        if ALLOWED_NLU_FORMATS.intersection(files_received).__len__() < 1:
            requirements.add('nlu')
        if ALLOWED_STORIES_FORMATS.intersection(files_received).__len__() < 1:
            requirements.add('stories')
        if ALLOWED_DOMAIN_FORMATS.intersection(files_received).__len__() < 1:
            requirements.add('domain')
        if ALLOWED_CONFIG_FORMATS.intersection(files_received).__len__() < 1:
            requirements.add('config')
        if ALLOWED_RULES_FORMATS.intersection(files_received).__len__() < 1:
            requirements.add('rules')
        if ALLOWED_HTTP_ACTIONS_FORMATS.intersection(files_received).__len__() < 1:
            requirements.add('http_actions')

        if requirements == REQUIREMENTS:
            if delete_dir_on_exception:
                Utility.delete_directory(bot_data_home_dir)
            raise AppException('Invalid files received')
        return requirements

    @staticmethod
    async def save_training_files(nlu: File, domain: File, config: File, stories: File, rules: File = None,
                                  http_action: File = None):
        """
        convert mongo data  to individual files

        :param nlu: nlu data
        :param domain: domain data
        :param stories: stories data
        :param config: config data
        :param rules: rules data
        :param http_action: http actions data
        :return: files path
        """
        training_file_loc = {}
        tmp_dir = tempfile.mkdtemp()
        data_path = os.path.join(tmp_dir, DEFAULT_DATA_PATH)
        os.makedirs(data_path)

        nlu_path = os.path.join(data_path, nlu.filename)
        domain_path = os.path.join(tmp_dir, domain.filename)
        stories_path = os.path.join(data_path, stories.filename)
        config_path = os.path.join(tmp_dir, config.filename)

        Utility.write_to_file(nlu_path, await nlu.read())
        Utility.write_to_file(domain_path, await domain.read())
        Utility.write_to_file(stories_path, await stories.read())
        Utility.write_to_file(config_path, await config.read())

        training_file_loc['rules'] = await DataUtility.write_rule_data(data_path, rules)
        training_file_loc['http_action'] = await DataUtility.write_http_data(tmp_dir, http_action)
        training_file_loc['nlu'] = nlu_path
        training_file_loc['config'] = config_path
        training_file_loc['stories'] = stories_path
        training_file_loc['domain'] = domain_path
        training_file_loc['root'] = tmp_dir
        return training_file_loc

    @staticmethod
    async def write_rule_data(data_path: str, rules: File = None):
        """
        writes the rule data to file and returns the file path

        :param data_path: path of the data files
        :param rules: rules data
        :return: rule file path
        """
        if rules and rules.filename:
            rules_path = os.path.join(data_path, rules.filename)
            Utility.write_to_file(rules_path, await rules.read())
            return rules_path
        else:
            return None

    @staticmethod
    async def write_http_data(temp_path: str, http_action: File = None):
        """
       writes the http_actions data to file and returns the file path

       :param temp_path: path of the temporary directory
       :param http_action: http_action data
       :return: http_action file path
       """
        if http_action and http_action.filename:
            http_path = os.path.join(temp_path, http_action.filename)
            Utility.write_to_file(http_path, await http_action.read())
            return http_path
        else:
            return None

    @staticmethod
    def extract_text_and_entities(text: Text):
        """
        extract entities and plain text from markdown intent example

        :param text: markdown intent example
        :return: plain intent, list of extracted entities
        """
        example = entities_parser.parse_training_example(text)
        return example.get(TEXT), example.get('entities', None)

    @staticmethod
    def __extract_response_button(buttons: Dict):
        """
        used to prepare ResponseButton by extracting buttons configuration from bot utterance

        :param buttons: button configuration in bot response
        :return: yields ResponseButton
        """
        from .data_objects import ResponseButton

        for button in buttons:
            yield ResponseButton._from_son(button)

    @staticmethod
    def prepare_response(value: Dict):
        """
        used to prepare bot utterance either Text or Custom for saving in Mongo

        :param value: utterance value
        :return: response type, response object
        """
        from .data_objects import ResponseText, ResponseCustom
        if RESPONSE.Text.value in value:
            response_text = ResponseText()
            response_text.text = str(value[RESPONSE.Text.value]).strip()
            if RESPONSE.IMAGE.value in value:
                response_text.image = value[RESPONSE.IMAGE.value]
            if RESPONSE.CHANNEL.value in value:
                response_text.channel = value["channel"]
            if RESPONSE.BUTTONS.value in value:
                response_text.buttons = list(
                    DataUtility.__extract_response_button(value[RESPONSE.BUTTONS.value])
                )
            data = response_text
            response_type = "text"
        elif RESPONSE.CUSTOM.value in value:
            data = ResponseCustom._from_son(
                {RESPONSE.CUSTOM.value: value[RESPONSE.CUSTOM.value]}
            )
            response_type = "custom"
        else:
            response_type = None
            data = None
        return response_type, data

    @staticmethod
    def get_rasa_core_policies():
        from rasa.core.policies import registry
        return list(Utility.get_imports(registry.__file__))

    @staticmethod
    def build_http_response_object(http_action_config: HttpActionConfig, user: str, bot: str):
        """
        Builds a new HttpActionConfigResponse object from HttpActionConfig object.
        :param http_action_config: HttpActionConfig object containing configuration for the Http action
        :param user: user id
        :param bot: bot id
        :return: HttpActionConfigResponse containing configuration for Http action
        """
        http_params = [
            HttpActionParametersResponse(key=param.key, value=param.value, parameter_type=param.parameter_type)
            for param in
            http_action_config.params_list]
        response = HttpActionConfigResponse(
            auth_token=http_action_config.auth_token,
            action_name=http_action_config.action_name,
            response=http_action_config.response,
            http_url=http_action_config.http_url,
            request_method=http_action_config.request_method,
            params_list=http_params,
            user=user,
            bot=bot
        )
        return response

    @staticmethod
    def trigger_data_generation_event(bot: str, user: str, token: str):
        try:
            event_url = Utility.environment['data_generation']['event_url']
            logger.info("Training data generator event started")
            response = requests.post(event_url, headers={'content-type': 'application/json'},
                                     json={'user': user, 'token': token})
            logger.info("Training data generator event completed" + response.content.decode('utf8'))
        except Exception as e:
            logger.error(str(e))
            TrainingDataGenerationProcessor.set_status(bot=bot,
                                                       user=user,
                                                       status=EVENT_STATUS.FAIL.value,
                                                       exception=str(e))

    @staticmethod
    def get_interpreter(model_path):
        from rasa.model import get_model, get_model_subdirectories
        from rasa.core.interpreter import create_interpreter
        try:
            with get_model(model_path) as unpacked_model:
                _, nlu_model = get_model_subdirectories(unpacked_model)
                _interpreter = create_interpreter(
                    nlu_model
                )
        except Exception:
            logger.debug(f"Could not load interpreter from '{model_path}'.")
            _interpreter = None
        return _interpreter

    @staticmethod
    def train_model(background_tasks: BackgroundTasks, bot: Text, user: Text, email: Text, process_type: Text):
        """
        train model common code when uploading files or training a model
        :param background_tasks: fast api background task
        :param bot: bot id
        :param user: user id
        :param email: user email for generating token for reload
        :param process_type: either upload or train
        """
        from ...shared.data.model_processor import ModelProcessor
        from ...shared.auth import Authentication
        from ...shared.data.constant import MODEL_TRAINING_STATUS
        from ...train import start_training
        exception = process_type != 'upload'
        ModelProcessor.is_training_inprogress(bot, raise_exception=exception)
        ModelProcessor.is_daily_training_limit_exceeded(bot, raise_exception=exception)
        ModelProcessor.set_training_status(
            bot=bot, user=user, status=MODEL_TRAINING_STATUS.INPROGRESS.value,
        )
        token = Authentication.create_access_token(data={"sub": email}, token_expire=180)
        background_tasks.add_task(
            start_training, bot, user, token
        )

    @staticmethod
    def validate_flow_events(events, type, name):
        from rasa.shared.core.constants import RULE_SNIPPET_ACTION_NAME
        Utility.validate_document_list(events)
        if type == "STORY" and events[0].type != "user":
            raise ValidationError("First event should be an user")

        if type == "RULE":
            if events[0].name == RULE_SNIPPET_ACTION_NAME and events[0].type == "action":
                if events[1].type != "user":
                    raise ValidationError('First event should be an user or conversation_start action')
            else:
                if events[0].type != "user":
                    raise ValidationError('First event should be an user or conversation_start action')

        if events[len(events) - 1].type == "user":
            raise ValidationError("user event should be followed by action")

        intents = 0
        for i, j in enumerate(range(1, len(events))):
            if events[i].type == "user":
                intents = intents + 1
            if events[i].type == "user" and events[j].type == "user":
                raise ValidationError("Found 2 consecutive user events")
            if type == "RULE" and intents > 1:
                raise ValidationError(
                    f"""Found rules '{name}' that contain more than user event.\nPlease use stories for this case""")

    @staticmethod
    def load_fallback_actions(bot: Text):
        from .processor import MongoProcessor

        mongo_processor = MongoProcessor()
        config = mongo_processor.load_config(bot)
        fallback_action = DataUtility.parse_fallback_action(config)
        nlu_fallback_action = MongoProcessor.fetch_nlu_fallback_action(bot)
        return fallback_action, nlu_fallback_action

    @staticmethod
    def parse_fallback_action(config: Dict):
        fallback_action = "action_default_fallback"
        action_fallback = next((comp for comp in config['policies'] if comp["name"] == "RulePolicy"), None)
        if action_fallback:
            fallback_action = action_fallback.get("core_fallback_action_name", fallback_action)
        return fallback_action

    @staticmethod
    def load_default_actions():
        from kairon.importer.validator.file_validator import DEFAULT_ACTIONS

        return list(DEFAULT_ACTIONS - {"action_default_fallback", "action_two_stage_fallback"})

    @staticmethod
    def get_template_type(story: Dict):
        steps = story['steps']
        if len(steps) == 2 and steps[0]['type'] == StoryStepType.intent and steps[1]['type'] == StoryStepType.bot:
            template_type = 'Q&A'
        else:
            template_type = 'CUSTOM'
        return template_type

    @staticmethod
    def augment_sentences(sentences: list, stopwords: list = None, num_variations: int = 5):
        from nlpaug.augmenter.char import KeyboardAug
        from nlpaug.augmenter.word import SynonymAug
        from nlpaug.flow import Sometimes
        from nlpaug.augmenter.word import SpellingAug
        from nlpaug.augmenter.word import AntonymAug

        keyboard_aug = KeyboardAug(aug_char_min=1, aug_char_max=10, aug_char_p=0.3, aug_word_p=0.3,
                                   aug_word_min=1, aug_word_max=10, stopwords=stopwords,
                                   include_special_char=False, include_numeric=False, include_upper_case=True,
                                   lang='en',
                                   min_char=4)
        synonym_aug = SynonymAug(aug_src='wordnet', aug_min=1, aug_max=4,
                                 aug_p=0.3, stopwords=stopwords,
                                 lang='eng')
        antonym_aug = AntonymAug(aug_min=1, aug_max=10, aug_p=0.3, stopwords=stopwords, lang='eng')
        spelling_aug = SpellingAug(aug_min=1, aug_max=10, aug_p=0.3, stopwords=stopwords, include_reverse=False)

        aug = Sometimes([keyboard_aug, synonym_aug, spelling_aug, antonym_aug], aug_p=0.25)
        augmented_text = aug.augment(sentences, n=num_variations)
        return set(chain.from_iterable(augmented_text))

    @staticmethod
    def generate_synonym(entity: str, num_variations: int = 3):
        from nltk.corpus import wordnet

        synonyms = []
        syn_sets = wordnet.synsets(entity)
        for syn in syn_sets:
            for word in syn.lemma_names():
                if word != entity:
                    synonyms.append(word)
                    num_variations -= 1
                if num_variations <= 0:
                    return synonyms
        return synonyms


class ChatHistoryUtils:

    @staticmethod
    def unique_user_input(month, current_user_bot):
        from ...shared.data.processor import MongoProcessor
        response = Utility.trigger_history_server_request(
            current_user_bot,
            f'/api/history/{current_user_bot}/metrics/users/input',
            {'month': month}
        )

        user_input = response['data']
        processor = MongoProcessor()
        training_examples = processor.get_all_training_examples(bot=current_user_bot)
        queries_not_present = [query for query in user_input if query['_id'] not in training_examples[0]]
        return queries_not_present

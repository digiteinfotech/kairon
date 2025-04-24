import os
import shutil
import tempfile
import uuid
from typing import Text, List, Dict
from urllib.parse import urljoin

import pandas as pd
from fastapi import File
from fastapi.security import OAuth2PasswordBearer
from loguru import logger
from mongoengine.errors import ValidationError
from pandas import DataFrame
from rasa.shared.core.training_data.structures import RuleStep

from .constant import ALLOWED_NLU_FORMATS, ALLOWED_STORIES_FORMATS, \
    ALLOWED_DOMAIN_FORMATS, ALLOWED_CONFIG_FORMATS, ALLOWED_RULES_FORMATS, ALLOWED_ACTIONS_FORMATS, \
    REQUIREMENTS, ACCESS_ROLES, TOKEN_TYPE, ALLOWED_CHAT_CLIENT_CONFIG_FORMATS, ALLOWED_MULTIFLOW_STORIES_FORMATS, \
    ALLOWED_BOT_CONTENT_FORMATS
from .constant import RESPONSE
from .data_objects import MultiflowStories
from ...exceptions import AppException
from ...shared.models import StoryStepType
from ...shared.utils import Utility


class DataUtility:
    """Class contains logic for various utilities"""

    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
    oauth2_scheme_non_strict = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

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
        from rasa.shared.constants import DEFAULT_DATA_PATH
        if not training_files:
            raise AppException("No files received!")

        if training_files[0].filename.endswith('.zip'):
            bot_data_home_dir = await DataUtility.save_training_files_as_zip(bot, training_files[0])
        else:
            bot_data_home_dir = os.path.join('training_data', bot, str(uuid.uuid4()))
            data_path = os.path.join(bot_data_home_dir, DEFAULT_DATA_PATH)
            Utility.make_dirs(data_path)

            for file in training_files:
                if not file:
                    continue
                if file.filename in ALLOWED_NLU_FORMATS.union(ALLOWED_STORIES_FORMATS).union(ALLOWED_RULES_FORMATS):
                    path = os.path.join(data_path, file.filename)
                    Utility.write_to_file(path, await file.read())
                elif file.filename in ALLOWED_CONFIG_FORMATS.union(ALLOWED_DOMAIN_FORMATS).union(
                        ALLOWED_ACTIONS_FORMATS, ALLOWED_CHAT_CLIENT_CONFIG_FORMATS, ALLOWED_MULTIFLOW_STORIES_FORMATS, ALLOWED_BOT_CONTENT_FORMATS):
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
        from rasa.shared.constants import DEFAULT_DATA_PATH
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
        if ALLOWED_ACTIONS_FORMATS.intersection(files_received).__len__() < 1:
            requirements.add('actions')
        if ALLOWED_CHAT_CLIENT_CONFIG_FORMATS.intersection(files_received).__len__() < 1:
            requirements.add('chat_client_config')
        if ALLOWED_MULTIFLOW_STORIES_FORMATS.intersection(files_received).__len__() < 1:
            requirements.add('multiflow_stories')
        if ALLOWED_BOT_CONTENT_FORMATS.intersection(files_received).__len__() < 1:
            requirements.add('bot_content')

        if requirements == REQUIREMENTS:
            if delete_dir_on_exception:
                Utility.delete_directory(bot_data_home_dir)
            raise AppException('Invalid files received')
        return requirements

    @staticmethod
    async def save_training_files(nlu: File, domain: File, config: File, stories: File, rules: File = None,
                                  http_action: File = None, multiflow_stories: File = None, bot_content: File = None):
        """
        convert mongo data  to individual files

        :param nlu: nlu data
        :param domain: domain data
        :param stories: stories data
        :param config: config data
        :param rules: rules data
        :param http_action: http actions data
        :param multiflow_stories: multiflow_stories data
        :param bot_content: bot_content data
        :return: files path
        """
        from rasa.shared.constants import DEFAULT_DATA_PATH
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
        training_file_loc['multiflow_stories'] = await DataUtility.write_multiflow_stories_data(tmp_dir,
                                                                                                multiflow_stories)
        training_file_loc['bot_content'] = await DataUtility.write_bot_content_data(tmp_dir,
                                                                                    bot_content)
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

    @staticmethod
    async def write_multiflow_stories_data(data_path: str, multiflow_stories: File = None):
        """
        writes the multiflow stories data to file and returns the file path
        :param data_path: path of the data files
        :param multiflow_stories: multiflow_stories data
        :return: rule file path
        """
        if multiflow_stories and multiflow_stories.filename:
            multiflow_stories_path = os.path.join(data_path, multiflow_stories.filename)
            Utility.write_to_file(multiflow_stories_path, await multiflow_stories.read())
            return multiflow_stories_path

    @staticmethod
    async def write_bot_content_data(temp_path: str, bot_content: File = None):
        """
        writes the bot content data to file and returns the file path
        :param temp_path: path of the data files
        :param bot_content: bot_content data
        :return: bot_content file path
        """
        if bot_content and bot_content.filename:
            bot_content_path: str = os.path.join(temp_path, bot_content.filename)
            Utility.write_to_file(bot_content_path, await bot_content.read())
            return bot_content_path

    @staticmethod
    def extract_text_and_entities(text: Text):
        """
        extract entities and plain text from markdown intent example

        :param text: markdown intent example
        :return: plain intent, list of extracted entities
        """
        from rasa.shared.nlu.constants import TEXT
        from rasa.shared.nlu.training_data import entities_parser
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
    def validate_flow_events(events, event_type, name):
        from rasa.shared.core.constants import RULE_SNIPPET_ACTION_NAME
        Utility.validate_document_list(events)
        if event_type == "STORY" and events[0].type != "user":
            raise ValidationError("First event should be an user")

        if event_type == "RULE":
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
            if event_type == "RULE" and intents > 1:
                raise ValidationError(
                    f"""Found rules '{name}' that contain more than user event.\nPlease use stories for this case""")

    @staticmethod
    def get_fallback_intent(bot: Text, user: Text):
        from kairon.shared.data.processor import MongoProcessor

        bot_settings = MongoProcessor.get_bot_settings(bot=bot, user=user)
        bot_settings = bot_settings.to_mongo().to_dict()
        fallback_intent = bot_settings['analytics']['fallback_intent']
        return fallback_intent

    @staticmethod
    def parse_fallback_action(config: Dict):
        fallback_action = "action_default_fallback"
        action_fallback = next((comp for comp in config['policies'] if "RulePolicy" in comp["name"]), None)
        if action_fallback:
            fallback_action = action_fallback.get("core_fallback_action_name", fallback_action)
        return fallback_action

    @staticmethod
    def get_template_type(story):
        """
        Retrieve template type(either QnA or Custom) from events in the flow.
        Receives a dict or instance of RuleStep or StoryStep and returns its type.
        """
        from rasa.shared.core.constants import RULE_SNIPPET_ACTION_NAME
        from rasa.shared.core.events import UserUttered, ActionExecuted

        template_type = 'CUSTOM'
        if isinstance(story, Dict):
            steps = story['steps']
            if (
                    len(steps) == 2 and
                    story["type"] == 'RULE' and
                    steps[0]['type'] == StoryStepType.intent and
                    steps[1]['type'] == StoryStepType.bot
            ) or (
                    len(steps) == 3 and
                    story["type"] == 'RULE' and
                    steps[0]['name'] == RULE_SNIPPET_ACTION_NAME and
                    steps[0]['type'] == StoryStepType.action and
                    steps[1]['type'] == StoryStepType.intent and
                    steps[2]['type'] == StoryStepType.bot
            ):
                template_type = 'Q&A'
        else:
            events = story.events
            if (
                    len(events) == 2 and
                    isinstance(story, RuleStep) and
                    isinstance(events[0], UserUttered) and
                    isinstance(events[1], ActionExecuted) and
                    events[1].action_name.startswith("utter_")
            ) or (
                    len(events) == 3 and
                    isinstance(story, RuleStep) and
                    isinstance(events[0], ActionExecuted) and
                    events[0].action_name == RULE_SNIPPET_ACTION_NAME and
                    isinstance(events[1], UserUttered) and
                    isinstance(events[2], ActionExecuted) and
                    events[2].action_name.startswith("utter_")
            ):
                template_type = 'Q&A'
        return template_type

    @staticmethod
    def get_channel_endpoint(channel_config: dict):
        from kairon.shared.auth import Authentication
        from kairon.shared.constants import ChannelTypes
        token, _ = Authentication.generate_integration_token(
            channel_config['bot'], channel_config['user'], role=ACCESS_ROLES.CHAT.value,
            access_limit=[f"/api/bot/{channel_config['connector_type']}/{channel_config['bot']}/.+"],
            token_type=TOKEN_TYPE.CHANNEL.value
        )
        if channel_config['connector_type'] in [ChannelTypes.MSTEAMS.value, ChannelTypes.LINE.value]:
            token = DataUtility.save_channel_metadata(config=channel_config, token=token)

        channel_endpoint = urljoin(
            Utility.environment['model']['agent']['url'],
            f"/api/bot/{channel_config['connector_type']}/{channel_config['bot']}/{token}"
        )
        return channel_endpoint

    @staticmethod
    def get_integration_endpoint(integration_config: dict):
        from kairon.shared.auth import Authentication

        token, _ = Authentication.generate_integration_token(
            integration_config['bot'], integration_config['user'], role=ACCESS_ROLES.DESIGNER.value,
            access_limit=[
                f"/api/bot/integration/{integration_config['provider']}/{integration_config['sync_type']}/{integration_config['bot']}/.+"],
            token_type=TOKEN_TYPE.DATA_INTEGRATION.value
        )

        integration_endpoint = urljoin(
            Utility.environment['model']['agent']['url'],
            f"/api/bot/integration/{integration_config['provider']}/{integration_config['sync_type']}/{integration_config['bot']}/{token}"
        )
        return integration_endpoint

    @staticmethod
    def save_channel_metadata(**kwargs):
        token = kwargs["token"]
        channel_config = kwargs.get("config")
        hashedtoken = hash(token).__str__()
        encrypted_token = Utility.encrypt_message(token)
        channel_config.meta_config = {"secrethash": hashedtoken, "secrettoken": encrypted_token}
        channel_config.save(validate=False)
        return hashedtoken

    @staticmethod
    def validate_existing_data_train(bot: Text):

        from kairon.shared.data.data_objects import Stories
        from kairon.shared.data.data_objects import Intents
        from kairon.shared.data.data_objects import Rules

        intent_count = Intents.objects(bot=bot, status=True).count()
        stories_count = Stories.objects(bot=bot, status=True).count()
        rule_count = Rules.objects(bot=bot, status=True).count()
        multiflow_count = MultiflowStories.objects(bot=bot, status=True).count()

        if intent_count < 2 or (stories_count + rule_count + multiflow_count) < 2:
            raise AppException('Please add at least 2 flows and 2 intents before training the bot!')

    @staticmethod
    def validate_faq_training_data(bot: Text, df: DataFrame):
        '''
        Checks whether there are duplicates between file and the existing bot data.
        Also validates whether there are duplicates within the file data.
        Total count of training examples and responses are recorded.

        :param bot: bot id
        :param df: dataframe from user given file
        :return: error_summary and component_count
        '''
        from kairon.shared.data.processor import MongoProcessor

        processor = MongoProcessor()
        error_summary = {'intents': [], 'utterances': [], 'training_examples': []}
        component_count = {'intents': 0, 'utterances': 0, 'stories': 0, 'rules': 0, 'training_examples': 0, 
                           'domain': {'intents': 0, 'utterances': 0}}
        if df.empty:
            raise AppException("No data found!")
        existing_responses = processor.fetch_list_of_response(bot=bot)
        existing_training_examples = processor.get_training_examples_as_dict(bot)
        existing_training_examples = {k.lower(): v for k, v in existing_training_examples.items()}

        # Iterate over excel/csv
        for index, row in df.iterrows():

            # Validate Training examples and keep count
            for question in row['questions'].split('\n'):
                if Utility.check_empty_string(question):
                    error_summary['training_examples'].append(f"Empty questions found at index {index + 1} for response '{row['answer']}'")
                if question.lower() in existing_training_examples:
                    error_summary['training_examples'].append(f"Phrase '{question}' already exists in the bot!")
                component_count['training_examples'] = component_count['training_examples'] + 1

            # Validate response and keep count
            if Utility.check_empty_string(row['answer']):
                error_summary['utterances'].append(f"Empty answer found at index {index + 1}")
            if {'text': row['answer']} in existing_responses:
                error_summary['utterances'].append(f"Answer '{row['answer']}' already exists in the bot!")
            component_count['utterances'] = component_count['utterances'] + 1

        # Duplicates within the given data
        duplicate_question = DataUtility.get_duplicate_values(df, 'questions')
        duplicate_utterance = DataUtility.get_duplicate_values(df, 'answer')
        if duplicate_question:
            error_summary['training_examples'].append(f"Found duplicate phrases within the given data - {duplicate_question}")
        if duplicate_utterance:
            error_summary['utterances'].append(f"Found duplicate answers within the given data - {duplicate_utterance}")
        return error_summary, component_count

    @staticmethod
    def get_duplicate_values(df: DataFrame, column_name: Text):
        '''
        Checks whether there are duplicates in a particular column.

        :param df: dataframe from user given file
        :param column_name: column on which duplicates are to be found
        :return: duplicates
        '''
        column_data = pd.DataFrame()
        column_data[column_name] = df.apply(lambda x: x[column_name].split("\n"), axis=1)
        new_line_splitted_data = column_data[column_name].explode()
        duplicates = new_line_splitted_data[new_line_splitted_data.duplicated(keep=False)]
        duplicates = set(duplicates.unique())
        return duplicates


class ChatHistoryUtils:

    @staticmethod
    def unique_user_input(from_date, to_date, current_user_bot):
        from ...shared.data.processor import MongoProcessor
        response = Utility.trigger_history_server_request(
            current_user_bot,
            f'/api/history/{current_user_bot}/metrics/users/input?from_date={from_date}&to_date={to_date}', {}
        )

        user_input = response['data']
        processor = MongoProcessor()
        training_examples = processor.get_all_training_examples(bot=current_user_bot)
        queries_not_present = [query for query in user_input if query['_id'] not in training_examples[0]]
        return queries_not_present

    @staticmethod
    def validate_history_endpoint(bot: Text):
        """
        Checks if the history endpoint is managed by kairon or client user
        :param bot: bot id
        :return: none
        """
        # Check history endpoint
        from kairon.shared.data.processor import MongoProcessor

        mongo_processor = MongoProcessor()
        history_endpoint = mongo_processor.get_history_server_endpoint(bot)
        if history_endpoint.get('type') and history_endpoint['type'] != 'kairon':
            raise AppException(f'History server not managed by Kairon!. Manually delete the collection:{bot}')

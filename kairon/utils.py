import os
import re
import shutil
import string
import tempfile
from datetime import datetime, timedelta
from glob import glob, iglob
from html import escape
from pathlib import Path
from io import BytesIO
from secrets import choice
from smtplib import SMTP
from typing import Text, List, Dict
from fastapi import File
from mongoengine import StringField, ListField
from rasa.shared.core.training_data.story_writer.yaml_story_writer import YAMLStoryWriter
from rasa.utils.endpoints import EndpointConfig
import requests
import yaml
from fastapi.security import OAuth2PasswordBearer
from jwt import encode, decode
from mongoengine.document import BaseDocument, Document
from mongoengine.errors import ValidationError
from passlib.context import CryptContext
from password_strength import PasswordPolicy
from password_strength.tests import Special, Uppercase, Numbers, Length
from pymongo.errors import InvalidURI
from pymongo.uri_parser import (
    SRV_SCHEME_LEN,
    SCHEME,
    SCHEME_LEN,
    SRV_SCHEME,
    parse_userinfo,
)
from rasa.shared.constants import DEFAULT_CONFIG_PATH, DEFAULT_DATA_PATH, DEFAULT_DOMAIN_PATH
from rasa.shared.constants import DEFAULT_MODELS_PATH
from rasa.shared.nlu.constants import TEXT
from rasa.core.tracker_store import MongoTrackerStore
from rasa.shared.core.training_data.structures import StoryGraph
from rasa.shared.importers.rasa import Domain
from rasa.shared.nlu.training_data.training_data import TrainingData
from rasa.shared.nlu.training_data.formats.markdown import MarkdownReader
from rasa.shared.nlu.training_data import entities_parser
from smart_config import ConfigLoader
from validators import ValidationFailure
from validators import email as mail_check

from .shared.actions.data_objects import HttpActionConfig
from .api.models import HttpActionParametersResponse, HttpActionConfigResponse
from .data_processor.constant import POSSIBLE_NLU_FILES, POSSIBLE_STORIES_FILES, \
    POSSIBLE_DOMAIN_FILES, POSSIBLE_CONFIG_FILES, EVENT_STATUS
from .exceptions import AppException
from kairon.data_processor.cache import InMemoryAgentCache
from loguru import logger


class Utility:
    """Class contains logic for various utilities"""

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
    environment = {}
    password_policy = PasswordPolicy.from_names(
        length=8,  # min length: 8
        uppercase=1,  # need min. 1 uppercase letters
        numbers=1,  # need min. 1 digits
        special=1,  # need min. 1 special characters
    )
    markdown_reader = MarkdownReader()
    email_conf = {}

    @staticmethod
    def check_empty_string(value: str):
        """
        checks for empty string

        :param value: string value
        :return: boolean
        """
        if not value:
            return True
        if not value.strip():
            return True
        else:
            return False

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
    def validate_document_list(documents: List[BaseDocument]):
        """
        validates list of documents

        :param documents: list of documents
        :return: None
        """
        if documents:
            for document in documents:
                document.validate()

    @staticmethod
    def load_yaml(file: Text):
        """
        loads yaml file

        :param file: yaml file path
        :return: dict
        """
        with open(file) as fp:
            return yaml.safe_load(fp)

    @staticmethod
    def load_evironment():
        """
        Loads the environment variables and their values from the
        system.yaml file for defining the working environment of the app

        :return: None
        """
        Utility.environment = ConfigLoader(os.getenv("system_file", "./system.yaml")).get_config()

    @staticmethod
    def is_exist(
            document: Document, exp_message: Text = None, raise_error=True, *args, **kwargs
    ):
        """
        check if document exist

        :param document: document type
        :param exp_message: exception message
        :param raise_error: boolean to raise exception
        :param kwargs: filter parameters
        :return: boolean
        """
        doc = document.objects(**kwargs)
        if doc.__len__():
            if raise_error:
                if Utility.check_empty_string(exp_message):
                    raise AppException("Exception message cannot be empty")
                raise AppException(exp_message)
            else:
                return True
        else:
            if not raise_error:
                return False

    @staticmethod
    def verify_password(plain_password, hashed_password):
        """
        verify password on constant time

        :param plain_password: user password
        :param hashed_password: saved password
        :return: boolean
        """
        return Utility.pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def get_password_hash(password):
        """
        convert plain password to hashed

        :param password: plain password
        :return: hashed password
        """
        if not Utility.check_empty_string(password):
            return Utility.pwd_context.hash(password)

    @staticmethod
    def get_latest_file(folder):
        """
        fetches latest file from folder

        :param folder: folder path
        :return: latest file
        """
        if not os.path.exists(folder):
            raise AppException("Folder does not exists!")
        return max(iglob(folder + "/*"), key=os.path.getctime)

    @staticmethod
    def deploy_model(endpoint: Dict, bot: Text):
        """
        deploys the model to the specified endpoint

        :param endpoint: endpoint configuration
        :param bot: bot id
        :return: endpoint deployed response
        """
        if not endpoint or not endpoint.get("bot_endpoint"):
            raise AppException("Please configure the bot endpoint for deployment!")
        headers = {"Content-type": "application/json", "Accept": "text/plain"}
        url = endpoint["bot_endpoint"].get("url")
        if endpoint["bot_endpoint"].get("token_type") and endpoint["bot_endpoint"].get(
                "token"
        ):
            headers["Authorization"] = (
                    endpoint["bot_endpoint"].get("token_type")
                    + " "
                    + endpoint["bot_endpoint"].get("token")
            )
        try:
            model_file = Utility.get_latest_file(os.path.join(DEFAULT_MODELS_PATH, bot))
            response = requests.put(
                url + "/model", json={"model_file": model_file}, headers=headers,
            )

            if response.status_code == 204:
                result = "Model was successfully replaced."
            else:
                json_response = response.json()
                if isinstance(json_response, str):
                    result = escape(json_response)
                elif isinstance(json_response, dict):
                    if "message" in json_response:
                        result = escape(json_response["message"])
                    elif "reason" in json_response:
                        result = escape(json_response["reason"])
                    else:
                        result = None
                else:
                    result = None
        except requests.exceptions.ConnectionError:
            raise AppException("Host is not reachable")
        except Exception as e:
            raise AppException(e)
        return result, model_file

    @staticmethod
    def generate_password(size=8, chars=string.ascii_letters + string.digits):
        """
        generates password

        :param size: size of password
        :param chars: password combination
        :return: generated password
        """
        return "".join(choice(chars) for _ in range(size))

    @staticmethod
    def make_dirs(path: Text, raise_exception_if_exists=False):
        if os.path.exists(path):
            if raise_exception_if_exists:
                raise AppException('Directory exists!')
        else:
            os.makedirs(path)

    @staticmethod
    async def save_and_validate_training_files(bot: Text, training_files: [File]):
        if not training_files:
            raise AppException("No files received!")

        if training_files[0].filename.endswith('.zip'):
            await Utility.unzip_and_validate(bot, training_files[0])
            return

        bot_data_home_dir = os.path.join('training_data', bot, str(datetime.utcnow()))
        data_path = os.path.join(bot_data_home_dir, DEFAULT_DATA_PATH)
        Utility.make_dirs(data_path)

        for file in training_files:
            if file.filename in POSSIBLE_NLU_FILES.union(POSSIBLE_STORIES_FILES).union({'rules.yml'}):
                path = os.path.join(data_path, file.filename)
                Utility.write_to_file(path, await file.read())
            elif file.filename in POSSIBLE_CONFIG_FILES.union(POSSIBLE_DOMAIN_FILES).union({'http_action.yml'}):
                path = os.path.join(bot_data_home_dir, file.filename)
                Utility.write_to_file(path, await file.read())

        Utility.validate_files(bot_data_home_dir, True)

    @staticmethod
    async def unzip_and_validate(bot: Text, training_file: File):
        tmp_dir = tempfile.mkdtemp()
        zipped_file = os.path.join(tmp_dir, training_file.filename)
        Utility.write_to_file(zipped_file, await training_file.read())
        unzip_path = os.path.join('training_data', bot, str(datetime.utcnow()))
        shutil.unpack_archive(zipped_file, unzip_path, 'zip')
        try:
            Utility.validate_files(unzip_path, True)
        finally:
            Utility.delete_directory(tmp_dir)

    @staticmethod
    def validate_files(bot_data_home_dir: Text, delete_dir_on_exception: bool = False):
        data_path = os.path.join(bot_data_home_dir, DEFAULT_DATA_PATH)

        if not os.path.exists(bot_data_home_dir) or not os.path.exists(data_path):
            if delete_dir_on_exception:
                Utility.delete_directory(bot_data_home_dir)
            raise AppException("Required directory structure not found!")
        files = set(os.listdir(bot_data_home_dir)).union(os.listdir(data_path))

        if POSSIBLE_NLU_FILES.intersection(files).__len__() < 1 or \
                POSSIBLE_STORIES_FILES.intersection(files).__len__() < 1 or \
                POSSIBLE_DOMAIN_FILES.intersection(files).__len__() < 1 or \
                POSSIBLE_CONFIG_FILES.intersection(files).__len__() < 1:
            if delete_dir_on_exception:
                Utility.delete_directory(bot_data_home_dir)
            raise AppException('Some training files are missing!')

    @staticmethod
    async def save_training_files(nlu: File, domain: File, config: File, stories: File, rules: File = None, http_action: File = None):
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

        training_file_loc['rules'] = await Utility.write_rule_data(data_path, rules)
        training_file_loc['http_action'] = await Utility.write_http_data(tmp_dir, http_action)
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
    def write_training_data(nlu: TrainingData, domain: Domain, config: dict,
                            stories: StoryGraph, rules: StoryGraph = None, http_action: dict = None):
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
        temp_path = tempfile.mkdtemp()
        data_path = os.path.join(temp_path, DEFAULT_DATA_PATH)
        os.makedirs(data_path)
        nlu_path = os.path.join(data_path, "nlu.yml")
        domain_path = os.path.join(temp_path, DEFAULT_DOMAIN_PATH)
        stories_path = os.path.join(data_path, "stories.yml")
        config_path = os.path.join(temp_path, DEFAULT_CONFIG_PATH)
        rules_path = os.path.join(data_path, "rules.yml")
        http_path = os.path.join(temp_path, "http_action.yml")

        nlu_as_str = nlu.nlu_as_yaml().encode()
        config_as_str = yaml.dump(config).encode()

        if isinstance(domain, Domain):
            domain_as_str = domain.as_yaml().encode()
            Utility.write_to_file(domain_path, domain_as_str)
        elif isinstance(domain, Dict):
            yaml.safe_dump(domain, open(domain_path, "w"))
        Utility.write_to_file(nlu_path, nlu_as_str)
        Utility.write_to_file(config_path, config_as_str)
        YAMLStoryWriter().dump(stories_path, stories.story_steps)
        if rules:
            YAMLStoryWriter().dump(rules_path, rules.story_steps)
        if http_action:
            http_as_str = yaml.dump(http_action).encode()
            Utility.write_to_file(http_path, http_as_str)
        return temp_path

    @staticmethod
    def write_to_file(file: Text, data: bytes):
        """
        open file in binary mode

        :param file: file path
        :param data: data to write
        :return: None
        """
        with open(file, "wb") as w:
            w.write(data)
            w.flush()

    @staticmethod
    def delete_directory(path: Text):
        """
        deletes directory with all files

        :param path: directory path
        :return: None
        """
        shutil.rmtree(path)

    @staticmethod
    def create_zip_file(
            nlu: TrainingData, domain: Domain, stories: StoryGraph, config: Dict, bot: Text, rules: StoryGraph = None,
            http_action: Dict = None
    ):
        """
        adds training files to zip

        :param nlu: nlu data
        :param domain: domain data
        :param stories: stories data
        :param config: config data
        :param http_action: http actions data
        :param bot: bot id
        :return: None
        """
        directory = Utility.write_training_data(
            nlu,
            domain,
            config,
            stories,
            rules,
            http_action
        )
        zip_path = os.path.join(tempfile.gettempdir(), bot)
        zip_file = shutil.make_archive(zip_path, format="zip", root_dir=directory)
        shutil.rmtree(directory)
        return zip_file

    @staticmethod
    def load_file_in_memory(file: Text):
        """
        load file in memory

        :param file: file path
        :return: bytes
        """
        data = BytesIO()
        with open(file, "rb") as fo:
            data.write(fo.read())
        data.seek(0)
        os.remove(file)
        return data

    @staticmethod
    def valid_password(password: Text):
        """
        validate password against password policy

        :param password: password
        :return: None
        :exception: list of failed policies
        """
        results = Utility.password_policy.test(password)
        if results:
            response = []
            for result in results:
                if isinstance(result, Length):
                    response.append("Password length must be " + str(result.length))
                elif isinstance(result, Special):
                    response.append("Missing " + str(result.count) + " special letter")
                elif isinstance(result, Uppercase):
                    response.append(
                        "Missing " + str(result.count) + " uppercase letter"
                    )
                elif isinstance(result, Numbers):
                    response.append("Missing " + str(result.count) + "number")

            if response:
                raise AppException("\n".join(response))

    @staticmethod
    def delete_document(documents: List[Document], bot: Text, user: Text, **kwargs):
        """
        perform soft delete on list of mongo collections

        :param documents: list of mongo collections
        :param bot: bot id
        :param user: user id
        :return: NONE
        """
        for document in documents:
            kwargs['bot'] = bot
            update = {'set__user': user, 'set__timestamp': datetime.utcnow()}
            if "status" in document._db_field_map:
                kwargs['status'] = True
                update['set__status'] = False
            fetched_documents = document.objects(**kwargs)
            if fetched_documents.count() > 0:
                fetched_documents.update(**update)

    @staticmethod
    def hard_delete_document(documents: List[Document], bot: Text, user: Text, **kwargs):
        """
        perform hard delete on list of mongo collections

        :param documents: list of mongo collections
        :param bot: bot id
        :param user: user id
        :return: NONE
        """
        for document in documents:
            kwargs['bot'] = bot
            fetched_documents = document.objects(**kwargs)
            if fetched_documents.count() > 0:
                fetched_documents.delete()


    @staticmethod
    def extract_user_password(uri: str):
        """
        extract username, password and host with port from mongo uri

        :param uri: mongo uri
        :return: username, password, scheme, hosts
        """
        if uri.startswith(SCHEME):
            scheme_free = uri[SCHEME_LEN:]
            scheme = uri[:SCHEME_LEN]
        elif uri.startswith(SRV_SCHEME):
            scheme_free = uri[SRV_SCHEME_LEN:]
            scheme = uri[:SRV_SCHEME_LEN]
        else:
            raise InvalidURI(
                "Invalid URI scheme: URI must "
                "begin with '%s' or '%s'" % (SCHEME, SRV_SCHEME)
            )

        if not scheme_free:
            raise InvalidURI("Must provide at least one hostname or IP.")

        host_part, _, _ = scheme_free.partition("/")
        if "@" in host_part:
            userinfo, _, hosts = host_part.rpartition("@")
            user, passwd = parse_userinfo(userinfo)
            return user, passwd, scheme + hosts
        else:
            return None, None, scheme + host_part

    @staticmethod
    def get_local_mongo_store(bot: Text, domain: Domain):
        """
        create local mongo tracker

        :param bot: bot id
        :param domain: domain data
        :return: mongo tracker
        """
        username, password, url, db_name = Utility.get_local_db()
        return MongoTrackerStore(
            domain=domain,
            host=url,
            db=db_name,
            collection=bot,
            username=username,
            password=password,
        )

    @staticmethod
    def special_match(strg, search=re.compile(r"[^a-zA-Z0-9_]").search):
        """
        check if string contains special character other than allowed ones

        :param strg: text value
        :param search: search pattern
        :return: boolen
        """
        return bool(search(strg))

    @staticmethod
    def extract_text_and_entities(text: Text):
        """
        extract entities and plain text from markdown intent example

        :param text: markdown intent example
        :return: plain intent, list of extracted entities
        """
        example = entities_parser.parse_training_example(text)
        return example.get(TEXT), example.get('entities',[])

    @staticmethod
    def __extract_response_button(buttons: Dict):
        """
        used to prepare ResponseButton by extracting buttons configuration from bot utterance

        :param buttons: button configuration in bot response
        :return: yields ResponseButton
        """
        from .data_processor.data_objects import ResponseButton

        for button in buttons:
            yield ResponseButton._from_son(button)

    @staticmethod
    def prepare_response(value: Dict):
        """
        used to prepare bot utterance either Text or Custom for saving in Mongo

        :param value: utterance value
        :return: response type, response object
        """
        from .data_processor.constant import RESPONSE
        from .data_processor.data_objects import ResponseText, ResponseCustom

        if RESPONSE.Text.value in value:
            response_text = ResponseText()
            response_text.text = str(value[RESPONSE.Text.value]).strip()
            if RESPONSE.IMAGE.value in value:
                response_text.image = value[RESPONSE.IMAGE.value]
            if RESPONSE.CHANNEL.value in value:
                response_text.channel = value["channel"]
            if RESPONSE.BUTTONS.value in value:
                response_text.buttons = list(
                    Utility.__extract_response_button(value[RESPONSE.BUTTONS.value])
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
            data =None
        return response_type, data

    @staticmethod
    def list_directories(path: Text):
        """
        list all the directories in given path

        :param path: directory path
        :return: list of directories
        """
        return list(os.listdir(path))

    @staticmethod
    def list_files(path: Text, extensions=None):
        """
        list all the files in directory

        :param path: directory path
        :param extensions: extension to search
        :return: file list
        """
        if extensions is None:
            extensions = ["yml", "yaml"]
        files = [glob(os.path.join(path, "*." + extension)) for extension in extensions]
        return sum(files, [])

    @staticmethod
    def get_rasa_core_policies():
        from rasa.core.policies import registry
        file1 = open(registry.__file__, 'r')
        Lines = file1.readlines()
        policy = []
        for line in Lines:
            if line.startswith("from"):
                items = line.split("import")[1].split(",")
                for item in items:
                    policy.append(item.strip())
        return policy

    @staticmethod
    def load_email_configuration():
        """
            Loads the variables from the
            email.yaml file
        """

        Utility.email_conf = ConfigLoader(os.getenv("EMAIL_CONF", "./email.yaml")).get_config()

    @staticmethod
    async def validate_and_send_mail(email: str, subject: str, body: str):
        """
        Used to validate the parameters of the mail to be sent

        :param email: email id of the recipient
        :param subject: subject of the mail
        :param body: body or message of the mail
        :return: None
        """
        if isinstance(mail_check(email), ValidationFailure):
            raise AppException("Please check if email is valid")

        if (
                Utility.check_empty_string(subject)
                or Utility.check_empty_string(body)
        ):
            raise ValidationError(
                "Subject and body of the mail cannot be empty or blank space"
            )
        await Utility.trigger_smtp(email, subject, body)

    @staticmethod
    async def trigger_smtp(email: str, subject: str, body: str):
        """
        Sends an email to the mail id of the recipient

        :param email: the mail id of the recipient
        :param subject: the subject of the mail
        :param body: the body of the mail
        :return: None
        """
        smtp = SMTP(Utility.email_conf["email"]["sender"]["service"],
                    port=Utility.email_conf["email"]["sender"]["port"])
        smtp.connect(Utility.email_conf["email"]["sender"]["service"], Utility.email_conf["email"]["sender"]["port"])
        if Utility.email_conf["email"]["sender"]["tls"]:
            smtp.starttls()
        smtp.login(Utility.email_conf["email"]["sender"]["userid"] if
                   Utility.email_conf["email"]["sender"]["userid"] else
                   Utility.email_conf["email"]["sender"]["email"],
                   Utility.email_conf["email"]["sender"]["password"])
        from_addr = Utility.email_conf["email"]["sender"]["email"]
        msg = "From: %s\nTo: %s\nSubject: %s\n\n\n%s" % (from_addr, email, subject, body)
        msg = msg.encode('utf-8')
        smtp.sendmail(from_addr, email, msg)
        smtp.quit()

    @staticmethod
    def generate_token(email: str, minutes_to_expire=1440):
        """
        Used to encode the mail id into a token

        :param email: mail id of the recipient
        :param minutes_to_expire: time in minutes until the token expires
        :return: the token with encoded mail id
        """
        data = {"mail_id": email}
        expire = datetime.utcnow() + timedelta(minutes=minutes_to_expire)
        data.update({"exp": expire})
        encoded_jwt = encode(
            data,
            Utility.environment['security']["secret_key"],
            algorithm=Utility.environment['security']["algorithm"],
        ).decode("utf-8")
        return encoded_jwt

    @staticmethod
    def verify_token(token: str):
        """
        Used to check if token is valid

        :param token: the token from the confirmation link
        :return: mail id
        """
        try:

            decoded_jwt = decode(
                token,
                Utility.environment['security']["secret_key"],
                algorithm=Utility.environment['security']["algorithm"],
            )
            mail = decoded_jwt["mail_id"]
            return mail

        except Exception:
            raise AppException("Invalid token")

    @staticmethod
    def get_local_db():
        db_url = Utility.environment['database']["url"]
        db_name = Utility.environment['database']["test_db"]
        username, password, url = Utility.extract_user_password(db_url)
        return username, password, url, db_name

    @staticmethod
    def get_timestamp_previous_month(month: int):
        start_time = datetime.now() - timedelta(month * 30, seconds=0, minutes=0, hours=0)
        return start_time.timestamp()

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
    def create_cache():
        return InMemoryAgentCache()

    @staticmethod
    def train_model_event(bot: str, user: str, token: str = None):
        event_url = Utility.environment['model']['train']['event_url']
        logger.info("model training event started")
        response = requests.post(event_url, headers={'content-type': 'application/json'}, json={'bot': bot, 'user': user, 'token': token})
        logger.info("model training event completed"+response.content.decode('utf8'))

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
            from .data_processor.processor import TrainingDataGenerationProcessor
            TrainingDataGenerationProcessor.set_status(bot=bot,
                                                       user=user,
                                                       status=EVENT_STATUS.FAIL.value,
                                                       exception=str(e))

    @staticmethod
    def http_request(method: str, url: str, token: str, user: str, json: Dict = None):
        logger.info("agent event started "+url)
        headers = {'content-type': 'application/json', 'X-USER': user}
        if token:
            headers['Authorization'] = 'Bearer '+token
        response = requests.request(method, url, headers=headers, json=json)
        logger.info("agent event completed" + response.content.decode('utf8'))
        return response.content.decode('utf8')

    @staticmethod
    def get_action_url(endpoint):
        if endpoint and endpoint.get("action_endpoint"):
            return EndpointConfig(url=endpoint["action_endpoint"]["url"])
        elif Utility.environment['action'].get('url'):
            return EndpointConfig(url=Utility.environment['action'].get('url'))
        else:
            return None

    @staticmethod
    async def upload_document(doc):
        if not (doc.filename.lower().endswith('.pdf') or doc.filename.lower().endswith('.docx')):
            raise AppException("Invalid File Format")
        folder_path = 'data_generator'
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        destination = os.path.join(folder_path, doc.filename)
        with Path(destination).open("wb") as buffer:
            shutil.copyfileobj(doc.file, buffer)
        return destination

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

    @staticmethod
    def read_yaml(path: Text, raise_exception: bool = False):
        content = None
        if os.path.exists(path):
            content = yaml.load(open(path), Loader=yaml.SafeLoader)
        else:
            if raise_exception:
                raise AppException('Path does not exists!')
        return content

    @staticmethod
    def replace_file_name(msg: str, root_dir: str):
        regex = '((\'*\"*{0}).*(/{1}\'*\"*))'
        files = ['nlu.yml', 'domain.yml', 'config.yml', 'stories.yml', 'nlu.yaml', 'domain.yaml', 'config.yaml',
                 'stories.yaml', 'nlu.md', 'stories.md']
        for file in files:
            file_regex = regex.format(root_dir, file)
            msg = re.sub(file_regex, file, msg)
        return msg

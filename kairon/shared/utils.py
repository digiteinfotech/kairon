import json
import os
import re
import shutil
import string
import tempfile
from datetime import datetime, timedelta
from glob import glob, iglob
from html import escape
from io import BytesIO
from pathlib import Path
from secrets import choice
from smtplib import SMTP
from typing import Text, List, Dict
from urllib.parse import unquote_plus
from password_strength.tests import Special, Uppercase, Numbers, Length
import requests
import yaml
from jwt import encode, decode
from loguru import logger
from mongoengine.document import BaseDocument, Document
from mongoengine.errors import ValidationError
from mongoengine.queryset.visitor import QCombination
from pymongo.common import _CaseInsensitiveDictionary
from pymongo.errors import InvalidURI
from pymongo.uri_parser import (
    SRV_SCHEME_LEN,
    SCHEME,
    SCHEME_LEN,
    SRV_SCHEME,
    parse_userinfo,
)
from pymongo.uri_parser import _BAD_DB_CHARS, split_options
from smart_config import ConfigLoader
from validators import ValidationFailure
from validators import email as mail_check
from password_strength import PasswordPolicy
from ..exceptions import AppException
from passlib.context import CryptContext
from urllib.parse import urljoin


class Utility:
    """Class contains logic for various utilities"""
    environment = {}
    email_conf = {}
    password_policy = PasswordPolicy.from_names(
        length=8,  # min length: 8
        uppercase=1,  # need min. 1 uppercase letters
        numbers=1,  # need min. 1 digits
        special=1,  # need min. 1 special characters
    )
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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
    def get_password_hash(password):
        """
        convert plain password to hashed

        :param password: plain password
        :return: hashed password
        """
        if not Utility.check_empty_string(password):
            return Utility.pwd_context.hash(password)

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
    def load_environment(env="system_file"):
        """
        Loads the environment variables and their values from the
        system.yaml file for defining the working environment of the app

        :return: None
        """
        Utility.environment = ConfigLoader(os.getenv(env, "./system.yaml")).get_config()

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
        doc = document.objects(args, **kwargs)
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
    def is_exist_query(
            document: Document, query: QCombination, exp_message: Text = None, raise_error = True
    ):
        """
        check if document exist

        :param document: document type
        :param exp_message: exception message
        :param raise_error: boolean to raise exception
        :param kwargs: filter parameters
        :return: boolean
        """
        doc = document.objects(query)
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
    def get_latest_file(folder, extension_pattern="*"):
        """
        Fetches latest file.
        If extension is provided, latest file with that extension is retrieved.
        By default, latest file in the folder is retrieved and can be of any type.
        Example extension patterns: "*.tar.gz", "*.zip", etc.

        :param folder: folder path
        :param extension_pattern: file extension as a regular expression
        :return: latest file
        """
        if not os.path.exists(folder):
            raise AppException("Folder does not exists!")
        return max(iglob(os.path.join(folder, extension_pattern)), key=os.path.getctime)

    @staticmethod
    def deploy_model(endpoint: Dict, bot: Text):
        """
        deploys the model to the specified endpoint

        :param endpoint: endpoint configuration
        :param bot: bot id
        :return: endpoint deployed response
        """
        from rasa.shared.constants import DEFAULT_MODELS_PATH

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

    def extract_db_config(uri: str):
        """
        extract username, password and host with port from mongo uri

        :param uri: mongo uri
        :return: username, password, scheme, hosts
        """
        user = None
        passwd = None
        dbase = None
        collection = None
        options = _CaseInsensitiveDictionary()
        is_mock = False
        if uri.startswith("mongomock://"):
            uri = uri.replace("mongomock://", "mongodb://", 1)
            is_mock = True

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
        host_part, _, path_part = scheme_free.partition("/")
        if not host_part:
            host_part = path_part
            path_part = ""

        if not path_part and '?' in host_part:
            raise InvalidURI("A '/' is required between "
                             "the host list and any options.")

        if path_part:
            dbase, _, opts = path_part.partition('?')
            if dbase:
                dbase = unquote_plus(dbase)
                if '.' in dbase:
                    dbase, collection = dbase.split('.', 1)
                if _BAD_DB_CHARS.search(dbase):
                    raise InvalidURI('Bad database name "%s"' % dbase)
            else:
                dbase = None

            if opts:
                options.update(split_options(opts, True, False, True))

        if "@" in host_part:
            userinfo, _, hosts = host_part.rpartition("@")
            user, passwd = parse_userinfo(userinfo)
            hosts = scheme + hosts
        else:
            hosts = scheme + host_part

        settings = {
            "username": user,
            "password": passwd,
            "host": hosts,
            "db": dbase,
            "options": options,
            "collection": collection
        }

        if is_mock:
            settings['is_mock'] = is_mock
        return settings

    @staticmethod
    def get_local_mongo_store(bot: Text, domain):
        """
        create local mongo tracker

        :param bot: bot id
        :param domain: domain data
        :return: mongo tracker
        """
        from rasa.core.tracker_store import MongoTrackerStore
        config = Utility.get_local_db()
        return MongoTrackerStore(
            domain=domain,
            host=config['host'],
            db=config['db'],
            collection=bot,
            username=config.get('username'),
            password=config.get('password'),
            auth_source= config['options'].get("authSource") if config['options'].get("authSource") else "admin"
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
    def load_email_configuration():
        """
            Loads the variables from the
            email.yaml file
        """

        Utility.email_conf = ConfigLoader(os.getenv("EMAIL_CONF", "./email.yaml")).get_config()

    @staticmethod
    def get_timestamp_previous_month(month: int):
        start_time = datetime.now() - timedelta(month * 30, seconds=0, minutes=0, hours=0)
        return start_time.timestamp()

    @staticmethod
    def get_local_db(url=None, db_name=None):
        if not url:
            url = Utility.environment['database']['url']
        config = Utility.extract_db_config(url)
        if not db_name:
            db_name = Utility.environment['database']['test_db']
        config['db'] = db_name
        return config

    @staticmethod
    def http_request(method: str, url: str, token: str, user: str=None, json: Dict = None):
        logger.info("agent event started " + url)
        headers = {'content-type': 'application/json'}
        if user:
            headers['X-USER'] = user
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if method.lower() == 'get':
            response = requests.request(method, url, headers=headers, params=json)
        else:
            response = requests.request(method, url, headers=headers, json=json)
        logger.info("agent event completed" + response.content.decode('utf8'))
        return response.content.decode('utf8')

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
    def move_old_models(path, model):
        if os.path.isdir(path):
            new_path = os.path.join(path, "old_model")
            if not os.path.exists(new_path):
                os.mkdir(new_path)
            for cleanUp in glob(os.path.join(path, '*.tar.gz')):
                if model != cleanUp:
                    shutil.move(cleanUp, new_path)

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
        smtp.connect(Utility.email_conf["email"]["sender"]["service"],
                     Utility.email_conf["email"]["sender"]["port"])
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
    def initiate_apm_client_config():
        logger.debug(f'apm_enable: {Utility.environment["elasticsearch"].get("enable")}')
        if Utility.environment["elasticsearch"].get("enable"):
            server_url = Utility.environment["elasticsearch"].get("apm_server_url")
            service_name = Utility.environment["elasticsearch"].get("service_name")
            env = Utility.environment["elasticsearch"].get("env_type")
            config = {"SERVER_URL": server_url,
                       "SERVICE_NAME": service_name,
                       'ENVIRONMENT': env, }
            if Utility.environment["elasticsearch"].get("secret_token"):
                config['SECRET_TOKEN'] = Utility.environment["elasticsearch"].get("secret_token")
            logger.debug(f'apm: {config}')
            if service_name and server_url:
                return config

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

    @staticmethod
    def get_event_url(event_type: str, raise_exc: bool = False):
        url = None
        if "DATA_IMPORTER" == event_type:
            if Utility.environment.get('model') and Utility.environment['model'].get('data_importer') and \
                    Utility.environment['model']['data_importer'].get('event_url'):
                url = Utility.environment['model']['data_importer'].get('event_url')
        elif "TRAINING" == event_type:
            if Utility.environment.get('model') and Utility.environment['model']['train'].get('event_url'):
                url = Utility.environment['model']['train'].get('event_url')
        else:
            raise AppException("Invalid event type received")
        if raise_exc:
            raise AppException("Could not find event url")
        return url

    @staticmethod
    def build_event_request(env_var: dict):
        """Creates request body for lambda."""
        event_request = []
        for key in env_var.keys():
            key_and_val = {'name': key, 'value': env_var[key]}
            event_request.append(key_and_val)
        return event_request

    @staticmethod
    def add_or_update_epoch(configs: dict, epochs_to_set: dict):
        if epochs_to_set.get("nlu_epochs"):
            component = next((comp for comp in configs['pipeline'] if comp["name"] == 'DIETClassifier'), {})
            if not component:
                component['name'] = 'DIETClassifier'
                configs['pipeline'].append(component)
            component['epochs'] = epochs_to_set.get("nlu_epochs")

        if epochs_to_set.get("response_epochs"):
            component = next((comp for comp in configs['pipeline'] if comp["name"] == 'ResponseSelector'), {})
            if not component:
                component['name'] = 'ResponseSelector'
                configs['pipeline'].append(component)
            component['epochs'] = epochs_to_set.get("response_epochs")

        if epochs_to_set.get("ted_epochs"):
            component = next((comp for comp in configs['policies'] if comp["name"] == 'TEDPolicy'), {})
            if not component:
                component['name'] = 'TEDPolicy'
                configs['policies'].append(component)
            component['epochs'] = epochs_to_set.get("ted_epochs")

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
    def decode_limited_access_token(token: Text):
        try:
            decoded_jwt = decode(
                token,
                Utility.environment['security']["secret_key"],
                algorithm=Utility.environment['security']["algorithm"],
            )
            return decoded_jwt
        except Exception:
            raise AppException("Invalid token")

    @staticmethod
    def load_json_file(path: Text, raise_exc: bool = True):
        if not os.path.exists(path) and raise_exc:
            raise AppException('file not found')
        config = json.load(open(path))
        return config

    @staticmethod
    def download_csv(conversation: Dict, message):
        import pandas as pd

        if not conversation.get("conversation_data"):
            if not message:
                raise AppException("No data available!")
            else:
                raise AppException(message)
        else:
            df = pd.json_normalize(conversation.get("conversation_data"))
            temp_path = tempfile.mkdtemp()
            file_path = os.path.join(temp_path, "conversation_history.csv")
            df.to_csv(file_path, index=False)
            return file_path, temp_path

    @staticmethod
    def mongoengine_connection(url=None):
        if not url:
            url = Utility.environment['database']['url']
        config = Utility.extract_db_config(url)
        options = config.pop("options")
        config.pop("collection")
        if "replicaset" in options:
            config["replicaSet"] = options["replicaset"]
        if "authsource" in options:
            config["authentication_source"] = options["authsource"]
        if "authmechanism" in options:
            config["authentication_mechanism"] = options["authmechanism"]
        return config

    @staticmethod
    def get_action_url(endpoint):
        from rasa.utils.endpoints import EndpointConfig

        if endpoint and endpoint.get("action_endpoint"):
            return EndpointConfig(url=endpoint["action_endpoint"]["url"])
        elif Utility.environment['action'].get('url'):
            return EndpointConfig(url=Utility.environment['action'].get('url'))
        else:
            return None

    @staticmethod
    def is_data_import_allowed(summary: dict, bot: Text, user: Text):
        from ..shared.data.processor import MongoProcessor

        bot_settings = MongoProcessor.get_bot_settings(bot, user)
        if bot_settings.force_import:
            return True
        if bot_settings.ignore_utterances:
            is_data_valid = all([not summary[key] for key in summary.keys() if 'utterances' != key])
        else:
            is_data_valid = all([not summary[key] for key in summary.keys()])
        return is_data_valid

    @staticmethod
    def write_training_data(nlu, domain, config: dict,
                            stories, rules = None, http_action: dict = None):
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
        from rasa.shared.core.training_data.story_writer.yaml_story_writer import YAMLStoryWriter
        from rasa.shared.constants import DEFAULT_CONFIG_PATH, DEFAULT_DATA_PATH, DEFAULT_DOMAIN_PATH
        from rasa.shared.importers.rasa import Domain

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
    def train_model_event(bot: str, user: str, token: str = None):
        event_url = Utility.environment['model']['train']['event_url']
        logger.info("model training event started")
        response = requests.post(event_url, headers={'content-type': 'application/json'},
                                 json={'bot': bot, 'user': user, 'token': token})
        logger.info("model training event completed" + response.content.decode('utf8'))

    @staticmethod
    def create_zip_file(
            nlu, domain, stories, config: Dict, bot: Text,
            rules = None,
            http_action: Dict = None
    ):
        """
        adds training files to zip

        :param nlu: nlu data
        :param domain: domain data
        :param stories: stories data
        :param config: config data
        :param bot: bot id
        :param rules: rules data
        :param http_action: http actions data
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
    def verify_password(plain_password, hashed_password):
        """
        verify password on constant time

        :param plain_password: user password
        :param hashed_password: saved password
        :return: boolean
        """
        return Utility.pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    async def chat(data: Text, bot: Text, user: Text, email: Text):
        if Utility.environment.get('model') and Utility.environment['model']['agent'].get('url'):
            from kairon.shared.auth import Authentication
            agent_url = Utility.environment['model']['agent'].get('url')
            token = Authentication.create_access_token(data={"sub": email})
            response = Utility.http_request('post', urljoin(agent_url, f"/api/bot/{bot}/chat"), token.decode('utf8'),
                                            user, json={'data': data})
            return json.loads(response)
        else:
            raise AppException("Agent config not found!")

    @staticmethod
    def reload_model(bot: Text, email: Text):
        if Utility.environment.get('model') and Utility.environment['model']['agent'].get('url'):
            from kairon.shared.auth import Authentication
            agent_url = Utility.environment['model']['agent'].get('url')
            token = Authentication.create_access_token(data={"sub": email})
            response = Utility.http_request('get', urljoin(agent_url, f"/api/bot/{bot}/reload"), token.decode('utf8'))
            return json.loads(response)
        else:
            raise AppException("Agent config not found!")

    @staticmethod
    def initiate_tornado_apm_client(app):
        from elasticapm.contrib.tornado import ElasticAPM
        config = Utility.initiate_apm_client_config()
        if config:
            app.settings['ELASTIC_APM'] = config
            ElasticAPM(app)

    @staticmethod
    def initiate_fastapi_apm_client():
        from elasticapm.contrib.starlette import make_apm_client
        config = Utility.initiate_apm_client_config()
        if config:
            return make_apm_client(config)

    @staticmethod
    def trigger_history_server_request(bot: Text, endpoint: Text, request_body: dict, request_method: str = 'GET',
                                       return_json: bool = True):
        from kairon.shared.data.processor import MongoProcessor

        headers = {}
        mongo_processor = MongoProcessor()
        history_server = mongo_processor.get_history_server_endpoint(bot)
        if not Utility.check_empty_string(history_server.get('token')):
            headers = {'Authorization': history_server['token']}
        url = urljoin(history_server['url'], endpoint)
        try:
            logger.info(f"url : {url} {request_body}")
            response = requests.request(request_method, url, headers=headers, json=request_body)
            logger.info(f"url : {response.url} {response.request.body}")
            if return_json:
                return response.json()
            else:
                return response
        except requests.exceptions.ConnectionError as e:
            logger.error(str(e))
            raise AppException(f'Unable to connect to history server: {str(e)}')

    @staticmethod
    def encrypt_message(msg: Text):
        from cryptography.fernet import Fernet

        key = Utility.environment['security']["fernet_key"]
        fernet = Fernet(key.encode('utf-8'))
        encoded_msg = msg.encode('utf-8')
        encrypted_msg = fernet.encrypt(encoded_msg)
        return encrypted_msg.decode('utf-8')

    @staticmethod
    def decrypt_message(msg: Text):
        from cryptography.fernet import Fernet

        key = Utility.environment['security']["fernet_key"]
        fernet = Fernet(key.encode('utf-8'))
        encoded_msg = msg.encode('utf-8')
        decrypted_msg = fernet.decrypt(encoded_msg)
        return decrypted_msg.decode('utf-8')

    @staticmethod
    def load_default_actions():
        from kairon.importer.validator.file_validator import DEFAULT_ACTIONS

        return list(DEFAULT_ACTIONS - {"action_default_fallback", "action_two_stage_fallback"})

    @staticmethod
    def get_latest_model(bot: Text):
        """
        fetches the latest model from the path

        :param bot: bot id
        :return: latest model path
        """
        from rasa.shared.constants import DEFAULT_MODELS_PATH

        model_file = os.path.join(DEFAULT_MODELS_PATH, bot)
        return Utility.get_latest_file(model_file, "*.tar.gz")

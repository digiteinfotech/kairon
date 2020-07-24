import glob
import os
import re
import shutil
import string
import tempfile
from glob import glob, iglob
from html import escape
from io import BytesIO
from secrets import choice
from typing import Text, List, Dict
from smtplib import SMTP
from smart_config import ConfigLoader

import requests
import yaml
from fastapi.security import OAuth2PasswordBearer
from mongoengine import StringField, ListField
from mongoengine.document import BaseDocument, Document
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
from rasa.constants import DEFAULT_CONFIG_PATH, DEFAULT_DATA_PATH, DEFAULT_DOMAIN_PATH
from rasa.constants import DEFAULT_MODELS_PATH
from rasa.core import config as configuration
from rasa.core.tracker_store import MongoTrackerStore
from rasa.core.training.structures import StoryGraph
from rasa.importers.rasa import Domain
from rasa.nlu.components import ComponentBuilder
from rasa.nlu.config import RasaNLUModelConfig
from rasa.nlu.training_data import TrainingData
from rasa.nlu.training_data.formats.markdown import MarkdownReader
from rasa.nlu.training_data.formats.markdown import entity_regex
from mongoengine.errors import ValidationError

from .exceptions import AppException
from jwt import encode, decode
from datetime import datetime, timedelta
from loguru import logger
from pathlib import Path
from json import loads

from validators import ValidationFailure
from validators import email as mail_check
class Utility:
    """
    Class contains logic for various utilities
    """

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
    environment = None
    password_policy = PasswordPolicy.from_names(
        length=8,  # min length: 8
        uppercase=1,  # need min. 1 uppercase letters
        numbers=1,  # need min. 1 digits
        special=1,  # need min. 1 special characters
    )
    markdown_reader = MarkdownReader()
    email_conf = None

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
                for entity in entities:
                    example = example.replace(
                        entity["value"],
                        "[" + entity["value"] + "](" + entity["entity"] + ")",
                    )
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
            return yaml.load(fp, yaml.FullLoader)

    @staticmethod
    def load_evironment():
        """
        Loads the environment variables and their values from the
        system.yaml file for defining the working environment of the app

        :return: None
        """
        Utility.environment = ConfigLoader(os.getenv("system_file", "./system.yaml")).get_config()

    @staticmethod
    def validate_fields(fields: Dict, data: Dict):
        """
        validate fields

        :param fields: fields
        :param data: data
        :return: None
        """
        error = ""
        for key, value in fields.items():
            if isinstance(value, StringField):
                if data[key] != None and str(data["key"]).strip():
                    error += "\n " + key + " cannot be empty or blank spaces"
            elif isinstance(value, ListField):
                if value.required and value:
                    error += "\n " + key + " cannot be empty"
        if error:
            raise error

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
    def check_empty_list_elements(items: List[Text]):
        """
        checks if any of the input strings are empty

        :param items: text list
        :return: boolean
        """
        for item in items:
            if Utility.check_empty_string(item):
                return True
        return False

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
        except requests.exceptions.ConnectionError as e:
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
    def save_files(nlu: bytes, domain: bytes, stories: bytes, config: bytes):
        """
        convert mongo data  to individual files

        :param nlu: nlu data
        :param domain: domain data
        :param stories: stories data
        :param config: config data
        :return: files path
        """
        temp_path = tempfile.mkdtemp()
        data_path = os.path.join(temp_path, DEFAULT_DATA_PATH)
        os.makedirs(data_path)
        nlu_path = os.path.join(data_path, "nlu.md")
        domain_path = os.path.join(temp_path, DEFAULT_DOMAIN_PATH)
        stories_path = os.path.join(data_path, "stories.md")
        config_path = os.path.join(temp_path, DEFAULT_CONFIG_PATH)
        Utility.write_to_file(nlu_path, nlu)
        Utility.write_to_file(domain_path, domain)
        Utility.write_to_file(stories_path, stories)
        Utility.write_to_file(config_path, config)
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
        nlu: TrainingData, domain: Domain, stories: StoryGraph, config: Dict, bot: Text
    ):
        """
        adds training files to zip

        :param nlu: nlu data
        :param domain: domain data
        :param stories: stories data
        :param config: config data
        :param bot: bot id
        :return: None
        """
        directory = Utility.save_files(
            nlu.nlu_as_markdown().encode(),
            domain.as_yaml().encode(),
            stories.as_story_string().encode(),
            yaml.dump(config).encode(),
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
            doc_list = document.objects(bot=bot, status=True, **kwargs)
            if doc_list:
                for doc in doc_list:
                    if "status" in document._db_field_map:
                        doc.status = False
                    doc.user = user
                    doc.timestamp = datetime.utcnow()
                    doc.save(validate=False)

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
        db_url = Utility.environment["mongo_url"]
        db_name = Utility.environment["test_conversation_db"]
        username, password, url = Utility.extract_user_password(db_url)
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
        example = re.sub(entity_regex, lambda m: m.groupdict()["entity_text"], text)
        entities = Utility.markdown_reader._find_entities_in_training_example(text)
        return example, entities

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
            type = "text"
        elif RESPONSE.CUSTOM.value in value:
            data = ResponseCustom._from_son(
                {RESPONSE.CUSTOM.value: value[RESPONSE.CUSTOM.value]}
            )
            type = "custom"

        return type, data

    @staticmethod
    def list_directories(path: Text):
        """
        list all the directories in given path

        :param path: directory path
        :return: list of directories
        """
        return list(os.listdir(path))

    @staticmethod
    def list_files(path: Text, extensions=["yml", "yaml"]):
        """
        list all the files in directory

        :param path: directory path
        :param extensions: extension to search
        :return: file list
        """
        files = [glob(os.path.join(path, "*." + extension)) for extension in extensions]
        return sum(files, [])

    @staticmethod
    def validate_rasa_config(config: Dict):
        """
        validates bot config.yml content for invalid entries

        :param config: configuration
        :return: None
        """
        rasa_config = RasaNLUModelConfig(config)
        component_builder = ComponentBuilder()
        for i in range(len(rasa_config.pipeline)):
            component_cfg = rasa_config.for_component(i)
            component_builder.create_component(component_cfg, rasa_config)

        configuration.load(config)


    @staticmethod
    def load_email_configuration():
        """
            Loads the variables from the
            email.yaml file
        """

        Utility.email_conf = ConfigLoader(os.getenv("EMAIL_CONF", "./email.yaml")).get_config()


    @staticmethod
    async def send_mail(email: str, subject: str, body: str):
        """
        Used to send the link for confirmation of new user account

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

        smtp = SMTP(Utility.email_conf["email"]["sender"]["service"], port=Utility.email_conf["email"]["sender"]["port"])
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
            Utility.environment["SECRET_KEY"],
            algorithm=Utility.environment["ALGORITHM"],
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
                Utility.environment["SECRET_KEY"],
                algorithm=Utility.environment["ALGORITHM"],
            )
            mail = decoded_jwt["mail_id"]
            return mail

        except Exception:
            raise AppException("Invalid token")

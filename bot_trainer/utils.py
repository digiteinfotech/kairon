import glob
import os
import re
import shutil
import string
import tempfile
from html import escape
from io import BytesIO
from secrets import choice
from typing import Text, List, Dict

import requests
import yaml
from fastapi.security import OAuth2PasswordBearer
from mongoengine import StringField, ListField
from mongoengine.document import BaseDocument, Document
from passlib.context import CryptContext
from password_strength import PasswordPolicy
from password_strength.tests import Special, Uppercase, Numbers, Length
from pymongo.uri_parser import SRV_SCHEME_LEN, SCHEME, SCHEME_LEN, SRV_SCHEME, parse_userinfo
from rasa.constants import DEFAULT_CONFIG_PATH, DEFAULT_DATA_PATH, DEFAULT_DOMAIN_PATH
from rasa.constants import DEFAULT_MODELS_PATH
from rasa.core.tracker_store import MongoTrackerStore
from rasa.core.training.structures import StoryGraph
from rasa.importers.rasa import Domain
from rasa.nlu.training_data import TrainingData
from rasa.nlu.training_data.formats.markdown import MarkdownReader

from bot_trainer.exceptions import AppException


class Utility:
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

    @staticmethod
    def check_empty_string(value: str):
        """ Checks for an empty string. Returns True if empty or not a string,
            and returns False if it is a string """
        if not value:
            return True
        if not value.strip():
            return True
        else:
            return False

    @staticmethod
    def prepare_nlu_text(example: Text, entities: List[Dict]):
        """ This function converts the entity data into the format required for the
            nlu file of the bot """
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
        """ Returns the validation results (if the document schema is valid or not)
            of the input documents """
        if documents:
            for document in documents:
                document.validate()

    @staticmethod
    def load_yaml(file: Text):
        """ Loads content from the .yaml file """
        with open(file) as fp:
            return yaml.load(fp, yaml.FullLoader)

    @staticmethod
    def load_evironment():
        """ Loads the environment variables and their values from the
            system.yaml file for defining the working environment of the app """
        environment = Utility.load_yaml(os.getenv("system_file", "./system.yaml"))
        for key in environment:
            if key in os.environ:
                environment[key] = os.getenv(key)
        Utility.environment = environment

    @staticmethod
    def validate_fields(fields: Dict, data: Dict):
        """ Checks if the input fields of a dictionary
            are valid (not empty) and returns an error if not """
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
        """ Verifies the password with the hashed version of the password """
        return Utility.pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def get_password_hash(password):
        """ Returns the hashed version of the input password """
        if not Utility.check_empty_string(password):
            return Utility.pwd_context.hash(password)

    @staticmethod
    def get_latest_file(folder):
        """ Gets the latest file in a folder """
        if not os.path.exists(folder):
            raise AppException("Folder does not exists!")
        return max(glob.iglob(folder + "/*"), key=os.path.getctime)

    @staticmethod
    def check_empty_list_elements(items: List[Text]):
        """ Checks if the input strings are empty. Returns True if empty and False,
            if not """
        for item in items:
            if Utility.check_empty_string(item):
                return True
        return False

    @staticmethod
    def deploy_model(endpoint: Dict, bot: Text):
        """ Deploys the chatbot to the specified endpoint """
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
            model_file = Utility.get_latest_file(
                        os.path.join(DEFAULT_MODELS_PATH, bot))
            response = requests.put(
                url + "/model",
                json={
                    "model_file": model_file
                },
                headers=headers,
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
    def generate_password(size=6, chars=string.ascii_uppercase + string.digits):
        return "".join(choice(chars) for _ in range(size))

    @staticmethod
    def save_files(nlu: bytes, domain: bytes, stories: bytes, config: bytes):
        """save nlu, domain, stories and config data to files in temporary location."""
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
        """open the files in binary mode and write to it"""
        with open(file, "wb") as w:
            w.write(data)
            w.flush()

    @staticmethod
    def delete_directory(path: Text):
        """delete file directory"""
        shutil.rmtree(path)

    @staticmethod
    def create_zip_file(
            nlu: TrainingData, domain: Domain, stories: StoryGraph, config: Dict, bot: Text
    ):

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
        data = BytesIO()
        with open(file, "rb") as fo:
            data.write(fo.read())
        data.seek(0)
        os.remove(file)
        return data

    @staticmethod
    def valid_password(password: Text):
        """Used to validate password against the password policy"""
        results = Utility.password_policy.test(password)
        if results:
            response = []
            for result in results:
                if isinstance(result, Length):
                    response.append("Password length must be " + str(result.length))
                elif isinstance(result, Special):
                    response.append("Missing " + str(result.count) + " special letter")
                elif isinstance(result, Uppercase):
                    response.append("Missing " + str(result.count) + " uppercase letter")
                elif isinstance(result, Numbers):
                    response.append("Missing " + str(result.count) + "number")

            if response:
                raise AppException("\n".join(response))

    @staticmethod
    def delete_document(documents : List[Document], bot: Text, user: Text):
        for document in documents:
            doc_list = document.objects(bot=bot)
            if doc_list:
                doc_list.update(set__status=False, set__user=user)

    @staticmethod
    def extract_user_password(uri: str):
        if uri.startswith(SCHEME):
            scheme_free = uri[SCHEME_LEN:]
            scheme = uri[:SCHEME_LEN]
        elif uri.startswith(SRV_SCHEME):
            scheme_free = uri[SRV_SCHEME_LEN:]
            scheme = uri[:SRV_SCHEME_LEN]

        host_part, _, path_part = scheme_free.partition('/')
        if '@' in host_part:
            userinfo, _, hosts = host_part.rpartition('@')
            user, passwd = parse_userinfo(userinfo)
            return user, passwd, scheme + hosts
        else:
            return None, None, scheme + host_part

    @staticmethod
    def get_local_mongo_store(bot: Text, domain:  Domain):
        db_url = Utility.environment['mongo_url']
        db_name = Utility.environment['test_conversation_db']
        username, password, url = Utility.extract_user_password(db_url)
        return MongoTrackerStore(domain=domain,
                          host=url,
                          db=db_name,
                          collection=bot,
                          username=username,
                          password=password)

    @staticmethod
    def special_match(strg, search=re.compile(r'[^a-zA-Z0-9_]').search):
        return not bool(search(strg))
import ast
import asyncio
import json
import os
import re
import shutil
import string
import tempfile
from datetime import datetime, timedelta, date
from dateutil import tz
import pytz
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from glob import glob, iglob
from html import escape
from io import BytesIO
from pathlib import Path
from secrets import choice
from smtplib import SMTP
from typing import Text, List, Dict, Union
from urllib.parse import unquote_plus
from urllib.parse import urljoin

import pandas as pd
import requests
import yaml
from botocore.exceptions import ClientError
from fastapi import File, UploadFile
from jwt import encode, decode, PyJWTError
from loguru import logger
from mongoengine.document import BaseDocument, Document
from mongoengine.errors import ValidationError
from mongoengine.queryset.visitor import QCombination
from networkx import DiGraph, Graph, is_connected, recursive_simple_cycles
from passlib.context import CryptContext
from password_strength import PasswordPolicy
from password_strength.tests import Special, Uppercase, Numbers, Length
from pymongo import MongoClient
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
from urllib3.util import parse_url
from validators import ValidationFailure
from validators import email as mail_check
from websockets import connect

from .actions.models import ActionParameterType
from .constants import MaskingStrategy, SYSTEM_TRIGGERED_UTTERANCES
from .constants import EventClass
from .data.base_data import AuditLogData
from .data.constant import TOKEN_TYPE, AuditlogActions, KAIRON_TWO_STAGE_FALLBACK
from .data.dto import KaironStoryStep
from .models import StoryStepType
from ..exceptions import AppException


class Utility:
    """Class contains logic for various utilities"""
    environment = {}
    email_conf = {}
    system_metadata = {}
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
                elif isinstance(result, Numbers):
                    response.append("Missing " + str(result.count) + " number")
                elif isinstance(result, Uppercase):
                    response.append(
                        "Missing " + str(result.count) + " uppercase letter"
                    )

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
        Utility.load_system_metadata()

    @staticmethod
    def load_system_metadata():
        """
        Loads the metadata for various actions including integrations
        and role based access control.

        :return: None
        """
        parent_dir = "./metadata"
        files = next(os.walk(parent_dir), (None, None, []))[2]
        for file in files:
            Utility.system_metadata.update(Utility.load_yaml(os.path.join(parent_dir, file)))

    @staticmethod
    def retrieve_field_values(
            document: Document, field: str, *args, **kwargs
    ):
        """
        Retrieve particular fields in document if exists, else returns None.
        This should only be used when the field is a required field in the document.

        :param document: document type
        :param field: field to retrieve from documents
        :param kwargs: filter parameters
        :return: list of values for a particular field if document exists else None
        """
        documents = document.objects(args, **kwargs)
        values = None
        if documents.__len__():
            values = [getattr(doc, field) for doc in documents]
        return values

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
            document: Document, query: QCombination, exp_message: Text = None, raise_error=True
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
        logger.info(f"Model path: {folder}")
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
    def delete_directory(path: Text, ignore_errors: bool = False):
        """
        deletes directory with all files

        :param path: directory path
        :param ignore_errors: ignore errors
        :return: None
        """
        logger.info(f"deleting data from path: {path}")
        shutil.rmtree(path, ignore_errors)

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
        from kairon.shared.data.signals import push_bulk_update_notification

        for document in documents:
            kwargs['bot'] = bot
            update = {'set__user': user, 'set__timestamp': datetime.utcnow()}
            if "status" in document._db_field_map:
                kwargs['status'] = True
                update['set__status'] = False
            fetched_documents = document.objects(**kwargs)
            if fetched_documents.count() > 0:
                list(fetched_documents)
                fetched_documents.update(**update)
                kwargs['event_type'] = 'delete'
                push_bulk_update_notification(document, fetched_documents, **kwargs)

    @staticmethod
    def hard_delete_document(documents: List[Document], bot: Text, **kwargs):
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
        from kairon.shared.trackers import KMongoTrackerStore
        config = Utility.get_local_db()
        return KMongoTrackerStore(
            domain=domain,
            host=config['host'],
            db=config['db'],
            collection=bot,
            username=config.get('username'),
            password=config.get('password'),
            auth_source=config['options'].get("authSource") if config['options'].get("authSource") else "admin"
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
    def convert_date_to_string(date_obj: date = datetime.utcnow().date()):
        return date_obj.strftime("%Y-%m-%d")

    @staticmethod
    def get_timestamp_from_date(date_obj: date = datetime.utcnow().date()):
        date_time = datetime.now().replace(date_obj.year, date_obj.month, date_obj.day)
        return date_time.timestamp()

    @staticmethod
    def validate_from_date_and_to_date(from_date: date, to_date: date):
        six_months_back_date = (datetime.utcnow() - timedelta(6 * 30)).date()
        today_date = datetime.utcnow().date()
        if six_months_back_date > from_date or from_date > today_date:
            raise AppException("from_date should be within six months and today date")
        elif six_months_back_date > to_date or to_date > today_date:
            raise AppException("to_date should be within six months and today date")
        elif from_date >= to_date:
            raise AppException("from_date must be less than to_date")

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
    def http_request(method: str, url: str, token: str = None, user: str = None, json_dict: Dict = None):
        logger.info("agent event started " + url)
        headers = {'content-type': 'application/json'}
        if user:
            headers['X-USER'] = user
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if method.lower() == 'get':
            response = requests.request(method, url, headers=headers, params=json_dict)
        else:
            response = requests.request(method, url, headers=headers, json=json_dict)
        logger.info("agent event completed" + response.content.decode('utf8'))
        return response.content.decode('utf8')

    @staticmethod
    async def websocket_request(uri: Text, msg: Text):
        logger.info(f'initiating websocket connection: {uri}')
        async with connect(uri) as web_socket:
            await web_socket.send(msg)
            await web_socket.close()
        logger.info("websocket request completed")

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
    async def format_and_send_mail(mail_type: str, email: str, first_name: str, url: str = None, **kwargs):
        if mail_type == 'password_reset':
            body = Utility.email_conf['email']['templates']['password_reset']
            body = body.replace('FIRST_NAME', first_name.capitalize())
            subject = Utility.email_conf['email']['templates']['password_reset_subject']
        elif mail_type == 'password_reset_confirmation':
            body = Utility.email_conf['email']['templates']['password_reset_confirmation']
            subject = Utility.email_conf['email']['templates']['password_changed_subject']
        elif mail_type == 'verification':
            body = Utility.email_conf['email']['templates']['verification']
            body = body.replace('FIRST_NAME', first_name.capitalize())
            subject = Utility.email_conf['email']['templates']['confirmation_subject']
        elif mail_type == 'verification_confirmation':
            body = Utility.email_conf['email']['templates']['verification_confirmation']
            body = body.replace('FIRST_NAME', first_name.capitalize())
            subject = Utility.email_conf['email']['templates']['confirmed_subject']
        elif mail_type == 'add_member':
            body = Utility.email_conf['email']['templates']['add_member_invitation']
            body = body.replace('BOT_NAME', kwargs.get('bot_name', ""))
            body = body.replace('BOT_OWNER_NAME', first_name.capitalize())
            body = body.replace('ACCESS_TYPE', kwargs.get('role', ""))
            body = body.replace('ACCESS_URL', url)
            subject = Utility.email_conf['email']['templates']['add_member_subject']
            subject = subject.replace('BOT_NAME', kwargs.get('bot_name', ""))
        elif mail_type == 'add_member_confirmation':
            body = Utility.email_conf['email']['templates']['add_member_confirmation']
            body = body.replace('BOT_NAME', kwargs.get('bot_name', ""))
            body = body.replace('ACCESS_TYPE', kwargs.get('role', ""))
            body = body.replace('INVITED_PERSON_NAME', kwargs.get('accessor_email', ""))
            subject = Utility.email_conf['email']['templates']['add_member_confirmation_subject']
            subject = subject.replace('INVITED_PERSON_NAME', kwargs.get('accessor_email', ""))
        elif mail_type == 'update_role_member_mail':
            body = Utility.email_conf['email']['templates']['update_role']
            body = body.replace('MAIL_BODY_HERE',
                                Utility.email_conf['email']['templates']['update_role_member_mail_body'])
            body = body.replace('BOT_NAME', kwargs.get('bot_name', ""))
            body = body.replace('NEW_ROLE', kwargs.get('new_role', ""))
            body = body.replace('STATUS', kwargs.get('status', ""))
            body = body.replace('MODIFIER_NAME', first_name.capitalize())
            subject = Utility.email_conf['email']['templates']['update_role_subject']
            subject = subject.replace('BOT_NAME', kwargs.get('bot_name', ""))
        elif mail_type == 'update_role_owner_mail':
            body = Utility.email_conf['email']['templates']['update_role']
            body = body.replace('MAIL_BODY_HERE',
                                Utility.email_conf['email']['templates']['update_role_owner_mail_body'])
            body = body.replace('MEMBER_EMAIL', kwargs.get('member_email', ""))
            body = body.replace('BOT_NAME', kwargs.get('bot_name', ""))
            body = body.replace('NEW_ROLE', kwargs.get('new_role', ""))
            body = body.replace('STATUS', kwargs.get('status', ""))
            body = body.replace('MODIFIER_NAME', first_name.capitalize())
            subject = Utility.email_conf['email']['templates']['update_role_subject']
            subject = subject.replace('BOT_NAME', kwargs.get('bot_name', ""))
        elif mail_type == 'transfer_ownership_mail':
            body = Utility.email_conf['email']['templates']['update_role']
            body = body.replace('MAIL_BODY_HERE',
                                Utility.email_conf['email']['templates']['transfer_ownership_mail_body'])
            body = body.replace('MEMBER_EMAIL', kwargs.get('member_email', ""))
            body = body.replace('BOT_NAME', kwargs.get('bot_name', ""))
            body = body.replace('NEW_ROLE', kwargs.get('new_role', ""))
            body = body.replace('MODIFIER_NAME', first_name.capitalize())
            subject = Utility.email_conf['email']['templates']['update_role_subject']
            subject = subject.replace('BOT_NAME', kwargs.get('bot_name', ""))
        elif mail_type == 'password_generated':
            body = Utility.email_conf['email']['templates']['password_generated']
            body = body.replace('PASSWORD', kwargs.get('password', ""))
            subject = Utility.email_conf['email']['templates']['password_generated_subject']
        elif mail_type == 'untrusted_login':
            geo_location = ""
            reset_password_url = Utility.email_conf["app"]["url"] + "/reset_password"
            body = Utility.email_conf['email']['templates']['untrusted_login']
            for key, value in kwargs.items():
                geo_location = f"{geo_location}<li>{key}: {value}</li>"
            body = body.replace('GEO_LOCATION', geo_location)
            body = body.replace('TRUST_DEVICE_URL', url)
            body = body.replace('RESET_PASSWORD_URL', reset_password_url)
            subject = Utility.email_conf['email']['templates']['untrusted_login_subject']
        elif mail_type == 'add_trusted_device':
            geo_location = ""
            body = Utility.email_conf['email']['templates']['add_trusted_device']
            for key, value in kwargs.items():
                geo_location = f"{geo_location}<li>{key}: {value}</li>"
            body = body.replace('GEO_LOCATION', geo_location)
            subject = Utility.email_conf['email']['templates']['add_trusted_device']
        else:
            logger.debug('Skipping sending mail as no template found for the mail type')
            return
        body = body.replace('FIRST_NAME', first_name)
        body = body.replace('USER_EMAIL', email)
        if url:
            body = body.replace('VERIFICATION_LINK', url)
        await Utility.validate_and_send_mail(email, subject, body)

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
    async def trigger_smtp(email: str, subject: str, body: str, content_type='html'):
        """
        Sends an email to the mail id of the recipient

        :param email: the mail id of the recipient
        :param subject: the subject of the mail
        :param body: the body of the mail
        :param content_type: "plain" or "html" content
        :return: None
        """
        await Utility.trigger_email([email],
                                    subject,
                                    body,
                                    content_type=content_type,
                                    smtp_url=Utility.email_conf["email"]["sender"]["service"],
                                    smtp_port=Utility.email_conf["email"]["sender"]["port"],
                                    sender_email=Utility.email_conf["email"]["sender"]["email"],
                                    smtp_userid=Utility.email_conf["email"]["sender"]["userid"],
                                    smtp_password=Utility.email_conf["email"]["sender"]["password"],
                                    tls=True)

    @staticmethod
    async def trigger_email(email: List[str],
                            subject: str,
                            body: str,
                            smtp_url: str,
                            smtp_port: int,
                            sender_email: str,
                            smtp_password: str,
                            smtp_userid: str = None,
                            tls: bool = False,
                            content_type='html'):
        """
        Sends an email to the mail id of the recipient

        :param smtp_userid:
        :param sender_email:
        :param tls:
        :param smtp_port:
        :param smtp_url:
        :param email: the mail id of the recipient
        :param subject: the subject of the mail
        :param body: the body of the mail
        :param content_type: "plain" or "html" content
        :return: None
        """
        smtp = SMTP(smtp_url, port=smtp_port, timeout=10)
        smtp.connect(smtp_url, smtp_port)
        if tls:
            smtp.starttls()
        smtp.login(smtp_userid if
                   smtp_userid else
                   sender_email,
                   smtp_password)
        from_addr = sender_email
        body = MIMEText(body, content_type)
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = from_addr
        msg['To'] = ",".join(email)
        msg.attach(body)
        smtp.sendmail(from_addr, email, msg.as_string())
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
        root_dir = root_dir.replace("\\", "/")
        files = ['nlu.yml', 'domain.yml', 'config.yml', 'stories.yml', 'nlu.yaml', 'domain.yaml', 'config.yaml',
                 'stories.yaml', 'nlu.md', 'stories.md']
        for file in files:
            file_regex = regex.format(root_dir, file)
            msg = re.sub(file_regex, file, msg)
        return msg

    @staticmethod
    def build_lambda_payload(env_var: dict):
        """Creates request body for lambda."""
        event_request = [{"name": key.upper(), "value": value} for key, value in env_var.items()]
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
        Used to encode the mail id into a token.

        :param email: mail id of the recipient
        :param minutes_to_expire: time in minutes until the token expires
        :return: the token with encoded mail id
        """
        encoded_jwt = Utility.generate_token_payload({"mail_id": email}, minutes_to_expire)
        return encoded_jwt

    @staticmethod
    def generate_token_payload(payload: dict, minutes_to_expire=1440):
        """
        Used to encode the payload of type dict into a token.

        :param payload: dict data
        :param minutes_to_expire: time in minutes until the token expires
        :return: the token
        """

        expire = datetime.utcnow() + timedelta(minutes=minutes_to_expire)
        payload.update({"exp": expire})
        encoded_jwt = encode(
            payload,
            Utility.environment['security']["secret_key"],
            algorithm=Utility.environment['security']["algorithm"],
        )
        return encoded_jwt

    @staticmethod
    def verify_token(token: str):
        """
        Used to check if token is valid

        :param token: the token from the confirmation link
        :return: decoded_jwt
        """
        try:
            decoded_jwt = Utility.decode_limited_access_token(token)
            return decoded_jwt

        except Exception as e:
            raise AppException("Invalid token")

    @staticmethod
    def decode_limited_access_token(token: Text):
        try:
            decoded_jwt = decode(
                token,
                Utility.environment['security']["secret_key"],
                algorithms=[Utility.environment['security']["algorithm"]],
            )
            return decoded_jwt
        except PyJWTError:
            raise PyJWTError("Invalid token")

    @staticmethod
    def validate_bot_specific_token(bot: Text, token: Text):
        from kairon.shared.account.processor import AccountProcessor

        claims = Utility.decode_limited_access_token(token)
        bot_config = AccountProcessor.get_bot(bot)
        multilingual_bots = list(AccountProcessor.get_multilingual_bots(bot))
        multilingual_bots = set(map(lambda bot_info: bot_info["id"], multilingual_bots))

        if bot_config['account'] != claims['account'] or bot not in multilingual_bots:
            raise AppException("Invalid token")
        return claims

    @staticmethod
    def load_json_file(path: Text, raise_exc: bool = True):
        if not os.path.exists(path) and raise_exc:
            raise AppException('file not found')
        config = json.load(open(path))
        return config

    @staticmethod
    def download_csv(data, message="No data available!", filename="conversation_history.csv"):
        if not data:
            raise AppException(message)
        else:
            df = pd.json_normalize(data)
            for col in df.columns:
                if col.endswith(".$date"):
                    col_name = col.replace(".$date", "")
                    df[col_name] = pd.to_datetime(df[col], unit="ms")
                    df = df.drop(col, axis=1)
            temp_path = tempfile.mkdtemp()
            file_path = os.path.join(temp_path, filename)
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
                            stories, rules=None, actions: dict = None):
        """
        convert mongo data  to individual files

        :param nlu: nlu data
        :param domain: domain data
        :param stories: stories data
        :param config: config data
        :param rules: rules data
        :param actions: action configuration data
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
        actions_path = os.path.join(temp_path, "actions.yml")

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
        if actions:
            actions_as_str = yaml.dump(actions).encode()
            Utility.write_to_file(actions_path, actions_as_str)
        return temp_path

    @staticmethod
    def create_zip_file(
            nlu, domain, stories, config: Dict, bot: Text,
            rules=None,
            actions: Dict = None
    ):
        """
        adds training files to zip

        :param nlu: nlu data
        :param domain: domain data
        :param stories: stories data
        :param config: config data
        :param bot: bot id
        :param rules: rules data
        :param actions: action configurations
        :return: None
        """
        directory = Utility.write_training_data(
            nlu,
            domain,
            config,
            stories,
            rules,
            actions
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
            token, _ = Authentication.generate_integration_token(bot, email, expiry=5, token_type=TOKEN_TYPE.CHANNEL.value)
            response = Utility.http_request('post', urljoin(agent_url, f"/api/bot/{bot}/chat"), token,
                                            user, json_dict={'data': data})
            return json.loads(response)
        else:
            raise AppException("Agent config not found!")

    @staticmethod
    def reload_model(bot: Text, email: Text):
        if Utility.environment.get('model') and Utility.environment['model']['agent'].get('url'):
            from kairon.shared.auth import Authentication
            agent_url = Utility.environment['model']['agent'].get('url')
            token, _ = Authentication.generate_integration_token(bot, email, expiry=5, token_type=TOKEN_TYPE.CHANNEL.value)
            response = Utility.http_request('get', urljoin(agent_url, f"/api/bot/{bot}/reload"), token, email)
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
    def record_custom_metric_apm(**kwargs):
        import elasticapm
        if Utility.environment['elasticsearch']['enable']:
            elasticapm.label(**kwargs)

    @staticmethod
    def trigger_history_server_request(bot: Text, endpoint: Text, request_body: dict = None, request_method: str = 'GET',
                                       return_json: bool = True):
        from kairon.shared.data.processor import MongoProcessor

        headers = {}
        mongo_processor = MongoProcessor()
        history_server = mongo_processor.get_history_server_endpoint(bot)
        if not Utility.check_empty_string(history_server.get('token')):
            headers = {'Authorization': f'Bearer {history_server["token"]}'}
        if not request_body:
            request_body = {}
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
    def prepare_form_validation_semantic(validations: dict):
        semantic = {}
        if validations:
            parent_operator = validations.get('logical_operator')
            expressions = validations.get('expressions')
            validation_semantic = []
            for exp in expressions:
                if exp.get('logical_operator'):
                    validation_semantic.append({exp['logical_operator']: exp.get('validations')})
                else:
                    validation_semantic.extend(exp.get('validations'))
            semantic = {parent_operator: validation_semantic}
        return semantic

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

    @staticmethod
    def delete_models(bot: Text):
        """
        fetches the latest model from the path

        :param bot: bot id
        :return: latest model path
        """
        from rasa.shared.constants import DEFAULT_MODELS_PATH

        retain_cnt = Utility.environment["model"]["retention"]
        model_file = os.path.join(DEFAULT_MODELS_PATH, bot, "old_model", "*.tar.gz")
        file_list = glob(model_file)
        file_list.sort(key=os.path.getctime, reverse=True)
        for file in file_list[retain_cnt:]:
            os.remove(file)
        return file_list

    @staticmethod
    def is_model_file_exists(bot: Text, raise_exc: bool = True):
        try:
            Utility.get_latest_model(bot)
            return True
        except AppException as e:
            logger.exception(e)
            if raise_exc:
                raise AppException('No model trained yet. Please train a model to test')
            return False

    @staticmethod
    def word_list_to_frequency(wordlist):
        wordfreq = [wordlist.count(p) for p in wordlist]
        return dict(list(zip(wordlist, wordfreq)))

    @staticmethod
    def sort_frequency_dict(freqdict):
        aux = [(freqdict[key], key) for key in freqdict]
        aux.sort()
        aux.reverse()
        return aux

    @staticmethod
    def get_imports(path):
        with open(path) as fh:
            root = ast.parse(fh.read(), path)

        for node in ast.iter_child_nodes(root):
            if not(isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom)):
                continue

            for n in node.names:
                yield n.name.split('.')[0]

    @staticmethod
    def validate_smtp(smtp_url: str, port: int):
        try:
            logger.info('validating smtp details')
            smtp = SMTP(timeout=10)
            smtp.connect(smtp_url, port)
            smtp.quit()
            return True
        except Exception as e:
            logger.exception(e)
            return False

    @staticmethod
    def check_is_enabled(sso_type: str, raise_error_is_not_enabled=True):
        """
        Checks if sso login for the sso_type is enabled in system.yaml.
        Valid sso_type: facebook, linkedin, google
        """
        is_enabled = Utility.environment.get("sso", {}).get(sso_type, {}).get('enable', False)
        if not is_enabled and raise_error_is_not_enabled:
            raise AppException(f'{sso_type} login is not enabled')
        return is_enabled

    @staticmethod
    def get_app_properties():
        properties = {
            'sso': {
                'facebook': Utility.check_is_enabled('facebook', False),
                'linkedin': Utility.check_is_enabled('linkedin', False),
                'google': Utility.check_is_enabled('google', False)
            },
            'enable_sso_only': Utility.environment["app"]["enable_sso_only"],
            'enable_apm': Utility.environment["elasticsearch"]["enable"],
            'enable_notifications': Utility.environment["notifications"]["enable"],
            'enable_multilingual': Utility.environment["multilingual"]["enable"],
            'validate_trusted_device': Utility.environment["user"]["validate_trusted_device"],
            'validate_recaptcha': Utility.environment["security"]["validate_recaptcha"],
        }
        return properties

    @staticmethod
    def push_notification(channel: Text, event_type: Text, collection: Text, metadata: dict):
        push_server_endpoint = Utility.environment['notifications']['server_endpoint']
        push_server_endpoint = urljoin(push_server_endpoint, channel)

        payload = {
            'event_type': event_type,
            'event': {
                'entity_type': collection,
                'data': metadata
            }
        }
        token = Utility.generate_token('push-server@digite.com', 1)
        headers = {"Authorization": token}
        io_loop = asyncio.get_event_loop()
        io_loop.run_until_complete(
            Utility.execute_http_request(request_method='POST', http_url=push_server_endpoint, request_body=payload,
                                         headers=headers)
        )

    @staticmethod
    def get_slack_team_info(token: Text):
        from slack import WebClient
        from slack.errors import SlackApiError

        try:
            response = WebClient(token).team_info()
            return {"id": response.data['team']['id'], "name": response.data['team']['name']}
        except SlackApiError as e:
            logger.exception(e)
            raise AppException(e)

    @staticmethod
    def validate_channel_config(channel, config, error, encrypt=True):
        if channel in list(Utility.system_metadata['channels'].keys()):
            for required_field in Utility.system_metadata['channels'][channel]['required_fields']:
                if required_field not in config:
                    raise error(
                        f"Missing {Utility.system_metadata['channels'][channel]['required_fields']} all or any in config")
                else:
                    if encrypt:
                        config[required_field] = Utility.encrypt_message(config[required_field])
        else:
            raise error(f"Invalid channel type {channel}")

    @staticmethod
    def get_channels():
        if Utility.system_metadata.get("channels"):
            return list(Utility.system_metadata['channels'].keys())
        else:
            return []

    @staticmethod
    def get_live_agents():
        return list(Utility.system_metadata.get('live_agents', {}).keys())

    @staticmethod
    def validate_live_agent_config(agent_type, config, error):
        if agent_type in list(Utility.system_metadata.get('live_agents', {}).keys()):
            for required_field in Utility.system_metadata['live_agents'][agent_type]['required_fields']:
                if required_field not in config:
                    raise error(
                        f"Missing {Utility.system_metadata['live_agents'][agent_type]['required_fields']} all or any in config")
        else:
            raise error("Agent system not supported")

    @staticmethod
    def register_telegram_webhook(access_token, webhook_url):
        api = Utility.system_metadata['channels']['telegram']['api']['url']
        response = Utility.http_request("GET", url=f"{api}/bot{access_token}/setWebhook", json_dict={"url": webhook_url})
        response_json = json.loads(response)
        if 'error_code' in response_json:
            raise ValidationError(response_json['description'])

    @staticmethod
    def filter_bot_details_for_integration_user(bot: Text, available_bots: dict):
        for bot_details in available_bots['account_owned']:
            if bot_details['_id'] == bot:
                return {'account_owned': [bot_details], 'shared': []}

        for bot_details in available_bots['shared']:
            if bot_details['_id'] == bot:
                return {'account_owned': [], 'shared': [bot_details]}

    @staticmethod
    def upload_bot_assets_to_s3(bot, asset_type, file_path):
        from kairon.shared.cloud.utils import CloudUtility

        bucket = Utility.environment['storage']['assets'].get('bucket')
        root_dir = Utility.environment['storage']['assets'].get('root_dir')
        extension = Path(file_path).suffix
        if extension not in Utility.environment['storage']['assets'].get('allowed_extensions'):
            raise AppException(f'Only {Utility.environment["storage"]["assets"].get("allowed_extensions")} type files allowed')
        output_filename = os.path.join(root_dir, bot, f"{asset_type}{extension}")
        try:
            url = CloudUtility.upload_file(file_path, bucket, output_filename)
            return url, output_filename
        except ClientError as e:
            logger.exception(e)
            raise AppException("File upload failed")

    @staticmethod
    def delete_bot_assets_on_s3(file):
        from kairon.shared.cloud.utils import CloudUtility

        bucket = Utility.environment['storage']['assets'].get('bucket')
        CloudUtility.delete_file(bucket, file)

    @staticmethod
    def execute_http_request(
            request_method: str, http_url: str, request_body: dict = None, headers: dict = None,
            return_json: bool = True, **kwargs
    ):
        """
        Executes http urls provided.

        :param http_url: HTTP url to be executed
        :param request_method: One of GET, PUT, POST, DELETE
        :param request_body: Request body to be sent with the request
        :param headers: header for the HTTP request
        :param return_json: return api output as json
        :param kwargs:
            validate_status: To validate status_code in response. False by default.
            expected_status_code: 200 by default
            err_msg: error message to be raised in case expected status code not received
        :return: dict/response object
        """
        if not headers:
            headers = {}

        if request_body is None:
            request_body = {}
        try:
            logger.info(f"Event started: {http_url}")
            if request_method.lower() == 'get':
                response = requests.request(
                    request_method.upper(), http_url, data=request_body, headers=headers, timeout=kwargs.get('timeout')
                )
            elif request_method.lower() in ['post', 'put', 'delete']:
                response = requests.request(
                    request_method.upper(), http_url, json=request_body, headers=headers, timeout=kwargs.get('timeout')
                )
            else:
                raise AppException("Invalid request method!")
            logger.debug("raw response: " + str(response.text))
            logger.debug("status " + str(response.status_code))
        except requests.exceptions.ConnectTimeout:
            _, _, host, _, _, _, _ = parse_url(http_url)
            raise AppException(f"Failed to connect to service: {host}")
        except Exception as e:
            logger.exception(e)
            raise AppException(f"Failed to execute the url: {str(e)}")

        if kwargs.get('validate_status', False) and response.status_code != kwargs.get('expected_status_code', 200):
            if Utility.check_empty_string(kwargs.get('err_msg')):
                raise AppException("err_msg cannot be empty")
            raise AppException(f"{kwargs['err_msg']}{response.reason}")

        if return_json:
            response = response.json()

        return response

    @staticmethod
    def get_event_server_url():
        """
        Retrieves event server URL from system.yml
        """
        if Utility.check_empty_string(Utility.environment['events'].get('server_url')):
            raise AppException("Event server url not found")

        return Utility.environment['events']['server_url']

    @staticmethod
    def request_event_server(event_class: EventClass, payload: dict):
        """
        Trigger request to event server along with payload.
        """
        event_server_url = Utility.get_event_server_url()
        logger.debug(payload)
        resp = Utility.execute_http_request(
            "POST", urljoin(event_server_url, f'/api/events/execute/{event_class}'),
            payload, err_msg=f"Failed to trigger {event_class} event: ", validate_status=True
        )
        if not resp['success']:
            raise AppException(f"Failed to trigger {event_class} event: {resp.get('message', '')}")

    @staticmethod
    def validate_recaptcha(recaptcha_response: str = None, remote_ip: str = None):
        secret = Utility.environment['security'].get('recaptcha_secret', None)
        if Utility.check_empty_string(recaptcha_response):
            raise AppException("recaptcha_response is required")
        captcha_verifier = Utility.environment['security']['recaptcha_url']
        url = f"{captcha_verifier}?secret={secret}&response={recaptcha_response}"
        if not Utility.check_empty_string(remote_ip):
            url = f"{url}&remoteip={remote_ip}"
        resp = Utility.execute_http_request(
            "POST", url, validate_status=True, err_msg="Failed to validate recaptcha: "
        )
        if not resp['success']:
            raise AppException("Failed to validate recaptcha")

    @staticmethod
    def compare_string_constant_time(val1: str, val2: str):
        if len(val1) != len(val2):
            return False
        result = 0
        for x, y in zip(bytes(val1, "utf-8"), bytes(val2, "utf-8")):
            result |= x ^ y
            if result > 0:
                break
        return True if result == 0 else False

    @staticmethod
    def validate_request(request, config):
        """
        This API validate request for whitelisted domains,
        return false if request is from non listed domain

        :param request HTTP request
        :param config chat-client-config

        :return boolean
        """
        from urllib.parse import urlparse
        http_referer = request.headers.get('HTTP_REFERER') if request.headers.get(
            'HTTP_REFERER') is not None else request.headers.get('referer')
        white_listed_domain = config['white_listed_domain'] if config.get('white_listed_domain') is not None else ["*"]

        if "*" in white_listed_domain:
            return True
        referrer_domain = urlparse(http_referer).netloc
        for domain in white_listed_domain:
            if Utility.compare_string_constant_time(referrer_domain, domain):
                return True
        return False

    @staticmethod
    def build_http_request_data_object(params: list):
        from kairon.shared.actions.data_objects import HttpActionRequestBody

        request = []
        for param in params or []:
            Utility.encrypt_action_parameter(param)
            request.append(HttpActionRequestBody(**param).to_mongo().to_dict())
        return request

    @staticmethod
    def encrypt_action_parameter(param: Dict):
        if param['encrypt'] is True and param['parameter_type'] == ActionParameterType.value.value:
            if not Utility.check_empty_string(param['value']):
                param['value'] = Utility.encrypt_message(param['value'])

    @staticmethod
    def decrypt_action_parameter(param: Dict):
        if param['encrypt'] is True and param['parameter_type'] == ActionParameterType.value.value:
            if not Utility.check_empty_string(param['value']):
                param['value'] = Utility.decrypt_message(param['value'])

    @staticmethod
    def create_mongo_client(url: Text):
        config = Utility.extract_db_config(url)
        logger.debug(f"Loading host:{config.get('host')}, db:{config.get('db')}")
        client = MongoClient(host=url)
        return client

    @staticmethod
    def get_masked_value(value: Text):
        unmasked_char_cnt = Utility.environment['security']['unmasked_char_count']
        unmasked_char_strategy = Utility.environment['security']['unmasked_char_strategy']
        if Utility.check_empty_string(value):
            masked_value = value
        elif len(value) <= 4:
            masked_value = '*' * len(value)
        else:
            str_len = len(value)
            mask = '*' * (str_len - unmasked_char_cnt)
            if unmasked_char_strategy == MaskingStrategy.from_left.value:
                masked_value = f"{value[:unmasked_char_cnt]}{mask}"
            elif unmasked_char_strategy == MaskingStrategy.from_right.value:
                masked_value = f"{mask}{value[(str_len - unmasked_char_cnt):]}"
            else:
                masked_value = '*' * str_len

        return masked_value

    @staticmethod
    def save_and_publish_auditlog(document, name, **kwargs):
        try:
            action = kwargs.get("action")
            if not document.status:
                action = AuditlogActions.SOFT_DELETE.value
        except AttributeError:
            action = kwargs.get("action")

        audit_log = AuditLogData(bot=document.bot,
                                 user=document.user,
                                 action=action,
                                 entity=name,
                                 data=document.to_mongo().to_dict())
        Utility.publish_auditlog(auditlog=audit_log, event_url=kwargs.get("event_url"))
        audit_log.save()

    @staticmethod
    def publish_auditlog(auditlog, event_url=None):
        from .data.data_objects import EventConfig
        from mongoengine.errors import DoesNotExist

        try:
            event_config = EventConfig.objects(bot=auditlog.bot).get()

            headers = json.loads(Utility.decrypt_message(event_config.headers))
            ws_url = event_config.ws_url
            method = event_config.method
            if ws_url is not None:
                Utility.execute_http_request(request_method=method, http_url=ws_url,
                                             request_body=auditlog.to_mongo().to_dict(), headers=headers, timeout=5)
        except (DoesNotExist, AppException):
            return

    @staticmethod
    def is_reserved_keyword(keyword: Text):
        return keyword in {KAIRON_TWO_STAGE_FALLBACK}.union(SYSTEM_TRIGGERED_UTTERANCES)

    @staticmethod
    def is_valid_action_name(name: Text, bot: Text, document: Document):
        from kairon.shared.actions.data_objects import Actions
        from kairon.shared.actions.data_objects import HttpActionConfig
        from kairon.shared.actions.data_objects import EmailActionConfig

        if Utility.is_reserved_keyword(name):
            raise AppException(f"{name} is a reserved keyword")
        q_filter = {"name__iexact": name, "bot": bot, "status": True, "exp_message": "Action exists!"}
        Utility.is_exist(Actions, **q_filter)
        if document in {HttpActionConfig, EmailActionConfig}:
            q_filter.pop("name__iexact")
            q_filter["action_name__iexact"] = name
        Utility.is_exist(document, **q_filter)

    @staticmethod
    def validate_enable_sso_only():
        if Utility.environment["app"]["enable_sso_only"]:
            raise AppException("This feature is disabled")

    @staticmethod
    def retrieve_gpt_response(resp):
        if resp and resp.get('choices') and resp['choices'][0].get("text"):
            return resp['choices'][0]["text"]

    @staticmethod
    def read_faq(faq_file: Union[Text, UploadFile]):
        '''
        Reads the file from a path or Uploaded file.
        :param faq_file: Text Path/File
        :return: Dataframe of the file.
        '''
        filename = faq_file
        data = faq_file
        if isinstance(faq_file, UploadFile):
            filename = faq_file.filename
            data = faq_file.file
        if Path(filename).suffix == '.csv':
            df = pd.read_csv(data, encoding='utf8', sep=",")
        elif Path(filename).suffix == '.xlsx':
            df = pd.read_excel(data, engine="openpyxl", sheet_name=0)
        else:
            raise AppException("Invalid file type!")
        df = df.fillna('')
        df.columns = map(str.lower, df.columns)
        return df

    @staticmethod
    def save_faq_training_files(bot: Text, faq_file: File):
        '''
        Saves uploaded faq file in bot data home directory.
        :param bot: bot id
        :param faq_file: Uploaded faq file.
        :return: Path of uploaded faq file.
        '''
        bot_data_home_dir = os.path.join('training_data', bot)
        Utility.make_dirs(bot_data_home_dir)
        file_name = os.path.join(bot_data_home_dir, faq_file.filename)
        faq_file.file.seek(0)
        faq_file_bytes = faq_file.file.read()
        Utility.write_to_file(file_name, faq_file_bytes)
        return bot_data_home_dir

    @staticmethod
    def validate_faq_training_file(faq_file: File):
        '''
        Validates whether faq file is in supported format.
        Also it should not be empty and must contain required column names.

        :param faq_file: Uploaded faq file.
        :return:
        '''
        if not faq_file or Path(faq_file.filename).suffix not in {'.csv', '.xlsx'}:
            raise AppException("Invalid file type! Only csv and xlsx files are supported.")

        if Path(faq_file.filename).suffix == '.csv':
            df = pd.read_csv(faq_file.file, encoding='utf8', sep=",")
        else:
            df = pd.read_excel(faq_file.file, engine="openpyxl", sheet_name=0)

        if df.empty:
            raise AppException("No data found in the file!")
        df.columns = map(str.lower, df.columns)
        columns = set(df.columns)
        required_headers = {'questions', 'answer'}
        if not required_headers.issubset(columns):
            raise AppException(f"Required columns {required_headers} not present in file.")

    @staticmethod
    def convert_utcdate_with_timezone(utcdatetime, datetimezone, date_format):
        zone = tz.gettz(datetimezone)
        utc_locale = utcdatetime.replace(tzinfo=pytz.utc).astimezone(zone).strftime(date_format)
        utc_locale_datetime = datetime.strptime(utc_locale, date_format)
        return utc_locale_datetime


class StoryValidator:

    @staticmethod
    def get_graph(steps: List) -> DiGraph:
        graph = DiGraph()
        vertices = {}
        for story_step in steps:
            vertices[story_step['step']['name']] = KaironStoryStep(story_step["step"]["name"],
                                                                   story_step["step"]["type"])
        for story_step in steps:
            story_step_object = vertices[story_step["step"]["name"]]
            for connected_story_step in story_step['connections'] or []:
                connection_object = vertices[connected_story_step["name"]]
                graph.add_edge(story_step_object, connection_object)
        return graph

    @staticmethod
    def validate_steps(steps: List):
        story_graph = StoryValidator.get_graph(steps)

        if not is_connected(Graph(story_graph)):
            raise AppException("All steps must be connected!")

        source = [x for x in story_graph.nodes() if story_graph.in_degree(x) == 0]
        if len(source) > 1:
            raise AppException("Story cannot have multiple sources!")

        if source[0].step_type != StoryStepType.intent:
            raise AppException("First step should be an intent")

        if recursive_simple_cycles(story_graph):
            raise AppException("Story cannot contain cycle!")

        leaf_nodes_with_intent = [node for node in story_graph.nodes() if story_graph.out_degree(node) == 0
                                    and node.step_type == 'INTENT']
        if leaf_nodes_with_intent:
            raise AppException("Leaf nodes cannot be intent")

        for story_node in story_graph.nodes():
            if story_node.step_type == "INTENT":
                if [successor for successor in story_graph.successors(story_node) if successor.step_type == "INTENT"]:
                    raise AppException("Intent should be followed by an Action")
                if len(list(story_graph.successors(story_node))) > 1:
                    raise AppException("Intent can only have one connection of action type")

import pickle
from calendar import timegm
from datetime import datetime, date
from requests import Response
from functools import partial
from types import ModuleType
from typing import Text, Dict, Callable
import requests
from AccessControl.SecurityInfo import allow_module
from apscheduler.triggers.date import DateTrigger
from apscheduler.util import obj_to_ref, astimezone
from bson import Binary
from pymongo import MongoClient
from RestrictedPython.Guards import safer_getattr
import orjson as json
from tzlocal import get_localzone
from uuid6 import uuid7
from loguru import logger

from kairon import Utility
from kairon.api.app.routers.bot.data import CognitionDataProcessor
from kairon.events.executors.factory import ExecutorFactory
from kairon.exceptions import AppException
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.actions.data_objects import EmailActionConfig
from kairon.shared.callback.data_objects import CallbackConfig
from kairon.shared.cognition.data_objects import CollectionData
from kairon.shared.concurrency.orchestrator import ActorOrchestrator
from kairon.shared.constants import ActorType
from kairon.shared.utils import MailUtility

import json
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key

allow_module("datetime")
allow_module("time")
allow_module("requests")
allow_module("googlemaps")
allow_module("_strptime")
cognition_processor = CognitionDataProcessor()


class CallbackUtility:

    @staticmethod
    def generate_id():
        return uuid7().hex

    @staticmethod
    def datetime_to_utc_timestamp(timeval):
        """
        Converts a datetime instance to a timestamp.

        :type timeval: datetime
        :rtype: float

        """
        if timeval is not None:
            return timegm(timeval.utctimetuple()) + timeval.microsecond / 1000000

    @staticmethod
    def add_schedule_job(schedule_action: Text, date_time: datetime, data: Dict, timezone: Text, _id: Text = None,
                         bot: Text = None, kwargs=None):

        if not bot:
            raise AppException("Missing bot id")

        if not _id:
            _id = uuid7().hex

        print(f"bot: {bot}, name: {schedule_action}")

        if not data:
            data = {}

        data['bot'] = bot
        data['event'] = _id

        callback_config = CallbackConfig.get_entry(bot=bot, name=schedule_action)

        script = callback_config.get('pyscript_code')

        func = obj_to_ref(ExecutorFactory.get_executor().execute_task)

        schedule_data = {
            'source_code': script,
            'predefined_objects': data
        }

        args = (func, "scheduler_evaluator", schedule_data,)
        kwargs = {'task_type': "Callback"} if kwargs is None else {**kwargs, 'task_type': "Callback"}
        trigger = DateTrigger(run_date=date_time, timezone=timezone)

        next_run_time = trigger.get_next_fire_time(None, datetime.now(astimezone(timezone) or get_localzone()))

        job_kwargs = {
            'version': 1,
            'trigger': trigger,
            'executor': "default",
            'func': func,
            'args': tuple(args) if args is not None else (),
            'kwargs': kwargs,
            'id': _id,
            'name': "execute_task",
            'misfire_grace_time': 7200,
            'coalesce': True,
            'next_run_time': next_run_time,
            'max_instances': 1,
        }

        logger.info(job_kwargs)

        client = MongoClient(Utility.environment['database']['url'])
        events_db_name = Utility.environment["events"]["queue"]["name"]
        events_db = client.get_database(events_db_name)
        scheduler_collection = Utility.environment["events"]["scheduler"]["collection"]
        job_store_name = events_db.get_collection(scheduler_collection)
        event_server = Utility.environment['events']['server_url']

        job_store_name.insert_one({
            '_id': _id,
            'next_run_time': CallbackUtility.datetime_to_utc_timestamp(next_run_time),
            'job_state': Binary(pickle.dumps(job_kwargs, pickle.HIGHEST_PROTOCOL))
        })

        http_response = ActionUtility.execute_http_request(
            f"{event_server}/api/events/dispatch/{_id}",
            "GET")

        if not http_response.get("success"):
            raise AppException(http_response)
        else:
            logger.info(http_response)

    @staticmethod
    def delete_schedule_job(event_id: Text, bot: Text):
        if not bot:
            raise AppException("Missing bot id")

        if not event_id:
            raise AppException("Missing event id")

        logger.info(f"event: {event_id}, bot: {bot}")

        event_server = Utility.environment['events']['server_url']

        http_response = ActionUtility.execute_http_request(
            f"{event_server}/api/events/{event_id}",
            "DELETE")

        if not http_response.get("success"):
            raise AppException(http_response)
        else:
            logger.info(http_response)

    @staticmethod
    def send_email(email_action: Text,
                   from_email: Text,
                   to_email: Text,
                   subject:  Text,
                   body: Text,
                   bot: Text):
        if not bot:
            raise AppException("Missing bot id")

        email_action_config = EmailActionConfig.objects(bot=bot, action_name=email_action).first()
        action_config = email_action_config.to_mongo().to_dict()

        smtp_password = action_config.get('smtp_password').get("value")
        smtp_userid = action_config.get('smtp_userid').get("value")

        MailUtility.trigger_email(
            email=[to_email],
            subject=subject,
            body=body,
            smtp_url=action_config['smtp_url'],
            smtp_port=action_config['smtp_port'],
            sender_email=from_email,
            smtp_password=smtp_password,
            smtp_userid=smtp_userid,
            tls=action_config['tls']
        )

    @staticmethod
    def perform_cleanup(local_vars: Dict):
        logger.info(f"local_vars: {local_vars}")
        filtered_locals = {}
        if local_vars:
            for key, value in local_vars.items():
                if not isinstance(value, Callable) and not isinstance(value, ModuleType):
                    if isinstance(value, datetime):
                        value = value.strftime("%m/%d/%Y, %H:%M:%S")
                    elif isinstance(value, date):
                        value = value.strftime("%Y-%m-%d")
                    elif isinstance(value, Response):
                        value = value.text
                    filtered_locals[key] = value
        logger.info(f"filtered_vars: {filtered_locals}")
        return filtered_locals

    @staticmethod
    def execute_script(source_code: Text, predefined_objects: Dict = None):
        logger.info(source_code)
        logger.info(predefined_objects)

        if not predefined_objects:
            predefined_objects = {}

        bot = predefined_objects.get("bot")

        predefined_objects['_getattr_'] = safer_getattr
        predefined_objects['requests']=requests
        predefined_objects['json'] = json
        predefined_objects['datetime']= datetime
        predefined_objects['add_schedule_job'] = partial(CallbackUtility.add_schedule_job, bot=bot)
        predefined_objects['delete_schedule_job'] = partial(CallbackUtility.delete_schedule_job, bot=bot)
        predefined_objects['send_email'] = partial(CallbackUtility.send_email, bot=bot)
        predefined_objects['add_data'] = partial(CallbackUtility.add_data, bot=bot)
        predefined_objects['get_data'] = partial(CallbackUtility.get_data, bot=bot)
        predefined_objects['delete_data'] = partial(CallbackUtility.delete_data, bot=bot)
        predefined_objects['update_data'] = partial(CallbackUtility.update_data, bot=bot)
        predefined_objects["generate_id"] = CallbackUtility.generate_id
        predefined_objects["datetime_to_utc_timestamp"]=CallbackUtility.datetime_to_utc_timestamp
        predefined_objects['decrypt_request'] = CallbackUtility.decrypt_request
        predefined_objects['encrypt_response'] = CallbackUtility.encrypt_response

        script_variables = ActorOrchestrator.run(
            ActorType.pyscript_runner.value, source_code=source_code, timeout=60,
            predefined_objects=predefined_objects
        )
        return script_variables

    @staticmethod
    def pyscript_handler(event, context):
        print(event)
        output = {
            "statusCode": 200,
            "statusDescription": "200 OK",
            "isBase64Encoded": False,
            "headers": {
                "Content-Type": "text/html; charset=utf-8"
            },
            "body": None
        }
        data = event
        if isinstance(data, list):
            data = {item['name'].lower(): item['value'] for item in data}
        try:
            response = CallbackUtility.execute_script(data['source_code'], data.get('predefined_objects'))
            output["body"] = response
        except Exception as e:
            logger.exception(e)
            output["statusCode"] = 422
            output["body"] = str(e)

        logger.info(output)
        return output

    @staticmethod
    def fetch_collection_data(query: dict):
        collection_data = CollectionData.objects(**query)

        for value in collection_data:
            final_data = {}
            item = value.to_mongo().to_dict()
            collection_name = item.pop('collection_name', None)
            is_secure = item.pop('is_secure')
            data = item.pop('data')
            data = cognition_processor.prepare_decrypted_data(data, is_secure)

            final_data["_id"] = str(item["_id"])
            final_data['collection_name'] = collection_name
            final_data['is_secure'] = is_secure
            final_data['data'] = data

            yield final_data

    @staticmethod
    def get_data(collection_name: str, user: str, data_filter: dict, bot: Text = None):
        if not bot:
            raise Exception("Missing bot id")

        collection_name = collection_name.lower()

        query = {"bot": bot, "collection_name": collection_name}

        query.update({f"data__{key}": value for key, value in data_filter.items()})
        data = list(CallbackUtility.fetch_collection_data(query))
        return {"data": data}

    @staticmethod
    def add_data(user: str, payload: dict, bot: str = None):
        if not bot:
            raise Exception("Missing bot id")

        collection_id = cognition_processor.save_collection_data(payload, user, bot)
        return {
            "message": "Record saved!",
            "data": {"_id": collection_id}
        }

    @staticmethod
    def update_data(collection_id: str, user: str, payload: dict, bot: str = None):
        if not bot:
            raise Exception("Missing bot id")

        collection_id = cognition_processor.update_collection_data(collection_id, payload, user, bot)
        return {
            "message": "Record updated!",
            "data": {"_id": collection_id}
        }

    @staticmethod
    def delete_data(collection_id: str, user: Text, bot: Text = None):
        if not bot:
            raise Exception("Missing bot id")

        cognition_processor.delete_collection_data(collection_id, bot, user)

        return {
            "message": f"Collection with ID {collection_id} has been successfully deleted.",
            "data": {"_id": collection_id}
        }

    @staticmethod
    def decrypt_request(request_body, private_key_pem):
        try:
            encrypted_data_b64 = request_body.get("encrypted_flow_data")
            encrypted_aes_key_b64 = request_body.get("encrypted_aes_key")
            iv_b64 = request_body.get("initial_vector")

            if not (encrypted_data_b64 and encrypted_aes_key_b64 and iv_b64):
                raise ValueError("Missing required encrypted data fields")

            # Decode base64 inputs
            encrypted_aes_key = base64.b64decode(encrypted_aes_key_b64)
            encrypted_data = base64.b64decode(encrypted_data_b64)
            iv = base64.b64decode(iv_b64)[:16]  # Ensure IV is exactly 16 bytes

            private_key = load_pem_private_key(private_key_pem.encode(), password=None)

            # Decrypt AES key using RSA and OAEP padding
            aes_key = private_key.decrypt(
                encrypted_aes_key,
                asym_padding.OAEP(
                    mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )

            if len(aes_key) not in (16, 24, 32):
                raise ValueError(f"Invalid AES key size: {len(aes_key)} bytes")

            # Extract GCM tag (last 16 bytes)
            encrypted_body = encrypted_data[:-16]
            tag = encrypted_data[-16:]

            # Decrypt AES-GCM
            cipher = Cipher(algorithms.AES(aes_key), modes.GCM(iv, tag))
            decryptor = cipher.decryptor()
            decrypted_bytes = decryptor.update(encrypted_body) + decryptor.finalize()
            decrypted_data = json.loads(decrypted_bytes.decode("utf-8"))

            response_dict = {
                "decryptedBody": decrypted_data,
                "aesKeyBuffer": aes_key,
                "initialVectorBuffer": iv,
            }

            return response_dict

        except Exception as e:
            raise Exception(f"decryption failed-{str(e)}")

    @staticmethod
    def encrypt_response(response_body, aes_key_buffer, initial_vector_buffer):
        try:
            if aes_key_buffer is None:
                raise ValueError("AES key cannot be None")

            if initial_vector_buffer is None:
                raise ValueError("Initialization vector (IV) cannot be None")

            # Flip the IV
            flipped_iv = bytes(byte ^ 0xFF for byte in initial_vector_buffer)

            # Encrypt using AES-GCM
            encryptor = Cipher(algorithms.AES(aes_key_buffer), modes.GCM(flipped_iv)).encryptor()
            encrypted_bytes = encryptor.update(json.dumps(response_body).encode("utf-8")) + encryptor.finalize()
            encrypted_data_with_tag = encrypted_bytes + encryptor.tag

            # Encode result as base64
            encoded_data = base64.b64encode(encrypted_data_with_tag).decode("utf-8")
            return encoded_data
        except Exception as e:
            raise Exception(f"encryption failed-{str(e)}")




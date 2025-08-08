import pickle
from calendar import timegm
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from smtplib import SMTP
from typing import Text, Dict, Callable, List
import base64
from apscheduler.triggers.date import DateTrigger
from apscheduler.util import obj_to_ref, astimezone
from pymongo import MongoClient
from tzlocal import get_localzone
from uuid6 import uuid7
from loguru import logger
from kairon import Utility
from kairon.events.executors.factory import ExecutorFactory
from kairon.exceptions import AppException
from kairon.shared.actions.data_objects import EmailActionConfig
from kairon.shared.actions.utils import ActionUtility
from bson import Binary
from types import ModuleType
from requests import Response
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from kairon.shared.callback.data_objects import CallbackConfig, CallbackData
import json as jsond

from kairon.shared.chat.user_media import UserMedia


class CallbackScriptUtility:

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

        if not data:
            data = {}

        data['bot'] = bot
        data['event'] = _id

        callback_config = CallbackConfig.get_entry(bot=bot, name=schedule_action)

        script = callback_config.get('pyscript_code')

        func = obj_to_ref(ExecutorFactory.get_executor_for_data(data).execute_task)

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
            'next_run_time': CallbackScriptUtility.datetime_to_utc_timestamp(next_run_time),
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
    def trigger_email(
                email: List[str],
                subject: str,
                body: str,
                smtp_url: str,
                smtp_port: int,
                sender_email: str,
                smtp_password: str,
                smtp_userid: str = None,
                tls: bool = False,
                content_type="html",
        ):
            """
            This is a sync email trigger.
            Sends an email to the mail id of the recipient

            :param smtp_userid:
            :param sender_email:
            :param tls:
            :param smtp_port:
            :param smtp_url:
            :param email: the mail id of the recipient
            :param smtp_password:
            :param subject: the subject of the mail
            :param body: the body of the mail
            :param content_type: "plain" or "html" content
            :return: None
            """
            smtp = None
            try:
                smtp = SMTP(smtp_url, port=smtp_port, timeout=10)
                smtp.connect(smtp_url, smtp_port)
                if tls:
                    smtp.starttls()
                smtp.login(smtp_userid if smtp_userid else sender_email, smtp_password)

                from_addr = sender_email
                mime_body = MIMEText(body, content_type)
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"] = from_addr
                msg["To"] = ",".join(email)
                msg.attach(mime_body)

                smtp.sendmail(from_addr, email, msg.as_string())

            except Exception as e:
                print(f"Failed to send email: {e}")
                raise
            finally:
                if smtp:
                    try:
                        smtp.quit()
                    except Exception as quit_error:
                        print(f"Failed to quit SMTP connection cleanly: {quit_error}")


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
        if not email_action_config:
            raise AppException(f"Email action '{email_action}' not configured for bot {bot}")
        action_config = email_action_config.to_mongo().to_dict()

        smtp_password = action_config.get('smtp_password').get("value")
        smtp_userid = action_config.get('smtp_userid').get("value")

        CallbackScriptUtility.trigger_email(
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
            decrypted_data = jsond.loads(decrypted_bytes.decode("utf-8"))

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
            encrypted_bytes = encryptor.update(jsond.dumps(response_body).encode("utf-8")) + encryptor.finalize()
            encrypted_data_with_tag = encrypted_bytes + encryptor.tag

            # Encode result as base64
            encoded_data = base64.b64encode(encrypted_data_with_tag).decode("utf-8")
            return encoded_data
        except Exception as e:
            raise Exception(f"encryption failed-{str(e)}")


    @staticmethod
    def create_callback(callback_name: str, metadata: dict, bot: str, sender_id: str, channel: str,
                        name: str = None):
        if not name:
            name=callback_name
        callback_url, identifier, standalone = CallbackData.create_entry(
            name=name,
            callback_config_name=callback_name,
            bot=bot,
            sender_id=sender_id,
            channel=channel,
            metadata=metadata,
        )
        if standalone:
            return identifier
        else:
            return callback_url

    @staticmethod
    def save_as_pdf(text: str, bot: str, sender_id:str):
        try:
            _, media_id = UserMedia.save_markdown_as_pdf(
                bot=bot,
                sender_id=sender_id,
                text=text,
                filepath="report.pdf"
            )
            return media_id
        except Exception as e:
            raise Exception(f"encryption failed-{str(e)}")
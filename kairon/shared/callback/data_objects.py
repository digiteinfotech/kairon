import base64
import time
from datetime import datetime
from enum import Enum
from typing import Any, Optional
import json
from uuid6 import uuid7

from mongoengine import StringField, DictField, DateTimeField, Document, DynamicField, IntField, BooleanField, \
    FloatField

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.actions.data_objects import CallbackActionConfig
from kairon.shared.data.audit.data_objects import Auditlog
from kairon.shared.data.signals import push_notification
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


def check_nonempty_string(value, msg="Value must be a non-empty string"):
    if not isinstance(value, str) or not value:
        raise AppException(msg)


def encrypt_secret(secret: str) -> str:
    secret = secret.encode("utf-8")
    fernet = Fernet(Utility.environment['security']['fernet_key'].encode("utf-8"))
    return fernet.encrypt(secret).decode("utf-8")


def decrypt_secret(encrypted_secret: str) -> str:
    fernet = Fernet(Utility.environment['security']['fernet_key'].encode("utf-8"))
    return fernet.decrypt(encrypted_secret.encode("utf-8")).decode("utf-8")


def xor_encrypt_secret(secret: str) -> str:
    """
    AES small length text encryption
    TODO: change function name
    """
    key = Utility.environment['async_callback_action']['short_secret']['aes_key']
    iv = Utility.environment['async_callback_action']['short_secret']['aes_iv']
    key = bytes.fromhex(key)
    iv = bytes.fromhex(iv)
    secret_bytes = secret.encode()
    cipher = Cipher(algorithms.AES(key), modes.CTR(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(secret_bytes) + encryptor.finalize()
    encoded_result = base64.urlsafe_b64encode(ciphertext).decode().rstrip("=")
    return encoded_result


def xor_decrypt_secret(encoded_secret: str) -> str:
    """
    AES encripted text decription function
    TODO: change function name
    """
    key = Utility.environment['async_callback_action']['short_secret']['aes_key']
    iv = Utility.environment['async_callback_action']['short_secret']['aes_iv']
    key = bytes.fromhex(key)
    iv = bytes.fromhex(iv)
    secret = None
    try:
        decoded_secret = base64.urlsafe_b64decode(encoded_secret + "=" * (4 - len(encoded_secret) % 4))
        cipher = Cipher(algorithms.AES(key), modes.CTR(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        secret = decryptor.update(decoded_secret) + decryptor.finalize()
        return secret.decode()
    except Exception:
        raise AppException("Invalid token!")


class CallbackExecutionMode(Enum):
    ASYNC = "async"
    SYNC = "sync"


@push_notification.apply
class CallbackConfig(Auditlog):
    name = StringField(required=True)
    pyscript_code = StringField(required=True)
    validation_secret = StringField(required=True)
    execution_mode = StringField(default=CallbackExecutionMode.ASYNC.value,
                                 choices=[v.value for v in CallbackExecutionMode.__members__.values()])
    expire_in = IntField(default=0)
    shorten_token = BooleanField(default=False)
    token_hash = StringField()
    token_value = StringField()
    standalone = BooleanField(default=False)
    standalone_id_path = StringField(default='')
    bot = StringField(required=True)
    meta = {"indexes": [{"fields": ["bot", "name"]}]}

    @staticmethod
    def get_all_names(bot) -> list[str]:
        names = CallbackConfig.objects(bot=bot).distinct(field="name")
        return list(names)

    @staticmethod
    def get_entry(bot, name) -> dict:
        entry = CallbackConfig.objects(bot=bot, name__iexact=name).first()
        if not entry:
            raise AppException(f"Callback Configuration with name '{name}' does not exist!")
        dict_form = entry.to_mongo().to_dict()
        dict_form.pop("_id")
        return dict_form

    @staticmethod
    def create_entry(bot: str,
                     name: str,
                     pyscript_code: str,
                     execution_mode: str = CallbackExecutionMode.ASYNC.value,
                     expire_in: int = 30,
                     shorten_token: bool = False,
                     standalone: bool = False,
                     standalone_id_path: str = '',
                     **kwargs):
        check_nonempty_string(name)
        if standalone and not standalone_id_path:
            raise AppException("Standalone ID path is required for standalone callbacks!")
        Utility.is_exist(
            CallbackConfig,
            exp_message=f"Callback Configuration with name '{name}' exists!",
            name__iexact=name,
            bot=bot,
            raise_error=True
        )
        check_nonempty_string(pyscript_code)
        validation_secret = encrypt_secret(uuid7().hex)
        token_hash = None
        if shorten_token:
            token_hash = uuid7().hex
        config = CallbackConfig(name=name,
                                bot=bot,
                                pyscript_code=pyscript_code,
                                validation_secret=validation_secret,
                                execution_mode=execution_mode,
                                expire_in=expire_in,
                                shorten_token=shorten_token,
                                token_hash=token_hash,
                                standalone=standalone,
                                standalone_id_path=standalone_id_path,
                                **kwargs)
        config.save()
        return config.to_mongo().to_dict()

    @staticmethod
    def get_auth_token(bot, name) -> tuple[str, bool]:
        entry = CallbackConfig.objects(bot=bot, name__iexact=name).first()
        if not entry:
            raise AppException(f"Callback Configuration with name '{name}' does not exist!")

        info = {
            "bot": entry.bot,
            "callback_name": entry.name,
            "validation_secret": decrypt_secret(entry.validation_secret),
            "expire_in": entry.expire_in,
        }

        token = encrypt_secret(json.dumps(info))

        if entry.shorten_token:
            entry.token_value = token
            entry.save()
            return xor_encrypt_secret(entry.token_hash), entry.standalone
        else:
            return token, entry.standalone

    @staticmethod
    def verify_auth_token(token: str):
        info = None
        if len(token) < 64:
            search_key = xor_decrypt_secret(token)
            config = CallbackConfig.objects(token_hash=search_key, shorten_token=True).first()
            if config:
                info = json.loads(decrypt_secret(config.token_value))
        else:
            info = json.loads(decrypt_secret(token))
        if not info:
            raise AppException("Invalid token!")

        config = CallbackConfig.objects(bot=info['bot'],
                                        name__iexact=info['callback_name'],
                                        ).first()
        if not config:
            raise AppException("Invalid token!")
        if decrypt_secret(config.validation_secret) != info['validation_secret']:
            raise AppException("Invalid token!")
        return config

    @staticmethod
    def edit(bot: str, name: str, **kwargs):
        check_nonempty_string(name)
        config = CallbackConfig.objects(bot=bot, name__iexact=name).first()
        if not config:
            raise AppException(f"Callback Configuration with name '{name}' does not exist!")
        for key, value in kwargs.items():
            setattr(config, key, value)
        if config.shorten_token and not config.token_hash:
            config.token_hash = uuid7().hex
        config.save()
        return config.to_mongo().to_dict()

    @staticmethod
    def delete_entry(bot: str, name: str):
        check_nonempty_string(name)
        callback_action = CallbackActionConfig.objects(bot=bot, callback_name=name).first()
        if callback_action:
            raise AppException(f"Cannot delete Callback Configuration '{name}' as it is attached to {callback_action.name} callback action!")
        config = CallbackConfig.objects(bot=bot, name__iexact=name).first()
        if not config:
            raise AppException(f"Callback Configuration with name '{name}' does not exist!")
        config.delete()
        return config.name

    @staticmethod
    def get_callback_url(bot: str, name: str):
        base_url = Utility.environment['async_callback_action']['url']
        auth_token, is_standalone = CallbackConfig.get_auth_token(bot, name)
        if not is_standalone:
            raise AppException(f"Callback Configuration with name '{name}' is not standalone!")
        callback_url = f"{base_url}/s/{auth_token}"
        return callback_url



class CallbackRecordStatusType(Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


@push_notification.apply
class CallbackData(Document):
    """
    this represents a record of every callback execution generated by action trigger
    """
    action_name = StringField()
    callback_name = StringField(required=True)
    bot = StringField(required=True)
    sender_id = StringField(required=True)
    channel = StringField(required=True)
    metadata = DictField()
    identifier = StringField(required=True)
    timestamp = FloatField(default=time.time)
    callback_url = StringField()
    execution_mode = StringField(default=CallbackExecutionMode.ASYNC.value,
                                 choices=[v.value for v in CallbackExecutionMode.__members__.values()])
    state = DynamicField(default=0)
    is_valid = BooleanField(default=True)
    meta = {"indexes": [{"fields": ["bot", "identifier"]}]}

    @staticmethod
    def create_entry(name: str, callback_config_name: str, bot: str, sender_id: str, channel: str, metadata: dict, **kwargs):
        check_nonempty_string(name)
        check_nonempty_string(callback_config_name)
        check_nonempty_string(bot)
        check_nonempty_string(sender_id)
        check_nonempty_string(channel)
        identifier = f"{uuid7().hex}"
        base_url = Utility.environment['async_callback_action']['url']
        auth_token, is_standalone = CallbackConfig.get_auth_token(bot, callback_config_name)
        callback_url = f"{base_url}/"
        if is_standalone:
            callback_url += f"s/{auth_token}"
        else:
            callback_url += f"d/{identifier}/{auth_token}"

        record = CallbackData(action_name=name,
                              callback_name=callback_config_name,
                              bot=bot,
                              sender_id=sender_id,
                              channel=channel,
                              metadata=metadata,
                              identifier=identifier,
                              callback_url=callback_url,
                              timestamp=time.time(),
                              is_valid=True,
                              **kwargs)
        record.save()
        return callback_url, identifier, is_standalone

    @staticmethod
    def get_value_from_json(json_obj, path):
        keys = path.split('.')
        value = json_obj
        try:
            for key in keys:
                if isinstance(value, list):
                    key = int(key)
                value = value[key]
        except (KeyError, IndexError, ValueError, TypeError):
            raise AppException(f"Cannot find identifier at path '{path}' in request data!")

        return value

    @staticmethod
    def validate_entry(token: str, identifier: Optional[str] = None, request_body: Any = None):
        check_nonempty_string(token)
        config_entry = CallbackConfig.verify_auth_token(token)

        if config_entry.standalone:
            if not request_body:
                raise AppException("Request data is required for standalone callbacks!")
            identifier = CallbackData.get_value_from_json(request_body, config_entry.standalone_id_path)

        record = CallbackData.objects(bot=config_entry.bot, identifier=identifier).first()
        if not record:
            raise AppException("Callback Record does not exist, invalid identifier!")
        if not record.is_valid:
            raise AppException("Callback has been invalidated!")
        if config_entry.expire_in > 0:
            exp_time = record.timestamp + config_entry.expire_in
            if exp_time < time.time():
                raise AppException("Callback time-limit expired")
        entry_dict = record.to_mongo().to_dict()
        entry_dict.pop('_id')
        entry_dict.pop('timestamp')
        callback_dict = config_entry.to_mongo().to_dict()
        return entry_dict, callback_dict

    @staticmethod
    def update_state(bot: str, identifier: str, state: dict, invalidate: bool):
        record = CallbackData.objects(bot=bot, identifier=identifier).first()
        if not record:
            raise AppException("Callback Record does not exist, invalid identifier!")
        record.state = state
        record.is_valid = not invalidate
        record.save()
        return record.to_mongo().to_dict()


@push_notification.apply
class CallbackLog(Document):
    """
        this represents the record of actual execution record of  callback after the callback url is triggered
    """
    callback_name = StringField(required=True)
    bot = StringField(required=True)
    channel = StringField(default='unsupported')
    identifier = StringField(required=True)
    pyscript_code = StringField(required=True)
    sender_id = StringField()
    log = StringField()
    timestamp = DateTimeField(default=datetime.utcnow)
    status = StringField(default=CallbackRecordStatusType.SUCCESS.value,
                         choices=[v.value for v in CallbackRecordStatusType.__members__.values()])
    request_data = DynamicField()
    metadata = DynamicField()
    callback_url = StringField(required=True)
    callback_source = StringField()

    meta = {"indexes": [{"fields": ["bot", "identifier"]}]}

    @staticmethod
    def create_success_entry(name: str,
                             bot: str,
                             channel: str,
                             identifier: str,
                             pyscript_code: str,
                             sender_id: str,
                             log: str,
                             request_data: Any,
                             metadata: dict,
                             callback_url: str,
                             callback_source: str):
        check_nonempty_string(name)
        check_nonempty_string(bot)
        check_nonempty_string(identifier)
        check_nonempty_string(pyscript_code)
        check_nonempty_string(callback_url)
        record = CallbackLog(callback_name=name,
                             bot=bot,
                             channel=channel,
                             identifier=identifier,
                             pyscript_code=pyscript_code,
                             sender_id=sender_id,
                             log=log,
                             request_data=request_data,
                             metadata=metadata,
                             callback_url=callback_url,
                             callback_source=callback_source,
                             status=CallbackRecordStatusType.SUCCESS.value,
                             timestamp=datetime.utcnow())
        record.save()
        return record.to_mongo().to_dict()

    @staticmethod
    def create_failure_entry(name: str,
                             bot: str,
                             channel: str,
                             identifier: str,
                             pyscript_code: str,
                             sender_id: str,
                             error_log: str,
                             request_data: Any,
                             metadata: dict,
                             callback_url: str,
                             callback_source: str):
        check_nonempty_string(name)
        check_nonempty_string(bot)
        check_nonempty_string(identifier)
        check_nonempty_string(pyscript_code)
        check_nonempty_string(callback_url)
        record = CallbackLog(callback_name=name,
                             bot=bot,
                             channel=channel,
                             identifier=identifier,
                             pyscript_code=pyscript_code,
                             sender_id=sender_id,
                             log=error_log,
                             request_data=request_data,
                             metadata=metadata,
                             callback_url=callback_url,
                             callback_source=callback_source,
                             status=CallbackRecordStatusType.FAILED.value,
                             timestamp=datetime.utcnow())
        record.save()
        return record.to_mongo().to_dict()

    @staticmethod
    def get_logs(query: dict, offset: int, limit: int):
        logs = CallbackLog.objects(**query).skip(offset).limit(limit).exclude('id').order_by('-timestamp').to_json()
        logs_dict_list = json.loads(logs)
        for log in logs_dict_list:
            log['timestamp'] = log['timestamp']['$date']
        total = CallbackLog.objects(**query).count()
        return logs_dict_list, total


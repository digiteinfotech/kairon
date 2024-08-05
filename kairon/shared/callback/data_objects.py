from datetime import datetime
from enum import Enum
from typing import Any

from uuid6 import uuid7

from mongoengine import StringField, DictField, DateTimeField, Document, DynamicField

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.data.audit.data_objects import Auditlog
from kairon.shared.data.signals import push_notification
from fernet import Fernet


def check_nonempty_string(value, msg="Value must be a non-empty string"):
    if not isinstance(value, str) or not value:
        raise AppException(msg)


def encrypt_secret(secret: str) -> str:
    secret = secret.encode("utf-8")
    fernet = Fernet(Utility.environment['security']['fernet_key'].encode("utf-8"))
    return fernet.encrypt(secret).decode("utf-8")


def decrypt_secret(secret: str) -> str:
    secret = secret.encode("utf-8")
    fernet = Fernet(Utility.environment['security']['fernet_key'].encode("utf-8"))
    return fernet.decrypt(secret).decode("utf-8")



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
        return  dict_form

    @staticmethod
    def create_entry(bot: str,
                     name: str,
                     pyscript_code: str,
                     validation_secret: str,
                     execution_mode: str = CallbackExecutionMode.ASYNC.value,
                     **kwargs):
        check_nonempty_string(name)
        Utility.is_exist(
            CallbackConfig,
            exp_message=f"Callback Configuration with name '{name}' exists!",
            name__iexact=name,
            bot=bot,
            raise_error=True
        )
        check_nonempty_string(pyscript_code)
        check_nonempty_string(validation_secret)
        validation_secret = encrypt_secret(validation_secret)
        config = CallbackConfig(name=name,
                                bot=bot,
                                pyscript_code=pyscript_code,
                                validation_secret=validation_secret,
                                execution_mode=execution_mode,
                                **kwargs)
        config.save()
        return config.to_mongo().to_dict()

    @staticmethod
    def get_auth_token(bot, name) -> str:
        entry = CallbackConfig.objects(bot=bot, name__iexact=name).first()
        if not entry:
            raise AppException(f"Callback Configuration with name '{name}' does not exist!")
        return entry.validation_secret

    @staticmethod
    def edit(bot: str, name: str, **kwargs):
        check_nonempty_string(name)
        config = CallbackConfig.objects(bot=bot, name__iexact=name).first()
        if not config:
            raise AppException(f"Callback Configuration with name '{name}' does not exist!")
        if kwargs.get('validation_secret') == 'new':
            kwargs.pop('validation_secret')
            kwargs['validation_secret'] = uuid7().hex

        if kwargs.get('validation_secret'):
            kwargs['validation_secret'] = encrypt_secret(kwargs['validation_secret'])
        for key, value in kwargs.items():
            if not value:
                continue
            setattr(config, key, value)
        config.save()
        return config.to_mongo().to_dict()

    @staticmethod
    def delete_entry(bot: str, name: str):
        check_nonempty_string(name)
        config = CallbackConfig.objects(bot=bot, name__iexact=name).first()
        if not config:
            raise AppException(f"Callback Configuration with name '{name}' does not exist!")
        config.delete()
        return config.name


class CallbackRecordStatusType(Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


@push_notification.apply
class CallbackData(Document):
    action_name = StringField()
    callback_name = StringField(required=True)
    bot = StringField(required=True)
    sender_id = StringField(required=True)
    channel = StringField(required=True)
    metadata = DictField()
    identifier = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    callback_url = StringField()
    execution_mode = StringField(default=CallbackExecutionMode.ASYNC.value,
                                 choices=[v.value for v in CallbackExecutionMode.__members__.values()])
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
        auth_token = CallbackConfig.get_auth_token(bot, callback_config_name)
        callback_url = f"{base_url}/{bot}/{name}/{identifier}?token={auth_token}"
        record = CallbackData(action_name=name,
                              callback_name=callback_config_name,
                              bot=bot,
                              sender_id=sender_id,
                              channel=channel,
                              metadata=metadata,
                              identifier=identifier,
                              callback_url=callback_url,
                              timestamp=datetime.utcnow(),
                              **kwargs)
        record.save()
        return callback_url

    @staticmethod
    def validate_entry(bot: str, name : str, dynamic_param: str, validation_secret: str):
        check_nonempty_string(bot)
        check_nonempty_string(validation_secret)
        record = CallbackData.objects(bot=bot, identifier=dynamic_param).first()
        if not record:
            raise AppException("Callback Record does not exist, invalid identifier!")
        if name != record.action_name:
            raise AppException("Invalid identifier!")
        config_exists = Utility.is_exist(
            CallbackConfig,
            name__iexact=record.callback_name,
            validation_secret__iexact=validation_secret,
            bot=bot,
            raise_error=False
        )
        if not config_exists:
            raise AppException("Invalid validation secret!")
        entry_dict = record.to_mongo().to_dict()
        entry_dict.pop('_id')
        return entry_dict



@push_notification.apply
class CallbackLog(Document):
    callback_name = StringField(required=True)
    bot = StringField(required=True)
    identifier = StringField(required=True)
    pyscript_code = StringField(required=True)
    sender_id = StringField()
    log = StringField()
    timestamp = DateTimeField(default=datetime.utcnow)
    status = StringField(default=CallbackRecordStatusType.SUCCESS.value, choices=[v.value for v in CallbackRecordStatusType.__members__.values()])
    request_data = DynamicField()
    metadata = DictField()
    callback_url = StringField(required=True)
    callback_source = StringField()

    meta = {"indexes": [{"fields": ["bot", "identifier"]}]}

    @staticmethod
    def create_success_entry(name: str,
                             bot: str,
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
    def get_logs(query: dict, page: int, limit: int):
        logs = CallbackLog.objects(**query).order_by("-timestamp").paginate(page=page, per_page=limit)
        return logs.items, logs.total


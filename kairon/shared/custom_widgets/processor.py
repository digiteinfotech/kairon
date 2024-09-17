from datetime import datetime
from typing import Dict, Text, List

from mongoengine import DoesNotExist
from loguru import logger
from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.custom_widgets.constants import CustomWidgetParameterType
from kairon.shared.custom_widgets.data_objects import CustomWidgets, CustomWidgetsRequestLog, CustomWidgetParameters


class CustomWidgetsProcessor:

    @staticmethod
    def save_config(widget_config: Dict, bot: Text, user: Text):
        Utility.is_exist(CustomWidgets, "Widget with name exists!", bot=bot, name=widget_config.get("name"))
        widget_config['bot'] = bot
        widget_config['user'] = user
        return CustomWidgets(**widget_config).save().id.__str__()

    @staticmethod
    def edit_config(widget_id: Text, widget_config: Dict, bot: Text, user: Text):
        try:
            widget = CustomWidgets.objects(id=widget_id, bot=bot).get()
            widget.name = widget_config.get("name")
            widget.http_url = widget_config.get("http_url")
            widget.request_method = widget_config.get("request_method")
            widget.request_parameters = [CustomWidgetParameters(**r) for r in
                                         widget_config["request_parameters"]] if widget_config.get("request_parameters") else None
            widget.dynamic_parameters = widget_config.get("dynamic_parameters")
            widget.headers = [CustomWidgetParameters(**h) for h in
                              widget_config["headers"]] if widget_config.get("headers") else None
            widget.timestamp = datetime.utcnow()
            widget.user = user
            widget.save()
        except DoesNotExist as e:
            logger.exception(e)
            raise AppException("Widget does not exists!")

    @staticmethod
    def get_config(bot: Text):
        for widget in CustomWidgets.objects(bot=bot):
            widget = widget.to_mongo().to_dict()
            widget.pop("timestamp")
            widget.pop("user")
            widget["_id"] = widget["_id"].__str__()
            yield widget

    @staticmethod
    def list_widgets(bot: Text):
        return [w_id.__str__() for w_id in CustomWidgets.objects(bot=bot).values_list('id')]

    @staticmethod
    def delete_config(widget_id: Text, bot: Text, user: str = None):
        try:
            widget = CustomWidgets.objects(id=widget_id, bot=bot).get()
            Utility.delete_documents(widget, user)
        except DoesNotExist as e:
            logger.exception(e)
            raise AppException("Widget does not exists!")

    @staticmethod
    def get_logs(bot: Text, start_idx: int = 0, page_size: int = 10):
        for log in CustomWidgetsRequestLog.objects(bot=bot).order_by("-timestamp").skip(start_idx).limit(page_size):
            log = log.to_mongo().to_dict()
            log.pop('_id')
            yield log

    @staticmethod
    def get_row_cnt(bot):
        from kairon.shared.data.processor import MongoProcessor

        return MongoProcessor().get_row_count(CustomWidgetsRequestLog, bot)

    @staticmethod
    def trigger_widget(widget_id: Text, bot: Text, user: Text, filters=None, raise_err: bool = True):
        config = {}
        resp = None
        exception = None
        headers_eval_log = None
        request_body_eval_log = None
        try:
            config = CustomWidgets.objects(id=widget_id, bot=bot).get().to_mongo().to_dict()
            headers, headers_eval_log = CustomWidgetsProcessor.__prepare_request_parameters(bot, config.get("headers"))
            request_body, request_body_eval_log = CustomWidgetsProcessor.__prepare_request_body(config)
            request_body, request_body_eval_log = CustomWidgetsProcessor.__attach_filters(request_body, request_body_eval_log, filters)
            timeout = config.get("timeout", 1)
            resp = Utility.execute_http_request(config["request_method"], config["http_url"], request_body, headers, timeout)
            return resp, None
        except Exception as e:
            logger.exception(e)
            if isinstance(e, DoesNotExist):
                e = "Widget does not exists!"
            exception = str(e)
            if raise_err:
                raise AppException(e)
            return None, exception
        finally:
            log_attributes = {
                "request_method": config.get("request_method"), "http_url": config.get("http_url"), "response": resp,
                "headers": headers_eval_log, "exception": exception, "request_parameters": request_body_eval_log,
                "bot": bot, "requested_by": user, "name": config.get("name")
            }
            CustomWidgetsRequestLog(**log_attributes).save()

    @staticmethod
    def __prepare_request_body(config):
        from ..actions.utils import ActionUtility

        if not Utility.check_empty_string(config.get('dynamic_parameters')):
            key_vault = ActionUtility.get_all_secrets_from_keyvault(config["bot"])
            body, _ = ActionUtility.evaluate_script(config['dynamic_parameters'], {"context": {"key_vault": key_vault}})
            body_log = ActionUtility.encrypt_secrets(body, {"key_vault": key_vault})
            return body, body_log

        return CustomWidgetsProcessor.__prepare_request_parameters(config["bot"], config.get("request_parameters"))

    @staticmethod
    def __prepare_request_parameters(bot: Text, params: List):
        from ..actions.utils import ActionUtility

        request_body = {}
        request_body_log = {}

        for param in params or []:
            if param['parameter_type'] == CustomWidgetParameterType.key_vault.value:
                value = ActionUtility.get_secret_from_key_vault(param['value'], bot, False)
                log_value = Utility.get_masked_value(value)
            else:
                value, log_value = param['value'], param['value']

            request_body[param['key']] = value
            request_body_log[param['key']] = log_value

        return request_body, request_body_log

    @staticmethod
    def __attach_filters(request_body, request_body_eval_log, filters):
        if filters:
            if not request_body:
                request_body = {}
                request_body_eval_log = {}
            request_body.update(filters)
            request_body_eval_log.update(filters)
        return request_body, request_body_eval_log

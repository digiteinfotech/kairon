import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Any, Text

from loguru import logger
from kairon import Utility
from kairon.async_callback.channel_message_dispacher import ChannelMessageDispatcher
from kairon.evaluator.processor import EvaluatorProcessor
from kairon.exceptions import AppException
from kairon.shared.callback.data_objects import CallbackData, CallbackConfig, CallbackLog, CallbackExecutionMode
from kairon.shared.cloud.utils import CloudUtility
from kairon.shared.constants import EventClass


async_task_executor = ThreadPoolExecutor(max_workers=64)


class CallbackProcessor:
    @staticmethod
    def run_pyscript(script: str, predefined_objects: dict):
        """
        Run python script
        """
        trigger_task = Utility.environment['async_callback_action']['pyscript']['trigger_task']
        try:
            if trigger_task:
                lambda_response = CloudUtility.trigger_lambda(EventClass.pyscript_evaluator, {
                    'script': script,
                    'predefined_objects': predefined_objects
                })
                if CloudUtility.lambda_execution_failed(lambda_response):
                    err = lambda_response['Payload'].get('body') or lambda_response
                    raise AppException(f"{err}")
                result = lambda_response["Payload"].get('body')
                return result.get('bot_response')

            response = EvaluatorProcessor.evaluate_pyscript(source_code=script, predefined_objects=predefined_objects)

            return response.get('bot_response')
        except AppException as e:
            raise AppException(f"Error while executing pyscript: {str(e)}")

    @staticmethod
    def run_pyscript_async(script: str, predefined_objects: dict, callback: Any):
        """
        Run python script asynchronously
        """

        async def execute_script_task(cb: Any, src_code: Text, pre_objs: Optional[dict] = None):
            try:
                data = CallbackProcessor.run_pyscript(script=src_code, predefined_objects=pre_objs)
                await cb({'result': data})
            except AppException as ex:
                await cb({'error': str(ex)})

        def run_async_task():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(execute_script_task(callback, script, predefined_objects))

        try:
            async_task_executor.submit(run_async_task)
        except AppException as e:
            raise AppException(f"Error while executing pyscript: {str(e)}")

    @staticmethod
    async def async_callback(obj: dict, ent: dict, cb: dict, c_src: str, bot_id: str, sid: str, chnl: str, rd: dict):
        try:
            if not obj:
                raise AppException("No response received from callback script")
            elif res := obj.get('result'):
                await ChannelMessageDispatcher.dispatch_message(bot_id, sid, res, chnl)
                CallbackLog.create_success_entry(name=ent.get("action_name"),
                                                 bot=bot_id,
                                                 identifier=ent.get("identifier"),
                                                 pyscript_code=cb.get("pyscript_code"),
                                                 sender_id=sid,
                                                 log=res,
                                                 request_data=rd,
                                                 metadata=ent.get("metadata"),
                                                 callback_url=ent.get("callback_url"),
                                                 callback_source=c_src)
            elif error := obj.get('error'):
                raise AppException(f"Error while executing pyscript: {error}")
            else:
                raise AppException("No response received from callback script")
        except Exception as e:
            logger.exception(e)
            CallbackLog.create_failure_entry(name=ent.get("action_name"),
                                             bot=bot_id,
                                             identifier=ent.get("identifier"),
                                             pyscript_code=cb.get("pyscript_code"),
                                             sender_id=sid,
                                             error_log=error,
                                             request_data=rd,
                                             metadata=ent.get("metadata"),
                                             callback_url=ent.get("callback_url"),
                                             callback_source=c_src)

    @staticmethod
    async def process_async_callback_request(bot: str,
                                             name: str,
                                             dynamic_param: str,
                                             token: str,
                                             request_data: Optional[dict] = None,
                                             callback_source: Optional[str] = None):
        """
        Process async callback request
        """
        predefined_objects = {
            "bot": bot,
            "req": request_data,
            "req_host": callback_source,
        }
        error_code = 0
        message = "success"
        data = None
        entry = CallbackData.validate_entry(bot=bot, name=name, dynamic_param=dynamic_param, validation_secret=token)
        predefined_objects.update(entry)
        callback = CallbackConfig.get_entry(name=entry.get("callback_name"), bot=bot)
        execution_mode = callback.get("execution_mode")
        predefined_objects.update(entry)
        try:
            if execution_mode == CallbackExecutionMode.ASYNC.value:
                async def callback_function(rsp: dict):
                    copied_func = functools.partial(CallbackProcessor.async_callback, rsp, entry, callback, callback_source, bot, entry.get("sender_id"), entry.get("channel"), request_data)
                    await copied_func()

                await CallbackProcessor.run_pyscript_async(script=callback.get("pyscript_code"), predefined_objects=predefined_objects, callback=callback_function)
            elif execution_mode == CallbackExecutionMode.SYNC.value:
                data = CallbackProcessor.run_pyscript(script=callback.get("pyscript_code"), predefined_objects=predefined_objects)
                await ChannelMessageDispatcher.dispatch_message(bot, entry.get("sender_id"), data, entry.get("channel"))
                CallbackLog.create_success_entry(name=entry.get("action_name"),
                                                 bot=bot,
                                                 identifier=entry.get("identifier"),
                                                 pyscript_code=callback.get("pyscript_code"),
                                                 sender_id=entry.get("sender_id"),
                                                 log=data,
                                                 request_data=request_data,
                                                 metadata=entry.get("metadata"),
                                                 callback_url=entry.get("callback_url"),
                                                 callback_source=callback_source)

        except AppException as e:
            error_code = 400
            message = str(e)
            CallbackLog.create_failure_entry(name=entry.get("action_name"),
                                             bot=bot,
                                             identifier=entry.get("identifier"),
                                             pyscript_code=callback.get("pyscript_code"),
                                             sender_id=entry.get("sender_id"),
                                             error_log=message,
                                             request_data=request_data,
                                             metadata=entry.get("metadata"),
                                             callback_url=entry.get("callback_url"),
                                             callback_source=callback_source)

        return data, message, error_code

import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Any, Text

from loguru import logger
from kairon import Utility
from kairon.async_callback.channel_message_dispacher import ChannelMessageDispatcher
from kairon.async_callback.utils import CallbackUtility
from kairon.exceptions import AppException
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.callback.data_objects import CallbackData, CallbackLog, CallbackExecutionMode, CallbackResponseType
from kairon.shared.cloud.utils import CloudUtility
from kairon.shared.constants import EventClass
from kairon.shared.data.constant import TASK_TYPE

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
                logger.info("Triggering lambda for pyscript evaluation")
                lambda_response = CloudUtility.trigger_lambda(EventClass.pyscript_evaluator, {
                    'source_code': script,
                    'predefined_objects': predefined_objects
                }, task_type=TASK_TYPE.CALLBACK.value)
                if CloudUtility.lambda_execution_failed(lambda_response):
                    err = lambda_response['Payload'].get('body') or lambda_response
                    raise AppException(f"{err}")
                if err := lambda_response["Payload"].get('errorMessage'):
                    raise AppException(f"{err}")
                result = lambda_response["Payload"].get('body')
                return result
            else:
                logger.info("Triggering Callback Server for pyscript evaluation")
                response = CallbackUtility.pyscript_handler({
                    'source_code': script,
                    'predefined_objects': predefined_objects
                }, None)
                if response["statusCode"] != 200:
                    err = response.get('body') or response
                    raise AppException(f"{err}")
                result = response.get('body')
                return result
        except AppException as e:
            raise AppException(f"Error while executing pyscript: {str(e)}")

    @staticmethod
    def parse_pyscript_data(data: dict):
        bot_response = data.get('bot_response')
        state = data.get('state')
        invalidate = data.get('invalidate')
        return bot_response, state, invalidate

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
    async def async_callback(obj: dict, ent: dict, cb: dict, c_src: str, bot_id: str, sid: str, chnl: str, ds: bool, rd: dict):
        try:
            if not obj:
                raise AppException("No response received from callback script")
            elif res := obj.get('result'):
                bot_response, state, invalidate = CallbackProcessor.parse_pyscript_data(res)
                CallbackData.update_state(ent['bot'], ent['identifier'], state, invalidate)
                if ds:
                    await ChannelMessageDispatcher.dispatch_message(bot_id, sid, bot_response, chnl)
                CallbackLog.create_success_entry(name=ent.get("action_name"),
                                                 bot=bot_id,
                                                 channel=chnl,
                                                 identifier=ent.get("identifier"),
                                                 pyscript_code=cb.get("pyscript_code"),
                                                 sender_id=sid,
                                                 log=str(bot_response),
                                                 request_data=rd,
                                                 metadata=ent.get("metadata"),
                                                 callback_url=ent.get("callback_url"),
                                                 callback_source=c_src)
            elif error := obj.get('error'):
                raise AppException(f"Error while executing pyscript: {error}")
            else:
                raise AppException("No response received from callback script")
        except Exception as e:
            error_msg = str(e)
            logger.exception(error_msg)
            CallbackLog.create_failure_entry(name=ent.get("action_name"),
                                             bot=bot_id,
                                             channel=chnl,
                                             identifier=ent.get("identifier"),
                                             pyscript_code=cb.get("pyscript_code"),
                                             sender_id=sid,
                                             error_log=error_msg,
                                             request_data=rd,
                                             metadata=ent.get("metadata"),
                                             callback_url=ent.get("callback_url"),
                                             callback_source=c_src)

    @staticmethod
    async def process_async_callback_request(token: str,
                                             identifier: Optional[str] = None,
                                             request_data: Optional[dict] = None,
                                             callback_source: Optional[str] = None):
        """
        Process async callback request
        """
        predefined_objects = {
            "req": request_data,
            "req_host": callback_source,
        }
        error_code = 0
        message = "success"
        data = None
        entry, callback = CallbackData.validate_entry(token, identifier, request_data.get('body'))
        predefined_objects.update(entry)
        bot = entry.get("bot")
        action_name = entry.get("action_name")
        callback_action_config = MongoProcessor.get_callback_action(bot, action_name)
        dispatch_response = callback_action_config.get("dispatch_bot_response")
        execution_mode = callback.get("execution_mode")
        response_type = callback.get("response_type", CallbackResponseType.KAIRON_JSON.value)
        try:
            if execution_mode == CallbackExecutionMode.ASYNC.value:
                logger.info(f"Executing async callback. Identifier: {entry.get('identifier')}")

                async def callback_function(rsp: dict):
                    copied_func = functools.partial(CallbackProcessor.async_callback, rsp, entry, callback, callback_source, bot, entry.get("sender_id"), entry.get("channel"), dispatch_response, request_data)
                    await copied_func()

                CallbackProcessor.run_pyscript_async(script=callback.get("pyscript_code"),
                                                     predefined_objects=predefined_objects,
                                                     callback=callback_function)
            elif execution_mode == CallbackExecutionMode.SYNC.value:
                logger.info(f"Executing sync callback. Identifier: {entry.get('identifier')}")
                result = CallbackProcessor.run_pyscript(script=callback.get("pyscript_code"),
                                                        predefined_objects=predefined_objects)
                bot_response, state, invalidate = CallbackProcessor.parse_pyscript_data(result)
                CallbackData.update_state(entry['bot'], entry['identifier'], state, invalidate)
                data = bot_response
                logger.info(f'Pyscript output: {bot_response, state, invalidate}')
                if dispatch_response:
                    await ChannelMessageDispatcher.dispatch_message(bot, entry.get("sender_id"), data, entry.get("channel"))
                CallbackLog.create_success_entry(name=entry.get("action_name"),
                                                 bot=bot,
                                                 channel=entry.get("channel"),
                                                 identifier=entry.get("identifier"),
                                                 pyscript_code=callback.get("pyscript_code"),
                                                 sender_id=entry.get("sender_id"),
                                                 log=str(data),
                                                 request_data=request_data,
                                                 metadata=entry.get("metadata"),
                                                 callback_url=entry.get("callback_url"),
                                                 callback_source=callback_source)

        except AppException as e:
            error_code = 400
            message = str(e)
            CallbackLog.create_failure_entry(name=entry.get("action_name"),
                                             bot=bot,
                                             channel=entry.get("channel"),
                                             identifier=entry.get("identifier"),
                                             pyscript_code=callback.get("pyscript_code"),
                                             sender_id=entry.get("sender_id"),
                                             error_log=message,
                                             request_data=request_data,
                                             metadata=entry.get("metadata"),
                                             callback_url=entry.get("callback_url"),
                                             callback_source=callback_source)

        return data, message, error_code, response_type
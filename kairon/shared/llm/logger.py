from litellm.integrations.custom_logger import CustomLogger
from .data_objects import LLMLogs
import ujson as json
from loguru import logger


class LiteLLMLogger(CustomLogger):

    def log_stream_event(self, kwargs, response_obj, start_time, end_time):
        self.__logs_litellm(**kwargs)

    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        self.__logs_litellm(**kwargs)

    def log_failure_event(self, kwargs, response_obj, start_time, end_time):
        self.__logs_litellm(**kwargs)

    async def async_log_stream_event(self, kwargs, response_obj, start_time, end_time):
        self.__logs_litellm(**kwargs)

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        self.__logs_litellm(**kwargs)

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        self.__logs_litellm(**kwargs)

    def __logs_litellm(self, **kwargs):
        logger.info("logging llms call")
        litellm_params = kwargs.get('litellm_params')
        self.__save_logs(**{'response': json.loads(kwargs.get('original_response')) if kwargs.get('original_response') else None,
                            'start_time': kwargs.get('start_time'),
                            'end_time': kwargs.get('end_time'),
                            'cost': kwargs.get("response_cost"),
                            'llm_call_id': litellm_params.get('litellm_call_id'),
                            'llm_provider': litellm_params.get('custom_llm_provider'),
                            'model_params': kwargs.get("additional_args", {}).get("complete_input_dict"),
                            'metadata': litellm_params.get('metadata')})

    def __save_logs(self, **kwargs):
        print(LLMLogs(**kwargs).save().to_mongo().to_dict())

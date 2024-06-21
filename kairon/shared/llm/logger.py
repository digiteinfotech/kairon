from litellm.integrations.custom_logger import CustomLogger
from .data_objects import LLMLogs
import ujson as json


class LiteLLMLogger(CustomLogger):
    def log_pre_api_call(self, model, messages, kwargs):
        pass

    def log_post_api_call(self, kwargs, response_obj, start_time, end_time):
        pass

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
        litellm_params = kwargs['litellm_params']
        self.__save_logs(**{'response': json.loads(kwargs['original_response']),
                            'start_time': kwargs['start_time'],
                            'end_time': kwargs['end_time'],
                            'cost': kwargs["response_cost"],
                            'llm_call_id': litellm_params['litellm_call_id'],
                            'llm_provider': litellm_params['custom_llm_provider'],
                            'model_params': kwargs["additional_args"]["complete_input_dict"],
                            'metadata': litellm_params['metadata']})

    def __save_logs(self, **kwargs):
        LLMLogs(**kwargs).save()

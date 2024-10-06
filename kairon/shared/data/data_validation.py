from uuid6 import uuid7

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.actions.models import ActionParameterType, DbActionOperationType
import ast


class DataValidation:
    @staticmethod
    def validate_http_action(bot: str, data: dict):
        action_param_types = {param.value for param in ActionParameterType}
        data_error = []
        if data.get('params_list'):
            for param in data.get('params_list'):
                if not param.get('key'):
                    data_error.append('Invalid params_list for http action: ' + data['action_name'])
                    continue
                if param.get('parameter_type') not in action_param_types:
                    data_error.append('Invalid params_list for http action: ' + data['action_name'])
                    continue
                if param.get('parameter_type') == 'slot' and not param.get('value'):
                    param['value'] = param.get('key')

        if data.get('headers'):
            for param in data.get('headers'):
                if not param.get('key'):
                    data_error.append('Invalid headers for http action: ' + data['action_name'])
                    continue
                if param.get('parameter_type') not in action_param_types:
                    data_error.append('Invalid headers for http action: ' + data['action_name'])
                    continue
                if param.get('parameter_type') == 'slot' and not param.get('value'):
                    param['value'] = param.get('key')

        return data_error

    @staticmethod
    def validate_form_validation_action(bot: str, data: dict):
        data_error = []
        if data.get('validation_semantic') and not isinstance(data['validation_semantic'], str):
            data_error.append(f'Invalid validation semantic: {data["name"]}')
        if data.get('slot_set'):
            if Utility.check_empty_string(data['slot_set'].get('type')):
                data_error.append('slot_set should have type current as default!')
            if data['slot_set'].get('type') == 'current' and not Utility.check_empty_string(
                    data['slot_set'].get('value')):
                data_error.append('slot_set with type current should not have any value!')
            if data['slot_set'].get('type') == 'slot' and Utility.check_empty_string(
                    data['slot_set'].get('value')):
                data_error.append('slot_set with type slot should have a valid slot value!')
            if data['slot_set'].get('type') not in ['current', 'custom', 'slot']:
                data_error.append('Invalid slot_set type!')
        return data_error

    @staticmethod
    def validate_database_action(bot: str, data: dict):
        data_error = []
        for idx, item in enumerate(data.get('payload', [])):
            if not item.get('query_type') or not item.get('type') or not item.get('value'):
                data_error.append(f"Payload {idx} must contain fields 'query_type', 'type' and 'value'!")
            if item.get('query_type') not in [qtype.value for qtype in DbActionOperationType]:
                data_error.append(f"Unknown query_type found: {item['query_type']} in payload {idx}")
        return data_error

    @staticmethod
    def validate_prompt_action(bot: str, data: dict):
        data_error = []
        if data.get('num_bot_responses') and (
                data['num_bot_responses'] > 5 or not isinstance(data['num_bot_responses'], int)):
            data_error.append(
                f'num_bot_responses should not be greater than 5 and of type int: {data.get("name")}')
        llm_prompts_errors = DataValidation.validate_llm_prompts(data['llm_prompts'])
        if data.get('hyperparameters'):
            llm_hyperparameters_errors = DataValidation.validate_llm_prompts_hyperparameters(
                data.get('hyperparameters'), data.get("llm_type", "openai"), bot)
            data_error.extend(llm_hyperparameters_errors)
        data_error.extend(llm_prompts_errors)

        return data_error

    @staticmethod
    def validate_pyscript_action(bot, data: dict):
        data_error = []
        if not data.get('source_code'):
            data_error.append('Script is required for pyscript action!')
            return data_error

        compile_time_error = DataValidation.validate_python_script_compile_time(data['source_code'])
        if compile_time_error:
            data_error.append(f"Error in python script: {compile_time_error}")
        return data_error

    @staticmethod
    def validate_python_script_compile_time(script: str):
        try:
            ast.parse(script)
        except SyntaxError as e:
            return e.msg
        return None

    @staticmethod
    def validate_llm_prompts_hyperparameters(hyperparameters: dict, llm_type: str, bot: str = None):
        error_list = []
        try:
            Utility.validate_llm_hyperparameters(hyperparameters, llm_type, bot, AppException)
        except AppException as e:
            error_list.append(e.__str__())
        return error_list

    @staticmethod
    def validate_llm_prompts(llm_prompts: list):
        error_list = []
        system_prompt_count = 0
        history_prompt_count = 0
        for prompt in llm_prompts:
            if prompt.get('hyperparameters') is not None:
                hyperparameters = prompt.get('hyperparameters')
                for key, value in hyperparameters.items():
                    if key == 'similarity_threshold':
                        if not (0.3 <= value <= 1.0) or not (
                                isinstance(value, float) or isinstance(value, int)):
                            error_list.append(
                                f"similarity_threshold should be within 0.3 and 1.0 and of type int or float!")
                    if key == 'top_results' and (value > 30 or not isinstance(value, int)):
                        error_list.append("top_results should not be greater than 30 and of type int!")

            if prompt.get('type') == 'system':
                system_prompt_count += 1
            elif prompt.get('source') == 'history':
                history_prompt_count += 1
            if prompt.get('type') not in ['user', 'system', 'query']:
                error_list.append('Invalid prompt type')
            if prompt.get('source') not in ['static', 'slot', 'action', 'history', 'bot_content']:
                error_list.append('Invalid prompt source')
            if prompt.get('type') and not isinstance(prompt.get('type'), str):
                error_list.append('type in LLM Prompts should be of type string.')
            if prompt.get('source') and not isinstance(prompt.get('source'), str):
                error_list.append('source in LLM Prompts should be of type string.')
            if prompt.get('instructions') and not isinstance(prompt.get('instructions'), str):
                error_list.append('Instructions in LLM Prompts should be of type string.')
            if prompt.get('type') == 'system' and prompt.get('source') != 'static':
                error_list.append('System prompt must have static source')
            if prompt.get('type') == 'query' and prompt.get('source') != 'static':
                error_list.append('Query prompt must have static source')
            if not prompt.get('data') and prompt.get('source') == 'action':
                error_list.append('Data must contain action name')
            if not prompt.get('data') and prompt.get('source') == 'slot':
                error_list.append('Data must contain slot name')
            if Utility.check_empty_string(prompt.get('name')):
                error_list.append('Name cannot be empty')
            if prompt.get('data') and not isinstance(prompt.get('data'), str):
                error_list.append('data field in prompts should of type string.')
            if not prompt.get('data') and prompt.get('source') == 'static':
                error_list.append('data is required for static prompts')
            if prompt.get('source') == 'bot_content' and Utility.check_empty_string(prompt.get('data')):
                error_list.append("Collection is required for bot content prompts!")
            if system_prompt_count > 1:
                error_list.append('Only one system prompt can be present')
            if system_prompt_count == 0:
                error_list.append('System prompt is required')
            if history_prompt_count > 1:
                error_list.append('Only one history source can be present')
        return error_list

    @staticmethod
    def validate_callback_config(bot: str, data: dict):
        data_error = []
        if not data.get('pyscript_code'):
            data_error.append('pyscript_code is required')
            return data_error

        compile_time_error = DataValidation.validate_python_script_compile_time(data['pyscript_code'])
        if compile_time_error:
            data_error.append(f"Error in python script: {compile_time_error}")
        return data_error

    @staticmethod
    def modify_callback_config(bot: str, data: dict) -> dict:
        data['token_hash'] = uuid7().hex
        return data

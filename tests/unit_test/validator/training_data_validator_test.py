import json
import re

import pytest

from kairon.exceptions import AppException
from kairon.importer.validator.file_validator import TrainingDataValidator
from kairon.shared.utils import Utility


class TestTrainingDataValidator:

    def test_config_validation(self):
        config = Utility.load_yaml("./tests/testing_data/yml_training_files/config.yml")
        TrainingDataValidator.validate_rasa_config(config)

    def test_config_validation_invalid_pipeline(self):
        Utility.load_environment()
        config = Utility.load_yaml("./tests/testing_data/yml_training_files/config.yml")
        config.get('pipeline').append({'name': "XYZ"})
        error = TrainingDataValidator.validate_rasa_config(config)
        assert error[0] == "Invalid component XYZ"

    def test_config_validation_invalid_config(self):
        Utility.load_environment()
        config = Utility.load_yaml("./tests/testing_data/yml_training_files/config.yml")
        config.get('policies').append({'name': "XYZ"})
        error = TrainingDataValidator.validate_rasa_config(config)
        assert error[0] == "Invalid policy XYZ"

    @pytest.mark.asyncio
    async def test_validate_with_file_importer_invalid_yaml_format(self):
        # domain
        root = 'tests/testing_data/all'
        domain_path = 'tests/testing_data/validator/invalid_yaml/domain.yml'
        nlu_path = 'tests/testing_data/all/data'
        config_path = 'tests/testing_data/all/config.yml'
        with pytest.raises(AppException):
            await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)

        # config
        root = 'tests/testing_data/all'
        domain_path = 'tests/testing_data/all/domain.yml'
        nlu_path = 'tests/testing_data/all/data'
        config_path = 'tests/testing_data/validator/invalid_yaml/config.yml'
        with pytest.raises(AppException):
            await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)

        # nlu
        root = 'tests/testing_data/all'
        domain_path = 'tests/testing_data/all/domain.yml'
        nlu_path = 'tests/testing_data/validator/invalid_yaml/data'
        config_path = 'tests/testing_data/all/config.yml'
        with pytest.raises(AppException):
            await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)

        # stories
        root = 'tests/testing_data/all'
        domain_path = 'tests/testing_data/all/domain.yml'
        nlu_path = 'tests/testing_data/validator/invalid_yaml/data_2'
        config_path = 'tests/testing_data/all/config.yml'
        with pytest.raises(AppException):
            await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)

    @pytest.mark.asyncio
    async def test_validate_intent_mismatch(self):
        root = 'tests/testing_data/validator/intent_name_mismatch'
        domain_path = 'tests/testing_data/validator/intent_name_mismatch/domain.yml'
        nlu_path = 'tests/testing_data/validator/intent_name_mismatch/data'
        config_path = 'tests/testing_data/validator/intent_name_mismatch/config.yml'
        validator = await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)
        with pytest.raises(AppException):
            validator.validate_training_data()

        validator.validate_training_data(False)
        assert validator.summary['intents'][
                   0] == "The intent 'affirm' is listed in the domain file, but is not found in the NLU training data."
        assert validator.summary['intents'][
                   1] == "The intent 'more_info' is listed in the domain file, but is not found in the NLU training data."
        assert validator.summary['intents'][
                   2] == "There is a message in the training data labeled with intent 'deny'. This intent is not listed in your domain."
        assert not validator.summary.get('utterances')
        assert not validator.summary.get('stories')
        assert not validator.summary.get('training_examples')
        assert not validator.summary.get('domain')
        assert not validator.summary.get('config')

    @pytest.mark.asyncio
    async def test_validate_empty_domain(self):
        root = 'tests/testing_data/validator/empty_domain'
        domain_path = 'tests/testing_data/validator/empty_domain/domain.yml'
        nlu_path = 'tests/testing_data/validator/valid/data'
        config_path = 'tests/testing_data/validator/valid/config.yml'
        validator = await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)
        with pytest.raises(AppException):
            validator.validate_training_data()

        validator.validate_training_data(False)
        assert validator.summary['intents']
        assert not validator.summary['utterances']
        assert validator.summary.get('stories')
        assert not validator.summary.get('training_examples')
        assert validator.summary['domain'] == ['domain.yml is empty!']
        assert not validator.summary.get('config')

    @pytest.mark.asyncio
    async def test_validate_story_with_conflicts(self):
        root = 'tests/testing_data/validator/conflicting_stories'
        domain_path = 'tests/testing_data/validator/conflicting_stories/domain.yml'
        nlu_path = 'tests/testing_data/validator/conflicting_stories/data'
        config_path = 'tests/testing_data/validator/conflicting_stories/config.yml'
        with pytest.raises(AppException):
            validator = await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)
            validator.validate_training_data()

        validator = await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)
        validator.validate_training_data(False)
        assert not validator.summary.get('intents')
        assert not validator.summary.get('utterances')
        assert validator.summary['stories'][
                   0] == "Story structure conflict after intent 'deny':\n  utter_goodbye predicted in 'deny'\n  utter_thanks predicted in 'refute'\n"
        assert not validator.summary.get('training_examples')
        assert not validator.summary.get('domain')
        assert not validator.summary.get('config')

    @pytest.mark.asyncio
    async def test_validate_intent_in_story_not_in_domain(self):
        root = 'tests/testing_data/validator/intent_missing_in_domain'
        domain_path = 'tests/testing_data/validator/intent_missing_in_domain/domain.yml'
        nlu_path = 'tests/testing_data/validator/intent_missing_in_domain/data'
        config_path = 'tests/testing_data/validator/intent_missing_in_domain/config.yml'
        with pytest.raises(AppException):
            validator = await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)
            validator.validate_training_data()

        validator = await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)
        validator.validate_training_data(False)
        assert 'The intent \'deny\' is used in your stories, but it is not listed in the domain file. You should add it to your domain file!' in \
               validator.summary['intents']
        assert 'The intent \'more_info\' is used in your stories, but it is not listed in the domain file. You should add it to your domain file!' in \
               validator.summary['intents']
        assert set(validator.summary['intents']) == {
            "There is a message in the training data labeled with intent 'deny'. This intent is not listed in your domain.",
            "The intent 'more_info' is used in your stories, but it is not listed in the domain file. You should add it to your domain file!",
            "There is a message in the training data labeled with intent 'more_info'. This intent is not listed in your domain.",
            "The intent 'deny' is used in your stories, but it is not listed in the domain file. You should add it to your domain file!"
        }
        assert not validator.summary.get('utterances')
        assert not validator.summary.get('stories')
        assert not validator.summary.get('training_examples')
        assert not validator.summary.get('domain')
        assert not validator.summary.get('config')

    @pytest.mark.asyncio
    async def test_validate_intent_not_used_in_any_story(self):
        root = 'tests/testing_data/validator/orphan_intents'
        domain_path = 'tests/testing_data/validator/orphan_intents/domain.yml'
        nlu_path = 'tests/testing_data/validator/orphan_intents/data'
        config_path = 'tests/testing_data/validator/orphan_intents/config.yml'
        with pytest.raises(AppException):
            validator = await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)
            validator.validate_training_data()

        validator = await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)
        validator.validate_training_data(False)
        assert validator.summary['intents'][0] == 'The intent \'bot_challenge\' is not used in any story.'
        assert not validator.summary.get('utterances')
        assert not validator.summary.get('stories')
        assert not validator.summary.get('training_examples')
        assert not validator.summary.get('domain')
        assert not validator.summary.get('config')

    @pytest.mark.asyncio
    async def test_validate_repeated_training_example(self):
        root = 'tests/testing_data/validator/common_training_examples'
        domain_path = 'tests/testing_data/validator/common_training_examples/domain.yml'
        nlu_path = 'tests/testing_data/validator/common_training_examples/data'
        config_path = 'tests/testing_data/validator/common_training_examples/config.yml'
        with pytest.raises(AppException):
            validator = await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)
            validator.validate_training_data()

        validator = await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)
        validator.validate_training_data(False)
        assert not validator.summary.get('intents')
        assert not validator.summary.get('utterances')
        assert not validator.summary.get('stories')
        assert validator.summary['training_examples'][
                   0] == 'The example \'no\' was found labeled with multiple different intents in the training data. Each annotated message should only appear with one intent. You should fix that conflict The example is labeled with: deny, refute.'
        assert validator.summary['training_examples'][
                   1] == 'The example \'never\' was found labeled with multiple different intents in the training data. Each annotated message should only appear with one intent. You should fix that conflict The example is labeled with: deny, refute.'
        assert not validator.summary.get('domain')
        assert not validator.summary.get('config')

    @pytest.mark.asyncio
    async def test_validate_utterance_in_story_not_in_domain(self):
        root = 'tests/testing_data/validator/utterance_missing_in_domain'
        domain_path = 'tests/testing_data/validator/utterance_missing_in_domain/domain.yml'
        nlu_path = 'tests/testing_data/validator/utterance_missing_in_domain/data'
        config_path = 'tests/testing_data/validator/utterance_missing_in_domain/config.yml'
        with pytest.raises(AppException):
            validator = await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)
            validator.validate_training_data()

        validator = await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)
        validator.validate_training_data(False)
        assert not validator.summary.get('intents')
        assert validator.summary['stories'][
                   0] == 'The action \'utter_goodbye\' is used in the stories, but is not a valid utterance action. Please make sure the action is listed in your domain and there is a template defined with its name.'
        assert not validator.summary.get('utterances')
        assert not validator.summary.get('training_examples')
        assert not validator.summary.get('domain')
        assert not validator.summary.get('config')

    @pytest.mark.asyncio
    async def test_validate_utterance_not_used_in_any_story(self):
        root = 'tests/testing_data/validator/orphan_utterances'
        domain_path = 'tests/testing_data/validator/orphan_utterances/domain.yml'
        nlu_path = 'tests/testing_data/validator/orphan_utterances/data_2'
        config_path = 'tests/testing_data/validator/orphan_utterances/config.yml'
        with pytest.raises(AppException):
            validator = await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)
            validator.validate_training_data()

        validator = await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)
        validator.validate_training_data(False)
        assert not validator.summary.get('intents')
        assert 'The utterance \'utter_good_feedback\' is not used in any story.' in validator.summary['utterances']
        assert 'The utterance \'utter_bad_feedback\' is not used in any story.' in validator.summary['utterances']
        print(set(validator.summary['utterances']))
        assert set(validator.summary['utterances']) == {
            "The utterance 'utter_bad_feedback' is not used in any story.",
            "The action 'utter_feedback' is used in the multiflow_stories, but is not a valid utterance action. Please make sure the action is listed in your domain and there is a template defined with its name.",
            "The action 'utter_offer_help' is used in the multiflow_stories, but is not a valid utterance action. Please make sure the action is listed in your domain and there is a template defined with its name.",
            "The utterance 'utter_more_info' is not used in any story.",
            "The utterance 'utter_query' is not used in any story.",
            "The utterance 'utter_performance' is not used in any story.",
            "The utterance 'utter_iamabot' is not used in any story.",
            "The utterance 'utter_good_feedback' is not used in any story."
        }
        print("\n\n")
        print(set(validator.summary['user_actions']))
        assert set(validator.summary['user_actions']) == {
            "The action 'email_action_one' is a user defined action used in the stories. Please make sure the action is listed in your domain file.",
            "The action 'action_performanceUser1001@digite.com' is a user defined action used in the multiflow_stories, Please make sure the action is listed in your domain file.",
            "The action 'google_search_action' is not used in any story."
        }
        assert not validator.summary.get('stories')
        assert not validator.summary.get('training_examples')
        assert not validator.summary.get('domain')
        assert not validator.summary.get('config')

    @pytest.mark.asyncio
    async def test_validate_valid_training_data(self):
        root = 'tests/testing_data/validator/valid'
        domain_path = 'tests/testing_data/validator/valid/domain.yml'
        nlu_path = 'tests/testing_data/validator/valid/data'
        config_path = 'tests/testing_data/validator/valid/config.yml'
        validator = await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)
        validator.validate_training_data()
        assert not validator.summary.get('intents')
        assert not validator.summary.get('utterances')
        assert not validator.summary.get('stories')
        assert not validator.summary.get('training_examples')
        assert not validator.summary.get('domain')
        assert not validator.summary.get('config')

    @pytest.mark.asyncio
    async def test_validate_valid_training_data_with_multiflow_stories(self):
        root = 'tests/testing_data/multiflow_stories/valid_with_multiflow'
        domain_path = 'tests/testing_data/multiflow_stories/valid_with_multiflow/domain.yml'
        nlu_path = 'tests/testing_data/multiflow_stories/valid_with_multiflow/data'
        config_path = 'tests/testing_data/multiflow_stories/valid_with_multiflow/config.yml'
        validator = await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)
        validator.validate_training_data()
        assert not validator.summary.get('intents')
        assert not validator.summary.get('utterances')
        assert not validator.summary.get('stories')
        assert not validator.summary.get('multiflow_stories')
        assert not validator.summary.get('training_examples')
        assert not validator.summary.get('domain')
        assert not validator.summary.get('config')

    @pytest.mark.asyncio
    async def test_validate_invalid_training_file_path(self):
        root = 'tests/testing_data/invalid_path/domain.yml'
        domain_path = 'tests/testing_data/invalid_path/domain.yml'
        nlu_path = 'tests/testing_data/validator/intent_name_mismatch/data'
        config_path = 'tests/testing_data/validator/intent_name_mismatch/config.yml'
        with pytest.raises(AppException):
            await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)

    @pytest.mark.asyncio
    async def test_validate_config_with_invalid_pipeline(self):
        root = 'tests/testing_data/validator/invalid_config'
        domain_path = 'tests/testing_data/validator/invalid_config/domain.yml'
        nlu_path = 'tests/testing_data/validator/invalid_config/data'
        config_path = 'tests/testing_data/validator/invalid_config/config.yml'
        with pytest.raises(AppException):
            validator = await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)
            validator.validate_training_data()

        validator = await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)
        validator.validate_training_data(False)
        assert not validator.summary.get('intents')
        assert not validator.summary.get('utterances')
        assert not validator.summary.get('stories')
        assert not validator.summary.get('training_examples')
        assert not validator.summary.get('domain')
        assert not validator.summary['config'] == "Failed to load the component 'CountTokenizer'"

    @pytest.mark.asyncio
    async def test_validate_invalid_multiflow_stories(self):
        root = 'tests/testing_data/multiflow_stories/invalid_yml_multiflow'
        domain_path = 'tests/testing_data/multiflow_stories/invalid_yml_multiflow/domain.yml'
        nlu_path = 'tests/testing_data/multiflow_stories/invalid_yml_multiflow/data'
        config_path = 'tests/testing_data/multiflow_stories/invalid_yml_multiflow/config.yml'
        validator = await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)
        with pytest.raises(AppException, match="Invalid multiflow_stories.yml. Check logs!"):
            validator.validate_training_data()

    def test_validate_http_action_empty_content(self):
        test_dict = {'http_action': []}
        assert TrainingDataValidator.validate_custom_actions(test_dict)
        assert TrainingDataValidator.validate_custom_actions([{}])

    def test_validate_http_action_error_duplicate(self):
        test_dict = {'http_action': [{'action_name': "act2", 'http_url': "http://www.alphabet.com", "response": 'asdf',
                                      "request_method": 'POST'},
                                     {'action_name': "act2", 'http_url': "http://www.alphabet.com", "response": 'asdf',
                                      "request_method": 'POST'}]}
        errors = TrainingDataValidator.validate_custom_actions(test_dict)
        assert 'Duplicate http action found: act2' in errors[1]['http_actions']

    def test_validate_http_action_error_missing_field(self):
        test_dict = {
            'http_action': [{'http_url': "http://www.alphabet.com", "response": 'asdf', "request_method": 'POST'}]}
        is_data_invalid, errors, component_count = TrainingDataValidator.validate_custom_actions(test_dict)
        assert "Required http action fields" in errors['http_actions'][0]

    def test_validate_http_action_invalid_request_method(self):
        test_dict = {"http_action": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                      "params_list": [{"key": 'location', "parameter_type": 'slot', "value": 'slot'}],
                                      "request_method": "OPTIONS", "response": "${RESPONSE}"}]}
        is_data_invalid, errors, component_count = TrainingDataValidator.validate_custom_actions(test_dict)
        assert 'Invalid request method: rain_today' in errors['http_actions']

    def test_validate_http_action_empty_params_list(self):
        test_dict = {"http_action": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                      "params_list": [{"key": '', "parameter_type": '', "value": ''}],
                                      "request_method": "GET", "response": "${RESPONSE}"}]}
        is_data_invalid, errors, component_count = TrainingDataValidator.validate_custom_actions(test_dict)
        assert 'Invalid params_list for http action: rain_today' in errors['http_actions']

    def test_validate_http_action_empty_headers(self):
        test_dict = {"http_action": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                      "headers": [],
                                      "request_method": "GET", "response": "${RESPONSE}"}]}
        assert TrainingDataValidator.validate_custom_actions(test_dict)

    def test_validate_http_action_header_with_empty_key(self):
        test_dict = {"http_action": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                      "headers": [{"key": '', "parameter_type": '', "value": ''}],
                                      "request_method": "GET", "response": "${RESPONSE}"}]}
        is_data_invalid, errors, component_count = TrainingDataValidator.validate_custom_actions(test_dict)
        assert 'Invalid headers for http action: rain_today' in errors['http_actions']

    def test_validate_http_action_header_with_no_parameter_type(self):
        test_dict = {"http_action": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                      "headers": [{"key": 'location', "parameter_type": '', "value": ''}],
                                      "request_method": "GET", "response": "${RESPONSE}"}]}
        is_data_invalid, errors, component_count = TrainingDataValidator.validate_custom_actions(test_dict)
        assert 'Invalid headers for http action: rain_today' in errors['http_actions']

    def test_validate_http_action_header_with_empty_slot_value(self):
        test_dict = {"http_action": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                      "headers": [
                                          {"key": 'location', "parameter_type": 'value', "value": 'Mumbai'},
                                          {"key": 'username', "parameter_type": 'slot', "value": ''}],
                                      "request_method": "GET", "response": "${RESPONSE}"}]}
        TrainingDataValidator.validate_custom_actions(test_dict)
        assert test_dict['http_action'][0]['headers'][1]['value'] == 'username'

    def test_validate_http_action_header(self):
        test_dict = {"http_action": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                      "headers": [
                                          {"key": 'location', "parameter_type": 'value', "value": 'Mumbai'},
                                          {"key": 'paid_user', "parameter_type": 'slot', "value": ''},
                                          {"key": 'username', "parameter_type": 'sender_id'},
                                          {"key": 'user_msg', "parameter_type": 'user_message'}],
                                      "request_method": "GET", "response": "${RESPONSE}"}]}
        TrainingDataValidator.validate_custom_actions(test_dict)
        assert test_dict['http_action'][0]['headers'][1]['value'] == 'paid_user'

    def test_validate_http_action_header_invalid_parameter_type(self):
        test_dict = {"http_action": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                      "headers": [
                                          {"key": 'location', "parameter_type": 'text', "value": 'Mumbai'}],
                                      "request_method": "GET", "response": "${RESPONSE}"}]}
        is_data_invalid, errors, component_count = TrainingDataValidator.validate_custom_actions(test_dict)
        assert 'Invalid headers for http action: rain_today' in errors['http_actions']

    def test_validate_http_action_empty_params_list_2(self):
        test_dict = {"http_action": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                      "params_list": [{"key": 'location', "parameter_type": '', "value": ''}],
                                      "request_method": "GET", "response": "${RESPONSE}"}]}
        is_data_invalid, errors, component_count = TrainingDataValidator.validate_custom_actions(test_dict)
        assert 'Invalid params_list for http action: rain_today' in errors['http_actions']

    def test_validate_http_action_empty_slot_type(self):
        test_dict = {"http_action": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                      "params_list": [
                                          {"key": 'location', "parameter_type": 'value', "value": 'Mumbai'},
                                          {"key": 'username', "parameter_type": 'slot', "value": ''},
                                          {"key": 'username', "parameter_type": 'user_message', "value": ''},
                                          {"key": 'username', "parameter_type": 'sender_id', "value": ''}],
                                      "request_method": "GET", "response": "${RESPONSE}"}]}
        assert TrainingDataValidator.validate_custom_actions(test_dict)
        assert test_dict['http_action'][0]['params_list'][1]['value'] == 'username'

    def test_validate_http_action_params_list_4(self):
        test_dict = {"http_action": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                      "params_list": [{"key": 'location', "parameter_type": 'value', "value": ''}],
                                      "request_method": "GET", "response": "${RESPONSE}"}]}
        assert TrainingDataValidator.validate_custom_actions(test_dict)

        test_dict = {"http_action": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                      "params_list": [{"key": 'location', "parameter_type": 'value', "value": None}],
                                      "request_method": "GET", "response": "${RESPONSE}"}]}
        assert TrainingDataValidator.validate_custom_actions(test_dict)

    def test_validate_http_action_empty_params_list_5(self):
        test_dict = {"http_action": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                      "request_method": "GET", "response": "${RESPONSE}"}]}
        assert TrainingDataValidator.validate_custom_actions(test_dict)

    def test_validate_http_action_empty_params_list_6(self):
        test_dict = {"http_action": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                      "params_list": [], "request_method": "GET", "response": "${RESPONSE}"}]}
        assert TrainingDataValidator.validate_custom_actions(test_dict)

    def test_validate_http_action_empty_params_list_7(self):
        test_dict = {"http_action": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                      "params_list": [{"key": 'location', "parameter_type": 'sender_id', "value": ''}],
                                      "request_method": "GET", "response": "${RESPONSE}"}]}
        assert TrainingDataValidator.validate_custom_actions(test_dict)

    def test_validate_custom_actions(self):
        test_dict = {"http_action": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                      "params_list": [{"key": 'location', "parameter_type": 'sender_id', "value": ''}],
                                      "request_method": "GET", "response": "${RESPONSE}"}]}
        is_data_invalid, error_summary, component_count = TrainingDataValidator.validate_custom_actions(test_dict)
        assert not is_data_invalid
        assert error_summary == {'http_actions': [], 'email_actions': [], 'form_validation_actions': [],
                                 'google_search_actions': [], 'jira_actions': [], 'slot_set_actions': [],
                                 'zendesk_actions': [], 'pipedrive_leads_actions': [], 'prompt_actions': []}
        assert component_count

    def test_validate_custom_actions_with_errors(self):
        with open('tests/testing_data/actions/validation_action_data.json', 'r') as file:
            data = file.read()
        test_dict = json.loads(data)
        is_data_invalid, error_summary, component_count = TrainingDataValidator.validate_custom_actions(test_dict)
        assert is_data_invalid
        assert len(error_summary['http_actions']) == 4
        assert len(error_summary['slot_set_actions']) == 7
        assert len(error_summary['form_validation_actions']) == 10
        assert len(error_summary['email_actions']) == 3
        assert len(error_summary['jira_actions']) == 4
        assert len(error_summary['google_search_actions']) == 2
        assert len(error_summary['zendesk_actions']) == 2
        assert len(error_summary['pipedrive_leads_actions']) == 3
        assert len(error_summary['prompt_actions']) == 46
        required_fields_error = error_summary["prompt_actions"][18]
        assert re.match(r"Required fields .* not found in action: prompt_action_with_no_llm_prompts", required_fields_error)
        del error_summary["prompt_actions"][18]
        assert error_summary['prompt_actions'] == [
            'top_results should not be greater than 30 and of type int: prompt_action_invalid_query_prompt',
            'similarity_threshold should be within 0.3 and 1 and of type int or float: prompt_action_invalid_query_prompt',
            'System prompt is required', 'Query prompt must have static source',
            'Name cannot be empty', 'System prompt is required',
            'num_bot_responses should not be greater than 5 and of type int: prompt_action_invalid_num_bot_responses',
            'data field in prompts should of type string.', 'data is required for static prompts',
            'Temperature must be between 0.0 and 2.0!', 'max_tokens must be between 5 and 4096!',
            'top_p must be between 0.0 and 1.0!', 'n must be between 1 and 5!',
            'presence_penality must be between -2.0 and 2.0!', 'frequency_penalty must be between -2.0 and 2.0!',
            'logit_bias must be a dictionary!', 'System prompt must have static source',
            'Only one bot_content source can be present',
            'Duplicate action found: test_add_prompt_action_one',
            'Invalid action configuration format. Dictionary expected.',
            'Temperature must be between 0.0 and 2.0!', 'max_tokens must be between 5 and 4096!',
            'top_p must be between 0.0 and 1.0!', 'n must be between 1 and 5!',
            'Stop must be None, a string, an integer, or an array of 4 or fewer strings or integers.',
            'presence_penality must be between -2.0 and 2.0!',
            'frequency_penalty must be between -2.0 and 2.0!',
            'logit_bias must be a dictionary!', 'Only one system prompt can be present',
            'Invalid prompt type', 'Invalid prompt source', 'Only one system prompt can be present',
            'Invalid prompt type', 'Invalid prompt source', 'type in LLM Prompts should be of type string.',
            'source in LLM Prompts should be of type string.', 'Instructions in LLM Prompts should be of type string.',
            'Only one system prompt can be present', 'Data must contain action name',
            'Only one system prompt can be present', 'Data must contain slot name',
            'Only one system prompt can be present', 'Only one system prompt can be present',
            'Only one system prompt can be present', 'Only one history source can be present']
        assert component_count == {'http_actions': 7, 'slot_set_actions': 10, 'form_validation_actions': 9,
                                   'email_actions': 5, 'google_search_actions': 5, 'jira_actions': 6,
                                   'zendesk_actions': 4, 'pipedrive_leads_actions': 5, 'prompt_actions': 8}

    def test_validate_multiflow_stories(self):
        with open('tests/testing_data/multiflow_stories/multiflow_test_data.json', 'r') as file:
            data = file.read()
        test_dict = json.loads(data)
        errors, count = TrainingDataValidator.validate_multiflow_stories(test_dict)
        assert len(errors) == 23
        assert count == 16

    def test_validate_multiflow_stories_empty_content(self):
        test_dict = {'multiflow_story': []}
        assert TrainingDataValidator.validate_multiflow_stories(test_dict)
        assert TrainingDataValidator.validate_multiflow_stories([{}])
        test = {None}
        assert TrainingDataValidator.validate_multiflow_stories(test)

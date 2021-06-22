import pytest

from kairon import Utility
from kairon.exceptions import AppException
from kairon.importer.validator.file_validator import TrainingDataValidator


class TestTrainingDataValidator:

    def test_config_validation(self):
        config = Utility.load_yaml("./tests/testing_data/yml_training_files/config.yml")
        TrainingDataValidator.validate_rasa_config(config)

    def test_config_validation_invalid_pipeline(self):
        config = Utility.load_yaml("./tests/testing_data/yml_training_files/config.yml")
        config.get('pipeline').append({'name': "XYZ"})
        error = TrainingDataValidator.validate_rasa_config(config)
        assert error[0] == "Invalid component XYZ"

    def test_config_validation_invalid_config(self):
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
                   1] == "There is a message in the training data labeled with intent 'deny'. This intent is not listed in your domain."
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
        assert validator.summary['utterances']
        assert not validator.summary.get('stories')
        assert not validator.summary.get('training_examples')
        assert validator.summary['domain'] == 'domain.yml is empty!'
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
        assert validator.summary['intents'][
                   0] == 'There is a message in the training data labeled with intent \'deny\'. This intent is not listed in your domain.'
        assert validator.summary['intents'][
                   1] == 'The intent \'deny\' is used in your stories, but it is not listed in the domain file. You should add it to your domain file!'
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
        assert validator.summary['intents'][0] == 'The intent \'affirm\' is not used in any story.'
        assert validator.summary['intents'][1] == 'The intent \'bot_challenge\' is not used in any story.'
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
        root= 'tests/testing_data/validator/utterance_missing_in_domain'
        domain_path = 'tests/testing_data/validator/utterance_missing_in_domain/domain.yml'
        nlu_path = 'tests/testing_data/validator/utterance_missing_in_domain/data'
        config_path = 'tests/testing_data/validator/utterance_missing_in_domain/config.yml'
        with pytest.raises(AppException):
            validator = await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)
            validator.validate_training_data()

        validator = await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)
        validator.validate_training_data(False)
        assert not validator.summary.get('intents')
        assert validator.summary['utterances'][
                   0] == 'The action \'utter_goodbye\' is used in the stories, but is not a valid utterance action. Please make sure the action is listed in your domain and there is a template defined with its name.'
        assert not validator.summary.get('stories')
        assert not validator.summary.get('training_examples')
        assert not validator.summary.get('domain')
        assert not validator.summary.get('config')

    @pytest.mark.asyncio
    async def test_validate_utterance_not_used_in_any_story(self):
        root = 'tests/testing_data/validator/orphan_utterances'
        domain_path = 'tests/testing_data/validator/orphan_utterances/domain.yml'
        nlu_path = 'tests/testing_data/validator/orphan_utterances/data'
        config_path = 'tests/testing_data/validator/orphan_utterances/config.yml'
        with pytest.raises(AppException):
            validator = await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)
            validator.validate_training_data()

        validator = await TrainingDataValidator.from_training_files(nlu_path, domain_path, config_path, root)
        validator.validate_training_data(False)
        assert not validator.summary.get('intents')
        assert 'The utterance \'utter_good_feedback\' is not used in any story.' in validator.summary['utterances']
        assert 'The utterance \'utter_bad_feedback\' is not used in any story.' in validator.summary['utterances']
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

    def test_validate_http_action_empty_content(self):
        test_dict = {'http_actions': []}
        assert not TrainingDataValidator.validate_http_actions(test_dict)
        assert not TrainingDataValidator.validate_http_actions({})

    def test_validate_http_action_error_duplicate(self):
        test_dict = {'http_actions': [{'action_name': "act2", 'http_url': "http://www.alphabet.com", "response": 'asdf',
                                       "request_method": 'POST'},
                                      {'action_name': "act2", 'http_url': "http://www.alphabet.com", "response": 'asdf',
                                       "request_method": 'POST'}]}
        errors = TrainingDataValidator.validate_http_actions(test_dict)
        assert 'Duplicate http action found: act2' in errors

    def test_validate_http_action_error_missing_field(self):
        test_dict = {
            'http_actions': [{'http_url': "http://www.alphabet.com", "response": 'asdf', "request_method": 'POST'}]}
        errors = TrainingDataValidator.validate_http_actions(test_dict)
        assert 'Required http action fields not found' in errors

    def test_validate_http_action_invalid_request_method(self):
        test_dict = {"http_actions": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                       "params_list": [{"key": 'location', "parameter_type": 'slot', "value": 'slot'}],
                                       "request_method": "OPTIONS", "response": "${RESPONSE}"}]}
        errors = TrainingDataValidator.validate_http_actions(test_dict)
        assert 'Invalid request method: rain_today' in errors

    def test_validate_http_action_empty_params_list(self):
        test_dict = {"http_actions": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                       "params_list": [{"key": '', "parameter_type": '', "value": ''}],
                                       "request_method": "GET", "response": "${RESPONSE}"}]}
        errors = TrainingDataValidator.validate_http_actions(test_dict)
        assert 'Invalid params_list for http action: rain_today' in errors

    def test_validate_http_action_empty_params_list_2(self):
        test_dict = {"http_actions": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                       "params_list": [{"key": 'location', "parameter_type": '', "value": ''}],
                                       "request_method": "GET", "response": "${RESPONSE}"}]}
        errors = TrainingDataValidator.validate_http_actions(test_dict)
        assert 'Invalid params_list for http action: rain_today' in errors

    def test_validate_http_action_empty_params_list_3(self):
        test_dict = {"http_actions": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                       "params_list": [
                                           {"key": 'location', "parameter_type": 'value', "value": 'Mumbai'},
                                           {"key": 'username', "parameter_type": 'slot', "value": ''}],
                                       "request_method": "GET", "response": "${RESPONSE}"}]}
        TrainingDataValidator.validate_http_actions(test_dict)
        assert test_dict['http_actions'][0]['params_list'][1]['value'] == 'username'

    def test_validate_http_action_params_list_4(self):
        test_dict = {"http_actions": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                       "params_list": [{"key": 'location', "parameter_type": 'value', "value": ''}],
                                       "request_method": "GET", "response": "${RESPONSE}"}]}
        assert not TrainingDataValidator.validate_http_actions(test_dict)

        test_dict = {"http_actions": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                       "params_list": [{"key": 'location', "parameter_type": 'value', "value": None}],
                                       "request_method": "GET", "response": "${RESPONSE}"}]}
        assert not TrainingDataValidator.validate_http_actions(test_dict)

    def test_validate_http_action_empty_params_list_5(self):
        test_dict = {"http_actions": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                       "request_method": "GET", "response": "${RESPONSE}"}]}
        assert not TrainingDataValidator.validate_http_actions(test_dict)

    def test_validate_http_action_empty_params_list_6(self):
        test_dict = {"http_actions": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                       "params_list": [], "request_method": "GET", "response": "${RESPONSE}"}]}
        assert not TrainingDataValidator.validate_http_actions(test_dict)

    def test_validate_http_action_empty_params_list_7(self):
        test_dict = {"http_actions": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                       "params_list": [{"key": 'location', "parameter_type": 'sender_id', "value": ''}],
                                       "request_method": "GET", "response": "${RESPONSE}"}]}
        assert not TrainingDataValidator.validate_http_actions(test_dict)

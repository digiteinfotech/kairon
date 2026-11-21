from tests.unit_test.data_processor.data_processor_support import *  # noqa: F403
from tests.unit_test.data_processor.data_processor_support import (
    MongoProcessorTestBase,
    fast_rasa_training,
)

class TestMongoProcessor(MongoProcessorTestBase):
    def test_add_pyscript_action_empty_name(self):
        bot = 'test_bot'
        user = 'test_user'
        action = "test_add_pyscript_action_empty_name"
        script = "bot_response='hello world'"
        processor = MongoProcessor()
        pyscript_config = PyscriptActionRequest(
            name=action,
            source_code=script,
            dispatch_response=False,
        )
        pyscript_config_dict = pyscript_config.model_dump()
        pyscript_config_dict['name'] = ''
        with pytest.raises(ValidationError, match="Action name cannot be empty"):
            processor.add_pyscript_action(pyscript_config_dict, user, bot)

    def test_add_pyscript_action_empty_source_code(self):
        bot = 'test_bot'
        user = 'test_user'
        action = "test_add_pyscript_action_empty_source_code"
        script = "bot_response='hello world'"
        processor = MongoProcessor()
        pyscript_config = PyscriptActionRequest(
            name=action,
            source_code=script,
            dispatch_response=False,
        )
        pyscript_config_dict = pyscript_config.model_dump()
        pyscript_config_dict['source_code'] = ''
        with pytest.raises(ValidationError, match="Source code cannot be empty"):
            processor.add_pyscript_action(pyscript_config_dict, user, bot)

    def test_add_pyscript_action_with_utter(self):
        bot = 'test_bot'
        user = 'test_user'
        action = "test_add_pyscript_action_empty_name"
        script = "bot_response='hello world'"
        processor = MongoProcessor()
        pyscript_config = PyscriptActionRequest(
            name=action,
            source_code=script,
            dispatch_response=False,
        )
        pyscript_config_dict = pyscript_config.model_dump()
        pyscript_config_dict['name'] = "utter_add_pyscript_action_empty_name"
        with pytest.raises(AppException, match="Action name cannot start with utter_"):
            processor.add_pyscript_action(pyscript_config_dict, user, bot)

    def test_add_pyscript_action(self):
        bot = 'test_bot'
        user = 'test_user'
        action = "test_add_pyscript_action"
        script = "bot_response='hello world'"
        processor = MongoProcessor()
        pyscript_config = PyscriptActionRequest(
            name=action,
            source_code=script,
            dispatch_response=False,
        )
        action_id = processor.add_pyscript_action(pyscript_config.model_dump(), user, bot)
        assert Actions.objects(name=action, status=True, bot=bot).get()
        pyscript_config_action = PyscriptActionConfig.objects(name=action, bot=bot, status=True).get()
        assert str(pyscript_config_action.id) == action_id
        assert pyscript_config_action.name == action
        assert pyscript_config_action.source_code == script
        assert not pyscript_config_action.dispatch_response

    def test_add_pyscript_action_with_name_already_exist(self):
        bot = 'test_bot'
        user = 'test_user'
        action = "test_add_pyscript_action"
        script = "bot_response='hello world'"
        processor = MongoProcessor()
        pyscript_config = PyscriptActionRequest(
            name=action,
            source_code=script,
            dispatch_response=False,
        )
        with pytest.raises(AppException, match="Action exists!"):
            processor.add_pyscript_action(pyscript_config.model_dump(), user, bot)

    def test_add_pyscript_action_case_insensitivity(self):
        bot = 'test_bot'
        user = 'test_user'
        action = "TEST_ADD_PYSCRIPT_ACTION_CASE_INSENSITIVITY"
        script = "bot_response='hello world'"
        processor = MongoProcessor()
        pyscript_config = PyscriptActionRequest(
            name=action,
            source_code=script,
            dispatch_response=False,
        )
        action_id = processor.add_pyscript_action(pyscript_config.model_dump(), user, bot)
        assert Actions.objects(name="test_add_pyscript_action_case_insensitivity", status=True, bot=bot).get()
        pyscript_config_action = PyscriptActionConfig.objects(name="test_add_pyscript_action_case_insensitivity",
                                                              bot=bot, status=True).get()
        assert str(pyscript_config_action.id) == action_id
        assert pyscript_config_action.name == "test_add_pyscript_action_case_insensitivity"
        assert pyscript_config_action.source_code == script
        assert not pyscript_config_action.dispatch_response

    def test_update_pyscript_action_doesnot_exist(self):
        bot = 'test_bot'
        user = 'test_user'
        action = "test_update_pyscript_action"
        script = "bot_response='hello world'"
        processor = MongoProcessor()
        pyscript_config = PyscriptActionRequest(
            name=action,
            source_code=script,
            dispatch_response=False,
        )
        with pytest.raises(AppException, match='Action with name "test_update_pyscript_action" not found'):
            processor.update_pyscript_action(pyscript_config.model_dump(), user, bot)

    def test_update_pyscript_action(self):
        bot = 'test_bot'
        user = 'test_user'
        action = "test_add_pyscript_action"
        script = "bot_response='hello world'"
        processor = MongoProcessor()
        pyscript_config = PyscriptActionRequest(
            name=action,
            source_code=script,
            dispatch_response=True,
        )
        action_id = processor.update_pyscript_action(pyscript_config.model_dump(), user, bot)
        assert Actions.objects(name=action, status=True, bot=bot).get()
        pyscript_config_action = PyscriptActionConfig.objects(name=action, bot=bot, status=True).get()
        assert pyscript_config_action.name == action
        assert pyscript_config_action.source_code == script
        assert pyscript_config_action.dispatch_response

    def test_list_pyscript_actions(self):
        bot = 'test_bot'
        user = 'test_user'
        script1 = "bot_response='hello world'"
        script2 = "bot_response='hello world'"
        processor = MongoProcessor()
        actions = list(processor.list_pyscript_actions(bot, True))
        assert len(actions) == 2
        assert actions[0]['name'] == 'test_add_pyscript_action'
        assert actions[0]['source_code'] == script1
        assert actions[0]['dispatch_response']
        assert actions[1]['name'] == 'test_add_pyscript_action_case_insensitivity'
        assert actions[1]['source_code'] == script2
        assert not actions[1]['dispatch_response']

    def test_delete_pyscript_action(self):
        name = 'test_add_pyscript_action'
        bot = 'test_bot'
        user = 'test_user'
        processor = MongoProcessor()
        processor.delete_action(name, bot, user)
        actions = list(processor.list_pyscript_actions(bot, True))
        assert len(actions) == 1

    def test_delete_pyscript_action_already_deleted(self):
        name = 'test_add_pyscript_action'
        bot = 'test_bot'
        user = 'test_user'
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Action with name "test_add_pyscript_action" not found'):
            processor.delete_action(name, bot, user)

    def test_add_pyscript_action_with_story(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "test_add_pyscript_action_case_insensitivity", "type": "PYSCRIPT_ACTION"},
        ]
        story_dict = {'name': "story with pyscript action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with pyscript action", bot=bot,
                                events__name='test_add_pyscript_action_case_insensitivity', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == "story with pyscript action"]
        assert story_with_form[0]['steps'] == [
            {"name": "greet", "type": "INTENT"},
            {"name": "test_add_pyscript_action_case_insensitivity", "type": "PYSCRIPT_ACTION"},
        ]
        processor.delete_complex_story(story_id, 'STORY', bot, user)

    def test_add_or_overwrite_config_no_existing_config(self):
        bot = 'test_config'
        user = 'test_config'
        processor = MongoProcessor()
        config = Utility.read_yaml('./tests/testing_data/valid_yml/config.yml')
        processor.add_or_overwrite_config(config, bot, user)
        config = Configs.objects().get(bot=bot).to_mongo().to_dict()
        assert config['language'] == 'fr'
        assert len(config['pipeline']) == 9
        assert len(config['policies']) == 3
        rule_policy = next((comp for comp in config["policies"] if 'RulePolicy' in comp['name']), {})
        assert rule_policy['core_fallback_action_name'] == 'action_small_talk'
        assert rule_policy['core_fallback_threshold'] == 0.75
        assert Rules.objects(block_name__iexact=DEFAULT_NLU_FALLBACK_RULE, bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_please_rephrase', bot=bot, status=True).get()

    def test_add_or_overwrite_config(self):
        bot = 'test_config'
        user = 'test_config'
        processor = MongoProcessor()
        config = Utility.read_yaml('./tests/testing_data/valid_yml/config.yml')
        idx = next((idx for idx, comp in enumerate(config["policies"]) if 'RulePolicy' in comp['name']), {})
        del config['policies'][idx]
        processor.add_or_overwrite_config(config, bot, user)
        config = Configs.objects().get(bot=bot).to_mongo().to_dict()
        assert config['language'] == 'fr'
        assert len(config['pipeline']) == 9
        assert len(config['policies']) == 3
        rule_policy = next((comp for comp in config["policies"] if 'RulePolicy' in comp['name']), {})
        assert rule_policy['core_fallback_action_name'] == 'action_default_fallback'
        assert rule_policy['core_fallback_threshold'] == 0.3
        assert Rules.objects(block_name__iexact=DEFAULT_NLU_FALLBACK_RULE, bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_please_rephrase', bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_default', bot=bot, status=True).get()

    def test_add_or_overwrite_config_user_fallback(self):
        bot = 'test_config'
        user = 'test_config'
        processor = MongoProcessor()
        config = Utility.read_yaml('./tests/testing_data/valid_yml/config.yml')
        comp = next((comp for comp in config["pipeline"] if comp['name'] == 'DIETClassifier'), {})
        comp['epoch'] = 200
        comp = next((comp for comp in config["policies"] if 'RulePolicy' in comp['name']), {})
        comp['core_fallback_action_name'] = 'action_error'
        comp['core_fallback_threshold'] = 0.5
        processor.add_or_overwrite_config(config, bot, user)
        config = Configs.objects().get(bot=bot).to_mongo().to_dict()
        assert config['language'] == 'fr'
        assert len(config['pipeline']) == 9
        assert len(config['policies']) == 3
        diet_classifier = next((comp for comp in config["pipeline"] if comp['name'] == 'DIETClassifier'), {})
        assert diet_classifier['epoch'] == 200
        rule_policy = next((comp for comp in config["policies"] if 'RulePolicy' in comp['name']), {})
        assert rule_policy['core_fallback_action_name'] == 'action_error'
        assert rule_policy['core_fallback_threshold'] == 0.5
        assert Rules.objects(block_name__iexact=DEFAULT_NLU_FALLBACK_RULE, bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_please_rephrase', bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_default', bot=bot, status=True).get()

    def test_add_or_overwrite_config_no_action_and_threshold(self):
        bot = 'test_config'
        user = 'test_config'
        processor = MongoProcessor()
        config = Utility.read_yaml('./tests/testing_data/valid_yml/config.yml')
        comp = next((comp for comp in config["policies"] if 'RulePolicy' in comp['name']), {})
        del comp['core_fallback_action_name']
        del comp['core_fallback_threshold']
        processor.add_or_overwrite_config(config, bot, user)
        config = Configs.objects().get(bot=bot).to_mongo().to_dict()
        assert config['language'] == 'fr'
        assert len(config['pipeline']) == 9
        assert len(config['policies']) == 3
        rule_policy = next((comp for comp in config["policies"] if 'RulePolicy' in comp['name']), {})
        assert rule_policy['core_fallback_action_name'] == 'action_default_fallback'
        assert rule_policy['core_fallback_threshold'] == 0.3
        assert Rules.objects(block_name__iexact=DEFAULT_NLU_FALLBACK_RULE, bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_please_rephrase', bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_default', bot=bot, status=True).get()

    def test_add_or_overwrite_config_with_fallback_classifier(self):
        bot = 'test_config'
        user = 'test_config'
        processor = MongoProcessor()
        config = Utility.read_yaml('./tests/testing_data/valid_yml/config.yml')
        config["pipeline"].append({'name': 'FallbackClassifier', 'threshold': 0.7})
        processor.add_or_overwrite_config(config, bot, user)
        config = Configs.objects().get(bot=bot).to_mongo().to_dict()
        assert config['language'] == 'fr'
        assert len(config['pipeline']) == 9
        assert len(config['policies']) == 3
        diet_classifier = next((comp for comp in config["pipeline"] if comp['name'] == 'DIETClassifier'), {})
        assert diet_classifier['epochs'] == 5
        rule_policy = next((comp for comp in config["policies"] if 'RulePolicy' in comp['name']), {})
        assert rule_policy['core_fallback_action_name'] == 'action_small_talk'
        assert rule_policy['core_fallback_threshold'] == 0.75
        assert Rules.objects(block_name__iexact=DEFAULT_NLU_FALLBACK_RULE, bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_please_rephrase', bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_default', bot=bot, status=True).get()

    def test_add_or_overwrite_config_with_fallback_policy(self):
        bot = 'test_config'
        user = 'test_config'
        processor = MongoProcessor()
        config = Utility.read_yaml('./tests/testing_data/valid_yml/config.yml')
        config['policies'].append({'name': 'FallbackPolicy', 'nlu_threshold': 0.75, 'core_threshold': 0.3})
        processor.add_or_overwrite_config(config, bot, user)
        config = Configs.objects().get(bot=bot).to_mongo().to_dict()
        assert config['language'] == 'fr'
        assert len(config['pipeline']) == 9
        assert len(config['policies']) == 3
        diet_classifier = next((comp for comp in config["pipeline"] if comp['name'] == 'DIETClassifier'), {})
        assert diet_classifier['epochs'] == 5
        rule_policy = next((comp for comp in config["policies"] if 'RulePolicy' in comp['name']), {})
        assert rule_policy['core_fallback_action_name'] == 'action_small_talk'
        assert rule_policy['core_fallback_threshold'] == 0.75
        assert not next((comp for comp in config["policies"] if comp['name'] == 'FallbackPolicy'), None)
        assert Rules.objects(block_name__iexact=DEFAULT_NLU_FALLBACK_RULE, bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_please_rephrase', bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_default', bot=bot, status=True).get()

    def test_add_or_overwrite_gpt_classifier_config_with_bot_id(self):
        bot = 'test_config'
        user = 'test_config'
        processor = MongoProcessor()
        config = Utility.read_yaml('./template/config/openai-classifier.yml')
        processor.add_or_overwrite_config(config, bot, user)
        config = Configs.objects().get(bot=bot).to_mongo().to_dict()
        assert config['language'] == 'en'
        assert config['pipeline'] == [{'name': 'kairon.shared.nlu.classifier.openai.OpenAIClassifier', 'bot_id': bot}]
        assert config['policies'] == [{'name': 'MemoizationPolicy'}, {'epochs': 200, 'name': 'TEDPolicy'},
                                      {'core_fallback_action_name': 'action_default_fallback',
                                       'core_fallback_threshold': 0.3, 'enable_fallback_prediction': False,
                                       'max_history': 5,
                                       'name': 'RulePolicy'}]

    def test_add_or_overwrite_gpt_featurizer_config_with_bot_id(self):
        bot = 'test_config'
        user = 'test_config'
        processor = MongoProcessor()
        config = Utility.read_yaml('./template/config/openai-featurizer.yml')
        processor.add_or_overwrite_config(config, bot, user)
        config = Configs.objects().get(bot=bot).to_mongo().to_dict()
        assert config['language'] == 'en'
        assert config['pipeline'] == [{'name': 'WhitespaceTokenizer'}, {'name': 'CountVectorsFeaturizer',
                                                                        'min_ngram': 1, 'max_ngram': 2},
                                      {'name': 'kairon.shared.nlu.featurizer.openai.OpenAIFeaturizer', 'bot_id': bot},
                                      {'name': 'DIETClassifier', 'epochs': 50, 'constrain_similarities': True,
                                       'entity_recognition': False},
                                      {'name': 'FallbackClassifier', 'threshold': 0.8}]
        assert config['policies'] == [{'name': 'MemoizationPolicy'}, {'epochs': 200, 'name': 'TEDPolicy'},
                                      {'core_fallback_action_name': 'action_default_fallback',
                                       'core_fallback_threshold': 0.3, 'enable_fallback_prediction': False,
                                       'max_history': 5,
                                       'name': 'RulePolicy'}]

    @pytest.mark.asyncio
    async def test_upload_case_insensitivity(self):
        processor = MongoProcessor()
        await (
            processor.save_from_path(
                "./tests/testing_data/upper_case_data", bot="test_upload_case_insensitivity", user="testUser"
            )
        )
        training_data = processor.load_nlu("test_upload_case_insensitivity")
        assert isinstance(training_data, TrainingData)
        assert training_data.intents == {'deny', 'greet'}
        assert training_data.entity_synonyms == {'Bangalore': 'karnataka', 'bengaluru': 'karnataka',
                                                 'karnataka': 'karnataka', 'KA': 'karnataka'}
        assert Synonyms.objects(bot="test_upload_case_insensitivity").get(name="karnataka")
        assert training_data.regex_features == [{'name': 'application_name', 'pattern': '[azAz09\\s+]*'},
                                                {'name': 'email_id', 'pattern': '[^@]+@[^@]+\\.[^@]+'}]
        assert training_data.lookup_tables == [{'name': 'application_name', 'elements': ['Firefox', 'Chrome', 'Tor']},
                                               {'name': 'location', 'elements': ['Mumbai', 'Karnataka', 'Bangalore']}]
        lookups = list(Lookup.objects(bot="test_upload_case_insensitivity", status=True).values_list("name"))
        assert all(item in lookups for item in ['application_name', 'location'])
        story_graph = processor.load_stories("test_upload_case_insensitivity")
        assert story_graph.story_steps[0].block_name == 'greet'
        assert story_graph.story_steps[1].block_name == 'say goodbye'
        domain = processor.load_domain("test_upload_case_insensitivity")
        assert all(slot.name in ['user', 'location', 'email_id', 'application_name', 'bot', 'kairon_action_response',
                                 'order', 'payment', 'http_status_code', 'image', 'audio', 'video', 'document',
                                 'doc_url', 'longitude', 'latitude', 'flow_reply', 'quick_reply',
                                 'session_started_metadata', 'requested_slot', 'mail_id', 'subject', 'body', 'media_ids',
                                 'flow_docs', 'flow_images', 'flow_data', 'llm_call_id',
                                 'user_identifier', 'temp_token', 'store_page_name', 'redirect_url', 'callback_identifier',
                                 'is_followup', 'parent_log_id', 'date', 'cc'] for slot in domain.slots)
        assert not DeepDiff(list(domain.responses.keys()), ['utter_please_rephrase', 'utter_greet', 'utter_goodbye',
                                                            'utter_default'], ignore_order=True)
        assert not DeepDiff(domain.entities,
                            ['user', 'location', 'email_id', 'application_name', 'bot', 'kairon_action_response',
                             'order', 'payment', 'http_status_code', 'image', 'audio', 'video', 'document', 'doc_url',
                             'longitude', 'latitude', 'flow_reply', 'quick_reply',  'mail_id', 'subject', 'body',
                             'media_ids', 'flow_docs', 'flow_images', 'flow_data', 'llm_call_id',
                             'user_identifier', 'temp_token', 'store_page_name', 'redirect_url', 'callback_identifier',
                             'is_followup', 'parent_log_id', 'date', 'cc'], ignore_order=True)
        assert domain.forms == {'ask_user': {'required_slots': ['user', 'email_id']},
                                'ask_location': {'required_slots': ['location', 'application_name']}}
        assert domain.user_actions == ['ACTION_GET_GOOGLE_APPLICATION', 'ACTION_GET_MICROSOFT_APPLICATION',
                                       'utter_default', 'utter_goodbye', 'utter_greet', 'utter_please_rephrase']
        assert processor.fetch_actions('test_upload_case_insensitivity') == ['ACTION_GET_GOOGLE_APPLICATION',
                                                                             'ACTION_GET_MICROSOFT_APPLICATION']
        assert domain.intents == ['back', 'deny', 'greet', 'nlu_fallback', 'out_of_scope', 'restart', 'session_start']
        assert domain.responses == {
            'utter_please_rephrase': [{'text': "I'm sorry, I didn't quite understand that. Could you rephrase?"}],
            'utter_greet': [{'text': 'Hey! How are you?'}], 'utter_goodbye': [{'text': 'Bye'}],
            'utter_default': [{'text': 'Can you rephrase!'}]}
        rules = processor.fetch_rule_block_names("test_upload_case_insensitivity")
        assert rules == ['rule which will not wait for user message once it was applied',
                         'ask the user to rephrase whenever they send a message with low nlu confidence']
        actions = processor.load_http_action("test_upload_case_insensitivity")
        assert actions == {'http_action': [
            {'action_name': 'ACTION_GET_GOOGLE_APPLICATION', 'http_url': 'http://www.alphabet.com',
             'content_type': 'json',
             'response': {'value': 'json', 'dispatch': True, 'evaluation_type': 'expression', 'dispatch_type': 'text'},
             'request_method': 'GET', 'headers': [
                {'_cls': 'HttpActionRequestBody', 'key': 'testParam1', 'value': '', 'parameter_type': 'chat_log',
                 'encrypt': False},
                {'_cls': 'HttpActionRequestBody', 'key': 'testParam2', 'value': '', 'parameter_type': 'user_message',
                 'encrypt': False},
                {'_cls': 'HttpActionRequestBody', 'key': 'testParam3', 'value': '', 'parameter_type': 'value',
                 'encrypt': False},
                {'_cls': 'HttpActionRequestBody', 'key': 'testParam4', 'value': '', 'parameter_type': 'intent',
                 'encrypt': False},
                {'_cls': 'HttpActionRequestBody', 'key': 'testParam5', 'value': '', 'parameter_type': 'sender_id',
                 'encrypt': False},
                {'_cls': 'HttpActionRequestBody', 'key': 'testParam4', 'value': 'testValue1',
                 'parameter_type': 'slot', 'encrypt': False}],
             'params_list': [{'_cls': 'HttpActionRequestBody', 'key': 'testParam1', 'value': 'testValue1',
                              'parameter_type': 'value', 'encrypt': False},
                             {'_cls': 'HttpActionRequestBody', 'key': 'testParam2', 'value': 'testValue1',
                              'parameter_type': 'slot', 'encrypt': False}],
             'dynamic_params': {
                 "farmid": '120d37d6-6159-45f1-a3d0-edfead442971',
                 "fields": [
                     {
                         "fieldid": '58ce899a-b5ad-4a76-905b-e615672c0c66',
                         "duration_min": 2
                     }
                 ]
             }},
            {'action_name': 'ACTION_GET_MICROSOFT_APPLICATION',
             'response': {'value': 'json', 'dispatch': True, 'evaluation_type': 'expression', 'dispatch_type': 'text'},
             'http_url': 'http://www.alphabet.com', 'request_method': 'GET', 'content_type': 'json',
             'params_list': [{'_cls': 'HttpActionRequestBody', 'key': 'testParam1', 'value': 'testValue1',
                              'parameter_type': 'value', 'encrypt': False},
                             {'_cls': 'HttpActionRequestBody', 'key': 'testParam2', 'value': 'testValue1',
                              'parameter_type': 'slot', 'encrypt': False},
                             {'_cls': 'HttpActionRequestBody', 'key': 'testParam1', 'value': '',
                              'parameter_type': 'chat_log', 'encrypt': False},
                             {'_cls': 'HttpActionRequestBody', 'key': 'testParam2', 'value': '',
                              'parameter_type': 'user_message', 'encrypt': False},
                             {'_cls': 'HttpActionRequestBody', 'key': 'testParam3', 'value': '',
                              'parameter_type': 'value', 'encrypt': False},
                             {'_cls': 'HttpActionRequestBody', 'key': 'testParam4', 'value': '',
                              'parameter_type': 'intent', 'encrypt': False},
                             {'_cls': 'HttpActionRequestBody', 'key': 'testParam5', 'value': '',
                              'parameter_type': 'sender_id', 'encrypt': False},
                             {'_cls': 'HttpActionRequestBody', 'key': 'testParam4', 'value': 'testValue1',
                              'parameter_type': 'slot', 'encrypt': False}]}]}
        assert set(Utterances.objects(bot='test_upload_case_insensitivity').values_list('name')) == {'utter_goodbye',
                                                                                                     'utter_greet',
                                                                                                     'utter_default',
                                                                                                     'utter_please_rephrase'}

    @pytest.mark.asyncio
    async def test_load_from_path_yml_training_files(self):
        processor = MongoProcessor()
        await (
            processor.save_from_path(
                "./tests/testing_data/yml_training_files", bot="test_load_from_path_yml_training_files", user="testUser"
            )
        )
        training_data = processor.load_nlu("test_load_from_path_yml_training_files")
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 305
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = processor.load_stories("test_load_from_path_yml_training_files")
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 16
        assert story_graph.story_steps[14].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[14].events[2].entities[0].get('start')
        assert not story_graph.story_steps[14].events[2].entities[0].get('end')
        assert story_graph.story_steps[14].events[2].entities[0]['value'] == 'like'
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdresponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[15].events[2].entities[0].get('start')
        assert not story_graph.story_steps[15].events[2].entities[0].get('end')
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdresponse'
        domain = processor.load_domain("test_load_from_path_yml_training_files")
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 41
        assert len([slot for slot in domain.slots if slot.influence_conversation is True]) == 25
        assert len([slot for slot in domain.slots if slot.influence_conversation is False]) == 16
        assert domain.intent_properties.__len__() == 32
        assert len([intent for intent in domain.intent_properties.keys() if
                    domain.intent_properties.get(intent)['used_entities']]) == 27
        assert len([intent for intent in domain.intent_properties.keys() if
                    not domain.intent_properties.get(intent)['used_entities']]) == 5
        assert domain.responses.keys().__len__() == 29
        assert domain.entities.__len__() == 41
        assert domain.forms.__len__() == 2
        assert domain.forms.__len__() == 2
        assert domain.forms['ticket_attributes_form'] == {
            'required_slots': ['date_time',
                               'priority']}
        assert domain.forms['ticket_file_form'] == {
            'required_slots': ['file']}
        assert isinstance(domain.forms, dict)
        assert domain.user_actions.__len__() == 48

        assert processor.list_actions('test_load_from_path_yml_training_files')["http_action"].__len__() == 17
        assert processor.list_actions('test_load_from_path_yml_training_files')["utterances"].__len__() == 29
        assert processor.list_actions('test_load_from_path_yml_training_files')["form_validation_action"].__len__() == 1
        assert domain.intents.__len__() == 32
        assert not Utility.check_empty_string(
            domain.responses["utter_cheer_up"][0]["image"]
        )
        assert domain.responses["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.responses["utter_offer_help"][0]["custom"]
        rules = processor.fetch_rule_block_names("test_load_from_path_yml_training_files")
        assert len(rules) == 4
        actions = processor.load_http_action("test_load_from_path_yml_training_files")
        actions_google = processor.load_google_search_action("test_load_from_path_yml_training_files")
        assert isinstance(actions, dict) is True
        assert len(actions['http_action']) == 17
        assert len(actions_google['google_search_action']) == 1
        assert Utterances.objects(bot='test_load_from_path_yml_training_files').count() == 29

    @pytest.mark.asyncio
    async def test_load_from_path_error(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            await (
                processor.save_from_path(
                    "./tests/testing_data/error", bot="tests", user="testUser"
                )
            )

    @pytest.mark.asyncio
    async def test_load_from_path_all_scenario(self):
        processor = MongoProcessor()
        await (
            processor.save_from_path("./tests/testing_data/all", bot="all", user="testUser")
        )
        training_data = processor.load_nlu("all")
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 292
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = processor.load_stories("all")
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 16
        assert story_graph.story_steps[14].events[2].intent['name'] == 'user_feedback'
        assert story_graph.story_steps[14].events[2].entities[0]['value'] == 'like'
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdresponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdresponse'
        domain = processor.load_domain("all")
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 40
        assert all(slot.mappings[0]['type'] == 'from_entity' and slot.mappings[0]['entity'] == slot.name for slot in
                   domain.slots if slot.name not in ['requested_slot', 'session_started_metadata'])
        assert domain.responses.keys().__len__() == 27
        assert domain.entities.__len__() == 40
        assert domain.forms.__len__() == 2
        assert domain.forms['ticket_attributes_form'] == {'required_slots': {}}
        assert isinstance(domain.forms, dict)
        assert domain.user_actions.__len__() == 27
        assert domain.intents.__len__() == 29
        assert not Utility.check_empty_string(
            domain.responses["utter_cheer_up"][0]["image"]
        )
        assert domain.responses["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.responses["utter_offer_help"][0]["custom"]
        assert Utterances.objects(bot='all').count() == 27

    @pytest.mark.asyncio
    async def test_load_from_path_all_scenario_append(self):
        processor = MongoProcessor()
        await (
            processor.save_from_path("./tests/testing_data/all",
                                     "all",
                                     overwrite=False,
                                     user="testUser")
        )
        training_data = processor.load_nlu("all")
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 292
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = processor.load_stories("all")
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 16
        assert story_graph.story_steps[14].events[2].intent['name'] == 'user_feedback'
        assert story_graph.story_steps[14].events[2].entities[0]['value'] == 'like'
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdresponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdresponse'
        domain = processor.load_domain("all")
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 40
        assert domain.responses.keys().__len__() == 27
        assert domain.entities.__len__() == 40
        assert domain.forms.__len__() == 2
        assert isinstance(domain.forms, dict)
        assert domain.user_actions.__len__() == 27
        assert domain.intents.__len__() == 29
        assert not Utility.check_empty_string(
            domain.responses["utter_cheer_up"][0]["image"]
        )
        assert domain.responses["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.responses["utter_offer_help"][0]["custom"]
        assert Utterances.objects(bot='all').count() == 27

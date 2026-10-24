from tests.unit_test.data_processor.data_processor_support import *  # noqa: F403
from tests.unit_test.data_processor.data_processor_support import (
    MongoProcessorTestBase,
    fast_rasa_training,
)

class TestMongoProcessor(MongoProcessorTestBase):
    def test_delete_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        Actions(name='action_custom', bot=bot, user=user).save()
        processor.delete_action('action_custom', bot, user)

    def test_delete_action_already_deleted(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()
        with pytest.raises(AppException, match=f'Action with name "action_custom" not found'):
            processor.delete_action('action_custom', bot, user)

        LLMSecret.objects.delete()

    def test_delete_action_with_attached_http_action(self):
        processor = MongoProcessor()
        bot = 'tester_bot'
        http_url = 'http://www.google.com'
        action = 'tester_action'
        user = 'tester_user'
        response = "json"
        request_method = 'GET'
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            user=user
        )
        llm_secret.save()
        http_params_list: List[HttpActionParameters] = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value")]
        header: List[HttpActionParameters] = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=ActionResponseEvaluation(value=response),
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list,
            headers=header
        )
        prompt_action_config = PromptActionConfigRequest(
            name='test_delete_action_with_attached_http_action',
            llm_prompts=[{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                          'source': 'static', 'is_enabled': True},
                         {'name': 'Action Prompt',
                          'data': 'tester_action',
                          'instructions': 'Answer according to the context', 'type': 'user',
                          'source': 'action',
                          'is_enabled': True}],
            llm_type=DEFAULT_LLM,
            hyperparameters=Utility.get_default_llm_hyperparameters(),
            bot=bot
        )
        processor.add_http_action_config(http_action_config.model_dump(), user, bot)
        processor.add_prompt_action(prompt_action_config.model_dump(), bot, user)
        with pytest.raises(AppException, match=f'Action with name tester_action is attached with PromptAction!'):
            processor.delete_action('tester_action', bot, user)

        LLMSecret.objects.delete()

    def test_delete_action_removes_typed_config_name_field(self):
        processor = MongoProcessor()
        bot = 'test_delete_typed'
        user = 'test'
        SlotSetAction(name='action_slot_to_delete', set_slots=[], bot=bot, user=user).save()
        Actions(name='action_slot_to_delete', type=ActionType.slot_set_action.value, bot=bot, user=user).save()
        assert SlotSetAction.objects(name='action_slot_to_delete', bot=bot, status=True).count() == 1
        processor.delete_action('action_slot_to_delete', bot, user)
        assert Actions.objects(name='action_slot_to_delete', bot=bot).count() == 0
        assert SlotSetAction.objects(name='action_slot_to_delete', bot=bot).count() == 0

    def test_delete_action_removes_typed_config_action_name_field(self):
        processor = MongoProcessor()
        bot = 'test_delete_typed'
        user = 'test'
        http_action_config = HttpActionConfigRequest(
            action_name='action_http_to_delete',
            response=ActionResponseEvaluation(value='json'),
            http_url='http://www.example.com',
            request_method='GET',
        )
        processor.add_http_action_config(http_action_config.model_dump(), user, bot)
        assert HttpActionConfig.objects(action_name='action_http_to_delete', bot=bot, status=True).count() == 1
        processor.delete_action('action_http_to_delete', bot, user)
        assert Actions.objects(name='action_http_to_delete', bot=bot).count() == 0
        assert HttpActionConfig.objects(action_name='action_http_to_delete', bot=bot).count() == 0

    @responses.activate
    def test_push_notifications_enabled_create_type_event(self):
        bot = 'test_notifications'
        user = 'test'
        url = f"http://localhost/events/{bot}"
        with patch.dict(Utility.environment['notifications'], {"enable": True, "server_endpoint": url}):
            processor = MongoProcessor()
            responses.add(
                'POST',
                url,
                json={'message': 'Event added'}
            )
            processor.add_intent('greet', bot, user, False)
            request_body = responses.calls[0].request
            request_body = request_body.body.decode('utf8')
            request_body = json.loads(request_body)
            assert responses.calls[0].request.headers['Authorization']
            assert request_body['event_type'] == "create"
            assert request_body['event']['entity_type'] == "Intents"
            assert request_body['event']['data']['name'] == 'greet'
            assert request_body['event']['data']['bot'] == bot
            assert request_body['event']['data']['user'] == user
            assert not Utility.check_empty_string(request_body['event']['data']['timestamp'])
            assert request_body['event']['data']['status']
            assert not request_body['event']['data']['is_integration']
            assert not request_body['event']['data']['use_entities']

    @responses.activate
    def test_push_notifications_enabled_update_type_event(self):
        bot = "tests"
        user = 'testUser'
        url = "http://localhost/events"
        with patch.dict(Utility.environment['notifications'], {"enable": True, "server_endpoint": url}):
            processor = MongoProcessor()
            responses.add(
                'POST',
                f'{url}/tests',
                json={'message': 'Event updated'}
            )
            examples = list(processor.get_training_examples("greet", bot))
            processor.edit_training_example(examples[0]["_id"], example="[Kanpur](location) India", intent="greet",
                                            bot=bot, user=user)
            request_body = responses.calls[0].request
            request_body = request_body.body.decode('utf8')
            request_body = json.loads(request_body)
            assert responses.calls[0].request.headers['Authorization']
            assert request_body['event_type'] == "update"
            assert request_body['event']['entity_type'] == "TrainingExamples"
            assert request_body['event']['data']['intent'] == 'greet'
            assert not Utility.check_empty_string(request_body['event']['data']['text'])
            assert request_body['event']['data']['bot'] == bot
            assert request_body['event']['data']['user'] == user
            assert not Utility.check_empty_string(request_body['event']['data']['timestamp'])
            assert request_body['event']['data']['status']

    @responses.activate
    def test_push_notifications_enabled_delete_type_event(self):
        bot = "test"
        user = 'test'
        url = "http://localhost/events"
        with patch.dict(Utility.environment['notifications'], {"enable": True, "server_endpoint": url}):
            processor = MongoProcessor()

            responses.add(
                'POST',
                f'{url}/test',
                json={'message': 'Event deleted'}
            )
            processor.delete_complex_story(pytest.slot_set_action_story_id, 'STORY', bot, user)

    def test_push_notifications_enabled_update_type_event_connection_error(self):
        bot = "test"
        user = 'test'
        utterance = 'utter_notifications'
        processor = MongoProcessor()
        processor.add_utterance_name(utterance, bot, user, raise_error_if_exists=True)
        assert Utterances.objects(bot=bot, status=True, name__iexact=utterance).get()

    def test_push_notifications_enabled_delete_type_connection_error(self):
        bot = "test"
        user = 'test'
        story_name = 'test_push_notifications'
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_thanks", "type": "ACTION"},
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'STORY', 'template_type': 'Q&A'}
        story_id = processor.add_complex_story(story_dict, bot, user)
        processor.delete_complex_story(story_id, 'STORY', bot, user)
        with pytest.raises(DoesNotExist):
            Stories.objects(block_name=story_name, bot=bot, status=True).get()

    @responses.activate
    def test_add_jira_action(self):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action', 'url': url, 'user_name': 'test@digite.com',
            'api_token': {"value": 'ASDFGHJKL'}, 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        responses.add(
            'GET',
            f'{url}/rest/api/2/serverInfo',
            json={'baseUrl': 'https://udit-pandey.atlassian.net', 'version': '1001.0.0-SNAPSHOT',
                  'versionNumbers': [1001, 0, 0], 'deploymentType': 'Cloud', 'buildNumber': 100191,
                  'buildDate': '2022-02-11T05:35:40.000+0530', 'serverTime': '2022-02-15T10:54:09.906+0530',
                  'scmInfo': '831671b3b59f40b5108ef3f9491df89a1317ecaa', 'serverTitle': 'Jira',
                  'defaultLocale': {'locale': 'en_US'}}
        )
        responses.add(
            'GET',
            f'{url}/rest/api/2/project/HEL',
            json={'expand': 'description,lead,issueTypes,url,projectKeys,permissions,insight',
                  'self': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000', 'id': '10000', 'key': 'HEL',
                  'description': '', 'lead': {
                    'self': 'https://udit-pandey.atlassian.net/rest/api/2/user?accountId=6205e1585d18ad00729aa75f',
                    'accountId': '6205e1585d18ad00729aa75f', 'avatarUrls': {
                        '48x48': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '24x24': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '16x16': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '32x32': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png'},
                    'displayName': 'Udit Pandey', 'active': True}, 'components': [], 'issueTypes': [
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10001', 'id': '10001',
                     'description': 'A small, distinct piece of work.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10318?size=medium',
                     'name': 'Task', 'subtask': False, 'avatarId': 10318, 'hierarchyLevel': 0},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10002', 'id': '10002',
                     'description': 'A collection of related bugs, stories, and tasks.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10307?size=medium',
                     'name': 'Epic', 'subtask': False, 'avatarId': 10307, 'hierarchyLevel': 1},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10003', 'id': '10003',
                     'description': 'Subtasks track small pieces of work that are part of a larger task.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10316?size=medium',
                     'name': 'Bug', 'subtask': True, 'avatarId': 10316, 'hierarchyLevel': -1}],
                  'assigneeType': 'UNASSIGNED', 'versions': [], 'name': 'helicopter', 'roles': {
                    'atlassian-addons-project-access': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10007',
                    'Administrator': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10004',
                    'Viewer': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10006',
                    'Member': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10005'}, 'avatarUrls': {
                    '48x48': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408',
                    '24x24': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=small',
                    '16x16': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=xsmall',
                    '32x32': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=medium'},
                  'projectTypeKey': 'software', 'simplified': True, 'style': 'next-gen', 'isPrivate': False,
                  'properties': {}, 'entityId': '8a851ebf-72eb-461d-be68-4c2c28805440',
                  'uuid': '8a851ebf-72eb-461d-be68-4c2c28805440'}
        )
        processor = MongoProcessor()
        assert processor.add_jira_action(action, bot, user)

    def test_add_jira_action_already_exists(self):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action', 'url': url, 'user_name': 'test@digite.com',
            'api_token': {'value': 'ASDFGHJKL'}, 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        processor = MongoProcessor()
        with pytest.raises(AppException, match="Action exists!"):
            processor.add_jira_action(action, bot, user)

    def test_add_jira_action_existing_name(self):
        processor = MongoProcessor()
        bot = 'test'
        http_url = 'http://www.google.com'
        action = 'test_action'
        # file deepcode ignore HardcodedNonCryptoSecret: Random string for testing
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        http_params_list: List[HttpActionParameters] = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value")]
        header: List[HttpActionParameters] = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=ActionResponseEvaluation(value=response),
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list,
            headers=header
        )
        processor.add_http_action_config(http_action_config.model_dump(), user, bot)

        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'test_action', 'url': url, 'user_name': 'test@digite.com',
            'api_token': 'ASDFGHJKL', 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
            'response': {"value": 'We have logged a ticket'}
        }
        processor = MongoProcessor()
        with pytest.raises(AppException, match="Action exists!"):
            processor.add_jira_action(action, bot, user)

    @responses.activate
    def test_add_jira_action_different_bot(self):
        bot = 'test_2'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action', 'url': url, 'user_name': 'test@digite.com',
            'api_token': {'value': 'ASDFGHJKL'}, 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        responses.add(
            'GET',
            f'{url}/rest/api/2/serverInfo',
            json={'baseUrl': 'https://udit-pandey.atlassian.net', 'version': '1001.0.0-SNAPSHOT',
                  'versionNumbers': [1001, 0, 0], 'deploymentType': 'Cloud', 'buildNumber': 100191,
                  'buildDate': '2022-02-11T05:35:40.000+0530', 'serverTime': '2022-02-15T10:54:09.906+0530',
                  'scmInfo': '831671b3b59f40b5108ef3f9491df89a1317ecaa', 'serverTitle': 'Jira',
                  'defaultLocale': {'locale': 'en_US'}}
        )
        responses.add(
            'GET',
            f'{url}/rest/api/2/project/HEL',
            json={'expand': 'description,lead,issueTypes,url,projectKeys,permissions,insight',
                  'self': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000', 'id': '10000', 'key': 'HEL',
                  'description': '', 'lead': {
                    'self': 'https://udit-pandey.atlassian.net/rest/api/2/user?accountId=6205e1585d18ad00729aa75f',
                    'accountId': '6205e1585d18ad00729aa75f', 'avatarUrls': {
                        '48x48': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '24x24': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '16x16': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '32x32': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png'},
                    'displayName': 'Udit Pandey', 'active': True}, 'components': [], 'issueTypes': [
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10001', 'id': '10001',
                     'description': 'A small, distinct piece of work.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10318?size=medium',
                     'name': 'Task', 'subtask': False, 'avatarId': 10318, 'hierarchyLevel': 0},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10002', 'id': '10002',
                     'description': 'A collection of related bugs, stories, and tasks.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10307?size=medium',
                     'name': 'Epic', 'subtask': False, 'avatarId': 10307, 'hierarchyLevel': 1},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10003', 'id': '10003',
                     'description': 'Subtasks track small pieces of work that are part of a larger task.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10316?size=medium',
                     'name': 'Bug', 'subtask': True, 'avatarId': 10316, 'hierarchyLevel': -1}],
                  'assigneeType': 'UNASSIGNED', 'versions': [], 'name': 'helicopter', 'roles': {
                    'atlassian-addons-project-access': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10007',
                    'Administrator': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10004',
                    'Viewer': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10006',
                    'Member': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10005'}, 'avatarUrls': {
                    '48x48': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408',
                    '24x24': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=small',
                    '16x16': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=xsmall',
                    '32x32': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=medium'},
                  'projectTypeKey': 'software', 'simplified': True, 'style': 'next-gen', 'isPrivate': False,
                  'properties': {}, 'entityId': '8a851ebf-72eb-461d-be68-4c2c28805440',
                  'uuid': '8a851ebf-72eb-461d-be68-4c2c28805440'}
        )
        processor = MongoProcessor()
        assert processor.add_jira_action(action, bot, user)

    def test_add_jira_action_invalid_url(self, monkeypatch):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action_new', 'url': url, 'user_name': 'test@digite.com',
            'api_token': {'value': 'ASDFGHJKL'}, 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
            'response': 'We have logged a ticket'
        }

        def _mock_error(*args, **kwargs):
            raise JIRAError(status_code=404, url=url)

        monkeypatch.setattr(JIRA, '_create_http_basic_session', _mock_error)

        processor = MongoProcessor()
        with pytest.raises(ValidationError, match='Could not connect to url: *'):
            processor.add_jira_action(action, bot, user)

    def test_add_jira_action_invalid_url_runtime_error(self, monkeypatch):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action_new', 'url': url, 'user_name': 'test@digite.com',
            'api_token': {'value': 'ASDFGHJKL'}, 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
            'response': 'We have logged a ticket'
        }

        def _mock_error(*args, **kwargs):
            raise RuntimeError()

        monkeypatch.setattr(JIRA, '_create_http_basic_session', _mock_error)

        processor = MongoProcessor()
        with pytest.raises(ValidationError, match='Could not connect to url: *'):
            processor.add_jira_action(action, bot, user)

    @responses.activate
    def test_add_jira_action_invalid_project_key(self):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action_new', 'url': url, 'user_name': 'test@digite.com',
            'api_token': {'value': 'ASDFGHJKL'}, 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        responses.add(
            'GET',
            f'{url}/rest/api/2/serverInfo',
            json={'baseUrl': 'https://udit-pandey.atlassian.net', 'version': '1001.0.0-SNAPSHOT',
                  'versionNumbers': [1001, 0, 0], 'deploymentType': 'Cloud', 'buildNumber': 100191,
                  'buildDate': '2022-02-11T05:35:40.000+0530', 'serverTime': '2022-02-15T10:54:09.906+0530',
                  'scmInfo': '831671b3b59f40b5108ef3f9491df89a1317ecaa', 'serverTitle': 'Jira',
                  'defaultLocale': {'locale': 'en_US'}}
        )
        responses.add(
            'GET',
            f'{url}/rest/api/2/project/HEL',
            json={'errorMessages': ["No project could be found with key 'HAL'."], 'errors': {}},
            status=404
        )
        processor = MongoProcessor()
        with pytest.raises(ValidationError):
            processor.add_jira_action(action, bot, user)

    @responses.activate
    def test_add_jira_action_invalid_issue_type(self):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        issue_type = 'ProdIssue'
        action = {
            'name': 'jira_action_new', 'url': url, 'user_name': 'test@digite.com',
            'api_token': {'value': 'ASDFGHJKL'}, 'project_key': 'HEL', 'issue_type': issue_type, 'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        responses.add(
            'GET',
            f'{url}/rest/api/2/serverInfo',
            json={'baseUrl': 'https://udit-pandey.atlassian.net', 'version': '1001.0.0-SNAPSHOT',
                  'versionNumbers': [1001, 0, 0], 'deploymentType': 'Cloud', 'buildNumber': 100191,
                  'buildDate': '2022-02-11T05:35:40.000+0530', 'serverTime': '2022-02-15T10:54:09.906+0530',
                  'scmInfo': '831671b3b59f40b5108ef3f9491df89a1317ecaa', 'serverTitle': 'Jira',
                  'defaultLocale': {'locale': 'en_US'}}
        )
        responses.add(
            'GET',
            f'{url}/rest/api/2/project/HEL',
            json={'expand': 'description,lead,issueTypes,url,projectKeys,permissions,insight',
                  'self': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000', 'id': '10000', 'key': 'HEL',
                  'description': '', 'lead': {
                    'self': 'https://udit-pandey.atlassian.net/rest/api/2/user?accountId=6205e1585d18ad00729aa75f',
                    'accountId': '6205e1585d18ad00729aa75f', 'avatarUrls': {
                        '48x48': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '24x24': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '16x16': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '32x32': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png'},
                    'displayName': 'Udit Pandey', 'active': True}, 'components': [], 'issueTypes': [
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10001', 'id': '10001',
                     'description': 'A small, distinct piece of work.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10318?size=medium',
                     'name': 'Task', 'subtask': False, 'avatarId': 10318, 'hierarchyLevel': 0},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10002', 'id': '10002',
                     'description': 'A collection of related bugs, stories, and tasks.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10307?size=medium',
                     'name': 'Epic', 'subtask': False, 'avatarId': 10307, 'hierarchyLevel': 1},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10003', 'id': '10003',
                     'description': 'Subtasks track small pieces of work that are part of a larger task.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10316?size=medium',
                     'name': 'Bug', 'subtask': True, 'avatarId': 10316, 'hierarchyLevel': -1}],
                  'assigneeType': 'UNASSIGNED', 'versions': [], 'name': 'helicopter', 'roles': {
                    'atlassian-addons-project-access': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10007',
                    'Administrator': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10004',
                    'Viewer': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10006',
                    'Member': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10005'}, 'avatarUrls': {
                    '48x48': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408',
                    '24x24': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=small',
                    '16x16': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=xsmall',
                    '32x32': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=medium'},
                  'projectTypeKey': 'software', 'simplified': True, 'style': 'next-gen', 'isPrivate': False,
                  'properties': {}, 'entityId': '8a851ebf-72eb-461d-be68-4c2c28805440',
                  'uuid': '8a851ebf-72eb-461d-be68-4c2c28805440'}
        )
        processor = MongoProcessor()
        with pytest.raises(ValidationError, match=f"No issue type '{issue_type}' exists"):
            processor.add_jira_action(action, bot, user)

    @responses.activate
    def test_add_jira_action_parent_key_not_given_for_subtask(self):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action_new', 'url': url, 'user_name': 'test@digite.com',
            'api_token': {'value': 'ASDFGHJKL'}, 'project_key': 'HEL', 'issue_type': 'Subtask', 'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        responses.add(
            'GET',
            f'{url}/rest/api/2/serverInfo',
            json={'baseUrl': 'https://udit-pandey.atlassian.net', 'version': '1001.0.0-SNAPSHOT',
                  'versionNumbers': [1001, 0, 0], 'deploymentType': 'Cloud', 'buildNumber': 100191,
                  'buildDate': '2022-02-11T05:35:40.000+0530', 'serverTime': '2022-02-15T10:54:09.906+0530',
                  'scmInfo': '831671b3b59f40b5108ef3f9491df89a1317ecaa', 'serverTitle': 'Jira',
                  'defaultLocale': {'locale': 'en_US'}}
        )
        responses.add(
            'GET',
            f'{url}/rest/api/2/project/HEL',
            json={'expand': 'description,lead,issueTypes,url,projectKeys,permissions,insight',
                  'self': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000', 'id': '10000', 'key': 'HEL',
                  'description': '', 'lead': {
                    'self': 'https://udit-pandey.atlassian.net/rest/api/2/user?accountId=6205e1585d18ad00729aa75f',
                    'accountId': '6205e1585d18ad00729aa75f', 'avatarUrls': {
                        '48x48': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '24x24': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '16x16': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '32x32': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png'},
                    'displayName': 'Udit Pandey', 'active': True}, 'components': [], 'issueTypes': [
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10001', 'id': '10001',
                     'description': 'A small, distinct piece of work.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10318?size=medium',
                     'name': 'Task', 'subtask': False, 'avatarId': 10318, 'hierarchyLevel': 0},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10002', 'id': '10002',
                     'description': 'A collection of related bugs, stories, and tasks.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10307?size=medium',
                     'name': 'Subtask', 'subtask': True, 'avatarId': 10307, 'hierarchyLevel': 1},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10003', 'id': '10003',
                     'description': 'Subtasks track small pieces of work that are part of a larger task.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10316?size=medium',
                     'name': 'Bug', 'subtask': True, 'avatarId': 10316, 'hierarchyLevel': -1}],
                  'assigneeType': 'UNASSIGNED', 'versions': [], 'name': 'helicopter', 'roles': {
                    'atlassian-addons-project-access': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10007',
                    'Administrator': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10004',
                    'Viewer': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10006',
                    'Member': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10005'}, 'avatarUrls': {
                    '48x48': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408',
                    '24x24': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=small',
                    '16x16': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=xsmall',
                    '32x32': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=medium'},
                  'projectTypeKey': 'software', 'simplified': True, 'style': 'next-gen', 'isPrivate': False,
                  'properties': {}, 'entityId': '8a851ebf-72eb-461d-be68-4c2c28805440',
                  'uuid': '8a851ebf-72eb-461d-be68-4c2c28805440'}
        )
        processor = MongoProcessor()
        with pytest.raises(ValidationError, match="parent key is required for issues of type 'Subtask'"):
            processor.add_jira_action(action, bot, user)

    def test_list_jira_actions(self):
        bot = 'test'
        processor = MongoProcessor()
        jira_actions = list(processor.list_jira_actions(bot))
        jira_actions[0].pop("_id")
        assert jira_actions == [
            {'name': 'jira_action', 'url': 'https://test-digite.atlassian.net', 'user_name': 'test@digite.com',
             'api_token': {'_cls': 'CustomActionRequestParameters', 'key': 'api_token', 'encrypt': False,
                           'value': 'ASDFGHJKL', 'parameter_type': 'value'}, 'project_key': 'HEL', 'issue_type': 'Bug',
             'summary': 'new user',
             'response': 'We have logged a ticket'}]

        jira_actions = list(processor.list_jira_actions(bot, False))
        assert jira_actions == [
            {'name': 'jira_action', 'url': 'https://test-digite.atlassian.net', 'user_name': 'test@digite.com',
             'api_token': {'_cls': 'CustomActionRequestParameters', 'key': 'api_token', 'encrypt': False,
                           'value': 'ASDFGHJKL', 'parameter_type': 'value'},
             'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
             'response': 'We have logged a ticket'}]

    @responses.activate
    def test_edit_jira_action(self):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action', 'url': url, 'user_name': 'test@digite.com',
            'api_token': {'value': 'ASDFGHJKL'}, 'project_key': 'HEL', 'issue_type': 'Subtask', 'parent_key': 'HEL-4',
            'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        responses.add(
            'GET',
            f'{url}/rest/api/2/serverInfo',
            json={'baseUrl': 'https://udit-pandey.atlassian.net', 'version': '1001.0.0-SNAPSHOT',
                  'versionNumbers': [1001, 0, 0], 'deploymentType': 'Cloud', 'buildNumber': 100191,
                  'buildDate': '2022-02-11T05:35:40.000+0530', 'serverTime': '2022-02-15T10:54:09.906+0530',
                  'scmInfo': '831671b3b59f40b5108ef3f9491df89a1317ecaa', 'serverTitle': 'Jira',
                  'defaultLocale': {'locale': 'en_US'}}
        )
        responses.add(
            'GET',
            f'{url}/rest/api/2/project/HEL',
            json={'expand': 'description,lead,issueTypes,url,projectKeys,permissions,insight',
                  'self': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000', 'id': '10000', 'key': 'HEL',
                  'description': '', 'lead': {
                    'self': 'https://udit-pandey.atlassian.net/rest/api/2/user?accountId=6205e1585d18ad00729aa75f',
                    'accountId': '6205e1585d18ad00729aa75f', 'avatarUrls': {
                        '48x48': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '24x24': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '16x16': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '32x32': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png'},
                    'displayName': 'Udit Pandey', 'active': True}, 'components': [], 'issueTypes': [
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10001', 'id': '10001',
                     'description': 'A small, distinct piece of work.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10318?size=medium',
                     'name': 'Task', 'subtask': False, 'avatarId': 10318, 'hierarchyLevel': 0},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10002', 'id': '10002',
                     'description': 'A collection of related bugs, stories, and tasks.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10307?size=medium',
                     'name': 'Subtask', 'subtask': True, 'avatarId': 10307, 'hierarchyLevel': 1},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10003', 'id': '10003',
                     'description': 'Subtasks track small pieces of work that are part of a larger task.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10316?size=medium',
                     'name': 'Bug', 'subtask': True, 'avatarId': 10316, 'hierarchyLevel': -1}],
                  'assigneeType': 'UNASSIGNED', 'versions': [], 'name': 'helicopter', 'roles': {
                    'atlassian-addons-project-access': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10007',
                    'Administrator': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10004',
                    'Viewer': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10006',
                    'Member': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10005'}, 'avatarUrls': {
                    '48x48': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408',
                    '24x24': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=small',
                    '16x16': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=xsmall',
                    '32x32': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=medium'},
                  'projectTypeKey': 'software', 'simplified': True, 'style': 'next-gen', 'isPrivate': False,
                  'properties': {}, 'entityId': '8a851ebf-72eb-461d-be68-4c2c28805440',
                  'uuid': '8a851ebf-72eb-461d-be68-4c2c28805440'}
        )
        processor = MongoProcessor()
        assert not processor.edit_jira_action(action, bot, user)

    def test_edit_jira_action_not_exists(self):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action_not_exists', 'url': url, 'user_name': 'test@digite.com',
            'api_token': 'ASDFGHJKL', 'project_key': 'HEL', 'issue_type': 'Subtask', 'parent_key': 'HEL-4',
            'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        processor = MongoProcessor()
        with pytest.raises(AppException, match=f'Action with name "{action.get("name")}" not found'):
            processor.edit_jira_action(action, bot, user)

    def test_list_jira_actions_after_update(self):
        bot = 'test'
        processor = MongoProcessor()
        jira_actions = list(processor.list_jira_actions(bot))
        jira_actions[0].pop("_id")
        assert jira_actions == [
            {'name': 'jira_action', 'url': 'https://test-digite.atlassian.net', 'user_name': 'test@digite.com',
             'api_token': {'_cls': 'CustomActionRequestParameters', 'key': 'api_token', 'encrypt': False,
                           'value': 'ASDFGHJKL', 'parameter_type': 'value'}, 'project_key': 'HEL',
             'issue_type': 'Subtask', 'parent_key': 'HEL-4',
             'summary': 'new user', 'response': 'We have logged a ticket'}
        ]

        jira_actions = list(processor.list_jira_actions(bot, False))
        assert jira_actions == [
            {'name': 'jira_action', 'url': 'https://test-digite.atlassian.net', 'user_name': 'test@digite.com',
             'api_token': {'_cls': 'CustomActionRequestParameters', 'key': 'api_token', 'encrypt': False,
                           'value': 'ASDFGHJKL', 'parameter_type': 'value'}, 'project_key': 'HEL',
             'issue_type': 'Subtask', 'parent_key': 'HEL-4',
             'summary': 'new user', 'response': 'We have logged a ticket'}
        ]

    def test_add_jira_action_with_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "jira_action", "type": "JIRA_ACTION"},
        ]
        story_dict = {'name': "story with jira action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with jira action", bot=bot, events__name='jira_action',
                                status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'story with jira action']
        assert story_with_form[0]['steps'] == [
            {'name': 'greet', 'type': 'INTENT'},
            {'name': 'jira_action', 'type': 'JIRA_ACTION'},
        ]
        processor.delete_complex_story(story_id, 'STORY', bot, user)

    def test_add_schedule_action_with_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'

        expected_data = {
            "name": "schedule_mp2",
            "schedule_time": {"value": "2024-08-06T09:00:00.000+0530", "parameter_type": "value"},
            "timezone": None,
            "schedule_action": "test_pyscript",
            "response_text": "action scheduled",
            "params_list": [],
            "dispatch_bot_response": True
        }

        processor.add_schedule_action(expected_data, bot, user)


        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "schedule_mp2", "type": "SCHEDULE_ACTION"},
        ]
        story_dict = {'name': "story with schedule action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with schedule action", bot=bot, events__name='schedule_mp2',
                                status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'story with schedule action']
        assert story_with_form[0]['steps'] == [
            {'name': 'greet', 'type': 'INTENT'},
            {'name': 'schedule_mp2', 'type': 'SCHEDULE_ACTION'},
        ]
        processor.delete_complex_story(story_id, 'STORY', bot, user)

    def test_delete_jira_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        processor.delete_action('jira_action', bot, user)
        with pytest.raises(DoesNotExist):
            Actions.objects(name='jira_action', bot=bot).get()
        with pytest.raises(DoesNotExist):
            JiraAction.objects(name='jira_action', bot=bot).get()

    def test_list_zendesk_actions_empty(self):
        bot = 'test'
        processor = MongoProcessor()
        assert list(processor.list_zendesk_actions(bot)) == []

    def test_add_zendesk_action(self):
        bot = 'test'
        user = 'test'
        action = {'name': 'zendesk_action', 'subdomain': 'digite751', 'api_token': {'value': '123456789'},
                  'subject': 'new ticket', 'user_name': 'udit.pandey@digite.com', 'response': 'ticket filed'}
        processor = MongoProcessor()
        with patch('zenpy.Zenpy'):
            assert processor.add_zendesk_action(action, bot, user)

    def test_add_zendesk_action_with_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "zendesk_action", "type": "ZENDESK_ACTION"},
        ]
        story_dict = {'name': "story with zendesk action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with zendesk action", bot=bot,
                                events__name='zendesk_action', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'story with zendesk action']
        assert story_with_form[0]['steps'] == [
            {"name": "greet", "type": "INTENT"},
            {"name": "zendesk_action", "type": "ZENDESK_ACTION"},
        ]
        processor.delete_complex_story(story_id, 'STORY', bot, user)

    def test_add_zendesk_action_invalid_subdomain(self):
        bot = 'test'
        user = 'test'
        action = {'name': 'zendesk_action_1', 'subdomain': 'digite751', 'api_token': {'value': '123456789'},
                  'subject': 'new ticket',
                  'user_name': 'udit.pandey@digite.com', 'response': 'ticket filed'}

        def __mock_zendesk_error(*args, **kwargs):
            from zenpy.lib.exception import APIException
            raise APIException({"error": {"title": "No help desk at digite751.zendesk.com"}})

        processor = MongoProcessor()
        with patch('zenpy.Zenpy') as mock:
            mock.side_effect = __mock_zendesk_error
            with pytest.raises(ValidationError):
                assert processor.add_zendesk_action(action, bot, user)

    def test_add_zendesk_action_invalid_credentials(self):
        bot = 'test'
        user = 'test'
        action = {'name': 'zendesk_action_1', 'subdomain': 'digite751', 'api_token': {'value': '123456789'},
                  'subject': 'new ticket',
                  'user_name': 'udit.pandey@digite.com', 'response': 'ticket filed'}

        def __mock_zendesk_error(*args, **kwargs):
            from zenpy.lib.exception import APIException
            raise APIException({"error": "Couldn't authenticate you"})

        processor = MongoProcessor()
        with patch('zenpy.Zenpy') as mock:
            mock.side_effect = __mock_zendesk_error
            with pytest.raises(ValidationError):
                assert processor.add_zendesk_action(action, bot, user)

    def test_add_zendesk_action_already_exists(self):
        bot = 'test'
        user = 'test'
        action = {'name': 'zendesk_action', 'subdomain': 'digite751',
                  'api_token': {'value': '123456789'}, 'subject': 'new ticket',
                  'user_name': 'udit.pandey@digite.com', 'response': 'ticket filed'}
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Action exists!'):
            assert processor.add_zendesk_action(action, bot, user)

    def test_add_zendesk_action_existing_name(self):
        processor = MongoProcessor()
        bot = 'test'
        http_url = 'http://www.google.com'
        action = 'test_action_1'
        # file deepcode ignore HardcodedNonCryptoSecret: Random string for testing
        user = 'test'
        response = "json"
        request_method = 'GET'
        http_params_list: List[HttpActionParameters] = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value")]
        header: List[HttpActionParameters] = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=ActionResponseEvaluation(value=response),
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list,
            headers=header
        )
        processor.add_http_action_config(http_action_config.model_dump(), user, bot)

        bot = 'test'
        user = 'test'
        action = {'name': 'test_action_1', 'subdomain': 'digite751', 'api_token': {'value': '123456789'},
                  'subject': 'new ticket', 'user_name': 'udit.pandey@digite.com', 'response': {"value": 'ticket filed'}}
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Action exists!'):
            assert processor.add_zendesk_action(action, bot, user)

    def test_edit_zendesk_action(self):
        bot = 'test'
        user = 'test'
        action = {'name': 'zendesk_action', 'subdomain': 'digite756', 'api_token': {'value': '123456789999'},
                  'subject': 'new ticket',
                  'user_name': 'udit.pandey@digite.com', 'response': 'ticket filed here'}
        processor = MongoProcessor()
        with patch('zenpy.Zenpy'):
            processor.edit_zendesk_action(action, bot, user)

    def test_edit_zendesk_action_invalid_subdomain(self):
        bot = 'test'
        user = 'test'
        action = {'name': 'zendesk_action', 'subdomain': 'digite751', 'api_token': {'value': '123456789'},
                  'subject': 'new ticket', 'user_name': 'udit.pandey@digite.com',
                  'response': 'ticket filed'}

        def __mock_zendesk_error(*args, **kwargs):
            from zenpy.lib.exception import APIException
            raise APIException({"error": {"title": "No help desk at digite751.zendesk.com"}})

        processor = MongoProcessor()
        with patch('zenpy.Zenpy') as mock:
            mock.side_effect = __mock_zendesk_error
            with pytest.raises(ValidationError):
                assert processor.edit_zendesk_action(action, bot, user)

    def test_edit_zendesk_action_does_not_exists(self):
        bot = 'test'
        user = 'test'
        action = {'name': 'zendesk_action_1', 'subdomain': 'digite751', 'api_token': {'value': '123456789'},
                  'subject': 'new ticket',
                  'user_name': 'udit.pandey@digite.com', 'response': 'ticket filed'}
        processor = MongoProcessor()
        with pytest.raises(AppException, match=f'Action with name "{action.get("name")}" not found'):
            assert processor.edit_zendesk_action(action, bot, user)

    def test_list_zendesk_actions(self):
        bot = 'test'
        processor = MongoProcessor()
        zendesk_actions = list(processor.list_zendesk_actions(bot))
        zendesk_actions[0].pop("_id")
        assert zendesk_actions == [
            {'name': 'zendesk_action', 'subdomain': 'digite756', 'user_name': 'udit.pandey@digite.com',
             'api_token': {'_cls': 'CustomActionRequestParameters', 'key': 'api_token', 'encrypt': False,
                           'value': '123456789999', 'parameter_type': 'value'}, 'subject': 'new ticket',
             'response': 'ticket filed here'}]
        bot = 'test_1'
        processor = MongoProcessor()
        assert list(processor.list_zendesk_actions(bot)) == []

    def test_list_zendesk_actions_unmasked(self):
        bot = 'test'
        processor = MongoProcessor()
        zendesk_actions = list(processor.list_zendesk_actions(bot, False))
        assert zendesk_actions[0].get('_id') is None
        assert zendesk_actions == [
            {'name': 'zendesk_action', 'subdomain': 'digite756', 'user_name': 'udit.pandey@digite.com',
             'api_token': {'_cls': 'CustomActionRequestParameters', 'key': 'api_token', 'encrypt': False,
                           'value': '123456789999', 'parameter_type': 'value'}, 'subject': 'new ticket',
             'response': 'ticket filed here'}]

    def test_delete_zendesk_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        processor.delete_action('zendesk_action', bot, user)
        with pytest.raises(DoesNotExist):
            Actions.objects(name='zendesk_action', status=True, bot=bot).get()
        with pytest.raises(DoesNotExist):
            ZendeskAction.objects(name='zendesk_action', status=True, bot=bot).get()

    def test_add_pipedrive_leads_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'pipedrive_leads',
            'domain': 'https://digite751.pipedrive.com/',
            'api_token': {'value': '12345678'},
            'title': 'new lead',
            'response': 'I have failed to create lead for you',
            'metadata': {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
        }
        with patch('pipedrive.client.Client'):
            assert processor.add_pipedrive_action(action, bot, user)
        assert Actions.objects(name='pipedrive_leads', status=True, bot=bot).get()
        assert PipedriveLeadsAction.objects(name='pipedrive_leads', status=True, bot=bot).get()

    def test_add_pipedrive_leads_action_required_metadata_absent(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'pipedrive_invalid_metadata',
            'domain': 'https://digite751.pipedrive.com/',
            'api_token': {'value': '12345678'},
            'title': 'new lead',
            'response': 'I have failed to create lead for you',
            'metadata': {'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
        }
        with pytest.raises(ValidationError, match='metadata: name is required'):
            with patch('pipedrive.client.Client'):
                assert processor.add_pipedrive_action(action, bot, user)

    def test_add_pipedrive_leads_action_invalid_auth(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'pipedrive_invalid_metadata',
            'domain': 'https://digite751.pipedrive.com/',
            'api_token': {'value': '12345678'},
            'title': 'new lead',
            'response': 'I have failed to create lead for you',
            'metadata': {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
        }

        def __mock_exception(*args, **kwargs):
            raise UnauthorizedError('Invalid authentication', {'error_code': 401})

        with pytest.raises(ValidationError, match='Invalid authentication*'):
            with patch('pipedrive.client.Client', __mock_exception):
                assert processor.add_pipedrive_action(action, bot, user)

    def test_add_pipedrive_leads_action_with_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "pipedrive_leads", "type": "PIPEDRIVE_LEADS_ACTION"},
        ]
        story_dict = {'name': "story with pipedrive leads", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with pipedrive leads", bot=bot,
                                events__name='pipedrive_leads', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'story with pipedrive leads']
        assert story_with_form[0]['steps'] == [
            {"name": "greet", "type": "INTENT"},
            {"name": "pipedrive_leads", "type": "PIPEDRIVE_LEADS_ACTION"},
        ]
        processor.delete_complex_story(story_id, 'STORY', bot, user)

    def test_add_pipedrive_leads_action_duplicate(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'pipedrive_leads',
            'domain': 'https://digite751.pipedrive.com/',
            'api_token': {'value': '12345678'},
            'title': 'new lead',
            'response': 'I have failed to create lead for you',
            'metadata': {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
        }
        with pytest.raises(AppException, match='Action exists!'):
            processor.add_pipedrive_action(action, bot, user)

    def test_add_pipedrive_leads_action_existing_name(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'pipedrive_leads_action',
            'domain': 'https://digite751.pipedrive.com/',
            'api_token': {'value': '12345678'},
            'title': 'new lead',
            'response': 'I have failed to create lead for you',
            'metadata': {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
        }
        Actions(name='pipedrive_leads_action', type=ActionType.pipedrive_leads_action.value, bot=bot, user=user).save()
        with pytest.raises(AppException, match='Action exists!'):
            processor.add_pipedrive_action(action, bot, user)

    def test_list_pipedrive_leads_action_masked(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.list_pipedrive_actions(bot))
        assert actions[0]['name'] == 'pipedrive_leads'
        assert actions[0]['api_token'] == {'_cls': 'CustomActionRequestParameters', 'encrypt': False,
                                           'key': 'api_token', 'parameter_type': 'value', 'value': '12345678'}
        assert actions[0]['domain'] == 'https://digite751.pipedrive.com/'
        assert actions[0]['response'] == 'I have failed to create lead for you'
        assert actions[0]['title'] == 'new lead'
        assert actions[0]['metadata'] == {'name': 'name', 'org_name': 'organization', 'email': 'email',
                                          'phone': 'phone'}

    def test_edit_pipedrive_leads_action_not_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'pipedrive_invalid_metadata',
            'domain': 'https://digite751.pipedrive.com/',
            'api_token': {'value': '12345678'},
            'title': 'new lead',
            'response': 'I have failed to create lead for you',
            'metadata': {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
        }
        with pytest.raises(AppException, match='Action with name "pipedrive_invalid_metadata" not found'):
            processor.edit_pipedrive_action(action, bot, user)

    def test_edit_pipedrive_leads_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'pipedrive_leads',
            'domain': 'https://digite7.pipedrive.com/',
            'api_token': {'value': 'asdfghjklertyui'},
            'title': 'new lead generated',
            'response': 'Failed to create lead for you',
            'metadata': {'name': 'name', 'email': 'email', 'phone': 'phone'}
        }
        with patch('pipedrive.client.Client'):
            assert not processor.edit_pipedrive_action(action, bot, user)

    def test_list_pipedrive_leads_action(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.list_pipedrive_actions(bot, False))
        assert actions[0]['name'] == 'pipedrive_leads'
        assert actions[0]['api_token'] == {'_cls': 'CustomActionRequestParameters', 'encrypt': False,
                                           'key': 'api_token', 'parameter_type': 'value', 'value': 'asdfghjklertyui'}
        assert actions[0]['domain'] == 'https://digite7.pipedrive.com/'
        assert actions[0]['response'] == 'Failed to create lead for you'
        assert actions[0]['title'] == 'new lead generated'
        assert actions[0]['metadata'] == {'name': 'name', 'email': 'email', 'phone': 'phone'}

        actions = list(processor.list_pipedrive_actions(bot, True))
        assert actions[0]['name'] == 'pipedrive_leads'
        assert actions[0]['api_token'] == {'_cls': 'CustomActionRequestParameters', 'encrypt': False,
                                           'key': 'api_token', 'parameter_type': 'value', 'value': 'asdfghjklertyui'}
        assert actions[0]['domain'] == 'https://digite7.pipedrive.com/'
        assert actions[0]['response'] == 'Failed to create lead for you'
        assert actions[0]['title'] == 'new lead generated'
        assert actions[0]['metadata'] == {'name': 'name', 'email': 'email', 'phone': 'phone'}

    def test_delete_pipedrive_leads_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        processor.delete_action('pipedrive_leads', bot, user)
        with pytest.raises(DoesNotExist):
            Actions.objects(name='pipedrive_leads', status=True, bot=bot).get()
        with pytest.raises(DoesNotExist):
            PipedriveLeadsAction.objects(name='pipedrive_leads', status=True, bot=bot).get()

    def test_add_razorpay_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action_name = 'razorpay_action'
        action = {
            'name': action_name,
            'api_key': {"value": "API_KEY", "parameter_type": "key_vault"},
            'api_secret': {"value": "API_SECRET", "parameter_type": "kay_vault"},
            'amount': {"value": "amount", "parameter_type": "slot"},
            'currency': {"value": "INR", "parameter_type": "value"},
            'username': {"parameter_type": "sender_id"},
            'email': {"parameter_type": "sender_id"},
            'contact': {"value": "contact", "parameter_type": "slot"},
            'notes': [
                {"key": "order_id", "parameter_type": "slot", "value": "order_id"},
                {"key": "phone_number", "parameter_type": "value", "value": "9876543210"}
            ]
        }
        assert processor.add_razorpay_action(action, bot, user)
        assert Actions.objects(name=action_name, status=True, bot=bot).get()
        assert RazorpayAction.objects(name=action_name, status=True, bot=bot).get()

    def test_add_razorpay_action_required_fields_absent(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action_name = 'test_add_razorpay_action_required_fields_absent'
        action = {
            'name': action_name,
            'amount': {"value": "amount", "parameter_type": "slot"},
            'currency': {"value": "INR", "parameter_type": "value"},
            'username': {"parameter_type": "sender_id"},
            'email': {"parameter_type": "sender_id"},
            'contact': {"value": "contact", "parameter_type": "slot"},
        }
        with pytest.raises(ValidationError):
            processor.add_razorpay_action(action, bot, user)

    def test_add_razorpay_action_with_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "razorpay_action", "type": "RAZORPAY_ACTION"},
        ]
        story_dict = {'name': "story with razorpay action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with razorpay action", bot=bot,
                                events__name='razorpay_action', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == "story with razorpay action"]
        assert story_with_form[0]['steps'] == [
            {"name": "greet", "type": "INTENT"},
            {"name": "razorpay_action", "type": "RAZORPAY_ACTION"},
        ]
        processor.delete_complex_story(story_id, 'STORY', bot, user)

    def test_add_razorpay_action_duplicate(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action_name = 'razorpay_action'
        action = {
            'name': action_name,
            'api_key': {"value": "API_KEY", "parameter_type": "key_vault"},
            'api_secret': {"value": "API_SECRET", "parameter_type": "kay_vault"},
            'amount': {"value": "amount", "parameter_type": "slot"},
            'currency': {"value": "INR", "parameter_type": "value"},
            'username': {"parameter_type": "sender_id"},
            'email': {"parameter_type": "sender_id"},
            'contact': {"value": "contact", "parameter_type": "slot"},
        }
        with pytest.raises(AppException, match='Action exists!'):
            processor.add_razorpay_action(action, bot, user)

    def test_list_razorpay_action(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.get_razorpay_action_config(bot))
        actions[0].pop("timestamp")
        actions[0].pop("_id")
        assert actions == [
            {
                'name': 'razorpay_action',
                'api_key': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'api_key',
                    'encrypt': False,
                    'value': 'API_KEY',
                    'parameter_type': 'key_vault'
                },
                'api_secret': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'api_secret',
                    'encrypt': False,
                    'value': 'API_SECRET',
                    'parameter_type': 'kay_vault'
                },
                'amount': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'amount',
                    'encrypt': False,
                    'value': 'amount',
                    'parameter_type': 'slot'
                },
                'currency': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'currency',
                    'encrypt': False,
                    'value': 'INR',
                    'parameter_type': 'value'
                },
                'username': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'username',
                    'encrypt': False,
                    'parameter_type': 'sender_id'
                },
                'email': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'email',
                    'encrypt': False,
                    'parameter_type': 'sender_id'
                },
                'contact': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'contact',
                    'encrypt': False,
                    'value': 'contact',
                    'parameter_type': 'slot'
                },
                'notes': [
                    {
                        '_cls': 'CustomActionRequestParameters',
                        'key': 'order_id',
                        'encrypt': False,
                        'value': 'order_id',
                        'parameter_type': 'slot'
                    },
                    {
                        '_cls': 'CustomActionRequestParameters',
                        'key': 'phone_number',
                        'encrypt': False,
                        'value': '9876543210',
                        'parameter_type': 'value'
                    }
                ]
            }
        ]

    def test_list_razorpay_action_with_false(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.get_razorpay_action_config(bot, False))
        actions[0].pop("timestamp")
        assert actions[0].get("_id") is None
        assert actions == [
            {
                'name': 'razorpay_action',
                'api_key': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'api_key',
                    'encrypt': False,
                    'value': 'API_KEY',
                    'parameter_type': 'key_vault'
                },
                'api_secret': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'api_secret',
                    'encrypt': False,
                    'value': 'API_SECRET',
                    'parameter_type': 'kay_vault'
                },
                'amount': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'amount',
                    'encrypt': False,
                    'value': 'amount',
                    'parameter_type': 'slot'
                },
                'currency': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'currency',
                    'encrypt': False,
                    'value': 'INR',
                    'parameter_type': 'value'
                },
                'username': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'username',
                    'encrypt': False,
                    'parameter_type': 'sender_id'
                },
                'email': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'email',
                    'encrypt': False,
                    'parameter_type': 'sender_id'
                },
                'contact': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'contact',
                    'encrypt': False,
                    'value': 'contact',
                    'parameter_type': 'slot'
                },
                'notes': [
                    {
                        '_cls': 'CustomActionRequestParameters',
                        'key': 'order_id',
                        'encrypt': False,
                        'value': 'order_id',
                        'parameter_type': 'slot'
                    },
                    {
                        '_cls': 'CustomActionRequestParameters',
                        'key': 'phone_number',
                        'encrypt': False,
                        'value': '9876543210',
                        'parameter_type': 'value'
                    }
                ]
            }
        ]

    def test_edit_razorpay_action_not_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action_name = 'test_edit_razorpay_action_not_exists'
        action = {
            'name': action_name,
            'api_key': {"value": "API_KEY", "parameter_type": "key_vault"},
            'api_secret': {"value": "API_SECRET", "parameter_type": "kay_vault"},
            'amount': {"value": "amount", "parameter_type": "slot"},
            'currency': {"value": "INR", "parameter_type": "value"},
            'username': {"parameter_type": "sender_id"},
            'email': {"parameter_type": "sender_id"},
            'contact': {"value": "contact", "parameter_type": "slot"},
        }
        with pytest.raises(AppException, match='Action with name "test_edit_razorpay_action_not_exists" not found'):
            processor.edit_razorpay_action(action, bot, user)

    def test_edit_razorpay_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action_name = 'razorpay_action'
        action = {
            'name': action_name,
            'api_key': {"value": "API_KEY", "parameter_type": "key_vault"},
            'api_secret': {"value": "API_SECRET", "parameter_type": "kay_vault"},
            'amount': {"value": "amount", "parameter_type": "slot"},
            'currency': {"value": "INR", "parameter_type": "value"},
            'notes': [
                {"key": "phone_number", "parameter_type": "value", "value": "9876543210"}
            ]
        }
        assert not processor.edit_razorpay_action(action, bot, user)

    def test_list_razorpay_action_after_update(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.get_razorpay_action_config(bot))
        actions[0].pop("timestamp")
        actions[0].pop("_id")
        assert actions == [
            {
                'name': 'razorpay_action',
                'api_key': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'api_key',
                    'encrypt': False,
                    'value': 'API_KEY',
                    'parameter_type': 'key_vault'
                },
                'api_secret': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'api_secret',
                    'encrypt': False,
                    'value': 'API_SECRET',
                    'parameter_type': 'kay_vault'
                },
                'amount': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'amount',
                    'encrypt': False,
                    'value': 'amount',
                    'parameter_type': 'slot'
                },
                'currency': {
                    '_cls': 'CustomActionRequestParameters',
                    'key': 'currency',
                    'encrypt': False,
                    'value': 'INR',
                    'parameter_type': 'value'
                },
                'notes': [
                    {
                        '_cls': 'CustomActionRequestParameters',
                        'key': 'phone_number',
                        'encrypt': False,
                        'value': '9876543210',
                        'parameter_type': 'value'
                    }
                ]
            }
        ]

    def test_delete_razorpay_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        processor.delete_action('razorpay_action', bot, user)
        with pytest.raises(DoesNotExist):
            Actions.objects(name='razorpay_action', status=True, bot=bot).get()
        with pytest.raises(DoesNotExist):
            RazorpayAction.objects(name='razorpay_action', status=True, bot=bot).get()

    @responses.activate
    def test_push_notifications_enabled_message_type_event(self, monkeypatch):
        bot = "test"
        user = 'test'
        url = "http://localhost/events"
        with patch.dict(Utility.environment['notifications'], {"enable": True, "server_endpoint": url}):
            responses.add(
                'POST',
                f'{url}/test',
                json={'message': 'Event in progress'}
            )
            ModelProcessor.set_training_status(bot, user, "Inprogress")
            request_body = responses.calls[0].request
            request_body = request_body.body.decode('utf8')
            request_body = json.loads(request_body)
            assert responses.calls[0].request.headers['Authorization']
            assert request_body['event_type'] == "message"
            assert request_body['event']['entity_type'] == "ModelTraining"
            assert request_body['event']['data']['status'] == 'Inprogress'
            assert request_body['event']['data']['bot'] == bot
            assert request_body['event']['data']['user'] == user
            assert not Utility.check_empty_string(request_body['event']['data']['start_timestamp'])

    def test_delete_valid_intent_only(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.delete_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        with pytest.raises(Exception):
            intent = Intents.objects(bot="tests", status=True).get(name="TestingDelGreeting")

    def test_delete_invalid_intent(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.delete_intent("TestingDelGreetingInvalid", "tests", "testUser", is_integration=False)

    def test_delete_empty_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AssertionError):
            processor.delete_intent("", "tests", "testUser", is_integration=False)

    def test_delete_valid_intent(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.delete_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)

    def test_delete_intent_case_insensitive(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.delete_intent("testingdelgreeting", "tests", "testUser", is_integration=False)

    def test_intent_no_stories(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.add_training_example(["Hows You Doing!"], "TestingDelGreeting", "tests", "testUser",
                                       is_integration=False)
        processor.delete_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        actual = processor.get_intents("tests")
        assert not any(intent['name'] == 'TestingDelGreeting' for intent in actual)
        actual = len(list(processor.get_training_examples("TestingDelGreeting", "tests")))
        assert not actual

    def test_get_intents_and_training_examples(self):
        processor = MongoProcessor()
        actual = processor.get_intents_and_training_examples("tests")
        assert len(actual) == 15

    def test_delete_intent_no_training_examples(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.delete_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        actual = processor.get_intents("tests")
        assert not any(intent['name'] == 'TestingDelGreeting' for intent in actual)

    def test_delete_intent_no_utterance(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.delete_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        actual = processor.get_intents("tests")
        assert not any(intent['name'] == 'TestingDelGreeting' for intent in actual)

    def test_delete_intent_with_examples_stories_utterance(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.add_training_example(["hello", "hi"], "TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.delete_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        actual = processor.get_intents("tests")
        assert not any(intent['name'] == 'TestingDelGreeting' for intent in actual)
        actual = list(processor.get_training_examples('TestingDelGreeting', "tests"))
        assert len(actual) == 0

    def test_move_training_example(self):
        processor = MongoProcessor()
        list(processor.add_training_example(["moving to another location", "i will stay"], "test_move_training_example",
                                            "tests", "testUser", is_integration=False))
        list(processor.add_training_example(
            ["moving to another intent [move_to_location](move_to_location)", "i will be here"],
            "move_training_example",
            "tests", "testUser", is_integration=False))
        list(processor.add_training_example(["this is forever"], "move_to_location",
                                            "tests", "testUser", is_integration=False))
        examples_to_move = ["moving to another location", "moving to another place",
                            "moving to another intent [move_to_location](move_to_location)", "this is new", "", " "]
        result = list(processor.add_or_move_training_example(examples_to_move, 'move_to_location', "tests", "testUser"))
        actual = list(processor.get_training_examples('move_to_location', "tests"))
        assert len(actual) == 5
        actual = list(processor.get_training_examples('test_move_training_example', "tests"))
        assert len(actual) == 1
        actual = list(processor.get_training_examples('move_training_example', "tests"))
        assert len(actual) == 1

    def test_move_training_example_intent_not_exists(self):
        processor = MongoProcessor()
        examples_to_move = ["moving to another location", "moving to another place", "", " "]
        with pytest.raises(AppException, match='Intent does not exists'):
            list(processor.add_or_move_training_example(examples_to_move, 'non_existent', "tests", "testUser"))

    def test_add_vector_embedding_action_config_op_embedding_search(self):
        processor = CognitionDataProcessor()
        processor_two = MongoProcessor()
        bot = 'test_vector_bot'
        user = 'test_vector_user'
        action = 'test_vectordb_action_op_embedding_search'
        response = '0'
        query_type = 'embedding_search'
        payload_body = {
            "ids": [
                0
            ],
            "with_payload": True,
            "with_vector": True
        }
        payload = {'type': 'from_value', 'value': payload_body, 'query_type': query_type,}
        schema = {
            "metadata": [
                {"column_name": "country", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "test_add_vector_embedding_action_config_op_embedding_search",
            "bot": bot,
            "user": user
        }
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        pytest.delete_schema_id_db_action = processor.save_cognition_schema(schema, user, bot)
        CognitionData(
            data={"country": "India"},
            content_type="json",
            collection="test_add_vector_embedding_action_config_op_embedding_search",
            bot=bot, user=user).save()
        vectordb_action_config = DatabaseActionRequest(
            name=action,
            collection='test_add_vector_embedding_action_config_op_embedding_search',
            payload=[payload],
            response=ActionResponseEvaluation(value=response)
        )
        processor_two.add_db_action(vectordb_action_config.model_dump(), user, bot)
        actual_vectordb_action = DatabaseAction.objects(name=action, bot=bot, status=True).get()
        assert actual_vectordb_action is not None
        assert Actions.objects(name=action, status=True, bot=bot).get()
        assert actual_vectordb_action['name'] == action
        assert actual_vectordb_action['payload'][0]['type'] == 'from_value'
        assert actual_vectordb_action['payload'][0]['value'] == {'ids': [0], 'with_payload': True, 'with_vector': True}
        assert actual_vectordb_action['payload'][0]['query_type'] == 'embedding_search'
        assert actual_vectordb_action['response']['value'] == '0'
        with pytest.raises(AppException,
                           match='Cannot remove collection test_add_vector_embedding_action_config_op_embedding_search linked to action "test_vectordb_action_op_embedding_search"!'):
            processor.delete_cognition_schema(pytest.delete_schema_id_db_action, bot, user=user)

    def test_add_vector_embedding_action_with_story(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot'
        user = 'test_vector_user'
        steps = [
            {"name": "helu", "type": "INTENT"},
            {"name": "test_vectordb_action_op_embedding_search", "type": "DATABASE_ACTION"},
        ]
        story_dict = {'name': "story with vector embedding action", 'steps': steps, 'type': 'STORY',
                      'template_type': 'CUSTOM'}
        story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with vector embedding action", bot=bot,
                                events__name='test_vectordb_action_op_embedding_search', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'story with vector embedding action']
        assert story_with_form[0]['steps'] == [
            {"name": "helu", "type": "INTENT"},
            {"name": "test_vectordb_action_op_embedding_search", "type": "DATABASE_ACTION"},
        ]
        processor.delete_complex_story(story_id, 'STORY', bot, user)

    def test_add_vector_embedding_action_config_op_payload_search(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot'
        user = 'test_vector_user'
        action = 'test_vectordb_action_op_payload_search'
        response = '1'
        query_type = 'payload_search'
        payload_body = {
            "filter": {
                "should": [
                    {"key": "city", "match": {"value": "London"}},
                    {"key": "color", "match": {"value": "red"}}
                ]
            }
        }
        payload = {'type': 'from_value', 'value': payload_body, 'query_type': query_type,}
        CognitionSchema(
            metadata=[{"column_name": "city", "data_type": "str", "enable_search": True, "create_embeddings": True},
                      {"column_name": "color", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            collection_name="test_add_vector_embedding_action_config_op_payload_search",
            bot=bot, user=user).save()
        CognitionData(
            data={"city": "London", "color": "red"},
            content_type="json",
            collection="test_add_vector_embedding_action_config_op_payload_search",
            bot=bot, user=user).save()
        vectordb_action_config = DatabaseActionRequest(
            name=action,
            collection='test_add_vector_embedding_action_config_op_payload_search',
            payload=[payload],
            response=ActionResponseEvaluation(value=response)
        )
        processor.add_db_action(vectordb_action_config.model_dump(), user, bot)
        actual_vectordb_action = DatabaseAction.objects(name=action, bot=bot, status=True).get()
        assert actual_vectordb_action is not None
        assert Actions.objects(name=action, status=True, bot=bot).get()
        assert actual_vectordb_action['name'] == action
        assert actual_vectordb_action['payload'][0]['type'] == 'from_value'
        assert actual_vectordb_action['payload'][0]['value'] == payload_body
        assert actual_vectordb_action['payload'][0]['query_type'] == 'payload_search'
        assert actual_vectordb_action['response']['value'] == '1'

    def test_add_vector_embedding_action_config_op_embedding_search_from_slot(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot'
        user = 'test_vector_user'
        action = 'test_vectordb_action_op_embedding_search_from_slot'
        response = 'nupur.khare'
        query_type = 'embedding_search'
        payload = {'type': 'from_slot', 'value': 'email', 'query_type': query_type,}
        processor.add_slot({"name": "email", "type": "text", "initial_value": "nupur.khare@digite.com",
                            "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)
        CognitionSchema(
            metadata=[{"column_name": "age", "data_type": "int", "enable_search": True, "create_embeddings": True}],
            collection_name="test_add_vector_embedding_action_config_op_embedding_search_from_slot",
            bot=bot, user=user).save()
        CognitionData(
            data={"age": 23},
            content_type="json",
            collection="test_add_vector_embedding_action_config_op_embedding_search_from_slot",
            bot=bot, user=user).save()
        vectordb_action_config = DatabaseActionRequest(
            name=action,
            collection='test_add_vector_embedding_action_config_op_embedding_search_from_slot',
            payload=[payload],
            response=ActionResponseEvaluation(value=response),
            set_slots=[SetSlotsUsingActionResponse(name="age", value="${data.age}", evaluation_type="expression")]
        )
        processor.add_db_action(vectordb_action_config.model_dump(), user, bot)
        actual_vectordb_action = DatabaseAction.objects(name=action, bot=bot, status=True).get()
        assert actual_vectordb_action is not None
        assert Actions.objects(name=action, status=True, bot=bot).get()
        assert actual_vectordb_action['name'] == action
        assert actual_vectordb_action[
                   'collection'] == 'test_add_vector_embedding_action_config_op_embedding_search_from_slot'
        assert actual_vectordb_action['payload'][0]['type'] == 'from_slot'
        assert actual_vectordb_action['payload'][0]['value'] == 'email'
        assert actual_vectordb_action['payload'][0]['query_type'] == 'embedding_search'
        assert actual_vectordb_action['response']['value'] == 'nupur.khare'

    def test_add_vector_embedding_action_config_op_embedding_search_from_slot_does_not_exists(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot_slot'
        user = 'test_vector_user_slot'
        action = 'test_vectordb_action_slot'
        response = 'nupur.khare'
        query_type = 'embedding_search'
        payload = {'type': 'from_slot', 'value': 'cuisine', 'query_type': query_type,}
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        vectordb_action_config = DatabaseActionRequest(
            name=action,
            collection='test_add_vector_embedding_action_config_op_embedding_search_from_slot_does_not_exists',
            payload=[payload],
            response=ActionResponseEvaluation(value=response),
            set_slots=[SetSlotsUsingActionResponse(name="age", value="${data.age}", evaluation_type="expression")]
        )
        with pytest.raises(AppException, match="Slot with name cuisine not found!"):
            processor.add_db_action(vectordb_action_config.model_dump(), user, bot)

    def test_add_vector_embedding_action_collection_does_not_exists(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot_slot'
        user = 'test_vector_user_slot'
        action = 'test_vectordb_action_collection_not_exists'
        response = '1'
        query_type = 'payload_search'
        payload_body = {
            "filter": {
                "should": [
                    {"key": "city", "match": {"value": "London"}},
                    {"key": "color", "match": {"value": "red"}}
                ]
            }
        }
        payload = {'type': 'from_value', 'value': payload_body, 'query_type': query_type,}
        vectordb_action_config = DatabaseActionRequest(
            name=action,
            collection='test_add_vector_embedding_action_collection_does_not_exists',
            payload=[payload],
            response=ActionResponseEvaluation(value=response),
        )
        with pytest.raises(AppException, match="Collection does not exist!"):
            processor.add_db_action(vectordb_action_config.model_dump(), user, bot)

    def test_add_vector_embedding_action_config_existing_name(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot'
        user = 'test_vector_user'
        action = 'test_vectordb_action_op_embedding_search'
        response = '0'
        query_type = 'embedding_search'
        payload_body = {
            "ids": [
                0
            ],
            "with_payload": True,
            "with_vector": True
        }
        payload = {'type': 'from_value', 'value': payload_body, 'query_type': query_type,}
        vectordb_action_config = DatabaseActionRequest(
            name=action,
            collection='test_add_vector_embedding_action_config_existing_name',
            payload=[payload],
            response=ActionResponseEvaluation(value=response)
        )
        with pytest.raises(AppException, match="Action exists"):
            processor.add_db_action(vectordb_action_config.model_dump(), user, bot)

    def test_add_vector_embedding_action_config_empty_payload_values(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot_empty_name'
        user = 'test_vector_user_empty_name'
        action = 'test_add_vectordb_action_config_empty_name'
        response = '0'
        query_type = 'embedding_search'
        payload_body = {
            "ids": [
                0
            ],
            "with_payload": True,
            "with_vector": True
        }
        payload = {'type': 'from_value', 'value': payload_body, 'query_type': query_type,}
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        CognitionSchema(
            metadata=[{"column_name": "age", "data_type": "int", "enable_search": True, "create_embeddings": True}],
            collection_name="test_add_vector_embedding_action_config_empty_payload_values",
            bot=bot, user=user).save()
        CognitionData(
            data={"age": 23},
            content_type="json",
            collection="test_add_vector_embedding_action_config_empty_payload_values",
            bot=bot, user=user).save()
        vectordb_action_config = DatabaseActionRequest(
            name=action,
            collection='test_add_vector_embedding_action_config_empty_payload_values',
            payload=[payload],
            response=ActionResponseEvaluation(value=response)
        )
        vectordb_action = vectordb_action_config.model_dump()
        vectordb_action['name'] = ''
        with pytest.raises(ValidationError, match="Action name cannot be empty"):
            processor.add_db_action(vectordb_action, user, bot)
        vectordb_action_config_two = DatabaseActionRequest(
            name=action,
            collection='test_add_vector_embedding_action_config_empty_payload_values',
            payload=[payload],
            response=ActionResponseEvaluation(value=response)
        )
        vectordb_action_two = vectordb_action_config_two.model_dump()
        vectordb_action_two['payload'][0]['type'] = ''
        with pytest.raises(ValidationError, match="payload type is required"):
            processor.add_db_action(vectordb_action_two, user, bot)

    def test_add_vector_embedding_action_config_empty_operation_values(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot_empty_operation_values'
        user = 'test_vector_user_empty_operation_values'
        action = 'test_add_vector_embedding_action_config_empty_operation_values'
        response = '0'
        query_type = 'payload_search'
        payload_body = {
            "ids": [
                0
            ],
            "with_payload": True,
            "with_vector": True
        }
        payload = {'type': 'from_value', 'value': payload_body, 'query_type': query_type,}
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        CognitionSchema(
            metadata=[{"column_name": "age", "data_type": "int", "enable_search": True, "create_embeddings": True}],
            collection_name="test_add_vector_embedding_action_config_empty_operation_values",
            bot=bot, user=user).save()
        CognitionData(
            data={"age": 23},
            content_type="json",
            collection="test_add_vector_embedding_action_config_empty_operation_values",
            bot=bot, user=user).save()
        vectordb_action_config = DatabaseActionRequest(
            name=action,
            collection='test_add_vector_embedding_action_config_empty_operation_values',
            payload=[payload],
            response=ActionResponseEvaluation(value=response)
        )
        vectordb_action = vectordb_action_config.model_dump()
        vectordb_action['name'] = ''
        with pytest.raises(ValidationError, match="Action name cannot be empty"):
            processor.add_db_action(vectordb_action, user, bot)
        vectordb_action_config_two = DatabaseActionRequest(
            name=action,
            collection='test_add_vector_embedding_action_config_empty_operation_values',
            payload=[payload],
            response=ActionResponseEvaluation(value=response)
        )
        vectordb_action_two = vectordb_action_config_two.model_dump()
        vectordb_action_two['payload'][0]['query_type'] = ''
        with pytest.raises(ValidationError, match="query type is required"):
            processor.add_db_action(vectordb_action_two, user, bot)

    def test_get_vector_embedding_action(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot_get'
        user = 'test_vector_user'
        action = 'test_get_vectordb_action'
        response = 'nupur.khare'

        query_type = 'embedding_search'
        payload = {'type': 'from_slot', 'value': 'email', 'query_type': query_type,}
        CognitionSchema(
            metadata=[{"column_name": "age", "data_type": "int", "enable_search": True, "create_embeddings": True}],
            collection_name="test_get_vector_embedding_action",
            bot=bot, user=user).save()
        CognitionData(
            data={"age": 23},
            content_type="json",
            collection="test_get_vector_embedding_action",
            bot=bot, user=user).save()
        DatabaseAction(
            name=action,
            collection='test_get_vector_embedding_action',
            payload=[payload],
            response=HttpActionResponse(value=response),
            set_slots=[SetSlotsFromResponse(name="email", value="${data.email}", evaluation_type="expression")],
            bot=bot,
            user=user
        ).save().to_mongo()
        actual = processor.get_db_action_config(bot=bot, action=action)
        assert actual is not None
        assert actual['name'] == action
        assert actual['payload'][0] == {'type': 'from_slot', 'value': 'email', 'query_type': 'embedding_search'}
        assert actual['collection'] == 'test_get_vector_embedding_action'
        assert actual['response'] == {'value': 'nupur.khare', 'dispatch': True, 'evaluation_type': 'expression',
                                      'dispatch_type': 'text'}
        assert actual['db_type'] == 'qdrant'
        assert actual['set_slots'] == [{'name': 'email', 'value': '${data.email}', 'evaluation_type': 'expression'}]

    def test_get_vector_embedding_action_does_not_exists(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot_get_action'
        user = 'test_vector_user'
        action = 'test_get_vectordb_action'
        response = 'nupur.khare'

        query_type = 'embedding_search'
        payload = {'type': 'from_slot', 'value': 'email', 'query_type': query_type,}
        DatabaseAction(
            name=action,
            collection='test_get_vector_embedding_action_does_not_exists',
            payload=[payload],
            response=HttpActionResponse(value=response),
            set_slots=[SetSlotsFromResponse(name="email", value="${data.email}", evaluation_type="expression")],
            bot=bot,
            user=user
        ).save().to_mongo()
        try:
            processor.get_db_action_config(bot=bot, action='embedding')
            assert False
        except AppException as e:
            assert str(e) == "Action does not exists!"

    def test_list_vector_embedding_action(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot'
        user = 'test_vector_user'
        actions = list(processor.list_db_actions(bot, True))
        assert len(actions) == 3

    def test_add_vector_embedding_action_with_utter(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot'
        user = 'test_vector_user'
        action = 'utter_test_vectordb_action_op_embedding_search'
        response = '0'
        query_type = 'embedding_search'
        payload_body = {
            "ids": [
                0
            ],
            "with_payload": True,
            "with_vector": True
        }
        payload = {'type': 'from_value', 'value': payload_body, 'query_type': query_type, }
        vectordb_action_config = DatabaseActionRequest(
            name=action,
            collection='test_add_vector_embedding_action_config_existing_name',
            payload=[payload],
            response=ActionResponseEvaluation(value=response)
        )
        with pytest.raises(AppException, match="Action name cannot start with utter_"):
            processor.add_db_action(vectordb_action_config.model_dump(), user, bot)

    def test_update_vector_embedding_action(self):
        processor = MongoProcessor()
        bot = 'test_update_vectordb_action_bot'
        user = 'test_update_vectordb_action_user'
        action = 'test_update_vectordb_action'
        response = '15'
        query_type = 'payload_search'
        payload_body = {
            "filter": {
                "should": [
                    {"key": "city", "match": {"value": "London"}},
                    {"key": "color", "match": {"value": "red"}}
                ]
            }
        }
        payload = {'type': 'from_value', 'value': payload_body, 'query_type': query_type,}
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        CognitionSchema(
            metadata=[{"column_name": "city", "data_type": "str", "enable_search": True, "create_embeddings": True},
                      {"column_name": "color", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            collection_name="test_update_vector_embedding_action",
            bot=bot, user=user).save()
        CognitionData(
            data={"city": "London", "color": "red"},
            content_type="json",
            collection="test_update_vector_embedding_action",
            bot=bot, user=user).save()
        vectordb_action_config = DatabaseActionRequest(
            name=action,
            collection='test_update_vector_embedding_action',
            payload=[payload],
            response=ActionResponseEvaluation(value=response)
        )
        processor.add_db_action(vectordb_action_config.model_dump(), user, bot)
        actual = DatabaseAction.objects(name=action, bot=bot, status=True).get()
        assert actual is not None
        assert actual['name'] == action
        assert actual['response']['value'] == '15'
        assert actual['payload'][0]['value'] == {'filter': {
            'should': [{'key': 'city', 'match': {'value': 'London'}}, {'key': 'color', 'match': {'value': 'red'}}]}}
        response_two = 'nimble'
        processor.add_slot({"name": "name", "type": "text", "initial_value": "nupur",
                            "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)
        payload_two = {'type': 'from_value', 'value': 'name', 'query_type': query_type}
        vectordb_action_config_updated = DatabaseActionRequest(
            name=action,
            collection='test_update_vector_embedding_action',
            payload=[payload_two],
            response=ActionResponseEvaluation(value=response_two),
            set_slots=[SetSlotsUsingActionResponse(name="name", value="${data.name}", evaluation_type="expression")]
        )
        processor.update_db_action(vectordb_action_config_updated.model_dump(), user, bot)
        actual_two = DatabaseAction.objects(name=action, bot=bot, status=True).get()
        assert actual_two is not None
        assert actual_two['name'] == action
        assert actual_two['response']['value'] == 'nimble'
        assert actual_two['payload'][0]['value'] == 'name'

    def test_update_vector_embedding_action_does_not_exists(self):
        processor = MongoProcessor()
        bot = 'test_update_vectordb_action_bot'
        user = 'test_update_vectordb_action_user'
        action = 'test_update_vectordb_action_does_not_exists'
        response = 'Digite'
        query_type = 'embedding_search'
        payload_body = {
            "ids": [
                0
            ],
            "with_payload": True,
            "with_vector": True
        }
        payload = {'type': 'from_value', 'value': payload_body, 'query_type': query_type,}
        vectordb_action_config = DatabaseActionRequest(
            name=action,
            collection='test_update_vector_embedding_action_does_not_exists',
            payload=[payload],
            response=ActionResponseEvaluation(value=response)
        )
        with pytest.raises(AppException,
                           match='Action with name "test_update_vectordb_action_does_not_exists" not found'):
            processor.update_db_action(vectordb_action_config.model_dump(), user, bot)

    def test_delete_vector_embedding_action_config(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot'
        user = 'test_vector_user'
        action = 'test_delete_vector_embedding_action_config'
        response = '0'
        query_type = 'embedding_search'
        payload_body = {
            "ids": [
                0
            ],
            "with_payload": True,
            "with_vector": True
        }
        payload = {'type': 'from_value', 'value': payload_body, 'query_type': query_type,}
        Actions(name=action, type=ActionType.database_action.value, bot=bot, user=user).save()
        DatabaseAction(
            name=action,
            collection='test_delete_vector_embedding_action_config',
            payload=[payload],
            response=HttpActionResponse(value=response),
            bot=bot,
            user=user
        ).save().to_mongo()
        processor.delete_action(action, user=user, bot=bot)
        try:
            DatabaseAction.objects(name=action, bot=bot, user=user, status=True).get(
                name__iexact=action)
            assert False
        except DoesNotExist:
            assert True

    def test_delete_vector_embedding_action_config_non_existing(self):
        processor = MongoProcessor()
        bot = 'test_vector_bot'
        user = 'test_vector_user'
        action = 'test_delete_vector_embedding_action_config_non_existing'
        response = '0'
        query_type = 'embedding_search'
        payload_body = {
            "ids": [
                0
            ],
            "with_payload": True,
            "with_vector": True
        }
        payload = {'type': 'from_value', 'value': payload_body, 'query_type': query_type,}
        DatabaseAction(
            name=action,
            collection='test_delete_vector_embedding_action_config_non_existing',
            payload=[payload],
            response=HttpActionResponse(value=response),
            bot=bot,
            user=user
        ).save().to_mongo()

        try:
            processor.delete_action("test_delete_vector_embedding_action_config_non_existing_non_existing", user=user,
                                    bot=bot)
            assert False
        except AppException as e:
            assert str(e).__contains__(
                'Action with name "test_delete_vector_embedding_action_config_non_existing_non_existing" not found')

    def test_add_http_action_config_with_utter(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'utter_test_action'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        params = [HttpActionParameters(key="key", value="value", parameter_type="slot")]

        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=ActionResponseEvaluation(value=response),
            http_url=http_url,
            request_method=request_method,
            params_list=params
        )
        with pytest.raises(AppException, match="Action name cannot start with utter_"):
            processor.add_http_action_config(http_action_config.model_dump(), user, bot)

    def test_add_http_action_config(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_action'
        # file deepcode ignore HardcodedNonCryptoSecret: Random string for testing
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        http_params_list: List[HttpActionParameters] = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value")]
        header: List[HttpActionParameters] = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=ActionResponseEvaluation(value=response),
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list,
            headers=header
        )
        processor.add_http_action_config(http_action_config.model_dump(), user, bot)
        actual_http_action = HttpActionConfig.objects(action_name=action, bot=bot, user=user, status=True).get(
            action_name__iexact=action).to_mongo().to_dict()
        assert actual_http_action is not None
        assert actual_http_action['action_name'] == action
        assert actual_http_action['http_url'] == http_url
        assert actual_http_action['response'] == {"value": response, "dispatch": True, "evaluation_type": "expression",
                                                  "dispatch_type": "text"}
        assert actual_http_action['request_method'] == request_method
        assert actual_http_action['params_list'] is not None
        assert actual_http_action['params_list'][0]['key'] == "param1"
        assert actual_http_action['params_list'][0]['value'] == "param1"
        assert actual_http_action['params_list'][0]['parameter_type'] == "slot"
        assert actual_http_action['params_list'][1]['key'] == "param2"
        assert actual_http_action['params_list'][1]['value'] == "value2"
        assert actual_http_action['params_list'][1]['parameter_type'] == "value"
        assert actual_http_action['headers'][0]['key'] == "param3"
        assert actual_http_action['headers'][0]['value'] == "param1"
        assert actual_http_action['headers'][0]['parameter_type'] == "slot"
        assert actual_http_action['headers'][1]['key'] == "param4"
        assert actual_http_action['headers'][1]['value'] == "value2"
        assert actual_http_action['headers'][1]['parameter_type'] == "value"
        assert Utility.is_exist(Actions, raise_error=False, name__iexact=action, bot=bot)

    def test_add_http_action_config_no_response(self):
        processor = MongoProcessor()
        bot = 'test_bot_2'
        http_url = 'http://www.google.com'
        action = 'test_add_http_action_config_no_response'
        user = 'test_user'
        request_method = 'GET'
        http_params_list: List[HttpActionParameters] = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value")]
        header: List[HttpActionParameters] = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=ActionResponseEvaluation(value=None, dispatch=False, evaluation_type="script"),
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list,
            headers=header,
            set_slots=[SetSlotsUsingActionResponse(name="bot", value="${data.key}", evaluation_type="script"),
                       SetSlotsUsingActionResponse(name="email", value="${data.email}", evaluation_type="expression")]
        )
        processor.add_http_action_config(http_action_config.model_dump(), user, bot)
        actual_http_action = HttpActionConfig.objects(action_name=action, bot=bot, user=user, status=True).get(
            action_name__iexact=action).to_mongo().to_dict()
        actual_http_action.pop('_id')
        actual_http_action.pop("timestamp")
        actual_http_action = json.loads(json.dumps(actual_http_action))
        assert actual_http_action is not None
        assert actual_http_action == {'action_name': 'test_add_http_action_config_no_response',
                                      'http_url': 'http://www.google.com',
                                      'request_method': 'GET', 'content_type': 'json', 'params_list': [
                {'_cls': 'HttpActionRequestBody', 'key': 'param1', 'value': 'param1', 'parameter_type': 'slot',
                 'encrypt': False},
                {'_cls': 'HttpActionRequestBody', 'key': 'param2', 'value': 'value2', 'parameter_type': 'value',
                 'encrypt': False}], 'headers': [
                {'_cls': 'HttpActionRequestBody', 'key': 'param3', 'value': 'param1', 'parameter_type': 'slot',
                 'encrypt': False},
                {'_cls': 'HttpActionRequestBody', 'key': 'param4', 'value': 'value2', 'parameter_type': 'value',
                 'encrypt': False}],
                                      'response': {'dispatch': False, 'evaluation_type': 'script'
                                          , "dispatch_type": "text"}, 'set_slots': [
                {'name': 'bot', 'value': '${data.key}', 'evaluation_type': 'script'},
                {'name': 'email', 'value': '${data.email}', 'evaluation_type': 'expression'}], 'bot': 'test_bot_2',
                                      'user': 'test_user', 'status': True}
        assert Utility.is_exist(Actions, raise_error=False, name__iexact=action, bot=bot)

    def test_add_http_action_config_complete_data(self):
        processor = MongoProcessor()
        bot = 'test_bot_1'
        http_url = 'http://www.google.com'
        action = 'test_add_http_action_config_complete_data'
        user = 'test_user'
        request_method = 'GET'
        http_params_list: List[HttpActionParameters] = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value", encrypt=True)]
        header: List[HttpActionParameters] = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value", encrypt=True)]
        http_action_config = HttpActionConfigRequest(
            content_type=HttpContentType.urlencoded_form_data.value,
            action_name=action,
            response=ActionResponseEvaluation(value="${RESPONSE}", dispatch=True, evaluation_type="expression"),
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list,
            headers=header,
            set_slots=[SetSlotsUsingActionResponse(name="bot", value="${data.key}", evaluation_type="script"),
                       SetSlotsUsingActionResponse(name="email", value="${data.email}", evaluation_type="expression")]
        )
        processor.add_http_action_config(http_action_config.model_dump(), user, bot)
        config = processor.get_http_action_config(bot, action)
        config.pop("timestamp")
        config = json.loads(json.dumps(config))
        assert config == {'action_name': 'test_add_http_action_config_complete_data',
                          'http_url': 'http://www.google.com', 'request_method': 'GET',
                          'content_type': 'application/x-www-form-urlencoded',
                          'params_list': [
                              {'key': 'param1', 'value': 'param1', 'parameter_type': 'slot', 'encrypt': False},
                              {'key': 'param2', 'value': 'value2', 'parameter_type': 'value', 'encrypt': True}],
                          'headers': [{'key': 'param3', 'value': 'param1', 'parameter_type': 'slot', 'encrypt': False},
                                      {'key': 'param4', 'value': 'value2', 'parameter_type': 'value', 'encrypt': True}],
                          'response': {'value': '${RESPONSE}', 'dispatch': True, 'evaluation_type': 'expression',
                                       "dispatch_type": "text"},
                          'set_slots': [{'name': 'bot', 'value': '${data.key}', 'evaluation_type': 'script'},
                                        {'name': 'email', 'value': '${data.email}', 'evaluation_type': 'expression'}],
                          'bot': 'test_bot_1', 'user': 'test_user', 'status': True}
        assert Utility.is_exist(Actions, raise_error=False, name__iexact=action, bot=bot)

    def test_add_http_action_config_missing_values(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_action_missing_values'
        # file deepcode ignore HardcodedNonCryptoSecret: Random string for testing
        auth_token = "bearer dhdshghfhzxfgadfhdhdhshdshsdfhsdhsdhnxngfgxngf"
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        http_params_list: List[HttpActionParameters] = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            auth_token=auth_token,
            action_name=action,
            response=ActionResponseEvaluation(value=response, dispatch_type=DispatchType.json.value),
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list
        )
        http_dict = http_action_config.model_dump()
        http_dict['action_name'] = ''
        with pytest.raises(ValidationError, match="Action name cannot be empty"):
            processor.add_http_action_config(http_dict, user, bot)
        http_dict['action_name'] = action
        http_dict['response']['dispatch_type'] = 'invalid_dispatch_type'
        with pytest.raises(ValidationError, match="Invalid dispatch_type"):
            processor.add_http_action_config(http_dict, user, bot)
        http_dict['response']['dispatch_type'] = DispatchType.json.value
        http_dict['http_url'] = None
        with pytest.raises(ValidationError, match="URL cannot be empty"):
            processor.add_http_action_config(http_dict, user, bot)
        http_dict['http_url'] = "www.google.com"
        with pytest.raises(ValidationError, match="URL is malformed"):
            processor.add_http_action_config(http_dict, user, bot)
        http_dict['http_url'] = http_url
        http_dict['request_method'] = "XYZ"
        with pytest.raises(ValidationError, match="Invalid HTTP method"):
            processor.add_http_action_config(http_dict, user, bot)
        http_dict['request_method'] = "GET"
        http_dict['params_list'][0]['key'] = None
        with pytest.raises(ValidationError, match="key in http action parameters cannot be empty"):
            processor.add_http_action_config(http_dict, user, bot)
        http_dict['params_list'][0]['value'] = None
        http_dict['params_list'][0]['key'] = "param1"
        with pytest.raises(ValidationError, match="Provide name of the slot as value"):
            processor.add_http_action_config(http_dict, user, bot)
        http_dict['params_list'][0]['value'] = "bot"
        http_dict['params_list'][0]['key'] = "param1"
        http_dict['response']['dispatch'] = True
        http_dict['response']['value'] = "  "
        with pytest.raises(ValidationError, match="response is required for dispatch"):
            processor.add_http_action_config(http_dict, user, bot)
        http_dict['response']['value'] = "Action executed"
        http_dict['params_list'].append(
            {"key": "Access_key", "value": "  ", "parameter_type": "key_vault", "encrypt": False})
        with pytest.raises(ValidationError, match="Provide key from key vault as value"):
            processor.add_http_action_config(http_dict, user, bot)

    def test_list_http_action(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        actions = processor.list_http_actions(bot)
        assert len(actions) == 1

    def test_list_http_action_names(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        actions = processor.list_http_action_names(bot)
        assert len(actions) == 1

    def test_list_http_action_names_empty(self):
        processor = MongoProcessor()
        bot = 'test_bot1'
        actions = processor.list_http_action_names(bot)
        assert len(actions) == 0

    def test_add_http_action_config_existing(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_add_http_action_config_existing'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        params = [HttpActionParameters(key="key", value="value", parameter_type="slot")]

        HttpActionConfig(
            action_name=action,
            response=HttpActionResponse(value=response),
            http_url=http_url,
            request_method=request_method,
            bot=bot,
            user=user
        ).save().id.__str__()

        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=ActionResponseEvaluation(value=response),
            http_url=http_url,
            request_method=request_method,
            params_list=params
        )
        try:
            processor.add_http_action_config(http_action_config.model_dump(), user, bot)
            assert False
        except AppException as ex:
            assert str(ex).__contains__("Action exists")

    def test_add_http_action_config_existing_name(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_action'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        params = [HttpActionParameters(key="key", value="value", parameter_type="slot")]

        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=ActionResponseEvaluation(value=response),
            http_url=http_url,
            request_method=request_method,
            params_list=params
        )
        with pytest.raises(AppException, match="Action exists"):
            processor.add_http_action_config(http_action_config.model_dump(), user, bot)

    def test_delete_http_action_config(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_delete_http_action_config'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        Actions(name=action, type=ActionType.http_action.value, bot=bot, user=user).save()
        HttpActionConfig(
            action_name=action,
            response=HttpActionResponse(value=response),
            http_url=http_url,
            request_method=request_method,
            bot=bot,
            user=user
        ).save().to_mongo()
        processor.delete_action(action, user=user, bot=bot)
        try:
            HttpActionConfig.objects(action_name=action, bot=bot, user=user, status=True).get(
                action_name__iexact=action)
            assert False
        except DoesNotExist:
            assert True

    def test_delete_http_action_config_non_existing(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        action = 'test_delete_http_action_config_non_existing'
        user = 'test_user'
        http_url = 'http://www.google.com'
        response = "json"
        request_method = 'GET'
        HttpActionConfig(
            action_name=action,
            response=HttpActionResponse(value=response),
            http_url=http_url,
            request_method=request_method,
            bot=bot,
            user=user
        ).save().to_mongo()
        try:
            processor.delete_action("test_delete_http_action_config_non_existing_non_existing", user=user, bot=bot)
            assert False
        except AppException as e:
            assert str(e).__contains__(
                'Action with name "test_delete_http_action_config_non_existing_non_existing" not found')

    def test_get_http_action_config(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_get_http_action_config1'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        HttpActionConfig(
            action_name=action,
            response=HttpActionResponse(value=response),
            http_url=http_url,
            request_method=request_method,
            bot=bot,
            user=user
        ).save().to_mongo()

        actual_test_user1 = processor.get_http_action_config(bot=bot, action_name=action)
        assert actual_test_user1 is not None
        assert actual_test_user1['action_name'] == action
        assert actual_test_user1['content_type'] == 'application/json'
        assert actual_test_user1['response'] == {'dispatch': True, 'evaluation_type': 'expression', 'value': 'json',
                                                 "dispatch_type": "text"}
        assert actual_test_user1['http_url'] == http_url
        assert actual_test_user1['request_method'] == request_method

        http_url1 = 'http://www.google.com'
        action1 = 'test_get_http_action_config'
        user1 = 'test_user1'
        response1 = ""
        request_method1 = 'POST'
        HttpActionConfig(
            action_name=action1,
            response=HttpActionResponse(value=response1, dispatch=False),
            http_url=http_url1,
            request_method=request_method1,
            bot=bot,
            user=user1
        ).save().to_mongo()

        actual_test_user2 = processor.get_http_action_config(bot=bot, action_name=action)
        assert actual_test_user2 is not None
        assert actual_test_user2['action_name'] == action
        assert actual_test_user2['response'] == {'dispatch': True, 'evaluation_type': 'expression', 'value': 'json',
                                                 "dispatch_type": "text"}
        assert actual_test_user2['http_url'] == http_url
        assert actual_test_user2['request_method'] == request_method

        http_url1 = 'http://www.google.com'
        action1 = 'test_get_http_action_config'
        user1 = 'test_user1'
        request_method1 = 'POST'
        HttpActionConfig(
            action_name=action1,
            response=HttpActionResponse(dispatch=False),
            http_url=http_url1,
            request_method=request_method1,
            bot=bot,
            user=user1
        ).save().to_mongo()

        actual_test_user2 = processor.get_http_action_config(bot=bot, action_name=action)
        assert actual_test_user2 is not None
        assert actual_test_user2['action_name'] == action
        assert actual_test_user2['response'] == {'dispatch': True, 'evaluation_type': 'expression', 'value': "json",
                                                 "dispatch_type": "text"}
        assert actual_test_user2['http_url'] == http_url
        assert actual_test_user2['request_method'] == request_method

    def test_get_http_action_config_non_existing(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_action'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        HttpActionConfig(
            action_name=action,
            response=HttpActionResponse(value=response),
            http_url=http_url,
            request_method=request_method,
            bot=bot,
            user=user
        ).save().to_mongo()

        try:
            processor.get_http_action_config(bot=bot, action_name="action")
            assert False
        except AppException as e:
            assert str(e) == "No HTTP action found for bot test_bot and action action"

    def test_add_http_action_config_with_dynamic_params(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_add_http_action_config_with_dynamic_params'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        dynamic_params = \
            "{\"sender_id\": \"${sender_id}\", \"user_message\": \"${user_message}\", \"intent\": \"${intent}\"}"
        dispatch_type = "json"
        header: List[HttpActionParameters] = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=ActionResponseEvaluation(value=response, dispatch_type=dispatch_type),
            http_url=http_url,
            request_method=request_method,
            dynamic_params=dynamic_params,
            headers=header
        )
        processor.add_http_action_config(http_action_config.model_dump(), user, bot)
        actual_http_action = HttpActionConfig.objects(action_name=action, bot=bot, user=user, status=True).get(
            action_name__iexact=action).to_mongo().to_dict()
        assert actual_http_action is not None
        assert actual_http_action['action_name'] == action
        assert actual_http_action['http_url'] == http_url
        assert actual_http_action['response'] == {"value": response, "dispatch": True, "evaluation_type": "expression",
                                                  "dispatch_type": "json"}
        assert actual_http_action['request_method'] == request_method
        assert actual_http_action['params_list'] == []
        assert actual_http_action['dynamic_params'] == dynamic_params
        assert actual_http_action['headers'][0]['key'] == "param3"
        assert actual_http_action['headers'][0]['value'] == "param1"
        assert actual_http_action['headers'][0]['parameter_type'] == "slot"
        assert actual_http_action['headers'][1]['key'] == "param4"
        assert actual_http_action['headers'][1]['value'] == "value2"
        assert actual_http_action['headers'][1]['parameter_type'] == "value"
        assert Utility.is_exist(Actions, raise_error=False, name__iexact=action, bot=bot)

    def test_update_http_config_with_dynamic_params(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_update_http_config_with_dynamic_params'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        dispatch_type = 'json'
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            content_type=HttpContentType.application_json.value,
            response=ActionResponseEvaluation(value=response, evaluation_type="script"),
            http_url=http_url,
            request_method=request_method,
            set_slots=[SetSlotsUsingActionResponse(name="bot", value="${data.key}", evaluation_type="script"),
                       SetSlotsUsingActionResponse(name="email", value="${data.email}", evaluation_type="expression")]
        )
        http_config_id = processor.add_http_action_config(http_action_config.model_dump(), user, bot)
        assert http_config_id is not None
        http_url = 'http://www.alphabet.com'
        response = "string"
        request_method = 'POST'
        dynamic_params = \
            "{\"sender_id\": \"${sender_id}\", \"user_message\": \"${user_message}\", \"intent\": \"${intent}\"}"
        dispatch_type = "text"
        header = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            content_type=HttpContentType.urlencoded_form_data.value,
            response=ActionResponseEvaluation(value=response, dispatch_type=dispatch_type),
            http_url=http_url,
            request_method=request_method,
            dynamic_params=dynamic_params,
            headers=header,
            set_slots=[SetSlotsUsingActionResponse(name="bot", value="${data.key}", evaluation_type="script")]
        )
        processor.update_http_config(http_action_config.model_dump(), user, bot)

        actual_http_action = HttpActionConfig.objects(action_name=action, bot=bot, user=user, status=True).get(
            action_name__iexact=action).to_mongo().to_dict()
        assert actual_http_action is not None
        assert actual_http_action['action_name'] == action
        assert actual_http_action['http_url'] == http_url
        assert actual_http_action['response'] == {"value": response, "dispatch": True, "evaluation_type": "expression",
                                                  "dispatch_type": "text"}
        assert actual_http_action['request_method'] == request_method
        assert actual_http_action['params_list'] == []
        assert actual_http_action['dynamic_params'] == dynamic_params
        assert actual_http_action['headers'][0]['key'] == "param3"
        assert actual_http_action['headers'][0]['value'] == "param1"
        assert actual_http_action['headers'][0]['parameter_type'] == "slot"
        assert actual_http_action['headers'][1]['key'] == "param4"
        assert actual_http_action['headers'][1]['value'] == "value2"
        assert actual_http_action['headers'][1]['parameter_type'] == "value"
        assert Utility.is_exist(Actions, raise_error=False, name__iexact=action, bot=bot)

    def test_update_http_config(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_update_http_config'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        http_params_list: List[HttpActionParameters] = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value", encrypt=True)]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            content_type=HttpContentType.application_json.value,
            response=ActionResponseEvaluation(value=response, evaluation_type="script"),
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list,
            set_slots=[SetSlotsUsingActionResponse(name="bot", value="${data.key}", evaluation_type="script"),
                       SetSlotsUsingActionResponse(name="email", value="${data.email}", evaluation_type="expression")]
        )
        http_config_id = processor.add_http_action_config(http_action_config.model_dump(), user, bot)
        assert http_config_id is not None
        http_url = 'http://www.alphabet.com'
        response = "string"
        request_method = 'POST'
        http_params_list = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value", encrypt=True),
            HttpActionParameters(key="param5", parameter_type="sender_id"),
            HttpActionParameters(key="param6", parameter_type="user_message"),
            HttpActionParameters(key="param7", parameter_type="chat_log"),
            HttpActionParameters(key="param8", parameter_type="intent")]
        header = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value", encrypt=True),
            HttpActionParameters(key="param3", parameter_type="sender_id"),
            HttpActionParameters(key="param4", parameter_type="user_message"),
            HttpActionParameters(key="param5", parameter_type="chat_log"),
            HttpActionParameters(key="param6", parameter_type="intent")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            content_type=HttpContentType.urlencoded_form_data.value,
            response=ActionResponseEvaluation(value=response),
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list,
            headers=header,
            set_slots=[SetSlotsUsingActionResponse(name="bot", value="${data.key}", evaluation_type="script")]
        )
        processor.update_http_config(http_action_config.model_dump(), user, bot)

        config = processor.get_http_action_config(bot, action)
        config.pop("timestamp")
        config = json.loads(json.dumps(config))
        assert config == {'action_name': 'test_update_http_config', 'http_url': 'http://www.alphabet.com',
                          'request_method': 'POST', 'content_type': 'application/x-www-form-urlencoded',
                          'params_list': [
                              {'key': 'param3', 'value': 'param1', 'parameter_type': 'slot', 'encrypt': False},
                              {'key': 'param4', 'value': 'value2', 'parameter_type': 'value', 'encrypt': True},
                              {'key': 'param5', 'value': '', 'parameter_type': 'sender_id', 'encrypt': False},
                              {'key': 'param6', 'value': '', 'parameter_type': 'user_message', 'encrypt': False},
                              {'key': 'param7', 'value': '', 'parameter_type': 'chat_log', 'encrypt': False},
                              {'key': 'param8', 'value': '', 'parameter_type': 'intent', 'encrypt': False}],
                          'headers': [{'key': 'param1', 'value': 'param1', 'parameter_type': 'slot', 'encrypt': False},
                                      {'key': 'param2', 'value': 'value2', 'parameter_type': 'value', 'encrypt': True},
                                      {'key': 'param3', 'value': '', 'parameter_type': 'sender_id', 'encrypt': False},
                                      {'key': 'param4', 'value': '', 'parameter_type': 'user_message',
                                       'encrypt': False},
                                      {'key': 'param5', 'value': '', 'parameter_type': 'chat_log', 'encrypt': False},
                                      {'key': 'param6', 'value': '', 'parameter_type': 'intent', 'encrypt': False}],
                          'response': {'value': 'string', 'dispatch': True, 'evaluation_type': 'expression',
                                       "dispatch_type": "text"},
                          'set_slots': [{'name': 'bot', 'value': '${data.key}', 'evaluation_type': 'script'}],
                          'bot': 'test_bot', 'user': 'test_user', 'status': True}

    def test_update_http_config_invalid_action(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_update_http_config_invalid_action'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        http_params_list: List[HttpActionParameters] = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=ActionResponseEvaluation(value=response),
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list
        )
        http_config_id = processor.add_http_action_config(http_action_config.model_dump(), user, bot)
        assert http_config_id is not None
        bot = 'test_bot'
        http_url = 'http://www.alphabet.com'
        action = 'test_update_http_config_invalid'
        user = 'test_user'
        response = "string"
        request_method = 'POST'
        http_params_list = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=ActionResponseEvaluation(value=response),
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list
        )
        try:
            processor.update_http_config(http_action_config.model_dump(), user, bot)
        except AppException as e:
            assert str(e) == 'No HTTP action found for bot test_bot and action test_update_http_config_invalid'

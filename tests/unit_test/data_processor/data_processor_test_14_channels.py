from tests.unit_test.data_processor.data_processor_support import *  # noqa: F403
from tests.unit_test.data_processor.data_processor_support import (
    MongoProcessorTestBase,
    fast_rasa_training,
)

class TestMongoProcessor(MongoProcessorTestBase):
    def test_add_email_action(self):
        processor = MongoProcessor()
        email_config = {"action_name": "email_config",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": None,
                        "smtp_password": {'value': "test"},
                        "from_email": {"value": "from_email", "parameter_type": "slot"},
                        "to_email": {"value": ["test@test.com", "test1@test.com"], "parameter_type": "value"},
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "dispatch_bot_response": True,
                        "tls": False
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            assert processor.add_email_action(email_config, "TEST", "tests") is not None

    def test_add_email_action_dispatch_false(self):
        processor = MongoProcessor()
        email_config = {"action_name": "email_config_disp_false",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": None,
                        "smtp_password": {'value': "test"},
                        "from_email": {"value": "from_email", "parameter_type": "slot"},
                        "to_email": {"value": ["test@test.com", "test1@test.com"], "parameter_type": "value"},
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "dispatch_bot_response": False,
                        "tls": False
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            assert processor.add_email_action(email_config, "TEST", "tests") is not None
            EmailActionConfig.objects(action_name="email_config_disp_false").delete()

    def test_add_email_action_with_custom_text(self):
        processor = MongoProcessor()
        email_config = {"action_name": "email_config_with_custom_text",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": None,
                        "smtp_password": {'value': "test"},
                        "from_email": {"value": "from_email", "parameter_type": "slot"},
                        "to_email": {"value": ["test@test.com", "test1@test.com"], "parameter_type": "value"},
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "dispatch_bot_response": True,

                        "tls": False,
                        "custom_text": {"value": "Hello from kairon!"}
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            assert processor.add_email_action(email_config, "TEST", "tests") is not None

    def test_add_email_action_with_story(self):
        processor = MongoProcessor()
        bot = 'TEST'
        user = 'tests'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "email_config", "type": "EMAIL_ACTION"},
        ]
        story_dict = {'name': "story with email action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with email action", bot=bot,
                                events__name='email_config', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == "story with email action"]
        assert story_with_form[0]['steps'] == [
            {'name': 'greet', 'type': 'INTENT'},
            {'name': 'email_config', 'type': 'EMAIL_ACTION'},
        ]
        processor.delete_complex_story(story_id, 'STORY', bot, user)

    def test_add_email_action_validation_error(self):
        processor = MongoProcessor()
        email_config = {"action_name": "email_config1",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": None,
                        "smtp_password": {'value': "test"},
                        "from_email": {"value": "from_email", "parameter_type": "slot"},
                        "to_email": {"value": ["test@test.com", "test1@test.com"], "parameter_type": "value"},
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "dispatch_bot_response": True,

                        "tls": False
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            mock_smtp.return_value = Exception()
            with pytest.raises(ValidationError, match="Invalid SMTP url"):
                processor.add_email_action(email_config, "TEST", "tests")

        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            temp = email_config['action_name']
            email_config['action_name'] = ""
            with pytest.raises(ValidationError, match="Action name cannot be empty"):
                processor.add_email_action(email_config, "TEST", "tests")
            email_config['action_name'] = temp

            temp = email_config['smtp_url']
            email_config['smtp_url'] = ""
            with pytest.raises(ValidationError, match="URL cannot be empty"):
                processor.add_email_action(email_config, "TEST", "tests")
            email_config['smtp_url'] = temp

            temp = email_config['from_email']
            email_config['from_email'] = {"value": "test@test", "parameter_type": "value"}
            with pytest.raises(ValidationError, match="Invalid From or To email address"):
                processor.add_email_action(email_config, "TEST", "tests")

            email_config['from_email'] = {"value": "", "parameter_type": "slot"}
            with pytest.raises(ValidationError, match="Provide name of the slot as value"):
                processor.add_email_action(email_config, "TEST", "tests")
            email_config['from_email'] = temp

            temp = email_config['to_email']
            email_config['to_email'] = {"value": "test@test", "parameter_type": "value"}
            with pytest.raises(ValidationError, match="Provide list of emails as value"):
                processor.add_email_action(email_config, "TEST", "tests")

            email_config['to_email'] = {"value": ["test@test"], "parameter_type": "value"}
            with pytest.raises(ValidationError, match="Invalid From or To email address"):
                processor.add_email_action(email_config, "TEST", "tests")

            email_config['to_email'] = {"value": "", "parameter_type": "slot"}
            with pytest.raises(ValidationError, match="Provide name of the slot as value"):
                processor.add_email_action(email_config, "TEST", "tests")

            email_config['to_email'] = temp

            email_config["custom_text"] = {"value": "custom_text_slot", "parameter_type": "sender_id"}
            with pytest.raises(ValidationError, match="custom_text can only be of type value or slot!"):
                processor.add_email_action(email_config, "TEST", "tests")

    def test_add_email_action_duplicate(self):
        processor = MongoProcessor()
        email_config = {"action_name": "email_config",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": None,
                        "smtp_password": {'value': "test"},
                        "from_email": {"value": "from_email", "parameter_type": "slot"},
                        "to_email": {"value": ["test@test.com", "test1@test.com"], "parameter_type": "value"},
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "dispatch_bot_response": True,

                        "tls": False
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            with pytest.raises(AppException, match="Action exists!"):
                processor.add_email_action(email_config, "TEST", "tests")

    def test_add_email_action_existing_name(self):
        processor = MongoProcessor()
        email_config = {"action_name": "test_action",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": None,
                        "smtp_password": {'value': "test"},
                        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
                        "to_email": {"value": "to_email", "parameter_type": "slot"},
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "dispatch_bot_response": True,

                        "tls": False
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            with pytest.raises(AppException, match="Action exists!"):
                processor.add_email_action(email_config, "test_bot", "tests")

    def test_edit_email_action(self):
        processor = MongoProcessor()
        email_config = {"action_name": "email_config",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": None,
                        "smtp_password": {'value': "test"},
                        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
                        "to_email": {"value": "to_email", "parameter_type": "slot"},
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "dispatch_bot_response": False,
                        "tls": False
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            assert processor.edit_email_action(email_config, "TEST", "tests") is None

        email_config["custom_text"] = {"value": "custom_text_slot", "parameter_type": "slot"}
        email_config["dispatch_bot_response"] = True
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            assert processor.edit_email_action(email_config, "TEST", "tests") is None

    def test_edit_email_action_validation_error(self):
        processor = MongoProcessor()
        email_config = {"action_name": "email_config",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": None,
                        "smtp_password": {'value': "test"},
                        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
                        "to_email": {"value": "to_email", "parameter_type": "slot"},
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "dispatch_bot_response": True,
                        "tls": False
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            mock_smtp.return_value = Exception()
            with pytest.raises(ValidationError, match="Invalid SMTP url"):
                processor.edit_email_action(email_config, "TEST", "tests")

        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            temp = email_config['action_name']
            email_config['action_name'] = ""
            with pytest.raises(AppException, match='Action with name "" not found'):
                processor.edit_email_action(email_config, "TEST", "tests")
            email_config['action_name'] = temp

            temp = email_config['smtp_url']
            email_config['smtp_url'] = ""
            with pytest.raises(ValidationError, match="URL cannot be empty"):
                processor.edit_email_action(email_config, "TEST", "tests")
            email_config['smtp_url'] = temp

            temp = email_config['from_email']
            email_config['from_email'] = {"value": "test@demo", "parameter_type": "value"}
            with pytest.raises(ValidationError, match="Invalid From or To email address"):
                processor.edit_email_action(email_config, "TEST", "tests")

            email_config['from_email'] = {"value": "", "parameter_type": "slot"}
            with pytest.raises(ValidationError, match="Provide name of the slot as value"):
                processor.edit_email_action(email_config, "TEST", "tests")
            email_config['from_email'] = temp

            temp = email_config['to_email']
            email_config['to_email'] = {"value": "test@test", "parameter_type": "value"}
            with pytest.raises(ValidationError, match="Provide list of emails as value"):
                processor.edit_email_action(email_config, "TEST", "tests")

            email_config['to_email'] = {"value": ["test@test"], "parameter_type": "value"}
            with pytest.raises(ValidationError, match="Invalid From or To email address"):
                processor.edit_email_action(email_config, "TEST", "tests")

            email_config['to_email'] = {"value": "", "parameter_type": "slot"}
            with pytest.raises(ValidationError, match="Provide name of the slot as value"):
                processor.edit_email_action(email_config, "TEST", "tests")
            email_config['to_email'] = temp

    def test_edit_email_action_does_not_exist(self):
        processor = MongoProcessor()
        email_config = {"action_name": "email_config1",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": None,
                        "smtp_password": {'value': "test"},
                        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
                        "to_email": {"value": "to_email", "parameter_type": "slot"},
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "tls": False
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            with pytest.raises(AppException, match='Action with name "email_config1" not found'):
                processor.edit_email_action(email_config, "TEST", "tests")

    def test_list_email_actions(self):
        processor = MongoProcessor()
        assert len(list(processor.list_email_action("TEST"))) == 2

    def test_list_email_actions_with_default_value(self):
        processor = MongoProcessor()
        email_actions = list(processor.list_email_action("TEST"))
        email_actions[0].pop('_id')
        assert email_actions[0]['action_name'] == 'email_config'
        assert email_actions[0]['smtp_url'] == 'test.test.com'
        assert email_actions[0]['smtp_port'] == 25

    def test_list_email_actions_with_false(self):
        processor = MongoProcessor()
        email_actions = list(processor.list_email_action("TEST", False))
        assert email_actions[0].get('_id') is None
        assert email_actions[0]['action_name'] == 'email_config'
        assert email_actions[0]['smtp_url'] == 'test.test.com'
        assert email_actions[0]['smtp_port'] == 25

    def test_add_google_search_action(self, monkeypatch):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'google_custom_search',
            'api_key': {'value': '12345678'},
            'search_engine_id': 'asdfg:123456', "dispatch_response": False, "set_slot": "google_search_result",
            'failure_response': 'I have failed to process your request',
            'website': 'https://www.google.com',
        }
        action2 = {
            'name': 'google_custom_search2',
            'api_key': {'value': '12345678'},
            'search_term':{"parameter_type":"slot","value":"subject"},
            'search_engine_id': 'asdfg:123456', "dispatch_response": False, "set_slot": "google_search_result",
            'failure_response': 'I have failed to process your request',
            'website': 'https://www.google.com',
        }
        assert processor.add_google_search_action(action, bot, user)
        assert Actions.objects(name='google_custom_search', status=True, bot=bot).get()
        assert GoogleSearchAction.objects(name='google_custom_search', status=True, bot=bot).get()
        assert processor.add_google_search_action(action2, bot, user)
        assert Actions.objects(name='google_custom_search2', status=True, bot=bot).get()
        assert GoogleSearchAction.objects(name='google_custom_search2', status=True, bot=bot).get()

        GoogleSearchAction.objects(name='google_custom_search2', status=True, bot=bot).delete()
        Actions.objects(name='google_custom_search2', status=True, bot=bot).delete()



        def __mock_get_slots(*args, **kwargs):
            return "some_mock_value"

        monkeypatch.setattr(BaseQuerySet, "get", __mock_get_slots)
        with pytest.raises(AppException, match=re.escape("Slot is attached to action: ['google_custom_search']")):
            processor.delete_slot("google_search_result", bot, user)

    def test_add_google_search_action_with_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "google_custom_search", "type": "GOOGLE_SEARCH_ACTION"},
        ]
        story_dict = {'name': "story with google action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with google action", bot=bot,
                                events__name='google_custom_search', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'story with google action']
        assert story_with_form[0]['steps'] == [
            {'name': 'greet', 'type': 'INTENT'},
            {'name': 'google_custom_search', 'type': 'GOOGLE_SEARCH_ACTION'},
        ]
        processor.delete_complex_story(story_id, 'STORY', bot, user)

    def test_add_google_search_action_duplicate(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'google_custom_search',
            'api_key': {'value': '12345678'},
            'search_engine_id': 'asdfg:123456',
            'failure_response': 'I have failed to process your request',
        }
        with pytest.raises(AppException, match='Action exists!'):
            processor.add_google_search_action(action, bot, user)
        assert Actions.objects(name='google_custom_search', status=True, bot=bot).get()
        assert GoogleSearchAction.objects(name='google_custom_search', status=True, bot=bot).get()

    def test_add_google_search_action_existing_name(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        action = {
            'name': 'test_action',
            'api_key': {'value': '12345678'},
            'search_engine_id': 'asdfg:123456',
            'failure_response': 'I have failed to process your request',
        }
        with pytest.raises(AppException, match='Action exists!'):
            processor.add_google_search_action(action, bot, user)
        assert Actions.objects(name='test_action', status=True, bot=bot).get()

    def test_list_google_search_action_masked(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.list_google_search_actions(bot))
        actions[0].pop('_id')
        assert actions[1]['name'] == 'google_custom_search'
        assert actions[1]['api_key'] == {'_cls': 'CustomActionRequestParameters', 'encrypt': False, 'key': 'api_key',
                                         'parameter_type': 'value', 'value': '12345678'}
        assert actions[1]['search_engine_id'] == 'asdfg:123456'
        assert actions[1]['failure_response'] == 'I have failed to process your request'
        assert actions[1]['website'] == 'https://www.google.com'
        assert actions[1]['num_results'] == 1
        assert not actions[1]['dispatch_response']
        assert actions[1]['set_slot'] == "google_search_result"

    def test_edit_google_search_action_not_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'custom_search',
            'api_key': {'value': '12345678'},
            'search_engine_id': 'asdfg:123456',
            'failure_response': 'I have failed to process your request',
        }
        with pytest.raises(AppException, match='Google search action with name "custom_search" not found'):
            processor.edit_google_search_action(action, bot, user)
        assert Actions.objects(name='google_custom_search', status=True, bot=bot).get()
        assert GoogleSearchAction.objects(name='google_custom_search', status=True, bot=bot).get()

    def test_edit_google_search_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action0 = {
            'name': 'google_custom_search',
            'api_key': {'value': '1234567889'},
            'search_engine_id': 'asdfg:12345689',
            'failure_response': 'Failed to perform search',
            'website': 'https://nimblework.com',
            "search_term": {"parameter_type": "slot", "value": "subject"}
        }

        assert not processor.edit_google_search_action(action0, bot, user)
        val = GoogleSearchAction.objects(name='google_custom_search', status=True, bot=bot).get()
        assert val
        assert val.search_term
        action = {
            'name': 'google_custom_search',
            'api_key': {'value': '1234567889'},
            'search_engine_id': 'asdfg:12345689',
            'failure_response': 'Failed to perform search',
            'website': 'https://nimblework.com',
        }
        assert not processor.edit_google_search_action(action, bot, user)
        assert Actions.objects(name='google_custom_search', status=True, bot=bot).get()
        val =  GoogleSearchAction.objects(name='google_custom_search', status=True, bot=bot).get()
        assert val
        assert not val.search_term


    def test_list_google_search_action(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.list_google_search_actions(bot, False))
        assert actions[1].get('_id') is None
        assert actions[1]['name'] == 'google_custom_search'
        assert actions[1]['api_key'] == {'_cls': 'CustomActionRequestParameters', 'encrypt': False, 'key': 'api_key',
                                         'parameter_type': 'value', 'value': '1234567889'}
        assert actions[1]['search_engine_id'] == 'asdfg:12345689'
        assert actions[1]['failure_response'] == 'Failed to perform search'
        assert actions[1]['website'] == 'https://nimblework.com'
        assert actions[1]['num_results'] == 1
        assert actions[1]['dispatch_response']
        assert not actions[1].get('set_slot')

    def test_delete_google_search_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        processor.delete_action('google_custom_search', bot, user)
        with pytest.raises(DoesNotExist):
            Actions.objects(name='google_custom_search', status=True, bot=bot).get()
        with pytest.raises(DoesNotExist):
            GoogleSearchAction.objects(name='google_custom_search', status=True, bot=bot).get()

    def test_add_web_search_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        slot_name = "public_search_result"
        action = {
            'name': 'public_custom_search',
            "dispatch_response": False, "set_slot": "public_search_result",
            'failure_response': 'I have failed to process your request',
            'website': 'https://www.google.com',
        }
        slot = {"name": slot_name, "type": "any", "initial_value": None, "influence_conversation": True}
        processor.add_slot(slot_value=slot, bot=bot, user=user)
        assert processor.add_web_search_action(action, bot, user)
        assert Actions.objects(name='public_custom_search', status=True, bot=bot).get()
        assert WebSearchAction.objects(name='public_custom_search', status=True, bot=bot).get()
        with pytest.raises(AppException,
                           match=re.escape("Slot is attached to action: ['public_custom_search']")):
            processor.delete_slot("public_search_result", bot, user)

    def test_add_web_search_action_with_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "public_custom_search", "type": "WEB_SEARCH_ACTION"},
        ]
        story_dict = {'name': "story with web search action", 'steps': steps, 'type': 'STORY',
                      'template_type': 'CUSTOM'}
        story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with web search action", bot=bot,
                                events__name='public_custom_search', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form_web = [s for s in stories if s['name'] == 'story with web search action']
        assert story_with_form_web[0]['steps'] == [
            {'name': 'greet', 'type': 'INTENT'},
            {'name': 'public_custom_search', 'type': 'WEB_SEARCH_ACTION'},
        ]
        processor.delete_complex_story(story_id, 'STORY', bot, user)

    def test_add_web_search_action_with_empty_name(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': ' ',
            "dispatch_response": False, "set_slot": "",
            'failure_response': 'I have failed to process your request',
            'website': 'https://www.google.com',
        }
        with pytest.raises(ValidationError, match="Action name cannot be empty"):
            processor.add_web_search_action(action, bot, user)

    def test_add_web_search_action_with_invalid_top_n(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'public_search_action_with_invalid_top_n',
            "dispatch_response": False, "set_slot": "", 'topn': 0,
            'failure_response': 'I have failed to process your request',
            'website': 'https://www.google.com',
        }
        with pytest.raises(ValidationError, match="topn must be greater than or equal to 1!"):
            processor.add_web_search_action(action, bot, user)

    def test_add_web_search_action_duplicate(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'public_custom_search',
            "dispatch_response": False, "set_slot": "public_search_result",
            'failure_response': 'I have failed to process your request',
            'website': 'https://www.google.com',
        }
        with pytest.raises(AppException, match='Action exists!'):
            processor.add_web_search_action(action, bot, user)
        assert Actions.objects(name='public_custom_search', status=True, bot=bot).get()
        assert WebSearchAction.objects(name='public_custom_search', status=True, bot=bot).get()

    def test_list_web_search_action_masked(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.list_web_search_actions(bot))
        actions[0].pop('_id')
        assert actions[0]['name'] == 'public_custom_search'
        assert actions[0]['failure_response'] == 'I have failed to process your request'
        assert actions[0]['website'] == 'https://www.google.com'
        assert actions[0]['topn'] == 1
        assert not actions[0]['dispatch_response']
        assert actions[0]['set_slot'] == "public_search_result"

    def test_edit_web_search_action_not_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'custom_search',
            'failure_response': 'I have failed to process your request',
        }
        with pytest.raises(AppException, match='Public search action with name "custom_search" not found'):
            processor.edit_web_search_action(action, bot, user)
        assert Actions.objects(name='public_custom_search', status=True, bot=bot).get()
        assert WebSearchAction.objects(name='public_custom_search', status=True, bot=bot).get()

    def test_edit_web_search_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'public_custom_search',
            "dispatch_response": False, "set_slot": "public_search_result",
            'failure_response': 'Failed to perform public search',
            'website': 'https://nimblework.com',
        }
        assert not processor.edit_web_search_action(action, bot, user)
        assert Actions.objects(name='public_custom_search', status=True, bot=bot).get()
        assert WebSearchAction.objects(name='public_custom_search', status=True, bot=bot).get()

    def test_list_web_search_action(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.list_web_search_actions(bot, False))
        assert actions[0].get('_id') is None
        assert actions[0]['name'] == 'public_custom_search'
        assert actions[0]['failure_response'] == 'Failed to perform public search'
        assert actions[0]['website'] == 'https://nimblework.com'
        assert actions[0]['topn'] == 1
        assert not actions[0]['dispatch_response']
        assert actions[0].get('set_slot')

    def test_delete_web_search_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        processor.delete_action('public_custom_search', bot, user)
        with pytest.raises(DoesNotExist):
            Actions.objects(name='public_custom_search', status=True, bot=bot).get()
        with pytest.raises(DoesNotExist):
            WebSearchAction.objects(name='public_custom_search', status=True, bot=bot).get()

    def test_add_hubspot_forms_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'action_hubspot_forms',
            'portal_id': '12345678',
            'form_guid': 'asdfg:123456',
            'fields': [
                {"key": 'email', 'value': 'email_slot', 'parameter_type': 'slot'},
                {"key": 'firstname', 'value': 'firstname_slot', 'parameter_type': 'slot'}
            ],
            'response': 'Form submitted'
        }
        assert processor.add_hubspot_forms_action(action, bot, user)
        assert Actions.objects(name='action_hubspot_forms', status=True, bot=bot).get()
        assert HubspotFormsAction.objects(name='action_hubspot_forms', status=True, bot=bot).get()

    def test_add_hubspot_forms_action_with_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "action_hubspot_forms", "type": "HUBSPOT_FORMS_ACTION"},
        ]
        story_dict = {'name': "story with hubspot form action", 'steps': steps, 'type': 'STORY',
                      'template_type': 'CUSTOM'}
        story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with hubspot form action", bot=bot,
                                events__name='action_hubspot_forms', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'story with hubspot form action']
        assert story_with_form[0]['steps'] == [
            {'name': 'greet', 'type': 'INTENT'},
            {'name': 'action_hubspot_forms', 'type': 'HUBSPOT_FORMS_ACTION'},
        ]
        processor.delete_complex_story(story_id, 'STORY', bot, user)

    def test_add_hubspot_forms_action_duplicate(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'action_hubspot_forms',
            'portal_id': '12345678',
            'form_guid': 'asdfg:123456',
            'fields': [
                {"key": 'email', 'value': 'email_slot', 'parameter_type': 'slot'},
                {"key": 'firstname', 'value': 'firstname_slot', 'parameter_type': 'slot'}
            ]
        }
        with pytest.raises(AppException, match='Action exists!'):
            processor.add_hubspot_forms_action(action, bot, user)
        assert Actions.objects(name='action_hubspot_forms', status=True, bot=bot).get()
        assert HubspotFormsAction.objects(name='action_hubspot_forms', status=True, bot=bot).get()

    def test_add_hubspot_forms_action_existing_name(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        action = {
            'name': 'test_action',
            'portal_id': '12345678',
            'form_guid': 'asdfg:123456',
            'fields': [
                {"key": 'email', 'value': 'email_slot', 'parameter_type': 'slot'},
                {"key": 'firstname', 'value': 'firstname_slot', 'parameter_type': 'slot'}
            ]
        }
        with pytest.raises(AppException, match='Action exists!'):
            processor.add_hubspot_forms_action(action, bot, user)
        assert Actions.objects(name='test_action', status=True, bot=bot).get()

    def test_edit_hubspot_forms_action_not_exists(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        action = {
            'name': 'test_action',
            'portal_id': '12345678',
            'form_guid': 'asdfg:123456',
            'fields': [
                {"key": 'email', 'value': 'email_slot', 'parameter_type': 'slot'},
                {"key": 'firstname', 'value': 'firstname_slot', 'parameter_type': 'slot'}
            ]
        }
        with pytest.raises(AppException, match=f'Action with name "{action.get("name")}" not found'):
            processor.edit_hubspot_forms_action(action, bot, user)

    def test_edit_hubspot_forms_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'action_hubspot_forms',
            'portal_id': '123456785787',
            'form_guid': 'asdfg:12345678787',
            'fields': [
                {"key": 'email', 'value': 'email_slot', 'parameter_type': 'slot'},
                {"key": 'fullname', 'value': 'fullname_slot', 'parameter_type': 'slot'},
                {"key": 'company', 'value': 'digite', 'parameter_type': 'value'},
                {"key": 'phone', 'value': 'phone_slot', 'parameter_type': 'slot'}
            ],
            'response': 'Hubspot Form submitted'
        }
        assert not processor.edit_hubspot_forms_action(action, bot, user)
        assert Actions.objects(name='action_hubspot_forms', status=True, bot=bot).get()
        assert HubspotFormsAction.objects(name='action_hubspot_forms', status=True, bot=bot).get()

    def test_list_hubspot_forms_action(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.list_hubspot_forms_actions(bot))
        assert actions[0]['name'] == 'action_hubspot_forms'
        assert actions[0]['portal_id'] == '123456785787'
        assert actions[0]['form_guid'] == 'asdfg:12345678787'
        assert actions[0]['fields'] == [
            {'_cls': 'HttpActionRequestBody', 'key': 'email', 'value': 'email_slot', 'parameter_type': 'slot',
             'encrypt': False},
            {'_cls': 'HttpActionRequestBody', 'key': 'fullname', 'value': 'fullname_slot', 'parameter_type': 'slot',
             'encrypt': False},
            {'_cls': 'HttpActionRequestBody', 'key': 'company', 'value': 'digite', 'parameter_type': 'value',
             'encrypt': False},
            {'_cls': 'HttpActionRequestBody', 'key': 'phone', 'value': 'phone_slot', 'parameter_type': 'slot',
             'encrypt': False}]
        assert actions[0]['response'] == 'Hubspot Form submitted'

    def test_list_hubspot_forms_action_with_false(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.list_hubspot_forms_actions(bot, False))
        assert actions[0].get('_id') is None
        assert actions[0]['name'] == 'action_hubspot_forms'
        assert actions[0]['portal_id'] == '123456785787'
        assert actions[0]['form_guid'] == 'asdfg:12345678787'
        assert actions[0]['fields'] == [
            {'_cls': 'HttpActionRequestBody', 'key': 'email', 'value': 'email_slot', 'parameter_type': 'slot',
             'encrypt': False},
            {'_cls': 'HttpActionRequestBody', 'key': 'fullname', 'value': 'fullname_slot', 'parameter_type': 'slot',
             'encrypt': False},
            {'_cls': 'HttpActionRequestBody', 'key': 'company', 'value': 'digite', 'parameter_type': 'value',
             'encrypt': False},
            {'_cls': 'HttpActionRequestBody', 'key': 'phone', 'value': 'phone_slot', 'parameter_type': 'slot',
             'encrypt': False}]
        assert actions[0]['response'] == 'Hubspot Form submitted'

    def test_delete_hubspot_forms_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        processor.delete_action('action_hubspot_forms', bot, user)
        with pytest.raises(DoesNotExist):
            Actions.objects(name='action_hubspot_forms', status=True, bot=bot).get()
        with pytest.raises(DoesNotExist):
            HubspotFormsAction.objects(name='action_hubspot_forms', status=True, bot=bot).get()

    def test_add_hubspot_forms_action_reserved_keyword(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        action = {
            'name': KAIRON_TWO_STAGE_FALLBACK,
            'portal_id': '12345678',
            'form_guid': 'asdfg:123456',
            'fields': [
                {"key": 'email', 'value': 'email_slot', 'parameter_type': 'slot'},
                {"key": 'firstname', 'value': 'firstname_slot', 'parameter_type': 'slot'}
            ]
        }
        with pytest.raises(AppException, match=f"{KAIRON_TWO_STAGE_FALLBACK} is a reserved keyword"):
            processor.add_hubspot_forms_action(action, bot, user)

    def test_list_all_actions(self):
        bot = 'test_bot'
        user = 'test_user'
        action = "test_list_all_action_pyscript_action"
        script = "bot_response='hello world'"
        processor = MongoProcessor()
        pyscript_config = PyscriptActionRequest(
            name=action,
            source_code=script,
            dispatch_response=False,
        )
        action_id = processor.add_pyscript_action(pyscript_config.model_dump(), user, bot)

        action = {
            'name': 'test_list_all_action_google_action',
            'api_key': {'value': '12345678'},
            'search_engine_id': 'asdfg:123456', "dispatch_response": False, "set_slot": "google_search_result",
            'failure_response': 'I have failed to process your request',
            'website': 'https://www.google.com',
        }
        action_id = processor.add_google_search_action(action, bot, user)

        actions_list = list(processor.list_all_actions(bot=bot))
        assert actions_list[-1]['name'] == 'test_list_all_action_google_action'
        assert actions_list[-2]['name'] == 'test_list_all_action_pyscript_action'


    def test_add_custom_2_stage_fallback_action_validation_error(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        request = {"trigger_rules": None, "text_recommendations": None}
        with pytest.raises(ValidationError):
            processor.add_two_stage_fallback_action(request, bot, user)

    def test_add_custom_2_stage_fallback_action_recommendations_only(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        request = {"fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                                       " Or else please rephrase your question.",
                   "trigger_rules": None,
                   "text_recommendations": {"count": 3, "use_intent_ranking": True}}
        processor.add_two_stage_fallback_action(request, bot, user)
        assert Actions.objects(name=KAIRON_TWO_STAGE_FALLBACK, bot=bot).get()
        config = list(processor.get_two_stage_fallback_action_config(bot, KAIRON_TWO_STAGE_FALLBACK))
        assert config[0].get("timestamp") is None
        config[0].pop("_id")
        assert config == [{'name': 'kairon_two_stage_fallback',
                           'text_recommendations': {"count": 3, "use_intent_ranking": True}, 'trigger_rules': [],
                           "fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                                               " Or else please rephrase your question."}]

    def test_add_custom_2_stage_fallback_action_with_false(self):
        processor = MongoProcessor()
        bot = 'test'
        assert Actions.objects(name=KAIRON_TWO_STAGE_FALLBACK, bot=bot).get()
        config = list(processor.get_two_stage_fallback_action_config(bot, KAIRON_TWO_STAGE_FALLBACK, False))
        assert config[0].get("timestamp") is None
        assert config[0].get("_id") is None
        assert config == [{'name': 'kairon_two_stage_fallback',
                           'text_recommendations': {"count": 3, "use_intent_ranking": True}, 'trigger_rules': [],
                           "fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                                               " Or else please rephrase your question."}]

    def test_add_custom_2_stage_fallback_action_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        request = {"trigger_rules": None, "text_recommendations": {"count": 3}}
        with pytest.raises(AppException, match="Action exists!"):
            processor.add_two_stage_fallback_action(request, bot, user)

    def test_add_custom_2_stage_fallback_action_rules_not_found(self):
        processor = MongoProcessor()
        bot = 'test_add_custom_2_stage_fallback_action_rules_not_found'
        user = 'test_user'
        request = {"trigger_rules": [{"text": "Mail me", "payload": "send_mail"},
                                     {"text": "Contact me", "payload": "call"}]}
        with pytest.raises(AppException, match=r"Intent {.+} do not exist in the bot"):
            processor.add_two_stage_fallback_action(request, bot, user)

    def test_add_custom_2_stage_fallback_action_rules_only(self):
        processor = MongoProcessor()
        bot = 'test_add_custom_2_stage_fallback_action_rules_only'
        user = 'test_user'
        request = {"fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                                       " Or else please rephrase your question.",
                   "trigger_rules": [{"text": "Mail me", "payload": "greet"},
                                     {"text": "Contact me", "payload": "call"}]}
        processor.add_intent("greet", bot, user, False)
        processor.add_intent("call", bot, user, False)
        processor.add_two_stage_fallback_action(request, bot, user)
        assert Actions.objects(name=KAIRON_TWO_STAGE_FALLBACK, bot=bot).get()
        config = list(processor.get_two_stage_fallback_action_config(bot, KAIRON_TWO_STAGE_FALLBACK))
        assert config[0].get("timestamp") is None
        config[0].pop("_id")
        assert config == [{'name': 'kairon_two_stage_fallback',
                           'trigger_rules': [{'text': 'Mail me', 'payload': 'greet', 'is_dynamic_msg': False},
                                             {'text': 'Contact me', 'payload': 'call', 'is_dynamic_msg': False}],
                           "fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                                               " Or else please rephrase your question."}]

    def test_add_custom_2_stage_fallback_action_with_user_message(self):
        processor = MongoProcessor()
        bot = 'test_add_custom_2_stage_fallback_action_with_static_user_message'
        user = 'test_user'
        request = {"fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                                       " Or else please rephrase your question.",
                   "trigger_rules": [
                       {"text": "Mail me", "payload": "greet", "message": "my payload", "is_dynamic_msg": True},
                       {"text": "Contact me", "payload": "call", "message": None, "is_dynamic_msg": False}]}
        processor.add_intent("greet", bot, user, False)
        processor.add_intent("call", bot, user, False)
        processor.add_two_stage_fallback_action(request, bot, user)
        assert Actions.objects(name=KAIRON_TWO_STAGE_FALLBACK, bot=bot).get()
        config = list(processor.get_two_stage_fallback_action_config(bot, KAIRON_TWO_STAGE_FALLBACK))
        assert config[0].get("timestamp") is None
        config[0].pop("_id")
        assert config == [{'name': 'kairon_two_stage_fallback', 'trigger_rules': [
            {'text': 'Mail me', 'payload': 'greet', 'message': 'my payload', 'is_dynamic_msg': True},
            {'text': 'Contact me', 'payload': 'call', 'is_dynamic_msg': False}],
                           "fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                                               " Or else please rephrase your question."}]

    def test_edit_custom_2_stage_fallback_action_not_found(self):
        processor = MongoProcessor()
        bot = 'test_edit_custom_2_stage_fallback_action_not_found'
        user = 'test_user'
        request = {"trigger_rules": None, "text_recommendations": {"count": 3}}
        with pytest.raises(AppException, match=f'Action with name "{KAIRON_TWO_STAGE_FALLBACK}" not found'):
            processor.edit_two_stage_fallback_action(request, bot, user)

    def test_get_2_stage_fallback_action_not_found(self):
        processor = MongoProcessor()
        bot = 'test_edit_custom_2_stage_fallback_action_not_found'
        assert list(processor.get_two_stage_fallback_action_config(bot)) == []

    def test_edit_custom_2_stage_fallback_action_recommendations_only(self):
        processor = MongoProcessor()
        bot = 'test_add_custom_2_stage_fallback_action_rules_only'
        user = 'test_user'
        request = {"fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                                       " Or else please rephrase your question.", "trigger_rules": None,
                   "text_recommendations": {"count": 3}}
        processor.edit_two_stage_fallback_action(request, bot, user)
        assert Actions.objects(name=KAIRON_TWO_STAGE_FALLBACK, bot=bot).get()
        config = list(processor.get_two_stage_fallback_action_config(bot, KAIRON_TWO_STAGE_FALLBACK))
        assert config[0].get("timestamp") is None
        config[0].pop("_id")
        assert config == [{'name': 'kairon_two_stage_fallback',
                           'text_recommendations': {"count": 3, "use_intent_ranking": False},
                           'trigger_rules': [],
                           "fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                                               " Or else please rephrase your question."}]

    def test_edit_custom_2_stage_fallback_action_rules_only(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        request = {"fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                                       " Or else please rephrase your question.",
                   "trigger_rules": [
                       {"text": "Mail me", "payload": "send_mail", 'message': 'my payload', 'is_dynamic_msg': False},
                       {"text": "Contact me", "payload": "call", "is_dynamic_msg": True}]}
        processor.add_intent("send_mail", bot, user, False)
        processor.add_intent("call", bot, user, False)
        processor.edit_two_stage_fallback_action(request, bot, user)
        assert Actions.objects(name=KAIRON_TWO_STAGE_FALLBACK, bot=bot).get()
        config = list(processor.get_two_stage_fallback_action_config(bot, KAIRON_TWO_STAGE_FALLBACK))
        assert config[0].get("timestamp") is None
        config[0].pop("_id")
        assert config == [{'name': 'kairon_two_stage_fallback', 'trigger_rules': [
            {'text': 'Mail me', 'payload': 'send_mail', 'message': 'my payload', 'is_dynamic_msg': False},
            {'text': 'Contact me', 'payload': 'call', 'is_dynamic_msg': True}],
                           "fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                                               " Or else please rephrase your question."}]

    def test_edit_custom_2_stage_fallback_action_rules_not_found(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        request = {"trigger_rules": [{"text": "DM me", "payload": "send_dm"}]}

        with pytest.raises(AppException, match=f"Intent {set(['send_dm'])} do not exist in the bot"):
            processor.edit_two_stage_fallback_action(request, bot, user)

    def test_delete_2_stage_fallback_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        processor.delete_complex_story(pytest.two_stage_fallback_story_id, "RULE", bot, user)
        processor.delete_action(KAIRON_TWO_STAGE_FALLBACK, bot, user)
        with pytest.raises(DoesNotExist):
            Actions.objects(name=KAIRON_TWO_STAGE_FALLBACK, status=True, bot=bot).get()

    def test_create_kairon_faq_action_rule(self):
        processor = MongoProcessor()
        bot = 'test_create_kairon_faq_action_rule'
        user = 'test_user'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "kairon_faq_action", "type": "PROMPT_ACTION"}
        ]
        request = {'name': steps[1]["name"],
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()
        processor.add_prompt_action(request, bot, user)

        story_dict = {'name': "activate kairon faq action", 'steps': steps, 'type': 'RULE', 'template_type': 'CUSTOM'}
        pytest.two_stage_fallback_story_id = processor.add_complex_story(story_dict, bot, user)
        rule = Rules.objects(block_name="activate kairon faq action", bot=bot,
                             events__name="kairon_faq_action", status=True).get()
        assert rule.to_mongo().to_dict()['events'] == [{'name': '...', 'type': 'action'},
                                                       {'name': 'greet', 'type': 'user'},
                                                       {'name': "kairon_faq_action", 'type': 'action'}]
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == "activate kairon faq action"]
        assert story_with_form[0]['steps'] == [
            {"name": "greet", "type": "INTENT"},
            {"name": "kairon_faq_action", "type": "PROMPT_ACTION"}
        ]

        LLMSecret.objects.delete()

    def test_add_secret(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        key = "AWS_KEY"
        value = "123456789-0dfghjk"
        id = processor.add_secret(key, value, bot, user)
        assert not Utility.check_empty_string(id)
        key_value = KeyVault.objects().get(id=id)
        assert key_value.key == key
        assert value == Utility.decrypt_message(key_value.value)

    def test_add_secret_already_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        key = "AWS_KEY"
        value = "123456789-0dfghjk"
        with pytest.raises(AppException, match="Key exists!"):
            processor.add_secret(key, value, bot, user)

    def test_add_secret_empty_value(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        key = "GOOGLE_KEY"
        value = None
        with pytest.raises(ValidationError):
            processor.add_secret(key, value, bot, user)

        key = None
        value = "sdfghj567"
        with pytest.raises(ValidationError):
            processor.add_secret(key, value, bot, user)

    def test_get_secret_after_addition(self):
        processor = MongoProcessor()
        bot = 'test'
        key = "AWS_KEY"
        assert processor.get_secret(key, bot) == "123456789-0dfghjk"

    def test_list_keys(self):
        processor = MongoProcessor()
        bot = 'test'
        assert ["AWS_KEY"] == processor.list_secrets(bot)

    def test_update_secret(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        key = "AWS_KEY"
        value = "123456789-0dfghjkdfghj"
        id = processor.update_secret(key, value, bot, user)
        assert not Utility.check_empty_string(id)
        key_value = KeyVault.objects().get(id=id)
        assert key_value.key == key
        assert value == Utility.decrypt_message(key_value.value)

    def test_update_secret_not_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        key = "GCP_KEY"
        value = "123456789-0dfghjkdfghj"
        with pytest.raises(AppException, match=f"key '{key}' does not exists!"):
            processor.update_secret(key, value, bot, user)

    def test_update_secret_empty_value(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        key = "AWS_KEY"
        value = None
        with pytest.raises(ValidationError):
            processor.update_secret(key, value, bot, user)

    def test_get_secret_after_update(self):
        processor = MongoProcessor()
        bot = 'test'
        key = "AWS_KEY"
        assert "123456789-0dfghjkdfghj" == processor.get_secret(key, bot)

    def test_delete_secret(self):
        processor = MongoProcessor()
        bot = 'test'
        key = "AWS_KEY"
        processor.delete_secret(key, bot, user="test")
        with pytest.raises(DoesNotExist):
            KeyVault.objects(key=key, bot=bot).get()

    def test_delete_secret_not_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        key = "GCPKEY"
        with pytest.raises(AppException, match=f"key '{key}' does not exists!"):
            processor.delete_secret(key, bot, user="test")

    def test_get_secret_not_found(self):
        processor = MongoProcessor()
        bot = 'test'
        key = "GOOGLE_KEY"
        with pytest.raises(AppException, match=f"key '{key}' does not exists!"):
            processor.get_secret(key, bot)

    def test_get_secret_no_error(self):
        processor = MongoProcessor()
        bot = 'test'
        key = "GOOGLE_KEY"
        assert None is processor.get_secret(key, bot, False)

    def test_list_keys_empty(self):
        processor = MongoProcessor()
        bot = 'test'
        assert [] == processor.list_secrets(bot)

    def test_delete_secret_attached_to_http_action(self):
        bot = 'test'
        key = "GCPKEY"
        user = "user"
        value = "123456789-0dfghjk"
        processor = MongoProcessor()
        processor.add_secret(key, value, bot, user)
        http_params_list = [HttpActionRequestBody(key="param1", value="param1", parameter_type="slot"),
                            HttpActionRequestBody(key="param2", value=key, parameter_type="key_vault")]
        HttpActionConfig(
            action_name="test_delete_secret_attached_to_http_action",
            response=HttpActionResponse(value="action executed!"),
            http_url="http://kairon.digite.com/get/all",
            request_method="POST",
            params_list=http_params_list,
            bot=bot,
            user=user
        ).save()
        with pytest.raises(AppException, match=re.escape(
                "Key is attached to action: ['test_delete_secret_attached_to_http_action']")):
            processor.delete_secret(key, bot, user="test")

        action = HttpActionConfig.objects(action_name="test_delete_secret_attached_to_http_action", bot=bot).get()
        action.params_list = []
        action.headers = http_params_list
        action.save()
        with pytest.raises(AppException, match=re.escape(
                "Key is attached to action: ['test_delete_secret_attached_to_http_action']")):
            processor.delete_secret(key, bot, user=user)

        action = HttpActionConfig.objects(action_name="test_delete_secret_attached_to_http_action", bot=bot).get()
        action.params_list = []
        action.headers = [HttpActionRequestBody(key="param1", value="param1", parameter_type="key_vault"),
                          HttpActionRequestBody(key="param2", value=key, parameter_type="value")]
        action.save()
        processor.delete_secret(key, bot, user=user)
        with pytest.raises(DoesNotExist):
            KeyVault.objects(key=key, bot=bot).get()

    def test_delete_secret_attached_to_email_action(self):
        bot = 'test'
        key = "KUBKEY"
        user = "user"
        value = "1526473-nxndj"
        processor = MongoProcessor()
        processor.add_secret(key, value, bot, user)
        smtp_userid_list = CustomActionRequestParameters(key="smtp_userid", value=key, parameter_type="key_vault")
        email_config = {"action_name": "test_delete_secret_attached_to_email_action",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": smtp_userid_list,
                        "smtp_password": {'value': "test"},
                        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
                        "to_email": {"value": "to_email", "parameter_type": "slot"},
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "tls": False
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True):
            processor.add_email_action(email_config, bot, user)
        with pytest.raises(AppException, match=re.escape(
                "Key is attached to action: ['test_delete_secret_attached_to_email_action']")):
            processor.delete_secret(key, bot, user="test")

        action = EmailActionConfig.objects(action_name="test_delete_secret_attached_to_email_action", bot=bot).get()
        action.smtp_userid = None
        action.smtp_password = smtp_userid_list
        with patch("kairon.shared.utils.SMTP", autospec=True):
            action.save()
        with pytest.raises(AppException, match=re.escape(
                "Key is attached to action: ['test_delete_secret_attached_to_email_action']")):
            processor.delete_secret(key, bot, user=user)

        action = EmailActionConfig.objects(action_name="test_delete_secret_attached_to_email_action", bot=bot).get()
        action.smtp_userid = None
        action.smtp_password = CustomActionRequestParameters(key="param2", value="param2", parameter_type="key_vault")
        with patch("kairon.shared.utils.SMTP", autospec=True):
            action.save()
        processor.delete_secret(key, bot, user=user)
        with pytest.raises(DoesNotExist):
            KeyVault.objects(key=key, bot=bot).get()

    def test_delete_secret_attached_to_google_action(self):
        processor = MongoProcessor()
        key = 'AZKEY'
        bot = 'test'
        user = 'test_user'
        value = '7362-jdnsn'
        processor.add_secret(key, value, bot, user)
        api_key_value = {'key': "api_key", 'value': key, 'parameter_type': "key_vault"}
        action = {
            'name': 'test_delete_secret_attached_to_google_action',
            'api_key': api_key_value,
            'search_engine_id': 'asdfg:123456',
            'failure_response': 'I have failed to process your request',
        }
        processor.add_google_search_action(action, bot, user)
        with pytest.raises(AppException, match=re.escape(
                "Key is attached to action: ['test_delete_secret_attached_to_google_action']")):
            processor.delete_secret(key, bot, user=user)

        action = GoogleSearchAction.objects(name="test_delete_secret_attached_to_google_action", bot=bot).get()
        action.api_key = CustomActionRequestParameters(key="param2", value="param2", parameter_type="key_vault")
        action.save()
        processor.delete_secret(key, bot, user=user)
        with pytest.raises(DoesNotExist):
            KeyVault.objects(key=key, bot=bot).get()

    def test_delete_secret_attached_to_jira_action(self):
        processor = MongoProcessor()
        key = 'QSKEY'
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        value = '7039-hffi'
        processor.add_secret(key, value, bot, user)
        api_token_value = {'key': "api_token", 'value': key, 'parameter_type': "key_vault"}
        action = {
            'name': 'test_delete_secret_attached_to_jira_action', 'url': url, 'user_name': 'test@digite.com',
            'api_token': api_token_value, 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
            'response': 'We have logged a ticket'
        }

        def _mock_validation(*args, **kwargs):
            return None

        with patch('kairon.shared.actions.data_objects.JiraAction.validate', new=_mock_validation):
            processor.add_jira_action(action, bot, user)
        with pytest.raises(AppException, match=re.escape(
                "Key is attached to action: ['test_delete_secret_attached_to_jira_action']")):
            processor.delete_secret(key, bot, user=user)

        action = JiraAction.objects(name="test_delete_secret_attached_to_jira_action", bot=bot).get()
        action.api_token = CustomActionRequestParameters(key="param2", value="param2", parameter_type="key_vault")
        with patch('kairon.shared.actions.data_objects.JiraAction.validate', new=_mock_validation):
            action.save()
        processor.delete_secret(key, bot, user=user)
        with pytest.raises(DoesNotExist):
            KeyVault.objects(key=key, bot=bot).get()

    def test_delete_secret_attached_to_zendesk_action(self):
        processor = MongoProcessor()
        key = 'ABKEY'
        bot = 'test'
        user = 'test'
        value = '4327-hssw'
        processor.add_secret(key, value, bot, user)
        api_token_value = {'key': "api_token", 'value': key, 'parameter_type': "key_vault"}
        action = {'name': 'test_delete_secret_attached_to_zendesk_action', 'subdomain': 'digite751',
                  'api_token': api_token_value, 'subject': 'new ticket', 'user_name': 'udit.pandey@digite.com',
                  'response': 'ticket filed'}

        def _mock_validation(*args, **kwargs):
            return None

        with patch('kairon.shared.actions.data_objects.ZendeskAction.validate', new=_mock_validation):
            processor.add_zendesk_action(action, bot, user)
        with pytest.raises(AppException, match=re.escape(
                "Key is attached to action: ['test_delete_secret_attached_to_zendesk_action']")):
            processor.delete_secret(key, bot, user=user)

        action = ZendeskAction.objects(name="test_delete_secret_attached_to_zendesk_action", bot=bot).get()
        action.api_token = CustomActionRequestParameters(key="param2", value="param2", parameter_type="key_vault")
        with patch('kairon.shared.actions.data_objects.ZendeskAction.validate', new=_mock_validation):
            action.save()
        processor.delete_secret(key, bot, user=user)
        with pytest.raises(DoesNotExist):
            KeyVault.objects(key=key, bot=bot).get()

    def test_delete_secret_attached_to_pipedrivelead_action(self):
        processor = MongoProcessor()
        key = 'NKKEY'
        bot = 'test'
        user = 'test_user'
        value = '1518-hshw'
        processor.add_secret(key, value, bot, user)
        api_token_value = {'key': "api_token", 'value': key, 'parameter_type': "key_vault"}
        action = {
            'name': 'test_delete_secret_attached_to_pipedrivelead_action',
            'domain': 'https://digite751.pipedrive.com/',
            'api_token': api_token_value,
            'title': 'new lead',
            'response': 'I have failed to create lead for you',
            'metadata': {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
        }

        def _mock_validation(*args, **kwargs):
            return None

        with patch('kairon.shared.actions.data_objects.PipedriveLeadsAction.validate', new=_mock_validation):
            processor.add_pipedrive_action(action, bot, user)
        with pytest.raises(AppException, match=re.escape(
                "Key is attached to action: ['test_delete_secret_attached_to_pipedrivelead_action']")):
            processor.delete_secret(key, bot, user=user)

        action = PipedriveLeadsAction.objects(name="test_delete_secret_attached_to_pipedrivelead_action", bot=bot).get()
        action.api_token = CustomActionRequestParameters(key="param2", value="param2", parameter_type="key_vault")
        with patch('kairon.shared.actions.data_objects.PipedriveLeadsAction.validate', new=_mock_validation):
            action.save()
        processor.delete_secret(key, bot, user=user)
        with pytest.raises(DoesNotExist):
            KeyVault.objects(key=key, bot=bot).get()

    def test_delete_secret_attached_to_hubspot_action(self):
        processor = MongoProcessor()
        key = 'VPKEY'
        bot = 'test'
        user = 'test_user'
        value = '7728-abcg'
        processor.add_secret(key, value, bot, user)
        fields_list = [HttpActionRequestBody(key="param1", value="param1", parameter_type="slot"),
                       HttpActionRequestBody(key="param2", value=key, parameter_type="key_vault")]
        action = {
            'name': 'test_delete_secret_attached_to_hubspot_action',
            'portal_id': '12345678',
            'form_guid': 'asdfg:123456',
            'fields': fields_list,
            'response': 'Form submitted'
        }

        def _mock_validation(*args, **kwargs):
            return None

        with patch('kairon.shared.actions.data_objects.HubspotFormsAction.validate', new=_mock_validation):
            processor.add_hubspot_forms_action(action, bot, user)
        with pytest.raises(AppException, match=re.escape(
                "Key is attached to action: ['test_delete_secret_attached_to_hubspot_action']")):
            processor.delete_secret(key, bot, user=user)

        action = HubspotFormsAction.objects(name="test_delete_secret_attached_to_hubspot_action", bot=bot).get()
        action.fields = [HttpActionRequestBody(key="param1", value="param1", parameter_type="key_vault"),
                         HttpActionRequestBody(key="param2", value=key, parameter_type="value")]
        with patch('kairon.shared.actions.data_objects.HubspotFormsAction.validate', new=_mock_validation):
            action.save()
        processor.delete_secret(key, bot, user=user)
        with pytest.raises(DoesNotExist):
            KeyVault.objects(key=key, bot=bot).get()

    def test_get_logs(self):
        till_date = utc_now().date()
        bot = "test_get_logs"
        user = "testUser2"
        start_time = utc_now() - timedelta(days=1)
        end_time = utc_now() + timedelta(days=1)
        processor = MongoProcessor()

        ModelProcessor.set_training_status(bot, user, "Done")
        ModelProcessor.set_training_status(bot, user, "Done")
        log_two = processor.get_logs(bot, "model_training", start_time, end_time)
        assert len(log_two) == 2
        ActionServerLogs(intent="intent2", action="http_action", sender="sender_id",
                         url="http://kairon-api.digite.com/api/bot",
                         request_params={}, api_response="Response", bot_response="Bot Response", bot=bot,
                         status="FAILURE").save()
        ActionServerLogs(intent="intent1", action="http_action", sender="sender_id",
                         request_params={}, api_response="Response", bot_response="Bot Response",
                         bot=bot).save()
        log_three = processor.get_logs(bot, "action_logs", start_time, end_time)
        assert len(log_three) == 2
        DataImporterLogProcessor.add_log(bot, user, is_data_uploaded=False, event_status=EVENT_STATUS.COMPLETED.value)
        DataImporterLogProcessor.add_log(bot, user, is_data_uploaded=False, event_status=EVENT_STATUS.COMPLETED.value)
        log_four = processor.get_logs(bot, "data_importer", start_time, end_time)
        assert len(log_four) == 2
        HistoryDeletionLogProcessor.add_log(bot, user, till_date, status=EVENT_STATUS.COMPLETED.value)
        HistoryDeletionLogProcessor.add_log(bot, user, till_date, status=EVENT_STATUS.COMPLETED.value)
        log_five = processor.get_logs(bot, "history_deletion", start_time, end_time)
        assert len(log_five) == 2
        MultilingualLogProcessor.add_log(source_bot=bot, user=user, event_status=EVENT_STATUS.COMPLETED.value)
        MultilingualLogProcessor.add_log(source_bot=bot, user=user, event_status=EVENT_STATUS.COMPLETED.value)
        log_six = processor.get_logs(bot, "multilingual", start_time, end_time)
        assert len(log_six) == 2
        ModelTestingLogProcessor.log_test_result(bot, user,
                                                 stories_result={},
                                                 nlu_result={},
                                                 event_status=EVENT_STATUS.COMPLETED.value)
        ModelTestingLogProcessor.log_test_result(bot, user,
                                                 stories_result={},
                                                 nlu_result={},
                                                 event_status=EVENT_STATUS.COMPLETED.value)
        log_seven = processor.get_logs(bot, "model_testing", start_time, end_time)
        assert len(log_seven) == 2
        log_eight = processor.get_logs(bot, "audit_logs", start_time, end_time)
        assert len(log_eight) == 6

    def test_delete_audit_logs(self):
        processor = MongoProcessor()
        start_time = utc_now()
        init_time = start_time - timedelta(days=1000)
        logs = processor.get_logs("test", "audit_logs", init_time, start_time)
        num_logs = len(logs)
        AuditLogData(
            attributes=[{"key": "bot", "value": "test"}], user="test", timestamp=start_time,
            action=AuditlogActions.SAVE.value,
            entity="ModelTraining"
        ).save()
        AuditLogData(
            attributes=[{"key": "bot", "value": "test"}], user="test", timestamp=start_time - timedelta(days=366),
            action=AuditlogActions.SAVE.value,
            entity="ModelTraining"
        ).save()
        AuditLogData(
            attributes=[{"key": "bot", "value": "test"}], user="test", timestamp=start_time - timedelta(days=480),
            action=AuditlogActions.SAVE.value,
            entity="ModelTraining"
        ).save()
        logs = processor.get_logs("test", "audit_logs", init_time, start_time)
        assert len(logs) == num_logs + 3
        processor.delete_audit_logs()
        logs = processor.get_logs("test", "audit_logs", init_time, start_time)
        assert len(logs) == num_logs + 1

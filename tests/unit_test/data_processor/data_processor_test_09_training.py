from tests.unit_test.data_processor.data_processor_support import *  # noqa: F403
from tests.unit_test.data_processor.data_processor_support import (
    MongoProcessorTestBase,
    fast_rasa_training,
)

class TestMongoProcessor(MongoProcessorTestBase):
    def test_train_model(self):
        model = train_model_for_bot("tests")
        assert model
        folder = os.path.join("models/tests", '*.tar.gz')
        assert len(list(glob.glob(folder))) == 1

    def test_train_model_validate_deletion(self, monkeypatch):
        file = glob.glob(os.path.join("models/tests", '*.tar.gz'))[0]
        for i in range(7):
            shutil.copy(file, os.path.join("models/tests", "old_model", f"{i}.tar.gz"))

        def _mock_train(*args, **kwargs):
            ob = object()
            ob.model = file
            return ob

        with patch("rasa.train") as mock_tr:
            mock_tr.side_effect = _mock_train
            model = train_model_for_bot("tests")
        assert model
        folder = os.path.join("models/tests", '*.tar.gz')
        assert len(list(glob.glob(folder))) == 1
        folder = os.path.join("models/tests", "old_model", "*.tar.gz")
        assert len(list(glob.glob(folder))) == 4

    def test_start_training_done(self, monkeypatch):
        model_path = start_training("tests", "testUser")
        assert model_path
        model_training = ModelTraining.objects(bot="tests", status="Done")
        assert model_training.__len__() == 1
        assert model_training.first().model_path == model_path

    def test_start_training_done_with_intrumentation(self):
        with patch.dict(Utility.environment["apm"], {"enable": True, 'service_name': 'kairon'}, clear=True):
            processor = MongoProcessor()
            loop = asyncio.get_event_loop()
            loop.run_until_complete(processor.save_from_path(
                "./tests/testing_data/initial", bot="test_initial", user="testUser"
            ))

            model_path = start_training("test_initial", "testUser")
            assert model_path
            model_training = ModelTraining.objects(bot="test_initial", status="Done")
            assert model_training.__len__() == 1
            assert model_training.first().model_path == model_path

    def test_start_training_fail(self):
        start_training("test", "testUser")
        model_training = ModelTraining.objects(bot="test", status="Fail")
        assert model_training.__len__() == 1
        assert model_training.first().exception in str("Training data does not exists!")

    @mock.patch(
        "kairon.shared.actions.utils.ActionUtility.execute_request_async",
        new_callable=AsyncMock
    )
    @patch("kairon.shared.rest_client.AioRestClient.request", autospec=True)
    @patch("kairon.shared.account.processor.AccountProcessor.get_bot", autospec=True)
    @patch("kairon.train.train_model_for_bot", autospec=True)
    def test_start_training_with_llm_faq(
        self, mock_train, mock_bot, mock_vec_client, mock_openai
    ):
        bot = "tests"
        user = "testUser"
        value = "nupurk"
        CognitionData(
            data="Welcome! Are you completely new to programming? If not then we presume you will be looking for information about why and how to get started with Python",
            bot=bot, user=user).save()
        CognitionData(
            data="Java is a high-level, class-based, object-oriented programming language that is designed to have as few implementation dependencies as possible.",
            bot=bot, user=user).save()
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key=value,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()
        MongoProcessor().add_action(GPT_LLM_FAQ, bot, user, False, ActionType.prompt_action.value)
        settings = BotSettings.objects(bot=bot).get()
        settings.llm_settings = LLMSettings(enable_faq=True)
        settings.save()
        embedding = list(np.random.random(1532))
        embedding = [[0.1] * 1532, [0.1] * 1532]
        mock_openai.return_value = (
            embedding,
            200,
            0.05,
            {}
        )
        mock_bot.return_value = {"account": 1}
        mock_train.return_value = f"/models/{bot}"
        start_training(bot, user)
        settings = BotSettings.objects(bot=bot).get()
        settings.llm_settings = LLMSettings(enable_faq=False)
        settings.save()
        log = Metering.objects(bot=bot, metric_type=MetricType.faq_training.value).get()
        assert log["faq"] == 2
        search_event = StoryEvents(name=DEFAULT_NLU_FALLBACK_INTENT_NAME, type=UserUttered.type_name)
        rule = Rules.objects(bot=bot, events__match=search_event, status=True).get()
        assert rule.events == [
            StoryEvents(name=RULE_SNIPPET_ACTION_NAME, type=ActionExecuted.type_name),
            StoryEvents(name="nlu_fallback", type=UserUttered.type_name),
            StoryEvents(name='utter_please_rephrase', type=ActionExecuted.type_name)
        ]

        LLMSecret.objects.delete()

    def test_add_endpoints(self):
        processor = MongoProcessor()
        config = {}
        processor.add_endpoints(config, bot="tests", user="testUser")
        endpoint = processor.get_endpoints("tests")
        assert endpoint.get("bot_endpoint") is None
        assert endpoint.get("action_endpoint") is None
        assert endpoint.get("tracker") is None

    def test_add_endpoints_add_bot_endpoint_empty_url(self):
        processor = MongoProcessor()
        config = {"bot_endpoint": {"url": ""}}
        with pytest.raises(AppException):
            processor.add_endpoints(config, bot="tests1", user="testUser")
            endpoint = processor.get_endpoints("tests1")
            assert endpoint.get("bot_endpoint") is None
            assert endpoint.get("action_endpoint") is None
            assert endpoint.get("tracker") is None

    def test_add_endpoints_add_bot_endpoint(self):
        processor = MongoProcessor()
        config = {"bot_endpoint": {"url": "http://localhost:5000/"}}
        processor.add_endpoints(config, bot="tests1", user="testUser")
        endpoint = processor.get_endpoints("tests1")
        assert endpoint["bot_endpoint"].get("url") == "http://localhost:5000/"
        assert endpoint.get("action_endpoint") is None
        assert endpoint.get("tracker") is None

    def test_add_endpoints_add_action_endpoint_empty_url(self):
        processor = MongoProcessor()
        config = {"action_endpoint": {"url": ""}}
        with pytest.raises(AppException):
            processor.add_endpoints(config, bot="tests2", user="testUser")
            endpoint = processor.get_endpoints("tests2")
            assert endpoint.get("bot_endpoint") is None
            assert endpoint.get("action_endpoint") is None
            assert endpoint.get("tracker") is None

    def test_add_endpoints_add_action_endpoint(self):
        processor = MongoProcessor()
        config = {"action_endpoint": {"url": "http://localhost:5000/"}}
        processor.add_endpoints(config, bot="tests2", user="testUser")
        endpoint = processor.get_endpoints("tests2")
        assert endpoint.get("bot_endpoint") is None
        assert endpoint.get("action_endpoint").get("url") == "http://localhost:5000/"
        assert endpoint.get("tracker") is None

    def test_add_endpoints_add_history_endpoint(self):
        processor = MongoProcessor()
        config = {
            "history_endpoint": {
                "url": "http://localhost:27017/",
                "token": "conversations"
            }
        }
        processor.add_endpoints(config, bot="tests3", user="testUser")
        endpoint = processor.get_endpoints("tests3")
        assert endpoint.get("bot_endpoint") is None
        assert endpoint.get("action_endpoint") is None
        assert endpoint.get("history_endpoint").get("url") == "http://localhost:27017/"
        assert endpoint.get("history_endpoint").get("token") == "conversations"

    def test_get_endpoints_mask_history_server_token(self):
        processor = MongoProcessor()
        config = {
            "history_endpoint": {
                "url": "http://localhost:27017/",
                "token": "conversations"
            }
        }
        processor.add_endpoints(config, bot="tests3", user="testUser")
        endpoint = processor.get_endpoints("tests3", mask_characters=True)
        assert endpoint.get("bot_endpoint") is None
        assert endpoint.get("action_endpoint") is None
        assert endpoint.get("history_endpoint").get("url") == "http://localhost:27017/"
        assert endpoint.get("history_endpoint").get("token") == "conversati***"

    def test_get_history_server_endpoint(self):
        processor = MongoProcessor()
        endpoint = processor.get_history_server_endpoint("tests3")
        assert endpoint.get("url") == "http://localhost:27017/"
        assert endpoint.get("token") == "conversations"
        assert endpoint.get("type") == 'user'

    def test_get_kairon_history_server_endpoint(self):
        processor = MongoProcessor()
        endpoint = processor.get_history_server_endpoint("test_bot")
        assert endpoint.get("url") == "http://localhost:8083"
        assert endpoint.get("token")
        assert endpoint.get("type") == 'kairon'

    def test_update_endpoints(self):
        processor = MongoProcessor()
        config = {
            "action_endpoint": {"url": "http://localhost:8000/"},
            "bot_endpoint": {"url": "http://localhost:5000/"},
            "history_endpoint": {
                "url": "http://localhost:27019/",
                "token": "kairon-history-user",
            },
        }
        processor.add_endpoints(config, bot="tests", user="testUser")
        endpoint = processor.get_endpoints("tests")
        assert endpoint.get("bot_endpoint").get("url") == "http://localhost:5000/"
        assert endpoint.get("action_endpoint").get("url") == "http://localhost:8000/"
        assert endpoint.get("history_endpoint").get("url") == "http://localhost:27019/"
        assert endpoint.get("history_endpoint").get("token") == "kairon-history-user"

    def test_update_endpoints_token_less_than_8_chars(self):
        processor = MongoProcessor()
        config = {
            "action_endpoint": {"url": "http://localhost:8000/"},
            "bot_endpoint": {"url": "http://localhost:5000/"},
            "history_endpoint": {
                "url": "http://localhost:27019/",
                "token": "kairon",
            },
        }
        with pytest.raises(AppException, match='token must contain at least 8 characters'):
            processor.add_endpoints(config, bot="tests", user="testUser")
        endpoint = processor.get_endpoints("tests")
        assert endpoint.get("bot_endpoint").get("url") == "http://localhost:5000/"
        assert endpoint.get("action_endpoint").get("url") == "http://localhost:8000/"
        assert endpoint.get("history_endpoint").get("url") == "http://localhost:27019/"
        assert endpoint.get("history_endpoint").get("token") == "kairon-history-user"

    def test_update_endpoints_token_with_space(self):
        processor = MongoProcessor()
        config = {
            "action_endpoint": {"url": "http://localhost:8000/"},
            "bot_endpoint": {"url": "http://localhost:5000/"},
            "history_endpoint": {
                "url": "http://localhost:27019/",
                "token": "kairon token",
            },
        }
        with pytest.raises(AppException, match='token cannot contain spaces'):
            processor.add_endpoints(config, bot="tests", user="testUser")
        endpoint = processor.get_endpoints("tests")
        assert endpoint.get("bot_endpoint").get("url") == "http://localhost:5000/"
        assert endpoint.get("action_endpoint").get("url") == "http://localhost:8000/"
        assert endpoint.get("history_endpoint").get("url") == "http://localhost:27019/"
        assert endpoint.get("history_endpoint").get("token") == "kairon-history-user"

    def test_update_endpoints_any(self):
        processor = MongoProcessor()
        config = {
            "action_endpoint": {"url": "http://127.0.0.1:8000/"},
            "bot_endpoint": {"url": "http://127.0.0.1:5000/"},
        }
        processor.add_endpoints(config, bot="tests", user="testUser")
        endpoint = processor.get_endpoints("tests")
        assert endpoint.get("bot_endpoint").get("url") == "http://127.0.0.1:5000/"
        assert endpoint.get("action_endpoint").get("url") == "http://127.0.0.1:8000/"
        assert endpoint.get("history_endpoint").get("url") == "http://localhost:27019/"
        assert endpoint.get("history_endpoint").get("token") == "kairon-history-user"

    def test_delete_endpoints(self):
        processor = MongoProcessor()
        config = {
            "bot_endpoint": {"url": "http://127.0.0.1:5000/"},
            "action_endpoint": {"url": "http://127.0.0.1:8000/"},
            "history_endpoint": {
                "url": "http://localhost:27019/",
                "token": "kairon-history-user",
            },
        }
        processor.add_endpoints(config, bot="test_delete_endpoint", user="testUser")

        processor.delete_endpoint('test_delete_endpoint', ENDPOINT_TYPE.BOT_ENDPOINT.value)
        endpoint = processor.get_endpoints("test_delete_endpoint")
        assert not endpoint.get(ENDPOINT_TYPE.BOT_ENDPOINT)
        assert endpoint.get("action_endpoint").get("url") == "http://127.0.0.1:8000/"
        assert endpoint.get("history_endpoint").get("url") == "http://localhost:27019/"

        processor.delete_endpoint('test_delete_endpoint', ENDPOINT_TYPE.ACTION_ENDPOINT.value)
        endpoint = processor.get_endpoints("test_delete_endpoint")
        assert not endpoint.get(ENDPOINT_TYPE.BOT_ENDPOINT)
        assert not endpoint.get(ENDPOINT_TYPE.ACTION_ENDPOINT)
        assert endpoint.get("history_endpoint").get("url") == "http://localhost:27019/"

        processor.delete_endpoint('test_delete_endpoint', ENDPOINT_TYPE.HISTORY_ENDPOINT.value)
        endpoint = processor.get_endpoints("test_delete_endpoint")
        assert not endpoint.get(ENDPOINT_TYPE.BOT_ENDPOINT.value)
        assert not endpoint.get(ENDPOINT_TYPE.ACTION_ENDPOINT.value)
        assert not endpoint.get(ENDPOINT_TYPE.HISTORY_ENDPOINT.value)

    def test_delete_endpoints_none(self):
        processor = MongoProcessor()
        config = {
            "bot_endpoint": {"url": "http://127.0.0.1:5000/"},
            "action_endpoint": {"url": "http://127.0.0.1:8000/"},
            "history_endpoint": {
                "url": "http://localhost:27019/",
                "token": "kairon-history-user",
            },
        }
        processor.add_endpoints(config, bot="test_delete_endpoint", user="testUser")

        with pytest.raises(AppException, match='endpoint_type is required for deletion'):
            processor.delete_endpoint('test_delete_endpoint', None)

    def test_delete_endpoints_not_exists(self):
        processor = MongoProcessor()
        with pytest.raises(AppException) as e:
            processor.delete_endpoint('test_delete_endpoints_not_exists', ENDPOINT_TYPE.BOT_ENDPOINT.value)
        assert str(e).__contains__("No Endpoint configured")

    def test_delete_endpoints_type_not_exists(self):
        processor = MongoProcessor()
        config = {
            "bot_endpoint": {"url": "http://127.0.0.1:5000/"},
        }
        processor.add_endpoints(config, bot="test_delete_endpoints_type_not_exists", user="testUser")

        with pytest.raises(AppException, match='Endpoint not configured'):
            processor.delete_endpoint('test_delete_endpoints_type_not_exists', ENDPOINT_TYPE.ACTION_ENDPOINT.value)

        processor.delete_endpoint('test_delete_endpoints_type_not_exists', ENDPOINT_TYPE.BOT_ENDPOINT.value)
        endpoint = processor.get_endpoints("test_delete_endpoints_type_not_exists")
        assert not endpoint.get(ENDPOINT_TYPE.BOT_ENDPOINT.value)

        with pytest.raises(AppException, match='Endpoint not configured') as e:
            processor.delete_endpoint('test_delete_endpoints_type_not_exists', ENDPOINT_TYPE.HISTORY_ENDPOINT.value)

    def test_get_kairon_history_server_endpoint_none_configured(self):
        processor = MongoProcessor()
        Utility.environment['history_server']['url'] = None
        with pytest.raises(AppException, match='No history server endpoint configured'):
            endpoint = processor.get_history_server_endpoint("test_bot")

    def test_download_data_files(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        file = processor.download_files("tests", "user@integration.com")
        assert file.endswith(".zip")

    def test_download_files_excludes_non_trainable_schema(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        CognitionSchema(
            bot="tests",
            user="user@integration.com",
            collection_name="normal_table",
            schema_metadata=SchemaMetadata(training_needed=True)
        ).save()

        CognitionSchema(
            bot="tests",
            user="user@integration.com",
            collection_name="analytics_pipeline",
            schema_metadata=SchemaMetadata(training_needed=False)
        ).save()

        processor = MongoProcessor()
        exported_data = processor._MongoProcessor__prepare_cognition_data_for_bot("tests")
        collections = [item["collection"] for item in exported_data]

        assert "normal_table" in collections
        assert "analytics_pipeline" not in collections

    def test_download_data_files_multiflow_stories(self, monkeypatch):
        from zipfile import ZipFile
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        story_name = "multiflow_story_STORY_download_data_files"
        steps = [
            {"step": {"name": "asking", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_asking", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_asking", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "moodyy", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foodyy", "type": "HTTP_ACTION", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foodyy", "type": "HTTP_ACTION", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_foodyy", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_foodyy", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_moodyy", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "moodyy", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_moodyy", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6', "flow_type": 'STORY'}, {"node_id": "5", "flow_type": 'RULE'}]
        story_dict = {'name': story_name, 'steps': steps, "metadata": metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, "tests_download", "user@integration.com")

        steps_story = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "deny", "type": "INTENT"},
            {"name": "utter_deny", "type": "BOT"}
        ]
        story_dict_one = {'name': "story for download", 'steps': steps_story, 'type': 'STORY',
                          'template_type': 'CUSTOM'}
        processor.add_complex_story(story_dict_one, "tests_download", "user@integration.com")

        steps_rule = [
            {"name": "food", "type": "INTENT"},
            {"name": "utter_food", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        rule_dict = {'name': "rule for download", 'steps': steps_rule, 'type': 'RULE', 'template_type': 'RULE'}
        processor.add_complex_story(rule_dict, "tests_download", "user@integration.com")

        file = processor.download_files("tests_download", "user@integration.com")
        assert file.endswith(".zip")
        zip_file = ZipFile(file, mode='r')
        assert zip_file.getinfo('multiflow_stories.yml')
        assert zip_file.getinfo('data/stories.yml')
        file_info_multiflow_stories = zip_file.getinfo('multiflow_stories.yml')
        file_multiflow_stories = zip_file.read(file_info_multiflow_stories)

        assert file_multiflow_stories == b"multiflow_story:\n- block_name: multiflow_story_story_download_data_files\n  end_checkpoints: []\n  events:\n  - connections:\n    - component_id: 63uNJw1QvpQZvIpP07dxnmFU\n      name: utter_asking\n      node_id: '2'\n      type: BOT\n    step:\n      component_id: 637d0j9GD059jEwt2jPnlZ7I\n      name: asking\n      node_id: '1'\n      type: INTENT\n  - connections:\n    - component_id: 633w6kSXuz3qqnPU571jZyCv\n      name: moodyy\n      node_id: '3'\n      type: INTENT\n    - component_id: 63WKbWs5K0ilkujWJQpXEXGD\n      name: foodyy\n      node_id: '4'\n      type: HTTP_ACTION\n    step:\n      component_id: 63uNJw1QvpQZvIpP07dxnmFU\n      name: utter_asking\n      node_id: '2'\n      type: BOT\n  - connections:\n    - component_id: 63gm5BzYuhC1bc6yzysEnN4E\n      name: utter_foodyy\n      node_id: '5'\n      type: BOT\n    step:\n      component_id: 63WKbWs5K0ilkujWJQpXEXGD\n      name: foodyy\n      node_id: '4'\n      type: HTTP_ACTION\n  - connections: []\n    step:\n      component_id: 63gm5BzYuhC1bc6yzysEnN4E\n      name: utter_foodyy\n      node_id: '5'\n      type: BOT\n  - connections: []\n    step:\n      component_id: 634a9bwPPj2y3zF5HOVgLiXx\n      name: utter_moodyy\n      node_id: '6'\n      type: BOT\n  - connections:\n    - component_id: 634a9bwPPj2y3zF5HOVgLiXx\n      name: utter_moodyy\n      node_id: '6'\n      type: BOT\n    step:\n      component_id: 633w6kSXuz3qqnPU571jZyCv\n      name: moodyy\n      node_id: '3'\n      type: INTENT\n  flow_tags:\n  - chatbot_flow\n  metadata:\n  - flow_type: STORY\n    node_id: '6'\n  - flow_type: RULE\n    node_id: '5'\n  start_checkpoints:\n  - STORY_START\n  template_type: CUSTOM\n"
        file_stories = zip_file.getinfo('data/stories.yml')
        stories = zip_file.read(file_stories)
        assert stories == b'version: "3.1"\nstories:\n- story: story for download\n  steps:\n  - intent: greet\n  - action: utter_greet\n  - intent: deny\n  - action: utter_deny\n'
        file_rules = zip_file.getinfo('data/rules.yml')
        rules = zip_file.read(file_rules)
        assert rules == b'version: "3.1"\nrules:\n- rule: rule for download\n  steps:\n  - intent: food\n  - action: utter_food\n  - action: utter_cheer_up\n  metadata:\n    flow_tags:\n    - chatbot_flow\n'
        zip_file.close()

        file_two = processor.download_files("tests_download", "user@integration.com", True)
        assert file_two.endswith(".zip")
        zip_file = ZipFile(file_two, mode='r')
        assert zip_file.getinfo('data/stories.yml')
        assert zip_file.getinfo('data/rules.yml')
        file_info_stories = zip_file.getinfo('data/stories.yml')
        file_info_rules = zip_file.getinfo('data/rules.yml')
        file_stories = zip_file.read(file_info_stories)
        file_rules = zip_file.read(file_info_rules)
        multiflow_story = zip_file.getinfo('multiflow_stories.yml')
        file_multiflow_story = zip_file.read(multiflow_story)
        assert file_stories == b'version: "3.1"\nstories:\n- story: story for download\n  steps:\n  - intent: greet\n  - action: utter_greet\n  - intent: deny\n  - action: utter_deny\n- story: multiflow_story_story_download_data_files_2\n  steps:\n  - intent: asking\n  - action: utter_asking\n  - intent: moodyy\n  - action: utter_moodyy\n'
        assert file_rules == b'version: "3.1"\nrules:\n- rule: rule for download\n  steps:\n  - intent: food\n  - action: utter_food\n  - action: utter_cheer_up\n  metadata:\n    flow_tags:\n    - chatbot_flow\n- rule: multiflow_story_story_download_data_files_1\n  steps:\n  - intent: asking\n  - action: utter_asking\n  - action: foodyy\n  - action: utter_foodyy\n'
        assert file_multiflow_story == b"multiflow_story:\n- block_name: multiflow_story_story_download_data_files\n  end_checkpoints: []\n  events:\n  - connections:\n    - component_id: 63uNJw1QvpQZvIpP07dxnmFU\n      name: utter_asking\n      node_id: '2'\n      type: BOT\n    step:\n      component_id: 637d0j9GD059jEwt2jPnlZ7I\n      name: asking\n      node_id: '1'\n      type: INTENT\n  - connections:\n    - component_id: 633w6kSXuz3qqnPU571jZyCv\n      name: moodyy\n      node_id: '3'\n      type: INTENT\n    - component_id: 63WKbWs5K0ilkujWJQpXEXGD\n      name: foodyy\n      node_id: '4'\n      type: HTTP_ACTION\n    step:\n      component_id: 63uNJw1QvpQZvIpP07dxnmFU\n      name: utter_asking\n      node_id: '2'\n      type: BOT\n  - connections:\n    - component_id: 63gm5BzYuhC1bc6yzysEnN4E\n      name: utter_foodyy\n      node_id: '5'\n      type: BOT\n    step:\n      component_id: 63WKbWs5K0ilkujWJQpXEXGD\n      name: foodyy\n      node_id: '4'\n      type: HTTP_ACTION\n  - connections: []\n    step:\n      component_id: 63gm5BzYuhC1bc6yzysEnN4E\n      name: utter_foodyy\n      node_id: '5'\n      type: BOT\n  - connections: []\n    step:\n      component_id: 634a9bwPPj2y3zF5HOVgLiXx\n      name: utter_moodyy\n      node_id: '6'\n      type: BOT\n  - connections:\n    - component_id: 634a9bwPPj2y3zF5HOVgLiXx\n      name: utter_moodyy\n      node_id: '6'\n      type: BOT\n    step:\n      component_id: 633w6kSXuz3qqnPU571jZyCv\n      name: moodyy\n      node_id: '3'\n      type: INTENT\n  flow_tags:\n  - chatbot_flow\n  metadata:\n  - flow_type: STORY\n    node_id: '6'\n  - flow_type: RULE\n    node_id: '5'\n  start_checkpoints:\n  - STORY_START\n  template_type: CUSTOM\n"
        zip_file.close()

    import yaml

    def test_download_data_files_prompt_action(self, monkeypatch):
        from zipfile import ZipFile
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot='tests_download_prompt',
            user='user@integration.com'
        )
        llm_secret.save()
        BotSettings(bot="tests_download_prompt", user="user@integration.com",
                    llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'prompt_action_with_default_values',
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}
                                   ],
                   "set_slots": [{"name": "gpt_result", "value": "${data}", "evaluation_type": "expression"},
                                 {"name": "gpt_result_type", "value": "${data.type}", "evaluation_type": "script"}],
                   "dispatch_response": False
                   }
        processor.add_prompt_action(request, "tests_download_prompt", "user@integration.com")
        file = processor.download_files("tests_download_prompt", "user@integration.com")
        assert file.endswith(".zip")
        zip_file = ZipFile(file, mode='r')
        assert zip_file.getinfo('actions.yml')
        file_info_actions = zip_file.getinfo('actions.yml')
        file_content_actions = zip_file.read(file_info_actions)
        yaml_content = yaml.safe_load(file_content_actions)

        # Check that the system prompt exists in the yaml
        prompts = yaml_content['prompt_action'][0]['llm_prompts']
        system_prompt = next((prompt for prompt in prompts if prompt['name'] == 'System Prompt'), None)
        assert system_prompt is not None
        assert system_prompt['data'] == 'You are a personal assistant.'
        assert system_prompt['source'] == 'static'
        assert system_prompt['type'] == 'system'
        assert system_prompt['is_enabled'] is True

        LLMSecret.objects.delete()

    def test_download_data_files_empty_data(self, monkeypatch):
        from zipfile import ZipFile
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()

        file = processor.download_files("tests_download_empty_data", "user@integration.com")
        assert file.endswith(".zip")
        zip_file = ZipFile(file, mode='r')
        assert zip_file.filelist.__len__() == 9
        assert zip_file.getinfo('data/stories.yml')
        assert zip_file.getinfo('data/rules.yml')
        file_info_stories = zip_file.getinfo('data/stories.yml')
        file_info_rules = zip_file.getinfo('data/rules.yml')
        file_content_stories = zip_file.read(file_info_stories)
        file_content_rules = zip_file.read(file_info_rules)
        assert file_content_stories == b'version: "3.1"\n'
        assert file_content_rules == b'version: "3.1"\n'
        zip_file.close()

    def test_download_data_files_multiflow_stories_with_actions(self, monkeypatch):
        from zipfile import ZipFile
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        story_name = "multiflow_story_STORY_download_data_files_with_actions"
        steps = [
            {"step": {"name": "asking", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_asking", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_asking", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "moodyy", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foodyy", "type": "HTTP_ACTION", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foodyy", "type": "HTTP_ACTION", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_foody", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_foody", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_moodyy", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "moodyy", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_moodyy", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6', "flow_type": 'STORY'}, {"node_id": "5", "flow_type": 'RULE'}]
        story_dict = {'name': story_name, 'steps': steps, "metadata": metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, "tests_download_again", "user@integration.com")
        file = processor.download_files("tests_download_again", "user@integration.com", True)
        assert file.endswith(".zip")
        zip_file = ZipFile(file, mode='r')
        assert zip_file.getinfo('data/stories.yml')
        assert zip_file.getinfo('data/rules.yml')
        file_info_stories = zip_file.getinfo('data/stories.yml')
        file_info_rules = zip_file.getinfo('data/rules.yml')
        file_content_stories = zip_file.read(file_info_stories)
        file_content_rules = zip_file.read(file_info_rules)
        print(file_content_stories)
        print(file_content_rules)

        assert file_content_stories == b'version: "3.1"\nstories:\n- story: multiflow_story_story_download_data_files_with_actions_2\n  steps:\n  - intent: asking\n  - action: utter_asking\n  - intent: moodyy\n  - action: utter_moodyy\n'
        assert file_content_rules == b'version: "3.1"\nrules:\n- rule: multiflow_story_story_download_data_files_with_actions_1\n  steps:\n  - intent: asking\n  - action: utter_asking\n  - action: foodyy\n  - action: utter_foody\n'
        zip_file.close()

    def test_download_data_files_with_actions(self, monkeypatch):
        from zipfile import ZipFile

        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'tests', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }
        #add a http action to the bot
        act_config = HttpActionConfig()
        act_config.action_name = "my_http_action"
        act_config.bot = 'tests'
        act_config.user = 'user@integration.com'
        act_config.status = True
        act_config.http_url = "https://jsonplaceholder.typicode.com/posts/1"
        act_config.request_method = "GET"
        act_config.content_type = "json"
        act_config.response = HttpActionResponse(value='zxcvb')
        act_config.save()

        action = Actions()
        action.name = 'my_http_action'
        action.bot = 'tests'
        action.user = 'user@integration.com'
        action.status = True
        action.type = ActionType.http_action.value
        action.save()

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        file_path = processor.download_files("tests", "user@integration.com")

        assert file_path.endswith(".zip")
        zip_file = ZipFile(file_path, mode='r')
        assert zip_file.filelist.__len__() == 10
        assert zip_file.getinfo('chat_client_config.yml')
        assert zip_file.getinfo('config.yml')
        assert zip_file.getinfo('domain.yml')
        assert zip_file.getinfo('actions.yml')
        assert zip_file.getinfo('multiflow_stories.yml')
        assert zip_file.getinfo('bot_content.yml')
        assert zip_file.getinfo('data/stories.yml')
        assert zip_file.getinfo('data/rules.yml')
        assert zip_file.getinfo('data/nlu.yml')
        file_info = zip_file.getinfo('actions.yml')
        file_content = zip_file.read(file_info)
        actual_actions = file_content.decode(encoding='utf-8')
        actual_actions_dict = yaml.safe_load(actual_actions)
        assert actual_actions_dict == {'http_action': [
            {
                'action_name': 'my_http_action',
                'content_type': 'json',
                'http_url': 'https://jsonplaceholder.typicode.com/posts/1',
                'params_list': [],
                'request_method': 'GET',
                'response': {
                    'dispatch': True,
                    'dispatch_type': 'text',
                    'evaluation_type': 'expression',
                    'value': 'zxcvb',
                },
                'headers': [],
                'set_slots': []
            }]}
        zip_file.close()

    def test_load_action_configurations(self):
        processor = MongoProcessor()
        action_config = processor.load_action_configurations("tests")
        assert action_config == {'http_action': [
            {
                'action_name': 'my_http_action',
                'content_type': 'json',
                'http_url': 'https://jsonplaceholder.typicode.com/posts/1',
                'request_method': 'GET',
                'response': {
                    'dispatch': True,
                    'dispatch_type': 'text',
                    'evaluation_type': 'expression',
                    'value': 'zxcvb',
                },
            }
        ], 'jira_action': [], 'email_action': [], 'zendesk_action': [],
                                 'form_validation_action': [], 'slot_set_action': [], 'google_search_action': [],
                                 'pipedrive_leads_action': [], 'two_stage_fallback': [], 'prompt_action': [],
                                 'razorpay_action': [], 'pyscript_action': [], 'database_action': [], 'live_agent_action': [],
                                 'store_page_action': [], 'agent_action': []}

    def test_get_utterance_from_intent(self):
        processor = MongoProcessor()
        response = processor.get_utterance_from_intent("deny", "tests")
        assert response[0] == "utter_goodbye"
        assert response[1] == UTTERANCE_TYPE.BOT

    def test_get_utterance_from_empty_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.get_utterance_from_intent("", "tests")

    def test_get_stories(self):
        processor = MongoProcessor()
        stories = list(processor.get_stories("tests"))
        assert stories.__len__() == 8
        assert stories[0]['name'] == 'happy path'
        assert stories[0]['type'] == 'STORY'
        assert stories[0]['steps'][0]['name'] == 'greet'
        assert stories[0]['steps'][0]['type'] == 'INTENT'
        assert stories[0]['steps'][1]['name'] == 'utter_greet'
        assert stories[0]['steps'][1]['type'] == 'BOT'
        assert stories[0]['template_type'] == 'CUSTOM'

    def test_get_multiflow_stories(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greeting", "type": "INTENT", "node_id": "1", "component_id": "63bLGgJEl8dz0axb9FvrWvHq"},
             "connections": [
                 {"name": "utter_hiii", "type": "BOT", "node_id": "2", "component_id": "63IjWdIIpHgT36sJXpqnS7Mx"}]
             },
            {"step": {"name": "utter_hiii", "type": "BOT", "node_id": "2", "component_id": "63IjWdIIpHgT36sJXpqnS7Mx"},
             "connections": [
                 {"name": "record", "type": "INTENT", "node_id": "3", "component_id": "634nMJ9hAAtbgr6Wn1Fhm89D"},
                 {"name": "id", "type": "INTENT", "node_id": "4", "component_id": "632o76BgDW2eo3JOqDGk9RQW"}]
             },
            {"step": {"name": "id", "type": "INTENT", "node_id": "4", "component_id": "632o76BgDW2eo3JOqDGk9RQW"},
             "connections": [
                 {"name": "utter_id", "type": "BOT", "node_id": "5", "component_id": "637d13it2UNSslxVSbWZjBqO"}]
             },
            {"step": {"name": "utter_id", "type": "BOT", "node_id": "5", "component_id": "637d13it2UNSslxVSbWZjBqO"},
             "connections": None
             },
            {"step": {"name": "utter_record", "type": "BOT", "node_id": "6",
                      "component_id": "63e63sU5PHRQnnINYPZitORt"},
             "connections": None
             },
            {"step": {"name": "record", "type": "INTENT", "node_id": "3", "component_id": "634nMJ9hAAtbgr6Wn1Fhm89D"},
             "connections": [
                 {"name": "utter_record", "type": "BOT", "node_id": "6", "component_id": "63e63sU5PHRQnnINYPZitORt"}]
             }
        ]
        story_dict = {"name": "a different story", 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, "tester", "TesterUser")
        stories = list(processor.get_multiflow_stories("tester"))
        assert stories.__len__() == 1
        assert stories[0]['name'] == 'a different story'
        assert stories[0]['type'] == 'MULTIFLOW'
        print(stories[0]['steps'])
        assert stories[0]['steps'] == [
            {'step': {'name': 'greeting', 'type': 'INTENT', 'node_id': '1', 'component_id': '63bLGgJEl8dz0axb9FvrWvHq'},
             'connections': [
                 {'name': 'utter_hiii', 'type': 'BOT', 'node_id': '2', 'component_id': '63IjWdIIpHgT36sJXpqnS7Mx'}]},
            {'step': {'name': 'utter_hiii', 'type': 'BOT', 'node_id': '2', 'component_id': '63IjWdIIpHgT36sJXpqnS7Mx'},
             'connections': [
                 {'name': 'record', 'type': 'INTENT', 'node_id': '3', 'component_id': '634nMJ9hAAtbgr6Wn1Fhm89D'},
                 {'name': 'id', 'type': 'INTENT', 'node_id': '4', 'component_id': '632o76BgDW2eo3JOqDGk9RQW'}]},
            {'step': {'name': 'id', 'type': 'INTENT', 'node_id': '4', 'component_id': '632o76BgDW2eo3JOqDGk9RQW'},
             'connections': [
                 {'name': 'utter_id', 'type': 'BOT', 'node_id': '5', 'component_id': '637d13it2UNSslxVSbWZjBqO'}]},
            {'step': {'name': 'utter_id', 'type': 'BOT', 'node_id': '5', 'component_id': '637d13it2UNSslxVSbWZjBqO'},
             'connections': []}, {'step': {'name': 'utter_record', 'type': 'BOT', 'node_id': '6',
                                           'component_id': '63e63sU5PHRQnnINYPZitORt'},
                                  'connections': []},
            {'step': {'name': 'record', 'type': 'INTENT', 'node_id': '3', 'component_id': '634nMJ9hAAtbgr6Wn1Fhm89D'},
             'connections': [
                 {'name': 'utter_record', 'type': 'BOT', 'node_id': '6', 'component_id': '63e63sU5PHRQnnINYPZitORt'}]}]

    def test_get_multiflow_stories_with_STORY_metadata(self):
        processor = MongoProcessor()
        story_name = "get_multiflow_story_STORY"
        bot = "test_get_path_story"
        user = "test_get_user_path_story"
        steps = [
            {"step": {"name": "asker", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_ask", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_ask", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "moody", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foody", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foody", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_food", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_food", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "moody", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6', "flow_type": 'STORY'}, {"node_id": "5", "flow_type": 'STORY'}]
        story_dict = {'name': story_name, 'steps': steps, "metadata": metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = list(processor.get_multiflow_stories("test_get_path_story"))
        assert multiflow_story.__len__() == 1
        assert multiflow_story[0]['metadata'] == [{'node_id': '6', 'flow_type': 'STORY'},
                                                  {'node_id': '5', 'flow_type': 'STORY'}]
        assert multiflow_story[0]['name'] == 'get_multiflow_story_story'

    def test_get_multiflow_stories_with_RULE_metadata(self):
        processor = MongoProcessor()
        story_name = "get_multiflow_story_RULE"
        bot = "test_get_path_rule"
        user = "test_get_user_path_rule"
        steps = [
            {"step": {"name": "asker", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_asker", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_asker", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "moody", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foody", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foody", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_foody", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_foody", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_moody", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "moody", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_moody", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6', "flow_type": 'RULE'}, {"node_id": "5", "flow_type": 'RULE'}]
        story_dict = {'name': story_name, 'steps': steps, "metadata": metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = list(processor.get_multiflow_stories("test_get_path_rule"))
        assert multiflow_story.__len__() == 1
        assert multiflow_story[0]['metadata'] == [{"node_id": '6', "flow_type": 'RULE'},
                                                  {"node_id": "5", "flow_type": 'RULE'}]
        assert multiflow_story[0]['name'] == 'get_multiflow_story_rule'

    def test_get_multiflow_stories_with_empty_metadata(self):
        processor = MongoProcessor()
        story_name = "get_multiflow_story_empty_metadata"
        bot = "test_get_path_empty_metadata"
        user = "test_get_user_path_empty_metadata"
        steps = [
            {"step": {"name": "question", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_question", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_question", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "moody", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foody", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foody", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_foody", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_foody", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_moody", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "moody", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_moody", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = list(processor.get_multiflow_stories("test_get_path_empty_metadata"))
        assert multiflow_story.__len__() == 1
        assert multiflow_story[0]['metadata'] == []
        assert multiflow_story[0]['name'] == 'get_multiflow_story_empty_metadata'

    def test_get_multiflow_stories_with_empty_path_type_metadata(self):
        processor = MongoProcessor()
        story_name = "test_get_multiflow_stories_with_empty_path_type_metadata"
        bot = "test_get_empty_path_type_metadata"
        user = "test_get_user_empty_path_type_metadata"
        steps = [
            {"step": {"name": "questionairre", "type": "INTENT", "node_id": "1",
                      "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_questionairre", "type": "BOT", "node_id": "2",
                  "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_questionairre", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "moody", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foody", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foody", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_foody", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_foody", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_moody", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "moody", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_moody", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6'}, {"node_id": "5"}]
        story_dict = {'name': story_name, 'steps': steps, 'metadata': metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = list(processor.get_multiflow_stories("test_get_empty_path_type_metadata"))
        assert multiflow_story.__len__() == 1
        assert multiflow_story[0]['metadata'] == [{'node_id': '6', 'flow_type': 'STORY'},
                                                  {'node_id': '5', 'flow_type': 'STORY'}]
        assert multiflow_story[0]['name'] == 'test_get_multiflow_stories_with_empty_path_type_metadata'

    def test_get_multiflow_stories_with_STORY_metadata(self):
        processor = MongoProcessor()
        story_name = "get_multiflow_story_STORY"
        bot = "test_get_path_story"
        user = "test_get_user_path_story"
        steps = [
            {"step": {"name": "asker", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_ask", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_ask", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "moody", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foody", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foody", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_food", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_food", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "moody", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6', "flow_type": 'STORY'}, {"node_id": "5", "flow_type": 'STORY'}]
        story_dict = {'name': story_name, 'steps': steps, "metadata": metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = list(processor.get_multiflow_stories("test_get_path_story"))
        assert multiflow_story.__len__() == 1
        assert multiflow_story[0]['metadata'] == [{'node_id': '6', 'flow_type': 'STORY'},
                                                  {'node_id': '5', 'flow_type': 'STORY'}]
        assert multiflow_story[0]['name'] == 'get_multiflow_story_story'

    def test_get_multiflow_stories_with_RULE_metadata(self):
        processor = MongoProcessor()
        story_name = "get_multiflow_story_RULE"
        bot = "test_get_path_rule"
        user = "test_get_user_path_rule"
        steps = [
            {"step": {"name": "asker", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_asker", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_asker", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "moody", "type": "HTTP_ACTION", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foody", "type": "HTTP_ACTION", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foody", "type": "HTTP_ACTION", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_foody", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_foody", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "moody", "type": "HTTP_ACTION", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6', "flow_type": 'RULE'}, {"node_id": "5", "flow_type": 'RULE'}]
        story_dict = {'name': story_name, 'steps': steps, "metadata": metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = list(processor.get_multiflow_stories("test_get_path_rule"))
        assert multiflow_story.__len__() == 1
        assert multiflow_story[0]['metadata'] == [{"node_id": '6', "flow_type": 'RULE'},
                                                  {"node_id": "5", "flow_type": 'RULE'}]
        assert multiflow_story[0]['name'] == 'get_multiflow_story_rule'

    def test_get_multiflow_stories_with_empty_metadata(self):
        processor = MongoProcessor()
        story_name = "get_multiflow_story_empty_metadata"
        bot = "test_get_path_empty_metadata"
        user = "test_get_user_path_empty_metadata"
        steps = [
            {"step": {"name": "question", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_question", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_question", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "moody", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foody", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foody", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_foody", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_foody", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_moody", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "moody", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_moody", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = list(processor.get_multiflow_stories("test_get_path_empty_metadata"))
        assert multiflow_story.__len__() == 1
        assert multiflow_story[0]['metadata'] == []
        assert multiflow_story[0]['name'] == 'get_multiflow_story_empty_metadata'

    def test_get_multiflow_stories_with_empty_path_type_metadata(self):
        processor = MongoProcessor()
        story_name = "test_get_multiflow_stories_with_empty_path_type_metadata"
        bot = "test_get_empty_path_type_metadata"
        user = "test_get_user_empty_path_type_metadata"
        steps = [
            {"step": {"name": "questionairre", "type": "INTENT", "node_id": "1",
                      "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_questionairre", "type": "BOT", "node_id": "2",
                  "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_questionairre", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "moody", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foody", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foody", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_foody", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_foody", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_moody", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "moody", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_moody", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6'}, {"node_id": "5"}]
        story_dict = {'name': story_name, 'steps': steps, 'metadata': metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = list(processor.get_multiflow_stories("test_get_empty_path_type_metadata"))
        assert multiflow_story.__len__() == 1
        assert multiflow_story[0]['metadata'] == [{'node_id': '6', 'flow_type': 'STORY'},
                                                  {'node_id': '5', 'flow_type': 'STORY'}]
        assert multiflow_story[0]['name'] == 'test_get_multiflow_stories_with_empty_path_type_metadata'

    def test_edit_training_example_duplicate(self):
        processor = MongoProcessor()
        examples = list(processor.get_training_examples("greet", "tests"))
        with pytest.raises(AppException):
            processor.edit_training_example(examples[0]["_id"], example="hey there", intent="greet", bot="tests",
                                            user="testUser")

    def test_edit_training_example_does_not_exists(self):
        processor = MongoProcessor()
        examples = list(processor.get_training_examples("greet", "tests"))
        with pytest.raises(AppException):
            processor.edit_training_example(examples[0]["_id"], example="hey there", intent="happy", bot="tests",
                                            user="testUser")

    def test_edit_training_example(self):
        processor = MongoProcessor()
        examples = list(processor.get_training_examples("greet", "tests"))
        processor.edit_training_example(examples[0]["_id"], example="hey, there", intent="greet", bot="tests",
                                        user="testUser")
        examples = list(processor.get_training_examples("greet", "tests"))
        assert any(example['text'] == "hey, there" for example in examples)

    def test_edit_training_example_case_insensitive(self):
        processor = MongoProcessor()
        examples = list(processor.get_training_examples("greet", "tests"))
        processor.edit_training_example(examples[0]["_id"], example="hello, there", intent="greet", bot="tests",
                                        user="testUser")
        examples = list(processor.get_training_examples("greet", "tests"))
        assert any(example['text'] == "hello, there" for example in examples)

    def test_edit_training_example_with_entities(self):
        processor = MongoProcessor()
        examples = list(processor.get_training_examples("greet", "tests"))
        processor.edit_training_example(examples[0]["_id"], example="[Meghalaya](location) India", intent="greet",
                                        bot="tests", user="testUser")
        examples = list(processor.get_training_examples("greet", "tests"))
        assert any(example['text'] == "[Meghalaya](location) India" for example in examples)

    def test_edit_same_training_example_with_entities(self):
        processor = MongoProcessor()
        examples = list(
            processor.add_training_example(["What is the weather today"], intent="greet", bot="tests", user="test",
                                           is_integration=False))
        processor.edit_training_example(examples[0]["_id"], example="What is the weather [today](date)", intent="greet",
                                        bot="tests", user="testUser")
        examples = list(processor.get_training_examples("greet", "tests"))
        assert any(example['text'] == "What is the weather [today](date)" for example in examples)
        processor.edit_training_example(examples[0]["_id"], example="What is the weather today", intent="greet",
                                        bot="tests", user="testUser")
        example = TrainingExamples.objects(bot="tests", status=True).get(id=examples[0]["_id"])
        assert example.text == "What is the weather today"
        assert not example.entities

    def test_edit_responses_duplicate(self):
        processor = MongoProcessor()
        responses = list(processor.get_response("utter_happy", "tests"))
        with pytest.raises(AppException):
            processor.edit_text_response(responses[0]["_id"], "Great, carry on!", name="utter_happy", bot="tests",
                                         user="testUser")

    def test_edit_responses_does_not_exist(self):
        processor = MongoProcessor()
        responses = list(processor.get_response("utter_happy", "tests"))
        with pytest.raises(AppException):
            processor.edit_text_response(responses[0]["_id"], "Great, carry on!", name="utter_greet", bot="tests",
                                         user="testUser")

    def test_edit_responses_empty_response(self):
        processor = MongoProcessor()
        responses = list(processor.get_response("utter_happy", "tests"))
        with pytest.raises(ValidationError):
            processor.edit_text_response(responses[0]["_id"], "", name="utter_happy", bot="tests",
                                         user="testUser")
        with pytest.raises(ValidationError):
            processor.edit_text_response(responses[0]["_id"], " ", name="utter_happy", bot="tests",
                                         user="testUser")

    def test_edit_responses(self):
        processor = MongoProcessor()
        responses = list(processor.get_response("utter_happy", "tests"))
        processor.edit_text_response(responses[0]["_id"], "Great!", name="utter_happy", bot="tests", user="testUser")
        responses = list(processor.get_response("utter_happy", "tests"))
        assert any(response['value']['text'] == "Great!" for response in responses if "text" in response['value'])

    def test_edit_responses_case_insensitivity(self):
        processor = MongoProcessor()
        responses = list(processor.get_response("utter_happy", "tests"))
        processor.edit_text_response(responses[0]["_id"], "That's Great!", name="utter_happy", bot="tests",
                                     user="testUser")
        responses = list(processor.get_response("utter_happy", "tests"))
        assert any(
            response['value']['text'] == "That's Great!" for response in responses if "text" in response['value'])

    @responses.activate
    def test_start_training_done_using_event(self, monkeypatch):
        responses.add(
            responses.POST,
            "http://localhost/train",
            status=200,
            match=[responses.matchers.json_params_matcher({"bot": "test_event", "user": "testUser", "token": None})],
        )
        monkeypatch.setitem(Utility.environment['model']['train'], "event_url", "http://localhost/train")
        model_path = start_training("test_event", "testUser")
        assert model_path is None

    @responses.activate
    def test_start_training_done_using_event_and_token(self, monkeypatch):
        token = Authentication.create_access_token(data={"sub": "test@gmail.com"})
        responses.add(
            responses.POST,
            "http://localhost/train",
            status=200,
            match=[responses.matchers.json_params_matcher(
                {"bot": "test_event_with_token", "user": "testUser", "token": token})],
        )
        monkeypatch.setitem(Utility.environment['model']['train'], "event_url", "http://localhost/train")
        model_path = start_training("test_event_with_token", "testUser", token)
        assert model_path is None

    @responses.activate
    def test_start_training_done_reload_event(self, monkeypatch):
        token = Authentication.create_access_token(data={"sub": "test@gmail.com"})
        bot = "tests"
        responses.add(
            responses.GET,
            f"http://localhost/api/bot/{bot}/reload",
            json='{"message": "Reloading Model!"}',
            status=200
        )
        monkeypatch.setitem(Utility.environment['model']['agent'], "url", "http://localhost/")
        model_path = start_training("tests", "testUser", token)
        assert model_path

    @responses.activate
    def test_start_training_done_reload_event_without_token(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['model']['agent'], "url", "http://localhost/")
        responses.add(
            responses.GET,
            f"http://localhost/api/bot/tests/reload",
            json='{"message": "Reloading Model!"}',
            status=200
        )
        model_path = start_training("tests", "testUser")
        assert model_path

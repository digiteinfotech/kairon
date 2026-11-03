from tests.unit_test.data_processor.data_processor_support import *  # noqa: F403
from tests.unit_test.data_processor.data_processor_support import (
    MongoProcessorTestBase,
    fast_rasa_training,
)

class TestMongoProcessor(MongoProcessorTestBase):
    def test_get_live_agent(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        live_agent = processor.get_live_agent(bot=bot)
        assert live_agent == []

    def test_enable_live_agent(self):
        processor = MongoProcessor()
        bot_settings = BotSettings.objects(bot='test_bot').get()
        bot_settings.live_agent_enabled = True
        bot_settings.save()
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request_data = {
            "bot_response": "connecting to live agent",
            "dispatch_bot_response": False,
        }
        result = processor.enable_live_agent(request_data=request_data, bot=bot, user=user)
        assert result is True

    def test_get_live_agent_after_enabled(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        live_agent = processor.get_live_agent(bot=bot)
        print(live_agent)
        assert live_agent == {'name': 'live_agent_action', 'bot_response': 'connecting to live agent', 'agent_connect_response': 'Connected to live agent', 'agent_disconnect_response': 'Disconnected from live agent', 'agent_not_available_response': 'No agents available', 'dispatch_bot_response': False, 'dispatch_agent_connect_response': True, 'dispatch_agent_disconnect_response': True, 'dispatch_agent_not_available_response': True}


    def test_enable_live_agent_already_exist(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request_data = {
            "bot_response": "connecting to live agent",
            "dispatch_bot_response": False,
        }
        result = processor.enable_live_agent(request_data=request_data, bot=bot, user=user)
        assert result is False

    def test_edit_live_agent(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request_data = {
            "bot_response": "connecting to different live agent...",
            "dispatch_bot_response": True,
        }
        result = processor.edit_live_agent(request_data=request_data, bot=bot, user=user)

        live_agent = processor.get_live_agent(bot=bot)
        print(live_agent)
        assert live_agent == {'name': 'live_agent_action', 'bot_response': 'connecting to different live agent...', 'agent_connect_response': 'Connected to live agent', 'agent_disconnect_response': 'Disconnected from live agent', 'agent_not_available_response': 'No agents available', 'dispatch_bot_response': True, 'dispatch_agent_connect_response': True, 'dispatch_agent_disconnect_response': True, 'dispatch_agent_not_available_response': True}

    def test_list_live_agent_actions(self):
        processor = MongoProcessor()
        res = processor.load_live_agent_action(bot='test_bot')
        assert res == {'live_agent_action': [
                            {'name': 'live_agent_action',
                             'bot_response': 'connecting to different live agent...',
                             'agent_connect_response': 'Connected to live agent',
                             'agent_disconnect_response': 'Disconnected from live agent',
                             'agent_not_available_response': 'No agents available',
                             'dispatch_bot_response': True,
                             'dispatch_agent_connect_response': True,
                             'dispatch_agent_disconnect_response': True,
                             'dispatch_agent_not_available_response': True}
                        ]}
        gen = processor.list_live_agent_actions('test_bot', True)
        list_data = list(gen)
        assert list_data[0]['name'] == 'live_agent_action'
        assert list_data[0]['bot_response'] == 'connecting to different live agent...'
        assert list_data[0].get('_id')
        assert len(list_data[0]['_id']) == 24

    def test_enable_live_agent_service_not_available(self):
        bot = "test_bot"
        user = "test_user"
        request_data = {"key": "value"}
        processor = MongoProcessor() 
        with patch.object(processor, 'is_live_agent_enabled', return_value=False):
            with pytest.raises(AppException, match="Live agent service is not available for the bot"):
                processor.enable_live_agent(request_data, bot, user)

    def test_disable_live_agent(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request_data = {
            "bot_response": "connecting to different live agent...",
            "dispatch_bot_response": True,
        }
        result = processor.disable_live_agent(bot=bot, user=user)

        live_agent = processor.get_live_agent(bot=bot)
        assert live_agent == []

    def test_edit_live_agent_does_not_exist(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request_data = {
            "bot_response": "connecting to different live agent...",
            "dispatch_bot_response": True,
        }
        with pytest.raises(AppException, match=f'Live agent not enabled for the bot'):
            result = processor.edit_live_agent(request_data=request_data, bot=bot, user=user)


    def test_get_callback_service_log_with_conditions(self):
        bot = "test_bot"
        service = MongoProcessor()

        with patch('kairon.shared.callback.data_objects.CallbackLog.get_logs', return_value=(["log1", "log2"], 2)) as mock_get_logs:
            name = "test_callback"
            sender_id = "test_sender"
            channel = "test_channel"
            identifier = "test_identifier"
            start = 0
            limit = 100

            logs, total_count = service.get_callback_service_log(
                bot=bot,
                name=name,
                sender_id=sender_id,
                channel=channel,
                identifier=identifier,
                start=start,
                limit=limit
            )

            expected_query = {
                "bot": bot,
                "callback_name": name,
                "sender_id": sender_id,
                "channel": channel,
                "identifier": identifier
            }
            mock_get_logs.assert_called_once_with(expected_query, start, limit)
            assert logs == ["log1", "log2"]
            assert total_count == 2

    def test_get_callback_service_log_without_conditions(self):
        bot = "test_bot"
        service = MongoProcessor()

        with patch('kairon.shared.callback.data_objects.CallbackLog.get_logs', return_value=(["log1", "log2"], 2)) as mock_get_logs:

            logs, total_count = service.get_callback_service_log(bot=bot)

            expected_query = {"bot": bot}
            mock_get_logs.assert_called_once_with(expected_query, 0, 100)
            assert logs == ["log1", "log2"]
            assert total_count == 2

    def test_auditlog_event_config_does_not_exist(self):
        result = MongoProcessor.get_auditlog_event_config("nobot")
        assert result == {}

    def test_auditlog_event_config_does_not_exist_none(self):
        result = MongoProcessor.get_auditlog_event_config(None)
        assert result == {}

    @pytest.mark.asyncio
    async def test_load_from_path(self):
        processor = MongoProcessor()
        result = await (
            processor.save_from_path(
                "./tests/testing_data/initial", bot="tests", user="testUser"
            )
        )
        assert result is None

    def test_edit_bot_settings_does_not_exist(self):
        processor = MongoProcessor()
        bot_settings = {
            "analytics": {'fallback_intent': 'nlu_fallback'},
        }
        with pytest.raises(AppException, match='Bot Settings for the bot not found'):
            processor.edit_bot_settings(bot_settings, 'new_test_bot', 'test')

    def test_edit_bot_settings(self):
        processor = MongoProcessor()
        BotSettings(bot='new_test_bot', user='test').save()
        bot_settings = {
            "analytics": {'fallback_intent': 'utter_please_rephrase'},
        }
        processor.edit_bot_settings(bot_settings, 'new_test_bot', 'test')
        updated_settings = processor.get_bot_settings('new_test_bot', 'test')
        assert not updated_settings.ignore_utterances
        assert not updated_settings.force_import
        assert updated_settings.status
        assert updated_settings.timestamp
        assert updated_settings.user
        assert updated_settings.bot
        assert updated_settings.analytics.to_mongo().to_dict() == {'fallback_intent': 'utter_please_rephrase'}
        assert updated_settings.llm_settings.to_mongo().to_dict() == {'enable_faq': False, 'provider': 'openai'}

    def test_abort_current_event_with_no_model_training_event(self):
        mongo_processor = MongoProcessor()
        bot = "test_bot"
        user = "test_user"
        with pytest.raises(AppException, match="No Enqueued model_training present for this bot."):
            mongo_processor.abort_current_event(bot=bot, user=user, event_type=EventClass.model_training)

    def test_abort_current_event_with_no_model_testing_event(self):
        mongo_processor = MongoProcessor()
        bot = "test_bot"
        user = "test_user"
        with pytest.raises(AppException, match="No Enqueued model_testing present for this bot."):
            mongo_processor.abort_current_event(bot=bot, user=user, event_type=EventClass.model_testing)

    def test_abort_current_event_with_no_delete_history_event(self):
        mongo_processor = MongoProcessor()
        bot = "test_bot"
        user = "test_user"
        with pytest.raises(AppException, match="No Enqueued delete_history present for this bot."):
            mongo_processor.abort_current_event(bot=bot, user=user, event_type=EventClass.delete_history)

    def test_abort_current_event_with_no_data_importer_event(self):
        mongo_processor = MongoProcessor()
        bot = "test_bot"
        user = "test_user"
        with pytest.raises(AppException, match="No Enqueued data_importer present for this bot."):
            mongo_processor.abort_current_event(bot=bot, user=user, event_type=EventClass.data_importer)

    @patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
    def test_abort_current_event_with_model_training(self, mock_event_server):
        mongo_processor = MongoProcessor()
        bot = "test_bot"
        user = "test_user"
        mock_event_server.return_value = {"success": True, "message": "Event triggered successfully!"}
        ModelProcessor.set_training_status(bot=bot, user=user, status=EVENT_STATUS.ENQUEUED.value)
        mongo_processor.abort_current_event(bot=bot, user=user, event_type=EventClass.model_training)
        model_training_object = ModelTraining.objects(bot=bot).get()
        assert model_training_object.status == EVENT_STATUS.ABORTED.value

    @patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
    def test_abort_current_event_with_model_testing(self, mock_event_server):
        mongo_processor = MongoProcessor()
        bot = "test_bot"
        user = "test_user"
        mock_event_server.return_value = {"success": True, "message": "Event triggered successfully!"}
        ModelTestingLogProcessor.log_test_result(bot=bot, user=user, event_status=EVENT_STATUS.ENQUEUED.value)
        mongo_processor.abort_current_event(bot=bot, user=user, event_type=EventClass.model_testing)
        model_testing_object = ModelTestingLogs.objects(bot=bot).get()
        assert model_testing_object.event_status == EVENT_STATUS.ABORTED.value

    @pytest.mark.asyncio
    async def test_save_from_path_yml(self):
        processor = MongoProcessor()
        result = await (
            processor.save_from_path(
                "./tests/testing_data/yml_training_files", bot="test_load_yml", user="testUser"
            )
        )
        assert result is None
        assert len(list(Intents.objects(bot="test_load_yml", user="testUser", use_entities=False))) == 5
        assert len(list(Intents.objects(bot="test_load_yml", user="testUser", use_entities=True))) == 23
        assert len(
            list(Slots.objects(bot="test_load_yml", user="testUser", influence_conversation=True, status=True))) == 25
        assert len(
            list(Slots.objects(bot="test_load_yml", user="testUser", influence_conversation=False, status=True))) == 14
        multiflow_stories = processor.load_multiflow_stories_yaml(bot='test_load_yml')
        print(multiflow_stories['multiflow_story'][0]['events'][0])
        step_data = multiflow_stories['multiflow_story'][0]['events'][0]['step']
        assert step_data['component_id'] is not None
        fields = ['block_name', 'start_checkpoints', 'end_checkpoints', 'events', 'metadata', 'template_type']
        for item in fields:
            assert item in multiflow_stories['multiflow_story'][0].keys()

    def test_bot_id_change(self):
        bot_id = Slots.objects(bot="test_load_yml", user="testUser", influence_conversation=False, name='bot').get()
        assert bot_id['initial_value'] == "test_load_yml"

    def test_get_action_server_logs_not_implicit(self):
        bot = "test_bot"
        request_params = {"key": "value", "key2": "value2"}

        # This log has implicit trigger_info (default), should be returned
        log_implicit = ActionServerLogs(
            intent="intent1",
            action="http_action",
            sender="sender_id",
            timestamp=datetime(2021, 4, 11, 11, 39, 48, 376000),
            request_params=request_params,
            api_response="Response",
            bot_response="Bot Response",
            bot=bot,
            trigger_info=TriggerInfo(trigger_id="123456", trigger_name="parallel_action", trigger_type="parallel_action")
        )
        log_implicit.save()

        # This log has explicit trigger_info, should be filtered out
        ActionServerLogs(
            intent="intent2",
            action="http_action2",
            sender="sender_id",
            url="http://kairon-api.digite.com/api/bot",
            request_params=request_params,
            api_response="Response",
            bot_response="Bot Response",
            bot=bot,
            status=STATUSES.FAIL.value,
            trigger_info=TriggerInfo(trigger_id="",trigger_name="explicit_action", trigger_type="parallel_action")
        ).save()

        processor = MongoProcessor()
        logs = list(processor.get_action_server_logs(bot))

        # Only the first one should be returned
        assert len(logs) == 1
        assert logs[0]['action'] == "http_action2"
        ActionServerLogs.objects(action="http_action").delete()
        ActionServerLogs.objects(action="http_action2").delete()

    def test_fetch_action_logs_for_parallel_action_by_id(self):
        bot = "test_bot_parallel"
        a1, a2, a3 = "action1", "action2", "action3"

        # 1) Create the ParallelActionConfig and grab its ObjectId string
        cfg = ParallelActionConfig(
            name="parallel_action",
            bot=bot,
            user="test_user",
            actions=[a1, a2],
            response_text="resp"
        ).save()
        trigger_id = str(cfg.id)

        # Patch _id field manually via __raw__ to simulate actual behavior
        parallel = ParallelActionConfig.objects(__raw__={"_id": ObjectId(trigger_id)}).first()
        assert parallel is not None  # safety check

        # 2) One log for the parallel action itself (ignored)
        ActionServerLogs(intent="i0", action=cfg.name, sender="s0", bot=bot,
                         trigger_info={"trigger_id": ""}).save()
        # 3) Two logs for the child actions (should be returned)
        ActionServerLogs(intent="i1", action=a1, sender="s1", bot=bot, trigger_info={"trigger_id": trigger_id}).save()
        ActionServerLogs(intent="i2", action=a2, sender="s2", bot=bot, trigger_info={"trigger_id": trigger_id}).save()
        # 4) One unrelated log (ignored)
        ActionServerLogs(intent="i3", action=a3, sender="s3", bot=bot,
                         trigger_info={"trigger_id": "some_other_id"}).save()

        # 5) Now call the function
        logs = MongoProcessor().fetch_action_logs_for_parallel_action(trigger_id, bot)

        # 6) Assert only the two child-action logs come back
        assert {log["action"] for log in logs} == {a1, a2}

        # Cleanup
        ParallelActionConfig.objects(id=cfg.id).delete()
        ActionServerLogs.objects(action__in=[cfg.name, a1, a2, a3]).delete()

    def test_fetch_action_logs_for_parallel_action_parallel_action_not_found(self):
        bot = "test_bot_parallel_2"
        trigger_id = str(ObjectId())  # valid ObjectId, but not in the DB

        processor = MongoProcessor()
        with pytest.raises(AppException, match="Logs for Actions in Parallel Action not found"):
            processor.fetch_action_logs_for_parallel_action(trigger_id, bot)

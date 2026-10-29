from tests.unit_test.data_processor.data_processor_support import *  # noqa: F403
from tests.unit_test.data_processor.data_processor_support import fast_rasa_training

class TestModelProcessor:

    @pytest.fixture(autouse=True, scope='class')
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection())
        yield None
        Utility.environment['notifications']['enable'] = False

    @pytest.fixture
    def test_set_training_status_inprogress(self):
        ModelProcessor.set_training_status("tests", "testUser", "Inprogress")
        model_training = ModelTraining.objects(bot="tests", status="Inprogress")
        return model_training

    def test_set_training_status_Done(self, test_set_training_status_inprogress):
        assert test_set_training_status_inprogress.__len__() == 1
        assert test_set_training_status_inprogress.first().bot == "tests"
        assert test_set_training_status_inprogress.first().user == "testUser"
        assert test_set_training_status_inprogress.first().status == "Inprogress"
        assert test_set_training_status_inprogress.first().model_config == MongoProcessor().load_config("tests")
        training_status_inprogress_id = test_set_training_status_inprogress.first().id

        ModelProcessor.set_training_status(bot="tests",
                                           user="testUser",
                                           status="Done",
                                           model_path="model_path"
                                           )
        model_training = ModelTraining.objects(bot="tests", status="Done")
        ids = [model.id for model in model_training]
        index = ids.index(training_status_inprogress_id)
        assert model_training.count() == 5
        assert training_status_inprogress_id in ids
        assert model_training[index].bot == "tests"
        assert model_training[index].user == "testUser"
        assert model_training[index].status == "Done"
        assert model_training[index].model_path == "model_path"
        assert ModelTraining.objects(bot="tests", status="Inprogress").__len__() == 0

    def test_set_training_status_Fail(self, test_set_training_status_inprogress):
        assert test_set_training_status_inprogress.__len__() == 1
        assert test_set_training_status_inprogress.first().bot == "tests"
        assert test_set_training_status_inprogress.first().user == "testUser"
        assert test_set_training_status_inprogress.first().status == "Inprogress"
        training_status_inprogress_id = test_set_training_status_inprogress.first().id

        ModelProcessor.set_training_status(bot="tests",
                                           user="testUser",
                                           status="Fail",
                                           model_path=None,
                                           exception="exception occurred while training model."
                                           )
        model_training = ModelTraining.objects(bot="tests", status="Fail")

        assert model_training.__len__() == 1
        assert model_training.first().id == training_status_inprogress_id
        assert model_training.first().bot == "tests"
        assert model_training.first().user == "testUser"
        assert model_training.first().status == "Fail"
        assert model_training.first().model_path is None
        assert model_training.first().exception == "exception occurred while training model."
        assert ModelTraining.objects(bot="tests", status="Inprogress").__len__() == 0

    def test_is_training_inprogress_False(self):
        actual_response = ModelProcessor.is_training_inprogress("tests")
        assert actual_response is False

    def test_is_training_inprogress_with_aborted(self):
        ModelProcessor.set_training_status("testbot", "testuser", "Aborted")
        model_training = ModelTraining.objects(bot="testbot", status="Aborted")
        actual_response = ModelProcessor.is_training_inprogress("tests", False)
        assert actual_response is False

    def test_is_training_inprogress_True(self, test_set_training_status_inprogress):
        assert test_set_training_status_inprogress.__len__() == 1
        assert test_set_training_status_inprogress.first().bot == "tests"
        assert test_set_training_status_inprogress.first().user == "testUser"
        assert test_set_training_status_inprogress.first().status == "Inprogress"

        actual_response = ModelProcessor.is_training_inprogress("tests", False)
        assert actual_response is True

    def test_is_training_inprogress_exception(self, test_set_training_status_inprogress):
        with pytest.raises(AppException) as exp:
            assert ModelProcessor.is_training_inprogress("tests")

        assert str(exp.value) == "Previous model training in progress."

    def test_is_daily_training_limit_exceeded_False(self, monkeypatch):
        bot = 'tests'
        bot_settings = BotSettings.objects(bot=bot).get()
        bot_settings.training_limit_per_day = 8
        bot_settings.save()
        actual_response = ModelProcessor.is_daily_training_limit_exceeded(bot)
        assert actual_response is False

    def test_is_daily_training_limit_exceeded_True(self, monkeypatch):
        bot = 'tests'
        bot_settings = BotSettings.objects(bot=bot).get()
        bot_settings.training_limit_per_day = 0
        bot_settings.save()
        actual_response = ModelProcessor.is_daily_training_limit_exceeded(bot, False)
        assert actual_response is True

    def test_is_daily_training_limit_exceeded_exception(self, monkeypatch):
        bot = 'tests'
        bot_settings = BotSettings.objects(bot=bot).get()
        bot_settings.training_limit_per_day = 0
        bot_settings.save()
        with pytest.raises(AppException) as exp:
            assert ModelProcessor.is_daily_training_limit_exceeded(bot)

        assert str(exp.value) == "Daily model training limit exceeded."

    @patch("kairon.chat.agent.agent.KaironAgent.load", autospec=True)
    def test_start_training_load_model_fail(self, mock_agent, monkeypatch):
        def mongo_store(*args, **kwargs):
            return None

        monkeypatch.setattr(Utility, "get_local_mongo_store", mongo_store)
        mock_agent.side_effect = Exception("Failed to load the model for the bot.")
        start_training("tests", "testUser")
        model_training = ModelTraining.objects(bot="tests", status="Fail")
        assert model_training.__len__() == 2
        assert model_training[1].exception in str("Failed to load the model for the bot.")

    def test_train_model_for_bot(self):
        model = train_model_for_bot("tests")
        created_model_file = os.path.basename(model)
        tar_files = glob.glob('models/tests/*.tar.gz')
        actual_model_file = os.path.basename(tar_files[0])
        folder = os.path.join("models/tests", '*.tar.gz')

        assert model
        assert len(list(glob.glob(folder))) == 1
        assert actual_model_file == created_model_file

    def test_get_training_history(self):
        actual_response = ModelProcessor.get_training_history("tests")
        assert actual_response

    def test_save_auditlog_event_config_without_eventurl(self):
        bot = "tests"
        user = "testuser"
        data = {}
        with pytest.raises(ValidationError, match='Event url can not be empty'):
            MongoProcessor.save_auditlog_event_config(bot=bot, user=user, data=data)

    def test_save_auditlog_event_config_without_headers(self):
        bot = "tests"
        user = "testuser"
        data = {"ws_url": "http://localhost:5000/event_url"}
        MongoProcessor.save_auditlog_event_config(bot=bot, user=user, data=data)
        result = MongoProcessor.get_auditlog_event_config(bot)
        assert result.get("ws_url") == data.get("ws_url")
        headers = json.loads(result.get("headers"))
        assert headers == {}

    @responses.activate
    def test_save_auditlog_event_config(self):
        bot = "tests"
        user = "testuser"
        data = {"ws_url": "http://localhost:5000/event_url",
                "headers": {'Autharization': '123456789'},
                "method": "GET"}
        responses.add(
            responses.GET,
            "http://localhost:5000/event_url",
            status=200,
            json='{"message": "success"}'
        )
        MongoProcessor.save_auditlog_event_config(bot=bot, user=user, data=data)
        result = MongoProcessor.get_auditlog_event_config(bot)
        assert result.get("ws_url") == data.get("ws_url")
        headers = json.loads(result.get("headers"))
        assert len(headers.keys()) == 1
        assert result.get("method") == "GET"

    def test_auditlog_for_chat_client_config(self):
        auditlog_data = list(AuditLogData.objects(attributes=[{"key": "bot", "value": "test"}], user='testUser',
                                                  entity='ChatClientConfig').order_by('-timestamp'))
        assert len(auditlog_data) > 0
        assert auditlog_data[0] is not None
        assert auditlog_data[0].attributes[0]["value"] == "test"
        assert auditlog_data[0].user == "testUser"
        assert auditlog_data[0].entity == "ChatClientConfig"

    def test_auditlog_for_intent(self):
        auditlog_data = list(
            AuditLogData.objects(attributes=[{"key": "bot", "value": "tests"}], user='testUser', action='save',
                                 entity='Intents').order_by('-timestamp'))
        assert len(auditlog_data) > 0
        assert auditlog_data is not None
        assert auditlog_data[0].attributes[0]["value"] == "tests"
        assert auditlog_data[0].user == "testUser"
        assert auditlog_data[0].entity == "Intents"

        auditlog_data = list(
            AuditLogData.objects(attributes=[{"key": "bot", "value": "tests"}], user='testUser', action='delete',
                                 entity='Intents').order_by('-timestamp'))
        # No hard delete supported for intents
        assert len(auditlog_data) == 8

    def test_get_auditlog_for_invalid_bot(self):
        bot = "invalid"
        page_size = 100
        auditlog_data, row_cnt = MongoProcessor.get_auditlog_for_bot(bot, page_size=page_size)
        assert auditlog_data == []

    def test_get_auditlog_for_bot_top_n_default(self):
        bot = "test"
        page_size = 100
        auditlog_data, row_cnt = MongoProcessor.get_auditlog_for_bot(bot, page_size=page_size)
        assert len(auditlog_data) > 90

    def test_get_auditlog_for_bot_date_range(self):
        bot = "test"
        from_date = utc_now().date() - timedelta(days=1)
        to_date = utc_now().date()
        page_size = 100
        auditlog_data, row_cnt = MongoProcessor.get_auditlog_for_bot(bot, from_date=from_date, to_date=to_date,
                                                                     page_size=page_size)
        assert len(auditlog_data) > 90

    def test_get_auditlog_for_bot_top_50(self):
        bot = "test"
        from_date = utc_now().date() - timedelta(days=1)
        to_date = utc_now().date()
        page_size = 50
        auditlog_data, row_cnt = MongoProcessor.get_auditlog_for_bot(bot, from_date=from_date, to_date=to_date,
                                                                     page_size=page_size)
        assert len(auditlog_data) == 50

    def test_get_auditlog_from_date_to_date_none(self):
        bot = "test"
        from_date = None
        to_date = None
        page_size = 50
        auditlog_data, row_cnt = MongoProcessor.get_auditlog_for_bot(bot, from_date=from_date, to_date=to_date,
                                                                     page_size=page_size)
        assert len(auditlog_data) == 50

    def test_edit_training_example_empty_or_blank(self):
        processor = MongoProcessor()
        examples = list(processor.get_training_examples("greet", "tests"))
        with pytest.raises(AppException, match="Training Example cannot be empty or blank spaces"):
            processor.edit_training_example(examples[0]["_id"], example="", intent="greet", bot="tests",
                                            user="testUser")

    def test_add_custom_form_attached_does_not_exist(self):
        processor = MongoProcessor()
        jsondata = {"type": "section",
                    "text": {
                        "text": "Make a bet on when the world will end:",
                        "type": "mrkdwn",
                        "accessory": {"type": "datepicker",
                                      "initial_date": "2019-05-21",
                                      "placeholder": {"type": "plain_text",
                                                      "text": "Select a date"}}}}
        with pytest.raises(AppException, match="Form 'unknown' does not exists"):
            assert processor.add_custom_response(jsondata, "utter_custom", "tests", "testUser", "unknown")

    def test_get_model_testing_accuracy(self):
        account = {
            "account": "test_accuarcy",
            "email": "divya.veeravelly@digite.com",
            "first_name": "test_first",
            "last_name": "test_last",
            "password": SecretStr("Quailink@46")
        }

        loop = asyncio.new_event_loop()
        user_detail, mail, link = loop.run_until_complete(AccountProcessor.account_setup(account_setup=account))

        pytest.account = user_detail['account']
        bot1 = AccountProcessor.add_bot("bot_1", 1, "divya.veeravelly@digite.com", False)
        bot2 = AccountProcessor.add_bot("bot_2", 1, "divya.veeravelly@digite.com", False)
        u1 = ModelTestingLogs()
        u1.data = {"intent_evaluation": {"accuracy": 0.6424565337899992}}
        u1.type = 'nlu'
        u1.bot = bot1["_id"].__str__()
        u1.user = "divya"
        BotSettings(bot=u1.bot, user="test", pos_enabled=False).save()
        u1.save()

        u2 = ModelTestingLogs()
        u2.data = {"intent_evaluation": {"accuracy": 0.9875645647434565}}
        u2.type = 'nlu'
        u2.bot = bot2["_id"].__str__()
        u2.user = "divya"
        BotSettings(bot=u2.bot, user="test", pos_enabled=False).save()
        u2.save()
        result = AccountProcessor.get_model_testing_accuracy_of_all_accessible_bots(1, "divya.veeravelly@digite.com")
        assert result[bot1["_id"].__str__()] == 0.6424565337899992
        assert result[bot2["_id"].__str__()] == 0.9875645647434565

    def test_get_model_testing_accuracy_field_not_exists(self):
        account = {
            "account": "test_accuarcy_log",
            "email": "abcd@xyz.com",
            "first_name": "test_first_1",
            "last_name": "test_last_1",
            "password": SecretStr("Quailink@46")
        }

        loop = asyncio.new_event_loop()
        user_detail, mail, link = loop.run_until_complete(AccountProcessor.account_setup(account_setup=account))

        pytest.account = user_detail['account']
        bot3 = AccountProcessor.add_bot("bot_3", 2, "abcd@xyz.com", False)
        bot4 = AccountProcessor.add_bot("bot_4", 2, "abcd@xyz.com", False)

        u1 = ModelTestingLogs()
        u1.data = {"intent_evaluation": {}}
        u1.type = 'nlu'
        u1.bot = bot3["_id"].__str__()
        u1.user = "divya"
        u1.save()

        u2 = ModelTestingLogs()
        u2.data = {"intent_evaluation": {}}
        u2.type = 'nlu'
        u2.bot = bot4["_id"].__str__()
        u2.user = "divya"
        u2.save()
        result = AccountProcessor.get_model_testing_accuracy_of_all_accessible_bots(2, "abcd@xyz.com")
        assert result[bot3["_id"].__str__()] is None
        assert result[bot4["_id"].__str__()] is None

    def test_get_model_testing_accuracy_mutliple_logs(self):
        account = {
            "account": "test_accuarcy_logs",
            "email": "wxyz@abcd.com",
            "first_name": "test_first_2",
            "last_name": "test_last_2",
            "password": SecretStr("abcdefg@123")
        }

        loop = asyncio.new_event_loop()
        user_detail, mail, link = loop.run_until_complete(AccountProcessor.account_setup(account_setup=account))

        pytest.account = user_detail['account']
        bot_a = AccountProcessor.add_bot("bot_a", 3, "wxyz@abcd.com", False)
        bot_c = AccountProcessor.add_bot("bot_c", 3, "wxyz@abcd.com", False)

        u1 = ModelTestingLogs()
        u1.type = "nlu"
        u1.user = "wxyz@abcd.com"
        u1.data = {"intent_evaluation": {}}
        u1.bot = bot_a["_id"].__str__()
        u1.save()

        u3 = ModelTestingLogs()
        u3.type = "nlu"
        u3.user = "wxyz@abcd.com"
        u3.bot = bot_a["_id"].__str__()
        u3.data = {"intent_evaluation": {"accuracy": 0.9424565337899992}}
        u3.save()

        u2 = ModelTestingLogs()
        u2.type = "nlu"
        u2.user = "wxyz@abcd.com"
        u2.bot = bot_a["_id"].__str__()
        u2.data = {"intent_evaluation": {}}
        u2.save()

        u4 = ModelTestingLogs()
        u4.type = "nlu"
        u4.user = "wxyz@abcd.com"
        u4.data = {"intent_evaluation": {"accuracy": 0.8424565337899992}}
        u4.bot = bot_c["_id"].__str__()
        u4.save()

        u5 = ModelTestingLogs()
        u5.type = "nlu"
        u5.user = "wxyz@abcd.com"
        u5.bot = bot_c["_id"].__str__()
        u5.data = {"intent_evaluation": {"accuracy": None}}
        u5.save()

        u6 = ModelTestingLogs()
        u6.type = "nlu"
        u6.user = "wxyz@abcd.com"
        u6.bot = bot_c["_id"].__str__()
        u6.data = {"intent_evaluation": {}}
        u6.save()

        result = AccountProcessor.get_model_testing_accuracy_of_all_accessible_bots(3, "wxyz@abcd.com")
        assert result[bot_a["_id"].__str__()] == 0.9424565337899992
        assert result[bot_c["_id"].__str__()] == 0.8424565337899992

    def test_auditlog_for_data_with_encrypted_field(self):
        start_time = utc_now() - timedelta(days=1)
        end_time = utc_now() + timedelta(days=1)

        processor = MongoProcessor()
        bot = 'secret'
        user = 'secret_user'
        key = "auditlog"
        value = "secret-value"
        processor.add_secret(key, value, bot, user)

        config = {
            "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K",
            "slack_signing_secret": "79f036b9894eef17c064213b90d1042b",
            "client_id": "3396830255712.3396861654876869879",
            "client_secret": "cf92180a7634d90bf42a217408376878"
        }
        connector_type = "slack"
        meta_config = {}

        Channels(bot=bot, user=user, connector_type=connector_type, config=config, meta_config=meta_config).save()

        auditlog_data = processor.get_logs("secret", "audit_logs", start_time, end_time)
        assert auditlog_data[0]["attributes"][0]["value"] == bot
        assert auditlog_data[0]["entity"] == "Channels"
        assert auditlog_data[0]["data"]["config"] != config

        assert auditlog_data[2]["attributes"][0]["value"] == bot
        assert auditlog_data[2]["entity"] == "KeyVault"
        assert auditlog_data[2]["data"]["value"] != value

    def test_add_schedule_action(self):
        bot = "testbot"
        user = "testuser"
        expected_data = {
            "name": "test_schedule_action",
            "schedule_time": {"value": "2024-08-06T09:00:00.000+0530", "parameter_type": "value"},
            "timezone": None,
            "schedule_action": "test_pyscript",
            "response_text": "action scheduled",
            "params_list": [
                {
                    "key": "param_key",
                    "value": "param_1",
                    "parameter_type": "value",
                }
            ],
            "dispatch_bot_response": True
        }

        processor = MongoProcessor()
        processor.add_schedule_action(expected_data, bot, user)

        actual_data = list(processor.list_schedule_action(bot))
        assert expected_data.get("name") == actual_data[0]["name"]
        for data in actual_data:
            data.pop("_id")
        assert actual_data == [
            {
                'name': 'test_schedule_action',
                'schedule_time': {'value': '2024-08-06T09:00:00.000+0530', 'parameter_type': 'value'},
                'timezone': 'UTC',
                'schedule_action': 'test_pyscript',
                'response_text': 'action scheduled',
                'schedule_action_type': 'pyscript',
                'params_list': [
                    {
                        '_cls': 'CustomActionRequestParameters',
                        'key': 'param_key',
                        'encrypt': False,
                        'value': 'param_1',
                        'parameter_type': 'value'
                    }
                ],
                'dispatch_bot_response': True
            }
        ]

    def test_add_schedule_action_duplicate(self):
        bot = "testbot"
        user = "testuser"
        expected_data = {
            "name": "test_schedule_action",
            "schedule_time": {"value": "2024-08-06T09:00:00.000+0530", "parameter_type": "value"},
            "timezone": None,
            "schedule_action": "test_pyscript",
            "response_text": "action scheduled",
            "params_list": [],
            "dispatch_bot_response": True
        }

        processor = MongoProcessor()
        with pytest.raises(AppException, match="Action exists!"):
            processor.add_schedule_action(expected_data, bot, user)

    def test_add_schedule_action_with_empty_name(self):
        bot = "testbot"
        user = "testuser"
        expected_data = {
            "name": "",
            "schedule_time": {"value": "2024-08-06T09:00:00.000+0530", "parameter_type": "value"},
            "timezone": None,
            "schedule_action": "test_pyscript",
            "response_text": "action scheduled",
            "params_list": [],
            "dispatch_bot_response": True
        }

        processor = MongoProcessor()
        with pytest.raises(Exception, match="Schedule action name can not be empty"):
            scheduled_acition = ScheduleActionRequest(**expected_data)
            processor.add_schedule_action(scheduled_acition, bot, user)

    def test_add_schedule_action_with_no_schedule_action(self):
        bot = "testbot"
        user = "testuser"
        expected_data = {
            "name": "test_schedule_action",
            "schedule_time": {"value": "2024-08-06T09:00:00.000+0530", "parameter_type": "value"},
            "timezone": None,
            "schedule_action": None,
            "response_text": "action scheduled",
            "params_list": [],
            "dispatch_bot_response": True
        }

        processor = MongoProcessor()
        with pytest.raises(Exception, match="Schedule action can not be empty, it is needed to execute on schedule time"):
            scheduled_acition = ScheduleActionRequest(**expected_data)
            processor.add_schedule_action(scheduled_acition.model_dump(), bot, user)

    def test_update_schedule_action_schedule_time(self):
        bot = "testbot"
        user = "testuser"
        expected_data = {
            "name": "test_schedule_action",
            "schedule_time": {"value": "2024-08-07T09:00:00.000+0530", "parameter_type": "value"},
            "timezone": None,
            "schedule_action": "test_pyscript",
            "response_text": "action scheduled",
            "params_list": [],
            "dispatch_bot_response": True
        }

        processor = MongoProcessor()
        processor.update_schedule_action(expected_data, bot, user)
        actual_data = list(processor.list_schedule_action(bot))
        assert expected_data.get("schedule_time").get("value") == actual_data[0]["schedule_time"]["value"]

    def test_update_schedule_action_scheduled_action(self):
        bot = "testbot"
        user = "testuser"
        expected_data = {
            "name": "test_schedule_action",
            "schedule_time": {"value": "2024-08-06T09:00:00.000+0530", "parameter_type": "value"},
            "timezone": None,
            "schedule_action": "test_pyscript_new",
            "response_text": "action scheduled",
            "params_list": [],
            "dispatch_bot_response": True
        }

        processor = MongoProcessor()
        processor.update_schedule_action(expected_data, bot, user)

        actual_data = list(processor.list_schedule_action(bot))
        assert expected_data.get("name") == actual_data[0]["name"]
        assert expected_data.get("schedule_action") == actual_data[0]["schedule_action"]

    def test_update_schedule_action_params_list(self):
        bot = "testbot"
        user = "testuser"
        expected_data = {
            "name": "test_schedule_action",
            "schedule_time": {"value": "2024-08-06T09:00:00.000+0530", "parameter_type": "value"},
            "timezone": None,
            "schedule_action": "test_pyscript_new",
            "response_text": "action scheduled",
            "params_list": [
                {
                    "key": "updated_key",
                    "value": "param_2",
                    "parameter_type": "value",
                }
            ],
            "dispatch_bot_response": True
        }

        processor = MongoProcessor()
        processor.update_schedule_action(expected_data, bot, user)

        actual_data = list(processor.list_schedule_action(bot))
        assert expected_data.get("name") == actual_data[0]["name"]
        assert expected_data.get("schedule_action") == actual_data[0]["schedule_action"]
        for data in actual_data:
            data.pop("_id")
        assert actual_data == [
            {
                'name': 'test_schedule_action',
                'schedule_time': {'value': '2024-08-06T09:00:00.000+0530', 'parameter_type': 'value'},
                'timezone': 'UTC',
                'schedule_action': 'test_pyscript_new',
                'schedule_action_type': 'pyscript',
                'response_text': 'action scheduled',
                'params_list': [
                    {
                        '_cls': 'CustomActionRequestParameters',
                        'key': 'updated_key',
                        'encrypt': False,
                        'value': 'param_2',
                        'parameter_type': 'value'
                    }
                ],
                'dispatch_bot_response': True
            }
        ]

    def test_update_schedule_action_schedule_time_param_type(self):
        bot = "testbot"
        user = "testuser"
        expected_data = {
            "name": "test_schedule_action",
            "schedule_time": {"value": "delivery_time", "parameter_type": "slot"},
            "timezone": None,
            "schedule_action": "test_pyscript",
            "response_text": "action scheduled",
            "params_list": [],
            "dispatch_bot_response": True
        }

        processor = MongoProcessor()
        processor.update_schedule_action(expected_data, bot, user)
        actual_data = list(processor.list_schedule_action(bot))
        assert "slot" == actual_data[0]["schedule_time"]["parameter_type"]
        assert "delivery_time" == actual_data[0]["schedule_time"]["value"]

    def test_get_schedule_action_by_name(self):
        name = "test_schedule_action"
        bot = "testbot"
        user = "testuser"
        processor = MongoProcessor()
        action = processor.get_schedule_action(bot, name)
        assert action is not None

    def test_get_schedule_action_by_name_not_exists(self):
        name = "test_schedule_action_not_exisits"
        bot = "testbot"
        user = "testuser"
        processor = MongoProcessor()
        action = processor.get_schedule_action(bot, name)
        assert action is None

    def test_add_parallel_action_success(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = MongoProcessor()

        action_1 = "action_1"
        action_2 = "action_2"

        processor.add_action(action_1, bot, user)
        processor.add_action(action_2, bot, user)

        request_data = {
            "name": "parallel_test_action",
            "dispatch_response_text": True,
            "response_text": "Executed parallel",
            "actions": [action_1, action_2]
        }

        action_id = processor.add_parallel_action(request_data, bot, user)

        result = ParallelActionConfig.objects(id=action_id, bot=bot).first()
        assert result is not None
        assert result.name == "parallel_test_action"
        assert result.actions == [action_1, action_2]

        Actions.objects(name__in=[action_1, action_2, "parallel_test_action"]).delete()
        ParallelActionConfig.objects(name__iexact="parallel_test_action", bot=bot).delete()

    def test_add_parallel_action_invalid_name(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = MongoProcessor()

        action_1 = "valid_action"
        processor.add_action(action_1, bot, user)

        request_data = {
            "name": "invalid name!",
            "dispatch_response_text": True,
            "response_text": "Invalid name case",
            "actions": [action_1]
        }

        with pytest.raises(AppException, match="Invalid name! Only letters, numbers, and underscores"):
            processor.add_parallel_action(request_data, bot, user)

        Actions.objects(name=action_1, bot=bot).delete()

    def test_add_parallel_action_duplicate_name_in_actions(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = MongoProcessor()

        action1 = "action1"
        duplicate_name = "duplicate_action"
        processor.add_action(duplicate_name, bot, user)
        processor.add_action(action1, bot, user)

        request_data = {
            "name": duplicate_name,
            "dispatch_response_text": True,
            "response_text": "should fail",
            "actions": [action1]
        }

        with pytest.raises(AppException, match="Action exists!"):
            processor.add_parallel_action(request_data, bot, user)

        Actions.objects(name__in=[duplicate_name, action1], bot=bot).delete()

    def test_add_parallel_action_duplicate_name_in_parallel_config(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = MongoProcessor()

        action1 = "action1"
        existing_parallel = "existing_parallel_action"
        processor.add_action(action1, bot, user)

        request_data_1 = {
            "name": existing_parallel,
            "dispatch_response_text": True,
            "response_text": "first one",
            "actions": [action1]
        }

        processor.add_parallel_action(request_data_1, bot, user)

        request_data_2 = {
            "name": existing_parallel,
            "dispatch_response_text": False,
            "response_text": "duplicate entry",
            "actions": [action1]
        }

        with pytest.raises(AppException, match="Action exists!"):
            processor.add_parallel_action(request_data_2, bot, user)

        Actions.objects(name__in=[existing_parallel, action1], bot=bot).delete()
        ParallelActionConfig.objects(name=existing_parallel, bot=bot).delete()

    def test_add_parallel_action_missing_subaction(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = MongoProcessor()

        valid_action = "valid_action"
        missing_action = "missing_action"
        processor.add_action(valid_action, bot, user)

        request_data = {
            "name": "parallel_missing_action",
            "dispatch_response_text": False,
            "response_text": "error case",
            "actions": [valid_action, missing_action]
        }

        with pytest.raises(AppException, match=f"Action with name {missing_action} does not exist!"):
            processor.add_parallel_action(request_data, bot, user)

        Actions.objects(name=valid_action, bot=bot).delete()

    def test_add_parallel_action_success_exceeds_max_actions(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = MongoProcessor()

        action_1 = "action_1"
        action_2 = "action_2"

        processor.add_action(action_1, bot, user)
        processor.add_action(action_2, bot, user)

        request_data = {
            "name": "parallel_test_action",
            "dispatch_response_text": True,
            "response_text": "Executed parallel",
            "actions": [action_1, action_2, action_1, action_2, action_1, action_2]
        }

        with pytest.raises(AppException, match="Maximum 5 actions are allowed in a parallel action."):
            processor.add_parallel_action(request_data, bot, user)

        Actions.objects(name__in=[action_1, action_2, "parallel_test_action"]).delete()
        ParallelActionConfig.objects(name__iexact="parallel_test_action", bot=bot).delete()

    def test_update_parallel_action_success(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = MongoProcessor()

        action_1 = "action_1"
        action_2 = "action_2"
        parallel_name = "update_test_parallel"

        processor.add_action(action_1, bot, user)
        processor.add_action(action_2, bot, user)

        create_data = {
            "name": parallel_name,
            "dispatch_response_text": False,
            "response_text": "Initial",
            "actions": [action_1]
        }

        processor.add_parallel_action(create_data, bot, user)

        update_data = {
            "name": parallel_name,
            "response_text": "Updated response",
            "actions": [action_1, action_2]
        }

        updated_id = processor.update_parallel_action(update_data, bot, user)
        updated = ParallelActionConfig.objects(id=updated_id).first()

        assert updated is not None
        assert updated.response_text == "Updated response"
        assert set(updated.actions) == {action_1, action_2}
        assert updated.user == user

        Actions.objects(name__in=[action_1, action_2, parallel_name], bot=bot).delete()
        ParallelActionConfig.objects(name=parallel_name, bot=bot).delete()

    def test_update_parallel_action_invalid_name(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = MongoProcessor()

        request_data = {
            "name": "invalid name!",
            "response_text": "invalid case",
            "actions": ["action_1"]
        }

        with pytest.raises(AppException, match="Invalid name! Only letters, numbers, and underscores"):
            processor.update_parallel_action(request_data, bot, user)

    def test_update_parallel_action_not_found(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = MongoProcessor()

        request_data = {
            "name": "non_existing_parallel",
            "response_text": "trying to update",
            "actions": ["action_1"]
        }

        with pytest.raises(AppException, match="Parallel Action with name 'non_existing_parallel' not found!"):
            processor.update_parallel_action(request_data, bot, user)

    def test_update_parallel_action_missing_sub_action(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = MongoProcessor()

        existing_action = "existing_action"
        missing_action = "missing_action"
        parallel_name = "update_missing_sub"

        processor.add_action(existing_action, bot, user)

        create_data = {
            "name": parallel_name,
            "dispatch_response_text": False,
            "response_text": "Initial",
            "actions": [existing_action]
        }

        processor.add_parallel_action(create_data, bot, user)

        update_data = {
            "name": parallel_name,
            "response_text": "Trying to add missing action",
            "actions": [existing_action, missing_action]
        }

        with pytest.raises(AppException, match=f"Action with name {missing_action} does not exist!"):
            processor.update_parallel_action(update_data, bot, user)

        Actions.objects(name__in=[existing_action, parallel_name], bot=bot).delete()
        ParallelActionConfig.objects(name=parallel_name, bot=bot).delete()

    def test_update_parallel_action_exceeds_max_actions(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = MongoProcessor()

        action_1 = "action_1"
        action_2 = "action_2"
        parallel_name = "update_test_parallel"

        processor.add_action(action_1, bot, user)
        processor.add_action(action_2, bot, user)

        create_data = {
            "name": parallel_name,
            "dispatch_response_text": False,
            "response_text": "Initial",
            "actions": [action_1]
        }

        processor.add_parallel_action(create_data, bot, user)

        update_data = {
            "name": parallel_name,
            "response_text": "Updated response",
            "actions": [action_1, action_2, action_1, action_2, action_1, action_2]
        }

        with pytest.raises(AppException, match="Maximum 5 actions are allowed in a parallel action."):
            processor.update_parallel_action(update_data, bot, user)

        Actions.objects(name__in=[action_1, action_2, parallel_name], bot=bot).delete()
        ParallelActionConfig.objects(name=parallel_name, bot=bot).delete()

    def test_list_parallel_action_returns_created_action(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = MongoProcessor()

        action_1 = "list_action_1"
        action_2 = "list_action_2"
        parallel_name = "parallel_list_test"

        processor.add_action(action_1, bot, user)
        processor.add_action(action_2, bot, user)

        request_data = {
            "name": parallel_name,
            "dispatch_response_text": True,
            "response_text": "List test response",
            "actions": [action_1, action_2]
        }

        processor.add_parallel_action(request_data, bot, user)

        result = list(processor.list_parallel_action(bot))
        found = next((action for action in result if action["name"] == parallel_name), None)

        assert found is not None
        assert found["name"] == parallel_name
        assert found["actions"] == [action_1, action_2]
        assert "user" not in found
        assert "bot" not in found
        assert "status" not in found

        Actions.objects(name__in=[action_1, action_2, parallel_name], bot=bot).delete()
        ParallelActionConfig.objects(name=parallel_name, bot=bot).delete()

    def test_list_parallel_action_empty_when_none_exist(self):
        bot = "test_bot_empty_list"
        processor = MongoProcessor()

        result = list(processor.list_parallel_action(bot))
        assert result == []

    def test_list_existing_actions_for_parallel_action_success(self):

        bot = "test_bot"
        user = "test_user"
        processor = MongoProcessor()
        Actions.objects(bot=bot).delete()
        action_1 = "http_action_1"
        action_2 = "email_action_1"
        action_3 = "jira_action_1"
        action_4 = "live_agent_action_1"
        action_5 = "parallel_action_1"

        processor.add_action(action_1, bot, user, action_type=ActionType.http_action)
        processor.add_action(action_2, bot, user, action_type=ActionType.email_action)
        processor.add_action(action_3, bot, user, action_type=ActionType.jira_action)
        processor.add_action(action_4, bot, user, action_type=ActionType.live_agent_action)
        processor.add_action(action_5, bot, user, action_type=ActionType.parallel_action)

        result = list(processor.list_existing_actions_for_parallel_action(bot))

        assert len(result) == 3

        action_names = [action["name"] for action in result]
        assert action_1 in action_names
        assert action_2 in action_names
        assert action_3 in action_names
        assert action_4 not in action_names
        assert action_5 not in action_names

        Actions.objects(name__in=[action_1, action_2, action_3, action_4, action_5], bot=bot).delete()

    def test_delete_parallel_action_success(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = MongoProcessor()

        action_1 = "action_1"
        action_2 = "action_2"

        processor.add_action(action_1, bot, user)
        processor.add_action(action_2, bot, user)

        request_data = {
            "name": "parallel_test_action",
            "dispatch_response_text": True,
            "response_text": "Executed parallel",
            "actions": [action_1, action_2]
        }

        action_id = processor.add_parallel_action(request_data, bot, user)

        result = ParallelActionConfig.objects(id=action_id, bot=bot).first()
        assert result is not None
        assert result.name == "parallel_test_action"
        assert result.actions == [action_1, action_2]

        processor.delete_action("parallel_test_action", bot, user)

        result = ParallelActionConfig.objects(name="parallel_test_action", bot=bot).first()
        assert result is None

        result = Actions.objects(name="parallel_test_action", bot=bot).first()
        assert result is None

        Actions.objects(name__in=[action_1, action_2, "parallel_test_action"]).delete()
        ParallelActionConfig.objects(name__iexact="parallel_test_action", bot=bot).delete()

    def test_delete_subaction_used_in_parallel_action(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = MongoProcessor()

        action_1 = "action_1"
        action_2 = "action_2"

        processor.add_action(action_1, bot, user)
        processor.add_action(action_2, bot, user)

        request_data = {
            "name": "parallel_test_action",
            "dispatch_response_text": True,
            "response_text": "Executed parallel",
            "actions": [action_1, action_2]
        }

        action_id = processor.add_parallel_action(request_data, bot, user)

        result = ParallelActionConfig.objects(id=action_id, bot=bot).first()
        assert result is not None
        assert result.name == "parallel_test_action"
        assert result.actions == [action_1, action_2]

        with pytest.raises(AppException, match=re.escape(
            "Action 'action_1' cannot be deleted because it is used in parallel actions: ['parallel_test_action']"
        )):
            processor.delete_action("action_1", bot, user)

        Actions.objects(name__in=[action_1, action_2, "parallel_test_action"]).delete()
        ParallelActionConfig.objects(name__iexact="parallel_test_action", bot=bot).delete()

    def test_check_action_usage_in_parallel_actions_raises_exception(self):
        bot = 'test_bot'
        user = 'test_user'
        processor = MongoProcessor()

        action_1 = "action_1"
        action_2 = "action_2"

        processor.add_action(action_1, bot, user)
        processor.add_action(action_2, bot, user)

        request_data = {
            "name": "parallel_test_action",
            "dispatch_response_text": True,
            "response_text": "Executed parallel",
            "actions": [action_1, action_2]
        }

        action_id = processor.add_parallel_action(request_data, bot, user)

        result = ParallelActionConfig.objects(id=action_id, bot=bot).first()
        assert result is not None
        assert result.name == "parallel_test_action"
        assert result.actions == [action_1, action_2]

        with pytest.raises(AppException, match=re.escape(
            "Action 'action_1' cannot be deleted because it is used in parallel actions: ['parallel_test_action']"
        )):
            processor.check_action_usage_in_parallel_actions(bot, action_1)

        Actions.objects(name__in=[action_1, action_2, "parallel_test_action"]).delete()
        ParallelActionConfig.objects(name__iexact="parallel_test_action", bot=bot).delete()

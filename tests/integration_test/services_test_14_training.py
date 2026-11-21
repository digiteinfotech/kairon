from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training



@pytest.fixture()
def save_actions():
    from unittest import mock
    import textwrap
    from kairon.shared.callback.data_objects import CallbackConfig, encrypt_secret
    from kairon.shared.actions.data_objects import SetSlots, CustomActionParameters, HttpActionConfig, \
        HttpActionResponse, HttpActionRequestBody, SetSlotsFromResponse, SlotSetAction, EmailActionConfig, \
        GoogleSearchAction, CustomActionRequestParameters, ZendeskAction, JiraAction, PipedriveLeadsAction, \
        PromptAction, UserQuestion, WebSearchAction, RazorpayAction, PyscriptActionConfig, DbQuery, \
        CallbackActionConfig, CustomActionDynamicParameters, ScheduleAction, DatabaseAction, LiveAgentActionConfig, \
        KaironTwoStageFallbackAction, FormValidationAction

    HttpActionConfig(
        action_name="http_action_1",
        response=HttpActionResponse(value="The value of ${data.a.b.3} in ${data.a.b.d.0} is ${data.a.b.d}"),
        http_url="http://localhost:8081/mock",
        request_method="GET",
        headers=[HttpActionRequestBody(key="bot", parameter_type="slot", value="bot", encrypt=True),
                 HttpActionRequestBody(key="user", parameter_type="value", value="1011", encrypt=True),
                 HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True),
                 HttpActionRequestBody(key="email", parameter_type="key_vault", value="EMAIL", encrypt=False)],
        params_list=[HttpActionRequestBody(key="bot", parameter_type="slot", value="bot", encrypt=True),
                     HttpActionRequestBody(key="user", parameter_type="value", value="1011", encrypt=False),
                     HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True),
                     HttpActionRequestBody(key="name", parameter_type="key_vault", value="FIRSTNAME",
                                           encrypt=False),
                     HttpActionRequestBody(key="contact", parameter_type="key_vault", value="CONTACT",
                                           encrypt=False)],
        set_slots=[SetSlotsFromResponse(name="name", value="${data.a.b.d}"),
                   SetSlotsFromResponse(name="age", value="${data.a.b.d.0}")],
        bot=pytest.bot,
        user="user"
    ).save()

    HttpActionConfig(
        action_name="http_action_2",
        response=HttpActionResponse(value="The value of ${data.a.b.3} in ${data.a.b.d.0} is ${data.a.b.d}"),
        http_url="http://localhost:8081/mock",
        request_method="GET",
        headers=[HttpActionRequestBody(key="bot", parameter_type="slot", value="bot", encrypt=True),
                 HttpActionRequestBody(key="user", parameter_type="value", value="1011", encrypt=True),
                 HttpActionRequestBody(key="name", parameter_type="slot", value="name", encrypt=True),
                 HttpActionRequestBody(key="email", parameter_type="key_vault", value="EMAIL", encrypt=False)],
        params_list=[HttpActionRequestBody(key="bot", parameter_type="slot", value="bot", encrypt=True),
                     HttpActionRequestBody(key="user", parameter_type="value", value="1011", encrypt=False),
                     HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True),
                     HttpActionRequestBody(key="name", parameter_type="key_vault", value="FIRSTNAME",
                                           encrypt=False),
                     HttpActionRequestBody(key="contact", parameter_type="key_vault", value="CONTACT",
                                           encrypt=False)],
        set_slots=[SetSlotsFromResponse(name="name", value="${data.a.b.d}"),
                   SetSlotsFromResponse(name="location", value="${data.a.b.d.0}")],
        bot=pytest.bot,
        user="user"
    ).save()

    SlotSetAction(
        name="slot_set_action_1",
        set_slots=[SetSlots(name="location", type="reset_slot", value="location"),
                   SetSlots(name="name", type="from_value", value="end_user"),
                   SetSlots(name="age", type="reset_slot")],
        bot=pytest.bot,
        user="user"
    ).save()
    SlotSetAction(
        name="slot_set_action_2",
        set_slots=[SetSlots(name="name", type="reset_slot", value="")],
        bot=pytest.bot,
        user="user"
    ).save()

    with patch('kairon.shared.utils.SMTP', autospec=True):
        EmailActionConfig(
            action_name="email_action_1",
            smtp_url="test.test.com",
            smtp_port=293,
            smtp_password=CustomActionRequestParameters(key='smtp_password', value="test"),
            from_email=CustomActionRequestParameters(value="name", parameter_type="slot"),
            to_email=CustomActionParameters(value=["test@test.com"], parameter_type="value"),
            subject="test",
            response="Email Triggered",
            bot=pytest.bot,
            user="user"
        ).save()
        EmailActionConfig(
            action_name="email_action_2",
            smtp_url="test.test.com",
            smtp_port=293,
            smtp_password=CustomActionRequestParameters(key='smtp_password', value="slot"),
            from_email=CustomActionRequestParameters(value="test@test.com", parameter_type="value"),
            to_email=CustomActionParameters(value=["test@test.com"], parameter_type="value"),
            subject="test",
            response="Email Triggered",
            bot=pytest.bot,
            user="user"
        ).save()
        EmailActionConfig(
            action_name="email_action_3",
            smtp_url="test.test.com",
            smtp_port=293,
            smtp_password=CustomActionRequestParameters(key='smtp_password', value="test"),
            from_email=CustomActionRequestParameters(value="from_email", parameter_type="slot"),
            to_email=CustomActionParameters(value="name", parameter_type="slot"),
            subject="test",
            response="Email Triggered",
            bot=pytest.bot,
            user="user"
        ).save()
        EmailActionConfig(
            action_name="email_action_4",
            smtp_url="test.test.com",
            smtp_port=293,
            smtp_password=CustomActionRequestParameters(key='name', parameter_type="slot", value="name"),
            from_email=CustomActionRequestParameters(value="test@test.com", parameter_type="value"),
            to_email=CustomActionParameters(value=["test@test.com"], parameter_type="value"),
            subject="test",
            response="Email Triggered",
            bot=pytest.bot,
            user="user"
        ).save()
        EmailActionConfig(
            action_name="email_action_5",
            smtp_url="test.test.com",
            smtp_port=293,
            smtp_userid=CustomActionRequestParameters(key='name', parameter_type="slot", value="name"),
            smtp_password=CustomActionRequestParameters(key='smtp_password', value="test"),
            from_email=CustomActionRequestParameters(value="test@test.com", parameter_type="value"),
            to_email=CustomActionParameters(value=["test@test.com"], parameter_type="value"),
            subject="test",
            response="Email Triggered",
            bot=pytest.bot,
            user="user"
        ).save()
        EmailActionConfig(
            action_name="email_action_6",
            smtp_url="test.test.com",
            smtp_port=293,
            smtp_userid=CustomActionRequestParameters(key='name', parameter_type="slot", value="name"),
            smtp_password=CustomActionRequestParameters(key='smtp_password', value="test"),
            from_email=CustomActionRequestParameters(value="test@test.com", parameter_type="value"),
            to_email=CustomActionParameters(value=["test@test.com"], parameter_type="value"),
            custom_text=CustomActionRequestParameters(key='bot', parameter_type="slot", value="bot"),
            subject="test",
            response="Email Triggered",
            bot=pytest.bot,
            user="user"
        ).save()

    GoogleSearchAction(
        name="google_action_1",
        api_key=CustomActionRequestParameters(value='1234567890'),
        search_engine_id='asdfg::123456',
        bot=pytest.bot,
        user="user",
        dispatch_response=False,
        num_results=3,
        set_slot="name"
    ).save()
    GoogleSearchAction(
        name="google_action_2",
        api_key=CustomActionRequestParameters(key='name', parameter_type="slot", value='name'),
        search_engine_id='asdfg::123456',
        bot=pytest.bot,
        user="user",
        dispatch_response=False,
        num_results=3,
        set_slot="location"
    ).save()

    with mock.patch('zenpy.Zenpy'):
        ZendeskAction(
            name="zendesk_action_1",
            subdomain='digite751',
            user_name='udit.pandey@digite.com',
            api_token=CustomActionRequestParameters(value='1234567890'),
            subject='new ticket',
            response='ticket created',
            bot=pytest.bot,
            user="user"
        ).save()
        ZendeskAction(
            name="zendesk_action_2",
            subdomain='digite751',
            user_name='udit.pandey@digite.com',
            api_token=CustomActionRequestParameters(key="name", parameter_type="slot", value='name'),
            subject='new ticket',
            response='ticket created',
            bot=pytest.bot,
            user="user"
        ).save()

    def _mock_response(*args, **kwargs):
        return None

    with mock.patch('kairon.shared.actions.data_objects.JiraAction.validate', new=_mock_response):
        JiraAction(
            name="jira_action_1",
            url='https://test-digite.atlassian.net',
            user_name='test@digite.com',
            api_token=CustomActionRequestParameters(key="name", parameter_type="slot", value='name'),
            project_key='HEL',
            issue_type='Bug',
            summary='fallback',
            response='Successfully created',
            bot=pytest.bot,
            user="user"
        ).save()
        JiraAction(
            name="jira_action_2",
            url='https://test-digite.atlassian.net',
            user_name='test@digite.com',
            api_token=CustomActionRequestParameters(key="location", parameter_type="slot", value='location'),
            project_key='HEL',
            issue_type='Bug',
            summary='fallback',
            response='Successfully created',
            bot=pytest.bot,
            user="user"
        ).save()

    with mock.patch('pipedrive.client.Client'):
        metadata = {'name': 'location', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
        PipedriveLeadsAction(
            name="pipedrive_action_1",
            domain='https://digite751.pipedrive.com/',
            api_token=CustomActionRequestParameters(key="name", parameter_type="slot", value='name'),
            title='new lead generated',
            response='lead created',
            metadata=metadata,
            bot=pytest.bot,
            user="user"
        ).save()
        metadata = {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
        PipedriveLeadsAction(
            name="pipedrive_action_2",
            domain='https://digite751.pipedrive.com/',
            api_token=CustomActionRequestParameters(key="location", parameter_type="slot", value='location'),
            title='new lead generated',
            response='lead created',
            metadata=metadata,
            bot=pytest.bot,
            user="user"
        ).save()
    llm_prompts = [
        {'name': 'System Prompt',
         'data': 'You are a personal assistant. Answer question based on the context below.',
         'type': 'system', 'source': 'static', 'is_enabled': True},
        {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True},
        {'name': 'Query Prompt', 'data': "What kind of language is python?", 'instructions': 'Rephrase the query.',
         'type': 'query', 'source': 'static', 'is_enabled': False},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
         'type': 'user', 'source': 'bot_content', 'data': 'python',
         'hyperparameters': {"top_results": 10, "similarity_threshold": 0.70},
         'is_enabled': True}
    ]
    PromptAction(
        name="prompt_action_1",
        llm_type="openai",
        hyperparameters=Utility.get_llm_hyperparameters("openai"),
        num_bot_responses=2,
        llm_prompts=llm_prompts,
        user_question=UserQuestion(type="from_slot", value="name"),
        set_slots=[SetSlotsFromResponse(name="location", value="${data.a.b.d.0}")],
        bot=pytest.bot,
        user="user"
    ).save()
    PromptAction(
        name="prompt_action_2",
        llm_type="openai",
        hyperparameters=Utility.get_llm_hyperparameters("openai"),
        num_bot_responses=2,
        llm_prompts=llm_prompts,
        user_question=UserQuestion(type="from_slot", value="location"),
        set_slots=[SetSlotsFromResponse(name="name", value="${data.a.b.d}")],
        bot=pytest.bot,
        user="user"
    ).save()

    llm_prompts = [
        {'name': 'System Prompt',
         'data': 'You are a personal assistant. Answer question based on the context below.',
         'type': 'system', 'source': 'static', 'is_enabled': True},
        {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True},
        {'name': 'Query Prompt', 'data': "What kind of language is python?", 'instructions': 'Rephrase the query.',
         'type': 'query', 'source': 'static', 'is_enabled': False},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
         'type': 'user', 'source': 'bot_content', 'data': 'python',
         'hyperparameters': {"top_results": 10, "similarity_threshold": 0.70},
         'is_enabled': True},
        {'name': 'Name Prompt',
         'data': 'name',
         'instructions': 'Answer according to the context', 'type': 'user', 'source': 'slot',
         'is_enabled': True},
        {'name': 'Location Prompt',
         'data': 'location',
         'instructions': 'Answer according to the context', 'type': 'user', 'source': 'slot',
         'is_enabled': True}
    ]
    PromptAction(
        name="prompt_action_3",
        llm_type="anthropic",
        hyperparameters=Utility.get_llm_hyperparameters("anthropic"),
        num_bot_responses=2,
        llm_prompts=llm_prompts,
        user_question=UserQuestion(type="from_user_message", value="hello"),
        bot=pytest.bot,
        user="user"
    ).save()
    WebSearchAction(
        name="web_search_action_1",
        website="https://www.w3schools.com/",
        topn=1,
        set_slot='location',
        bot=pytest.bot,
        user="user"
    ).save()
    WebSearchAction(
        name="web_search_action_2",
        website="https://www.w3schools.com/",
        topn=1,
        set_slot='name',
        bot=pytest.bot,
        user="user"
    ).save()
    RazorpayAction(
        name="razorpay_action_1",
        api_key=CustomActionRequestParameters(value="API_KEY", parameter_type="ActionParameterType.key_vault"),
        api_secret=CustomActionRequestParameters(value="API_SECRET", parameter_type="ActionParameterType.key_vault"),
        amount=CustomActionRequestParameters(value="amount", parameter_type="slot"),
        currency=CustomActionRequestParameters(value="INR", parameter_type="value"),
        username=CustomActionRequestParameters(parameter_type="sender_id"),
        email=CustomActionRequestParameters(parameter_type="sender_id"),
        contact=CustomActionRequestParameters(value="name", parameter_type="slot"),
        notes=[
            CustomActionRequestParameters(key="order_id", parameter_type="slot",
                                          value="order_id", encrypt=True),
            CustomActionRequestParameters(key="location", parameter_type="slot",
                                          value="location", encrypt=False),
        ],
        bot=pytest.bot,
        user="user"
    ).save()
    RazorpayAction(
        name="razorpay_action_2",
        api_key=CustomActionRequestParameters(value="API_KEY", parameter_type="key_vault"),
        api_secret=CustomActionRequestParameters(value="API_SECRET", parameter_type="key_vault"),
        amount=CustomActionRequestParameters(value="location", parameter_type="slot"),
        currency=CustomActionRequestParameters(value="INR", parameter_type="value"),
        username=CustomActionRequestParameters(parameter_type="sender_id"),
        email=CustomActionRequestParameters(parameter_type="sender_id"),
        contact=CustomActionRequestParameters(value="contact", parameter_type="slot"),
        notes=[
            CustomActionRequestParameters(key="name", parameter_type="slot",
                                          value="name", encrypt=True),
            CustomActionRequestParameters(key="phone_number", parameter_type="value",
                                          value="9876543210", encrypt=False),
        ],
        bot=pytest.bot,
        user="user"
    ).save()

    script = """
    name = slot["name"]
    bot_response = slots
    type = text
    """
    script = textwrap.dedent(script)
    PyscriptActionConfig(
        name="pyscript_action_1",
        source_code=script,
        dispatch_response=True,
        bot=pytest.bot,
        user="user"
    ).save()
    script = """
    slots = {"location": "Bangalore"}
    bot_response = slots
    type = text
    """
    script = textwrap.dedent(script)
    PyscriptActionConfig(
        name="pyscript_action_2",
        source_code=script,
        dispatch_response=True,
        bot=pytest.bot,
        user="user"
    ).save()
    DatabaseAction(
        name="database_action_1",
        collection='vector_db_collection',
        payload=[DbQuery(query_type=DbActionOperationType.payload_search.value,
                         type=DbQueryValueType.from_slot.value,
                         value="name")],
        response=HttpActionResponse(value="The value of ${data.0.city} with color ${data.0.color} is ${data.0.id}"),
        set_slots=[SetSlotsFromResponse(name="city_value", value="${data.0.id}")],
        bot=pytest.bot,
        user="user"
    ).save()
    DatabaseAction(
        name="database_action_2",
        collection='vector_db_collection',
        payload=[DbQuery(query_type=DbActionOperationType.payload_search.value,
                         type=DbQueryValueType.from_slot.value,
                         value="search")],
        response=HttpActionResponse(value="The value of ${data.0.city} with color ${data.0.color} is ${data.0.id}"),
        set_slots=[SetSlotsFromResponse(name="location", value="${data.0.id}")],
        bot=pytest.bot,
        user="user"
    ).save()

    CallbackConfig(
        name="callback_script2",
        pyscript_code="bot_response='hello world'",
        validation_secret=encrypt_secret(
            "gAAAAABmqK71xDb4apnxOAfJjDUv1lrCTooWNX0GPyBHhqW1KBlblUqGNPwsX1V7FlIlgpwWGRWljiYp9mYAf1eG4AcG1dTXQuZCndCewox"),
        execution_mode="sync",
        bot="6697add6b8e47524eb983373",
    ).save()

    CallbackActionConfig(
        name="callback_action1",
        callback_name="callback_script2",
        dynamic_url_slot_name="location",
        metadata_list=[],
        bot_response="Hello",
        dispatch_bot_response=True,
        bot=pytest.bot,
        user="user"
    ).save()
    CallbackActionConfig(
        name="callback_action2",
        callback_name="callback_script2",
        dynamic_url_slot_name="name",
        metadata_list=[],
        bot_response="Hello",
        dispatch_bot_response=True,
        bot=pytest.bot,
        user="user"
    ).save()
    ScheduleAction(
        name="schedule_action_1",
        bot=pytest.bot,
        user="user",
        schedule_time=CustomActionDynamicParameters(parameter_type=ActionParameterType.slot.value,
                                                    value="name"),
        schedule_action="callback_script2",
        timezone="Asia/Kolkata",
        response_text="Action schedule",
        params_list=[CustomActionRequestParameters(key="bot", parameter_type="slot", value="bot", encrypt=True),
                     CustomActionRequestParameters(key="user", parameter_type="value", value="1011", encrypt=False)]
    ).save()
    ScheduleAction(
        name="schedule_action_2",
        bot=pytest.bot,
        user="user",
        schedule_time=CustomActionDynamicParameters(parameter_type=ActionParameterType.slot.value,
                                                    value="location"),
        schedule_action="callback_script2",
        timezone="Asia/Kolkata",
        response_text="Action schedule",
        params_list=[CustomActionRequestParameters(key="name", parameter_type="slot", value="name", encrypt=True),
                     CustomActionRequestParameters(key="user", parameter_type="value", value="1011", encrypt=False)]
    ).save()
    LiveAgentActionConfig(
        name="live_agent_action",
        bot_response="Connecting to live agent",
        dispatch_bot_response=True,
        bot=pytest.bot,
        user="user",
    ).save()
    KaironTwoStageFallbackAction(
        name="two_stage_fallback_action",
        text_recommendations={
            "count": 3,
            "use_intent_ranking": True
        },
        bot=pytest.bot,
        user="user",
    ).save()
    semantic_expression = "if ((location in ['Mumbai', 'Bangalore'] && location.startsWith('M') " \
                          "&& location.endsWith('i')) || location.length() > 20) " \
                          "{return true;} else {return false;}"
    FormValidationAction(
        name="form_validation_action",
        slot="location",
        validation_semantic=semantic_expression,
        bot=pytest.bot,
        user="user"
    ).save()


def test_get_slot_actions(save_actions):
    response = client.get(
        f"/api/bot/{pytest.bot}/slots/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["data"] == {
        'http_action': ['http_action_1', 'http_action_2'],
        'email_action': ['email_action_6'],
        'zendesk_action': [],
        'jira_action': [],
        'slot_set_action': [],
        'google_search_action': [],
        'pipedrive_leads_action': [],
        'prompt_action': [],
        'web_search_action': [],
        'razorpay_action': [],
        'pyscript_action': [],
        'database_action': [],
        'callback_action': [],
        'schedule_action': ['schedule_action_1']
    }

    response = client.get(
        f"/api/bot/{pytest.bot}/slots/location",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["data"] == {
        'http_action': ['http_action_2'],
        'email_action': [],
        'zendesk_action': [],
        'jira_action': ['jira_action_2'],
        'slot_set_action': ['slot_set_action_1'],
        'google_search_action': ['google_action_2'],
        'pipedrive_leads_action': ['pipedrive_action_1', 'pipedrive_action_2'],
        'prompt_action': ['prompt_action_1', 'prompt_action_2', 'prompt_action_3'],
        'web_search_action': ['web_search_action_1'],
        'razorpay_action': ['razorpay_action_1', 'razorpay_action_2'],
        'pyscript_action': ['pyscript_action_2'],
        'database_action': ['database_action_2'],
        'callback_action': ['callback_action1'],
        'schedule_action': ['schedule_action_2']
    }

    response = client.get(
        f"/api/bot/{pytest.bot}/slots/name",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["data"] == {
        'http_action': ['http_action_1', 'http_action_2'],
        'email_action': ['email_action_1', 'email_action_3', 'email_action_4', 'email_action_5', 'email_action_6'],
        'zendesk_action': ['zendesk_action_2'],
        'jira_action': ['jira_action_1'],
        'slot_set_action': ['slot_set_action_1', 'slot_set_action_2'],
        'google_search_action': ['google_action_1', 'google_action_2'],
        'pipedrive_leads_action': ['pipedrive_action_1', 'pipedrive_action_2'],
        'prompt_action': ['prompt_action_1', 'prompt_action_2', 'prompt_action_3'],
        'web_search_action': ['web_search_action_2'],
        'razorpay_action': ['razorpay_action_1', 'razorpay_action_2'],
        'pyscript_action': ['pyscript_action_1'],
        'database_action': ['database_action_1'],
        'callback_action': ['callback_action2'],
        'schedule_action': ['schedule_action_1', 'schedule_action_2']
    }


def test_update_bot_name():
    response = client.put(
        f"/api/account/bot/{pytest.bot}",
        json={"data":"Hi-Hello-bot"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response["message"] == "Name updated"
    assert response["error_code"] == 0
    assert response["success"]

    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert len(response["data"]) == 2
    pytest.bot = response["data"]["account_owned"][0]["_id"]
    assert response["data"]["account_owned"][0]["name"] == "Hi-Hello-bot"
    assert response["data"]["account_owned"][1]["name"] == "covid-bot"


@pytest.fixture()
def resource_test_upload_zip():
    data_path = "tests/testing_data/yml_training_files"
    tmp_dir = tempfile.gettempdir()
    zip_file = os.path.join(tmp_dir, "test")
    shutil.make_archive(zip_file, "zip", data_path)
    pytest.zip = open(zip_file + ".zip", "rb").read()
    yield "resource_test_upload_zip"
    if os.path.exists(zip_file + ".zip"):
        os.remove(zip_file + ".zip")
    if os.path.exists(os.path.join("training_data", pytest.bot)):
        shutil.rmtree(os.path.join("training_data", pytest.bot))


@responses.activate
def test_upload_zip(resource_test_upload_zip):
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    files = (
        ("training_files", ("data.zip", pytest.zip)),
        (
            "training_files",
            ("domain.yml", open("tests/testing_data/all/domain.yml", "rb")),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=false",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer
    )


@responses.activate
def test_upload():
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    files = (
        (
            "training_files",
            ("nlu.yml", open("tests/testing_data/all/data/nlu.yml", "rb")),
        ),
        (
            "training_files",
            ("domain.yml", open("tests/testing_data/all/domain.yml", "rb")),
        ),
        (
            "training_files",
            ("stories.yml", open("tests/testing_data/all/data/stories.yml", "rb")),
        ),
        (
            "training_files",
            ("config.yml", open("tests/testing_data/all/config.yml", "rb")),
        ),
        (
            "training_files",
            (
                "chat_client_config.yml",
                open("tests/testing_data/all/chat_client_config.yml", "rb"),
            ),
        ),
        (
            "training_files",
            (
                "bot_content.yml",
                open("tests/testing_data/all/bot_content.yml", "rb"),
            ),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer
    )


@responses.activate
def test_upload_yml():
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    files = (
        (
            "training_files",
            ("nlu.yml", open("tests/testing_data/valid_yml/data/nlu.yml", "rb")),
        ),
        (
            "training_files",
            ("domain.yml", open("tests/testing_data/valid_yml/domain.yml", "rb")),
        ),
        (
            "training_files",
            (
                "stories.yml",
                open("tests/testing_data/valid_yml/data/stories.yml", "rb"),
            ),
        ),
        (
            "training_files",
            ("config.yml", open("tests/testing_data/valid_yml/config.yml", "rb")),
        ),
        (
            "training_files",
            ("actions.yml", open("tests/testing_data/valid_yml/actions.yml", "rb")),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer
    )


def test_list_entities():
    response = client.get(
        f"/api/bot/{pytest.bot}/entities",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    expected = {'bot', 'file', 'category', 'file_text', 'ticketid', 'file_error',
                'priority', 'requested_slot', 'fdresponse', 'kairon_action_response',
                'audio', 'image', 'doc_url', 'document', 'video', 'order', 'payment', 'latitude',
                'longitude', 'flow_reply', 'http_status_code', 'name', 'quick_reply', 'mail_id',
                'subject', 'body', 'media_ids','flow_docs', 'flow_images', 'flow_data', 'llm_call_id',
                'user_identifier', 'temp_token', 'store_page_name','redirect_url', 'callback_identifier',
                'is_followup', 'parent_log_id', 'date', 'cc'}
    assert not DeepDiff({item['name'] for item in actual['data']}, expected, ignore_order=True)
    assert actual["success"]


def test_model_testing_no_existing_models():
    response = client.post(
        url=f"/api/bot/{pytest.bot}/test",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "No model trained yet. Please train a model to test"
    assert not actual["success"]


@responses.activate
@patch.object(ModelProcessor, "is_daily_training_limit_exceeded")
def test_train(mock_training_limit):
    mock_training_limit.return_value = False
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.model_training}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Model training started."
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.model_training
    )

@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_upload_limit_exceeded(mock_request_event_server, monkeypatch):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.data_importer_limit_per_day = 2
    bot_settings.save()
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=false",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files={
            "training_files": (
                "nlu.yml",
                open("tests/testing_data/yml_training_files/data/nlu.yml", "rb"),
            )
        },
    )
    actual = response.json()
    assert actual["message"] == "Daily limit exceeded."
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert not actual["success"]


@responses.activate
def test_upload_using_event_failure(monkeypatch):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.data_importer_limit_per_day = 15
    bot_settings.save()
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST", event_url, json={"success": False, "message": "Failed to trigger url"}
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=(
            (
                "training_files",
                (
                    "nlu.yml",
                    open("tests/testing_data/yml_training_files/data/nlu.yml", "rb"),
                ),
            ),
            (
                "training_files",
                (
                    "domain.yml",
                    open("tests/testing_data/yml_training_files/domain.yml", "rb"),
                ),
            ),
            (
                "training_files",
                (
                    "stories.yml",
                    open(
                        "tests/testing_data/yml_training_files/data/stories.yml", "rb"
                    ),
                ),
            ),
            (
                "training_files",
                (
                    "config.yml",
                    open("tests/testing_data/yml_training_files/config.yml", "rb"),
                ),
            ),
            (
                "training_files",
                (
                    "actions.yml",
                    open("tests/testing_data/yml_training_files/actions.yml", "rb"),
                ),
            ),
        ),
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert (
            actual["message"]
            == "Failed to trigger data_importer event: Failed to trigger url"
    )


@responses.activate
def test_upload_using_event_append(monkeypatch):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.data_importer_limit_per_day = 15
    bot_settings.save()

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        responses.POST,
        event_url,
        json={"success": True},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {
                    "data": {
                        "bot": pytest.bot,
                        "user": pytest.username,
                        "import_data": "--import-data",
                        "overwrite": "",
                        "event_type": EventClass.data_importer,
                    },
                    "cron_exp": None,
                    "timezone": None,
                    "run_at": None
                }
            )
        ],
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=false",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=(
            (
                "training_files",
                (
                    "nlu.yml",
                    open("tests/testing_data/yml_training_files/data/nlu.yml", "rb"),
                ),
            ),
            (
                "training_files",
                (
                    "domain.yml",
                    open("tests/testing_data/yml_training_files/domain.yml", "rb"),
                ),
            ),
            (
                "training_files",
                (
                    "stories.yml",
                    open(
                        "tests/testing_data/yml_training_files/data/stories.yml", "rb"
                    ),
                ),
            ),
            (
                "training_files",
                (
                    "config.yml",
                    open("tests/testing_data/yml_training_files/config.yml", "rb"),
                ),
            ),
            (
                "training_files",
                (
                    "actions.yml",
                    open("tests/testing_data/yml_training_files/actions.yml", "rb"),
                ),
            ),
        ),
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Upload in progress! Check logs."
    complete_end_to_end_event_execution(
        pytest.bot, "test_user", EventClass.data_importer
    )


def test_get_qna(monkeypatch):
    data = [
        {
            "_id": "638dde37cfe8a7de324067fa",
            "story": "accelerator_28",
            "intent": "accelerator_28",
            "utterance": "utter_accelerator_28",
            "training_examples": [
                {
                    "text": "What is the purpose of an acceleration?",
                    "_id": "638dde36cfe8a7de32405eaa",
                },
                {
                    "text": "What is the purpose of an accelerators?",
                    "_id": "638dde36cfe8a7de32405eab",
                },
            ],
            "responses": [
                {
                    "_id": "638dde35cfe8a7de32405ada",
                    "text": {
                        "text": "•\tAnything that helps project teams reduce effort, save cost"
                    },
                }
            ],
        },
        {
            "_id": "638dde37cfe8a7de324067fd",
            "story": "accelerator_subscription_mainspring_31",
            "intent": "accelerator_subscription_mainspring_31",
            "utterance": "utter_accelerator_subscription_mainspring_31",
            "training_examples": [
                {
                    "text": "•\tHow do I subscribe to accelerators for my project?",
                    "_id": "638dde36cfe8a7de32405ec0",
                },
                {
                    "text": "•\tHow to do accelerator subscription in mainspring",
                    "_id": "638dde36cfe8a7de32405ec1",
                },
            ],
            "responses": [
                {
                    "_id": "638dde35cfe8a7de32405b64",
                    "custom": {
                        "custom": {
                            "data": [
                                {
                                    "type": "paragraph",
                                    "children": [
                                        {
                                            "text": "Step 1 : Navigate to PM Plan >> Delivery Assets"
                                        }
                                    ],
                                },
                                {
                                    "type": "paragraph",
                                    "children": [
                                        {
                                            "text": "Step 2 : Subscribe the accelerators which are applicable"
                                        }
                                    ],
                                },
                            ]
                        }
                    },
                }
            ],
        },
        {
            "_id": "638dde37cfe8a7de324067fe",
            "story": "accelerators_auto_recommended_32",
            "intent": "accelerators_auto_recommended_32",
            "utterance": "utter_accelerators_auto_recommended_32",
            "training_examples": [
                {
                    "text": "•\tOn what basis are accelerators recommended for a project?",
                    "_id": "638dde36cfe8a7de32405ec3",
                },
                {
                    "text": "•\tWhat is the criteria based on which accelerators are auto recommended ?",
                    "_id": "638dde36cfe8a7de32405ec4",
                },
            ],
            "responses": [
                {
                    "_id": "638dde35cfe8a7de32405b2d",
                    "text": {
                        "text": "•\tAccelerators are auto-recommended from Knowhub based on these project attributes"
                    },
                }
            ],
        },
    ]

    def __mock_qna(*args, **kwargs):
        for item in data:
            yield item

    monkeypatch.setattr(BaseQuerySet, "aggregate", __mock_qna)

    response = client.get(
        f"/api/bot/{pytest.bot}/qna/flatten",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"]
    assert actual["data"] == {"qna": data, "total": 0}


def test_model_testing_exhosted_daily_limit():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.test_limit_per_day = 0
    bot_settings.save()
    response = client.post(
        url=f"/api/bot/{pytest.bot}/test",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "Daily limit exceeded."
    assert not actual["success"]


def test_get_data_importer_logs():
    response = client.get(
        f"/api/bot/{pytest.bot}/importer/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["logs"]) == 10
    assert actual["data"]["total"] == 10
    assert actual["data"]["logs"][0]["event_status"] == EVENT_STATUS.COMPLETED.value
    assert set(actual["data"]["logs"][0]["files_received"]) == {
        "stories",
        "nlu",
        "domain",
        "config",
        "actions",
    }
    assert actual["data"]["logs"][0]["is_data_uploaded"]
    assert actual["data"]["logs"][0]["start_timestamp"]
    assert actual["data"]["logs"][0]["end_timestamp"]

    assert actual['data']["logs"][1]['event_status'] == EVENT_STATUS.COMPLETED.value
    assert actual['data']["logs"][1]['status'] == STATUSES.SUCCESS.value
    assert set(actual['data']["logs"][1]['files_received']) == {'stories', 'nlu', 'domain', 'config', 'actions'}
    assert actual['data']["logs"][1]['is_data_uploaded']
    assert actual['data']["logs"][1]['start_timestamp']
    assert actual['data']["logs"][1]['end_timestamp']
    del actual['data']["logs"][1]['start_timestamp']
    del actual['data']["logs"][1]['end_timestamp']
    del actual['data']["logs"][1]['files_received']
    assert actual['data']["logs"][1] == {'intents': {'count': 14, 'data': []}, 'utterances': {'count': 14, 'data': []},
                                         'stories': {'count': 16, 'data': []},
                                         'training_examples': {'count': 192, 'data': []},
                                         'domain': {'intents_count': 15, 'actions_count': 23, 'slots_count': 10,
                                                    'utterances_count': 14, 'forms_count': 2, 'entities_count': 8,
                                                    'data': []},
                                         'config': {'count': 0, 'data': []}, 'rules': {'count': 1, 'data': []},
                                         'actions': [{'type': 'http_actions', 'count': 14, 'data': []},
                                                     {'type': 'two_stage_fallbacks', 'count': 0, 'data': []},
                                                     {'type': 'email_actions', 'count': 0, 'data': []},
                                                     {'type': 'zendesk_actions', 'count': 0, 'data': []},
                                                     {'type': 'jira_actions', 'count': 0, 'data': []},
                                                     {'type': 'form_validation_actions', 'count': 0, 'data': []},
                                                     {'type': 'slot_set_actions', 'count': 0, 'data': []},
                                                     {'type': 'google_search_actions', 'count': 0, 'data': []},
                                                     {'type': 'pipedrive_leads_actions', 'count': 0, 'data': []},
                                                     {'type': 'prompt_actions', 'count': 0, 'data': []},
                                                     {'type': 'web_search_actions', 'count': 0, 'data': []},
                                                     {'type': 'razorpay_actions', 'count': 0, 'data': []},
                                                     {'type': 'pyscript_actions', 'count': 0, 'data': []},
                                                     {'type': 'database_actions', 'count': 0, 'data': []},
                                                     {'type': 'live_agent_actions', 'count': 0, 'data': []},
                                                     {'type': 'callback_actions', 'count': 0, 'data': []},
                                                     {'type': 'schedule_actions', 'count': 0, 'data': []},
                                                     {'type': 'parallel_actions', 'count': 0, 'data': []},
                                                     {'type': 'voice_call_actions', 'count': 0, 'data': []},
                                                     {'type': 'store_page_actions', 'count': 0, 'data': []},
                                                     {'type': 'agent_actions', 'count': 0, 'data': []}],
                                         'multiflow_stories': {'count': 0, 'data': []},
                                         'bot_content': {'count': 0, 'data': []},
                                         'user_actions': {'count': 9, 'data': []},
                                         'exception': '',
                                         'is_data_uploaded': True,
                                         'status': STATUSES.SUCCESS.value, 'event_status': EVENT_STATUS.COMPLETED.value}
    assert actual['data']["logs"][2]['event_status'] == EVENT_STATUS.COMPLETED.value
    assert actual['data']["logs"][2]['status'] == STATUSES.FAIL.value
    assert set(actual['data']["logs"][2]['files_received']) == {'stories', 'nlu', 'domain', 'config',
                                                                'chat_client_config', 'bot_content'}
    assert actual['data']["logs"][2]['is_data_uploaded']
    assert actual['data']["logs"][2]['start_timestamp']
    assert actual['data']["logs"][2]['end_timestamp']

    assert actual['data']["logs"][3]['event_status'] == EVENT_STATUS.COMPLETED.value
    assert actual['data']["logs"][3]['status'] == STATUSES.FAIL.value
    assert set(actual['data']["logs"][3]['files_received']) == {'rules', 'stories', 'nlu', 'domain', 'config',
                                                                'actions', 'chat_client_config', 'multiflow_stories',
                                                                'bot_content'}
    assert actual['data']["logs"][3]['is_data_uploaded']
    assert actual['data']["logs"][3]['start_timestamp']
    assert actual['data']["logs"][3]['end_timestamp']
    assert actual['data']["logs"][3]['intents']['count'] == 19
    assert len(actual['data']["logs"][3]['intents']['data']) == 21
    assert actual['data']["logs"][3]['utterances']['count'] == 27
    assert len(actual['data']["logs"][3]['utterances']['data']) == 11
    assert actual['data']["logs"][3]['stories']['count'] == 16
    assert len(actual['data']["logs"][3]['stories']['data']) == 1
    assert actual['data']["logs"][3]['rules']['count'] == 3
    assert len(actual['data']["logs"][3]['rules']['data']) == 0
    assert actual['data']["logs"][3]['training_examples']['count'] == 305
    assert len(actual['data']["logs"][3]['training_examples']['data']) == 0
    assert actual['data']["logs"][3]['domain'] == {'intents_count': 28, 'actions_count': 41, 'slots_count': 11,
                                                   'utterances_count': 27, 'forms_count': 2, 'entities_count': 9,
                                                   'data': []}
    assert actual['data']["logs"][3]['config'] == {'count': 0, 'data': []}
    assert actual['data']["logs"][3]['actions'] == [{'type': 'http_actions', 'count': 17, 'data': []},
                                                    {'type': 'two_stage_fallbacks', 'count': 0, 'data': []},
                                                    {'type': 'email_actions', 'count': 0, 'data': []},
                                                    {'type': 'zendesk_actions', 'count': 0, 'data': []},
                                                    {'type': 'jira_actions', 'count': 0, 'data': []},
                                                    {'type': 'form_validation_actions', 'count': 1, 'data': []},
                                                    {'type': 'slot_set_actions', 'count': 0, 'data': []},
                                                    {'type': 'google_search_actions', 'count': 1, 'data': []},
                                                    {'type': 'pipedrive_leads_actions', 'count': 0, 'data': []},
                                                    {'type': 'prompt_actions', 'count': 0, 'data': []},
                                                    {'type': 'web_search_actions', 'count': 0, 'data': []},
                                                    {'type': 'razorpay_actions', 'count': 0, 'data': []},
                                                    {'type': 'pyscript_actions', 'count': 0, 'data': []},
                                                    {'type': 'database_actions', 'count': 0, 'data': []},
                                                    {'type': 'live_agent_actions', 'count': 0, 'data': []},
                                                    {'type': 'callback_actions', 'count': 0, 'data': []},
                                                    {'type': 'schedule_actions', 'count': 0, 'data': []},
                                                    {'type': 'parallel_actions', 'count': 0, 'data': []},
                                                    {'type': 'voice_call_actions', 'count': 0, 'data': []},
                                                    {'type': 'store_page_actions', 'count': 0, 'data': []},
                                                    {'type': 'agent_actions', 'count': 0, 'data': []}]
    assert actual['data']["logs"][3]['is_data_uploaded']
    assert set(actual['data']["logs"][3]['files_received']) == {'rules', 'stories', 'nlu', 'config', 'domain',
                                                                'actions', 'chat_client_config', 'multiflow_stories',
                                                                'bot_content'}


@responses.activate
def test_upload_with_chat_client_config_only():
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    files = (
        (
            "training_files",
            (
                "chat_client_config.yml",
                open("tests/testing_data/all/chat_client_config.yml", "rb"),
            ),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    response = client.get(
        f"/api/bot/{pytest.bot}/importer/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["logs"][0]["event_status"] == EVENT_STATUS.COMPLETED.value
    assert set(actual["data"]["logs"][0]["files_received"]) == {"chat_client_config"}
    assert actual["data"]["logs"][0]["is_data_uploaded"]
    assert actual["data"]["logs"][0]["start_timestamp"]
    assert actual["data"]["logs"][0]["end_timestamp"]

    response = client.get(
        f"/api/bot/{pytest.bot}/chat/client/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    actual['data'].pop('headers')
    actual['data'].pop('nudge_server_url')
    assert actual["data"] == Utility.read_yaml("tests/testing_data/all/chat_client_config.yml")["config"]


@responses.activate
def test_upload_with_chat_client_config():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.data_importer_limit_per_day = 15
    bot_settings.save()
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    files = (
        (
            "training_files",
            ("nlu.yml", open("tests/testing_data/all/data/nlu.yml", "rb")),
        ),
        (
            "training_files",
            ("domain.yml", open("tests/testing_data/all/domain.yml", "rb")),
        ),
        (
            "training_files",
            ("stories.yml", open("tests/testing_data/all/data/stories.yml", "rb")),
        ),
        (
            "training_files",
            ("config.yml", open("tests/testing_data/all/config.yml", "rb")),
        ),
        (
            "training_files",
            (
                "chat_client_config.yml",
                open("tests/testing_data/all/chat_client_config.yml", "rb"),
            ),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer
    )


@responses.activate
def test_upload_without_chat_client_config():
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    files = (
        (
            "training_files",
            ("nlu.yml", open("tests/testing_data/all/data/nlu.yml", "rb")),
        ),
        (
            "training_files",
            ("domain.yml", open("tests/testing_data/all/domain.yml", "rb")),
        ),
        (
            "training_files",
            ("stories.yml", open("tests/testing_data/all/data/stories.yml", "rb")),
        ),
        (
            "training_files",
            ("config.yml", open("tests/testing_data/all/config.yml", "rb")),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer
    )


def test_download_data_with_chat_client_config():
    response = client.get(
        f"/api/bot/{pytest.bot}/download/data",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    file_bytes = BytesIO(response.content)
    zip_file = ZipFile(file_bytes, mode="r")
    assert zip_file.filelist.__len__() == 10
    assert zip_file.getinfo("chat_client_config.yml")
    assert zip_file.getinfo("config.yml")
    assert zip_file.getinfo("domain.yml")
    assert zip_file.getinfo("actions.yml")
    assert zip_file.getinfo("bot_content.yml")
    assert zip_file.getinfo("multiflow_stories.yml")
    assert zip_file.getinfo("data/stories.yml")
    assert zip_file.getinfo("data/rules.yml")
    assert zip_file.getinfo("data/nlu.yml")

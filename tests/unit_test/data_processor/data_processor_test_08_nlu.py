from tests.unit_test.data_processor.data_processor_support import *  # noqa: F403
from tests.unit_test.data_processor.data_processor_support import (
    MongoProcessorTestBase,
    fast_rasa_training,
)

class TestMongoProcessor(MongoProcessorTestBase):
    def test_load_nlu(self):
        processor = MongoProcessor()
        training_data = processor.load_nlu("tests")
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 52
        assert training_data.entity_synonyms.__len__() == 0
        assert training_data.regex_features.__len__() == 0
        assert training_data.lookup_tables.__len__() == 0

    def test_load_domain(self):
        processor = MongoProcessor()
        domain = processor.load_domain("tests")
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 32
        assert [s.name for s in domain.slots if s.name == 'kairon_action_response' and s.value is None]
        assert domain.responses.keys().__len__() == 11
        assert domain.entities.__len__() == 31
        assert domain.form_names.__len__() == 0
        assert domain.user_actions.__len__() == 11
        assert domain.intents.__len__() == 14
        assert Utterances.objects(bot="tests").count() == 11

    def test_load_stories(self):
        processor = MongoProcessor()
        story_graph = processor.load_stories("tests")
        assert isinstance(story_graph, StoryGraph)
        assert story_graph.story_steps.__len__() == 7

    def test_add_intent(self):
        processor = MongoProcessor()
        assert processor.add_intent("greeting", "tests", "testUser", is_integration=False)
        intent = Intents.objects(bot="tests").get(name="greeting")
        assert intent.name == "greeting"

    def test_get_intents(self):
        processor = MongoProcessor()
        actual = processor.get_intents("tests")
        assert actual.__len__() == 11

    def test_add_intent_with_underscore(self):
        processor = MongoProcessor()
        assert processor.add_intent("greeting_examples", "tests", "testUser", is_integration=False)
        intent = Intents.objects(bot="tests").get(name="greeting_examples")
        assert intent.name == "greeting_examples"

    def test_add_intent_duplicate(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.add_intent("greeting", "tests", "testUser", is_integration=False)

    def test_add_intent_duplicate_case_insensitive(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.add_intent("Greeting", "tests", "testUser", is_integration=False)

    def test_add_none_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_intent(None, "tests", "testUser", is_integration=False)

    def test_add_empty_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_intent("", "tests", "testUser", is_integration=False)

    def test_add_blank_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_intent("  ", "tests", "testUser", is_integration=False)

    def test_add_training_example(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example(["Hi, How are you?"], "greeting", "tests", "testUser", is_integration=False)
        )
        assert results[0]["_id"]
        assert results[0]["text"] == "Hi, How are you?"
        assert results[0]["message"] == "Training Example added"

    def test_add_same_training_example(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example(["Hi"], "greeting", "tests", "testUser", is_integration=False)
        )
        assert results[0]["_id"] is None
        assert results[0]["text"] == "Hi"
        assert results[0]["message"] == 'Training Example exists in intent: [\'greet\']'

    def test_add_training_example_duplicate_case_insensitive(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example(["hi"], "greeting", "tests", "testUser", is_integration=False)
        )
        assert results[0]["_id"] is None
        assert results[0]["text"] == "hi"
        assert results[0]["message"] == 'Training Example exists in intent: [\'greet\']'

    def test_add_training_example_none_text(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example([None], "greeting", "tests", "testUser", is_integration=False)
        )
        assert results[0]["_id"] is None
        assert results[0]["text"] is None
        assert (
                results[0]["message"]
                == "Training Example cannot be empty or blank spaces"
        )

    def test_add_training_example_empty_text(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example([""], "greeting", "tests", "testUser", is_integration=False)
        )
        assert results[0]["_id"] is None
        assert results[0]["text"] == ""
        assert (
                results[0]["message"]
                == "Training Example cannot be empty or blank spaces"
        )

    def test_add_training_example_blank_text(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example(["  "], "greeting", "tests", "testUser", is_integration=False)
        )
        assert results[0]["_id"] is None
        assert results[0]["text"] == "  "
        assert (
                results[0]["message"]
                == "Training Example cannot be empty or blank spaces"
        )

    def test_add_training_example_none_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            results = list(
                processor.add_training_example(
                    ["Hi! How are you"], None, "tests", "testUser", is_integration=False
                )
            )
            assert results[0]["_id"] is None
            assert results[0]["text"] == "Hi! How are you"
            assert (
                    results[0]["message"]
                    == "Intent cannot be empty or blank spaces"
            )

    def test_add_training_example_empty_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            results = list(
                processor.add_training_example(
                    ["Hi! How are you"], "", "tests", "testUser", is_integration=False
                )
            )
            assert results[0]["_id"] is None
            assert results[0]["text"] == "Hi! How are you"
            assert (
                    results[0]["message"]
                    == "Intent cannot be empty or blank spaces"
            )

    def test_add_training_example_blank_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            results = list(
                processor.add_training_example(
                    ["Hi! How are you"], "  ", "tests", "testUser", is_integration=False
                )
            )
            assert results[0]["_id"] is None
            assert results[0]["text"] == "Hi! How are you"
            assert (
                    results[0]["message"]
                    == "Intent cannot be empty or blank spaces"
            )

    def test_add_empty_training_example(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            results = list(
                processor.add_training_example([""], None, "tests", "testUser", is_integration=False)
            )
            assert results[0]["_id"] is None
            assert results[0]["text"] == "Hi! How are you"
            assert (
                    results[0]["message"]
                    == "Training Example cannot be empty or blank spaces"
            )

    def test_get_training_examples(self):
        processor = MongoProcessor()
        expected = ["hey", "hello", "hi", "good morning", "good evening", "hey there"]
        actual = list(processor.get_training_examples("greet", "tests"))
        assert actual.__len__() == expected.__len__()
        assert all(a_val["text"] in expected for a_val in actual)

    def test_get_training_examples_empty(self):
        processor = MongoProcessor()
        actual = list(processor.get_training_examples("greets", "tests"))
        assert actual.__len__() == 0

    def test_get_all_training_examples(self):
        processor = MongoProcessor()
        training_examples, ids = processor.get_all_training_examples("tests")
        assert training_examples
        assert ids

    def test_training_example_exists(self):
        processor = MongoProcessor()
        intent = processor.check_training_example_exists("hey", "tests")
        assert intent == {"is_exists": True, "intent": "greet"}

    def test_training_example_does_not_exists(self):
        processor = MongoProcessor()
        intent = processor.check_training_example_exists("hgbsncj", "tests")
        assert intent == {"is_exists": False, "intent": None}

    def test_get_training_examples_as_dict(self, monkeypatch):
        processor = MongoProcessor()
        training_examples_expected = {'hi': 'greet', 'hello': 'greet', 'ok': 'affirm', 'no': 'deny'}

        def _mongo_aggregation(*args, **kwargs):
            return [{'training_examples': training_examples_expected}]

        monkeypatch.setattr(BaseQuerySet, 'aggregate', _mongo_aggregation)
        training_examples = processor.get_training_examples_as_dict("tests")
        assert training_examples == training_examples_expected

    def test_get_training_examples_as_dict_no_examples_added(self, monkeypatch):
        processor = MongoProcessor()

        def _mongo_aggregation(*args, **kwargs):
            return []

        monkeypatch.setattr(BaseQuerySet, 'aggregate', _mongo_aggregation)
        training_examples = processor.get_training_examples_as_dict("tests_bot")
        assert training_examples == {}

    def test_add_training_example_with_entity(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example(
                ["Log a [critical issue](priority)"],
                "get_priority",
                "tests",
                "testUser",
                is_integration=False
            )
        )
        assert results[0]["_id"]
        assert results[0]["text"] == "Log a [critical issue](priority)"
        assert results[0]["message"] == "Training Example added"
        intents = processor.get_intents("tests")
        assert any("get_priority" == intent["name"] for intent in intents)
        entities = processor.get_entities("tests")
        assert any("priority" == entity["name"] for entity in entities)
        new_training_example = TrainingExamples.objects(bot="tests").get(
            text="Log a critical issue"
        )
        slots = Slots.objects(bot="tests")
        new_slot = slots.get(name="priority")
        assert slots.__len__() == 32
        assert new_slot.name == "priority"
        assert new_slot.type == "text"
        assert new_training_example.text == "Log a critical issue"

    def test_get_training_examples_with_entities(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example(
                ["Make [TKT456](ticketID) a [critical issue](priority)"],
                "get_priority",
                "tests",
                "testUser",
                is_integration=False
            )
        )
        assert results[0]["_id"]
        assert (
                results[0]["text"] == "Make [TKT456](ticketid) a [critical issue](priority)"
        )
        assert results[0]["message"] == "Training Example added"
        actual = list(processor.get_training_examples("get_priority", "tests"))
        slots = Slots.objects(bot="tests")
        new_slot = slots.get(name="ticketid")
        assert any(
            [value["text"] == "Log a [critical issue](priority)" for value in actual]
        )
        assert any(
            [
                value["text"] == "Make [TKT456](ticketid) a [critical issue](priority)"
                for value in actual
            ]
        )
        assert slots.__len__() == 33
        assert new_slot.name == "ticketid"
        assert new_slot.type == "text"
        expected = ["hey", "hello", "hi", "good morning", "good evening", "hey there"]
        actual = list(processor.get_training_examples("greet", "tests"))
        assert actual.__len__() == expected.__len__()
        assert all(a_val["text"] in expected for a_val in actual)

    def test_delete_training_example(self):
        processor = MongoProcessor()
        training_examples = list(processor.get_training_examples(intent="get_priority", bot="tests"))
        expected_length = training_examples.__len__() - 1
        training_example = training_examples[0]
        expected_text = training_example['text']
        processor.remove_document(
            TrainingExamples, training_example['_id'], "tests", "testUser"
        )
        new_training_examples = list(
            processor.get_training_examples(intent="get_priority", bot="tests")
        )
        assert new_training_examples.__len__() == expected_length
        assert any(
            expected_text != example["text"] for example in new_training_examples
        )

    def test_add_training_example_multiple(self):
        processor = MongoProcessor()
        actual = list(processor.add_training_example(["Log a [critical issue](priority)",
                                                      "Make [TKT456](ticketID) a [high issue](priority)"],
                                                     intent="get_priority",
                                                     bot="tests", user="testUser", is_integration=False))
        assert actual[0]['message'] == 'Training Example exists in intent: [\'get_priority\']'
        assert actual[1]['message'] == "Training Example added"

    def test_add_entity(self):
        processor = MongoProcessor()
        assert processor.add_entity("file_text", "tests", "testUser")
        enitity = Entities.objects(bot="tests", status=True).get(name="file_text")
        assert enitity.name == "file_text"

    def test_get_entities(self):
        processor = MongoProcessor()
        expected = ["bot", "priority", "file_text", "ticketid", 'kairon_action_response', 'image', 'video', 'audio',
                    'doc_url', 'document', 'order', 'payment', 'quick_reply', 'longitude', 'latitude', 'flow_reply',
                    'http_status_code', 'mail_id', 'subject', 'body', 'media_ids', 'flow_docs', 'flow_images',
                    'flow_data', 'llm_call_id', 'user_identifier', 'temp_token', 'store_page_name', 'redirect_url',
                    'callback_identifier', 'is_followup', 'parent_log_id', 'date', 'cc']
        actual = processor.get_entities("tests")
        print([item["name"]  for item in actual])
        assert actual.__len__() == expected.__len__()
        assert all(item["name"] in expected for item in actual)

    def test_add_entity_duplicate(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            assert processor.add_entity("file_text", "tests", "testUser")

    def test_add_entity_duplicate_case_insensitive(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            assert processor.add_entity("File_Text", "tests", "testUser")

    def test_add_none_entity(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_entity(None, "tests", "testUser")

    def test_add_empty_entity(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_entity("", "tests", "testUser")

    def test_add_blank_entity(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_entity("  ", "tests", "testUser")

    def test_add_action(self):
        processor = MongoProcessor()
        assert processor.add_action("get_priority", "test", "testUser")
        action = Actions.objects(bot="test").get(name="get_priority")
        assert action.name == "get_priority"

    def test_add_action_starting_with_utter(self):
        processor = MongoProcessor()
        assert not processor.add_action("utter_get_priority", "test", "testUser")
        with pytest.raises(DoesNotExist):
            Actions.objects(bot="test").get(name="utter_get_priority")

    def test__action_data_object(self):
        assert Actions(name="test_action", bot='test', user='test')

    def test_data_obj_action_empty(self):
        with pytest.raises(ValidationError):
            Actions(name=" ", bot='test', user='test').save()

    def test_data_obj_action_starting_with_utter(self):
        with pytest.raises(ValidationError):
            Actions(name="utter_get_priority", bot='test', user='test').save()

    def test_get_actions(self):
        processor = MongoProcessor()
        actual = processor.get_actions("test")
        assert actual.__len__() == 1
        assert actual[0]['name'] == 'get_priority'

    def test_add_action_duplicate(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.add_action("get_priority", "test", "testUser")

    def test_add_action_duplicate_case_insensitive(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            assert processor.add_action("Utter_Priority", "tests", "testUser") is None

    def test_add_none_action(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_action(None, "tests", "testUser")

    def test_add_empty_action(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_action("", "tests", "testUser")

    def test_add_blank_action(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_action("  ", "tests", "testUser")

    def test_add_text_response(self):
        processor = MongoProcessor()
        assert processor.add_text_response("Great", "utter_Happy", "tests", "testUser")
        response = Responses.objects(
            bot="tests", name="utter_happy", text__text="Great"
        ).get()
        assert response.name == "utter_happy"
        assert response.text.text == "Great"

    def test_add_custom_response(self):
        processor = MongoProcessor()
        jsondata = {"type": "section",
                    "text": {
                        "text": "Make a bet on when the world will end:",
                        "type": "mrkdwn",
                        "accessory": {"type": "datepicker",
                                      "initial_date": "2019-05-21",
                                      "placeholder": {"type": "plain_text",
                                                      "text": "Select a date"}}}}
        assert processor.add_custom_response(jsondata, "utter_custom", "tests", "testUser")
        response = Responses.objects(
            bot="tests", name="utter_custom", custom__custom=jsondata
        ).get()
        assert response.name == "utter_custom"
        assert response.custom.custom == jsondata

    def test_add_text_response_case_insensitive(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.add_text_response("Great", "Utter_Happy", "tests", "testUser")

    def test_add_custom_response_case_insensitive(self):
        processor = MongoProcessor()
        jsondata = {"type": "section",
                    "text": {
                        "text": "Make a bet on when the world will end:",
                        "type": "mrkdwn",
                        "accessory": {"type": "datepicker",
                                      "initial_date": "2019-05-21",
                                      "placeholder": {"type": "plain_text",
                                                      "text": "Select a date"}}}}
        with pytest.raises(AppException, match='Utterance already exists!'):
            processor.add_custom_response(jsondata, "UTTER_CUSTOM", "tests", "testUser")

    def test_add_text_response_duplicate(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.add_text_response("Great", "utter_happy", "tests", "testUser")

    def test_add_custom_response_duplicate(self):
        processor = MongoProcessor()
        jsondata = {"type": "section",
                    "text": {
                        "text": "Make a bet on when the world will end:",
                        "type": "mrkdwn",
                        "accessory": {"type": "datepicker",
                                      "initial_date": "2019-05-21",
                                      "placeholder": {"type": "plain_text",
                                                      "text": "Select a date"}}}}
        with pytest.raises(AppException, match='Utterance already exists!'):
            processor.add_custom_response(jsondata, "utter_custom", "tests", "testUser")

    def test_add_custom_dict_check_response(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match="Utterance must be dict type and must not be empty"):
            processor.add_custom_response("Greetings", "utter_happy", "tests", "testUser")

    def test_get_text_response(self):
        processor = MongoProcessor()
        expected = ["Great, carry on!", "Great"]
        actual = list(processor.get_response("utter_happy", "tests"))
        assert actual.__len__() == expected.__len__()
        assert all(
            item["value"]["text"] in expected
            for item in actual
            if "text" in item["value"]
        )

    def test_get_custom_response(self):
        processor = MongoProcessor()
        actual = list(processor.get_response("utter_custom", "tests"))
        actual = actual[0]
        actual.pop("_id")
        assert actual == {'value': {'custom': {'type': 'section',
                                               'text': {'text': 'Make a bet on when the world will end:',
                                                        'type': 'mrkdwn', 'accessory': {'type': 'datepicker',
                                                                                        'initial_date': '2019-05-21',
                                                                                        'placeholder': {
                                                                                            'type': 'plain_text',
                                                                                            'text': 'Select a date'}}}}},
                          'type': 'json'}

    def test_get_text_response_empty_utterance(self):
        processor = MongoProcessor()
        actual = list(processor.get_response("", "tests"))
        assert actual.__len__() == 0
        actual = list(processor.get_response(" ", "tests"))
        assert actual.__len__() == 0

    def test_delete_text_response(self):
        processor = MongoProcessor()
        responses = list(processor.get_response(name="utter_happy", bot="tests"))
        expected_length = responses.__len__() - 1
        response = responses[0]
        expected_text = response['value']['text']
        processor.remove_document(Responses, response['_id'], "tests", "testUser")
        actual = list(processor.get_response("utter_happy", "tests"))
        assert actual.__len__() == expected_length
        assert all(
            expected_text != item["value"]["text"]
            for item in actual
            if "text" in item["value"]
        )

    def test_add_none_text_response(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_text_response(None, "utter_happy", "tests", "testUser")

    def test_add_none_custom_response(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_custom_response(None, "utter_custom", "tests", "testUser")

    def test_add_empty_text_Response(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_text_response("", "utter_happy", "tests", "testUser")

    def test_add_empty_custom_response(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_custom_response("", "utter_custom", "tests", "testUser")

    def test_add_blank_text_response(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_text_response("", "utter_happy", "tests", "testUser")

    def test_add_blank_custom_response(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_custom_response("", "utter_custom", "tests", "testUser")

    def test_add_none_response_name(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_text_response("Greet", None, "tests", "testUser")

    def test_add_none_custom_response_name(self):
        processor = MongoProcessor()
        jsondata = {"type": "section",
                    "text": {
                        "text": "Make a bet on when the world will end:",
                        "type": "mrkdwn",
                        "accessory": {"type": "datepicker",
                                      "initial_date": "2019-05-21",
                                      "placeholder": {"type": "plain_text",
                                                      "text": "Select a date"}}}}
        with pytest.raises(AppException):
            processor.add_custom_response(jsondata, None, "tests", "testUser")

    def test_add_empty_response_name(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_text_response("Welcome", "", "tests", "testUser")

    def test_add_blank_response_name(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_text_response("Welcome", " ", "tests", "testUser")

    def test_edit_custom_responses_duplicate(self):
        processor = MongoProcessor()
        jsondata = {"type": "section",
                    "text": {
                        "text": "Make a bet on when the world will end:",
                        "type": "mrkdwn",
                        "accessory": {"type": "button",
                                      "initial_date": "2019-05-21",
                                      "placeholder": {"type": "plain_text",
                                                      "text": "Select a date"}}}}
        assert processor.add_custom_response(jsondata, "utter_custom", "tests", "testUser")
        responses = list(processor.get_response("utter_custom", "tests"))
        with pytest.raises(AppException, match="Utterance already exists!"):
            processor.edit_custom_response(responses[0]["_id"], jsondata, name="utter_happy", bot="tests",
                                           user="testUser")

    def test_edit_custom_responses_empty(self):
        processor = MongoProcessor()
        jsondata = {}
        responses = list(processor.get_response("utter_custom", "tests"))
        with pytest.raises(ValidationError, match="Utterance must be dict type and must not be empty"):
            processor.edit_custom_response(responses[0]["_id"], jsondata, name="utter_custom", bot="tests",
                                           user="testUser")

    def test_edit_custom_responses(self):
        processor = MongoProcessor()
        jsondata = {"type": "section",
                    "text": {
                        "text": "Make a bet",
                        "type": "mrkdwn",
                        "accessory": {"type": "button",
                                      "initial_date": "2019-05-21",
                                      "placeholder": {"type": "plain_text",
                                                      "text": "Select a date"}}}}
        responses = list(processor.get_response("utter_custom", "tests"))
        processor.edit_custom_response(responses[0]["_id"], jsondata, name="utter_custom", bot="tests", user="testUser")
        responses = list(processor.get_response("utter_custom", "tests"))
        assert any(response['value']['custom'] == jsondata and response['type'] == "json"
                   for response in responses if "custom" in response['value'])

    def test_add_catalog_custom_response_convention(self):
        processor = MongoProcessor()
        catalog_payload = {
            "type": "catalog",
            "data": {
                "page_name": "store_home",
                "identifierType": "slot",
                "identifierValue": "customer_id"
            }
        }
        # R1: payload has marker field, data section, valid identifierType
        assert catalog_payload["type"] == "catalog"
        assert all(k in catalog_payload["data"] for k in ("page_name", "identifierType", "identifierValue"))
        assert catalog_payload["data"]["identifierType"] in ("slot", "value")
        # R2: saved via existing create operation, no endpoint change
        assert processor.add_custom_response(catalog_payload, "utter_catalog_test", "tests", "testUser")

    def test_get_catalog_custom_response_round_trip(self):
        # R3: fetch returns correct marker, page_name, identifierType, identifierValue
        processor = MongoProcessor()
        responses = list(processor.get_response("utter_catalog_test", "tests"))
        assert len(responses) > 0
        resp = responses[0]
        payload = resp["value"]["custom"]
        assert payload["type"] == "catalog"
        assert payload["data"]["page_name"] == "store_home"
        assert payload["data"]["identifierType"] == "slot"
        assert payload["data"]["identifierValue"] == "customer_id"

    def test_edit_catalog_custom_response_round_trip(self):
        # R3: after edit, fetch returns updated values; R2: uses existing edit operation
        processor = MongoProcessor()
        updated_payload = {
            "type": "catalog",
            "data": {
                "page_name": "store_detail",
                "identifierType": "value",
                "identifierValue": "acme-corp"
            }
        }
        responses = list(processor.get_response("utter_catalog_test", "tests"))
        processor.edit_custom_response(
            responses[0]["_id"], updated_payload, name="utter_catalog_test", bot="tests", user="testUser"
        )
        responses = list(processor.get_response("utter_catalog_test", "tests"))
        payload = responses[0]["value"]["custom"]
        assert payload["type"] == "catalog"
        assert payload["data"]["page_name"] == "store_detail"
        assert payload["data"]["identifierType"] == "value"
        assert payload["data"]["identifierValue"] == "acme-corp"

    def test_catalog_identifiertype_value_convention(self):
        # R1: identifierType "value" is accepted
        processor = MongoProcessor()
        catalog_payload = {
            "type": "catalog",
            "data": {
                "page_name": "offers",
                "identifierType": "value",
                "identifierValue": "literal-id-123"
            }
        }
        assert catalog_payload["data"]["identifierType"] in ("slot", "value")
        assert processor.add_custom_response(catalog_payload, "utter_catalog_value_test", "tests", "testUser")
        responses = list(processor.get_response("utter_catalog_value_test", "tests"))
        assert responses[0]["value"]["custom"]["data"]["identifierType"] == "value"

    def test_non_catalog_custom_response_unaffected(self):
        # R4: non-catalog custom saves and fetches unchanged, never reinterpreted as catalog
        processor = MongoProcessor()
        plain_payload = {"type": "image", "url": "https://example.com/img.png"}
        assert processor.add_custom_response(plain_payload, "utter_non_catalog_test", "tests", "testUser")
        responses = list(processor.get_response("utter_non_catalog_test", "tests"))
        payload = responses[0]["value"]["custom"]
        assert payload == plain_payload
        assert payload.get("type") != "catalog"

    def test_catalog_label_field_round_trip(self):
        # R1 c4: data section MAY contain optional label field with any string value
        # R3 c4: label value equals saved value on fetch
        processor = MongoProcessor()
        catalog_payload = {
            "type": "catalog",
            "data": {
                "page_name": "store_home",
                "identifierType": "slot",
                "identifierValue": "customer_id",
                "label": "View Catalog"
            }
        }
        assert processor.add_custom_response(catalog_payload, "utter_catalog_label_test", "tests", "testUser")
        responses = list(processor.get_response("utter_catalog_label_test", "tests"))
        assert len(responses) > 0
        payload = responses[0]["value"]["custom"]
        assert payload["type"] == "catalog"
        assert payload["data"]["label"] == "View Catalog"

    def test_catalog_label_empty_and_whitespace_no_validation_error(self):
        # R1 c5: saving with empty string or whitespace-only label succeeds with no validation error
        processor = MongoProcessor()
        for label_value in ["", "   "]:
            catalog_payload = {
                "type": "catalog",
                "data": {
                    "page_name": "store_home",
                    "identifierType": "value",
                    "identifierValue": "acme",
                    "label": label_value
                }
            }
            utterance_name = f"utter_catalog_empty_label_{label_value.strip() or 'empty'}_test"
            assert processor.add_custom_response(
                catalog_payload, utterance_name, "tests", "testUser"
            ), f"Save should succeed for label={repr(label_value)}"
            responses = list(processor.get_response(utterance_name, "tests"))
            assert responses[0]["value"]["custom"]["data"]["label"] == label_value

    def test_catalog_label_edit_add_change_remove(self):
        # R3 c5: editing label (add, change, remove) round-trips correctly
        processor = MongoProcessor()
        base_payload = {
            "type": "catalog",
            "data": {
                "page_name": "offers",
                "identifierType": "value",
                "identifierValue": "promo-id"
            }
        }
        assert processor.add_custom_response(base_payload, "utter_catalog_label_edit_test", "tests", "testUser")
        responses = list(processor.get_response("utter_catalog_label_edit_test", "tests"))
        resp_id = responses[0]["_id"]

        # add label
        with_label = dict(base_payload)
        with_label["data"] = dict(base_payload["data"], label="Shop Now")
        processor.edit_custom_response(resp_id, with_label, name="utter_catalog_label_edit_test", bot="tests", user="testUser")
        responses = list(processor.get_response("utter_catalog_label_edit_test", "tests"))
        assert responses[0]["value"]["custom"]["data"]["label"] == "Shop Now"

        # change label
        changed = dict(base_payload)
        changed["data"] = dict(base_payload["data"], label="Browse")
        processor.edit_custom_response(resp_id, changed, name="utter_catalog_label_edit_test", bot="tests", user="testUser")
        responses = list(processor.get_response("utter_catalog_label_edit_test", "tests"))
        assert responses[0]["value"]["custom"]["data"]["label"] == "Browse"

        # remove label
        removed = dict(base_payload)
        removed["data"] = dict(base_payload["data"])  # no label key
        processor.edit_custom_response(resp_id, removed, name="utter_catalog_label_edit_test", bot="tests", user="testUser")
        responses = list(processor.get_response("utter_catalog_label_edit_test", "tests"))
        assert "label" not in responses[0]["value"]["custom"]["data"]

    def test_get_session_config(self):
        processor = MongoProcessor()
        session_config = processor.get_session_config("tests")
        assert session_config
        assert all(
            session_config[key] for key in ["sesssionExpirationTime", "carryOverSlots"]
        )

    def test_update_session_config(self):
        processor = MongoProcessor()
        session_config = processor.get_session_config("tests")
        assert session_config
        assert all(
            session_config[key] for key in ["sesssionExpirationTime", "carryOverSlots"]
        )
        id_updated = processor.add_session_config(
            id=session_config["_id"],
            sesssionExpirationTime=30,
            carryOverSlots=False,
            bot="tests",
            user="testUser",
        )
        assert id_updated == session_config["_id"]
        session_config = processor.get_session_config("tests")
        assert session_config["sesssionExpirationTime"] == 30
        assert session_config["carryOverSlots"] is False

    def test_add_session_config_duplicate(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_session_config(
                sesssionExpirationTime=30,
                carryOverSlots=False,
                bot="tests",
                user="testUser",
            )

    def test_add_session_config_empty_id(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_session_config(
                id="",
                sesssionExpirationTime=30,
                carryOverSlots=False,
                bot="tests",
                user="testUser",
            )

    def test_train_on_multiflow_story(self):
        bot = "tests"
        user = "testUser"
        processor = MongoProcessor()
        list(processor.add_training_example(["How is the sky today?"], intent="query", bot=bot, user=user,
                                            is_integration=False))
        list(processor.add_training_example(["Will it rain?"], intent="more_queries", bot=bot, user=user,
                                            is_integration=False))
        list(processor.add_training_example(["Bubye, will see you!"], intent="goodbye", bot=bot, user=user,
                                            is_integration=False))

        processor.add_response({"text": "It is Sunny!"}, "utter_query", bot, user)
        processor.add_response({"text": "See you, Bye!"}, "utter_goodbye", bot, user)
        processor.add_response({"text": "No, it won't rain."}, "utter_more_queries", bot, user)

        steps = [
            {"step": {"name": "query", "type": "INTENT", "node_id": "1", "component_id": "61m96mPGu2VexybDeVg1dLyH"},
             "connections": [
                 {"name": "utter_query", "type": "BOT", "node_id": "2", "component_id": "61uaImwNrsJI1pVphl8mZh20"}]
             },
            {"step": {"name": "utter_query", "type": "BOT", "node_id": "2", "component_id": "61uaImwNrsJI1pVphl8mZh20"},
             "connections": [
                 {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "62By0VXVLpUNDNPqkr5vRRzm"},
                 {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "62N9BCfSKVYOKoBivGhWDRHC"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "62N9BCfSKVYOKoBivGhWDRHC"},
             "connections": [
                 {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "62uzXd9Pj5a9tEbVBkMuVn3o"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5",
                      "component_id": "62uzXd9Pj5a9tEbVBkMuVn3o"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                      "component_id": "62ib6tlbgIGth8vBSwSYFvbS"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3",
                      "component_id": "62By0VXVLpUNDNPqkr5vRRzm"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                              "component_id": "62ib6tlbgIGth8vBSwSYFvbS"}]
             }
        ]

        story_dict = {'name': "story for training", 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        story = MultiflowStories.objects(block_name="story for training", bot=bot).get()
        assert len(story.events) == 6

    def test_add_session_config(self):
        processor = MongoProcessor()
        id_add = processor.add_session_config(
            sesssionExpirationTime=30, carryOverSlots=False, bot="test", user="testUser"
        )
        assert id_add

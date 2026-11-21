from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training



def test_get_metering():
    response = client.get(
        f"/api/bot/{pytest.bot}/metric/test_chat",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual == {"success": True, "message": None, "data": 0, "error_code": 0}
    response = client.get(
        f"/api/bot/{pytest.bot}/metric/prod_chat",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual == {"success": True, "message": None, "data": 0, "error_code": 0}


def test_add_story_with_no_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_story_with_no_type",
            "type": "STORY",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow added successfully"

    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "STORY",
            "steps": [
                {"name": "test_greet", "type": "INTENT"},
                {"name": "utter_test_greet", "type": "ACTION"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow added successfully"
    assert actual["success"]
    assert actual["error_code"] == 0


def test_get_stories_another_bot():
    response = client.get(
        f"/api/bot/{pytest.bot}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert actual["data"][0]["template_type"] == "CUSTOM"
    assert actual["data"][1]["template_type"] == "CUSTOM"
    assert actual["data"][8]["template_type"] == "CUSTOM"
    assert actual["data"][8]["name"] == "ask the user to rephrase whenever they send a message with low nlu confidence"
    assert actual["data"][9]["template_type"] == "Q&A"
    assert actual["data"][9]["name"] == "test_path"


def test_add_regex_invalid():
    response = client.post(
        f"/api/bot/{pytest.bot}/regex",
        json={"name": "bot_add", "pattern": "[0-9"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "invalid regular expression"


def test_add_regex_empty_name():
    response = client.post(
        f"/api/bot/{pytest.bot}/regex",
        json={"name": "", "pattern": "q"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"][0]["msg"] == "Regex name cannot be empty or a blank space"


def test_add_regex_empty_pattern():
    response = client.post(
        f"/api/bot/{pytest.bot}/regex",
        json={"name": "b", "pattern": ""},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"][0]["msg"] == "Regex pattern cannot be empty or a blank space"
    )


def test_add_regex_():
    response = client.post(
        f"/api/bot/{pytest.bot}/regex",
        json={"name": "b", "pattern": "bb"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Regex pattern added successfully!"


def test_get_regex():
    response = client.get(
        f"/api/bot/{pytest.bot}/regex",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 1
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])
    assert "b" in actual["data"][0].values()
    assert "bb" in actual["data"][0].values()


def test_edit_regex():
    response = client.put(
        f"/api/bot/{pytest.bot}/regex",
        json={"name": "b", "pattern": "bbb"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Regex pattern modified successfully!"

    response = client.get(
        f"/api/bot/{pytest.bot}/regex",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 1
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])
    assert "b" in actual["data"][0].values()
    assert "bbb" in actual["data"][0].values()


def test_delete_regex():
    response = client.delete(
        f"/api/bot/{pytest.bot}/regex/b",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Regex pattern deleted!"

    response = client.get(
        f"/api/bot/{pytest.bot}/regex",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 0
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_add_and_move_training_examples_to_different_intent():
    response = client.post(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        json={"data": ["hey, there [bot](bot)!!"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"][0]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    response = client.get(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 7

    response = client.post(
        f"/api/bot/{pytest.bot}/intents",
        json={"data": "test_add_and_move"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Intent added successfully!"

    response = client.post(
        f"/api/bot/{pytest.bot}/training_examples/move/test_add_and_move",
        json={
            "data": [
                "this will be moved",
                "this is a new [example](example)",
                " ",
                "",
                "hey, there [bot](bot)!!",
            ]
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"][0]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    response = client.get(
        f"/api/bot/{pytest.bot}/training_examples/test_add_and_move",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 3


def test_add_and_move_training_examples_to_different_intent_not_exists():
    response = client.post(
        f"/api/bot/{pytest.bot}/training_examples/move/greeting",
        json={
            "data": [
                "this will be moved",
                "this is a new [example](example)",
                " ",
                "",
                "hey, there [bot](bot)!!",
            ]
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Intent does not exists"


def test_get_lookup_tables():
    response = client.get(
        f"/api/bot/{pytest.bot}/lookups",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 0
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_add_lookup_tables():
    response = client.post(
        f"/api/bot/{pytest.bot}/lookup",
        json={"data": "country"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Lookup added!"
    assert actual["data"]["_id"]

    response = client.post(
        f"/api/bot/{pytest.bot}/lookup/country/values",
        json={"value": ["india", "australia"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Lookup values added!"
    assert all(
        key in item.keys() for item in actual["data"] for key in ["_id", "value"]
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/lookup",
        json={"data": "number"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Lookup added!"
    assert actual["data"]["_id"]

    response = client.post(
        f"/api/bot/{pytest.bot}/lookup/number/values",
        json={"value": ["one", "two"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Lookup values added!"

    response = client.get(
        f"/api/bot/{pytest.bot}/lookup/number/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert all(item["value"] in ["one", "two"] for item in actual["data"])
    assert all(
        key in item.keys()
        for item in actual["data"]
        for key in ["_id", "lookup", "value"]
    )


def test_get_lookup_table_values():
    response = client.get(
        f"/api/bot/{pytest.bot}/lookup/country/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 2


def test_add_lookup_duplicate():
    response = client.post(
        f"/api/bot/{pytest.bot}/lookup/country/values",
        json={"value": ["india"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Lookup value already exists"


def test_add_lookup_empty():
    response = client.post(
        f"/api/bot/{pytest.bot}/lookup/country/values",
        json={"value": []},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"][0]["msg"] == "value field cannot be empty"


def test_edit_lookup():
    response = client.get(
        f"/api/bot/{pytest.bot}/lookup/country/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    response = client.put(
        f"/api/bot/{pytest.bot}/lookup/country/value/{actual['data'][0]['_id']}",
        json={"data": "japan"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Lookup value updated!"


def test_add_lookup_empty_name():
    response = client.post(
        f"/api/bot/{pytest.bot}/lookup/%20/values",
        json={"value": ["h"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Lookup cannot be an empty string"


def test_delete_lookup_one_value():
    response = client.get(
        f"/api/bot/{pytest.bot}/lookup/country/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    response = client.delete(
        f"/api/bot/{pytest.bot}/lookup/country/value/{actual['data'][0]['_id']}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Lookup value removed!"

    response = client.get(
        f"/api/bot/{pytest.bot}/lookup/country/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert len(actual["data"]) == 1


def test_delete_lookup():
    response = client.get(
        f"/api/bot/{pytest.bot}/lookups",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0

    lookup = actual["data"][0]

    response = client.delete(
        f"/api/bot/{pytest.bot}/lookup/{lookup['_id']}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Lookup removed!"

    response = client.get(
        f"/api/bot/{pytest.bot}/lookups",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert len(actual["data"]) == 1


def test_add_lookup_empty_value_element():
    response = client.post(
        f"/api/bot/{pytest.bot}/lookup/country/values",
        json={"value": ["df", ""]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"][0]["msg"] == "lookup value cannot be empty or a blank space"
    )


def test_list_form_none_exists():
    response = client.get(
        f"/api/bot/{pytest.bot}/forms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == []


def test_add_form_invalid_parameters():
    path = [
        {
            "ask_questions": [],
            "slot": "name",
            "slot_set": {"type": "custom", "value": "Mahesh"},
        },
        {
            "ask_questions": ["seats required?"],
            "slot": "num_people",
            "slot_set": {"type": "current", "value": 10},
        },
    ]
    request = {"name": "restaurant_form", "settings": path}
    response = client.post(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "settings", 0, "ask_questions"],
            "msg": "Questions cannot be empty or contain spaces",
            "type": "value_error",
        }
    ]

    path = [
        {
            "ask_questions": [" "],
            "slot": "name",
            "slot_set": {"type": "custom", "value": "Mahesh"},
        },
        {
            "ask_questions": ["seats required?"],
            "slot": "num_people",
            "slot_set": {"type": "current", "value": 10},
        },
    ]
    request = {"name": "restaurant_form", "settings": path}
    response = client.post(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "settings", 0, "ask_questions"],
            "msg": "Questions cannot be empty or contain spaces",
            "type": "value_error",
        }
    ]

    path = [
        {
            "ask_questions": ["name ?"],
            "slot": "",
            "slot_set": {"type": "custom", "value": "Mahesh"},
        },
        {
            "ask_questions": ["seats required?"],
            "slot": "num_people",
            "slot_set": {"type": "current", "value": 10},
        },
    ]
    request = {"name": "restaurant_form", "settings": path}
    response = client.post(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "settings", 0, "slot"],
            "msg": "Slot is required",
            "type": "value_error",
        }
    ]


def test_get_slot_mapping_empty():
    response = client.get(
        f"/api/bot/{pytest.bot}/slots/mapping",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["data"] == []


def test_add_slot_mapping():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "name", "type": "text"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]
    assert actual["error_code"] == 0
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "name",
            "mapping": {"type": "from_text", "value": "user", "entity": "name"},
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_empty_slot_mapping():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={"slot": "num_people", "mapping": {}},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["success"]
    assert actual["message"] == [
        {
            "loc": ["body", "mapping", 'type'],
            "msg": "field required",
            "type": "value_error.missing",
        }
    ]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={"slot": "num_people",
              "mapping": {"type": "from_text", "conditions": [{"requested_slot": "num_people"}]}},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["success"]
    assert actual["message"] == [{'loc': ['body', 'mapping', 'conditions', 0, '__root__'],
                                  'msg': 'active_loop is required to add requested_slot as condition!',
                                  'type': 'value_error'}]


def test_add_form_with_invalid_slot_set_type():
    path = [
        {
            "ask_questions": ["what is your name?", "name?"],
            "slot": "name",
            "slot_set": {"type": "invalid_type", "value": "Mahesh"},
        },
        {
            "ask_questions": ["seats required?"],
            "slot": "num_people",
            "slot_set": {"type": "current", "value": 10},
        },
    ]
    request = {"name": "restaurant_form", "settings": path}
    response = client.post(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert str(actual["message"]).__contains__(
        "value is not a valid enumeration member"
    )


def test_add_form():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "num_people", "type": "float"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "num_people",
            "mapping":
                {
                    "type": "from_entity",
                    "intent": ["inform", "request_restaurant"],
                    "entity": "number",
                }
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "cuisine", "type": "text"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "cuisine",
            "mapping": {"type": "from_entity", "entity": "cuisine"},
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "outdoor_seating", "type": "text"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "outdoor_seating",
            "mapping":
                {"type": "from_text", "not_intent": ["affirm"],
                 "conditions": [{"active_loop": "booking", "requested_slot": "outdoor_seating"}]}
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "preferences", "type": "text"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "preferences",
            "mapping":
                {"type": "from_text", "not_intent": ["affirm"],
                 "conditions": [{"active_loop": "booking", "requested_slot": "preferences"}]}
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "feedback", "type": "text"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "feedback",
            "mapping":
                {"type": "from_entity", "entity": "feedback"}
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    path = [
        {
            "ask_questions": ["please give us your name?"],
            "slot": "name",
            "slot_set": {"type": "custom", "value": "Mahesh"},
        },
        {
            "ask_questions": ["seats required?"],
            "slot": "num_people",
            "slot_set": {"type": "current", "value": 10},
        },
        {
            "ask_questions": ["type of cuisine?"],
            "slot": "cuisine",
            "slot_set": {"type": "current", "value": "Indian Cuisine"},
        },
        {"ask_questions": ["outdoor seating required?"], "slot": "outdoor_seating"},
        {
            "ask_questions": ["any preferences?"],
            "slot": "preferences",
            "slot_set": {"type": "slot", "value": "preferences"},
        },
        {
            "ask_questions": ["Please give your feedback on your experience so far"],
            "slot": "feedback",
            "slot_set": {"type": "custom", "value": "Very Nice!"},
        },
    ]
    request = {"name": "restaurant_form", "settings": path}
    response = client.post(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Form added"


def test_add_slot_mapping_2():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "na", "type": "text"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]
    assert actual["error_code"] == 0
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "na",
            "mapping": {"type": "from_text", "value": "user", "entity": "na"},
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]
    assert actual["error_code"] == 0


def test_delete_slot_mapping_exists():
    response = client.delete(
        f"/api/bot/{pytest.bot}/slots/mapping/na",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Slot mapping deleted"


def test_delete_slots_exists():
    response = client.delete(
        f"/api/bot/{pytest.bot}/slots/na",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["message"] == "Slot deleted!"
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_form_with_any_slot():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "user_feedback", "type": "any"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "user_feedback",
            "mapping":
                {"type": "from_text"},
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "user_feedback",
            "mapping":
                {"type": "from_entity", "entity": "user_feedback"},
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]
    path = [
        {
            "ask_questions": ["please give us your name?"],
            "slot": "name",
            "slot_set": {"type": "custom", "value": "Mahesh"},
        },
        {
            "ask_questions": ["seats required?"],
            "slot": "num_people",
            "slot_set": {"type": "current", "value": 10},
        },
        {
            "ask_questions": ["type of cuisine?"],
            "slot": "cuisine",
            "slot_set": {"type": "current", "value": "Indian Cuisine"},
        },
        {"ask_questions": ["outdoor seating required?"], "slot": "outdoor_seating"},
        {
            "ask_questions": ["any preferences?"],
            "slot": "preferences",
            "slot_set": {"type": "slot", "value": "preferences"},
        },
        {
            "ask_questions": ["Please give your feedback on your experience so far"],
            "slot": "user_feedback",
            "slot_set": {"type": "custom", "value": "Very Nice!"},
        }
    ]
    request = {"name": "restaurant_booking_form", "settings": path}
    response = client.post(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "form will not accept any type slots: {'user_feedback'}"


def test_add_utterance_to_form():
    response = client.post(
        f"/api/bot/{pytest.bot}/response/utter_ask_restaurant_form_num_people?form_attached=restaurant_form",
        json={"data": "num people?"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Response added!"


def test_delete_utterance_in_form():
    response = client.get(
        f"/api/bot/{pytest.bot}/response/utter_ask_restaurant_form_num_people",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]
    assert actual["success"]
    assert actual["error_code"] == 0
    id = actual["data"][0]["_id"]
    response = client.delete(
        f"/api/bot/{pytest.bot}/response/{id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Response removed!"


def test_create_rule_with_form_invalid_step():
    steps = [
        {"name": None, "type": "INTENT"},
        {"name": "know_user", "type": "FORM_ACTION"},
        {"name": "know_user", "type": "FORM_START"},
        {"type": "FORM_END"},
        {"name": "utter_submit", "type": "BOT"},
    ]
    story_dict = {
        "name": "activate form",
        "steps": steps,
        "type": "RULE",
        "template_type": "CUSTOM",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json=story_dict,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "steps"],
            "msg": "Only FORM_END step type can have empty name",
            "type": "value_error",
        }
    ]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422

    steps = [
        {"name": "greet", "type": "INTENT"},
        {"name": "   ", "type": "FORM_ACTION"},
        {"name": "know_user", "type": "FORM_START"},
        {"type": "FORM_END"},
        {"name": "utter_submit", "type": "BOT"},
    ]
    story_dict = {
        "name": "activate form",
        "steps": steps,
        "type": "RULE",
        "template_type": "CUSTOM",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json=story_dict,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "steps"],
            "msg": "Only FORM_END step type can have empty name",
            "type": "value_error",
        }
    ]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_create_rule_with_form():
    steps = [
        {"name": "greet", "type": "INTENT"},
        {"name": "know_user", "type": "FORM_ACTION"},
        {"name": "know_user", "type": "FORM_START"},
        {"type": "FORM_END"},
        {"name": "utter_submit", "type": "BOT"},
    ]
    story_dict = {
        "name": "activate form",
        "steps": steps,
        "type": "RULE",
        "template_type": "CUSTOM",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json=story_dict,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0


def test_create_stories_with_form():
    steps = [
        {"name": "greet", "type": "INTENT"},
        {"name": "know_user", "type": "FORM_ACTION"},
        {"name": "know_user", "type": "FORM_START"},
        {"name": "deny", "type": "INTENT"},
        {"name": "utter_ask_continue", "type": "BOT"},
        {"name": "affirm", "type": "INTENT"},
        {"type": "FORM_END"},
        {"name": "utter_submit", "type": "BOT"},
    ]
    story_dict = {
        "name": "stop form - continue",
        "steps": steps,
        "type": "STORY",
        "template_type": "CUSTOM",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json=story_dict,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0


def test_get_form_with_no_validations():
    response = client.get(
        f"/api/bot/{pytest.bot}/forms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    form_id = actual["data"][0]["_id"]

    response = client.get(
        f"/api/bot/{pytest.bot}/forms/{form_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    form = actual["data"]
    assert len(form["settings"]) == 6
    assert form["settings"][0]["slot"] == "name"
    assert form["settings"][1]["slot"] == "num_people"
    assert form["settings"][2]["slot"] == "cuisine"
    assert form["settings"][3]["slot"] == "outdoor_seating"
    assert form["settings"][4]["slot"] == "preferences"
    assert form["settings"][5]["slot"] == "feedback"
    assert form["settings"][0]["ask_questions"][0]["_id"]
    assert form["settings"][1]["ask_questions"][0]["_id"]
    assert form["settings"][2]["ask_questions"][0]["_id"]
    assert form["settings"][3]["ask_questions"][0]["_id"]
    assert form["settings"][4]["ask_questions"][0]["_id"]
    assert form["settings"][5]["ask_questions"][0]["_id"]
    assert (
            form["settings"][0]["ask_questions"][0]["value"]["text"]
            == "please give us your name?"
    )
    assert form["settings"][1]["ask_questions"][0]["value"]["text"] == "seats required?"
    assert (
            form["settings"][2]["ask_questions"][0]["value"]["text"] == "type of cuisine?"
    )
    assert (
            form["settings"][3]["ask_questions"][0]["value"]["text"]
            == "outdoor seating required?"
    )
    assert (
            form["settings"][4]["ask_questions"][0]["value"]["text"] == "any preferences?"
    )
    assert (
            form["settings"][5]["ask_questions"][0]["value"]["text"]
            == "Please give your feedback on your experience so far"
    )
    assert form["settings"][0]["slot_set"] == {"type": "custom", "value": "Mahesh"}
    assert form["settings"][1]["slot_set"] == {"type": "current", "value": 10}
    assert form["settings"][2]["slot_set"] == {
        "type": "current",
        "value": "Indian Cuisine",
    }
    assert form["settings"][3]["slot_set"] == {"type": "current", "value": None}
    assert form["settings"][4]["slot_set"] == {"type": "slot", "value": "preferences"}
    assert form["settings"][5]["slot_set"] == {"type": "custom", "value": "Very Nice!"}

    response = client.get(
        f"/api/bot/{pytest.bot}/response/all",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    saved_responses = {response["name"] for response in actual["data"]}
    assert (
            len(
                {
                    "utter_ask_restaurant_form_name",
                    "utter_ask_restaurant_form_num_people",
                    "utter_ask_restaurant_form_cuisine",
                    "utter_ask_restaurant_form_outdoor_seating",
                    "utter_ask_restaurant_form_preferences",
                    "utter_ask_restaurant_form_feedback",
                }.difference(saved_responses)
            )
            == 0
    )
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_form_slot_not_present():
    path = [
        {
            "ask_questions": ["please give us your location?"],
            "slot": "location",
            "slot_set": {"type": "custom", "value": "Bangalore"},
            "mapping": [
                {"type": "from_text", "value": "user", "entity": "name"},
                {"type": "from_entity", "entity": "name"},
            ],
        },
        {
            "ask_questions": ["seats required?"],
            "slot": "num_people",
            "slot_set": {"type": "current", "value": 10},
            "mapping": [
                {
                    "type": "from_entity",
                    "intent": ["inform", "request_restaurant"],
                    "entity": "number",
                }
            ],
        },
        {
            "ask_questions": ["type of cuisine?"],
            "slot": "cuisine",
            "slot_set": {"type": "current", "value": "Indian Cuisine"},
            "mapping": [{"type": "from_entity", "entity": "cuisine"}],
        },
        {
            "ask_questions": ["outdoor seating required?"],
            "slot": "outdoor_seating",
            "slot_set": {"type": "custom", "value": True},
            "mapping": [
                {"type": "from_entity", "entity": "seating"},
                {"type": "from_intent", "intent": ["affirm"], "value": True},
                {"type": "from_intent", "intent": ["deny"], "value": False},
            ],
        },
        {
            "ask_questions": ["any preferences?"],
            "slot": "preferences",
            "slot_set": {"type": "slot", "value": "preferences"},
            "mapping": [
                {"type": "from_text", "not_intent": ["affirm"]},
                {
                    "type": "from_intent",
                    "intent": ["affirm"],
                    "value": "no additional preferences",
                },
            ],
        },
        {
            "ask_questions": ["Please give your feedback on your experience so far"],
            "slot": "feedback",
            "slot_set": {"type": "custom", "value": "Very Nice!"},
            "mapping": [
                {"type": "from_text"},
                {"type": "from_entity", "entity": "feedback"},
            ],
        },
    ]
    request = {"name": "know_user", "settings": path}
    response = client.post(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"].__contains__("slots not exists: {")


def test_add_form_with_validations():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "age", "type": "float"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "age",
            "mapping":
                {
                    "type": "from_intent",
                    "intent": ["get_age"],
                    "entity": "age",
                    "value": "18",
                }
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "location", "type": "text"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "location",
            "mapping": {"type": "from_entity", "entity": "location"},
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "occupation", "type": "text"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "occupation",
            "mapping":
                {
                    "type": "from_intent",
                    "intent": ["get_occupation"],
                    "entity": "occupation",
                    "value": "business",
                }
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "occupation",
            "mapping":
                {"type": "from_text", "entity": "occupation", "value": "engineer"},
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "occupation",
            "mapping": {"type": "from_entity", "entity": "occupation"},
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "occupation",
            "mapping":
                {
                    "type": "from_trigger_intent",
                    "entity": "occupation",
                    "value": "tester",
                    "intent": ["get_business", "is_engineer", "is_tester"],
                    "not_intent": ["get_age", "get_name"],
                }
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    name_validation = (
        "if (&& name.contains('i') && name.length() > 4 || !name.contains("
        ")) "
        "{return true;} else {return false;}"
    )

    age_validation = "if (age > 10 && age < 70) {return true;} else {return false;}"

    occupation_validation = (
        "if (occupation in ['teacher', 'programmer', 'student', 'manager'] "
        "&& !occupation.contains("
        ") && occupation.length() > 20) "
        "{return true;} else {return false;}"
    )

    path = [
        {
            "ask_questions": ["what is your name?", "name?"],
            "slot": "name",
            "validation_semantic": name_validation,
            "is_required": True,
            "slot_set": {"type": "custom", "value": "Mahesh"},
            "valid_response": "got it",
            "invalid_response": "please rephrase",
        },
        {
            "ask_questions": ["what is your age?", "age?"],
            "slot": "age",
            "validation_semantic": age_validation,
            "is_required": True,
            "slot_set": {"type": "current", "value": 22},
            "valid_response": "valid entry",
            "invalid_response": "please enter again",
        },
        {
            "ask_questions": ["what is your location?", "location?"],
            "slot": "location",
            "slot_set": {"type": "custom", "value": "Bangalore"},
        },
        {
            "ask_questions": ["what is your occupation?", "occupation?"],
            "slot": "occupation",
            "slot_set": {"type": "slot", "value": "occupation"},
            "validation_semantic": occupation_validation,
            "is_required": False,
        },
    ]
    request = {"name": "know_user_form", "settings": path}
    response = client.post(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Form added"


def test_get_form_with_validations():
    response = client.get(
        f"/api/bot/{pytest.bot}/forms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    form_id = actual["data"][1]["_id"]

    response = client.get(
        f"/api/bot/{pytest.bot}/forms/{form_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    form = actual["data"]
    assert len(form["settings"]) == 4
    assert form["settings"][0]["slot"] == "name"
    assert form["settings"][1]["slot"] == "age"
    assert form["settings"][2]["slot"] == "location"
    assert form["settings"][3]["slot"] == "occupation"
    assert form["settings"][0]["ask_questions"][0]["_id"]
    assert form["settings"][1]["ask_questions"][0]["_id"]
    assert form["settings"][2]["ask_questions"][0]["_id"]
    assert form["settings"][0]["ask_questions"][0]["value"]["text"]
    assert form["settings"][1]["ask_questions"][0]["value"]["text"]
    assert form["settings"][2]["ask_questions"][0]["value"]["text"]
    assert form["settings"][3]["ask_questions"][0]["value"]["text"]
    assert (
            form["settings"][0]["validation_semantic"]
            == "if (&& name.contains('i') && name.length() > 4 || "
               "!name.contains("
               ")) {return true;} else {return false;}"
    )
    assert form["settings"][0]["is_required"]
    assert form["settings"][0]["slot_set"] == {"type": "custom", "value": "Mahesh"}
    assert (
            form["settings"][1]["validation_semantic"]
            == "if (age > 10 && age < 70) {return true;} else {return false;}"
    )
    assert form["settings"][1]["is_required"]
    assert form["settings"][1]["slot_set"] == {"type": "current", "value": 22}
    assert not form["settings"][2]["validation_semantic"]
    assert form["settings"][2]["is_required"]
    assert form["settings"][2]["slot_set"] == {"type": "custom", "value": "Bangalore"}
    assert (
            form["settings"][3]["validation_semantic"]
            == "if (occupation in ['teacher', 'programmer', 'student', 'manager'] "
               "&& !occupation.contains("
               ") && occupation.length() > 20) "
               "{return true;} else {return false;}"
    )
    assert not form["settings"][3]["is_required"]
    assert form["settings"][3]["slot_set"] == {"type": "slot", "value": "occupation"}


def test_edit_form_add_validations():
    name_validation = (
        "if (&& name.contains('i') && name.length() > 4 || "
        "!name.contains("
        ")) {return true;} else {return false;}"
    )
    num_people_validation = (
        "if (num_people > 1 && num_people < 10) {return true;} else {return false;}"
    )
    path = [
        {
            "ask_questions": ["please give us your name?"],
            "slot": "name",
            "slot_set": {"type": "custom", "value": "Mahesh"},
            "mapping": [
                {"type": "from_text", "value": "user", "entity": "name"},
                {"type": "from_entity", "entity": "name"},
            ],
            "validation_semantic": name_validation,
            "is_required": True,
        },
        {
            "ask_questions": ["seats required?"],
            "slot": "num_people",
            "mapping": [
                {
                    "type": "from_entity",
                    "intent": ["inform", "request_restaurant"],
                    "entity": "number",
                }
            ],
            "validation_semantic": num_people_validation,
            "is_required": False,
            "valid_response": "valid value",
            "invalid_response": "invalid value. please enter again",
        },
        {
            "ask_questions": ["type of cuisine?"],
            "slot": "cuisine",
            "slot_set": {"type": "custom", "value": "Indian Cuisine"},
            "mapping": [{"type": "from_entity", "entity": "cuisine"}],
        },
        {
            "ask_questions": ["outdoor seating required?"],
            "slot": "outdoor_seating",
            "mapping": [
                {"type": "from_entity", "entity": "seating"},
                {"type": "from_intent", "intent": ["affirm"], "value": True},
                {"type": "from_intent", "intent": ["deny"], "value": False},
            ],
        },
        {
            "ask_questions": ["any preferences?"],
            "slot": "preferences",
            "slot_set": {"type": "slot", "value": "preferences"},
            "mapping": [
                {"type": "from_text", "not_intent": ["affirm"]},
                {
                    "type": "from_intent",
                    "intent": ["affirm"],
                    "value": "no additional preferences",
                },
            ],
        },
        {
            "ask_questions": ["Please give your feedback on your experience so far"],
            "slot": "feedback",
            "slot_set": {"type": "custom", "value": "Very Nice!"},
            "mapping": [
                {"type": "from_text"},
                {"type": "from_entity", "entity": "feedback"},
            ],
        },
    ]
    request = {"name": "restaurant_form", "settings": path}
    response = client.put(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Form updated"


def test_edit_form_remove_validations():
    path = [
        {
            "ask_questions": ["what is your name?", "name?"],
            "slot": "name",
            "valid_response": "got it",
            "slot_set": {"type": "custom", "value": "Mahesh"},
            "invalid_response": "please rephrase",
        },
        {
            "ask_questions": ["what is your age?", "age?"],
            "slot": "age",
            "slot_set": {"type": "current", "value": 22},
            "valid_response": "valid entry",
            "invalid_response": "please enter again",
        },
        {
            "ask_questions": ["what is your location?", "location?"],
            "slot": "location",
            "slot_set": {"type": "custom", "value": "Bangalore"},
        },
        {
            "ask_questions": ["what is your occupation?", "occupation?"],
            "slot": "occupation",
            "slot_set": {"type": "slot", "value": "occupation"},
        },
    ]
    request = {"name": "know_user_form", "settings": path}
    response = client.put(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Form updated"


def test_list_form():
    response = client.get(
        f"/api/bot/{pytest.bot}/forms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"][0]["name"] == "restaurant_form"
    assert actual["data"][0]["required_slots"] == [
        "name",
        "num_people",
        "cuisine",
        "outdoor_seating",
        "preferences",
        "feedback",
    ]
    assert actual["data"][1]["name"] == "know_user_form"
    assert actual["data"][1]["required_slots"] == [
        "name",
        "age",
        "location",
        "occupation",
    ]


def test_get_form_after_edit():
    response = client.get(
        f"/api/bot/{pytest.bot}/forms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    form_1 = actual["data"][0]["_id"]

    response = client.get(
        f"/api/bot/{pytest.bot}/forms/{form_1}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    form = actual["data"]
    assert len(form["settings"]) == 6
    assert form["settings"][0]["slot"] == "name"
    assert form["settings"][1]["slot"] == "num_people"
    assert form["settings"][2]["slot"] == "cuisine"
    assert form["settings"][3]["slot"] == "outdoor_seating"
    assert form["settings"][4]["slot"] == "preferences"
    assert form["settings"][5]["slot"] == "feedback"
    assert form["settings"][0]["ask_questions"][0]["_id"]
    assert form["settings"][1]["ask_questions"][0]["_id"]
    assert form["settings"][2]["ask_questions"][0]["_id"]
    assert form["settings"][3]["ask_questions"][0]["_id"]
    assert form["settings"][4]["ask_questions"][0]["_id"]
    assert form["settings"][5]["ask_questions"][0]["_id"]
    assert (
            form["settings"][0]["ask_questions"][0]["value"]["text"]
            == "please give us your name?"
    )
    assert form["settings"][1]["ask_questions"][0]["value"]["text"] == "seats required?"
    assert (
            form["settings"][2]["ask_questions"][0]["value"]["text"] == "type of cuisine?"
    )
    assert (
            form["settings"][3]["ask_questions"][0]["value"]["text"]
            == "outdoor seating required?"
    )
    assert (
            form["settings"][4]["ask_questions"][0]["value"]["text"] == "any preferences?"
    )
    assert (
            form["settings"][5]["ask_questions"][0]["value"]["text"]
            == "Please give your feedback on your experience so far"
    )
    assert (
            form["settings"][0]["validation_semantic"]
            == "if (&& name.contains('i') && name.length() > 4 || "
               "!name.contains("
               ")) {return true;} else {return false;}"
    )
    assert form["settings"][0]["is_required"]
    assert form["settings"][0]["slot_set"] == {"type": "custom", "value": "Mahesh"}
    assert (
            form["settings"][1]["validation_semantic"]
            == "if (num_people > 1 && num_people < 10) {return true;} else {return false;}"
    )
    assert not form["settings"][1]["is_required"]
    assert form["settings"][1]["slot_set"] == {"type": "current", "value": None}
    assert not form["settings"][2]["validation_semantic"]
    assert form["settings"][2]["slot_set"] == {
        "type": "custom",
        "value": "Indian Cuisine",
    }
    assert not form["settings"][3]["validation_semantic"]
    assert form["settings"][3]["slot_set"] == {"type": "current", "value": None}
    assert not form["settings"][4]["validation_semantic"]
    assert form["settings"][4]["slot_set"] == {"type": "slot", "value": "preferences"}

    response = client.get(
        f"/api/bot/{pytest.bot}/response/all",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    saved_responses = {response["name"] for response in actual["data"]}
    assert (
            len(
                {
                    "utter_ask_restaurant_form_name",
                    "utter_ask_restaurant_form_num_people",
                    "utter_ask_restaurant_form_cuisine",
                    "utter_ask_restaurant_form_outdoor_seating",
                    "utter_ask_restaurant_form_preferences",
                    "utter_ask_restaurant_form_feedback",
                }.difference(saved_responses)
            )
            == 0
    )
    assert actual["success"]
    assert actual["error_code"] == 0


def test_edit_form():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "ac_required", "type": "text"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "ac_required",
            "mapping": {"type": "from_intent", "intent": ["affirm"], "value": True}
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "ac_required",
            "mapping":
                {"type": "from_intent", "intent": ["deny"], "value": False}
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    path = [
        {
            "ask_questions": ["which location would you prefer?"],
            "slot": "location",
            "slot_set": {"type": "custom", "value": "Bangalore"},
            "mapping": [
                {"type": "from_text", "value": "user", "entity": "location"},
                {"type": "from_entity", "entity": "location"},
            ],
        },
        {
            "ask_questions": ["seats required?"],
            "slot": "num_people",
            "slot_set": {"type": "current", "value": 10},
            "mapping": [
                {
                    "type": "from_entity",
                    "intent": ["inform", "request_restaurant"],
                    "entity": "number",
                }
            ],
        },
        {
            "ask_questions": ["type of cuisine?"],
            "slot": "cuisine",
            "slot_set": {"type": "custom", "value": "Indian Cuisine"},
            "mapping": [{"type": "from_entity", "entity": "cuisine"}],
        },
        {
            "ask_questions": ["outdoor seating required?"],
            "slot": "outdoor_seating",
            "slot_set": {"type": "custom", "value": True},
            "mapping": [
                {"type": "from_entity", "entity": "seating"},
                {"type": "from_intent", "intent": ["affirm"], "value": True},
                {"type": "from_intent", "intent": ["deny"], "value": False},
            ],
        },
        {
            "ask_questions": ["any preferences?"],
            "slot": "preferences",
            "slot_set": {"type": "slot", "value": "preferences"},
            "mapping": [
                {"type": "from_text", "not_intent": ["affirm"]},
                {
                    "type": "from_intent",
                    "intent": ["affirm"],
                    "value": "no additional preferences",
                },
            ],
        },
        {
            "ask_questions": ["do you want to go with an AC room?"],
            "slot": "ac_required",
            "slot_set": {"type": "current", "value": True},
        },
        {
            "ask_questions": ["Please give your feedback on your experience so far"],
            "slot": "feedback",
            "slot_set": {"type": "custom", "value": "Very Nice!"},
            "mapping": [
                {"type": "from_text"},
                {"type": "from_entity", "entity": "feedback"},
            ],
        },
    ]
    request = {"name": "restaurant_form", "settings": path}
    response = client.put(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Form updated"


def test_edit_form_with_any_slot():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "account_required", "type": "any"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "account_required",
            "mapping":
                {"type": "from_intent", "intent": ["affirm"], "value": True},
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "account_required",
            "mapping":
                {"type": "from_intent", "intent": ["deny"], "value": False},
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    path = [
        {
            "ask_questions": ["which location would you prefer?"],
            "slot": "location",
            "slot_set": {"type": "custom", "value": "Bangalore"},
            "mapping": [
                {"type": "from_text", "value": "user", "entity": "location"},
                {"type": "from_entity", "entity": "location"},
            ],
        },
        {
            "ask_questions": ["seats required?"],
            "slot": "num_people",
            "slot_set": {"type": "current", "value": 10},
            "mapping": [
                {
                    "type": "from_entity",
                    "intent": ["inform", "request_restaurant"],
                    "entity": "number",
                }
            ],
        },
        {
            "ask_questions": ["type of cuisine?"],
            "slot": "cuisine",
            "slot_set": {"type": "custom", "value": "Indian Cuisine"},
            "mapping": [{"type": "from_entity", "entity": "cuisine"}],
        },
        {
            "ask_questions": ["outdoor seating required?"],
            "slot": "outdoor_seating",
            "slot_set": {"type": "custom", "value": True},
            "mapping": [
                {"type": "from_entity", "entity": "seating"},
                {"type": "from_intent", "intent": ["affirm"], "value": True},
                {"type": "from_intent", "intent": ["deny"], "value": False},
            ],
        },
        {
            "ask_questions": ["any preferences?"],
            "slot": "preferences",
            "slot_set": {"type": "slot", "value": "preferences"},
            "mapping": [
                {"type": "from_text", "not_intent": ["affirm"]},
                {
                    "type": "from_intent",
                    "intent": ["affirm"],
                    "value": "no additional preferences",
                },
            ],
        },
        {
            "ask_questions": ["do you want to go with an AC room?"],
            "slot": "account_required",
            "slot_set": {"type": "current", "value": True},
        },
    ]
    request = {"name": "restaurant_form", "settings": path}
    response = client.put(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "form will not accept any type slots: {'account_required'}"


def test_edit_slot_mapping():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "cuisine",
            "mapping":
                {"type": "from_intent", "intent": ["order", "menu"], "value": "cuisine"}
            ,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]
    assert actual["error_code"] == 0
    mapping_id = actual["data"]["id"]
    response = client.put(
        f"/api/bot/{pytest.bot}/slots/mapping/{mapping_id}",
        json={
            "slot": "cuisine",
            "mapping":
                {"type": "from_intent", "intent": ["order", "menu"], "value": "cuisine"}
            ,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping updated"
    assert actual["success"]
    assert actual["error_code"] == 0


def test_get_slot_mapping():
    response = client.get(
        f"/api/bot/{pytest.bot}/slots/mapping",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    for obj in actual['data']:
        for m in obj['mapping']:
            m.pop('_id')

    assert not DeepDiff(
        actual["data"],
        [{'slot': 'ac_required',
          'mapping': [{'type': 'from_intent', 'value': True, 'intent': ['affirm']},
                      {'type': 'from_intent', 'value': False, 'intent': ['deny']}]},
         {'slot': 'account_required',
          'mapping': [{'type': 'from_intent', 'value': True, 'intent': ['affirm']},
                      {'type': 'from_intent', 'value': False, 'intent': ['deny']}]},
         {'slot': 'age', 'mapping': [
             {'type': 'from_intent', 'value': '18', 'intent': ['get_age'], }]},
         {'slot': 'cuisine',
          'mapping': [{'type': 'from_entity', 'entity': 'cuisine'},
                      {'type': 'from_intent', 'value': 'cuisine', 'intent': ['order', 'menu'],
                       }]},
         {'slot': 'feedback', 'mapping': [
             {'type': 'from_entity', 'entity': 'feedback'}]}, {'slot': 'location',
                                                               'mapping': [{
                                                                   'type': 'from_entity',
                                                                   'entity': 'location',
                                                               }]},
         {'slot': 'name', 'mapping': [{'type': 'from_text', 'value': 'user'}]},
         {'slot': 'num_people', 'mapping': [
             {'type': 'from_entity', 'entity': 'number', 'intent': ['inform', 'request_restaurant'],
              }]}, {'slot': 'occupation', 'mapping': [
            {'type': 'from_intent', 'value': 'business', 'intent': ['get_occupation'],
             },
            {'type': 'from_text', 'value': 'engineer'},
            {'type': 'from_entity', 'entity': 'occupation'},
            {'type': 'from_trigger_intent', 'value': 'tester', 'intent': ['get_business', 'is_engineer', 'is_tester'],
             'not_intent': ['get_age', 'get_name']}]},
         {'slot': 'outdoor_seating',
          'mapping': [
              {'type': 'from_text',
               'not_intent': [
                   'affirm'],
               'conditions': [{
                   'active_loop': 'booking',
                   'requested_slot': 'outdoor_seating'}],
               }]},
         {'slot': 'preferences', 'mapping': [{'type': 'from_text', 'not_intent': ['affirm'], 'conditions': [
             {'active_loop': 'booking', 'requested_slot': 'preferences'}]}]},
         {'slot': 'user_feedback', 'mapping': [{'type': 'from_text'},
                                               {'type': 'from_entity', 'entity': 'user_feedback',
                                                }]}]
        ,
        ignore_order=True,
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/slots/mapping?form=booking",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    for obj in actual['data']:
        for m in obj['mapping']:
            m.pop('_id')
    assert actual["success"]
    assert actual["data"] == [{'slot': 'outdoor_seating', 'mapping': [{'type': 'from_text', 'not_intent': ['affirm'],
                                                                       'conditions': [{'active_loop': 'booking',
                                                                                       'requested_slot': 'outdoor_seating'}]}]},
                              {'slot': 'preferences', 'mapping': [{'type': 'from_text', 'not_intent': ['affirm'],
                                                                   'conditions': [{'active_loop': 'booking',
                                                                                   'requested_slot': 'preferences'}]}]}]

    assert actual["error_code"] == 0


def test_delete_form():
    response = client.delete(
        f"/api/bot/{pytest.bot}/forms/restaurant_form",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Form deleted"


def test_delete_form_already_deleted():
    response = client.delete(
        f"/api/bot/{pytest.bot}/forms/restaurant_form",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Form "restaurant_form" does not exists'


def test_delete_form_not_exists():
    response = client.delete(
        f"/api/bot/{pytest.bot}/forms/form_not_exists",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Form "form_not_exists" does not exists'


def test_delete_slot_mapping():
    response = client.delete(
        f"/api/bot/{pytest.bot}/slots/mapping/ac_required",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Slot mapping deleted"


def test_delete_slot_mapping_non_existing():
    response = client.delete(
        f"/api/bot/{pytest.bot}/slots/mapping/ac_required",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "No slot mapping exists for slot: ac_required"


def test_add_slot_set_action():
    request = {
        "name": "action_set_name_slot",
        "set_slots": [
            {"name": "name", "type": "from_value", "value": 5},
            {"name": "age", "type": "reset_slot"},
        ],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/slotset",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"


def test_add_slot_set_action_slot_not_exists():
    request = {
        "name": "action_set_new_user_slot",
        "set_slots": [{"name": "new_user", "type": "from_value", "value": False}],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/slotset",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Slot with name "new_user" not found'


def test_list_slot_set_actions():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/slotset",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 1
    actual["data"][0].pop("_id")
    assert actual["data"][0] == {
        "name": "action_set_name_slot",
        "set_slots": [
            {"name": "name", "type": "from_value", "value": 5},
            {"name": "age", "type": "reset_slot"},
        ],
    }


def test_edit_slot_set_action():
    request = {
        "name": "action_set_name_slot",
        "set_slots": [{"name": "name", "type": "from_value", "value": "age"}],
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/slotset",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"


def test_edit_slot_set_action_slot_not_exists():
    request = {
        "name": "action_set_name_slot",
        "set_slots": [{"name": "non_existant", "type": "from_value", "value": "age"}],
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/slotset",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Slot with name "non_existant" not found'


def test_delete_slot_set_action_not_exists():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/non_existant",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Action with name "non_existant" not found'


def test_delete_slot_set_action():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/action_set_name_slot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action deleted"


def test_list_slot_set_action_none_present():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/slotset",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == []


def test_add_intent_case_insensitivity():
    response = client.post(
        f"/api/bot/{pytest.bot}/intents",
        json={"data": "CASE_INSENSITIVE_INTENT"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Intent added successfully!"

    response = client.get(
        f"/api/bot/{pytest.bot}/intents",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    intents_added = [i["name"] for i in actual["data"]]
    assert "CASE_INSENSITIVE_INTENT" not in intents_added
    assert "case_insensitive_intent" in intents_added
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.post(
        f"/api/bot/{pytest.bot}/training_examples/CASE_INSENSITIVE_INTENT",
        json={"data": ["IS THIS CASE_INSENSITIVE_INTENT?"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"][0]["message"] == "Training Example added"

    response = client.get(
        f"/api/bot/{pytest.bot}/training_examples/case_insensitive_intent",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    training_examples = [t["text"] for t in actual["data"]]
    assert "IS THIS CASE_INSENSITIVE_INTENT?" in training_examples
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_training_example_case_insensitivity():
    response = client.post(
        f"/api/bot/{pytest.bot}/training_examples/CASE_INSENSITIVE_TRAINING_EX_INTENT",
        json={"data": ["IS THIS CASE_INSENSITIVE_TRAINING_EX_INTENT?"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"][0]["message"] == "Training Example added"

    response = client.get(
        f"/api/bot/{pytest.bot}/training_examples/case_insensitive_training_ex_intent",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "IS THIS CASE_INSENSITIVE_TRAINING_EX_INTENT?" in [
        t["text"] for t in actual["data"]
    ]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_utterances_case_insensitivity():
    response = client.post(
        f"/api/bot/{pytest.bot}/utterance",
        json={"data": "utter_CASE_INSENSITIVE_UTTERANCE"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Utterance added!"

    response = client.get(
        f"/api/bot/{pytest.bot}/utterance",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    utterances_added = [u["name"] for u in actual["data"]["utterances"]]
    assert "utter_CASE_INSENSITIVE_UTTERANCE" not in utterances_added
    assert "utter_case_insensitive_utterance" in utterances_added


def test_add_responses_case_insensitivity():
    response = client.post(
        f"/api/bot/{pytest.bot}/response/utter_CASE_INSENSITIVE_RESPONSE",
        json={"data": "yes, this is utter_CASE_INSENSITIVE_RESPONSE"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Response added!"

    response = client.get(
        f"/api/bot/{pytest.bot}/response/utter_CASE_INSENSITIVE_RESPONSE",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"][0]["value"] == {
        "text": "yes, this is utter_CASE_INSENSITIVE_RESPONSE"
    }

    response = client.get(
        f"/api/bot/{pytest.bot}/response/utter_case_insensitive_response",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 1


def test_add_story_case_insensitivity():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "CASE_INSENSITIVE_STORY",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [
                {"name": "case_insensitive_training_ex_intent", "type": "INTENT"},
                {"name": "utter_case_insensitive_response", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    pytest.story_id = actual["data"]["_id"]

    response = client.get(
        f"/api/bot/{pytest.bot}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])
    stories_added = [s["name"] for s in actual["data"]]
    assert "CASE_INSENSITIVE_STORY" not in stories_added
    assert "case_insensitive_story" in stories_added

    response = client.delete(
        f"/api/bot/{pytest.bot}/stories/{pytest.story_id}/STORY",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow deleted successfully"


def test_add_rule_case_insensitivity():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "CASE_INSENSITIVE_RULE",
            "type": "RULE",
            "steps": [
                {"name": "case_insensitive_training_ex_intent", "type": "INTENT"},
                {"name": "utter_case_insensitive_response", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])
    stories_added = [s["name"] for s in actual["data"]]
    assert "CASE_INSENSITIVE_RULE" not in stories_added
    assert "case_insensitive_rule" in stories_added


def test_add_regex_case_insensitivity():
    response = client.post(
        f"/api/bot/{pytest.bot}/regex",
        json={"name": "CASE_INSENSITIVE_REGEX", "pattern": "b*b"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Regex pattern added successfully!"

    response = client.get(
        f"/api/bot/{pytest.bot}/regex",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])
    assert "CASE_INSENSITIVE_REGEX" != actual["data"][0]["name"]
    assert "case_insensitive_regex" == actual["data"][0]["name"]


def test_add_lookup_single_value():
    response = client.post(
        f"/api/bot/{pytest.bot}/lookup",
        json={"data": "single_value"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Lookup added!"

    response = client.post(
        f"/api/bot/{pytest.bot}/lookup/single_value/value",
        json={"data": "test"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Lookup value added!"

    response = client.get(
        f"/api/bot/{pytest.bot}/lookup/single_value/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert len(actual["data"]) == 1
    assert all(
        key in item.keys()
        for item in actual["data"]
        for key in ["_id", "value", "lookup"]
    )


def test_add_lookup_table_case_insensitivity():
    response = client.post(
        f"/api/bot/{pytest.bot}/lookup",
        json={"data": "CASE_INSENSITIVE_LOOKUP"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Lookup added!"

    response = client.post(
        f"/api/bot/{pytest.bot}/lookup/CASE_INSENSITIVE_LOOKUP/values",
        json={"value": ["test1", "test2"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Lookup values added!"

    response = client.get(
        f"/api/bot/{pytest.bot}/lookup/CASE_INSENSITIVE_LOOKUP/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert len(actual["data"]) == 2
    assert any("case_insensitive_lookup" == item["lookup"] for item in actual["data"])

    response = client.get(
        f"/api/bot/{pytest.bot}/lookups",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert any("case_insensitive_lookup" == item["lookup"] for item in actual["data"])


def test_add_entity_synonym_case_insensitivity():
    response = client.post(
        f"/api/bot/{pytest.bot}/entity/synonym",
        json={"data": "CASE_INSENSITIVE"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Synonym added!"

    response = client.post(
        f"/api/bot/{pytest.bot}/entity/synonym/CASE_INSENSITIVE/values",
        json={"value": ["CASE_INSENSITIVE_SYNONYM"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Synonym values added!"

    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonym/case_insensitive/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert any(
        item["value"] == "CASE_INSENSITIVE_SYNONYM"
        and item["synonym"] == "case_insensitive"
        for item in actual["data"]
    )


def test_add_slot_case_insensitivity():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={
            "name": "CASE_INSENSITIVE_SLOT",
            "type": "any",
            "initial_value": "bot",
            "influence_conversation": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert "data" in actual
    assert actual["message"] == "Slot added successfully!"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/slots",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"])
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_form_case_insensitivity():
    path = [
        {
            "ask_questions": ["please give us your name?"],
            "slot": "name",
            "slot_set": {"type": "custom", "value": "Mahesh"},
            "mapping": [
                {"type": "from_text", "value": "user", "entity": "name"},
                {"type": "from_entity", "entity": "name"},
            ],
        },
    ]
    request = {"name": "CASE_INSENSITIVE_FORM", "settings": path}
    response = client.post(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Form added"

    response = client.get(
        f"/api/bot/{pytest.bot}/forms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    form_1 = actual["data"][1]["_id"]

    response = client.get(
        f"/api/bot/{pytest.bot}/forms/{form_1}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["name"] == "case_insensitive_form"


def test_add_slot_set_action_case_insensitivity():
    request = {
        "name": "CASE_INSENSITIVE_SLOT_SET_ACTION",
        "set_slots": [{"name": "name", "type": "from_value", "value": 5}],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/slotset",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"

    response = client.get(
        f"/api/bot/{pytest.bot}/action/slotset",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 1
    actual["data"][0].pop("_id")
    assert actual["data"][0] == {
        "name": "case_insensitive_slot_set_action",
        "set_slots": [{"name": "name", "type": "from_value", "value": 5}],
    }


def test_add_http_action_case_insensitivity():
    request_body = {
        "action_name": "CASE_INSENSITIVE_HTTP_ACTION",
        "response": {"value": "string"},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "params_list": [
            {"key": "testParam1", "parameter_type": "value", "value": "testValue1"}
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/httpaction/CASE_INSENSITIVE_HTTP_ACTION",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["data"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/httpaction/case_insensitive_http_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]
    assert actual["success"]


def test_add_slot_mapping_1():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "name_slot", "type": "text"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]
    assert actual["error_code"] == 0
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "name_slot",
            "mapping": {"type": "from_text", "value": "user", "entity": "name_slot"},
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]
    assert actual["error_code"] == 0


def test_delete_slot_mapping_1():
    response = client.get(
        f"/api/bot/{pytest.bot}/slots/mapping",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    for slot_mapping in actual["data"]:
        if slot_mapping['slot'] == "name_slot":
            mapping_id = slot_mapping['mapping'][0]['_id']
            break
    assert len(actual["data"]) == 12

    response = client.delete(
        f"/api/bot/{pytest.bot}/slots/mapping_id/{mapping_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["message"] == "Slot mapping deleted"
    assert actual["error_code"] == 0
    assert not actual["data"]

    response = client.get(
        f"/api/bot/{pytest.bot}/slots/mapping",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 11


def test_delete_slot_mapping_does_not_exist():
    response = client.delete(
        f"/api/bot/{pytest.bot}/slots/mapping_id/{pytest.bot}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert not actual["data"]
    assert actual["message"] == 'No slot mapping exists'
    assert actual["error_code"] == 422

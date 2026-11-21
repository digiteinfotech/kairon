from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training



def test_get_slots():
    response = client.get(
        f"/api/bot/{pytest.bot}/slots",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 38
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])
    default_slots_count = sum(slot.get('is_default') for slot in actual["data"])
    assert default_slots_count == 31


def test_add_slots():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={
            "name": "bot_add",
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


def test_add_slots_duplicate():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={
            "name": "bot_add",
            "type": "any",
            "initial_value": "bot",
            "influence_conversation": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["message"] == "Slot already exists!"
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_empty_slots():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={
            "name": "",
            "type": "any",
            "initial_value": "bot",
            "influence_conversation": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Slot Name cannot be empty or blank spaces"


def test_add_invalid_slots_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={
            "name": "bot_invalid",
            "type": "invalid",
            "initial_value": "bot",
            "influence_conversation": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert (
            actual["message"][0]["msg"]
            == "value is not a valid enumeration member; permitted: 'float', 'categorical', 'list', 'text', 'bool', 'any'"
    )
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_edit_slots():
    response = client.put(
        f"/api/bot/{pytest.bot}/slots",
        json={
            "name": "bot",
            "type": "text",
            "initial_value": "bot",
            "influence_conversation": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Slot updated!"


def test_edit_empty_slots():
    response = client.put(
        f"/api/bot/{pytest.bot}/slots",
        json={
            "name": "",
            "type": "any",
            "initial_value": "bot",
            "influence_conversation": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Slot Name cannot be empty or blank spaces"


def test_delete_slots():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={
            "name": "color",
            "type": "any",
            "initial_value": "bot",
            "influence_conversation": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = client.delete(
        f"/api/bot/{pytest.bot}/slots/color",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["message"] == "Slot deleted!"
    assert actual["success"]
    assert actual["error_code"] == 0


def test_edit_invalid_slots_type():
    response = client.put(
        f"/api/bot/{pytest.bot}/slots",
        json={
            "name": "bot",
            "type": "invalid",
            "initial_value": "bot",
            "influence_conversation": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"][0]["msg"]
            == "value is not a valid enumeration member; permitted: 'float', 'categorical', 'list', 'text', 'bool', 'any'"
    )


def test_get_intents():
    response = client.get(
        f"/api/bot/{pytest.bot}/intents",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 15
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_get_all_intents():
    response = client.get(
        f"/api/bot/{pytest.bot}/intents/all",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 15
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_add_intents():
    response = client.post(
        f"/api/bot/{pytest.bot}/intents",
        json={"data": "happier"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Intent added successfully!"


def test_add_intents_duplicate():
    response = client.post(
        f"/api/bot/{pytest.bot}/intents",
        json={"data": "happier"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Intent already exists!"


def test_add_empty_intents():
    response = client.post(
        f"/api/bot/{pytest.bot}/intents",
        json={"data": ""},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Intent Name cannot be empty or blank spaces"


def test_get_training_examples():
    response = client.get(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 8
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_training_example_exists():
    response = client.get(
        f"/api/bot/{pytest.bot}/training_examples/exists/hey",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"] == {"is_exists": True, "intent": "greet"}
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_training_example_does_not_exist():
    response = client.get(
        f"/api/bot/{pytest.bot}/training_examples/exists/xyz",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"] == {"is_exists": False, "intent": None}
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_get_training_examples_empty_intent():
    response = client.get(
        f"/api/bot/{pytest.bot}/training_examples/ ",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 0
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_get_training_examples_as_dict(monkeypatch):
    training_examples = {"hi": "greet", "hello": "greet", "ok": "affirm", "no": "deny"}

    def _mongo_aggregation(*args, **kwargs):
        return [{"training_examples": training_examples}]

    monkeypatch.setattr(BaseQuerySet, "aggregate", _mongo_aggregation)

    response = client.get(
        f"/api/bot/{pytest.bot}/training_examples",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"] == training_examples
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_training_examples():
    response = client.post(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        json={"data": ["How do you do?"]},
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
    assert len(actual["data"]) == 9


def test_add_training_examples_duplicate():
    response = client.post(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        json={"data": ["How do you do?"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert (
            actual["data"][0]["message"] == "Training Example exists in intent: ['greet']"
    )
    assert actual["data"][0]["_id"] is None


def test_add_empty_training_examples():
    response = client.post(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        json={"data": [""]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert (
            actual["data"][0]["message"]
            == "Training Example cannot be empty or blank spaces"
    )
    assert actual["data"][0]["_id"] is None


def test_remove_training_examples():
    training_examples = client.get(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    assert len(training_examples["data"]) == 9
    id = training_examples["data"][0]["_id"]
    response = client.delete(
        f"/api/bot/{pytest.bot}/training_examples/{id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Training Example removed!"
    training_examples = client.get(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    assert len(training_examples["data"]) == 8


def test_remove_training_examples_empty_id():
    response = client.delete(
        f"/api/bot/{pytest.bot}/training_examples/ ",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Unable to remove document"


def test_edit_training_examples():
    training_examples = client.get(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    response = client.put(
        f"/api/bot/{pytest.bot}/training_examples/greet/"
        + training_examples["data"][0]["_id"],
        json={"data": "hey, there"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Training Example updated!"


def test_get_responses():
    response = client.get(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 1
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_get_all_responses():
    response = client.get(
        f"/api/bot/{pytest.bot}/response/all",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 14
    assert actual["data"][0]["name"]
    assert actual["data"][0]["texts"][0]["text"]
    assert not actual["data"][0]["customs"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_add_response_already_exists():
    response = client.post(
        f"/api/bot/{pytest.bot}/utterance",
        json={"data": "utter_greet"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Utterance exists"


def test_add_utterance_name():
    response = client.post(
        f"/api/bot/{pytest.bot}/utterance",
        json={"data": "utter_test_add_name"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Utterance added!"


def test_add_utterance_name_empty():
    response = client.post(
        f"/api/bot/{pytest.bot}/utterance",
        json={"data": " "},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_get_utterances():
    response = client.get(
        f"/api/bot/{pytest.bot}/utterance",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["utterances"]) == 15
    assert type(actual["data"]["utterances"]) == list


def test_add_response():
    response = client.post(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        json={"data": "Wow! How are you?"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Response added!"
    response = client.get(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 2


def test_add_custom_response():
    response = client.post(
        f"/api/bot/{pytest.bot}/response/json/utter_custom",
        json={"data": {"question": "Wow! How are you?"}},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Response added!"
    response = client.get(
        f"/api/bot/{pytest.bot}/utterance",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 1


def test_get_custom_responses():
    response = client.get(
        f"/api/bot/{pytest.bot}/response/utter_custom",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 1
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_add_response_upper_case():
    response = client.post(
        f"/api/bot/{pytest.bot}/response/Utter_Greet",
        json={"data": "Upper Greet Response"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Response added!"


def test_get_response_upper_case():
    response = client.get(
        f"/api/bot/{pytest.bot}/response/Utter_Greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 3

    response_lower = client.get(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual_lower = response_lower.json()
    assert len(actual_lower["data"]) == 3
    assert actual_lower["data"] == actual["data"]


def test_add_response_duplicate():
    response = client.post(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        json={"data": "Wow! How are you?"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Utterance already exists!"


def test_add_custom_response_duplicate():
    response = client.post(
        f"/api/bot/{pytest.bot}/response/json/utter_custom",
        json={"data": {"question": "Wow! How are you?"}},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Utterance already exists!"


def test_add_empty_response():
    response = client.post(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        json={"data": ""},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Utterance text cannot be empty or blank spaces"


def test_add_custom_empty_response():
    response = client.post(
        f"/api/bot/{pytest.bot}/response/json/utter_custom",
        json={"data": ""},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Utterance must be dict type and must not be empty"


def test_remove_response():
    response = client.get(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    utterances = response.json()
    assert len(utterances["data"]) == 3
    id = utterances["data"][0]["_id"]
    response = client.delete(
        f"/api/bot/{pytest.bot}/response/{id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Response removed!"
    training_examples = client.get(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    assert len(training_examples["data"]) == 2


def test_remove_utterance_attached_to_story():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_remove_utterance_attached_to_story",
            "type": "STORY",
            "template_type": "Q&A",
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
    response = client.delete(
        f"/api/bot/{pytest.bot}/responses/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"]
            == 'Cannot remove action "utter_greet" linked to flow "greet again"'
    )


def test_remove_utterance():
    client.post(
        f"/api/bot/{pytest.bot}/response/utter_remove_utterance",
        json={"data": "this will be removed"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = client.delete(
        f"/api/bot/{pytest.bot}/responses/utter_remove_utterance",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Utterance removed!"


def test_remove_utterance_non_existing():
    response = client.delete(
        f"/api/bot/{pytest.bot}/responses/utter_delete_non_existing",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Utterance does not exists"


def test_remove_utterance_empty():
    response = client.delete(
        f"/api/bot/{pytest.bot}/responses/ ",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Utterance cannot be empty or spaces"


def test_remove_response_empty_id():
    response = client.delete(
        f"/api/bot/{pytest.bot}/response/ ",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Response Id cannot be empty or spaces"


def test_edit_response():
    training_examples = client.get(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    response = client.put(
        f"/api/bot/{pytest.bot}/response/utter_greet/"
        + training_examples["data"][0]["_id"],
        json={"data": "Hello, How are you!"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Utterance updated!"


def test_edit_custom_response():
    training_examples = client.get(
        f"/api/bot/{pytest.bot}/response/utter_custom",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    response = client.put(
        f"/api/bot/{pytest.bot}/response/json/utter_custom/"
        + training_examples["data"][0]["_id"],
        json={"data": {"question": "How are you?"}},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Utterance updated!"

    training_examples = client.get(
        f"/api/bot/{pytest.bot}/response/utter_custom",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    assert training_examples["data"][0]["_id"]
    assert training_examples["data"][0]["value"] == {
        "custom": {"question": "How are you?"}
    }
    assert training_examples["data"][0]["type"] == "json"


def test_remove_custom_utterance():
    response = client.post(
        f"/api/bot/{pytest.bot}/response/json/utter_custom",
        json={"data": {"question": "are you ok?"}},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    id = actual["data"]["_id"]
    response = client.delete(
        f"/api/bot/{pytest.bot}/response/{id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Response removed!"

    response = client.delete(
        f"/api/bot/{pytest.bot}/responses/utter_custom",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Utterance removed!"

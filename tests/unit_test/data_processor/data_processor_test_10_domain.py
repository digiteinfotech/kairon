from tests.unit_test.data_processor.data_processor_support import *  # noqa: F403
from tests.unit_test.data_processor.data_processor_support import (
    MongoProcessorTestBase,
    fast_rasa_training,
)

class TestMongoProcessor(MongoProcessorTestBase):
    def test_add_training_data(self):
        training_data = [
            models.TrainingData(intent="intent1",
                                training_examples=["example1", "example2"],
                                response="response1"),
            models.TrainingData(intent="intent2",
                                training_examples=["example3", "example4"],
                                response="response2")
        ]
        processor = MongoProcessor()
        processor.add_training_data(training_data, "training_bot", "training_user", False)
        assert Intents.objects(name="intent1").get() is not None
        assert Intents.objects(name="intent2").get() is not None
        training_examples = list(TrainingExamples.objects(intent="intent1"))
        assert training_examples is not None
        assert len(training_examples) == 2
        training_examples = list(TrainingExamples.objects(intent="intent2"))
        assert len(training_examples) == 2
        assert Responses.objects(name="utter_intent1") is not None
        assert Responses.objects(name="utter_intent2") is not None
        story = Stories.objects(block_name="path_intent1").get()
        assert story is not None
        assert story['events'][0]['name'] == 'intent1'
        assert story['events'][0]['type'] == StoryEventType.user
        assert story['events'][1]['name'] == "utter_intent1"
        assert story['events'][1]['type'] == StoryEventType.action
        story = Stories.objects(block_name="path_intent2").get()
        assert story is not None

    def test_add_training_data_with_invalid_training_example(self):
        training_data = [
            models.TrainingData(intent="intent3",
                                training_examples=[" ", "example"],
                                response="response3")]
        processor = MongoProcessor()
        processor.add_training_data(training_data, "training_bot", "training_user", False)
        assert Intents.objects(name="intent3").get() is not None
        training_examples = list(TrainingExamples.objects(intent="intent3"))
        assert training_examples is not None
        assert len(training_examples) == 1
        assert Responses.objects(name="utter_intent3") is not None
        story = Stories.objects(block_name="path_intent3").get()
        assert story is not None
        assert story['events'][0]['name'] == 'intent3'
        assert story['events'][0]['type'] == StoryEventType.user
        assert story['events'][1]['name'] == "utter_intent3"
        assert story['events'][1]['type'] == StoryEventType.action
        story = Stories.objects(block_name="path_intent3").get()
        assert story is not None

    def test_add_training_data_with_intent_exists(self):
        training_data = [
            models.TrainingData(intent="intent3",
                                training_examples=["example for intent3"],
                                response="response3")]
        processor = MongoProcessor()
        processor.add_training_data(training_data, "training_bot", "training_user", False)
        assert Intents.objects(name="intent3").get() is not None
        training_examples = list(TrainingExamples.objects(intent="intent3"))
        assert training_examples is not None
        assert len(training_examples) == 2
        assert Responses.objects(name="utter_intent3") is not None
        story = Stories.objects(block_name="path_intent3").get()
        assert story is not None
        assert story['events'][0]['name'] == 'intent3'
        assert story['events'][0]['type'] == StoryEventType.user
        assert story['events'][1]['name'] == "utter_intent3"
        assert story['events'][1]['type'] == StoryEventType.action
        story = Stories.objects(block_name="path_intent3").get()
        assert story is not None

    def test_delete_response(self):
        processor = MongoProcessor()
        intent = "test_delete_response_with_story"
        utterance = "utter_" + intent
        story = "path_" + intent
        bot = "testBot"
        user = "testUser"
        utter_intentA_1_id = processor.add_response({"text": "demo_response"}, utterance, bot, user)
        utter_intentA_2_id = processor.add_response({"text": "demo_response2"}, utterance, bot, user)
        resp = processor.get_response(utterance, bot)
        assert len(list(resp)) == 2
        processor.delete_response(utter_intentA_1_id, bot, user=user)
        resp = processor.get_response(utterance, bot)
        assert len(list(resp)) == 1
        assert Utterances.objects(name=utterance, bot=bot, status=True).get()
        processor.delete_response(utter_intentA_2_id, bot, user=user)
        resp = processor.get_response(utterance, bot)
        assert len(list(resp)) == 0
        with pytest.raises(DoesNotExist):
            Utterances.objects(name=utterance, bot=bot, status=True).get()

    def test_delete_response_non_existing(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_response("0123456789ab0123456789ab", "testBot")

    def test_delete_response_empty(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_response(" ", "testBot")

    def test_delete_utterance(self):
        processor = MongoProcessor()
        utterance = "test_delete_utterance"
        bot = "testBot"
        user = "testUser"
        processor.add_response({"text": "demo_response1"}, utterance, bot, user)
        Utterances.objects(name=utterance, bot=bot, status=True).get()
        processor.delete_utterance(utterance, bot, user=user)
        with pytest.raises(DoesNotExist):
            Utterances.objects(name=utterance, bot=bot, status=True).get()

    def test_delete_utterance_non_existing(self):
        processor = MongoProcessor()
        utterance = "test_delete_utterance_non_existing"
        bot = "testBot"
        user = "testUser"
        with pytest.raises(AppException):
            processor.delete_utterance(utterance, bot, user=user)

    def test_delete_utterance_empty(self):
        processor = MongoProcessor()
        utterance = " "
        bot = "testBot"
        user = "testUser"
        with pytest.raises(AppException):
            processor.delete_utterance(utterance, bot, user=user)

    def test_delete_utterance_name_having_no_responses(self):
        processor = MongoProcessor()
        utterance = "test_delete_utterance_name_having_no_responses"
        bot = "testBot"
        user = "testUser"
        processor.add_utterance_name(utterance, bot, user)
        processor.delete_utterance(utterance, bot, user=user)
        with pytest.raises(DoesNotExist):
            Utterances.objects(name__iexact=utterance, bot=bot, status=True).get()

    def test_add_slot_invalid_values(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'
        with pytest.raises(AppException, match='initial value must not be an empty string'):
            processor.add_slot(
                {"name": "bot", "type": "any", "initial_value": "", "influence_conversation": True},
                bot, user, raise_exception_if_exists=True
            )

        with pytest.raises(AppException, match='initial value must not be an empty string'):
            processor.add_slot(
                {"name": "bot", "type": "text", "initial_value": " ", "influence_conversation": False},
                bot, user, raise_exception_if_exists=True
            )

        with pytest.raises(AppException, match='initial value for type Text must be a string'):
            processor.add_slot(
                {"name": "bot", "type": "text", "initial_value": 123, "influence_conversation": True},
                bot, user, raise_exception_if_exists=False)

        with pytest.raises(AppException, match='initial value for type Boolean must be a true or false'):
            processor.add_slot(
                {"name": "bot", "type": "bool", "initial_value": "true", "influence_conversation": True},
                bot, user, raise_exception_if_exists=False)

        with pytest.raises(AppException, match='initial value for type List must be a list of elements'):
            processor.add_slot(
                {"name": "bot", "type": "list", "initial_value": "sample value", "influence_conversation": True},
                bot, user, raise_exception_if_exists=False)

        with pytest.raises(AppException, match='initial value for type Float must be a numeric value'):
            processor.add_slot(
                {"name": "bot", "type": "float", "initial_value": "invalid value", "min_value": 1, "max_value": 3,
                 "influence_conversation": True}, bot, user, raise_exception_if_exists=False)

        with pytest.raises(AppException, match='initial value for type Float must be a numeric value'):
            processor.add_slot(
                {"name": "bot", "type": "float", "initial_value": '0.7', "min_value": 0.5, "max_value": 1.0,
                 "influence_conversation": True}, bot, user, raise_exception_if_exists=False)

        with pytest.raises(AppException, match='min_value must be a numeric value'):
            processor.add_slot(
                {"name": "bot", "type": "float", "initial_value": 0.7, "min_value": '0.5', "max_value": 1.0,
                 "influence_conversation": True}, bot, user, raise_exception_if_exists=False)

        with pytest.raises(AppException, match='min_value must be less than max_value'):
            processor.add_slot(
                {"name": "bot", "type": "float", "initial_value": 0.7, "min_value": 1.0, "max_value": 0.5,
                 "influence_conversation": True}, bot, user, raise_exception_if_exists=False)

        with pytest.raises(AppException, match='only None is not valid values for Categorical type'):
            processor.add_slot(
                {"name": "bot", "type": "categorical", "values": [None], "influence_conversation": True},
                bot, user, raise_exception_if_exists=False)

    def test_add_slot_with_none(self):
        processor = MongoProcessor()
        bot = 'test_add_slot_with_none'
        user = 'test_user'
        processor.add_slot(
            {"name": "bot", "type": "text", "initial_value": None, "influence_conversation": True},
            bot, user, raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='bot', bot=bot, user=user).get()
        assert slot['name'] == 'bot'
        assert slot['type'] == 'text'
        assert slot['initial_value'] is None
        assert slot['influence_conversation']

        processor.add_slot(
            {"name": "is_authenticated", "type": "bool", "initial_value": None, "influence_conversation": True},
            bot, user, raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='is_authenticated', bot=bot, user=user).get()
        assert slot['name'] == 'is_authenticated'
        assert slot['type'] == 'bool'
        assert slot['initial_value'] is None
        assert slot['influence_conversation']

        processor.add_slot({"name": "color", "type": "categorical", "values": ["red", None, "blue"],
                            "initial_value": None, "influence_conversation": True},
                           bot, user, raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='color', bot=bot, user=user).get()
        assert slot['name'] == 'color'
        assert slot['type'] == 'categorical'
        assert slot['values'] == ["red", None, "blue"]
        assert slot['initial_value'] is None
        assert slot['influence_conversation']

        processor.add_slot(
            {"name": "range", "type": "float", "initial_value": None, "min_value": 0.1, "max_value": 0.3,
             "influence_conversation": True}, bot, user, raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='range', bot=bot, user=user).get()
        assert slot['name'] == 'range'
        assert slot['type'] == 'float'
        assert slot['min_value'] == 0.1
        assert slot['max_value'] == 0.3
        assert slot['initial_value'] is None
        assert slot['influence_conversation']

        processor.add_slot(
            {"name": "colors", "type": "list", "initial_value": None, "influence_conversation": True},
            bot, user, raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='colors', bot=bot, user=user).get()
        assert slot['name'] == 'colors'
        assert slot['type'] == 'list'
        assert slot['initial_value'] is None
        assert slot['influence_conversation']

    def test_add_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'
        processor.add_slot({"name": "bot", "type": "text", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='bot', bot=bot, user=user).get()
        assert slot['name'] == 'bot'
        assert slot['type'] == 'text'
        assert slot['initial_value'] is None
        assert slot['influence_conversation']
        assert Entities.objects(name='bot', bot=bot, user=user, status=True).get()

        processor.add_slot({"name": "bot", "type": "any", "initial_value": bot, "influence_conversation": False}, bot,
                           user, raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='bot', bot=bot, user=user).get()
        assert slot['name'] == 'bot'
        assert slot['type'] == 'any'
        assert slot['initial_value'] == bot
        assert not slot['influence_conversation']
        assert Entities.objects(name='bot', bot=bot, user=user, status=True).get()

    def test_add_duplicate_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        with pytest.raises(AppException):
            msg = processor.add_slot(
                {"name": "bot", "type": "any", "initial_value": bot, "influence_conversation": False}, bot, user,
                raise_exception_if_exists=True)
            assert msg == 'Slot already exists!'
            assert Entities.objects(name='bot', bot=bot, user=user, status=True).get()

    def test_add_empty_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        with pytest.raises(AppException):
            msg = processor.add_slot(
                {"name": "", "type": "invalid", "initial_value": bot, "influence_conversation": False}, bot, user,
                raise_exception_if_exists=False)
            assert msg == 'Slot Name cannot be empty or blank spaces'

    def test_add_invalid_slot_type(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        with pytest.raises(AppException):
            msg = processor.add_slot(
                {"name": "bot", "type": "invalid", "initial_value": bot, "influence_conversation": False}, bot, user,
                raise_exception_if_exists=False)
            assert msg == 'Invalid slot type.'

    def test_min_max_for_other_slot_types(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        for slot_type in SLOT_TYPE:
            if slot_type == SLOT_TYPE.FLOAT or slot_type == SLOT_TYPE.CATEGORICAL:
                continue
            else:
                processor.add_slot({"name": "bot", "type": slot_type, "max_value": 0.5, "min_value": 0.1,
                                    "influence_conversation": True}, bot, user, raise_exception_if_exists=False)
                slot = Slots.objects(name__iexact='bot', bot=bot, user=user).get()
                assert slot['name'] == 'bot'
                assert slot['type'] == slot_type
                assert slot['max_value'] is None
                assert slot['min_value'] is None

    def test_add_float_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'
        processor.add_slot({"name": "bot", "type": "float", "initial_value": 0.2, "max_value": 0.5, "min_value": 0.1,
                            "influence_conversation": True}, bot, user, raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='bot', bot=bot, user=user).get()
        assert slot['name'] == 'bot'
        assert slot['type'] == 'float'
        assert slot['initial_value'] == 0.2
        assert slot['influence_conversation']
        assert slot['max_value'] == 0.5
        assert slot['min_value'] == 0.1

    def test_values_for_other_slot_types(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        for slot_type in SLOT_TYPE:

            if slot_type == SLOT_TYPE.CATEGORICAL:
                continue
            else:
                processor.add_slot(
                    {"name": "bot", "type": slot_type, "values": ["red", "blue"],
                     "influence_conversation": True}, bot, user, raise_exception_if_exists=False)
                slot = Slots.objects(name__iexact='bot', bot=bot, user=user).get()
                assert slot['name'] == 'bot'
                assert slot['type'] == slot_type
                assert slot['values'] is None
                assert slot['influence_conversation']

    def test_add_categorical_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'
        processor.add_slot({"name": "color", "type": "categorical", "values": ["red", "blue"],
                            "influence_conversation": True}, bot, user, raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='color', bot=bot, user=user).get()
        assert slot['name'] == 'color'
        assert slot['type'] == 'categorical'
        assert slot['values'] == ["red", "blue"]
        assert slot['influence_conversation']

    def test_add_categorical_slot_without_values(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'
        with pytest.raises(ValidationError):
            msg = processor.add_slot({"name": "bot", "type": "categorical",
                                      "influence_conversation": True}, bot, user, raise_exception_if_exists=False)
            assert msg == "CategoricalSlot must have list of categories in values field"

    def test_delete_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        processor.delete_slot(slot_name='color', bot=bot, user=user)

        with pytest.raises(DoesNotExist):
            Slots.objects(name__iexact='color', bot=bot).get()
        assert not Entities.objects(name='color', bot=bot, status=True)

    def test_delete_slot_default_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        with pytest.raises(AppException, match='Default kAIron slot deletion not allowed'):
            processor.delete_slot(slot_name='bot', bot=bot, user=user)

        with pytest.raises(AppException, match='Default kAIron slot deletion not allowed'):
            processor.delete_slot(slot_name='kairon_action_response', bot=bot, user=user)

        with pytest.raises(AppException, match='Default kAIron slot deletion not allowed'):
            processor.delete_slot(slot_name='image', bot=bot, user=user)

        with pytest.raises(AppException, match='Default kAIron slot deletion not allowed'):
            processor.delete_slot(slot_name='video', bot=bot, user=user)

        with pytest.raises(AppException, match='Default kAIron slot deletion not allowed'):
            processor.delete_slot(slot_name='audio', bot=bot, user=user)

        with pytest.raises(AppException, match='Default kAIron slot deletion not allowed'):
            processor.delete_slot(slot_name='document', bot=bot, user=user)

        with pytest.raises(AppException, match='Default kAIron slot deletion not allowed'):
            processor.delete_slot(slot_name='doc_url', bot=bot, user=user)

        with pytest.raises(AppException, match='Default kAIron slot deletion not allowed'):
            processor.delete_slot(slot_name='order', bot=bot, user=user)

    def test_delete_slot_having_story_attached(self):
        processor = MongoProcessor()
        story_name = "delete story with slot"
        bot = "test_slot_delete"
        user = "test_user"
        slot_name = "is_new_user"
        slot = {"name": slot_name, "type": "any", "initial_value": None, "influence_conversation": False}
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": slot_name, "type": "SLOT", "value": None},
            {"name": "utter_welcome_user", "type": "BOT"},
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.add_slot(slot_value=slot, bot=bot, user=user)
        pytest.story_id = processor.add_complex_story(story_dict, bot, user)

        with pytest.raises(AppException) as e:
            processor.delete_slot(slot_name=slot_name, bot=bot, user=user)
            assert str(e) == "Slot is attached to story: ['delete story with slot']"

    def test_delete_slot_having_training_attached(self):
        processor = MongoProcessor()
        bot = "test_slot_delete_training"
        user = "test_user"
        slot_name = "time"
        intent = "greet"
        slot = {"name": slot_name, "type": "any", "initial_value": None, "influence_conversation": True}
        processor.add_slot(slot_value=slot, bot=bot, user=user)
        processor.add_intent(intent, bot=bot, user=user, is_integration=False)
        response = list(processor.add_training_example(["hi [Good Morning](time)"], intent, bot=bot, user=user,
                                                       is_integration=False))
        assert len(response) == 1
        with pytest.raises(AppException) as e:
            processor.delete_slot(slot_name=slot_name, bot=bot, user=user)
            assert str(e) == f"Slot is attached to training example: ['{intent}']"

    def test_delete_slot_having_multi_story_attached(self):
        processor = MongoProcessor()
        bot = "test_slot_delete_multi_story"
        user = "test_user"
        slot_name = "mood"
        story_name = "mood multi flow"
        slot = {"name": slot_name, "type": "any", "initial_value": None, "influence_conversation": True}
        processor.add_slot(slot_value=slot, bot=bot, user=user)
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "mood", "type": "SLOT", "value": "Happy", "node_id": "3",
                  "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "food", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "food", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
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
            {"step": {"name": "mood", "type": "SLOT", "value": "Happy", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        pytest.story_id = processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = MultiflowStories.objects(block_name=story_name, bot=bot).get()
        assert len(multiflow_story.events) == 6

        with pytest.raises(AppException) as e:
            processor.delete_slot(slot_name=slot_name, bot=bot, user=user)
            assert str(e) == f"Slot is attached to multiflow story: : ['{story_name}']"

    def test_delete_slot_having_slot_mapping_attached(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'
        slot_name = 'is_new_user'
        slot = {"name": slot_name, "type": "any", "initial_value": None, "influence_conversation": False}
        mapping = {"slot": slot_name, 'mapping': {'type': 'from_entity', 'entity': 'name'}}
        processor.add_slot(slot_value=slot, bot=bot, user=user)
        processor.add_slot_mapping(mapping, bot, user)

        with pytest.raises(AppException, match="Cannot delete slot without removing its mappings!"):
            processor.delete_slot(slot_name=slot_name, bot=bot, user=user)

        processor.delete_slot_mapping(slot_name, bot, user)
        processor.delete_slot(slot_name=slot_name, bot=bot, user=user)

    def test_delete_inexistent_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        with pytest.raises(AppException) as e:
            processor.delete_slot(slot_name='bot_doesnt_exist', bot=bot, user=user)
        assert str(e).__contains__('Slot does not exist.')

    def test_delete_empty_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        with pytest.raises(AppException) as e:
            processor.delete_slot(slot_name='', bot=bot, user=user)
        assert str(e).__contains__('Slot does not exist.')

    def test_delete_entity_not_exists(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Entity not found'):
            processor.delete_entity('entity_not_exists', 'test_bot', 'test_user')

    def test_fetch_rule_block_names(self):
        processor = MongoProcessor()
        Rules(
            block_name="rule1",
            condition_events_indices=[],
            start_checkpoints=["START"],
            end_checkpoints=["END"],
            events=[StoryEvents(name="greet", type="user"), StoryEvents(name="utter_greet", type="action")],
            bot="test_bot",
            user="rule_creator",
        ).save()
        Rules(
            block_name="rule2",
            condition_events_indices=[],
            start_checkpoints=["START"],
            end_checkpoints=["END"],
            events=[StoryEvents(name="greet", type="user"), StoryEvents(name="utter_greet", type="action")],
            bot="test_bot",
            user="rule_creator",
        ).save()
        block_names = processor.fetch_rule_block_names("test_bot")
        assert block_names[0] == "rule1"
        assert block_names[1] == "rule2"

    def test_fetch_rule_block_names_no_rules_present(self):
        processor = MongoProcessor()
        block_names = processor.fetch_rule_block_names("rule_creator")
        assert not block_names

    def test_save_rules(self):
        processor = MongoProcessor()
        intent = {
            STORY_EVENT.NAME.value: "greet",
            STORY_EVENT.CONFIDENCE.value: 1.0,
        }
        events = [UserUttered(text="greet", intent=intent),
                  ActionExecuted(action_name="utter_greet")]
        story_steps = [RuleStep(block_name="rule1",
                                start_checkpoints=[Checkpoint("START")],
                                end_checkpoints=[Checkpoint("END")],
                                events=events,
                                condition_events_indices={0}),
                       RuleStep(block_name="rule2",
                                start_checkpoints=[Checkpoint("START")],
                                end_checkpoints=[Checkpoint("END")],
                                events=events,
                                condition_events_indices={0})
                       ]
        processor.save_rules(story_steps, "test_save_rules", "rules_creator")
        rules = list(Rules.objects(bot="test_save_rules", user="rules_creator", status=True))
        assert rules[0]['block_name'] == "rule1"
        assert rules[0]['condition_events_indices'] == [0]
        assert rules[0]['start_checkpoints'] == ["START"]
        assert rules[0]['end_checkpoints'] == ["END"]
        assert rules[0]['events'][0]['name'] == "greet"
        assert rules[0]['events'][0]['type'] == "user"
        assert not rules[0]['events'][0]['value']
        assert rules[0]['events'][1]['name'] == "utter_greet"
        assert rules[0]['events'][1]['type'] == "action"
        assert not rules[0]['events'][1]['value']
        assert rules[1]['block_name'] == "rule2"

    def test_save_rules_already_present(self):
        processor = MongoProcessor()
        events = [UserUttered(text="greet"),
                  ActionExecuted(action_name="utter_greet")]
        Rules(block_name="rule2",
              start_checkpoints=["START"],
              end_checkpoints=["END"],
              events=[StoryEvents(name="greet", type="user"),
                      StoryEvents(name="utter_greet", type="action")],
              condition_events_indices={0}, bot="test_save_rules_already_present", user="rules_creator").save()
        story_steps = [RuleStep(block_name="rule1",
                                start_checkpoints=[Checkpoint("START")],
                                end_checkpoints=[Checkpoint("END")],
                                events=events,
                                condition_events_indices={0}),
                       RuleStep(block_name="rule2",
                                start_checkpoints=[Checkpoint("START")],
                                end_checkpoints=[Checkpoint("END")],
                                events=events,
                                condition_events_indices={0})
                       ]
        processor.save_rules(story_steps, "test_save_rules_already_present", "rules_creator")
        rules = list(Rules.objects(bot="test_save_rules_already_present", user="rules_creator", status=True))
        assert len(rules) == 2
        assert rules[0]['block_name'] == "rule2"
        assert rules[0]['condition_events_indices'] == [0]
        assert rules[0]['start_checkpoints'] == ["START"]
        assert rules[0]['end_checkpoints'] == ["END"]
        assert rules[0]['events'][0]['name'] == "greet"
        assert rules[0]['events'][0]['type'] == "user"
        assert not rules[0]['events'][0]['value']
        assert rules[0]['events'][1]['name'] == "utter_greet"
        assert rules[0]['events'][1]['type'] == "action"
        assert not rules[0]['events'][1]['value']
        assert rules[1]['block_name'] == "rule1"

    def test_get_rules_for_training(self):
        Rules(
            block_name="rule1",
            condition_events_indices=[],
            start_checkpoints=["START"],
            end_checkpoints=["END"],
            events=[StoryEvents(name="greet", type="user"), StoryEvents(name="utter_greet", type="action")],
            bot="test_get_rules_for_training",
            user="rule_creator",
        ).save()
        Rules(
            block_name="rule2",
            condition_events_indices=[],
            start_checkpoints=["START"],
            end_checkpoints=["END"],
            events=[StoryEvents(name="greet", type="user"), StoryEvents(name="utter_greet", type="action")],
            bot="test_get_rules_for_training",
            user="rule_creator",
        ).save()
        processor = MongoProcessor()
        rules = processor.get_rules_for_training("test_get_rules_for_training")
        assert isinstance(rules, StoryGraph)
        assert len(rules.story_steps) == 2

    def test_get_rules_no_rules_present(self):
        processor = MongoProcessor()
        rules = processor.get_rules_for_training("test_get_rules_no_rules_present")
        assert not rules.story_steps

    def test_delete_rules(self):
        processor = MongoProcessor()
        rules = (Rules.objects(bot="test_save_rules_already_present", user="rules_creator", status=True))
        assert rules
        processor.delete_rules("test_save_rules_already_present", "rules_creator")
        rules = (Rules.objects(bot="test_save_rules_already_present", user="rules_creator", status=True))
        assert not rules

    def test_delete_rules_no_rules(self):
        processor = MongoProcessor()
        rules = (Rules.objects(bot="test_save_rules_already_present", user="rules_creator", status=True))
        assert not rules
        processor.delete_rules("test_save_rules_already_present", "rules_creator")

    @pytest.mark.asyncio
    async def test_upload_and_save(self):
        processor = MongoProcessor()
        nlu_content = "nlu:\n  - intent: greet\n    examples: |\n      - hey\n      - hello".encode()
        stories_content = "stories:\n  - story: greet\n    steps:\n      - intent: greet\n      - action: utter_offer_help\n      - action: action_restart".encode()
        config_content = "language: en\npipeline:\n- name: WhitespaceTokenizer\n- name: RegexFeaturizer\n- name: LexicalSyntacticFeaturizer\n- name: CountVectorsFeaturizer\n- analyzer: char_wb\n  max_ngram: 4\n  min_ngram: 1\n  name: CountVectorsFeaturizer\n- epochs: 5\n  name: DIETClassifier\n- name: EntitySynonymMapper\n- epochs: 5\n  name: ResponseSelector\npolicies:\n- name: MemoizationPolicy\n- epochs: 5\n  max_history: 5\n  name: TEDPolicy\n- name: RulePolicy\n- core_threshold: 0.3\n  fallback_action_name: action_small_talk\n  name: FallbackPolicy\n  nlu_threshold: 0.75\n".encode()
        domain_content = "intents:\n- greet\nresponses:\n  utter_offer_help:\n  - text: 'how may i help you'\nactions:\n- utter_offer_help\n".encode()
        nlu = UploadFile(filename="nlu.yml", file=BytesIO(nlu_content))
        stories = UploadFile(filename="stories.yml", file=BytesIO(stories_content))
        config = UploadFile(filename="config.yml", file=BytesIO(config_content))
        domain = UploadFile(filename="domain.yml", file=BytesIO(domain_content))
        await processor.upload_and_save(nlu, domain, stories, config, None, None, None, None, "test_upload_and_save",
                                        "rules_creator")
        assert len(list(Intents.objects(bot="test_upload_and_save", user="rules_creator"))) == 2
        assert len(list(Stories.objects(bot="test_upload_and_save", user="rules_creator"))) == 1
        assert len(list(Responses.objects(bot="test_upload_and_save", user="rules_creator"))) == 3
        assert len(
            list(TrainingExamples.objects(intent="greet", bot="test_upload_and_save", user="rules_creator"))) == 2

    @pytest.mark.asyncio
    async def test_upload_and_save_with_rules(self):
        processor = MongoProcessor()
        nlu_content = "nlu:\n  - intent: greet\n    examples: |\n      - hey\n      - hello".encode()
        stories_content = "stories:\n  - story: greet\n    steps:\n      - intent: greet\n      - action: utter_offer_help\n      - action: action_restart".encode()
        config_content = "language: en\npipeline:\n- name: WhitespaceTokenizer\n- name: RegexFeaturizer\n- name: LexicalSyntacticFeaturizer\n- name: CountVectorsFeaturizer\n- analyzer: char_wb\n  max_ngram: 4\n  min_ngram: 1\n  name: CountVectorsFeaturizer\n- epochs: 5\n  name: DIETClassifier\n- name: EntitySynonymMapper\n- epochs: 5\n  name: ResponseSelector\npolicies:\n- name: MemoizationPolicy\n- epochs: 5\n  max_history: 5\n  name: TEDPolicy\n- name: RulePolicy\n- core_threshold: 0.3\n  fallback_action_name: action_small_talk\n  name: FallbackPolicy\n  nlu_threshold: 0.75\n".encode()
        domain_content = "intents:\n- greet\nresponses:\n  utter_offer_help:\n  - text: 'how may i help you'\nactions:\n- utter_offer_help\n".encode()
        rules_content = "rules:\n\n- rule: Only say `hello` if the user provided a location\n  condition:\n  - slot_was_set:\n    - location: true\n  steps:\n  - intent: greet\n  - action: utter_greet\n".encode()
        nlu = UploadFile(filename="nlu.yml", file=BytesIO(nlu_content))
        stories = UploadFile(filename="stories.yml", file=BytesIO(stories_content))
        config = UploadFile(filename="config.yml", file=BytesIO(config_content))
        domain = UploadFile(filename="domain.yml", file=BytesIO(domain_content))
        rules = UploadFile(filename="rules.yml", file=BytesIO(rules_content))
        await processor.upload_and_save(nlu, domain, stories, config, rules, None, None, None, "test_upload_and_save",
                                        "rules_creator")
        assert len(list(Intents.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 2
        assert len(list(Stories.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 1
        assert len(list(Responses.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 3
        assert len(
            list(TrainingExamples.objects(intent="greet", bot="test_upload_and_save", user="rules_creator",
                                          status=True))) == 2
        assert len(list(Rules.objects(bot="test_upload_and_save", user="rules_creator"))) == 2

    @pytest.mark.asyncio
    async def test_upload_and_save_with_http_action(self):
        processor = MongoProcessor()
        nlu_content = "nlu:\n  - intent: greet\n    examples: |\n      - hey\n      - hello".encode()
        stories_content = "stories:\n  - story: greet\n    steps:\n      - intent: greet\n      - action: utter_offer_help\n      - action: action_restart".encode()
        config_content = "language: en\npipeline:\n- name: WhitespaceTokenizer\n- name: RegexFeaturizer\n- name: LexicalSyntacticFeaturizer\n- name: CountVectorsFeaturizer\n- analyzer: char_wb\n  max_ngram: 4\n  min_ngram: 1\n  name: CountVectorsFeaturizer\n- epochs: 5\n  name: DIETClassifier\n- name: EntitySynonymMapper\n- epochs: 5\n  name: ResponseSelector\npolicies:\n- name: MemoizationPolicy\n- epochs: 5\n  max_history: 5\n  name: TEDPolicy\n- name: RulePolicy\n- core_threshold: 0.3\n  fallback_action_name: action_small_talk\n  name: FallbackPolicy\n  nlu_threshold: 0.75\n".encode()
        domain_content = "intents:\n- greet\nresponses:\n  utter_offer_help:\n  - text: 'how may i help you'\nactions:\n- utter_offer_help\n".encode()
        http_action_content = "http_action:\n- action_name: action_performanceUser1000@digite.com\n  http_url: http://www.alphabet.com\n  headers:\n  - key: auth_token\n    parameter_type: value\n    value: bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf\n  params_list:\n  - key: testParam1\n    parameter_type: value\n    value: testValue1\n  - key: testParam2\n    parameter_type: slot\n    value: testValue1\n  request_method: GET\n  response:\n    value: json\n".encode()
        nlu = UploadFile(filename="nlu.yml", file=BytesIO(nlu_content))
        stories = UploadFile(filename="stories.yml", file=BytesIO(stories_content))
        config = UploadFile(filename="config.yml", file=BytesIO(config_content))
        domain = UploadFile(filename="domain.yml", file=BytesIO(domain_content))
        http_action = UploadFile(filename="actions.yml", file=BytesIO(http_action_content))
        await processor.upload_and_save(nlu, domain, stories, config, None, http_action, None, None, "test_upload_and_save",
                                        "rules_creator")
        assert len(list(Intents.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 2
        assert len(list(Stories.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 1
        assert len(list(Responses.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 3
        assert len(
            list(TrainingExamples.objects(intent="greet", bot="test_upload_and_save", user="rules_creator",
                                          status=True))) == 2
        assert len(list(HttpActionConfig.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 1

    @pytest.mark.asyncio
    async def test_upload_and_save_with_empty_multiflow_stories(self):
        processor = MongoProcessor()
        nlu_content = 'version: "3.1"\nnlu:\n- intent: greet\n  examples: |\n    - hey\n    - hello\n    - hi\n    - good morning\n- intent: deny\n  examples: |\n    - no\n    - never\n    - I dont think so\n    - dont like that\n- intent: query\n  examples: |\n    - What is AI?\n    - Tell me about AI?\n    - Do you know about AI\n'.encode()
        stories_content = 'version: "3.1"\nstories:\n- story: greet\n  steps:\n  - intent: greet\n  - action: utter_greet\n  - action: action_restart\n'.encode()
        config_content = "language: en\npipeline:\n- name: WhitespaceTokenizer\n- name: RegexFeaturizer\n- name: LexicalSyntacticFeaturizer\n- name: CountVectorsFeaturizer\n- analyzer: char_wb\n  max_ngram: 4\n  min_ngram: 1\n  name: CountVectorsFeaturizer\n- epochs: 5\n  name: DIETClassifier\n- name: EntitySynonymMapper\n- epochs: 5\n  name: ResponseSelector\npolicies:\n- name: MemoizationPolicy\n- epochs: 5\n  max_history: 5\n  name: TEDPolicy\n- name: RulePolicy\n- core_threshold: 0.3\n  fallback_action_name: action_small_talk\n  name: FallbackPolicy\n  nlu_threshold: 0.75\n".encode()
        domain_content = "intents:\n- query\nresponses:\n  utter_query:\n  - text: 'Artificial intelligence is the simulation of human intelligence processes by machines, especially computer systems'\nactions:\n- utter_query\n".encode()
        http_action_content = "http_action:\n- action_name: action_performanceUser1000@digite.com\n  http_url: http://www.alphabet.com\n  headers:\n  - key: auth_token\n    parameter_type: value\n    value: bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf\n  params_list:\n  - key: testParam1\n    parameter_type: value\n    value: testValue1\n  - key: testParam2\n    parameter_type: slot\n    value: testValue1\n  request_method: GET\n  response:\n    value: json\n".encode()
        multiflow_stories_content = "multiflow_story:\n".encode()
        nlu = UploadFile(filename="nlu.yml", file=BytesIO(nlu_content))
        stories = UploadFile(filename="stories.yml", file=BytesIO(stories_content))
        config = UploadFile(filename="config.yml", file=BytesIO(config_content))
        domain = UploadFile(filename="domain.yml", file=BytesIO(domain_content))
        http_action = UploadFile(filename="actions.yml", file=BytesIO(http_action_content))
        multiflow_story = UploadFile(filename="multiflow_stories.yml", file=BytesIO(multiflow_stories_content))
        await processor.upload_and_save(nlu, domain, stories, config, None, http_action, multiflow_story, None,
                                        "test_upload_and_save",
                                        "rules_creator")
        assert len(list(Intents.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 2
        assert len(list(Stories.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 1
        assert len(list(Responses.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 3
        assert len(
            list(TrainingExamples.objects(intent="greet", bot="test_upload_and_save", user="rules_creator",
                                          status=True))) == 4
        assert len(list(MultiflowStories.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 0

    @pytest.mark.asyncio
    async def test_upload_and_save_with_empty_multiflow_stories_none(self):
        processor = MongoProcessor()
        nlu_content = 'version: "3.1"\nnlu:\n- intent: greet\n  examples: |\n    - hey\n    - hello\n    - hi\n    - good morning\n- intent: deny\n  examples: |\n    - no\n    - never\n    - I dont think so\n    - dont like that\n- intent: query\n  examples: |\n    - What is AI?\n    - Tell me about AI?\n    - Do you know about AI\n'.encode()
        stories_content = 'version: "3.1"\nstories:\n- story: greet\n  steps:\n  - intent: greet\n  - action: utter_greet\n  - action: action_restart\n'.encode()
        config_content = "language: en\npipeline:\n- name: WhitespaceTokenizer\n- name: RegexFeaturizer\n- name: LexicalSyntacticFeaturizer\n- name: CountVectorsFeaturizer\n- analyzer: char_wb\n  max_ngram: 4\n  min_ngram: 1\n  name: CountVectorsFeaturizer\n- epochs: 5\n  name: DIETClassifier\n- name: EntitySynonymMapper\n- epochs: 5\n  name: ResponseSelector\npolicies:\n- name: MemoizationPolicy\n- epochs: 5\n  max_history: 5\n  name: TEDPolicy\n- name: RulePolicy\n- core_threshold: 0.3\n  fallback_action_name: action_small_talk\n  name: FallbackPolicy\n  nlu_threshold: 0.75\n".encode()
        domain_content = "intents:\n- query\nresponses:\n  utter_query:\n  - text: 'Artificial intelligence is the simulation of human intelligence processes by machines, especially computer systems'\nactions:\n- utter_query\n".encode()
        http_action_content = "http_action:\n- action_name: action_performanceUser1000@digite.com\n  http_url: http://www.alphabet.com\n  headers:\n  - key: auth_token\n    parameter_type: value\n    value: bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf\n  params_list:\n  - key: testParam1\n    parameter_type: value\n    value: testValue1\n  - key: testParam2\n    parameter_type: slot\n    value: testValue1\n  request_method: GET\n  response:\n    value: json\n".encode()
        multiflow_stories_content = "".encode()
        nlu = UploadFile(filename="nlu.yml", file=BytesIO(nlu_content))
        stories = UploadFile(filename="stories.yml", file=BytesIO(stories_content))
        config = UploadFile(filename="config.yml", file=BytesIO(config_content))
        domain = UploadFile(filename="domain.yml", file=BytesIO(domain_content))
        http_action = UploadFile(filename="actions.yml", file=BytesIO(http_action_content))
        multiflow_story = UploadFile(filename="multiflow_stories.yml", file=BytesIO(multiflow_stories_content))
        await processor.upload_and_save(nlu, domain, stories, config, None, http_action, multiflow_story, None,
                                        "test_upload_and_save",
                                        "rules_creator")
        assert len(list(Intents.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 2
        assert len(list(Stories.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 1
        assert len(list(Responses.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 3
        assert len(
            list(TrainingExamples.objects(intent="greet", bot="test_upload_and_save", user="rules_creator",
                                          status=True))) == 4
        assert len(list(MultiflowStories.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 0

    @pytest.mark.asyncio
    async def test_upload_and_save_with_multiflow_stories(self):
        processor = MongoProcessor()
        nlu_content = 'version: "3.1"\nnlu:\n- intent: greet\n  examples: |\n    - hey\n    - hello\n    - hi\n    - good morning\n- intent: deny\n  examples: |\n    - no\n    - never\n    - I dont think so\n    - dont like that\n- intent: query\n  examples: |\n    - What is AI?\n    - Tell me about AI?\n    - Do you know about AI\n- intent: affirm\n  examples: |\n    - affirmative\n    - sure, please go ahead\n    - sounds good right\n'.encode()
        stories_content = 'version: "3.1"\nstories:\n- story: greet\n  steps:\n  - intent: greet\n  - action: utter_greet\n  - action: action_restart\n'.encode()
        config_content = "language: en\npipeline:\n- name: WhitespaceTokenizer\n- name: RegexFeaturizer\n- name: LexicalSyntacticFeaturizer\n- name: CountVectorsFeaturizer\n- analyzer: char_wb\n  max_ngram: 4\n  min_ngram: 1\n  name: CountVectorsFeaturizer\n- epochs: 5\n  name: DIETClassifier\n- name: EntitySynonymMapper\n- epochs: 5\n  name: ResponseSelector\npolicies:\n- name: MemoizationPolicy\n- epochs: 5\n  max_history: 5\n  name: TEDPolicy\n- name: RulePolicy\n- core_threshold: 0.3\n  fallback_action_name: action_small_talk\n  name: FallbackPolicy\n  nlu_threshold: 0.75\n".encode()
        domain_content = "intents:\n- greet\n- query\n- deny\n- affirm\nresponses:\n  utter_offer_help:\n  - text: 'how may i help you'\n  utter_query:\n  - text: 'Artificial intelligence is the simulation of human intelligence processes by machines, especially computer systems'\n  utter_goodbye:\n  - text: 'Bye'\n  utter_feedback:\n  - text: 'Thanks you for loving us. Keep using.'\nactions:\n- utter_offer_help\n- utter_query\n- utter_goodbye\n- utter_feedback\n".encode()
        http_action_content = "http_action:\n- action_name: action_performanceUser1000@digite.com\n  http_url: http://www.alphabet.com\n  headers:\n  - key: auth_token\n    parameter_type: value\n    value: bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf\n  params_list:\n  - key: testParam1\n    parameter_type: value\n    value: testValue1\n  - key: testParam2\n    parameter_type: slot\n    value: testValue1\n  request_method: GET\n  response:\n    value: json\n".encode()
        multiflow_stories_content = "multiflow_story:\n- block_name: mf_one_1\n  events:\n    - step:\n        name: query\n        type: INTENT\n        node_id: '1'\n      connections:\n        - name: utter_query\n          type: BOT\n          node_id: '2'\n    - step:\n        name: utter_query\n        type: BOT\n        node_id: '2'\n      connections:\n        - name: deny\n          type: INTENT\n          node_id: '3'\n        - name: affirm\n          type: INTENT\n          node_id: '4'\n    - step:\n        name: affirm\n        type: INTENT\n        node_id: '4'\n      connections:\n        - name: utter_feedback\n          type: BOT\n          node_id: '5'\n    - step:\n        name: utter_feedback\n        type: BOT\n        node_id: '5'\n      connections: null\n    - step:\n        name: utter_goodbye\n        type: BOT\n        node_id: '6'\n      connections: null\n    - step:\n        name: deny\n        type: INTENT\n        node_id: '3'\n      connections:\n        - name: utter_goodbye\n          type: BOT\n          node_id: '6'\n  metadata:\n    - node_id: '6'\n      flow_type: STORY\n  start_checkpoints: [STORY_START]\n  end_checkpoints:".encode()
        nlu = UploadFile(filename="nlu.yml", file=BytesIO(nlu_content))
        stories = UploadFile(filename="stories.yml", file=BytesIO(stories_content))
        config = UploadFile(filename="config.yml", file=BytesIO(config_content))
        domain = UploadFile(filename="domain.yml", file=BytesIO(domain_content))
        http_action = UploadFile(filename="actions.yml", file=BytesIO(http_action_content))
        multiflow_story = UploadFile(filename="multiflow_stories.yml", file=BytesIO(multiflow_stories_content))
        await processor.upload_and_save(nlu, domain, stories, config, None, http_action, multiflow_story, None,
                                        "test_upload_and_save",
                                        "rules_creator")
        assert len(list(Intents.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 5
        assert len(list(Stories.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 1
        assert len(list(Responses.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 6
        assert len(
            list(TrainingExamples.objects(intent="greet", bot="test_upload_and_save", user="rules_creator",
                                          status=True))) == 4
        assert len(list(MultiflowStories.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 1

    def test_load_and_delete_http_action(self):
        HttpActionConfig(
            action_name="act1",
            http_url="http://www.alphabet.com",
            request_method="POST",
            response=HttpActionResponse(value='zxcvb'),
            bot="test_http",
            user="http_creator",
        ).save()
        processor = MongoProcessor()
        actions = processor.load_http_action("test_http")
        assert actions
        assert isinstance(actions, dict)
        assert len(actions["http_action"]) == 1
        processor.delete_bot_actions(bot="test_http", user="http_creator")
        actions = processor.load_http_action("test_http")
        assert not actions['http_action']
        assert isinstance(actions, dict)

    def test_save_http_action_already_exists(self):
        test_dict = {"http_action": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                      "params_list": [{"key": 'location', "parameter_type": 'sender_id', "value": ''}],
                                      "request_method": "GET", "response": {"value": "${RESPONSE}"}},
                                     {"action_name": "test_save_http_action_already_exists",
                                      "http_url": "http://f2724.kairon.io/",
                                      "request_method": "GET", "response": {"value": "${RESPONSE}"}}
                                     ]}
        HttpActionConfig(action_name="test_save_http_action_already_exists",
                         http_url='http://kairon.ai',
                         response=HttpActionResponse(value='response'),
                         request_method='GET',
                         bot='test', user='test').save()
        Actions(name='test_save_http_action_already_exists', bot='test', user='test', status=True,
                type=ActionType.http_action.value).save()
        processor = MongoProcessor()
        processor.save_integrated_actions(test_dict, 'test', 'test')
        action = HttpActionConfig.objects(bot='test', user='test', status=True).get(
            action_name="test_save_http_action_already_exists")
        assert action
        assert action['http_url'] == "http://kairon.ai"
        assert not action['params_list']
        action = HttpActionConfig.objects(bot='test', user='test').get(action_name="rain_today")
        assert action
        assert action['http_url'] == "http://f2724.kairon.io/"
        assert action['params_list']

    def test_get_action_server_logs_empty(self):
        processor = MongoProcessor()
        logs = list(processor.get_action_server_logs("test_bot"))
        assert logs == []

    def test_get_action_server_logs(self):
        bot = "test_bot"
        bot_2 = "testing_bot"
        expected_intents = ["intent13", "intent11", "intent9", "intent8", "intent7", "intent6", "intent5",
                            "intent4", "intent3", "intent2"]
        request_params = {"key": "value", "key2": "value2"}
        ActionServerLogs(intent="intent1", action="http_action", sender="sender_id",
                         timestamp=datetime(2021, 4, 11, 11, 39, 48, 376000),
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot).save()
        ActionServerLogs(intent="intent2", action="http_action", sender="sender_id",
                         url="http://kairon-api.digite.com/api/bot",
                         request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot,
                         status=STATUSES.FAIL.value).save()
        ActionServerLogs(intent="intent1", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot_2).save()
        ActionServerLogs(intent="intent3", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot,
                         status=STATUSES.FAIL.value).save()
        ActionServerLogs(intent="intent4", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot).save()
        ActionServerLogs(intent="intent5", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot,
                         status=STATUSES.FAIL.value).save()
        ActionServerLogs(intent="intent6", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot).save()
        ActionServerLogs(intent="intent7", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot).save()
        ActionServerLogs(intent="intent8", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot).save()
        ActionServerLogs(intent="intent9", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot).save()
        ActionServerLogs(intent="intent10", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot_2).save()
        ActionServerLogs(intent="intent11", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot).save()
        ActionServerLogs(intent="intent12", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot_2,
                         status=STATUSES.FAIL.value).save()
        ActionServerLogs(intent="intent13", action="http_action", sender="sender_id_13",
                         request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot,
                         status=STATUSES.FAIL.value).save()
        processor = MongoProcessor()
        logs = list(processor.get_action_server_logs(bot))
        assert len(logs) == 10
        assert [log['intent'] in expected_intents for log in logs]
        assert logs[0]['action'] == "http_action"
        assert any([log['request_params'] == request_params for log in logs])
        assert any([log['sender'] == "sender_id_13" for log in logs])
        assert any([log['api_response'] == "Response" for log in logs])
        assert any([log['bot_response'] == "Bot Response" for log in logs])
        assert any([log['status'] == STATUSES.FAIL.value for log in logs])
        assert any([log['status'] == STATUSES.SUCCESS.value for log in logs])

        logs = list(processor.get_action_server_logs(bot_2))
        assert len(logs) == 3

    def test_get_action_server_logs_start_idx_page_size(self):
        processor = MongoProcessor()
        bot = "test_bot"
        bot_2 = "testing_bot"
        logs = list(processor.get_action_server_logs(bot, 10, 15))
        assert len(logs) == 1

        logs = list(processor.get_action_server_logs(bot, 10, 1))
        assert len(logs) == 1

        logs = list(processor.get_action_server_logs(bot, 0, 5))
        assert len(logs) == 5

        logs = list(processor.get_action_server_logs(bot_2, 0, 5))
        assert len(logs) == 3

        logs = list(processor.get_action_server_logs(bot_2, 2, 1))
        assert len(logs) == 1
        log = logs[0]
        assert log['intent'] == "intent1"

    def test_get_action_server_logs_cnt(self):
        processor = MongoProcessor()
        bot = "test_bot"
        bot_2 = "testing_bot"
        cnt = processor.get_row_count(ActionServerLogs, bot)
        assert cnt == 11

        cnt = processor.get_row_count(ActionServerLogs, bot_2)
        assert cnt == 3

    def test_get_existing_slots(self):
        Slots(
            name="location",
            type="text",
            initial_value="delhi",
            bot="test_get_existing_slots",
            user="bot_user",
        ).save()
        Slots(
            name="email_id",
            type="text",
            initial_value="bot_user@digite.com",
            bot="test_get_existing_slots",
            user="bot_user",
        ).save()
        Slots(
            name="username",
            type="text",
            initial_value="bot_user",
            bot="test_get_existing_slots",
            user="bot_user",
            status=False
        ).save()
        slots = list(MongoProcessor.get_existing_slots("test_get_existing_slots"))
        assert len(slots) == 2
        assert slots[0]['name'] == 'location'
        assert slots[1]['name'] == 'email_id'

    def test_get_existing_slots_bot_not_exists(self):
        slots = list(MongoProcessor.get_existing_slots("test_get_existing_slots_bot_not_exists"))
        assert len(slots) == 0

    def test_add_system_required_slots_includes_mail_channel_slots(self):
        """add_system_required_slots must provision is_followup (boolean), parent_log_id (text),
        date (text), and cc (list) as system slots."""
        from kairon.shared.data.data_objects import Slots as SlotsDoc
        bot = "test_sys_slots_mail_channel"
        user = "test_user"
        processor = MongoProcessor()
        processor.add_system_required_slots(bot, user)

        slot_map = {s.name: s for s in SlotsDoc.objects(bot=bot, status=True)}

        assert "is_followup" in slot_map, "is_followup slot must be provisioned"
        assert slot_map["is_followup"].type == "bool"
        assert slot_map["is_followup"].is_default is True

        assert "parent_log_id" in slot_map, "parent_log_id slot must be provisioned"
        assert slot_map["parent_log_id"].type == "text"
        assert slot_map["parent_log_id"].is_default is True

        assert "date" in slot_map, "date slot must be provisioned"
        assert slot_map["date"].type == "text"
        assert slot_map["date"].is_default is True

        assert "cc" in slot_map, "cc slot must be provisioned"
        assert slot_map["cc"].type == "list"
        assert slot_map["cc"].is_default is True

    @pytest.mark.asyncio
    async def test_save_training_data_all(self, get_training_data, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        path = 'tests/testing_data/yml_training_files'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions, multiflow_stories,  bot_content, chat_client_config = await get_training_data(
            path)

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, config, domain, story_graph, nlu, http_actions, multiflow_stories, bot_content,
                                           chat_client_config, overwrite=True)

        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 305
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = mongo_processor.load_stories(bot)
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
        domain = mongo_processor.load_domain(bot)
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
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 48
        assert domain.intents.__len__() == 32
        assert not Utility.check_empty_string(
            domain.responses["utter_cheer_up"][0]["image"]
        )
        assert domain.responses["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.responses["utter_offer_help"][0]["custom"]
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 4
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert len(actions['http_action']) == 17
        assert len(Actions.objects(type='http_action', bot=bot)) == 17
        multiflow_stories = mongo_processor.load_multiflow_stories_yaml(bot)
        assert isinstance(multiflow_stories, dict) is True
        bot_content = mongo_processor.load_bot_content(bot)
        assert isinstance(bot_content, list) is True

    @pytest.mark.asyncio
    async def test_save_training_data_no_rules_and_http_actions(self, get_training_data, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        path = 'tests/testing_data/all'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions, multiflow_stories, bot_content, chat_client_config = await get_training_data(
            path)

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, config, domain, story_graph, nlu, http_actions, multiflow_stories, bot_content,
                                           chat_client_config, overwrite=True)

        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 292
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 16
        assert story_graph.story_steps[14].events[2].intent['name'] == 'user_feedback'
        assert story_graph.story_steps[14].events[2].entities[0]['value'] == 'like'
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdresponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdresponse'
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 40
        assert domain.responses.keys().__len__() == 27
        assert domain.entities.__len__() == 40
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 27
        assert domain.intents.__len__() == 29
        assert not Utility.check_empty_string(
            domain.responses["utter_cheer_up"][0]["image"]
        )
        assert domain.responses["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.responses["utter_offer_help"][0]["custom"]
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert rules == ['ask the user to rephrase whenever they send a message with low nlu confidence']
        actions = mongo_processor.load_http_action(bot)
        assert not actions['http_action']
        assert Utterances.objects(bot=bot).count() == 27

    @pytest.mark.asyncio
    async def test_save_training_data_all_overwrite_slot_mapping(self, get_training_data, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com',
                'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        path = 'tests/testing_data/yml_training_files'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions, multiflow_stories, bot_content, chat_client_config = await get_training_data(
            path)
        domain.slots[0].mappings[0]['conditions'] = [{"active_loop": "ticket_attributes_form", "requested_slot": "date_time"}]
        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, config, domain, story_graph, nlu, http_actions, multiflow_stories, bot_content,
                                           chat_client_config, overwrite=True)

        slot_mapping = SlotMapping.objects(form_name="ticket_attributes_form").get()
        assert slot_mapping.slot == "date_time"

    @pytest.mark.asyncio
    async def test_save_training_data_all_overwrite(self, get_training_data, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        path = 'tests/testing_data/yml_training_files'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions, multiflow_stories, bot_content, chat_client_config = await get_training_data(
            path)

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, config, domain, story_graph, nlu, http_actions, multiflow_stories, bot_content,
                                           chat_client_config, overwrite=True)

        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 305
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = mongo_processor.load_stories(bot)
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
        domain = mongo_processor.load_domain(bot)
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
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 48
        assert domain.intents.__len__() == 32
        assert not Utility.check_empty_string(
            domain.responses["utter_cheer_up"][0]["image"]
        )
        assert domain.responses["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.responses["utter_offer_help"][0]["custom"]
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 4
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert len(actions['http_action']) == 17

    @pytest.mark.asyncio
    async def test_save_training_data_all_append(self, get_training_data, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        path = 'tests/testing_data/validator/append'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions, multiflow_stories, bot_content, chat_client_config = await get_training_data(
            path)

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, config, domain, story_graph, nlu, http_actions, multiflow_stories, bot_content,
                                           chat_client_config, overwrite=False,
                                           what=REQUIREMENTS.copy() - {"chat_client_config"})

        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 308
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 18
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
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 41
        assert len([slot for slot in domain.slots if slot.influence_conversation is True]) == 25
        assert len([slot for slot in domain.slots if slot.influence_conversation is False]) == 16
        assert domain.intent_properties.__len__() == 33
        assert len([intent for intent in domain.intent_properties.keys() if
                    domain.intent_properties.get(intent)['used_entities']]) == 27
        assert len([intent for intent in domain.intent_properties.keys() if
                    not domain.intent_properties.get(intent)['used_entities']]) == 6
        assert domain.responses.keys().__len__() == 31
        assert domain.entities.__len__() == 41
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 50
        assert domain.intents.__len__() == 33
        assert not Utility.check_empty_string(
            domain.responses["utter_cheer_up"][0]["image"]
        )
        assert domain.responses["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.responses["utter_offer_help"][0]["custom"]
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 4
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert len(actions['http_action']) == 17

    def test_delete_nlu_only(self):
        bot = 'test'
        user = 'test'
        mongo_processor = MongoProcessor()
        mongo_processor.delete_bot_data(bot, user, {"nlu"})
        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 0
        assert training_data.entity_synonyms.__len__() == 0
        assert training_data.regex_features.__len__() == 0
        assert training_data.lookup_tables.__len__() == 0
        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 18
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
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 41
        assert len([slot for slot in domain.slots if slot.influence_conversation is True]) == 25
        assert len([slot for slot in domain.slots if slot.influence_conversation is False]) == 16
        assert domain.intent_properties.__len__() == 33
        assert len([intent for intent in domain.intent_properties.keys() if
                    domain.intent_properties.get(intent)['used_entities']]) == 27
        assert len([intent for intent in domain.intent_properties.keys() if
                    not domain.intent_properties.get(intent)['used_entities']]) == 6
        assert domain.responses.keys().__len__() == 31
        assert domain.entities.__len__() == 41
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 50
        assert domain.intents.__len__() == 33
        assert not Utility.check_empty_string(
            domain.responses["utter_cheer_up"][0]["image"]
        )
        assert domain.responses["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.responses["utter_offer_help"][0]["custom"]
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 4
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert len(actions['http_action']) == 17

    @pytest.mark.asyncio
    async def test_save_nlu_only(self, get_training_data):
        path = 'tests/testing_data/yml_training_files'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions, multiflow_stories, bot_content, chat_client_config = await get_training_data(
            path)

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, nlu=nlu, overwrite=True, what={'nlu'})

        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 305
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1

    def test_delete_stories_only(self):
        bot = 'test'
        user = 'test'
        mongo_processor = MongoProcessor()
        mongo_processor.delete_bot_data(bot, user, {"stories"})
        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 305
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 0
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 41
        assert len([slot for slot in domain.slots if slot.influence_conversation is True]) == 25
        assert len([slot for slot in domain.slots if slot.influence_conversation is False]) == 16
        assert domain.intent_properties.__len__() == 33
        assert len([intent for intent in domain.intent_properties.keys() if
                    domain.intent_properties.get(intent)['used_entities']]) == 27
        assert len([intent for intent in domain.intent_properties.keys() if
                    not domain.intent_properties.get(intent)['used_entities']]) == 6
        assert domain.responses.keys().__len__() == 31
        assert domain.entities.__len__() == 41
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 50
        assert domain.intents.__len__() == 33
        assert not Utility.check_empty_string(
            domain.responses["utter_cheer_up"][0]["image"]
        )
        assert domain.responses["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.responses["utter_offer_help"][0]["custom"]
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 4
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert len(actions['http_action']) == 17

    def test_delete_multiflow_stories_only(self):
        bot = 'test'
        user = 'test'
        mongo_processor = MongoProcessor()
        mongo_processor.delete_bot_data(bot, user, {"multiflow_stories"})
        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 305
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 0
        multiflow_story = mongo_processor.load_linear_flows_from_multiflow_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 0
        print(multiflow_story)
        assert story_graph.story_steps.__len__() == 0
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 41
        assert len([slot for slot in domain.slots if slot.influence_conversation is True]) == 25
        assert len([slot for slot in domain.slots if slot.influence_conversation is False]) == 16
        assert domain.intent_properties.__len__() == 33
        assert len([intent for intent in domain.intent_properties.keys() if
                    domain.intent_properties.get(intent)['used_entities']]) == 27
        assert len([intent for intent in domain.intent_properties.keys() if
                    not domain.intent_properties.get(intent)['used_entities']]) == 6
        assert domain.responses.keys().__len__() == 31
        assert domain.entities.__len__() == 41
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 50
        assert domain.intents.__len__() == 33

    @pytest.mark.asyncio
    async def test_save_stories_only(self, get_training_data):
        path = 'tests/testing_data/yml_training_files'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions, multiflow_stories, bot_content, chat_client_config = await get_training_data(
            path)

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, story_graph=story_graph, overwrite=True, what={'stories'})

        story_graph = mongo_processor.load_stories(bot)
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

    def test_delete_config_and_actions_only(self):
        bot = 'test'
        user = 'test'
        mongo_processor = MongoProcessor()
        mongo_processor.delete_bot_data(bot, user, {"config", "actions"})
        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 305
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 16
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 41
        assert domain.intent_properties.__len__() == 33
        assert domain.responses.keys().__len__() == 31
        assert domain.entities.__len__() == 41
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 31
        assert domain.intents.__len__() == 33
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 4
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert not actions['http_action']
        assert mongo_processor.load_config(bot)

    @pytest.mark.asyncio
    async def test_save_actions_and_config_only(self, get_training_data):
        path = 'tests/testing_data/yml_training_files'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions, multiflow_stories, bot_content, chat_client_config = await get_training_data(
            path)
        config['language'] = 'fr'

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, config=config, actions=http_actions, overwrite=True,
                                           what={'actions', 'config'})

        assert len(mongo_processor.load_http_action(bot)['http_action']) == 17
        config = mongo_processor.load_config(bot)
        assert config['language'] == 'fr'
        assert config['pipeline']
        assert config['policies']

    def test_delete_rules_and_domain_only(self):
        bot = 'test'
        user = 'test'
        mongo_processor = MongoProcessor()
        mongo_processor.delete_bot_data(bot, user, {"rules", "domain"})
        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 305
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 16
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 1
        assert domain.intent_properties.__len__() == 5
        assert domain.responses.keys().__len__() == 0
        assert domain.entities.__len__() == 0
        assert domain.form_names.__len__() == 0
        assert domain.user_actions.__len__() == 19
        assert domain.intents.__len__() == 5
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 0
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert len(actions['http_action']) == 17

    @pytest.mark.asyncio
    async def test_save_rules_and_domain_only(self, get_training_data):
        path = 'tests/testing_data/yml_training_files'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions, multiflow_stories, bot_content, chat_client_config = await get_training_data(
            path)

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, story_graph=story_graph, domain=domain, overwrite=True,
                                           what={'rules', 'domain'})

        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 3
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 41
        assert domain.intent_properties.__len__() == 32
        assert domain.responses.keys().__len__() == 27
        assert domain.entities.__len__() == 41
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 46
        assert domain.intents.__len__() == 32

    @pytest.fixture()
    def resource_prepare_training_data_for_validation_with_home_dir(self):
        tmp_dir = tempfile.mkdtemp()
        pytest.dir = tmp_dir
        yield 'resource_prepare_training_data_for_validation_with_home_dir'
        Utility.delete_directory(pytest.dir)

    @pytest.fixture()
    def resource_prepare_training_data_for_validation(self):
        yield 'resource_prepare_training_data_for_validation'
        Utility.delete_directory(os.path.join('training_data', 'test'))

    def test_prepare_training_data_for_validation_no_data(self, resource_prepare_training_data_for_validation):
        bot = 'test'
        processor = MongoProcessor()
        processor.prepare_training_data_for_validation(bot)
        bot_home = os.path.join('training_data', bot)
        assert os.path.exists(bot_home)
        dirs = os.listdir(bot_home)
        files = set(os.listdir(os.path.join(bot_home, dirs[0]))).union(
            os.listdir(os.path.join(bot_home, dirs[0], DEFAULT_DATA_PATH)))
        assert ALLOWED_DOMAIN_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_CONFIG_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_NLU_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_STORIES_FORMATS.intersection(files).__len__() == 1

    def test_prepare_training_data_for_validation_with_home_dir(self,
                                                                resource_prepare_training_data_for_validation_with_home_dir):
        bot = 'test'
        processor = MongoProcessor()
        processor.prepare_training_data_for_validation(bot, pytest.dir)
        bot_home = pytest.dir
        assert os.path.exists(bot_home)
        files = set(os.listdir(bot_home)).union(os.listdir(os.path.join(bot_home, DEFAULT_DATA_PATH)))
        assert ALLOWED_DOMAIN_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_CONFIG_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_NLU_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_STORIES_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_RULES_FORMATS.intersection(files).__len__() == 1

    @pytest.fixture()
    def resource_prepare_training_data_for_validation_nlu_only(self):
        pytest.nlu_only_tmp_dir = tempfile.mkdtemp()
        yield 'resource_prepare_training_data_for_validation_nlu_only'
        Utility.delete_directory(pytest.nlu_only_tmp_dir)

    @pytest.fixture()
    def resource_prepare_training_data_for_validation_rules_only(self):
        pytest.nlu_only_tmp_dir = tempfile.mkdtemp()
        yield 'resource_prepare_training_data_for_validation_rules_only'
        Utility.delete_directory(pytest.nlu_only_tmp_dir)

    def test_prepare_training_data_for_validation_nlu_domain_only(self,
                                                                  resource_prepare_training_data_for_validation_nlu_only):
        bot = 'test'
        processor = MongoProcessor()
        processor.prepare_training_data_for_validation(bot, pytest.nlu_only_tmp_dir, {'nlu', 'domain'})
        bot_home = pytest.nlu_only_tmp_dir
        assert os.path.exists(bot_home)
        files = set(os.listdir(os.path.join(bot_home))).union(
            os.listdir(os.path.join(bot_home, DEFAULT_DATA_PATH)))
        assert ALLOWED_DOMAIN_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_NLU_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_CONFIG_FORMATS.intersection(files).__len__() == 0
        assert ALLOWED_STORIES_FORMATS.intersection(files).__len__() == 0
        assert ALLOWED_RULES_FORMATS.intersection(files).__len__() == 0

    def test_prepare_training_data_for_validation_rules_only(self,
                                                             resource_prepare_training_data_for_validation_rules_only):
        bot = 'test'
        processor = MongoProcessor()
        processor.prepare_training_data_for_validation(bot, pytest.nlu_only_tmp_dir, {'rules'})
        bot_home = pytest.nlu_only_tmp_dir
        assert os.path.exists(bot_home)
        files = set(os.listdir(os.path.join(bot_home))).union(
            os.listdir(os.path.join(bot_home, DEFAULT_DATA_PATH)))
        assert ALLOWED_DOMAIN_FORMATS.intersection(files).__len__() == 0
        assert ALLOWED_NLU_FORMATS.intersection(files).__len__() == 0
        assert ALLOWED_CONFIG_FORMATS.intersection(files).__len__() == 0
        assert ALLOWED_STORIES_FORMATS.intersection(files).__len__() == 0
        assert ALLOWED_RULES_FORMATS.intersection(files).__len__() == 1

    def test_prepare_training_data_for_validation(self, resource_prepare_training_data_for_validation):
        bot = 'test'
        processor = MongoProcessor()
        processor.prepare_training_data_for_validation(bot)
        bot_home = os.path.join('training_data', bot)
        assert os.path.exists(bot_home)
        dirs = os.listdir(bot_home)
        files = set(os.listdir(os.path.join(bot_home, dirs[0]))).union(
            os.listdir(os.path.join(bot_home, dirs[0], DEFAULT_DATA_PATH)))
        assert ALLOWED_DOMAIN_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_CONFIG_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_NLU_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_STORIES_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_RULES_FORMATS.intersection(files).__len__() == 1

    @pytest.fixture()
    def resource_unzip_and_validate(self):
        pytest.bot = 'test_validate_and_prepare_data'
        data_path = 'tests/testing_data/yml_training_files'
        tmp_dir = tempfile.gettempdir()
        zip_file = os.path.join(tmp_dir, 'test')
        shutil.make_archive(zip_file, 'zip', data_path)
        pytest.zip = UploadFile(filename="test.zip", file=BytesIO(open(zip_file + '.zip', 'rb').read()))
        yield "resource_unzip_and_validate"
        os.remove(zip_file + '.zip')
        shutil.rmtree(os.path.join('training_data', pytest.bot))

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_zip(self, resource_unzip_and_validate):
        processor = MongoProcessor()
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', [pytest.zip], True)
        assert REQUIREMENTS == files_received
        assert is_event_data
        bot_data_home_dir = Utility.get_latest_file(os.path.join('training_data', pytest.bot))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'actions.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert not non_event_validation_summary

    @pytest.fixture()
    def resource_save_and_validate_training_files(self):
        pytest.bot = 'test_validate_and_prepare_data'
        config_path = 'tests/testing_data/yml_training_files/config.yml'
        chat_client_config_path = "tests/testing_data/yml_training_files/chat_client_config.yml"
        domain_path = 'tests/testing_data/yml_training_files/domain.yml'
        nlu_path = 'tests/testing_data/yml_training_files/data/nlu.yml'
        stories_path = 'tests/testing_data/yml_training_files/data/stories.yml'
        http_action_path = 'tests/testing_data/yml_training_files/actions.yml'
        rules_path = 'tests/testing_data/yml_training_files/data/rules.yml'
        pytest.config = UploadFile(filename="config.yml", file=BytesIO(open(config_path, 'rb').read()))
        pytest.chat_client_config = UploadFile(filename="chat_client_config.yml",
                                               file=BytesIO(open(chat_client_config_path, 'rb').read()))
        pytest.domain = UploadFile(filename="domain.yml", file=BytesIO(open(domain_path, 'rb').read()))
        pytest.nlu = UploadFile(filename="nlu.yml", file=BytesIO(open(nlu_path, 'rb').read()))
        pytest.stories = UploadFile(filename="stories.yml", file=BytesIO(open(stories_path, 'rb').read()))
        pytest.http_actions = UploadFile(filename="actions.yml", file=BytesIO(open(http_action_path, 'rb').read()))
        pytest.rules = UploadFile(filename="rules.yml", file=BytesIO(open(rules_path, 'rb').read()))
        pytest.non_nlu = UploadFile(filename="non_nlu.yml", file=BytesIO(open(rules_path, 'rb').read()))
        yield "resource_save_and_validate_training_files"
        shutil.rmtree(os.path.join('training_data', pytest.bot))

    @pytest.mark.asyncio
    async def test_load_chat_client_config(self, monkeypatch, resource_save_and_validate_training_files):
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        training_file = [pytest.chat_client_config]
        is_event_data = await processor.validate_and_log(pytest.bot, 'user@integration.com', training_file, True)
        chat_client_config = processor.load_chat_client_config(pytest.bot, 'user@integration.com')
        assert not is_event_data
        assert chat_client_config["config"]
        assert chat_client_config['white_listed_domain'] == ["*"]
        assert chat_client_config['config']['welcomeMessage'] == "Hello! How are you? This is Testing Welcome Message."
        assert chat_client_config['config']['name'] == "kairon_testing"
        assert not chat_client_config["config"].get('headers')
        assert not chat_client_config["config"].get('multilingual')
        assert not chat_client_config.get("_id")
        assert not chat_client_config.get("bot")
        assert not chat_client_config.get("status")
        assert not chat_client_config.get("user")
        assert not chat_client_config.get("timestamp")

    @pytest.mark.asyncio
    async def test_download_data_files_with_chat_client_config(self, monkeypatch,
                                                               resource_save_and_validate_training_files):
        from zipfile import ZipFile

        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        training_file = [pytest.chat_client_config]
        is_event_data = await processor.validate_and_log(pytest.bot, 'user@integration.com', training_file, True)
        file_path = processor.download_files(pytest.bot, "user@integration.com")
        assert file_path.endswith(".zip")
        zip_file = ZipFile(file_path, mode='r')
        assert zip_file.filelist.__len__() == 9
        assert zip_file.getinfo('chat_client_config.yml')

    @pytest.fixture()
    def resource_validate_and_prepare_data_save_actions_and_config_append(self):
        import ujson as json

        pytest.bot = 'test_validate_and_prepare_data'
        config = "language: fr\npipeline:\n- name: WhitespaceTokenizer\n- name: LexicalSyntacticFeaturizer\n-  name: DIETClassifier\npolicies:\n-  name: TEDPolicy".encode()
        actions = {"http_action": [
            {"action_name": "test_validate_and_prepare_data", "http_url": "http://www.alphabet.com",
             "request_method": "GET", "response": {"value": "json"}}]}
        actions = json.dumps(actions).encode('utf-8')
        pytest.config = UploadFile(filename="config.yml", file=BytesIO(config))
        pytest.http_actions = UploadFile(filename="actions.yml", file=BytesIO(actions))
        yield "resource_validate_and_prepare_data_save_actions_and_config_append"
        shutil.rmtree(os.path.join('training_data', pytest.bot))

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_training_files(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.config, pytest.domain, pytest.nlu, pytest.stories, pytest.http_actions, pytest.rules,
                         pytest.chat_client_config]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        assert REQUIREMENTS - {'multiflow_stories','bot_content'} == files_received
        assert is_event_data
        bot_data_home_dir = Utility.get_latest_file(os.path.join('training_data', pytest.bot))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'chat_client_config.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'actions.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert not non_event_validation_summary

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_nlu_only(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.nlu]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        assert {'nlu'} == files_received
        assert is_event_data
        bot_data_home_dir = Utility.get_latest_file(os.path.join('training_data', pytest.bot))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'actions.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert not non_event_validation_summary

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_stories_only(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.stories]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        assert {'stories'} == files_received
        assert is_event_data
        bot_data_home_dir = Utility.get_latest_file(os.path.join('training_data', pytest.bot))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'actions.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert not non_event_validation_summary

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_config(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.config]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        assert {'config'} == files_received
        assert not is_event_data
        assert not non_event_validation_summary.get("config")
        assert not non_event_validation_summary.get("http_actions")
        assert processor.list_http_actions(pytest.bot).__len__() == 0
        config = processor.load_config(pytest.bot)
        assert config['pipeline']
        assert config['policies']
        assert config['language']

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_chat_client_config(self, resource_save_and_validate_training_files,
                                                                     monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        training_file = [pytest.chat_client_config]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        assert {'chat_client_config'} == files_received
        assert not is_event_data
        assert not non_event_validation_summary.get("config")
        assert not non_event_validation_summary.get("http_actions")
        chat_client_config = processor.load_chat_client_config(pytest.bot, 'test')
        assert chat_client_config['config']
        assert chat_client_config['white_listed_domain'] == ["*"]
        assert chat_client_config['config']['welcomeMessage'] == "Hello! How are you? This is Testing Welcome Message."
        assert chat_client_config['config']['name'] == "kairon_testing"
        assert not chat_client_config.get("_id")
        assert not chat_client_config.get('status')
        assert not chat_client_config.get('user')
        assert not chat_client_config.get('bot')
        assert chat_client_config['white_listed_domain']

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_rules(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.rules]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        assert {'rules'} == files_received
        assert is_event_data
        bot_data_home_dir = Utility.get_latest_file(os.path.join('training_data', pytest.bot))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'actions.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert not non_event_validation_summary

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_actions(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.http_actions]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        print(non_event_validation_summary)
        assert {'actions'} == files_received
        assert not is_event_data
        assert not non_event_validation_summary.get("http_actions")
        assert not non_event_validation_summary.get("config")
        assert processor.list_http_actions(pytest.bot).__len__() == 17

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_domain(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.domain]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        assert {'domain'} == files_received
        assert is_event_data
        bot_data_home_dir = Utility.get_latest_file(os.path.join('training_data', pytest.bot))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'actions.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert not non_event_validation_summary


    def test_get_latest_file_folder_not_exists(self,tmp_path):
        folder = tmp_path / "non_existent"

        with pytest.raises(AppException, match="Folder does not exists"):
            Utility.get_latest_file(str(folder))


    def test_get_latest_file_returns_latest(self,tmp_path):
        folder = tmp_path / "files"
        import time
        import os
        folder.mkdir()

        file1 = folder / "a.txt"
        file2 = folder / "b.txt"

        file1.write_text("first")
        time.sleep(1)
        file2.write_text("second")

        latest = Utility.get_latest_file(str(folder))

        assert latest == str(file2)

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_actions_and_config_overwrite(self,
                                                                               resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.http_actions, pytest.config]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        print(non_event_validation_summary)
        assert {'actions', 'config'} == files_received
        assert not is_event_data
        assert not non_event_validation_summary.get("http_actions")
        assert not non_event_validation_summary.get("config")
        assert processor.list_http_actions(pytest.bot).__len__() == 17
        config = processor.load_config(pytest.bot)
        assert config['pipeline']
        assert config['policies']
        assert config['language']

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_actions_and_config_append(self,
                                                                            resource_validate_and_prepare_data_save_actions_and_config_append):
        processor = MongoProcessor()
        training_file = [pytest.http_actions, pytest.config]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, False)
        assert {'actions', 'config'} == files_received
        assert not is_event_data
        assert not non_event_validation_summary.get("http_actions")
        assert not non_event_validation_summary.get("config")
        assert processor.list_http_actions(pytest.bot).__len__() == 18
        config = processor.load_config(pytest.bot)
        assert config['pipeline']
        assert config['policies']
        assert config['language'] == 'fr'

    @pytest.fixture()
    def resource_validate_and_prepare_data_no_valid_file_in_zip(self):
        data_path = 'tests/testing_data/validator'
        tmp_dir = tempfile.gettempdir()
        zip_file = os.path.join(tmp_dir, 'test')
        shutil.make_archive(zip_file, 'zip', data_path)
        pytest.zip = UploadFile(filename="test.zip", file=BytesIO(open(zip_file + '.zip', 'rb').read()))
        yield "resource_validate_and_prepare_data_no_valid_file_in_zip"
        os.remove(zip_file + '.zip')

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_no_valid_file_received(self,
                                                                    resource_validate_and_prepare_data_no_valid_file_in_zip):
        processor = MongoProcessor()
        bot = 'test_validate_and_prepare_data'
        with pytest.raises(AppException) as e:
            await processor.validate_and_prepare_data(bot, 'test', [pytest.zip], True)
        assert str(e).__contains__('Invalid files received')

    @pytest.fixture()
    def resource_validate_and_prepare_data_zip_actions_config(self):
        tmp_dir = tempfile.mkdtemp()
        pytest.bot = 'validate_and_prepare_data_zip_actions_config'
        zip_file = os.path.join(tmp_dir, 'test')
        shutil.copy2('tests/testing_data/yml_training_files/actions.yml', tmp_dir)
        shutil.copy2('tests/testing_data/yml_training_files/config.yml', tmp_dir)
        shutil.make_archive(zip_file, 'zip', tmp_dir)
        pytest.zip = UploadFile(filename="test.zip", file=BytesIO(open(zip_file + '.zip', 'rb').read()))
        yield "resource_validate_and_prepare_data_zip_actions_config"
        shutil.rmtree(tmp_dir)
        shutil.rmtree(os.path.join('training_data', pytest.bot))

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_zip_actions_config(self,
                                                                resource_validate_and_prepare_data_zip_actions_config):
        processor = MongoProcessor()
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', [pytest.zip], True)
        assert {'actions', 'config'} == files_received
        assert not is_event_data
        assert not non_event_validation_summary.get("http_actions")
        assert not non_event_validation_summary.get("config")
        assert processor.list_http_actions(pytest.bot).__len__() == 17
        config = processor.load_config(pytest.bot)
        assert config['pipeline']
        assert config['policies']
        assert config['language']

    @pytest.fixture()
    def resource_validate_and_prepare_data_invalid_zip_actions_config(self):
        import ujson as json
        tmp_dir = tempfile.mkdtemp()
        pytest.bot = 'validate_and_prepare_data_zip_actions_config'
        zip_file = os.path.join(tmp_dir, 'test')
        actions = Utility.read_yaml('tests/testing_data/yml_training_files/actions.yml')
        actions['http_action'][0].pop('action_name')
        actions['google_search_action'][0].pop('name')
        Utility.write_to_file(os.path.join(tmp_dir, 'actions.yml'), json.dumps(actions).encode())
        shutil.copy2('tests/testing_data/yml_training_files/config.yml', tmp_dir)
        shutil.make_archive(zip_file, 'zip', tmp_dir)
        pytest.zip = UploadFile(filename="test.zip", file=BytesIO(open(zip_file + '.zip', 'rb').read()))
        yield "resource_validate_and_prepare_data_zip_actions_config"
        shutil.rmtree(tmp_dir)
        shutil.rmtree(os.path.join('training_data', pytest.bot))

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_invalid_zip_actions_config(self,
                                                                        resource_validate_and_prepare_data_invalid_zip_actions_config):
        processor = MongoProcessor()
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', [pytest.zip], True)
        print(non_event_validation_summary)
        assert 'No name found for  [http_action]' in non_event_validation_summary['summary']['http_action'][0]
        assert files_received == {'actions', 'config'}
        assert not is_event_data

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_all_actions(self):
        bot = 'test_validate_and_prepare_data_all_actions'
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user='test'
        )
        llm_secret.save()
        with patch('kairon.shared.utils.SMTP'):
            with patch('kairon.shared.actions.data_objects.ZendeskAction.validate'):
                with patch('kairon.shared.actions.data_objects.JiraAction.validate'):
                    with patch('pipedrive.client.Client'):
                        processor = MongoProcessor()
                        BotSettings(bot=bot, user='test',
                                    llm_settings=LLMSettings(enable_faq=True)).save()
                        actions = UploadFile(filename="actions.yml",
                                             file=BytesIO(open('tests/testing_data/actions/actions.yml', 'rb').read()))
                        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
                            bot, 'test', [actions], True)
                        assert not DeepDiff(non_event_validation_summary['summary'], {
                            'http_action': [], 'slot_set_action': [], 'form_validation_action': [],
                            'email_action': [],
                            'google_search_action': [], 'jira_action': [], 'zendesk_action': [],
                            'pipedrive_leads_action': [], 'prompt_action': [], 'razorpay_action': [],
                            'pyscript_action': [], 'database_action': [], 'callback_action': [], 'callbackconfig': [],
                            'two_stage_fallback': [], 'schedule_action': [], 'web_search_action': [], 'live_agent_action': [],
                            'parallel_action': [], 'voice_call_action': [], 'store_page_action': [], 'agent_action': []
                        }, ignore_order=True)
                        assert non_event_validation_summary['component_count']['http_action'] == 4
                        assert non_event_validation_summary['component_count']['jira_action'] == 2
                        assert non_event_validation_summary['component_count']['google_search_action'] == 2
                        assert non_event_validation_summary['component_count']['zendesk_action'] == 2
                        assert non_event_validation_summary['component_count']['email_action'] == 2
                        assert non_event_validation_summary['component_count']['slot_set_action'] == 3
                        assert non_event_validation_summary['component_count']['form_validation_action'] == 4
                        assert non_event_validation_summary['component_count']['pipedrive_leads_action'] == 2
                        assert non_event_validation_summary['component_count']['prompt_action'] == 2
                        assert non_event_validation_summary['validation_failed'] is False
                        assert files_received == {'actions'}
                        assert not is_event_data
                        saved_actions = processor.load_action_configurations(
                            bot)
                        assert len(saved_actions['http_action']) == 4
                        assert len(saved_actions['slot_set_action']) == 3
                        assert len(saved_actions['form_validation_action']) == 4
                        assert len(saved_actions['jira_action']) == 2
                        assert len(saved_actions['google_search_action']) == 2
                        assert len(saved_actions['zendesk_action']) == 2
                        assert len(saved_actions['email_action']) == 2
                        assert len(saved_actions['pipedrive_leads_action']) == 2
                        assert len(saved_actions['prompt_action']) == 2
                        assert len(saved_actions['two_stage_fallback']) == 1
                        assert saved_actions['two_stage_fallback'][0]['name'] == "kairon_two_stage_fallback"
                        assert saved_actions['two_stage_fallback'][0]['text_recommendations'] == \
                               {'count': 0, 'use_intent_ranking': True}
                        assert saved_actions['two_stage_fallback'][0]['trigger_rules'] == \
                               [{'text': 'Hi', 'payload': 'greet', 'is_dynamic_msg': False}]
                        assert saved_actions['two_stage_fallback'][0]['fallback_message'] \
                               == "I could not understand you! Did you mean any of the suggestions below? " \
                                  "Or else please rephrase your question."
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    async def test_load_action_configurations_with_two_stage_fallback(self):
        processor = MongoProcessor()
        saved_actions = processor.load_action_configurations('test_validate_and_prepare_data_all_actions')
        assert len(saved_actions['two_stage_fallback']) == 1
        two_stage_fallback_action = saved_actions['two_stage_fallback'][0]
        assert two_stage_fallback_action['name'] == "kairon_two_stage_fallback"
        assert two_stage_fallback_action['text_recommendations'] == {'count': 0, 'use_intent_ranking': True}
        assert two_stage_fallback_action['trigger_rules'] == [{'text': 'Hi', 'payload': 'greet',
                                                               'is_dynamic_msg': False}]
        assert two_stage_fallback_action['fallback_message'] \
               == "I could not understand you! Did you mean any of the suggestions below? " \
                  "Or else please rephrase your question."

    def test_save_component_properties_all(self):
        config = {"nlu_epochs": 200,
                  "response_epochs": 300,
                  "ted_epochs": 400,
                  "nlu_confidence_threshold": 0.6,
                  "action_fallback": "action_default_fallback"}
        Responses(name='utter_default', bot='test_all', user='test',
                  text=ResponseText(text='Sorry I didnt get that. Can you rephrase?')).save()
        processor = MongoProcessor()
        processor.save_component_properties(config, 'test_all', 'test')
        config = processor.load_config('test_all')
        nlu = next((comp for comp in config['pipeline'] if comp["name"] == "DIETClassifier"), None)
        assert nlu['name'] == 'DIETClassifier'
        assert nlu['epochs'] == 200
        response = next((comp for comp in config['pipeline'] if comp["name"] == "ResponseSelector"), None)
        assert response['name'] == 'ResponseSelector'
        assert response['epochs'] == 300
        action_fallback = next((comp for comp in config['policies'] if comp["name"] == "TEDPolicy"), None)
        assert action_fallback['name'] == 'TEDPolicy'
        assert action_fallback['epochs'] == 400
        nlu_fallback = next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        assert nlu_fallback['name'] == 'FallbackClassifier'
        assert nlu_fallback['threshold'] == 0.6
        rule_policy = next((comp for comp in config['policies'] if "RulePolicy" in comp["name"]), None)
        assert len(rule_policy) == 5
        assert rule_policy['core_fallback_action_name'] == 'action_default_fallback'
        assert rule_policy['core_fallback_threshold'] == 0.3
        expected = {'recipe': 'default.v1', 'language': 'en',
                    'pipeline': [{'name': 'WhitespaceTokenizer'}, {'name': 'RegexEntityExtractor'},
                                 {'model_name': 'bert', 'from_pt': True,
                                  'model_weights': 'google/bert_uncased_L-2_H-128_A-2',
                                  'name': 'kairon.shared.nlu.featurizer.lm_featurizer.LanguageModelFeaturizer'},
                                 {'name': 'LexicalSyntacticFeaturizer'},
                                 {'name': 'CountVectorsFeaturizer'},
                                 {'analyzer': 'char_wb', 'max_ngram': 4, 'min_ngram': 1,
                                  'name': 'CountVectorsFeaturizer'},
                                 {'epochs': 200, 'name': 'DIETClassifier'},
                                 {'name': 'FallbackClassifier', 'threshold': 0.6},
                                 {'name': 'EntitySynonymMapper'},
                                 {'epochs': 300, 'name': 'ResponseSelector'}],
                    'policies': [{'name': 'MemoizationPolicy'}, {'epochs': 400, 'max_history': 5, 'name': 'TEDPolicy'},
                                 {'core_fallback_action_name': 'action_default_fallback',
                                  'core_fallback_threshold': 0.3, 'enable_fallback_prediction': True,
                                  'max_history': 5,
                                  'name': 'RulePolicy'}]}
        assert not DeepDiff(config, expected, ignore_order=True)

    def test_get_config_properties(self):
        expected = {'nlu_confidence_threshold': 0.6,
                    'action_fallback_threshold': 0.3,
                    'action_fallback': 'action_default_fallback',
                    'ted_epochs': 400,
                    'nlu_epochs': 200,
                    'response_epochs': 300}
        processor = MongoProcessor()
        config = processor.list_epoch_and_fallback_config('test_all')
        assert config == expected

    def test_save_component_properties_action_fallback_threshold_greater(self):
        config = {"nlu_epochs": 200,
                  "response_epochs": 300,
                  "ted_epochs": 400,
                  "nlu_confidence_threshold": 0.6,
                  "action_fallback_threshold": 0.7,
                  "action_fallback": "action_default_fallback"}
        processor = MongoProcessor()
        with pytest.raises(AppException,
                           match='Action fallback threshold should always be smaller than nlu fallback threshold'):
            processor.save_component_properties(config, 'test_all', 'test')

    def test_save_component_properties_action_fallback(self):
        config = {"nlu_epochs": 200,
                  "response_epochs": 300,
                  "ted_epochs": 400,
                  "nlu_confidence_threshold": 0.6,
                  "action_fallback_threshold": 0.6,
                  "action_fallback": "action_default_fallback"}
        processor = MongoProcessor()
        processor.save_component_properties(config, 'test_all', 'test')
        config = processor.load_config('test_all')
        nlu = next((comp for comp in config['pipeline'] if comp["name"] == "DIETClassifier"), None)
        assert nlu['name'] == 'DIETClassifier'
        assert nlu['epochs'] == 200
        response = next((comp for comp in config['pipeline'] if comp["name"] == "ResponseSelector"), None)
        assert response['name'] == 'ResponseSelector'
        assert response['epochs'] == 300
        action_fallback = next((comp for comp in config['policies'] if comp["name"] == "TEDPolicy"), None)
        assert action_fallback['name'] == 'TEDPolicy'
        assert action_fallback['epochs'] == 400
        nlu_fallback = next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        assert nlu_fallback['name'] == 'FallbackClassifier'
        assert nlu_fallback['threshold'] == 0.6
        rule_policy = next((comp for comp in config['policies'] if "RulePolicy" in comp["name"]), None)
        assert len(rule_policy) == 5
        assert rule_policy['core_fallback_action_name'] == 'action_default_fallback'
        assert rule_policy['core_fallback_threshold'] == 0.6

    def test_get_config_properties_action_fallback(self):
        expected = {'nlu_confidence_threshold': 0.6,
                    'action_fallback_threshold': 0.6,
                    'action_fallback': 'action_default_fallback',
                    'ted_epochs': 400,
                    'nlu_epochs': 200,
                    'response_epochs': 300}
        processor = MongoProcessor()
        config = processor.list_epoch_and_fallback_config('test_all')
        assert config == expected

    def test_save_component_properties_epoch_only(self):
        config = {"nlu_epochs": 200,
                  "response_epochs": 300,
                  "ted_epochs": 400}
        processor = MongoProcessor()
        processor.save_component_properties(config, 'test_epoch_only', 'test')
        config = processor.load_config('test_epoch_only')
        nlu = next((comp for comp in config['pipeline'] if comp["name"] == "DIETClassifier"), None)
        assert nlu['name'] == 'DIETClassifier'
        assert nlu['epochs'] == 200
        response = next((comp for comp in config['pipeline'] if comp["name"] == "ResponseSelector"), None)
        assert response['name'] == 'ResponseSelector'
        assert response['epochs'] == 300
        ted = next((comp for comp in config['policies'] if comp["name"] == "TEDPolicy"), None)
        assert ted['name'] == 'TEDPolicy'
        assert ted['epochs'] == 400
        expected = {'recipe': 'default.v1', 'language': 'en',
                    'pipeline': [{'name': 'WhitespaceTokenizer'}, {'name': 'RegexEntityExtractor'},
                                 {'model_name': 'bert', 'from_pt': True,
                                  'model_weights': 'google/bert_uncased_L-2_H-128_A-2',
                                  'name': 'kairon.shared.nlu.featurizer.lm_featurizer.LanguageModelFeaturizer'},
                                 {'name': 'LexicalSyntacticFeaturizer'},
                                 {'name': 'CountVectorsFeaturizer'},
                                 {'analyzer': 'char_wb', 'max_ngram': 4, 'min_ngram': 1,
                                  'name': 'CountVectorsFeaturizer'},
                                 {'epochs': 200, 'name': 'DIETClassifier'},
                                 {'name': 'EntitySynonymMapper'},
                                 {'name': 'FallbackClassifier', 'threshold': 0.7},
                                 {'epochs': 300, 'name': 'ResponseSelector'}],
                    'policies': [{'name': 'MemoizationPolicy'}, {'epochs': 400, 'max_history': 5, 'name': 'TEDPolicy'},
                                 {'core_fallback_action_name': 'action_default_fallback',
                                  'core_fallback_threshold': 0.5, 'enable_fallback_prediction': True,
                                  'max_history': 5,
                                  'name': 'RulePolicy'}]}
        assert not DeepDiff(config, expected, ignore_order=True)

    def test_get_config_properties_epoch_only(self):
        expected = {'nlu_confidence_threshold': 0.7, 'action_fallback': 'action_default_fallback',
                    'action_fallback_threshold': 0.5, 'ted_epochs': 400, 'nlu_epochs': 200, 'response_epochs': 300}
        processor = MongoProcessor()
        config = processor.list_epoch_and_fallback_config('test_epoch_only')
        assert config == expected

    def test_save_component_properties_empty(self, monkeypatch):
        monkeypatch.setitem(Utility.environment["model"]["train"], "default_model_training_config_path",
                            "./tests/testing_data/kairon-default.yml")
        processor = MongoProcessor()
        with pytest.raises(AppException) as e:
            processor.save_component_properties({}, 'test_properties_empty', 'test')
        assert str(e).__contains__('At least one field is required')
        config = processor.load_config('test_properties_empty')
        assert config == Utility.read_yaml('./tests/testing_data/kairon-default.yml')
        nlu = next((comp for comp in config['pipeline'] if comp["name"] == "DIETClassifier"), None)
        assert nlu['name'] == 'DIETClassifier'
        assert nlu['epochs'] == 5
        response = next((comp for comp in config['pipeline'] if comp["name"] == "ResponseSelector"), None)
        assert response['name'] == 'ResponseSelector'
        assert response['epochs'] == 5
        ted = next((comp for comp in config['policies'] if comp["name"] == "TEDPolicy"), None)
        assert ted['name'] == 'TEDPolicy'
        assert ted['epochs'] == 5

    def test_get_config_properties_fallback_not_set(self):
        expected = {'nlu_confidence_threshold': 0.7, 'action_fallback': 'action_default_fallback',
                    'action_fallback_threshold': 0.5, 'ted_epochs': 10, 'nlu_epochs': 5, 'response_epochs': 10}
        processor = MongoProcessor()
        config = processor.list_epoch_and_fallback_config('test_fallback_not_set')
        assert config == expected

    def test_list_epochs_for_components_not_present(self):
        configs = Configs._from_son(
            read_config_file("./tests/testing_data/kairon-default.yml")
        ).to_mongo().to_dict()
        del configs['pipeline'][4]
        del configs['pipeline'][6]
        del configs['policies'][1]
        processor = MongoProcessor()
        processor.save_config(configs, 'test_list_component_not_exists', 'test')

        expected = {'nlu_confidence_threshold': 0.7, 'action_fallback': 'action_default_fallback',
                    'action_fallback_threshold': 0.5, 'ted_epochs': None, 'nlu_epochs': 5, 'response_epochs': 5}
        processor = MongoProcessor()
        actual = processor.list_epoch_and_fallback_config('test_list_component_not_exists')
        assert actual == expected

    def test_save_component_properties_component_not_exists(self):
        configs = Configs._from_son(
            read_config_file("./tests/testing_data/kairon-default.yml")
        ).to_mongo().to_dict()
        del configs['pipeline'][5]
        del configs['pipeline'][7]
        del configs['policies'][1]
        processor = MongoProcessor()
        processor.save_config(configs, 'test_component_not_exists', 'test')

        config = {"nlu_epochs": 10,
                  "response_epochs": 10,
                  "ted_epochs": 10}
        processor = MongoProcessor()
        processor.save_component_properties(config, 'test_component_not_exists', 'test')
        config = processor.load_config('test_component_not_exists')
        diet = next((comp for comp in config['pipeline'] if comp["name"] == "DIETClassifier"), None)
        assert diet['name'] == 'DIETClassifier'
        assert diet['epochs'] == 10
        response = next((comp for comp in config['pipeline'] if comp["name"] == "ResponseSelector"), None)
        assert response['name'] == 'ResponseSelector'
        assert response['epochs'] == 10
        ted = next((comp for comp in config['policies'] if comp["name"] == "TEDPolicy"), None)
        assert ted['name'] == 'TEDPolicy'
        assert ted['epochs'] == 10

    def test_save_component_fallback_not_configured(self):
        Actions(name='action_say_bye', bot='test_fallback_not_configured', user='test').save()
        configs = Configs._from_son(
            read_config_file("./tests/testing_data/kairon-default.yml")
        ).to_mongo().to_dict()
        del configs['pipeline'][6]
        del configs['policies'][2]
        processor = MongoProcessor()
        processor.save_config(configs, 'test_fallback_not_configured', 'test')

        config = {'nlu_confidence_threshold': 0.8,
                  'action_fallback': 'action_say_bye'}
        processor = MongoProcessor()
        processor.save_component_properties(config, 'test_fallback_not_configured', 'test')
        config = processor.load_config('test_fallback_not_configured')
        expected = {'recipe': 'default.v1', 'language': 'en',
                    'pipeline': [{'name': 'WhitespaceTokenizer'}, {'name': 'RegexEntityExtractor'},
                                 {'model_name': 'bert', 'from_pt': True,
                                  'model_weights': 'google/bert_uncased_L-2_H-128_A-2',
                                  'name': 'kairon.shared.nlu.featurizer.lm_featurizer.LanguageModelFeaturizer'},
                                 {'name': 'LexicalSyntacticFeaturizer'},
                                 {'name': 'CountVectorsFeaturizer'},
                                 {'epochs': 5, 'name': 'DIETClassifier'},
                                 {'name': 'FallbackClassifier', 'threshold': 0.8},
                                 {'epochs': 5, 'name': 'ResponseSelector'}],
                    'policies': [{'name': 'MemoizationPolicy'}, {'epochs': 5, 'name': 'TEDPolicy'},
                                 {'name': 'RulePolicy', 'max_history': 5, 'core_fallback_action_name': 'action_say_bye',
                                  'core_fallback_threshold': 0.3}]}
        assert not DeepDiff(config, expected, ignore_order=True)

    def test_save_component_properties_nlu_fallback_only(self):
        nlu_fallback = {"nlu_confidence_threshold": 0.75}
        processor = MongoProcessor()
        processor.save_component_properties(nlu_fallback, 'test_nlu_fallback_only', 'test')
        config = processor.load_config('test_nlu_fallback_only')
        nlu_fallback = next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        assert nlu_fallback['name'] == 'FallbackClassifier'
        assert nlu_fallback['threshold'] == 0.75
        rule_policy = next((comp for comp in config['policies'] if "RulePolicy" in comp["name"]), None)
        assert len(rule_policy) == 5
        expected = {'recipe': 'default.v1', 'language': 'en',
                    'pipeline': [{'name': 'WhitespaceTokenizer'}, {'name': 'RegexEntityExtractor'},
                                 {'model_name': 'bert', 'from_pt': True,
                                  'model_weights': 'google/bert_uncased_L-2_H-128_A-2',
                                  'name': 'kairon.shared.nlu.featurizer.lm_featurizer.LanguageModelFeaturizer'},
                                 {'name': 'LexicalSyntacticFeaturizer'},
                                 {'name': 'CountVectorsFeaturizer'},
                                 {'analyzer': 'char_wb', 'max_ngram': 4, 'min_ngram': 1,
                                  'name': 'CountVectorsFeaturizer'},
                                 {'epochs': 5, 'name': 'DIETClassifier'},
                                 {'name': 'FallbackClassifier', 'threshold': 0.75},
                                 {'name': 'EntitySynonymMapper'},
                                 {'epochs': 10, 'name': 'ResponseSelector'}],
                    'policies': [{'name': 'MemoizationPolicy'}, {'epochs': 10, 'max_history': 5, 'name': 'TEDPolicy'},
                                 {'core_fallback_action_name': 'action_default_fallback',
                                  'core_fallback_threshold': 0.5, 'enable_fallback_prediction': True,
                                  'max_history': 5,
                                  'name': 'RulePolicy'}]}
        assert not DeepDiff(config, expected)

    def test_save_component_properties_all_nlu_fallback_update_threshold(self):
        nlu_fallback = {"nlu_confidence_threshold": 0.7}
        processor = MongoProcessor()
        processor.save_component_properties(nlu_fallback, 'test_nlu_fallback_only', 'test')
        config = processor.load_config('test_nlu_fallback_only')
        nlu_fallback = next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        assert nlu_fallback['name'] == 'FallbackClassifier'
        assert nlu_fallback['threshold'] == 0.7
        rule_policy = next((comp for comp in config['policies'] if "RulePolicy" in comp["name"]), None)
        assert len(rule_policy) == 5

    def test_save_component_properties_action_fallback_only(self):
        nlu_fallback = {'action_fallback': 'action_say_bye'}
        Actions(name='action_say_bye', bot='test_action_fallback_only', user='test').save()
        processor = MongoProcessor()
        processor.save_component_properties(nlu_fallback, 'test_action_fallback_only', 'test')
        config = processor.load_config('test_action_fallback_only')
        assert next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        rule_policy = next((comp for comp in config['policies'] if "RulePolicy" in comp["name"]), None)
        assert len(rule_policy) == 5
        assert rule_policy['core_fallback_action_name'] == 'action_say_bye'
        assert rule_policy['core_fallback_threshold'] == 0.3
        expected = {'recipe': 'default.v1', 'language': 'en',
                    'pipeline': [{'name': 'WhitespaceTokenizer'}, {'name': 'RegexEntityExtractor'},
                                 {'model_name': 'bert', 'from_pt': True,
                                  'model_weights': 'google/bert_uncased_L-2_H-128_A-2',
                                  'name': 'kairon.shared.nlu.featurizer.lm_featurizer.LanguageModelFeaturizer'},
                                 {'name': 'LexicalSyntacticFeaturizer'},
                                 {'name': 'CountVectorsFeaturizer'},
                                 {'analyzer': 'char_wb', 'max_ngram': 4, 'min_ngram': 1,
                                  'name': 'CountVectorsFeaturizer'},
                                 {'epochs': 5, 'name': 'DIETClassifier'},
                                 {'name': 'EntitySynonymMapper'},
                                 {'name': 'FallbackClassifier', 'threshold': 0.7},
                                 {'epochs': 10, 'name': 'ResponseSelector'}],
                    'policies': [{'name': 'MemoizationPolicy'}, {'epochs': 10, 'max_history': 5, 'name': 'TEDPolicy'},
                                 {'core_fallback_action_name': 'action_say_bye', 'core_fallback_threshold': 0.3,
                                  'enable_fallback_prediction': True, 'max_history': 5, 'name': 'RulePolicy'}]}
        assert not DeepDiff(config, expected, ignore_order=True)

    def test_save_component_properties_all_action_fallback_update(self):
        nlu_fallback = {'action_fallback': 'action_say_bye_bye'}
        Actions(name='action_say_bye_bye', bot='test_action_fallback_only', user='test').save()
        processor = MongoProcessor()
        processor.save_component_properties(nlu_fallback, 'test_action_fallback_only', 'test')
        config = processor.load_config('test_action_fallback_only')
        assert next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        rule_policy = next((comp for comp in config['policies'] if "RulePolicy" in comp["name"]), None)
        assert len(rule_policy) == 5
        assert rule_policy['core_fallback_action_name'] == 'action_say_bye_bye'
        assert rule_policy['core_fallback_threshold'] == 0.3

    def test_save_component_properties_all_action_fallback_action_not_exists(self):
        nlu_fallback = {'action_fallback': 'action_say_hello'}
        processor = MongoProcessor()
        with pytest.raises(AppException) as e:
            processor.save_component_properties(nlu_fallback, 'test_action_fallback_only', 'test')
        assert str(e).__contains__("Action fallback action_say_hello does not exists")
        config = processor.load_config('test_action_fallback_only')
        assert next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        rule_policy = next((comp for comp in config['policies'] if "RulePolicy" in comp["name"]), None)
        assert len(rule_policy) == 5
        assert rule_policy['core_fallback_action_name'] == 'action_say_bye_bye'
        assert rule_policy['core_fallback_threshold'] == 0.3

    def test_save_component_properties_all_action_fallback_utter_default_not_set(self):
        nlu_fallback = {'action_fallback': 'action_default_fallback'}
        processor = MongoProcessor()
        Responses.objects(name="utter_default", bot="test_action_fallback_only").delete()
        with pytest.raises(AppException) as e:
            processor.save_component_properties(nlu_fallback, 'test_action_fallback_only', 'test')
        assert str(e).__contains__("Utterance utter_default not defined")
        config = processor.load_config('test_action_fallback_only')
        assert next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        rule_policy = next((comp for comp in config['policies'] if "RulePolicy" in comp["name"]), None)
        assert len(rule_policy) == 5
        assert rule_policy['core_fallback_action_name'] == 'action_say_bye_bye'
        assert rule_policy['core_fallback_threshold'] == 0.3

    def test_save_component_properties_all_action_fallback_utter_default_set(self):
        nlu_fallback = {'action_fallback': 'action_default_fallback'}
        Responses(name='utter_default', bot='test_action_fallback_only', user='test',
                  text={'text': 'Sorry I didnt get that. Can you rephrase?'}).save()
        processor = MongoProcessor()
        processor.save_component_properties(nlu_fallback, 'test_action_fallback_only', 'test')
        config = processor.load_config('test_action_fallback_only')
        assert next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        rule_policy = next((comp for comp in config['policies'] if "RulePolicy" in comp["name"]), None)
        assert len(rule_policy) == 5
        assert rule_policy['core_fallback_action_name'] == 'action_default_fallback'
        assert rule_policy['core_fallback_threshold'] == 0.3

    def test_add_synonym(self):
        processor = MongoProcessor()
        bot = 'add_synonym'
        user = 'test_user'
        processor.add_synonym("bot", bot, user)

        with pytest.raises(AppException, match="Synonym already exists!"):
            processor.add_synonym("bot", bot, user)

        with pytest.raises(ValidationError, match="Synonym cannot be empty or blank spaces"):
            processor.add_synonym(" ", bot, user)

        with pytest.raises(TypeError):
            processor.add_synonym(None, bot, user)

    def test_add_synonym_single_value(self):
        processor = MongoProcessor()
        bot = 'add_synonym_single_value'
        user = 'test_user'
        processor.add_synonym("bot", bot, user)
        processor.add_synonym_value("exp", "bot", bot, user)
        syn = list(EntitySynonyms.objects(name__exact='bot', bot=bot, user=user))
        assert syn[0]['name'] == "bot"
        assert syn[0]['value'] == "exp"

        with pytest.raises(AppException, match="Synonym value already exists"):
            processor.add_synonym_value(
                "exp", "bot", bot, user)

        with pytest.raises(ValidationError, match="Synonym name and value cannot be empty or blank spaces"):
            processor.add_synonym_value(
                " ", "bot", bot, user)

        with pytest.raises(TypeError):
            processor.add_synonym_value(
                None, "bot", bot, user)

        with pytest.raises(ValidationError, match="Synonym name and value cannot be empty or blank spaces"):
            processor.add_synonym_value(
                "exp", " ", bot, user)

        with pytest.raises(TypeError):
            processor.add_synonym_value(
                "exp", None, bot, user)

    def test_add__and_get_synonym(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        processor.add_synonym("bot", bot, user)
        processor.add_synonym_values(
            {"name": "bot", "value": ["exp"]}, bot, user)
        syn = list(EntitySynonyms.objects(name__iexact='bot', bot=bot, user=user))
        assert syn[0]['name'] == "bot"
        assert syn[0]['value'] == "exp"

    def test_get_specific_synonym(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        response = list(processor.get_synonym_values("bot", bot))
        assert response[0]["value"] == "exp"

    def test_add_duplicate_synonym(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        with pytest.raises(AppException) as exp:
            processor.add_synonym_values({"name": "bot", "value": ["exp"]}, bot, user)
        assert str(exp.value) == "Synonym value already exists"

    def test_edit_specific_synonym(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        response = list(processor.get_synonym_values("bot", bot))
        processor.edit_synonym(response[0]["_id"], "exp2", "bot", bot, user)
        response = list(processor.get_synonym_values("bot", bot))
        assert response[0]["value"] == "exp2"

    def test_edit_synonym_duplicate(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        response = list(processor.get_synonym_values("bot", bot))
        with pytest.raises(AppException):
            processor.edit_synonym(response[0]["_id"], "exp2", "bot", bot, user)

    def test_edit_synonym_unavailable(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        response = list(processor.get_synonym_values("bot", bot))
        with pytest.raises(AppException):
            processor.edit_synonym(response[0]["_id"], "exp3", "bottt", bot, user)

    def test_add_delete_synonym_value(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        processor.add_synonym_values({"name": "bot", "value": ["exp"]}, bot, user)
        response = list(processor.get_synonym_values("bot", bot))
        assert len(response) == 2
        processor.delete_synonym_value("bot", response[0]["_id"], bot, user=user)
        response = list(processor.get_synonym_values("bot", bot))
        assert len(response) == 1

    def test_delete_synonym_value_empty(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_synonym_value(" ", "df", "ff")

    def test_delete_non_existent_synonym(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_synonym_value(value_id="0123456789ab0123456789ab", synonym_name="df", bot="ff")

    def test_delete_synonym_name(self):
        processor = MongoProcessor()
        bot = 'test_delete_synonym'
        synonym_id = processor.add_synonym("bot", bot, "test")
        response = list(processor.fetch_synonyms(bot))
        assert len(response) == 1

        processor.add_synonym_value("test", "bot", bot, "test")
        response = list(processor.get_synonym_values("bot", bot))
        assert len(response) == 1

        processor.delete_synonym(synonym_id, bot, user="test")
        response = list(processor.fetch_synonyms(bot))
        assert len(response) == 0

        response = list(processor.get_synonym_values("bot", bot))
        assert len(response) == 0

    def test_delete_synonym_name_empty(self):
        processor = MongoProcessor()
        with pytest.raises(ValidationError):
            processor.delete_synonym(" ", "df")

    def test_delete_non_existent_synonym_name(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_synonym(id="0123456789ab0123456789ab", bot="df")

    def test_add_empty_synonym(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        with pytest.raises(AppException) as exp:
            processor.add_synonym_values({"synonym": "", "value": ["exp"]}, bot, user)
        assert str(exp.value) == "Synonym name cannot be an empty!"

    def test_add_synonym_with_empty_value_list(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        with pytest.raises(AppException) as exp:
            processor.add_synonym_values({"name": "bot", "value": []}, bot, user)
        assert str(exp.value) == "Synonym value cannot be an empty!"

    def test_add_synonym_with_empty_element_in_value_list(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        with pytest.raises(AppException) as exp:
            processor.add_synonym_values({"name": "bot", "value": ["df", '']}, bot, user)
        assert str(exp.value) == "Synonym value cannot be an empty!"

    def test_add_utterance(self):
        processor = MongoProcessor()
        processor.add_utterance_name('test_add', 'test', 'testUser')

    def test_add_utterance_already_exists(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Utterance exists'):
            processor.add_utterance_name('test_add', 'test', 'testUser', raise_error_if_exists=True)

    def test_add_utterance_empty(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Name cannot be empty'):
            processor.add_utterance_name(' ', 'test', 'testUser', True)

    def test_utterance_data_object(self):
        with pytest.raises(ValidationError, match='Utterance Name cannot be empty or blank spaces'):
            Utterances(name=' ', bot='test', user='user').save()

    def test_add_utterance_already_exists_no_exc(self):
        processor = MongoProcessor()
        assert not processor.add_utterance_name('test_add', 'test', 'testUser')

    def test_get_utterance(self):
        processor = MongoProcessor()
        actual = list(processor.get_utterances('test'))
        assert len(actual) == 28

    def test_delete_utterance_name_does_not_exists(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Utterance not found'):
            processor.delete_utterance_name('test_add_1', 'test', raise_exc=True)

    def test_delete_utterance_name_does_not_exists_no_exc(self):
        processor = MongoProcessor()
        processor.delete_utterance_name('test_add_1', 'test')

    def test_delete_utterance_name(self):
        processor = MongoProcessor()
        processor.delete_utterance_name('test_add', 'test', user="test")

    def test_get_bot_settings_not_added(self):
        processor = MongoProcessor()
        settings = processor.get_bot_settings('not_created', 'test')
        assert not settings.ignore_utterances
        assert not settings.force_import
        assert settings.status
        assert settings.timestamp
        assert settings.user
        assert settings.bot
        assert settings.llm_settings.to_mongo().to_dict() == {'enable_faq': False, 'provider': 'openai'}

    def test_get_bot_settings(self):
        processor = MongoProcessor()
        settings = BotSettings.objects(bot='not_created').get()
        settings.ignore_utterances = True
        settings.force_import = True
        settings.save()
        fresh_settings = processor.get_bot_settings('not_created', 'test')
        assert fresh_settings.ignore_utterances
        assert fresh_settings.force_import
        assert fresh_settings.status
        assert fresh_settings.timestamp
        assert fresh_settings.user
        assert fresh_settings.bot
        assert settings.llm_settings.to_mongo().to_dict() == {'enable_faq': False, 'provider': 'openai'}

    def test_save_bot_settings_error(self):
        with pytest.raises(ValidationError, match="refresh_token_expiry must be greater than chat_token_expiry!"):
            BotSettings(chat_token_expiry=60, refresh_token_expiry=60, bot="test", user="test").save()

    def test_save_chat_client_config_not_exists(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {'name': 'test', 'account': 1, 'user': 'user@integration.com', 'status': True}

        def _mock_list_bot_accessors(*args, **kwargs):
            yield {'accessor_email': 'user@integration.com'}

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        monkeypatch.setattr(AccountProcessor, 'list_bot_accessors', _mock_list_bot_accessors)
        processor = MongoProcessor()
        config_path = "./template/chat-client/default-config.json"
        config = json.load(open(config_path))
        processor.save_chat_client_config(config, 'test', 'testUser')
        saved_config = ChatClientConfig.objects(bot='test').get()
        assert saved_config.config == config
        assert saved_config.user == 'testUser'
        assert saved_config.timestamp
        assert saved_config.status

    def test_save_chat_client_config(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {'name': 'test', 'account': 1, 'user': 'user@integration.com', 'status': True}

        def _mock_list_bot_accessors(*args, **kwargs):
            yield {'accessor_email': 'user@integration.com'}

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        monkeypatch.setattr(AccountProcessor, 'list_bot_accessors', _mock_list_bot_accessors)
        processor = MongoProcessor()
        config_path = "./template/chat-client/default-config.json"
        config = json.load(open(config_path))
        config['headers'] = {}
        config['headers']['authorization'] = 'Bearer eygbsbvuyfhbsfinlasfmishfiufnasfmsnf'
        config['headers']['X-USER'] = 'user@integration.com'
        processor.save_chat_client_config(config, 'test', 'testUser')
        saved_config = ChatClientConfig.objects(bot='test').get()
        assert saved_config.config == config
        assert saved_config.status
        assert saved_config.white_listed_domain == ["*"]

    def test_get_chat_client_config_not_exists(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True,
                "metadata": {"source_bot_id": None}
            }

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        config_path = "./template/chat-client/default-config.json"
        expected_config = json.load(open(config_path))
        actual_config = processor.get_chat_client_config('test_bot', 'user@integration.com')
        assert actual_config.config['headers']['authorization']['access_token']
        assert actual_config.config['headers']['authorization']['token_type'] == 'Bearer'
        assert actual_config.config['headers']['authorization']['refresh_token']
        assert actual_config.config['headers']['authorization']['access_token_ttl'] == 30
        assert actual_config.config['headers']['authorization']['refresh_token_ttl'] == 60
        ate = actual_config.config['headers']['authorization']['access_token_expiry']
        rte = actual_config.config['headers']['authorization']['refresh_token_expiry']
        ate_minutes = round((utc_from_timestamp(ate) - utc_now()).total_seconds() / 60)
        rte_minutes = round((utc_from_timestamp(rte) - utc_now()).total_seconds() / 60)
        assert 31 >= ate_minutes >= 29
        assert 61 >= rte_minutes >= 59
        assert actual_config.config['headers']['X-USER'] == 'user@integration.com'
        assert actual_config.config['api_server_host_url']
        del actual_config.config['api_server_host_url']
        assert actual_config.config['nudge_server_url']
        del actual_config.config['nudge_server_url']
        assert 'chat_server_base_url' in actual_config.config
        actual_config.config.pop('chat_server_base_url')
        actual_config.config.pop('live_agent_socket_url')
        headers = actual_config.config.pop('headers')
        expected_config['multilingual'] = {'enable': False, 'bots': []}
        expected_config['live_agent_enabled'] = True
        assert expected_config == actual_config.config

        primary_token_claims = Utility.decode_limited_access_token(headers['authorization']['access_token'])
        iat = datetime.fromtimestamp(primary_token_claims.get('iat'), tz=timezone.utc)
        claims = Utility.decode_limited_access_token(headers['authorization']['refresh_token'])
        assert claims['iat'] == primary_token_claims.get('iat')
        refresh_token_expiry = datetime.fromtimestamp(claims['exp'], tz=timezone.utc)
        assert round((refresh_token_expiry - iat).total_seconds() / 60) == 60
        del claims['iat']
        del claims['exp']
        assert claims == {'ttl': 30, 'bot': 'test_bot', 'sub': 'user@integration.com', 'type': 'refresh',
                          'role': 'tester', 'account': 2,
                          'primary-token-type': TOKEN_TYPE.DYNAMIC.value,
                          'primary-token-role': 'chat', 'primary-token-access-limit': [
                '/api/bot/.+/chat', '/api/bot/.+/agent/live/.+', '/api/bot/.+/conversation',
                '/api/bot/.+/metric/user/logs/user_metrics'
            ], 'access-limit': ['/api/auth/.+/token/refresh']}

    def test_get_chat_client_config_live_agent_enabled_false(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {
                "_id": "9876543210", 'name': 'test_bot', 'account': 2, 'user': 'user@integration.com',
                'status': True,
                "metadata": {"source_bot_id": None}
            }
        def _mock_is_live_agent_service_available(*args, **kwargs):
            return False
        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        monkeypatch.setattr(LiveAgentHandler, 'is_live_agent_service_available', _mock_is_live_agent_service_available)
        processor = MongoProcessor()
        actual_config = processor.get_chat_client_config('test_bot', 'user@integration.com')
        assert actual_config.config['live_agent_enabled'] == False


    def test_save_chat_client_config_without_whitelisted_domain(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {'name': 'test', 'account': 1, 'user': 'user@integration.com', 'status': True}

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        config_path = "./template/chat-client/default-config.json"
        config = json.load(open(config_path))
        config['headers'] = {}
        config['headers']['authorization'] = 'Bearer eygbsbvuyfhbsfinlasfmishfiufnasfmsnf'
        config['headers']['X-USER'] = 'user@integration.com'
        config.pop("whitelist")
        processor.save_chat_client_config(config, 'test', 'testUser')
        saved_config = ChatClientConfig.objects(bot='test').get()
        assert saved_config.config == config
        assert saved_config.status
        assert saved_config.white_listed_domain == ["*"]

    def test_save_chat_client_config_valid_white_list(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {'name': 'test', 'account': 1, 'user': 'user@integration.com', 'status': True}

        def _mock_list_bot_accessors(*args, **kwargs):
            yield {'accessor_email': 'user@integration.com'}

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        monkeypatch.setattr(AccountProcessor, 'list_bot_accessors', _mock_list_bot_accessors)
        processor = MongoProcessor()
        config_path = "./template/chat-client/default-config.json"
        config = json.load(open(config_path))
        config['headers'] = {}
        config['headers']['authorization'] = 'Bearer eygbsbvuyfhbsfinlasfmishfiufnasfmsnf'
        config['headers']['X-USER'] = 'user@integration.com'
        config['whitelist'] = ["kairon.digite.com", "kairon-api.digite.com"]
        processor.save_chat_client_config(config, 'test', 'testUser')
        saved_config = ChatClientConfig.objects(bot='test').get()
        assert saved_config.config == config
        assert saved_config.status
        assert saved_config.white_listed_domain == ["kairon.digite.com", "kairon-api.digite.com"]

    def test_validate_white_listed_domain_success(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {'name': 'test', 'account': 1, 'user': 'user@integration.com', 'status': True}

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/",
            "headers": Headers({
                'host': 'kairon.digite.com',
                'accept': 'application/json',
                'referer': 'https://kairon.digite.com'
            }).raw,
            "server": ("kairon.digite.com", 443),
        }

        request = Request(scope=scope)
        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        config_path = "./template/chat-client/default-config.json"
        config = json.load(open(config_path))
        config['headers'] = {}
        config['headers']['authorization'] = 'Bearer eygbsbvuyfhbsfinlasfmishfiufnasfmsnf'
        config['headers']['X-USER'] = 'user@integration.com'
        config['whitelist'] = ["kairon.digite.com", "kairon-api.digite.com"]
        processor.save_chat_client_config(config, 'test', 'testUser')

        fetched_config = processor.get_chat_client_config('test', 'user@integration.com')
        fetched_config = fetched_config.to_mongo().to_dict()
        assert Utility.validate_request(request, fetched_config)

    def test_validate_white_listed_domain_attackers(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {'name': 'test', 'account': 1, 'user': 'user@integration.com', 'status': True}

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/",
            "headers": Headers({
                'host': 'kairon.digite.com',
                'accept': 'application/json',
                'referer': 'http://attackers.com'
            }).raw,
            "server": ("kairon.digite.com", 443),
        }

        request = Request(scope=scope)
        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        config_path = "./template/chat-client/default-config.json"
        config = json.load(open(config_path))
        config['headers'] = {}
        config['headers']['authorization'] = 'Bearer eygbsbvuyfhbsfinlasfmishfiufnasfmsnf'
        config['headers']['X-USER'] = 'user@integration.com'
        config['whitelist'] = ["kairon.digite.com", "kairon-api.digite.com"]
        processor.save_chat_client_config(config, 'test', 'testUser')

        fetched_config = processor.get_chat_client_config('test', 'user@integration.com')
        fetched_config = fetched_config.to_mongo().to_dict()
        assert not Utility.validate_request(request, fetched_config)

    def test_get_chat_client_config(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {'name': 'test', 'account': 1, 'user': 'user@integration.com', 'status': True}

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        processor = MongoProcessor()
        actual_config = processor.get_chat_client_config('test', 'user@integration.com')
        assert actual_config.config['headers']['authorization']
        assert actual_config.config['headers']['X-USER'] == 'user@integration.com'

    def test_get_chat_client_config_default_not_found(self, monkeypatch):
        def _mock_exception(*args, **kwargs):
            raise AppException('Config not found')

        def _mock_bot_info(*args, **kwargs):
            return {'name': 'test', 'account': 1, 'user': 'user@integration.com', 'status': True}

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        monkeypatch.setattr(os.path, 'exists', _mock_exception)
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Config not found'):
            processor.get_chat_client_config('test_bot', 'user@integration.com')

    def test_add__and_get_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        processor.add_regex(
            {"name": "bot", "pattern": "exp"}, bot, user)
        reg = RegexFeatures.objects(name__iexact='bot', bot=bot, user=user).get()
        assert reg['name'] == "bot"
        assert reg['pattern'] == "exp"

    def test_add__duplicate_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        with pytest.raises(AppException) as e:
            processor.add_regex({"name": "bot", "pattern": "f"}, bot=bot, user=user)
        assert str(e).__contains__("Regex name already exists!")

    def test_add__empty_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        with pytest.raises(AppException) as e:
            processor.add_regex({"name": "", "pattern": "f"}, bot=bot, user=user)
        assert str(e).__contains__("Regex name and pattern cannot be empty or blank spaces")

    def test_edit__and_get_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        processor.edit_regex(
            {"name": "bot", "pattern": "exp1"}, bot, user)
        reg = RegexFeatures.objects(name__iexact='bot', bot=bot, user=user).get()
        assert reg['name'] == "bot"
        assert reg['pattern'] == "exp1"

    def test_edit__unavailable_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        with pytest.raises(AppException) as e:
            processor.edit_regex({"name": "bot1", "pattern": "f"}, bot=bot, user=user)
        assert str(e).__contains__("Regex name does not exist!")

    def test_edit__empty_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        with pytest.raises(AppException) as e:
            processor.edit_regex({"name": "bot", "pattern": ""}, bot=bot, user=user)
        assert str(e).__contains__("Regex name and pattern cannot be empty or blank spaces")

    def test_delete__unavailable_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        with pytest.raises(AppException) as e:
            processor.delete_regex("f", bot=bot, user=user)
        assert str(e).__contains__("Regex name does not exist.")

    def test_delete__and_get_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        processor.delete_regex("bot", bot, user)
        with pytest.raises(DoesNotExist):
            RegexFeatures.objects(name__iexact='bot', bot=bot, status=True).get()

    def test_add__invalid_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        with pytest.raises(AppException) as e:
            processor.add_regex({"name": "bot11", "pattern": "[0-9"}, bot=bot, user=user)
        assert str(e).__contains__("invalid regular expression")

    def test_add_lookup(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup_value'
        user = 'test_user'

        processor.add_lookup("number", bot, user)
        processor.add_lookup_value("number", "one", bot, user)

        with pytest.raises(ValidationError, match="Lookup name and value cannot be empty or blank spaces"):
            processor.add_lookup_value("number", " ", bot, user)

        with pytest.raises(TypeError):
            processor.add_lookup_value("number", None, bot, user)

        with pytest.raises(ValidationError, match="Lookup name and value cannot be empty or blank spaces"):
            processor.add_lookup_value("number", "one", bot, user)

        with pytest.raises(ValidationError, match="Lookup name and value cannot be empty or blank spaces"):
            processor.add_lookup_value(" ", "one", bot, user)

        with pytest.raises(TypeError):
            processor.add_lookup_value(None, "one", bot, user)

    def test_add_lookup(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup'
        user = 'test_user'

        processor.add_lookup("number", bot, user)

        with pytest.raises(ValidationError, match="Lookup cannot be empty or blank spaces"):
            processor.add_lookup(" ", bot, user)

        with pytest.raises(TypeError):
            processor.add_lookup(None, bot, user)

        with pytest.raises(AppException, match="Lookup already exists!"):
            processor.add_lookup("number", bot, user)

    def test_add__and_get_lookup_values(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup_values'
        user = 'test_user'
        processor.add_lookup("number", bot, user)
        processor.add_lookup_values(
            {"name": "number", "value": ["one"]}, bot, user)
        table = list(LookupTables.objects(name__iexact='number', bot=bot, user=user))
        assert table[0]['name'] == "number"
        assert table[0]['value'] == "one"

    def test_get_specific_lookup(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup_values'
        response = list(processor.get_lookup_values("number", bot))
        assert response[0]["value"] == "one"

    def test_add_duplicate_lookup(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup_values'
        user = 'test_user'
        with pytest.raises(AppException) as exp:
            processor.add_lookup_values({"name": "number", "value": ["one"]}, bot, user)
        assert str(exp.value) == "Lookup value already exists"

    def test_edit_specific_lookup(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup_values'
        user = 'test_user'
        response = list(processor.get_lookup_values("number", bot))
        processor.edit_lookup_value(response[0]["_id"], "two", "number", bot, user)
        response = list(processor.get_lookup_values("number", bot))
        assert response[0]["value"] == "two"

    def test_edit_lookup_duplicate(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup_values'
        user = 'test_user'
        response = list(processor.get_lookup_values("number", bot))
        with pytest.raises(AppException):
            processor.edit_lookup_value(response[0]["_id"], "two", "number", bot, user)

    def test_edit_lookup_unavailable(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup_values'
        user = 'test_user'
        response = list(processor.get_lookup_values("number", bot))
        with pytest.raises(AppException):
            processor.edit_lookup_value(response[0]["_id"], "exp3", "bottt", bot, user)

    def test_add_delete_lookup_value(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup_values'
        user = 'test_user'
        processor.add_lookup_values({"name": "number", "value": ["one"]}, bot, user)
        response = list(processor.get_lookup_values("number", bot))
        assert len(response) == 2
        processor.delete_lookup_value(response[0]["_id"], "number", bot, user)
        response = list(processor.get_lookup_values("number", bot))
        assert len(response) == 1

    def test_delete_lookup_value_empty(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_lookup_value(" ", "df", "test", "test_user")

    def test_delete_non_existent_lookup(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_lookup_value("0123456789ab0123456789ab", "df", "test", "test_user")

    def test_delete_lookup_name(self):
        processor = MongoProcessor()
        bot = 'test_delete_lookup'
        user = 'test_user'
        lookup_id = processor.add_lookup("bot", bot, user)
        processor.add_lookup_value("bot", "exp", bot, user)
        assert len(list(processor.get_lookups(bot))) == 1
        assert len(list(processor.get_lookup_values("bot", bot))) == 1
        processor.delete_lookup(lookup_id, bot, user)
        response = list(processor.get_lookups(bot))
        assert len(response) == 0
        response = list(processor.get_lookup_values("bot", bot))
        assert len(response) == 0

    def test_delete_lookup_name_empty(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_lookup(" ", "df", "test")

    def test_delete_non_existent_lookup_name(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_lookup("0123456789ab0123456789ab", "df", "test")

    def test_add_empty_lookup(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup_values'
        user = 'test_user'
        with pytest.raises(AppException) as exp:
            processor.add_lookup_values({"name": "", "value": ["exp"]}, bot, user)
        assert str(exp.value) == "Lookup cannot be an empty string"

    def test_add_lookup_with_empty_value_list(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup_values'
        user = 'test_user'
        with pytest.raises(AppException) as exp:
            processor.add_lookup_values({"name": "bot", "value": []}, bot, user)
        assert str(exp.value) == "Lookup value cannot be an empty string"

    def test_add_lookup_with_empty_element_in_value_list(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup_values'
        user = 'test_user'
        processor.add_lookup("bot", bot, user)
        with pytest.raises(AppException) as exp:
            processor.add_lookup_values({"name": "bot", "value": ["df", '']}, bot, user)
        assert str(exp.value) == "Lookup value cannot be an empty string"

    def test_add_slot_mapping_slot_not_added(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        expected_slot = {"slot": "cuisine", 'mapping': {'type': 'from_entity', 'entity': 'name'}}
        with pytest.raises(AppException, match='Slot with name \"cuisine\" not found'):
            processor.add_slot_mapping(expected_slot, bot, user)

    def test_add_slot_with_mapping(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        expected_slot = {"slot": "name", 'mapping': {'type': 'from_intent', 'value': 'user'}}
        processor.add_slot_mapping(expected_slot, bot, user)
        slot = SlotMapping.objects(slot='name', bot=bot, user=user).get()
        assert slot.mapping == {'type': 'from_intent', 'value': 'user'}

    def test_add_slot_with_empty_mapping(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        expected_slot = {"slot": "name", 'mapping': {}}
        with pytest.raises(ValueError, match='At least one mapping is required'):
            processor.add_slot_mapping(expected_slot, bot, user)


    def test_update_slot_with_mapping(self):
        expected_slot = {"name": "age", "type": "float", "influence_conversation": True}
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        processor.add_slot(expected_slot, bot, user, raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='age', bot=bot, user=user).get()
        assert slot['name'] == 'age'
        assert slot['type'] == 'float'
        assert slot['initial_value'] is None
        assert slot['influence_conversation']

        expected_slot = {"slot": "age",
                         'mapping': {'type': 'from_intent', 'intent': ['get_age'], 'entity': 'age', 'value': '18',
                                      "conditions": [{"active_loop": "booking", "requested_slot": "age"}]}}
        processor.add_slot_mapping(expected_slot, bot, user)
        slot = Slots.objects(name__iexact='age', bot=bot, user=user).get()
        assert slot['name'] == 'age'
        assert slot['type'] == 'float'
        assert slot['initial_value'] is None
        assert slot['influence_conversation']
        slot = SlotMapping.objects(slot='age', bot=bot, user=user).get()
        assert slot.mapping == {'type': 'from_intent', 'intent': ['get_age'], 'value': '18',
                                 "conditions": [{"active_loop": "booking", "requested_slot": "age"}]}

    def test_remove_slot_mapping(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        processor.add_slot({"name": "occupation", "type": "text", "influence_conversation": True}, bot, user)
        expected_slot = {"slot": "occupation",
                         'mapping': [{'type': 'from_intent', 'intent': ['get_occupation'], 'value': 'business'},
                                     {'type': 'from_text', 'value': 'engineer',
                                      "conditions": [{"active_loop": "booking", "requested_slot": "engineer"}]},
                                     {'type': 'from_entity', 'entity': 'occupation'},
                                     {'type': 'from_trigger_intent', 'value': 'tester',
                                      'intent': ['get_business', 'is_engineer', 'is_tester'],
                                      'not_intent': ['get_age', 'get_name']}]}
        expected_slots = []
        for m in expected_slot['mapping']:
            expected_slots.append({"slot": "occupation", "mapping": m})
        for slot in expected_slots:
            processor.add_slot_mapping(slot, bot, user)
        processor.delete_slot_mapping("occupation", bot, user)
        slot = Slots.objects(name__iexact='occupation', bot=bot, user=user).get()
        assert slot['name'] == 'occupation'
        assert slot['type'] == 'text'
        assert slot['initial_value'] is None
        assert slot['influence_conversation']
        with pytest.raises(DoesNotExist):
            SlotMapping.objects(slot='occupation', bot=bot, status=True).get()
        expected_slots=[]
        expected_slot = {"slot": "occupation", 'mapping': [
            {'type': 'from_intent', 'intent': ['get_occupation'], 'value': 'business'},
            {'type': 'from_text', 'value': 'engineer',
             "conditions": [{"active_loop": "booking", "requested_slot": "engineer"}]},
            {'type': 'from_entity', 'entity': 'occupation'},
            {'type': 'from_trigger_intent', 'value': 'tester',
             'intent': ['get_business', 'is_engineer', 'is_tester'],
             'not_intent': ['get_age', 'get_name']}]}
        for m in expected_slot['mapping']:
            expected_slots.append({"slot": "occupation", "mapping": m})
        for slot in expected_slots:
            processor.add_slot_mapping(slot, bot, user)
        slots = SlotMapping.objects(slot='occupation', bot=bot, status=True)
        assert len(list(slots)) == 4


    def test_get_slot(self):
        bot = 'test'
        processor = MongoProcessor()
        slots = list(processor.get_existing_slots(bot))
        print(slots)
        expected = [
            {'name': 'kairon_action_response', 'type': 'any', 'influence_conversation': False, '_has_been_set': False, 'is_default': True},
            {'name': 'bot', 'type': 'any', 'initial_value': 'test', 'influence_conversation': False,
             '_has_been_set': False, 'is_default': True},
            {'name': 'order', 'type': 'any', 'influence_conversation': False, '_has_been_set': False, 'is_default': True},
            {'name': 'payment', 'type': 'any', 'influence_conversation': False, '_has_been_set': False, 'is_default': True},
            {'name': 'flow_reply', 'type': 'any', 'influence_conversation': False, '_has_been_set': False, 'is_default': True},
            {'name': 'http_status_code', 'type': 'any', 'influence_conversation': False, '_has_been_set': False, 'is_default': True},
            {'name': 'image', 'type': 'text', 'influence_conversation': True, '_has_been_set': False, 'is_default': True},
            {'name': 'audio', 'type': 'text', 'influence_conversation': True, '_has_been_set': False, 'is_default': True},
            {'name': 'video', 'type': 'text', 'influence_conversation': True, '_has_been_set': False, 'is_default': True},
            {'name': 'document', 'type': 'text', 'influence_conversation': True, '_has_been_set': False, 'is_default': True},
            {'name': 'doc_url', 'type': 'text', 'influence_conversation': True, '_has_been_set': False, 'is_default': True},
            {'name': 'longitude', 'type': 'text', 'influence_conversation': True, '_has_been_set': False, 'is_default': True},
            {'name': 'latitude', 'type': 'text', 'influence_conversation': True, '_has_been_set': False, 'is_default': True},
            {'name': 'date_time', 'type': 'text', 'influence_conversation': True, '_has_been_set': False, 'is_default': False},
            {'name': 'category', 'type': 'text', 'influence_conversation': False, '_has_been_set': False, 'is_default': False},
            {'name': 'file', 'type': 'text', 'influence_conversation': False, '_has_been_set': False, 'is_default': False},
            {'name': 'file_error', 'type': 'text', 'influence_conversation': False, '_has_been_set': False, 'is_default': False},
            {'name': 'file_text', 'type': 'text', 'influence_conversation': False, '_has_been_set': False, 'is_default': False},
            {'name': 'name', 'type': 'text', 'influence_conversation': True, '_has_been_set': False, 'is_default': False},
            {'name': 'priority', 'type': 'categorical', 'values': ['low', 'medium', 'high', '__other__'],
             'influence_conversation': True, '_has_been_set': False, 'is_default': False},
            {'name': 'ticketid', 'type': 'float', 'initial_value': 1.0, 'max_value': 1.0, 'min_value': 0.0,
             'influence_conversation': True, '_has_been_set': False, 'is_default': False},
            {'name': 'age', 'type': 'float', 'max_value': 1.0, 'min_value': 0.0, 'influence_conversation': True,
             '_has_been_set': False, 'is_default': False},
            {'name': 'occupation', 'type': 'text', 'influence_conversation': True, '_has_been_set': False, 'is_default': False},
            {'name': 'quick_reply', 'type': 'text', 'influence_conversation': True, '_has_been_set': False, 'is_default': True},
            {'name': 'mail_id', 'type': 'text', 'influence_conversation': True, '_has_been_set': False,
             'is_default': True},
            {'name': 'subject', 'type': 'text', 'influence_conversation': True, '_has_been_set': False,
             'is_default': True},
            {'name': 'body', 'type': 'text', 'influence_conversation': True, '_has_been_set': False,
             'is_default': True},
            {'name': 'media_ids', 'type': 'list', 'influence_conversation': True, '_has_been_set': False,
             'is_default': True},
            {'name': 'flow_docs', 'type': 'text', 'influence_conversation': True, '_has_been_set': False,
             'is_default': True},
            {'name': 'flow_images', 'type': 'text', 'influence_conversation': True, '_has_been_set': False,
             'is_default': True},
            {'name': 'flow_data', 'type': 'text', 'influence_conversation': True, '_has_been_set': False,
             'is_default': True},
            {'name': 'llm_call_id', 'type': 'text', 'influence_conversation': True, '_has_been_set': False,
             'is_default': True},
            {'name': 'user_identifier', 'type': 'any', 'influence_conversation': False, '_has_been_set': False, 'is_default': True},
            {'name': 'temp_token', 'type': 'any', 'influence_conversation': False, '_has_been_set': False, 'is_default': True},
            {'name': 'store_page_name', 'type': 'any', 'influence_conversation': False, '_has_been_set': False, 'is_default': True},
            {'name': 'redirect_url', 'type': 'text', 'influence_conversation': True, '_has_been_set': False, 'is_default': True},
            {'name': 'callback_identifier', 'type': 'any', 'influence_conversation': False, '_has_been_set': False,
             'is_default': True},
            {'name': 'is_followup', 'type': 'bool', 'influence_conversation': True, '_has_been_set': False,
             'is_default': True},
            {'name': 'parent_log_id', 'type': 'text', 'influence_conversation': True, '_has_been_set': False,
             'is_default': True},
            {'name': 'date', 'type': 'text', 'influence_conversation': True, '_has_been_set': False,
             'is_default': True},
            {'name': 'cc', 'type': 'list', 'influence_conversation': True, '_has_been_set': False,
             'is_default': True},
        ]
        assert len(slots) == 41
        assert not DeepDiff(slots, expected, ignore_order=True)

    def test_update_slot_add_value_intent_and_not_intent(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        processor.add_slot({"name": "location", "type": "text", "influence_conversation": True}, bot, user)
        slot = {"slot": "location", 'mapping': {'type': 'from_text', 'value': 'user', 'entity': 'location'}}

        slot2 = {"slot": "location", 'mapping': {'type': 'from_entity', 'entity': 'location'}}
        id1 = processor.add_slot_mapping(slot, bot, user)
        id2 = processor.add_slot_mapping(slot2, bot, user)

        slots = [{"slot": "age", 'mapping': {'type': 'from_intent', 'intent': ['retrieve_age', 'ask_age'],
                                              'not_intent': ['get_age', 'affirm', 'deny'], 'value': 20}},
                 {"slot": "location",
                  'mapping': {'type': 'from_intent', 'intent': ['get_location'], 'value': 'Mumbai'}},
                 {"slot": "location",
                  'mapping': {'type': 'from_text', 'value': 'Bengaluru'}}]

        processor.add_slot_mapping(slots[0], bot, user)
        processor.update_slot_mapping(slots[1], id1)
        processor.update_slot_mapping(slots[2], id2)

        slots = list(processor.get_slot_mappings(bot))
        diff = DeepDiff(slots,
                        [{'slot': 'age', 'mapping': [{'type': 'from_intent', 'value': '18', 'intent': ['get_age'], 'conditions': [{'active_loop': 'booking', 'requested_slot': 'age'}]}, {'type': 'from_intent', 'value': 20, 'intent': ['retrieve_age', 'ask_age'], 'not_intent': ['get_age', 'affirm', 'deny']}]}, {'slot': 'date_time', 'mapping': [{'type': 'from_entity', 'entity': 'date_time'}]}, {'slot': 'file', 'mapping': [{'type': 'from_entity', 'entity': 'file'}]}, {'slot': 'location', 'mapping': [{'type': 'from_intent', 'value': 'Mumbai', 'intent': ['get_location']}, {'type': 'from_text', 'value': 'Bengaluru'}]}, {'slot': 'name', 'mapping': [{'type': 'from_intent', 'value': 'user'}]}, {'slot': 'occupation', 'mapping': [{'type': 'from_intent', 'value': 'business', 'intent': ['get_occupation']}, {'type': 'from_text', 'value': 'engineer', 'conditions': [{'active_loop': 'booking', 'requested_slot': 'engineer'}]}, {'type': 'from_entity', 'entity': 'occupation'}, {'type': 'from_trigger_intent', 'value': 'tester', 'intent': ['get_business', 'is_engineer', 'is_tester'], 'not_intent': ['get_age', 'get_name']}]}, {'slot': 'priority', 'mapping': [{'type': 'from_entity', 'entity': 'priority'}]}],
                        ignore_order=True,
                        )
        assert not diff

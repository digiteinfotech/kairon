import os

import pytest
from mongoengine import ValidationError, connect
from rasa.shared.core.training_data.structures import STORY_START

from kairon import Utility
from kairon.api.models import HttpActionConfigRequest, HttpActionParameters, ActionResponseEvaluation
from kairon.shared.actions.data_objects import SetSlots, HttpActionRequestBody, KaironTwoStageFallbackAction
from kairon.shared.data.data_objects import Slots, SlotMapping, Entity, StoryEvents, StepFlowEvent, \
    MultiflowStoryEvents, MultiflowStories


class TestBotModels:

    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        Utility.load_email_configuration()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))
        yield None

    def test_http_action_params_valid(self):
        assert HttpActionParameters(key="param1", value="param1", parameter_type="slot")
        assert HttpActionParameters(key="param1", value="param1", parameter_type="value")
        HttpActionParameters(key="key", value="", parameter_type="value")
        HttpActionParameters(key="key", value=None, parameter_type="value")
        assert HttpActionParameters(key="param1", value="param1", parameter_type="sender_id")
        assert HttpActionParameters(key="param1", value="", parameter_type="sender_id")
        assert HttpActionParameters(key="param1", parameter_type="sender_id")

    def test_http_action_params_invalid(self):
        with pytest.raises(ValueError, match=r".*key cannot be empty.*"):
            HttpActionParameters(key="", value="param1", parameter_type="slot")
        with pytest.raises(ValueError, match=r".*key cannot be empty.*"):
            HttpActionParameters(key=None, value="param1", parameter_type="slot")
        with pytest.raises(ValueError, match=r".*Provide name of the slot as value.*"):
            HttpActionParameters(key="key", value="", parameter_type="slot")
        with pytest.raises(ValueError, match=r".*Provide name of the slot as value.*"):
            HttpActionParameters(key="key", value=None, parameter_type="slot")
        with pytest.raises(ValueError, match=r".*parameter_type\n  value is not a valid enumeration member.*"):
            HttpActionParameters(key="key", value="value", parameter_type="unknown_type")

    def test_http_action_config_request_valid(self):
        HttpActionConfigRequest(
            auth_token="",
            action_name="test_action",
            response=ActionResponseEvaluation(value="response"),
            http_url="http://www.google.com",
            request_method="GET",
            http_params_list=[]
        )
        HttpActionConfigRequest(
            auth_token=None,
            action_name="test_action",
            response=ActionResponseEvaluation(value="response"),
            http_url="http://www.google.com",
            request_method="GET",
            http_params_list=[]
        )

    def test_http_action_config_request_invalid(self):
        with pytest.raises(ValueError, match=r".*none is not an allowed value.*"):
            HttpActionConfigRequest(auth_token="", action_name=None, response="response",
                                    http_url="http://www.google.com",
                                    request_method="GET", http_params_list=[])
        with pytest.raises(ValueError, match=r".*action_name is required*"):
            HttpActionConfigRequest(auth_token="", action_name="", response="response",
                                    http_url="http://www.google.com",
                                    request_method="GET", http_params_list=[])
        HttpActionConfigRequest(auth_token="", action_name="http_action", response=None, http_url="http://www.google.com",
                                request_method="GET", http_params_list=[])
        with pytest.raises(ValueError, match=r".*URL is malformed.*"):
            HttpActionConfigRequest(auth_token="", action_name="http_action", response="response", http_url="",
                                    request_method="GET", http_params_list=[])
        with pytest.raises(ValueError, match=r".*none is not an allowed value.*"):
            HttpActionConfigRequest(auth_token="", action_name="http_action", response="response", http_url=None,
                                    request_method="GET", http_params_list=[])
        with pytest.raises(ValueError, match=r".URL is malformed.*"):
            HttpActionConfigRequest(auth_token="", action_name="http_action", response="response",
                                    http_url="www.google.com", request_method="GET", http_params_list=[])
        with pytest.raises(ValueError, match=r".*Invalid HTTP method.*"):
            HttpActionConfigRequest(auth_token="", action_name="http_action", response="response",
                                    http_url="http://www.google.com",
                                    request_method="OPTIONS", http_params_list=[])
        with pytest.raises(ValueError, match=r".*Invalid HTTP method.*"):
            HttpActionConfigRequest(auth_token="", action_name="http_action", response="response",
                                    http_url="http://www.google.com",
                                    request_method="", http_params_list=[])
        with pytest.raises(ValueError, match=r".*none is not an allowed value.*"):
            HttpActionConfigRequest(auth_token="", action_name="http_action", response="response",
                                    http_url="http://www.google.com",
                                    request_method=None, http_params_list=[])

    def test_slot(self):
        with pytest.raises(ValueError, match="Slot name and type cannot be empty or blank spaces"):
            Slots(name='email_id', type=' ', auto_fill=True).save()
        with pytest.raises(ValueError, match="Slot name and type cannot be empty or blank spaces"):
            Slots(name=' ', type='text', auto_fill=True).save()

    def test_validate_slot_mapping(self):
        with pytest.raises(ValueError, match="Slot name cannot be empty or blank spaces"):
            SlotMapping(slot=' ', mapping=[{"type": "from_value"}]).save()
        with pytest.raises(ValidationError,
                           match="Your form 'form_name' uses an invalid slot mapping of type 'from_value' for slot 'email_id'. Please see https://rasa.com/docs/rasa/forms for more information."):
            SlotMapping(slot='email_id', mapping=[{"type": "from_value"}]).save()
        assert not SlotMapping(
            slot='email_id', mapping=[{"type": "from_intent", "value": 'uditpandey@hotmail.com'}]
        ).validate()

    def test_http_action_request_body(self):
        http_action_request_one = HttpActionRequestBody(key="key1", value="value1", parameter_type="slot")
        http_action_request_duplicate = HttpActionRequestBody(key="key1", value="value1", parameter_type="slot")
        http_action_request_two = HttpActionRequestBody(key="key2", value="value1", parameter_type="slot")
        other_instance_type = SetSlots(name="slot1", value="value of slot", type="from_value")
        assert http_action_request_one == http_action_request_duplicate
        assert not http_action_request_one == http_action_request_two
        assert not http_action_request_one == other_instance_type

    def test_set_slots(self):
        set_slots_one = SetSlots(name="slot1", value="value of slot", type="from_value")
        set_slots_duplicate = SetSlots(name="slot1", value="value of slot", type="from_value")
        set_slots_two = SetSlots(name="slot2", value="value of slot", type="from_value")
        other_instance_type = Entity(start=0, end=6, value="DEF1234", entity="item_id")
        assert set_slots_one == set_slots_duplicate
        assert not set_slots_one == set_slots_two
        assert not set_slots_one == other_instance_type

    def test_entity(self):
        entity_one = Entity(start=0, end=6, value="DEF1234", entity="item_id")
        entity_duplicate = Entity(start=0, end=6, value="DEF1234", entity="item_id")
        entity_two = Entity(start=0, end=6, value="USR999", entity="item_id")
        other_instance_type = SetSlots(name="slot1", value="value of slot", type="from_value")
        assert entity_one == entity_duplicate
        assert not entity_one == entity_two
        assert not entity_one == other_instance_type

    def test_story_events(self):
        story_events_one = StoryEvents(name="greet", type="user")
        story_events_duplicate = StoryEvents(name="greet", type="user")
        story_events_two = StoryEvents(name="thanks", type="user")
        other_instance_type = SetSlots(name="slot1", value="value of slot", type="from_value")
        assert story_events_one == story_events_duplicate
        assert not story_events_one == story_events_two
        assert not story_events_one == other_instance_type

    def test_multiflow_story_events_stepname_empty(self):
        steps = [
            {"step": {"name": "", "type": "INTENT", "node_id": "MyhhQSAdhs", "component_id": "Mnvehd"},
             "connections": [{"name": "utter_greet", "type": "BOT", "node_id": "MyhhQSAdhs", "component_id": "Mnvehd"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "MyhhQSAdhs", "component_id": "Mnvehd"},
             "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "MyhhQSAdhs", "component_id": "Mnvehd"},
                             {"name": "goodbye", "type": "INTENT", "node_id": "MyhhQSAdhs", "component_id": "Mnvehd"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "MyhhQSAdhs", "component_id": "Mnvehd"},
             "connections": [{"name": "utter_goodbye", "type": "BOT", "node_id": "MyhhQSAdhs", "component_id": "Mnvehd"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "MyhhQSAdhs", "component_id": "Mnvehd"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "MyhhQSAdhs", "component_id": "Mnvehd"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "MyhhQSAdhs", "component_id": "Mnvehd"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "MyhhQSAdhs", "component_id": "Mnvehd"}]
             }
        ]

        events = [MultiflowStoryEvents(**step) for step in steps]
        story_obj = MultiflowStories()
        story_obj.block_name = "a story"
        story_obj.events = events
        story_obj.bot = "test"
        story_obj.user = "testdemo"
        story_obj.start_checkpoints = [STORY_START]
        with pytest.raises(ValidationError, match="Name cannot be empty"):
            story_obj.save()

    def test_multiflow_story_events_storyname_empty(self):
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "MyhhQSAdhs", "component_id": "Mnvehd"},
             "connections": [{"name": "utter_greet", "type": "BOT", "node_id": "MyhhQSAdhs", "component_id": "Mnvehd"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "MyhhQSAdhs", "component_id": "Mnvehd"},
             "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "MyhhQSAdhs", "component_id": "Mnvehd"},
                             {"name": "goodbye", "type": "INTENT", "node_id": "MyhhQSAdhs", "component_id": "Mnvehd"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "MyhhQSAdhs", "component_id": "Mnvehd"},
             "connections": [{"name": "utter_goodbye", "type": "BOT", "node_id": "MyhhQSAdhs", "component_id": "Mnvehd"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "MyhhQSAdhs", "component_id": "Mnvehd"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "MyhhQSAdhs", "component_id": "Mnvehd"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "MyhhQSAdhs", "component_id": "Mnvehd"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "MyhhQSAdhs", "component_id": "Mnvehd"}]
             }
        ]

        events = [MultiflowStoryEvents(**step) for step in steps]
        story_obj = MultiflowStories()
        story_obj.block_name = " "
        story_obj.events = events
        story_obj.bot = "test"
        story_obj.user = "testdemo"
        story_obj.start_checkpoints = [STORY_START]
        with pytest.raises(ValidationError, match="Story name cannot be empty or blank spaces"):
            story_obj.save()

    def test_multiflow_story_events_empty(self):
        steps = []
        events = [MultiflowStoryEvents(**step) for step in steps]
        story_obj = MultiflowStories()
        story_obj.block_name = "empty event story"
        story_obj.events = events
        story_obj.bot = "test"
        story_obj.user = "testdemo"
        story_obj.start_checkpoints = [STORY_START]
        with pytest.raises(ValidationError, match="events cannot be empty"):
            story_obj.save()

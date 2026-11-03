from tests.unit_test.data_processor.data_processor_support import *  # noqa: F403
from tests.unit_test.data_processor.data_processor_support import (
    MongoProcessorTestBase,
    fast_rasa_training,
)

class TestMongoProcessor(MongoProcessorTestBase):
    def test_add_complex_story_without_http_action(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        story_dict = {'name': "story without action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.add_complex_story(story_dict, "test_without_http", "testUser")
        story = Stories.objects(block_name="story without action", bot="test_without_http").get()
        assert len(story.events) == 5
        actions = processor.list_actions("test_without_http")
        assert actions == {
            'utterances': [], 'http_action': [], 'slot_set_action': [], 'form_validation_action': [],
            'email_action': [], 'google_search_action': [], 'jira_action': [], 'zendesk_action': [],
            'pipedrive_leads_action': [], 'hubspot_forms_action': [], 'two_stage_fallback': [],
            'kairon_bot_response': [], 'razorpay_action': [], 'prompt_action': [], 'actions': [],
            'database_action': [], 'pyscript_action': [], 'web_search_action': [], 'live_agent_action': [],
            'callback_action': [], 'schedule_action': [], 'voice_call_action': [], 'parallel_action': [],
            'kairon_voice_disconnect': [], 'store_page_action': [], 'agent_action': []
        }

    def test_add_complex_story_with_action(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "action_check", "type": "ACTION"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        story_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.add_complex_story(story_dict, "test_with_action", "testUser")
        story = Stories.objects(block_name="story with action", bot="test_with_action").get()
        assert len(story.events) == 6
        actions = processor.list_actions("test_with_action")
        assert actions == {
            'actions': ['action_check'], 'utterances': [], 'http_action': [], 'slot_set_action': [],
            'form_validation_action': [], 'email_action': [], 'google_search_action': [], 'jira_action': [],
            'zendesk_action': [], 'pipedrive_leads_action': [], 'hubspot_forms_action': [], 'two_stage_fallback': [],
            'kairon_bot_response': [], 'razorpay_action': [], 'prompt_action': [], 'database_action': [],
            'pyscript_action': [], 'voice_call_action': [], 'web_search_action': [], 'live_agent_action': [], 'callback_action': [], 'schedule_action': [],
            'parallel_action': [], 'kairon_voice_disconnect': [], 'store_page_action': [], 'agent_action': []
        }

    def test_add_complex_story(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        story_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        pytest.story_id_two = processor.add_complex_story(story_dict, "tests", "testUser")
        story = Stories.objects(block_name="story with action", bot="tests").get()
        assert len(story.events) == 6
        actions = processor.list_actions("tests")
        assert not DeepDiff(actions, {'actions': [], 'zendesk_action': [], 'pipedrive_leads_action': [],
                                      'hubspot_forms_action': [],
                                      'http_action': ['my_http_action'], 'google_search_action': [], 'jira_action': [],
                                      'two_stage_fallback': [],
                                      'slot_set_action': [], 'email_action': [], 'form_validation_action': [],
                                      'kairon_bot_response': [],
                                      'razorpay_action': [], 'prompt_action': ['gpt_llm_faq'],
                                      'database_action': [], 'pyscript_action': [], 'web_search_action': [], 'live_agent_action': [],
                                      'callback_action': [], 'schedule_action': [], 'voice_call_action': [], 'parallel_action': [],
                                      'kairon_voice_disconnect': [], 'store_page_action': [], 'agent_action': [],
                                      'utterances': ['utter_greet',
                                                     'utter_cheer_up',
                                                     'utter_did_that_help',
                                                     'utter_happy',
                                                     'utter_goodbye',
                                                     'utter_iamabot',
                                                     'utter_feedback',
                                                     'utter_good_feedback',
                                                     'utter_bad_feedback',
                                                     'utter_default',
                                                     'utter_please_rephrase', 'utter_custom', 'utter_query',
                                                     'utter_more_queries',
                                                     'utter_catalog_test', 'utter_catalog_value_test',
                                                     'utter_non_catalog_test', 'utter_catalog_label_test',
                                                     'utter_catalog_empty_label_empty_test',
                                                     'utter_catalog_label_edit_test']}, ignore_order=True)

    def test_add_complex_story_with_stop_flow_action(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_goodbye", "type": "BOT"},
            {"name": "utter_goodbye", "type": "BOT"},
            {"name": "stop", "type": "STOP_FLOW_ACTION"}
        ]
        story_dict = {'name': "story with stop flow action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        pytest.story_id_three = processor.add_complex_story(story_dict, "tests", "testUser")
        story = Stories.objects(block_name="story with stop flow action", bot="tests").get()
        assert len(story.events) == 4
        assert story is not None
        if story:
            stop_action_event = story.events[-1]
            assert stop_action_event.name == "action_listen"
            assert stop_action_event.type == "action"

    def test_add_multiflow_story_with_stop_flow_action(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": [
                 {"name": "stop_flow", "type": "STOP_FLOW_ACTION", "node_id": "7",
                  "component_id": "63gm5BzYuhC1bc6yzysEnN65"}]
             },
            {"step": {"name": "stop_flow", "type": "STOP_FLOW_ACTION", "node_id": "7",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN65"},
             "connections": None
             },
        ]
        story_dict = {'name': "multiflow story with stop flow action", 'steps': steps, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, "test", "TestUser")
        story = MultiflowStories.objects(block_name="multiflow story with stop flow action", bot="test").get()
        assert len(story.events) == 7
        stop_flow_step = story.events[6]['step']
        assert stop_flow_step['name'] == "stop_flow"
        assert stop_flow_step['type'] == "STOP_FLOW_ACTION"

    def test_add_duplicate_complex_story(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        with pytest.raises(Exception):
            story_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.add_complex_story(story_dict, "tests", "testUser")

    def test_add_duplicate_case_insensitive_complex_story(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        with pytest.raises(Exception):
            story_dict = {'name': "Story with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.add_complex_story(story_dict, "tests", "testUser")

    def test_add_none_complex_story_name(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            story_dict = {'name': None, 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.add_complex_story(story_dict, "tests", "testUser")

    def test_add_empty_complex_story_name(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"}
        ]
        with pytest.raises(AppException):
            story_dict = {'name': "", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.add_complex_story(story_dict, "tests", "testUser")

    def test_add_blank_complex_story_name(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"}
        ]
        with pytest.raises(AppException):
            story_dict = {'name': " ", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.add_complex_story(story_dict, "tests", "testUser")

    def test_add_empty_complex_story_event(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            story_dict = {'name': "empty path", 'steps': [], 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.add_complex_story(story_dict, "tests", "testUser")

    def test_add_duplicate_complex_story_using_events(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        with pytest.raises(Exception):
            story_dict = {'name': "story duplicate using events", 'steps': steps, 'type': 'STORY',
                          'template_type': 'CUSTOM'}
            processor.add_complex_story(story_dict, "tests", "testUser")

    def test_add_complex_story_with_invalid_event(self):
        processor = MongoProcessor()
        steps = [
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="First event should be an user"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="user event should be followed by action"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "mood_sad", "type": "INTENT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="Found 2 consecutive user events"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_multiflow_story(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]

        story_dict = {'name': "story", 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, "test", "TestUser")
        story = MultiflowStories.objects(block_name="story", bot="test").get()
        assert len(story.events) == 6

    def test_add_multiflow_story_with_slot(self):
        processor = MongoProcessor()
        story_name = "multiflow story with slot"
        bot = "test_slot"
        user = "test_user"
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
        stories = list(processor.get_multiflow_stories("test_slot"))
        assert stories[0]['type'] == "MULTIFLOW"
        assert len(stories[0]['steps']) == 6
        updated_steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "mood", "type": "SLOT", "value": "Happy", "node_id": "3",
                  "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "food", "type": "SLOT", "value": "Indian", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "food", "type": "SLOT", "value": "Indian", "node_id": "4",
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
            {"step": {"name": "mood", "type": "SLOT", "value": "Happy", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        updated_story_dict = {'name': story_name, 'steps': updated_steps, 'type': 'MULTIFLOW',
                              'template_type': 'CUSTOM'}
        processor.update_multiflow_story(pytest.story_id, updated_story_dict, bot)
        updated_multiflow_story = MultiflowStories.objects(block_name=story_name, bot=bot).get()
        assert len(updated_multiflow_story.events) == 6
        stories = list(processor.get_multiflow_stories("test_slot"))
        assert stories[0]['type'] == "MULTIFLOW"
        assert len(stories[0]['steps']) == 6
        load_story = processor.load_linear_flows_from_multiflow_stories(bot)
        assert load_story[0].story_steps[0].events[2].key == 'food'
        assert load_story[0].story_steps[0].events[2].value == 'Indian'
        assert load_story[0].story_steps[1].events[2].key == 'mood'
        assert load_story[0].story_steps[1].events[2].value == 'Happy'

    def test_add_multiflow_story_with_slot_value_int(self):
        processor = MongoProcessor()
        story_name = "multiflow story with slot int"
        bot = "test_slot_int"
        user = "test_user"
        steps = [
            {"step": {"name": "greeting", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_greeting", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greeting", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "age", "type": "SLOT", "value": 23, "node_id": "3",
                  "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foody", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foody", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_foody", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_foody", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_age", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "age", "type": "SLOT", "value": 23, "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_age", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = MultiflowStories.objects(block_name=story_name, bot=bot).get()
        assert len(multiflow_story.events) == 6
        stories = list(processor.get_multiflow_stories("test_slot_int"))
        assert stories[0]['type'] == "MULTIFLOW"
        assert len(stories[0]['steps']) == 6

    def test_add_multiflow_story_with_slot_value_bool(self):
        processor = MongoProcessor()
        story_name = "multiflow story with slot bool"
        bot = "test_slot_bool"
        user = "test_user"
        steps = [
            {"step": {"name": "greeting", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_greeting", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greeting", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "mood", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foody", "type": "SLOT", "value": True, "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foody", "type": "SLOT", "value": True, "node_id": "4",
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
            {"step": {"name": "mood", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = MultiflowStories.objects(block_name=story_name, bot=bot).get()
        assert len(multiflow_story.events) == 6
        stories = list(processor.get_multiflow_stories("test_slot_bool"))
        assert stories[0]['type'] == "MULTIFLOW"
        assert len(stories[0]['steps']) == 6

    def test_add_multiflow_story_with_slot_value_None(self):
        processor = MongoProcessor()
        story_name = "Multiflow None"
        bot = "test_slot_none"
        user = "test_user"
        steps = [
            {"step": {"name": "greeting", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_greeting", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greeting", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "mood", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "hobbies", "type": "SLOT", "value": None, "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "hobbies", "type": "SLOT", "value": None, "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_hobbies", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_hobbies", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "mood", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = MultiflowStories.objects(bot=bot).get()
        assert len(multiflow_story.events) == 6
        stories = list(processor.get_multiflow_stories("test_slot_none"))
        assert stories[0]['type'] == "MULTIFLOW"
        assert len(stories[0]['steps']) == 6

    def test_add_multiflow_story_with_slot_value_invalid(self):
        processor = MongoProcessor()
        story_name = "multiflow story with slot invalid"
        bot = "test_slot_invalid"
        user = "test_user"
        steps = [
            {"step": {"name": "greeting", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_greeting", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greeting", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "mood", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "games", "type": "SLOT", "value": {"1": "cricket"}, "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "games", "type": "SLOT", "value": {"1": "cricket"}, "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_games", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_games", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "mood", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError,
                           match="slot values in multiflow story must be either None or of type int, str or boolean"):
            processor.add_multiflow_story(story_dict, bot, user)

    def test_add_multiflow_story_with_slot_value_invalid_type(self):
        story_name = "multiflow story with slot invalid"
        bot = "test_slot_invalid"
        user = "test_user"
        steps = [
            {"step": {"name": "greeting", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_greeting", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greeting", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "mood", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "games", "type": "SLOT", "value": {"1": "cricket"}, "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "games", "type": "SLOT", "value": {"1": "cricket"}, "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_games", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_games", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "mood", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        events = [MultiflowStoryEvents(**step) for step in steps]
        with pytest.raises(ValidationError, match="slot values must be either None or of type int, str or boolean"):
            MultiflowStories(block_name="multiflow story with slot invalid", bot=bot, user=user, events=events).save()

    def test_add_multiflow_story_with_invalid_events(self):
        processor = MongoProcessor()
        story_name = "multiflow story with invalid events"
        bot = "test_slot_invalid"
        user = "test_user"
        steps = [
            {"step": {"name": "hello", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_hello", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_hello", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "mood", "type": "INTENT", "value": "Good", "node_id": "3",
                  "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "games", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "games", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_games", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_games", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "mood", "type": "INTENT", "value": "Good", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="Value is allowed only for slot events in multiflow story"):
            processor.add_multiflow_story(story_dict, bot, user)

    def test_add_multiflow_story_with_value_for_invalid_event(self):
        processor = MongoProcessor()
        story_name = "multiflow story with value for invalid events"
        bot = "test_slot_invalid"
        user = "test_user"
        steps = [
            {"step": {"name": "hello", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_hello", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_hello", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "mood", "type": "INTENT", "value": "Good", "node_id": "3",
                  "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "games", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "games", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_games", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_games", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "mood", "type": "INTENT", "value": "Good", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        events = [MultiflowStoryEvents(**step) for step in steps]
        with pytest.raises(ValidationError, match="Value is allowed only for slot events"):
            MultiflowStories(block_name="multiflow story with value for invalid events", bot=bot, user=user,
                             events=events).save()

    def test_add_multiflow_story_with_path_type_as_STORY(self):
        processor = MongoProcessor()
        story_name = "multiflow_story_STORY"
        bot = "test_path_story"
        user = "test_user_path_story"
        steps = [
            {"step": {"name": "ask", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_ask", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_ask", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "mood", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "food", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "food", "type": "INTENT", "node_id": "4",
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
            {"step": {"name": "mood", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6', "flow_type": 'STORY'}, {"node_id": "5", "flow_type": 'STORY'}]
        story_dict = {'name': story_name, 'steps': steps, "metadata": metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = MultiflowStories.objects(bot=bot).get()
        assert len(multiflow_story.events) == 6
        assert len(multiflow_story.metadata) == 2

    def test_add_multiflow_story_with_path_type_as_RULE(self):
        processor = MongoProcessor()
        story_name = "multiflow story with path as RULE"
        bot = "test_path_rule"
        user = "test_user"
        steps = [
            {"step": {"name": "asking", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_asking", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_asking", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "moody", "type": "HTTP_ACTION", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foody_act", "type": "HTTP_ACTION", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foody_act", "type": "HTTP_ACTION", "node_id": "4",
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
            {"step": {"name": "moody", "type": "HTTP_ACTION", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_moody", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6', "flow_type": 'RULE'}, {"node_id": "5", "flow_type": 'RULE'}]
        story_dict = {'name': story_name, 'steps': steps, "metadata": metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = MultiflowStories.objects(bot=bot).get()
        assert len(multiflow_story.events) == 6
        assert len(multiflow_story.metadata) == 2

    def test_add_multiflow_story_with_multiple_user_events_RULE(self):
        processor = MongoProcessor()
        story_name = "test_add_multiflow_story_with_multiple_user_events_RULE"
        bot = "test_path_rule"
        user = "test_user"
        steps = [
            {"step": {"name": "wish", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "moody", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "foody_act", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "foody_act", "type": "INTENT", "node_id": "4",
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
        metadata = [{"node_id": '6', "flow_type": 'RULE'}, {"node_id": "5", "flow_type": 'STORY'}]
        story_dict = {'name': story_name, 'steps': steps, "metadata": metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        with pytest.raises(AppException, match="Path tagged as RULE can have only one intent!"):
            processor.add_multiflow_story(story_dict, bot, user)

    def test_add_multiflow_story_with_no_path_type(self):
        processor = MongoProcessor()
        story_name = "multiflow story with no path type"
        bot = "test_no_path_type"
        user = "test_user"
        steps = [
            {"step": {"name": "welcome", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_welcome", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_welcome", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "coffee", "type": "HTTP_ACTION", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "tea", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "tea", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_tea", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_tea", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_coffee", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "coffee", "type": "HTTP_ACTION", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_coffee", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6'}, {"node_id": "5"}]
        story_dict = {'name': story_name, 'steps': steps, "metadata": metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, bot, user)
        multiflow_story = MultiflowStories.objects(bot=bot).get()
        assert len(multiflow_story.events) == 6
        assert multiflow_story.metadata[0]['flow_type'] == 'STORY'
        assert multiflow_story.metadata[0]['flow_type'] == 'STORY'

    def test_add_multiflow_story_with_leaf_node_slot(self):
        processor = MongoProcessor()
        story_name = "multiflow_story_with_leaf_node_slot"
        bot = "test_story_with_leaf_node_slot"
        user = "test_user"
        steps = [
            {"step": {"name": "weathery", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_weathery", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_weathery", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "sunny", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "rainy", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "sunny", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_sunny", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_sunny", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "umbrella", "type": "SLOT", "value": 'Yes', "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "rainy", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "umbrella", "type": "SLOT", "value": 'Yes', "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '6', "flow_type": "RULE"}, {"node_id": "5", "flow_type": "STORY"}]
        story_dict = {'name': story_name, 'steps': steps, "metadata": metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        with pytest.raises(AppException, match="Slots cannot be leaf nodes!"):
            processor.add_multiflow_story(story_dict, bot, user)

    def test_load_multiflow_stories(self):
        processor = MongoProcessor()
        story_name_one = "greeting story"
        story_name_two = "farmer story"
        story_name_three = "shopping story"
        bot = "load_linear_flows_from_multiflow_stories"
        user = "test_user"
        steps_one = [
            {"step": {"name": "welcome", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_welcome", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_welcome", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "coffee", "type": "HTTP_ACTION", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "tea", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "tea", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_tea", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_tea", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_coffee", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "coffee", "type": "HTTP_ACTION", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_coffee", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        steps_two = [
            {"step": {"name": "farmer", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_farmer", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_farmer", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "rice", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "wheat", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "wheat", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_wheat", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_wheat", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_rice", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "rice", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_rice", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        steps_three = [
            {"step": {"name": "shopping", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_shopping", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_shopping", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "clothes", "type": "HTTP_ACTION", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "handbags", "type": "HTTP_ACTION", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "handbags", "type": "HTTP_ACTION", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_handbags", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_handbags", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_clothes", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "clothes", "type": "HTTP_ACTION", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_clothes", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata_one = [{"node_id": '6', "flow_type": 'RULE'}, {"node_id": "5", "flow_type": 'STORY'}]
        metadata_two = [{"node_id": '6', "flow_type": 'STORY'}, {"node_id": "5", "flow_type": 'STORY'}]
        metadata_three = [{"node_id": '6', "flow_type": 'RULE'}, {"node_id": "5", "flow_type": 'RULE'}]

        story_dict_one = {'name': story_name_one, 'steps': steps_one, "metadata": metadata_one, 'type': 'MULTIFLOW',
                          'template_type': 'CUSTOM'}
        story_dict_two = {'name': story_name_two, 'steps': steps_two, "metadata": metadata_two,
                          'type': 'MULTIFLOW',
                          'template_type': 'CUSTOM'}
        story_dict_three = {'name': story_name_three, 'steps': steps_three, "metadata": metadata_three,
                            'type': 'MULTIFLOW',
                            'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict_one, bot, user)
        processor.add_multiflow_story(story_dict_two, bot, user)
        processor.add_multiflow_story(story_dict_three, bot, user)
        multiflow_story = processor.load_linear_flows_from_multiflow_stories(bot)
        assert multiflow_story[0].story_steps[0].block_name == 'greeting story_1'
        assert multiflow_story[1].story_steps[0].block_name == 'greeting story_2'
        assert multiflow_story[0].story_steps[1].block_name == 'farmer story_1'
        assert multiflow_story[0].story_steps[2].block_name == 'farmer story_2'
        assert multiflow_story[1].story_steps[1].block_name == 'shopping story_1'
        assert multiflow_story[1].story_steps[2].block_name == 'shopping story_2'
        assert multiflow_story[1].story_steps[0].events[0].action_name == '...'
        assert multiflow_story[1].story_steps[1].events[0].action_name == '...'
        assert multiflow_story[1].story_steps[2].events[0].action_name == '...'

    def test_add_multiflow_story_with_path_type_for_invalid_node(self):
        processor = MongoProcessor()
        story_name = "multiflow story with path for invalid node"
        bot = "test_invalid_node_path"
        user = "test_user"
        steps = [
            {"step": {"name": "weather", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_weather", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_weather", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "sunny", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "rainy", "type": "INTENT", "node_id": "4",
                  "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "sunny", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_sunny", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_sunny", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_rainy", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "rainy", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_rainy", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        metadata = [{"node_id": '2', "flow_type": "RULE"}, {"node_id": "5", "flow_type": "STORY"}]
        story_dict = {'name': story_name, 'steps': steps, "metadata": metadata, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="Only leaf nodes can be tagged with a flow"):
            processor.add_multiflow_story(story_dict, bot, user)

    def test_add_multiflow_story_same_action_intent_name(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1",
                      "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [{"name": "utter_greet", "type": "BOT", "node_id": "2",
                              "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "3",
                              "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                             {"name": "goodbye", "type": "INTENT", "node_id": "4",
                              "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [{"name": "goodbye", "type": "EMAIL_ACTION", "node_id": "5",
                              "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "goodbye", "type": "EMAIL_ACTION", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "633xnjCuP4iNZfEq5D7jyI9A",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             }
        ]

        story_dict = {'name': "story with same action name as intent", 'steps': steps, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, "test", "TestUser")
        story = MultiflowStories.objects(block_name="story with same action name as intent", bot="test").get()
        assert len(story.events) == 6

    def test_add_multiflow_story_with_same_events(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [
                 {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [
                 {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                 {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [
                 {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]

        story_dict = {'name': "story with same flow events", 'steps': steps, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        with pytest.raises(AppException, match="Story flow already exists!"):
            processor.add_multiflow_story(story_dict, "test", "TestUser")

    def test_add_multiflow_story_with_multiple_actions(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "63sKhFlHTZCgTyY6aCi34T6P"},
             "connections": [
                 {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63ybbEJli191Ey3ek2XML6Po"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63ybbEJli191Ey3ek2XML6Po"},
             "connections": [
                 {"name": "utter_qoute", "type": "BOT", "node_id": "3", "component_id": "63LamdXLIvKT4A1Lo8Nrlgso"},
                 {"name": "utter_thought", "type": "BOT", "node_id": "4", "component_id": "63jwAHaBHS7qMWZiGTOgX2V1"}]
             },
            {"step": {"name": "utter_thought", "type": "BOT", "node_id": "4",
                      "component_id": "63jwAHaBHS7qMWZiGTOgX2V1"},
             "connections": [
                 {"name": "more_queries", "type": "INTENT", "node_id": "5", "component_id": "63kn8FkXZajTdGwrSbOgVnpg"}]
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "5",
                      "component_id": "63kn8FkXZajTdGwrSbOgVnpg"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                              "component_id": "63ovTDWUJ7gP5IlhhRNmc327"}]
             },
            {"step": {"name": "utter_qoute", "type": "BOT", "node_id": "3", "component_id": "63LamdXLIvKT4A1Lo8Nrlgso"},
             "connections": [
                 {"name": "goodbye", "type": "INTENT", "node_id": "7", "component_id": "63DVHaMnngGY70EUgG9ATwVF"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "7", "component_id": "63DVHaMnngGY70EUgG9ATwVF"},
             "connections": [
                 {"name": "utter_goodbye", "type": "BOT", "node_id": "8", "component_id": "632hGiC1QFwtD48CH5VWXOjH"}]
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                      "component_id": "63ovTDWUJ7gP5IlhhRNmc327"},
             "connections": None
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "8",
                      "component_id": "632hGiC1QFwtD48CH5VWXOjH"},
             "connections": None
             }
        ]

        story_dict = {'name': "story with multiple actions", 'steps': steps, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.add_multiflow_story(story_dict, "test", "TestUser")
        story = MultiflowStories.objects(block_name="story with multiple actions", bot="test").get()
        assert len(story.events) == 8

    def test_add_multiflow_story_with_cycle(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "ppooakak"},
             "connections": [{"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ppooakak"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ppooakak"},
             "connections": [{"name": "utter_qoute", "type": "BOT", "node_id": "3", "component_id": "ppooakak"},
                             {"name": "utter_thought", "type": "BOT", "node_id": "4", "component_id": "ppooakak"}]
             },
            {"step": {"name": "utter_thought", "type": "BOT", "node_id": "4", "component_id": "ppooakak"},
             "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "5", "component_id": "ppooakak"}]
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "5", "component_id": "ppooakak"},
             "connections": [{"name": "goodbye", "type": "INTENT", "node_id": "6", "component_id": "ppooakak"}]
             },
            {"step": {"name": "utter_qoute", "type": "BOT", "node_id": "3", "component_id": "ppooakak"},
             "connections": [{"name": "goodbye", "type": "INTENT", "node_id": "6", "component_id": "ppooakak"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "6", "component_id": "ppooakak"},
             "connections": [{"name": "utter_qoute", "type": "BOT", "node_id": "3", "component_id": "ppooakak"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "6", "component_id": "ppooakak"},
             "connections": None
             }
        ]

        with pytest.raises(AppException, match="Story cannot contain cycle!"):
            story_dict = {'name': "story with cycle", 'steps': steps, 'type': 'MULTIFLOW',
                          'template_type': 'CUSTOM'}
            processor.add_multiflow_story(story_dict, "test", "TestUser")

    def test_add_multiflow_story_no_multiple_action_for_intent(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "heyyy", "type": "INTENT", "node_id": "1", "component_id": "ppooakak"},
             "connections": [{"name": "utter_heyyy", "type": "BOT", "node_id": "2", "component_id": "ppooakak"},
                             {"name": "utter_greet", "type": "BOT", "node_id": "3", "component_id": "ppooakak"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "3", "component_id": "ppooakak"},
             "connections": [{"name": "more_queriesss", "type": "INTENT", "node_id": "4", "component_id": "ppooakak"},
                             {"name": "goodbyeee", "type": "INTENT", "node_id": "5", "component_id": "ppooakak"}]
             },
            {"step": {"name": "goodbyeee", "type": "INTENT", "node_id": "5", "component_id": "ppooakak"},
             "connections": [{"name": "utter_goodbyeee", "type": "BOT", "node_id": "6", "component_id": "ppooakak"}]
             },
            {"step": {"name": "utter_goodbyeee", "type": "BOT", "node_id": "6", "component_id": "ppooakak"},
             "connections": None
             },
            {"step": {"name": "utter_more_queriesss", "type": "BOT", "node_id": "7", "component_id": "ppooakak"},
             "connections": None
             },
            {"step": {"name": "more_queriesss", "type": "INTENT", "node_id": "4", "component_id": "ppooakak"},
             "connections": [
                 {"name": "utter_more_queriesss", "type": "BOT", "node_id": "7", "component_id": "ppooakak"}]
             },
            {"step": {"name": "utter_heyyy", "type": "BOT", "node_id": "2", "component_id": "ppooakak"},
             "connections": None
             }
        ]

        with pytest.raises(AppException, match="Intent can only have one connection of action type or slot type"):
            story_dict = {'name': "story with multiple action for an intent", 'steps': steps, 'type': 'MULTIFLOW',
                          'template_type': 'CUSTOM'}
            processor.add_multiflow_story(story_dict, "test", "TestUser")

    def test_add_multiflow_story_with_connected_nodes(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "63ue2YkCdcVmnU0L7Q8wCjnc"},
             "connections": [
                 {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63NSzOE45TM6VxMTkak6C5Oy"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "63NSzOE45TM6VxMTkak6C5Oy"},
             "connections": [
                 {"name": "thought", "type": "INTENT", "node_id": "3", "component_id": "63qydua5wtsuI3Dr0Q4gAtlj"},
                 {"name": "mood", "type": "INTENT", "node_id": "4", "component_id": "63ejBpfbp5XXvmgbkfYdWt8t"}]
             },
            {"step": {"name": "mood", "type": "INTENT", "node_id": "4", "component_id": "63ejBpfbp5XXvmgbkfYdWt8t"},
             "connections": [
                 {"name": "utter_mood", "type": "BOT", "node_id": "5", "component_id": "63Mcq10uhqwcrP8Pq29eqQYa"}]
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "5", "component_id": "63Mcq10uhqwcrP8Pq29eqQYa"},
             "connections": [
                 {"name": "utter_thought", "type": "BOT", "node_id": "6", "component_id": "63CYvgxUsX0aeLYV4WdfIJF2"}]
             },
            {"step": {"name": "utter_thought", "type": "BOT", "node_id": "6",
                      "component_id": "63CYvgxUsX0aeLYV4WdfIJF2"},
             "connections": None
             },
            {"step": {"name": "thought", "type": "INTENT", "node_id": "3", "component_id": "63qydua5wtsuI3Dr0Q4gAtlj"},
             "connections": [
                 {"name": "utter_thought", "type": "BOT", "node_id": "6", "component_id": "63CYvgxUsX0aeLYV4WdfIJF2"}]
             }
        ]

        story_dict = {'name': "story with connected nodes", 'steps': steps, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        pytest.multiflow_story_id = processor.add_multiflow_story(story_dict, "test", "TestUser")
        story = MultiflowStories.objects(block_name="story with connected nodes", bot="test").get()
        assert len(story.events) == 6

    def test_add_none_multiflow_story_name(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "ksos09"},
             "connections": [{"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ksos09"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ksos09"},
             "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "ksos09"},
                             {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "ksos09"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "ksos09"},
             "connections": [{"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "ksos09"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "ksos09"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "ksos09"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "ksos09"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "ksos09"}]
             }
        ]
        with pytest.raises(AppException, match="Story name cannot be empty or blank spaces"):
            story_dict = {'name': None, 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
            processor.add_multiflow_story(story_dict, "tests", "testUser")

    def test_add_multiflow_story_same_source(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "ksos09"},
             "connections": [{"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ksos09"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ksos09"},
             "connections": None
             },
            {"step": {"name": "mood", "type": "INTENT", "node_id": "3", "component_id": "ksos09"},
             "connections": [{"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ksos09"}]
             },
        ]

        with pytest.raises(AppException, match="Story cannot have multiple sources!"):
            story_dict = {'name': 'story with multiple source node', 'steps': steps, 'type': 'MULTIFLOW',
                          'template_type': 'CUSTOM'}
            processor.add_multiflow_story(story_dict, "tests", "testUser")

    def test_add_multiflow_story_connected_steps(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "ksos09"},
             "connections": [{"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ksos09"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ksos09"},
             "connections": None
             },
            {"step": {"name": "mood", "type": "INTENT", "node_id": "3", "component_id": "ksos09"},
             "connections": [{"name": "utter_mood", "type": "BOT", "node_id": "4", "component_id": "ksos09"}]
             },
            {"step": {"name": "utter_mood", "type": "BOT", "node_id": "4", "component_id": "ksos09"},
             "connections": None
             },
        ]

        with pytest.raises(AppException, match="All steps must be connected!"):
            story_dict = {'name': 'story with no connected steps', 'steps': steps, 'type': 'MULTIFLOW',
                          'template_type': 'CUSTOM'}
            processor.add_multiflow_story(story_dict, "tests", "testUser")

    def test_add_empty_multiflow_story_name(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "ksos09"},
             "connections": [{"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ksos09"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ksos09"},
             "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "ksos09"},
                             {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "ksos09"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "ksos09"},
             "connections": [{"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "ksos09"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "ksos09"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "ksos09"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "ksos09"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "ksos09"}]
             }
        ]
        with pytest.raises(AppException, match="Story name cannot be empty or blank spaces"):
            story_dict = {'name': "", 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
            processor.add_multiflow_story(story_dict, "tests", "testUser")

    def test_add_blank_multiflow_story_name(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "ksos09"},
             "connections": [{"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ksos09"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2", "component_id": "ksos09"},
             "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "ksos09"},
                             {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "ksos09"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "ksos09"},
             "connections": [{"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "ksos09"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "ksos09"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "ksos09"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "ksos09"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "ksos09"}]
             }
        ]
        with pytest.raises(AppException, match="Story name cannot be empty or blank spaces"):
            story_dict = {'name': " ", 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
            processor.add_multiflow_story(story_dict, "tests", "testUser")

    def test_add_empty_multiflow_story_event(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match="steps are required"):
            story_dict = {'name': "empty path", 'steps': [], 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
            processor.add_multiflow_story(story_dict, "test", "TestUser")

    def test_update_multiflow_story(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "63TARMJ08PO7uSpktNcGIY9l"},
             "connections": [
                 {"name": "utter_time", "type": "BOT", "node_id": "2", "component_id": "63GU3Xjvf2wYX1XBKXzZkuzK"}]
             },
            {"step": {"name": "utter_time", "type": "BOT", "node_id": "2", "component_id": "63GU3Xjvf2wYX1XBKXzZkuzK"},
             "connections": [
                 {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "63YbD6G7rrqVrAFt3N1IaXRC"},
                 {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "63gso6SSgHYX7vLF6ghdq0Zy"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "63gso6SSgHYX7vLF6ghdq0Zy"},
             "connections": [
                 {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "63tmj2qy4zQX2tflE4Pbhby9"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5",
                      "component_id": "63tmj2qy4zQX2tflE4Pbhby9"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                      "component_id": "63Ff9XE3qlHN4UKH6jCsaTC2"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3",
                      "component_id": "63YbD6G7rrqVrAFt3N1IaXRC"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                              "component_id": "63Ff9XE3qlHN4UKH6jCsaTC2"}]
             }
        ]
        story_dict = {'name': "updated_story", 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        processor.update_multiflow_story(pytest.multiflow_story_id, story_dict, "test")
        story = MultiflowStories.objects(block_name="updated_story", bot="test").get()
        assert story.events[0]['connections'][0]['name'] == "utter_time"

    def test_update_multiflow_story_with_same_events(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "63TARMJ08PO7uSpktNcGIY9l"},
             "connections": [
                 {"name": "utter_time", "type": "BOT", "node_id": "2", "component_id": "63GU3Xjvf2wYX1XBKXzZkuzK"}]
             },
            {"step": {"name": "utter_time", "type": "BOT", "node_id": "2", "component_id": "63GU3Xjvf2wYX1XBKXzZkuzK"},
             "connections": [
                 {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "63YbD6G7rrqVrAFt3N1IaXRC"},
                 {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "63gso6SSgHYX7vLF6ghdq0Zy"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "63gso6SSgHYX7vLF6ghdq0Zy"},
             "connections": [
                 {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "63tmj2qy4zQX2tflE4Pbhby9"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5",
                      "component_id": "63tmj2qy4zQX2tflE4Pbhby9"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                      "component_id": "63Ff9XE3qlHN4UKH6jCsaTC2"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3",
                      "component_id": "63YbD6G7rrqVrAFt3N1IaXRC"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                              "component_id": "63Ff9XE3qlHN4UKH6jCsaTC2"}]
             }
        ]

        story_dict = {'name': "story update with same flow events", 'steps': steps, 'type': 'MULTIFLOW',
                      'template_type': 'CUSTOM'}
        processor.update_multiflow_story(pytest.multiflow_story_id, story_dict, "test")

    def test_update_multiflow_story_with_same_events_with_different_story_id(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1",
                      "component_id": "637d0j9GD059jEwt2jPnlZ7I"},
             "connections": [{"name": "utter_greet", "type": "BOT", "node_id": "2",
                              "component_id": "63uNJw1QvpQZvIpP07dxnmFU"}]
             },
            {"step": {"name": "utter_greet", "type": "BOT", "node_id": "2",
                      "component_id": "63uNJw1QvpQZvIpP07dxnmFU"},
             "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "3",
                              "component_id": "633w6kSXuz3qqnPU571jZyCv"},
                             {"name": "goodbye", "type": "INTENT", "node_id": "4",
                              "component_id": "63WKbWs5K0ilkujWJQpXEXGD"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4",
                      "component_id": "63WKbWs5K0ilkujWJQpXEXGD"},
             "connections": [{"name": "utter_goodbye", "type": "BOT", "node_id": "5",
                              "component_id": "63gm5BzYuhC1bc6yzysEnN4E"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5",
                      "component_id": "63gm5BzYuhC1bc6yzysEnN4E"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                      "component_id": "634a9bwPPj2y3zF5HOVgLiXx"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3",
                      "component_id": "633w6kSXuz3qqnPU571jZyCv"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6",
                              "component_id": "634a9bwPPj2y3zF5HOVgLiXx"}]
             }
        ]
        story_dict = {'name': "story with same flow events",
                      'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        with pytest.raises(AppException, match="Story flow already exists!"):
            processor.update_multiflow_story(pytest.multiflow_story_id, story_dict, "test")

    def test_update_non_existing_multiflow_story(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greeted", "type": "INTENT", "node_id": "1", "component_id": "NKUPKJ"},
             "connections": [{"name": "utter_timed", "type": "BOT", "node_id": "2", "component_id": "NKUPKJ"}]
             },
            {"step": {"name": "utter_timed", "type": "BOT", "node_id": "2", "component_id": "NKUPKJ"},
             "connections": [{"name": "some_more_queries", "type": "INTENT", "node_id": "3", "component_id": "NKUPKJ"},
                             {"name": "saying_goodbye", "type": "INTENT", "node_id": "4", "component_id": "NKUPKJ"}]
             },
            {"step": {"name": "saying_goodbye", "type": "INTENT", "node_id": "4", "component_id": "NKUPKJ"},
             "connections": [{"name": "utter_saying_goodbye", "type": "BOT", "node_id": "5", "component_id": "NKUPKJ"}]
             },
            {"step": {"name": "utter_saying_goodbye", "type": "BOT", "node_id": "5", "component_id": "NKUPKJ"},
             "connections": None
             },
            {"step": {"name": "utter_some_more_queries", "type": "BOT", "node_id": "6", "component_id": "NKUPKJ"},
             "connections": None
             },
            {"step": {"name": "some_more_queries", "type": "INTENT", "node_id": "3", "component_id": "NKUPKJ"},
             "connections": [
                 {"name": "utter_some_more_queries", "type": "BOT", "node_id": "6", "component_id": "NKUPKJ"}]
             }
        ]
        with pytest.raises(AppException, match="Flow does not exists"):
            story_dict = {'name': "non existing story conditional", 'steps': steps, 'type': 'MULTIFLOW',
                          'template_type': 'CUSTOM'}
            processor.update_multiflow_story("5e564fbcdcf0d5fad89e3acd", story_dict, "test")

    def test_update_multiflow_story_with_invalid_event(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "BOT", "node_id": "1", "component_id": "NKUPKJ"},
             "connections": [{"name": "utter_time", "type": "BOT", "node_id": "2", "component_id": "NKUPKJ"}]
             },
            {"step": {"name": "utter_time", "type": "BOT", "node_id": "2", "component_id": "NKUPKJ"},
             "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "NKUPKJ"},
                             {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "NKUPKJ"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "NKUPKJ"},
             "connections": [{"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "NKUPKJ"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "NKUPKJ"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "NKUPKJ"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "NKUPKJ"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "NKUPKJ"}]
             }
        ]
        story_dict = {'name': "story", 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        with pytest.raises(AppException, match="First step should be an intent"):
            processor.update_multiflow_story(pytest.multiflow_story_id, story_dict, "test")

        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "NKUPKJ"},
             "connections": [{"name": "utter_time", "type": "INTENT", "node_id": "2", "component_id": "NKUPKJ"}]
             },
            {"step": {"name": "utter_time", "type": "INTENT", "node_id": "2", "component_id": "NKUPKJ"},
             "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "NKUPKJ"},
                             {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "NKUPKJ"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "NKUPKJ"},
             "connections": [{"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "NKUPKJ"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "NKUPKJ"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "NKUPKJ"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "NKUPKJ"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "4", "component_id": "NKUPKJ"}]
             }
        ]
        rule_dict = {'name': "story", 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        with pytest.raises(AppException, match="Intent should be followed by an Action or Slot type event"):
            processor.update_multiflow_story(pytest.multiflow_story_id, rule_dict, "test")

    def test_update_multiflow_story_name(self):
        processor = MongoProcessor()
        events = [
            {"step": {"name": "greet", "type": "BOT", "node_id": "1", "component_id": "NKUPKJ"},
             "connections": [{"name": "utter_greeting", "type": "BOT", "node_id": "2", "component_id": "NKUPKJ"}]
             },
            {"step": {"name": "utter_time", "type": "BOT", "node_id": "2", "component_id": "NKUPKJ"},
             "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "NKUPKJ"},
                             {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "NKUPKJ"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "NKUPKJ"},
             "connections": [{"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "NKUPKJ"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "NKUPKJ"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "NKUPKJ"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "NKUPKJ"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "NKUPKJ"}]
             }
        ]
        with pytest.raises(AppException, match='Story name cannot be empty or blank spaces'):
            story_dict = {'name': None, 'steps': events, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
            processor.update_multiflow_story(pytest.multiflow_story_id, story_dict, "tests")

    def test_update_empty_multiflow_story_name(self):
        processor = MongoProcessor()
        events = [
            {"step": {"name": "greet", "type": "BOT", "node_id": "1", "component_id": "MkkfnA"},
             "connections": [{"name": "utter_time", "type": "BOT", "node_id": "2", "component_id": "MkkfnA"}]
             },
            {"step": {"name": "utter_time", "type": "BOT", "node_id": "2", "component_id": "MkkfnA"},
             "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "MkkfnA"},
                             {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "MkkfnA"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "MkkfnA"},
             "connections": [{"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "MkkfnA"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "MkkfnA"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "MkkfnA"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "MkkfnA"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "MkkfnA"}]
             }
        ]
        with pytest.raises(AppException, match='Story name cannot be empty or blank spaces'):
            story_dict = {'name': "", 'steps': events, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
            processor.update_multiflow_story(pytest.multiflow_story_id, story_dict, "tests")

    # def test_update_valid_multiflow_story_name(self):
    #     processor = MongoProcessor()
    #     events = [
    #         {"step": {"name": "greet", "type": "BOT", "node_id": "1", "component_id": "NKUPKJ"},
    #          "connections": [{"name": "utter_greeting", "type": "BOT", "node_id": "2", "component_id": "NKUPKJ"}]
    #          },
    #         {"step": {"name": "utter_time", "type": "BOT", "node_id": "2", "component_id": "NKUPKJ"},
    #          "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "NKUPKJ"},
    #                          {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "NKUPKJ"}]
    #          },
    #         {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "NKUPKJ"},
    #          "connections": [{"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "NKUPKJ"}]
    #          },
    #         {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "NKUPKJ"},
    #          "connections": None
    #          },
    #         {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "NKUPKJ"},
    #          "connections": None
    #          },
    #         {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "NKUPKJ"},
    #          "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "NKUPKJ"}]
    #          }
    #     ]
    #     with pytest.raises(AppException,
    #                        match="Path name can only contain letters, numbers, hyphens (-), and underscores (_)"):
    #         story_dict = {'name': "Invalid_Name", 'steps': events, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
    #         processor.update_multiflow_story(pytest.multiflow_story_id, story_dict, "tests")


    def test_update_blank_multiflow_story_name(self):
        processor = MongoProcessor()
        events = [
            {"step": {"name": "greet", "type": "BOT", "node_id": "1", "component_id": "MkkfnA"},
             "connections": [{"name": "utter_time", "type": "BOT", "node_id": "2", "component_id": "MkkfnA"}]
             },
            {"step": {"name": "utter_time", "type": "BOT", "node_id": "2", "component_id": "MkkfnA"},
             "connections": [{"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "MkkfnA"},
                             {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "MkkfnA"}]
             },
            {"step": {"name": "goodbye", "type": "INTENT", "node_id": "4", "component_id": "MkkfnA"},
             "connections": [{"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "MkkfnA"}]
             },
            {"step": {"name": "utter_goodbye", "type": "BOT", "node_id": "5", "component_id": "MkkfnA"},
             "connections": None
             },
            {"step": {"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "MkkfnA"},
             "connections": None
             },
            {"step": {"name": "more_queries", "type": "INTENT", "node_id": "3", "component_id": "MkkfnA"},
             "connections": [{"name": "utter_more_queries", "type": "BOT", "node_id": "6", "component_id": "MkkfnA"}]
             }
        ]
        with pytest.raises(AppException, match='Story name cannot be empty or blank spaces'):
            story_dict = {'name': " ", 'steps': events, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
            processor.update_multiflow_story(pytest.multiflow_story_id, story_dict, "tests")

    def test_update_empty_multiflow_story_event(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match='steps are required'):
            story_dict = {'name': "empty path", 'steps': [], 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
            processor.update_multiflow_story(pytest.multiflow_story_id, story_dict, "tests")

    def test_delete_multiflow_story(self):
        processor = MongoProcessor()
        processor.delete_complex_story(pytest.multiflow_story_id, "MULTIFLOW", "test", "TestUser")

    def test_case_delete_multiflow_story(self):
        processor = MongoProcessor()
        steps = [
            {"step": {"name": "greet", "type": "INTENT", "node_id": "1", "component_id": "63K8PA5su49O7HQBDmSrgJXz"},
             "connections": [
                 {"name": "utter_hi", "type": "BOT", "node_id": "2", "component_id": "63OgU8uyVaj0649DWx5VOSAk"}]
             },
            {"step": {"name": "utter_hi", "type": "BOT", "node_id": "2", "component_id": "63OgU8uyVaj0649DWx5VOSAk"},
             "connections": [
                 {"name": "status", "type": "INTENT", "node_id": "3", "component_id": "63KWJCwd8MUGVpNQWlKWhiTa"},
                 {"name": "id", "type": "INTENT", "node_id": "4", "component_id": "63aLcDfR8mIfWaiVSUwNQLa6"}]
             },
            {"step": {"name": "id", "type": "INTENT", "node_id": "4", "component_id": "63aLcDfR8mIfWaiVSUwNQLa6"},
             "connections": [
                 {"name": "utter_id", "type": "BOT", "node_id": "5", "component_id": "636lABcKF5Y6hoRvYOC4xPbv"}]
             },
            {"step": {"name": "utter_id", "type": "BOT", "node_id": "5", "component_id": "636lABcKF5Y6hoRvYOC4xPbv"},
             "connections": None
             },
            {"step": {"name": "utter_status", "type": "BOT", "node_id": "6",
                      "component_id": "63sQZwlPiuydd8eVgIQwAmXw"},
             "connections": None
             },
            {"step": {"name": "status", "type": "INTENT", "node_id": "3", "component_id": "63KWJCwd8MUGVpNQWlKWhiTa"},
             "connections": [
                 {"name": "utter_status", "type": "BOT", "node_id": "6", "component_id": "63sQZwlPiuydd8eVgIQwAmXw"}]
             }
        ]
        story_dict = {"name": "a story", 'steps': steps, 'type': 'MULTIFLOW', 'template_type': 'CUSTOM'}
        story_id = processor.add_multiflow_story(story_dict, "test", "TestUser")
        processor.delete_complex_story(story_id, "MULTIFLOW", "test", "TestUser")

    def test_update_complex_story(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        story_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.update_complex_story(pytest.story_id_two, story_dict, "tests", "testUser")
        story = Stories.objects(block_name="story with action", bot="tests").get()
        assert story.events[1].name == "utter_nonsense"

    def test_update_complex_story_same_events(self):
        def test_update_complex_story(self):
            processor = MongoProcessor()
            steps = [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_nonsense", "type": "BOT"},
                {"name": "utter_cheer_up", "type": "BOT"},
                {"name": "mood_great", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
                {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
            ]
            story_dict = {'name': "story with same events", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
            with pytest.raises(AppException, match="FLow already exists!"):
                processor.update_complex_story(pytest.story_id_two, story_dict, "tests", "testUser")

    def test_add_complex_story_with_same_events(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        story_dict = {'name': "story with same events", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(AppException, match="Flow already exists!"):
            processor.add_complex_story(story_dict, "tests", "testUser")

    def test_update_complex_story_with_same_events_with_same_story_id(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        story_dict = {'name': "story with same events", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.update_complex_story(pytest.story_id_two, story_dict, "tests", "testUser")

    def test_case_insensitive_update_complex_story(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"},
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        story_dict = {'name': "STory with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.update_complex_story(pytest.story_id_two, story_dict, "tests", "testUser")
        story = Stories.objects(block_name="story with action", bot="tests").get()
        assert story.events[1].name == "utter_nonsense"

    def test_update_non_existing_complex_story(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"},
        ]
        with pytest.raises(AppException, match="Flow does not exists"):
            story_dict = {'name': "non existing story", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.update_complex_story('5e564fbcdcf0d5fad89e3acd', story_dict, "tests", "testUser")

    def test_update_complex_story_with_invalid_event(self):
        processor = MongoProcessor()
        steps = [
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="First event should be an user"):
            processor.update_complex_story(pytest.story_id_two, rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
        ]
        rule_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="user event should be followed by action"):
            processor.update_complex_story(pytest.story_id_two, rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "mood_sad", "type": "INTENT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="Found 2 consecutive user events"):
            processor.update_complex_story(pytest.story_id_two, rule_dict, "tests", "testUser")

    def test_update_complex_story_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"}
        ]
        with pytest.raises(AppException):
            story_dict = {'name': None, 'steps': events, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.update_complex_story(pytest.story_id, story_dict, "tests", "testUser")

    def test_update_empty_complex_story_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"}
        ]
        with pytest.raises(AppException):
            story_dict = {'name': "", 'steps': events, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.update_complex_story(pytest.story_id, story_dict, "tests", "testUser")

    def test_update_invalid_complex_story_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"}
        ]
        with pytest.raises(AppException):
            story_dict = {'name': "Invalid@Name!", 'steps': events, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.update_complex_story(pytest.story_id, story_dict, "tests", "testUser")

    def test_update_valid_complex_story_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"}
        ]
        with pytest.raises(AppException):
            story_dict = {'name': "Invalid_Name", 'steps': events, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.update_complex_story(pytest.story_id, story_dict, "tests", "testUser")

    def test_update_blank_complex_story_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"}
        ]
        with pytest.raises(AppException):
            story_dict = {'name': " ", 'steps': events, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.update_complex_story(pytest.story_id, story_dict, "tests", "testUser")

    def test_update_empty_complex_story_event(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            story_dict = {'name': "empty path", 'steps': [], 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.update_complex_story(pytest.story_id, story_dict, "tests", "testUser")

    def test_list_actions(self):
        processor = MongoProcessor()
        processor.add_action("reset_slot", "test_upload_and_save", "test_user")
        actions = processor.list_actions("test_upload_and_save")
        assert not DeepDiff(actions, {
            'actions': ['reset_slot'], 'google_search_action': [], 'jira_action': [], 'pipedrive_leads_action': [],
            'http_action': ['action_performanceUser1000@digite.com'], 'zendesk_action': [], 'slot_set_action': [],
            'hubspot_forms_action': [], 'two_stage_fallback': [], 'kairon_bot_response': [], 'razorpay_action': [],
            'email_action': [], 'form_validation_action': [], 'prompt_action': [], 'database_action': [],
            'pyscript_action': [], 'web_search_action': [], 'live_agent_action': [], 'callback_action': [], 'schedule_action': [],
            'voice_call_action': [], 'kairon_voice_disconnect': [], 'store_page_action': [], 'agent_action': [],
            'utterances': ['utter_offer_help', 'utter_query', 'utter_goodbye', 'utter_feedback', 'utter_default',
                           'utter_please_rephrase'], 'parallel_action': []}, ignore_order=True)

    def test_delete_non_existing_complex_story(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match="Flow does not exists"):
            processor.delete_complex_story("5e564fbcdcf0d5fad89e3acd", "STORY", "tests", "testUser")

    def test_delete_empty_complex_story(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.delete_complex_story('5e564fbcdcf0d5fad89e3acd', "STORY", "tests", "testUser")

    def test_case_insensitive_delete_complex_story(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"},
        ]
        story_dict = {"name": "story2", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        story_id = processor.add_complex_story(story_dict, "tests", "testUser")
        processor.delete_complex_story(story_id, "STORY", "tests", "testUser")

    def test_delete_complex_story(self):
        processor = MongoProcessor()
        processor.delete_complex_story(pytest.story_id_two, "STORY", "tests", "testUser")

    def test_get_utterance_from_intent_non_existing(self):
        processor = MongoProcessor()
        user = "test_user"
        story = "new_story"
        action = story
        bot = "bot"
        intent = "greet_you"
        story_event = [StoryEvents(name=intent, type="user"),
                       StoryEvents(name="bot", type="slot", value=bot),
                       StoryEvents(name="http_action_config", type="slot", value=action),
                       StoryEvents(name="kairon_http_action", type="action")]
        cust = ResponseCustom(custom={"key": "value"})
        text = ResponseText(text="hello")

        Responses(
            name=intent,
            text=text,
            custom=cust,
            bot=bot,
            user=user
        ).save(validate=False).to_mongo()
        Stories(
            block_name=story,
            bot=bot,
            user=user,
            events=story_event
        ).save(validate=False).to_mongo()
        HttpActionConfig(
            action_name=action,
            response=HttpActionResponse(value="", dispatch=False),
            http_url="http://www.google.com",
            request_method="GET",
            bot=bot,
            user=user
        ).save().to_mongo()
        actual_action = processor.get_utterance_from_intent(intent="intent", bot=bot)
        assert actual_action[0] is None
        assert actual_action[1] is None

    def test_add_and_delete_non_integration_intent_by_integration_user(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        with pytest.raises(Exception):
            processor.delete_intent("TestingDelGreeting", "tests", "testUser1", is_integration=True,
                                    )

    def test_add_and_delete_integration_intent_by_same_integration_user(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting1", "tests", "testUser", is_integration=True)
        processor.delete_intent("TestingDelGreeting1", "tests", "testUser", is_integration=True,
                                )

    def test_add_and_delete_integration_intent_by_different_integration_user(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting2", "tests", "testUser", is_integration=True)
        processor.delete_intent("TestingDelGreeting2", "tests", "testUser2", is_integration=True,
                                )

    def test_add_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        rule_dict = {'name': "rule with action", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
        pytest.story_id = processor.add_complex_story(rule_dict, "tests", "testUser")
        story = Rules.objects(block_name="rule with action", bot="tests").get()
        assert len(story.events) == 4
        assert story.events[0].name == "..."
        assert story.events[0].type == "action"
        actions = processor.list_actions("tests")
        assert not DeepDiff(actions, {
            'actions': [], 'zendesk_action': [], 'hubspot_forms_action': [], 'two_stage_fallback': [],
            'http_action': ['my_http_action'], 'google_search_action': [], 'pipedrive_leads_action': [], 'kairon_bot_response': [],
            'razorpay_action': [], 'prompt_action': ['gpt_llm_faq'],
            'slot_set_action': [], 'email_action': [], 'form_validation_action': [], 'jira_action': [],
            'database_action': [], 'pyscript_action': [], 'web_search_action': [], 'live_agent_action': [],
            'callback_action': [], 'schedule_action': [], 'voice_call_action': [], 'parallel_action': [],
            'kairon_voice_disconnect': [], 'store_page_action': [], 'agent_action': [],
            'utterances': ['utter_greet',
                           'utter_cheer_up',
                           'utter_did_that_help',
                           'utter_happy',
                           'utter_goodbye',
                           'utter_iamabot',
                           'utter_feedback',
                           'utter_good_feedback',
                           'utter_bad_feedback',
                           'utter_default',
                           'utter_please_rephrase', 'utter_custom', 'utter_query', 'utter_more_queries',
                           'utter_catalog_test', 'utter_catalog_value_test',
                           'utter_non_catalog_test', 'utter_catalog_label_test',
                           'utter_catalog_empty_label_empty_test',
                           'utter_catalog_label_edit_test']},
                            ignore_order=True)

    def test_add_duplicate_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        with pytest.raises(Exception):
            rule_dict = {'name': "rule with action", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_rule_invalid_type(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        with pytest.raises(Exception):
            rule_dict = {'name': "rule with action", 'steps': steps, 'type': 'TEST', 'template_type': 'CUSTOM'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_duplicate_case_insensitive_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        with pytest.raises(Exception):
            rule_dict = {'name': "RUle with action", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_none_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': None, 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_empty_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': "", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_blank_rule_name(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': " ", 'steps': steps, 'type': 'rule', 'template_type': 'RULE'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_empty_rule_event(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            rule_dict = {'name': "empty path", 'steps': [], 'type': 'RULE', 'template_type': 'RULE'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_rule_with_multiple_intents(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "rule with multiple intents", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
        with pytest.raises(ValidationError,
                           match="Found rules 'rule with multiple intents' that contain more than user event.\nPlease use stories for this case"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_rule_with_invalid_event(self):
        processor = MongoProcessor()
        steps = [
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
        with pytest.raises(ValidationError, match="First event should be an user or conversation_start action"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
        with pytest.raises(ValidationError, match="user event should be followed by action"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "mood_sad", "type": "INTENT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
        with pytest.raises(ValidationError, match="Found 2 consecutive user events"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_update_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        rule_dict = {'name': "rule with action", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
        processor.update_complex_story(pytest.story_id, rule_dict, "tests", "testUser")
        rule = Rules.objects(block_name="rule with action", bot="tests").get()
        assert rule.events[2].name == "utter_nonsense"
        assert rule.events[0].name == "..."
        assert rule.events[0].type == "action"

    def test_case_insensitive_update_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        rule_dict = {'name': "RUle with action", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
        processor.update_complex_story(pytest.story_id, rule_dict, "tests", "testUser")
        rule = Rules.objects(block_name="rule with action", bot="tests").get()
        assert rule.events[4].name == "utter_greet"

    def test_update_non_existing_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        with pytest.raises(Exception):
            rule_dict = {'name': "non existing story", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
            processor.update_complex_story('non existing story_id', rule_dict, "tests", "testUser")

    def test_update_rule_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': None, 'steps': events, 'type': 'RULE', 'template_type': 'RULE'}
            processor.update_complex_story(pytest.story_id, rule_dict, "tests", "testUser")

    def test_fetch_stories_with_rules(self):
        processor = MongoProcessor()
        data = list(processor.get_stories("tests"))
        assert all(item['type'] in ['STORY', 'RULE'] for item in data)
        assert len(data) == 10

    def test_update_empty_rule_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': "", 'steps': events, 'type': 'RULE', 'template_type': 'RULE'}
            processor.update_complex_story(pytest.story_id, rule_dict, "tests", "testUser")

    def test_update_blank_rule_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': " ", 'steps': events, 'type': 'RULE', 'template_type': 'RULE'}
            processor.update_complex_story(pytest.story_id, rule_dict, "tests", "testUser")

    def test_update_empty_rule_event(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            rule_dict = {'name': "empty path", 'steps': [], 'type': 'RULE', 'template_type': 'RULE'}
            processor.update_complex_story(pytest.story_id, rule_dict, "tests", "testUser")

    def test_update_rule_invalid_type(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': "rule with action", 'steps': steps, 'type': 'TEST', 'template_type': 'RULE'}
            processor.update_complex_story(pytest.story_id, rule_dict, "tests", "testUser")

    def test_delete_non_existing_rule(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match="Flow does not exists"):
            processor.delete_complex_story("5e564fbcdcf0d5fad89e3acd", "RULE", "tests", "testUser")

    def test_update_rules_with_multiple_intents(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"}
        ]
        with pytest.raises(ValidationError,
                           match="Found rules 'rule with action' that contain more than user event.\nPlease use stories for this case"):
            rule_dict = {'name': "rule with action", 'steps': events, 'type': 'RULE', 'template_type': 'RULE'}
            processor.update_complex_story(pytest.story_id, rule_dict, "tests", "testUser")

    def test_update_rules_with_invalid_type(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "USER"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"}
        ]
        with pytest.raises(AppException, match="Invalid event type!"):
            rule_dict = {'name': "rule with action", 'steps': events, 'type': 'RULE', 'template_type': 'RULE'}
            processor.update_complex_story(pytest.story_id, rule_dict, "tests", "testUser")

    def test_delete_empty_rule(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.delete_complex_story('5e564fbcdcf0d5fad89e3acd', "RULE", "tests", "testUser")

    def test_case_insensitive_delete_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"},
        ]
        rule_dict = {"name": "rule2", 'steps': steps, 'type': 'RULE'}
        story_id = processor.add_complex_story(rule_dict, "tests", "testUser")
        processor.delete_complex_story(story_id, "RULE", "tests", "testUser")

    def test_update_rule_with_invalid_event(self):
        processor = MongoProcessor()
        steps = [
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'RULE'}
        with pytest.raises(ValidationError, match="First event should be an user"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'RULE'}
        with pytest.raises(ValidationError, match="user event should be followed by action"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "mood_sad", "type": "INTENT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'RULE'}
        with pytest.raises(ValidationError, match="Found 2 consecutive user events"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_delete_rule(self):
        processor = MongoProcessor()
        processor.delete_complex_story(pytest.story_id, "RULE", "tests", "testUser")

    def test_delete_rule_invalid_type(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match="Invalid type"):
            processor.delete_complex_story(pytest.story_id, "TEST", "tests", "testUser")

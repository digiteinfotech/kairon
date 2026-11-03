from tests.unit_test.data_processor.data_processor_support import *  # noqa: F403
from tests.unit_test.data_processor.data_processor_support import (
    MongoProcessorTestBase,
    fast_rasa_training,
)

class TestMongoProcessor(MongoProcessorTestBase):
    def test_add_form_with_any_slot(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['what is your name?', 'name?'], 'slot': 'name',
                 'slot_set': {'type': 'custom', 'value': 'Mahesh'}},
                {'ask_questions': ['what is your age?', 'age?'], 'slot': 'age',
                 'slot_set': {'type': 'current', 'value': 22}},
                {'ask_questions': ['what is your occupation?', 'occupation?'], 'slot': 'occupation',
                 'slot_set': {'type': 'slot', 'value': 'occupation'}},
                {'ask_questions': ['what is your order?', 'order?'], 'slot': 'order',
                 'slot_set': {'type': 'slot', 'value': 'order'}}
                ]
        bot = 'test'
        user = 'user'
        with pytest.raises(AppException, match="form will not accept any type slots: {'order'}"):
            processor.add_form('know_user', path, bot, user)

    def test_add_form(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['what is your name?', 'name?'], 'slot': 'name',
                 'slot_set': {'type': 'custom', 'value': 'Mahesh'}},
                {'ask_questions': ['what is your age?', 'age?'], 'slot': 'age',
                 'slot_set': {'type': 'current', 'value': 22}},
                {'ask_questions': ['what is your occupation?', 'occupation?'], 'slot': 'occupation',
                 'slot_set': {'type': 'slot', 'value': 'occupation'}}]
        bot = 'test'
        user = 'user'
        assert processor.add_form('know_user', path, bot, user)
        form = Forms.objects(name='know_user', bot=bot).get()
        assert form.required_slots == ['name', 'age', 'occupation']
        assert Utterances.objects(name='utter_ask_know_user_name', bot=bot,
                                  status=True).get().form_attached == 'know_user'
        assert Utterances.objects(name='utter_ask_know_user_age', bot=bot,
                                  status=True).get().form_attached == 'know_user'
        assert Utterances.objects(name='utter_ask_know_user_occupation', bot=bot,
                                  status=True).get().form_attached == 'know_user'
        resp = list(Responses.objects(name='utter_ask_know_user_name', bot=bot, status=True))
        assert resp[0].text.text == 'what is your name?'
        assert resp[1].text.text == 'name?'
        resp = list(Responses.objects(name='utter_ask_know_user_age', bot=bot, status=True))
        assert resp[0].text.text == 'what is your age?'
        assert resp[1].text.text == 'age?'
        resp = list(Responses.objects(name='utter_ask_know_user_occupation', bot=bot, status=True))
        assert resp[0].text.text == 'what is your occupation?'
        assert resp[1].text.text == 'occupation?'

    def test_add_utterance_to_form(self):
        bot = 'test'
        user = 'user'
        processor = MongoProcessor()
        assert processor.add_text_response('your occupation?', 'utter_ask_know_user_occupation', bot, user, 'know_user')

    def test_delete_utterance_from_form_2(self):
        bot = 'test'
        user = 'user'
        processor = MongoProcessor()
        resp = list(Responses.objects(name='utter_ask_know_user_occupation', bot=bot, status=True))
        assert resp[0].text.text == 'what is your occupation?'
        assert resp[1].text.text == 'occupation?'
        assert resp[2].text.text == 'your occupation?'
        assert not processor.delete_response(str(resp[2].id), bot, user=user)

    def test_add_utterance_to_form_not_exists(self):
        bot = 'test'
        user = 'user'
        processor = MongoProcessor()
        with pytest.raises(AppException, match="Form 'know_user_here' does not exists"):
            processor.add_text_response('give occupation', 'utter_ask_know_user_occupation', bot, user,
                                        'know_user_here')

    def test_create_flow_with_empty_step_name(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "", "type": "FORM_ACTION"},
            {"name": "know_user", "type": "FORM_START"},
            {"type": "FORM_END"},
            {"name": "utter_submit", "type": "BOT"},
        ]
        story_dict = {'name': "activate form", 'steps': steps, 'type': 'RULE', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="Empty name is allowed only for active_loop"):
            processor.add_complex_story(story_dict, bot, user)

    def test_create_flow_with_invalid_slot_value(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "age", "type": "SLOT", "value": {'a': 1}},
            {"name": "utter_greet", "type": "BOT"},
        ]
        story_dict = {'name': "slot form one", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="slot values must be either None or of type int, str or boolean"):
            processor.add_complex_story(story_dict, bot, user)

    def test_create_flow_with_invalid_events(self):
        bot = 'test'
        user = 'user'
        steps = [
            {"name": "hi", "type": "user"},
            {"name": "utter_hi", "type": "action", "value": "Hello"},
        ]
        events = [StoryEvents(**step) for step in steps]
        with pytest.raises(ValidationError, match="Value is allowed only for slot events"):
            Stories(block_name="invalid events flow", bot=bot, user=user, events=events).save()

    def test_create_flow_with_int_slot_value(self):
        processor = MongoProcessor()
        story_name = "slot form two"
        bot = 'test'
        user = 'user'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "age", "type": "SLOT", "value": 23},
            {"name": "utter_greet", "type": "BOT"},
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name=story_name, bot=bot).get()
        assert len(story['events']) == 3

    def test_create_flow_with_none_slot_value(self):
        processor = MongoProcessor()
        story_name = "slot form three"
        bot = 'test'
        user = 'user'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "age", "type": "SLOT", "value": None},
            {"name": "utter_greet", "type": "BOT"},
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name=story_name, bot=bot).get()
        assert len(story['events']) == 3

    def test_create_flow_with_bool_slot_value(self):
        processor = MongoProcessor()
        story_name = "slot form four"
        bot = 'test'
        user = 'user'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "food", "type": "SLOT", "value": True},
            {"name": "utter_greet", "type": "BOT"},
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name=story_name, bot=bot).get()
        assert len(story['events']) == 3

    def test_create_flow_with_str_slot_value(self):
        processor = MongoProcessor()
        story_name = "slot form five"
        bot = 'test'
        user = 'user'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "cuisine", "type": "SLOT", "value": 'Indian'},
            {"name": "utter_greet", "type": "BOT"},
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name=story_name, bot=bot).get()
        assert len(story['events']) == 3

    def test_create_two_stage_fallback_rule(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "nlu_fallback", "type": "INTENT"},
            {"name": KAIRON_TWO_STAGE_FALLBACK, "type": "TWO_STAGE_FALLBACK_ACTION"}
        ]
        story_dict = {'name': "activate two stage fallback", 'steps': steps, 'type': 'RULE', 'template_type': 'CUSTOM'}
        pytest.two_stage_fallback_story_id = processor.add_complex_story(story_dict, bot, user)
        rule = Rules.objects(block_name="activate two stage fallback", bot=bot,
                             events__name=KAIRON_TWO_STAGE_FALLBACK, status=True).get()
        assert rule.to_mongo().to_dict()['events'] == [{'name': '...', 'type': 'action'},
                                                       {'name': 'nlu_fallback', 'type': 'user'},
                                                       {'name': KAIRON_TWO_STAGE_FALLBACK, 'type': 'action'}]
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == "activate two stage fallback"]
        assert story_with_form[0]['steps'] == steps

    def test_create_form_activation_and_deactivation_rule(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "know_user", "type": "FORM_ACTION"},
            {"name": "know_user", "type": "FORM_START"},
            {"type": "FORM_END"},
            {"name": "utter_submit", "type": "BOT"},
        ]
        story_dict = {'name': "activate form", 'steps': steps, 'type': 'RULE', 'template_type': 'CUSTOM'}
        pytest.activate_form_story_id = processor.add_complex_story(story_dict, bot, user)
        rule = Rules.objects(block_name="activate form", bot=bot, events__name='know_user', status=True).get()
        assert rule.events[2].type == 'action'
        assert rule.events[3].name == 'know_user'
        assert rule.events[3].type == 'active_loop'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'activate form']
        assert story_with_form[0]['steps'] == steps

    def test_create_unhappy_path_form_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
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
        story_dict = {'name': "stop form - continue", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        pytest.form_continue_story_id = processor.add_complex_story(story_dict, bot, user)
        stories = Stories.objects(block_name="stop form - continue", bot=bot, events__name='know_user',
                                  status=True).get()
        assert stories.events[1].type == 'action'
        assert stories.events[2].type == 'active_loop'
        assert stories.events[2].name == 'know_user'
        assert stories.events[6].type == 'active_loop'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'stop form - continue']
        assert story_with_form[0]['steps'] == steps

    def test_create_unhappy_path_form_story_to_breakout(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "know_user", "type": "FORM_ACTION"},
            {"name": "know_user", "type": "FORM_START"},
            {"name": "deny", "type": "INTENT"},
            {"name": "utter_ask_continue", "type": "BOT"},
            {"name": "deny", "type": "INTENT"},
            {"type": "FORM_END"},
            {"name": "utter_submit", "type": "BOT"},
        ]
        story_dict = {'name': "stop form - stop", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        pytest.form_stop_story_id = processor.add_complex_story(story_dict, bot, user)
        stories = Stories.objects(block_name="stop form - stop", bot=bot, events__name='know_user', status=True).get()
        assert stories.events[1].type == 'action'
        assert stories.events[2].type == 'active_loop'
        assert stories.events[2].name == 'know_user'
        assert stories.events[6].type == 'active_loop'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'stop form - stop']
        assert story_with_form[0]['steps'] == steps

    def test_delete_slot_mapping_attached_to_form(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        with pytest.raises(AppException, match=re.escape('Slot mapping is required for form: [\'know_user\']')):
            processor.delete_slot_mapping("occupation", bot, user)

    def test_delete_slot_mapping_not_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        with pytest.raises(AppException, match='No slot mapping exists for slot: menu_card'):
            processor.delete_slot_mapping("menu_card", bot, user)

    def test_add_form_slots_not_exists(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['please give us your name?'], 'slot': 'name',
                 'mapping': [{'type': 'from_text', 'value': 'user', 'entity': 'name'},
                             {'type': 'from_entity', 'entity': 'name'}]},
                {'ask_questions': ['seats required?'], 'slot': 'num_people',
                 'mapping': [{'type': 'from_entity', 'intent': ['inform', 'request_restaurant'], 'entity': 'number'}]},
                {'ask_questions': ['type of cuisine?'], 'slot': 'cuisine',
                 'mapping': [{'type': 'from_entity', 'entity': 'cuisine'}]},
                {'ask_questions': ['outdoor seating required?'], 'slot': 'outdoor_seating',
                 'mapping': [{'type': 'from_entity', 'entity': 'seating'},
                             {'type': 'from_intent', 'intent': ['affirm'], 'value': True},
                             {'type': 'from_intent', 'intent': ['deny'], 'value': False}]},
                {'ask_questions': ['any preferences?'], 'slot': 'preferences',
                 'mapping': [{'type': 'from_text', 'not_intent': ['affirm']},
                             {'type': 'from_intent', 'intent': ['affirm'], 'value': 'no additional preferences'}]},
                {'ask_questions': ['Please give your feedback on your experience so far'], 'slot': 'feedback',
                 'mapping': [{'type': 'from_text'},
                             {'type': 'from_entity', 'entity': 'feedback'}]},
                ]
        bot = 'test'
        user = 'user'
        Slots(name='num_people', type="float", bot=bot, user=user).save()
        Slots(name='cuisine', type="text", bot=bot, user=user).save()

        with pytest.raises(AppException) as e:
            processor.add_form('form', path, bot, user)
            assert str(e).__contains__('slots not exists: {')

    def test_add_form_mapping_not_found(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['please give us your name?'], 'slot': 'name'},
                {'ask_questions': ['seats required?'], 'slot': 'num_people'},
                {'ask_questions': ['food choice?'], 'slot': 'category'},
                {'ask_questions': ['outdoor seating required?'], 'slot': 'outdoor_seating'}]
        bot = 'test'
        user = 'user'
        Slots(name='outdoor_seating', type="text", bot=bot, user=user).save()
        with pytest.raises(AppException, match=r"Mapping is required for slot: {.*}"):
            processor.add_form('restaurant_form', path, bot, user)

    def test_add_form_2(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['please give us your name?'], 'slot': 'name',
                 'slot_set': {'type': 'custom', 'value': 'Mahesh'}},
                {'ask_questions': ['seats required?'], 'slot': 'num_people',
                 'slot_set': {'type': 'current', 'value': 10}},
                {'ask_questions': ['type of cuisine?'], 'slot': 'cuisine',
                 'slot_set': {'type': 'slot', 'value': 'cuisine'}},
                {'ask_questions': ['outdoor seating required?'], 'slot': 'outdoor_seating'},
                {'ask_questions': ['any preferences?'], 'slot': 'preferences'},
                {'ask_questions': ['Please give your feedback on your experience so far'], 'slot': 'feedback',
                 'slot_set': {'type': 'custom', 'value': 'Very Nice!'}}]
        bot = 'test'
        user = 'user'
        slot = {"slot": "num_people",
                'mapping': {'type': 'from_entity', 'intent': ['inform', 'request_restaurant'], 'entity': 'number'}}
        processor.add_slot_mapping(slot, bot, user)
        slot = {"slot": "cuisine", 'mapping': {'type': 'from_entity', 'entity': 'cuisine'}}
        processor.add_slot_mapping(slot, bot, user)
        slot = {"slot": "outdoor_seating",
                'mapping': [{'type': 'from_entity', 'entity': 'seating'},
                            {'type': 'from_intent', 'intent': ['affirm'], 'value': True},
                            {'type': 'from_intent', 'intent': ['deny'], 'value': False}]}
        processor.add_slot({"name": "outdoor_seating", "type": "text", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)
        for s in slot['mapping']:
            processor.add_slot_mapping({"slot": slot["slot"], "mapping": s}, bot, user)
        slot = {"slot": "preferences",
                'mapping': [{'type': 'from_text', 'not_intent': ['affirm']},
                            {'type': 'from_intent', 'intent': ['affirm'], 'value': 'no additional preferences'}]}
        processor.add_slot({"name": "preferences", "type": "text", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)
        for s in slot['mapping']:
            processor.add_slot_mapping({"slot": slot["slot"], "mapping": s}, bot, user)
        slot = {"slot": "feedback", 'mapping': [{'type': 'from_text'},
                                                {'type': 'from_entity', 'entity': 'feedback'}]}
        processor.add_slot({"name": "feedback", "type": "text", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)
        for s in slot['mapping']:
            processor.add_slot_mapping({"slot": slot["slot"], "mapping": s}, bot, user)

        assert processor.add_form('restaurant_form', path, bot, user)
        form = Forms.objects(name='restaurant_form', bot=bot, status=True).get()
        assert form.required_slots == ['name', 'num_people', 'cuisine', 'outdoor_seating', 'preferences', 'feedback']
        assert Utterances.objects(name='utter_ask_restaurant_form_name', bot=bot, status=True).get()
        assert Utterances.objects(name='utter_ask_restaurant_form_num_people', bot=bot, status=True).get()
        assert Utterances.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()
        assert Utterances.objects(name='utter_ask_restaurant_form_outdoor_seating', bot=bot, status=True).get()
        assert Utterances.objects(name='utter_ask_restaurant_form_preferences', bot=bot, status=True).get()
        assert Utterances.objects(name='utter_ask_restaurant_form_feedback', bot=bot, status=True).get()
        assert Responses.objects(name='utter_ask_restaurant_form_name', bot=bot,
                                 status=True).get().text.text == 'please give us your name?'
        assert Responses.objects(name='utter_ask_restaurant_form_num_people', bot=bot,
                                 status=True).get().text.text == 'seats required?'
        assert Responses.objects(name='utter_ask_restaurant_form_cuisine', bot=bot,
                                 status=True).get().text.text == 'type of cuisine?'
        assert Responses.objects(name='utter_ask_restaurant_form_outdoor_seating', bot=bot,
                                 status=True).get().text.text == 'outdoor seating required?'
        assert Responses.objects(name='utter_ask_restaurant_form_preferences', bot=bot,
                                 status=True).get().text.text == 'any preferences?'
        assert Responses.objects(name='utter_ask_restaurant_form_feedback', bot=bot,
                                 status=True).get().text.text == 'Please give your feedback on your experience so far'

        validations_added = list(FormValidationAction.objects(name='validate_restaurant_form', bot=bot, status=True))
        assert len(validations_added) == 6
        assert validations_added[0].slot == 'name'
        assert validations_added[0].is_required
        assert validations_added[0].slot_set.type == 'custom'
        assert validations_added[0].slot_set.value == 'Mahesh'
        assert validations_added[1].slot == 'num_people'
        assert validations_added[1].is_required
        assert validations_added[1].slot_set.type == 'current'
        assert validations_added[1].slot_set.value == 10
        assert validations_added[2].slot == 'cuisine'
        assert validations_added[2].is_required
        assert validations_added[2].slot_set.type == 'slot'
        assert validations_added[2].slot_set.value == 'cuisine'
        assert validations_added[3].slot == 'outdoor_seating'
        assert validations_added[3].is_required
        assert validations_added[3].slot_set.type == 'current'
        assert not validations_added[3].slot_set.value
        assert validations_added[4].slot == 'preferences'
        assert validations_added[4].is_required
        assert validations_added[4].slot_set.type == 'current'
        assert not validations_added[4].slot_set.value
        assert validations_added[5].slot == 'feedback'
        assert validations_added[5].is_required
        assert validations_added[5].slot_set.type == 'custom'
        assert validations_added[5].slot_set.value == "Very Nice!"

    def test_add_number_slot_with_min_max(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'

        processor.add_slot({"name": "na", "type": "float", "initial_value": 0.2,
                            "max_value": 0.5, "min_value": 0.1,
                            "influence_conversation": True}, bot, user, raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='na', bot=bot, user=user).get()
        assert slot['name'] == 'na'
        assert slot['type'] == "float"
        assert slot['max_value'] == 0.5
        assert slot['min_value'] == 0.1

    def test_delete_slot_exist(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'

        processor.delete_slot(slot_name='na', bot=bot, user=user)

        with pytest.raises(DoesNotExist):
            Slots.objects(name__iexact='na', bot=bot).get()
        assert not Entities.objects(name='na', bot=bot, status=True)

    def test_delete_slot_having_slot_mapping_attached_1(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        slot_name = 'na'
        slot = {"name": slot_name, "type": "any", "initial_value": None, "influence_conversation": False}
        mapping = {"slot": slot_name, 'mapping': {'type': 'from_entity', 'entity': 'name'}}
        processor.add_slot(slot_value=slot, bot=bot, user=user)
        processor.add_slot_mapping(mapping, bot, user)

        with pytest.raises(AppException, match="Cannot delete slot without removing its mappings!"):
            processor.delete_slot(slot_name=slot_name, bot=bot, user=user)

        processor.delete_slot_mapping(slot_name, bot, user)
        processor.delete_slot(slot_name=slot_name, bot=bot, user=user)

    def test_add_form_already_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        with pytest.raises(AppException, match="Form with the name 'restaurant_form' already exists"):
            processor.add_form('restaurant_form', [], bot, user)

    def test_add_form_name_empty(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        with pytest.raises(AppException, match='Form name cannot be empty or spaces'):
            processor.add_form(' ', [], bot, user)

    def test_add_form_no_entity_and_mapping_type(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['what is your name?'], 'slot': 'name'},
                {'ask_questions': ['what is your age?'], 'slot': 'age'},
                {'ask_questions': ['where are you located?'], 'slot': 'category'}]
        bot = 'test'
        user = 'user'
        with pytest.raises(AppException, match="Mapping is required for slot: {'category'}"):
            processor.add_form('get_user', path, bot, user)

    def test_add_form_with_validations(self):
        processor = MongoProcessor()
        name_validation = "if (&& name.contains('i') && name.length() > 4 || !name.contains(" ")) " \
                          "{return true;} else {return false;}"
        age_validation = "if (age > 10 && age < 70) {return true;} else {return false;}"
        occupation_validation = "if (occupation in ['teacher', 'programmer', 'student', 'manager'] " \
                                "&& !occupation.contains(" ") && occupation.length() > 20) " \
                                "{return true;} else {return false;}"
        path = [{'ask_questions': ['your name?', 'ur name?'], 'slot': 'name',
                 'validation_semantic': name_validation,
                 'valid_response': 'got it',
                 'is_required': False,
                 'slot_set': {'type': 'custom', 'value': 'Mahesh'},
                 'invalid_response': 'please rephrase'},
                {'ask_questions': ['your age?', 'ur age?'], 'slot': 'age',
                 'validation_semantic': age_validation,
                 'valid_response': 'valid entry',
                 'is_required': True,
                 'slot_set': {'type': 'current', 'value': 22},
                 'invalid_response': 'please enter again'
                 },
                {'ask_questions': ['your occupation?', 'ur occupation?'], 'slot': 'occupation',
                 'validation_semantic': occupation_validation, 'is_required': False,
                 'slot_set': {'type': 'slot', 'value': 'occupation'}}]
        bot = 'test'
        user = 'user'
        assert processor.add_form('know_user_form', path, bot, user)
        form = Forms.objects(name='know_user_form', bot=bot).get()
        assert form.required_slots == ['name', 'age', 'occupation']
        assert Utterances.objects(name='utter_ask_know_user_form_name', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        assert Utterances.objects(name='utter_ask_know_user_form_age', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        assert Utterances.objects(name='utter_ask_know_user_form_occupation', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        resp = list(Responses.objects(name='utter_ask_know_user_form_name', bot=bot, status=True))
        assert resp[0].text.text == 'your name?'
        assert resp[1].text.text == 'ur name?'
        resp = list(Responses.objects(name='utter_ask_know_user_form_age', bot=bot, status=True))
        assert resp[0].text.text == 'your age?'
        assert resp[1].text.text == 'ur age?'
        resp = list(Responses.objects(name='utter_ask_know_user_form_occupation', bot=bot, status=True))
        assert resp[0].text.text == 'your occupation?'
        assert resp[1].text.text == 'ur occupation?'

        validations_added = list(FormValidationAction.objects(name='validate_know_user_form', bot=bot, status=True))
        assert len(validations_added) == 3
        assert validations_added[0].slot == 'name'
        assert validations_added[0].validation_semantic == "if (&& name.contains('i') && name.length() > 4 || " \
                                                           "!name.contains(" ")) {return true;} else {return false;}"
        assert validations_added[0].valid_response == 'got it'
        assert validations_added[0].invalid_response == 'please rephrase'
        assert not validations_added[0].is_required
        assert validations_added[0].slot_set.type == 'custom'
        assert validations_added[0].slot_set.value == 'Mahesh'

        assert validations_added[1].slot == 'age'
        assert validations_added[1].validation_semantic == \
               "if (age > 10 && age < 70) {return true;} else {return false;}"
        assert validations_added[1].valid_response == 'valid entry'
        assert validations_added[1].invalid_response == 'please enter again'
        assert validations_added[1].is_required
        assert validations_added[1].slot_set.type == 'current'
        assert validations_added[1].slot_set.value == 22

        assert validations_added[2].slot == 'occupation'
        assert validations_added[2].validation_semantic == \
               "if (occupation in ['teacher', 'programmer', 'student', 'manager'] && !occupation.contains(" ") " \
               "&& occupation.length() > 20) {return true;} else {return false;}"
        assert not validations_added[2].valid_response
        assert not validations_added[2].invalid_response
        assert not validations_added[2].is_required
        assert validations_added[2].slot_set.type == 'slot'
        assert validations_added[2].slot_set.value == 'occupation'

    def test_list_forms(self):
        processor = MongoProcessor()
        forms = list(processor.list_forms('test'))
        assert len(forms) == 5
        assert len([f['name'] for f in forms]) == 5
        assert len([f['_id'] for f in forms]) == 5
        required_slots = [f['required_slots'] for f in forms]
        assert required_slots == [['date_time', 'priority'], ['file'], ['name', 'age', 'occupation'],
                                  ['name', 'num_people', 'cuisine', 'outdoor_seating', 'preferences', 'feedback'],
                                  ['name', 'age', 'occupation']]

    def test_list_forms_no_form_added(self):
        processor = MongoProcessor()
        forms = list(processor.list_forms('new_bot'))
        assert forms == []

    def test_get_form(self):
        processor = MongoProcessor()
        forms = list(processor.list_forms('test'))
        form_id = [f['_id'] for f in forms if f['name'] == 'know_user'][0]
        form = processor.get_form(form_id, 'test')
        assert form['settings'][0]['slot'] == 'name'
        assert form['settings'][1]['slot'] == 'age'
        assert form['settings'][2]['slot'] == 'occupation'
        assert form['settings'][0]['ask_questions'][0]['_id']
        assert form['settings'][0]['ask_questions'][0]['value'] == {'text': 'name?'}
        assert form['settings'][0]['ask_questions'][1]['value'] == {'text': 'what is your name?'}
        assert form['settings'][1]['ask_questions'][0]['_id']
        assert form['settings'][1]['ask_questions'][0]['value'] == {'text': 'age?'}
        assert form['settings'][1]['ask_questions'][1]['value'] == {'text': 'what is your age?'}
        assert form['settings'][2]['ask_questions'][0]['_id']
        assert form['settings'][2]['ask_questions'][0]['value'] == {'text': 'occupation?'}
        assert form['settings'][2]['ask_questions'][1]['value'] == {'text': 'what is your occupation?'}
        assert form['settings'][0]['slot_set'] == {'type': 'custom', 'value': 'Mahesh'}
        assert not form['settings'][0]['validation_semantic']
        assert not form['settings'][0]['invalid_response']
        assert not form['settings'][0]['valid_response']
        assert form['settings'][1]['slot_set'] == {'type': 'current', 'value': 22}
        assert not form['settings'][1]['validation_semantic']
        assert not form['settings'][1]['invalid_response']
        assert not form['settings'][1]['valid_response']
        assert form['settings'][2]['slot_set'] == {'type': 'slot', 'value': 'occupation'}
        assert not form['settings'][2]['validation_semantic']
        assert not form['settings'][2]['invalid_response']
        assert not form['settings'][2]['valid_response']

    def test_get_form_with_validations(self):
        processor = MongoProcessor()
        forms = list(processor.list_forms('test'))
        form_id = [f['_id'] for f in forms if f['name'] == 'know_user_form'][0]
        form = processor.get_form(form_id, 'test')
        assert form['settings'][0]['slot'] == 'name'
        assert form['settings'][1]['slot'] == 'age'
        assert form['settings'][2]['slot'] == 'occupation'
        assert form['settings'][0]['ask_questions'][0]['_id']
        assert form['settings'][0]['ask_questions'][0]['value']['text']
        assert form['settings'][0]['ask_questions'][1]['value']['text']
        assert form['settings'][1]['ask_questions'][0]['_id']
        assert form['settings'][1]['ask_questions'][0]['value']['text']
        assert form['settings'][1]['ask_questions'][1]['value']['text']
        assert form['settings'][2]['ask_questions'][0]['_id']
        assert form['settings'][2]['ask_questions'][0]['value']['text']
        assert form['settings'][2]['ask_questions'][1]['value']['text']
        assert form['settings'][0]['validation_semantic'] == "if (&& name.contains('i') && name.length() > 4 || " \
                                                             "!name.contains(" ")) {return true;} else {return false;}"
        assert form['settings'][0]['invalid_response'] == 'please rephrase'
        assert form['settings'][0]['valid_response'] == 'got it'
        assert not form['settings'][0]['is_required']
        assert form['settings'][0]['slot_set'] == {'type': 'custom', 'value': 'Mahesh'}
        assert form['settings'][1]['validation_semantic'] == \
               "if (age > 10 && age < 70) {return true;} else {return false;}"
        assert form['settings'][1]['invalid_response'] == 'please enter again'
        assert form['settings'][1]['valid_response'] == 'valid entry'
        assert form['settings'][1]['is_required']
        assert form['settings'][1]['slot_set'] == {'type': 'current', 'value': 22}
        assert form['settings'][2]['validation_semantic'] == \
               "if (occupation in ['teacher', 'programmer', 'student', 'manager'] && !occupation.contains(" ") " \
               "&& occupation.length() > 20) {return true;} else {return false;}"
        assert not form['settings'][2]['invalid_response']
        assert not form['settings'][2]['valid_response']
        assert not form['settings'][2]['is_required']
        assert form['settings'][2]['slot_set'] == {'type': 'slot', 'value': 'occupation'}

    def test_get_form_not_added(self):
        import mongomock

        with pytest.raises(AppException, match='Form does not exists'):
            MongoProcessor().get_form(mongomock.ObjectId().__str__(), 'test')

    def test_get_form_having_on_intent_and_not_intent(self):
        processor = MongoProcessor()
        forms = list(processor.list_forms('test'))
        form_id = [f['_id'] for f in forms if f['name'] == 'restaurant_form'][0]
        form = MongoProcessor().get_form(form_id, 'test')
        assert form['settings'][0]['slot'] == 'name'
        assert form['settings'][1]['slot'] == 'num_people'
        assert form['settings'][2]['slot'] == 'cuisine'
        assert form['settings'][3]['slot'] == 'outdoor_seating'
        assert form['settings'][4]['slot'] == 'preferences'
        assert form['settings'][5]['slot'] == 'feedback'
        assert form['settings'][0]['ask_questions'][0]['_id']
        assert form['settings'][1]['ask_questions'][0]['_id']
        assert form['settings'][2]['ask_questions'][0]['_id']
        assert form['settings'][3]['ask_questions'][0]['_id']
        assert form['settings'][4]['ask_questions'][0]['_id']
        assert form['settings'][5]['ask_questions'][0]['_id']
        assert form['settings'][0]['ask_questions'][0]['value']['text']
        assert form['settings'][1]['ask_questions'][0]['value']['text']
        assert form['settings'][2]['ask_questions'][0]['value']['text']
        assert form['settings'][3]['ask_questions'][0]['value']['text']
        assert form['settings'][4]['ask_questions'][0]['value']['text']
        assert form['settings'][5]['ask_questions'][0]['value']['text']

    def test_edit_form_slot_not_present(self):
        processor = MongoProcessor()
        path = [{'ask_questions': 'which location would you prefer?', 'slot': 'restaurant_location',
                 'mapping': [{'type': 'from_text', 'value': 'user', 'entity': 'location'},
                             {'type': 'from_entity', 'entity': 'location'}]},
                {'ask_questions': 'seats required?', 'slot': 'num_people',
                 'mapping': [{'type': 'from_entity', 'intent': ['inform', 'request_restaurant'], 'entity': 'number'}]},
                {'ask_questions': 'type of cuisine?', 'slot': 'cuisine',
                 'mapping': [{'type': 'from_entity', 'entity': 'cuisine'}]},
                {'ask_questions': 'outdoor seating required?', 'slot': 'outdoor_seating',
                 'mapping': [{'type': 'from_entity', 'entity': 'seating'},
                             {'type': 'from_intent', 'intent': ['affirm'], 'value': True},
                             {'type': 'from_intent', 'intent': ['deny'], 'value': False}]},
                {'ask_questions': 'any preferences?', 'slot': 'preferences',
                 'mapping': [{'type': 'from_text', 'not_intent': ['affirm']},
                             {'type': 'from_intent', 'intent': ['affirm'], 'value': 'no additional preferences'}]},
                {'ask_questions': 'do you want to go with an AC room?', 'slot': 'ac_required',
                 'mapping': [{'type': 'from_intent', 'intent': ['affirm'], 'value': True},
                             {'type': 'from_intent', 'intent': ['deny'], 'value': False}]},
                {'ask_questions': 'Please give your feedback on your experience so far', 'slot': 'feedback',
                 'mapping': [{'type': 'from_text'},
                             {'type': 'from_entity', 'entity': 'feedback'}]}
                ]
        bot = 'test'
        user = 'user'

        with pytest.raises(AppException) as e:
            processor.edit_form('restaurant_form', path, bot, user)
            assert str(e).__contains__('slots not exists: {')

    def test_edit_form_change_validations(self):
        processor = MongoProcessor()
        name_validation = "if (&& name.contains('i') && name.length() > 4 || " \
                          "!name.contains(" ")) {return true;} else {return false;}"
        age_validation = "if (age > 10 && age < 70) {return true;} else {return false;}"
        path = [{'ask_questions': ['what is your name?', 'name?'], 'slot': 'name',
                 'validation_semantic': name_validation,
                 'valid_response': 'got it',
                 'is_required': True,
                 'slot_set': {'type': 'custom', 'value': 'Mahesh'},
                 'invalid_response': 'please rephrase'},
                {'ask_questions': ['what is your age?', 'age?'], 'slot': 'age',
                 'validation_semantic': age_validation,
                 'valid_response': 'valid entry',
                 'invalid_response': 'please enter again',
                 'is_required': False,
                 'slot_set': {'type': 'current', 'value': 22}
                 },
                {'ask_questions': ['what is your occupation?', 'occupation?'], 'slot': 'occupation',
                 'validation_semantic': None, 'is_required': False,
                 'slot_set': {'type': 'slot', 'value': 'occupation'}}]
        bot = 'test'
        user = 'user'
        processor.edit_form('know_user_form', path, bot, user)
        form = Forms.objects(name='know_user_form', bot=bot).get()
        assert form.required_slots == ['name', 'age', 'occupation']
        assert Utterances.objects(name='utter_ask_know_user_form_name', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        assert Utterances.objects(name='utter_ask_know_user_form_age', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        assert Utterances.objects(name='utter_ask_know_user_form_occupation', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        resp = list(Responses.objects(name='utter_ask_know_user_form_name', bot=bot, status=True))
        assert resp[0].text.text == 'your name?'
        assert resp[1].text.text == 'ur name?'
        resp = list(Responses.objects(name='utter_ask_know_user_form_age', bot=bot, status=True))
        assert resp[0].text.text == 'your age?'
        assert resp[1].text.text == 'ur age?'
        resp = list(Responses.objects(name='utter_ask_know_user_form_occupation', bot=bot, status=True))
        assert resp[0].text.text == 'your occupation?'
        assert resp[1].text.text == 'ur occupation?'

        validations_added = list(FormValidationAction.objects(name='validate_know_user_form', bot=bot, status=True))
        assert len(validations_added) == 3
        assert validations_added[0].slot == 'name'
        assert validations_added[0].validation_semantic == \
               "if (&& name.contains('i') && name.length() > 4 || " \
               "!name.contains(" ")) {return true;} else {return false;}"
        assert validations_added[0].valid_response == 'got it'
        assert validations_added[0].invalid_response == 'please rephrase'
        assert validations_added[0].is_required
        assert validations_added[0].slot_set.type == 'custom'
        assert validations_added[0].slot_set.value == 'Mahesh'

        assert validations_added[1].slot == 'age'
        assert validations_added[1].validation_semantic == \
               "if (age > 10 && age < 70) {return true;} else {return false;}"
        assert validations_added[1].valid_response == 'valid entry'
        assert validations_added[1].invalid_response == 'please enter again'
        assert not validations_added[1].is_required
        assert validations_added[1].slot_set.type == 'current'
        assert validations_added[1].slot_set.value == 22

        assert validations_added[2].slot == 'occupation'
        assert not validations_added[2].validation_semantic
        assert not validations_added[2].is_required
        assert validations_added[2].slot_set.type == 'slot'
        assert validations_added[2].slot_set.value == 'occupation'

    def test_edit_form_remove_validations(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['what is your name?', 'name?'], 'slot': 'name',
                 'mapping': [{'type': 'from_text', 'value': 'user', 'entity': 'name'},
                             {'type': 'from_entity', 'entity': 'name'}],
                 'validation_semantic': None,
                 'is_required': True,
                 'slot_set': {'type': 'custom', 'value': 'Mahesh'},
                 'valid_response': 'got it',
                 'invalid_response': 'please rephrase'},
                {'ask_questions': ['what is your age?', 'age?'], 'slot': 'age',
                 'mapping': [{'type': 'from_intent', 'intent': ['get_age'], 'entity': 'age', 'value': '18'}],
                 'validation_semantic': None,
                 'is_required': True,
                 'slot_set': {'type': 'current', 'value': 22},
                 'valid_response': 'valid entry',
                 'invalid_response': 'please enter again'
                 },
                {'ask_questions': ['what is your occupation?', 'occupation?'], 'slot': 'occupation',
                 'mapping': [
                     {'type': 'from_intent', 'intent': ['get_occupation'], 'entity': 'occupation', 'value': 'business'},
                     {'type': 'from_text', 'entity': 'occupation', 'value': 'engineer'},
                     {'type': 'from_entity', 'entity': 'occupation'},
                     {'type': 'from_trigger_intent', 'entity': 'occupation', 'value': 'tester',
                      'intent': ['get_business', 'is_engineer', 'is_tester'], 'not_intent': ['get_age', 'get_name']}],
                 'validation_semantic': None, 'is_required': False,
                 'slot_set': {'type': 'slot', 'value': 'occupation'}}]
        bot = 'test'
        user = 'user'
        processor.edit_form('know_user_form', path, bot, user)
        form = Forms.objects(name='know_user_form', bot=bot).get()
        assert form.required_slots == ['name', 'age', 'occupation']
        assert Utterances.objects(name='utter_ask_know_user_form_name', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        assert Utterances.objects(name='utter_ask_know_user_form_age', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        assert Utterances.objects(name='utter_ask_know_user_form_occupation', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        resp = list(Responses.objects(name='utter_ask_know_user_form_name', bot=bot, status=True))
        assert resp[0].text.text == 'your name?'
        assert resp[1].text.text == 'ur name?'
        resp = list(Responses.objects(name='utter_ask_know_user_form_age', bot=bot, status=True))
        assert resp[0].text.text == 'your age?'
        assert resp[1].text.text == 'ur age?'
        resp = list(Responses.objects(name='utter_ask_know_user_form_occupation', bot=bot, status=True))
        assert resp[0].text.text == 'your occupation?'
        assert resp[1].text.text == 'ur occupation?'

        validations = list(FormValidationAction.objects(name='validate_know_user_form', bot=bot, status=True))
        assert len(validations) == 3
        assert not validations[0].validation_semantic
        assert validations[0].valid_response == 'got it'
        assert validations[0].invalid_response == 'please rephrase'
        assert validations[0].is_required
        assert validations[0].slot_set.type == 'custom'
        assert validations[0].slot_set.value == 'Mahesh'
        assert not validations[1].validation_semantic
        assert validations[1].valid_response == 'valid entry'
        assert validations[1].invalid_response == 'please enter again'
        assert validations[1].is_required
        assert validations[1].slot_set.type == 'current'
        assert validations[1].slot_set.value == 22
        assert not validations[2].validation_semantic
        assert not validations[2].valid_response
        assert not validations[2].invalid_response
        assert not validations[2].is_required
        assert validations[2].slot_set.type == 'slot'
        assert validations[2].slot_set.value == 'occupation'

    def test_edit_form_add_validations(self):
        processor = MongoProcessor()
        name_validation = "if (&& name.contains('i') && name.length() > 4 || " \
                          "!name.contains(" ")) {return true;} else {return false;}"
        path = [{'ask_questions': ['what is your name?', 'name?'], 'slot': 'name',
                 'validation_semantic': name_validation,
                 'valid_response': 'got it',
                 'is_required': False,
                 'slot_set': {'type': 'custom', 'value': 'Mahesh'},
                 'invalid_response': 'please rephrase'},
                {'ask_questions': ['what is your age?', 'age?'], 'slot': 'age',
                 'validation_semantic': None,
                 'is_required': True,
                 'slot_set': {'type': 'current', 'value': 22},
                 'valid_response': 'valid entry',
                 'invalid_response': 'please enter again'
                 },
                {'ask_questions': ['what is your occupation?', 'occupation?'], 'slot': 'occupation',
                 'validation_semantic': None, 'is_required': False,
                 'slot_set': {'type': 'slot', 'value': 'occupation'}}]
        bot = 'test'
        user = 'user'
        processor.edit_form('know_user_form', path, bot, user)

        validations_added = list(FormValidationAction.objects(name='validate_know_user_form', bot=bot, status=True))
        assert len(validations_added) == 3
        assert validations_added[0].slot == 'name'
        assert validations_added[0].validation_semantic == "if (&& name.contains('i') && name.length() > 4 || " \
                                                           "!name.contains(" ")) {return true;} else {return false;}"
        assert validations_added[0].valid_response == 'got it'
        assert validations_added[0].invalid_response == 'please rephrase'
        assert not validations_added[0].is_required
        assert validations_added[0].slot_set.type == 'custom'
        assert validations_added[0].slot_set.value == 'Mahesh'
        assert validations_added[1].is_required
        assert validations_added[1].slot_set.type == 'current'
        assert validations_added[1].slot_set.value == 22
        assert not validations_added[2].is_required
        assert validations_added[2].slot_set.type == 'slot'
        assert validations_added[2].slot_set.value == 'occupation'

    def test_edit_form_with_any_slot(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['which location would you prefer?'], 'slot': 'location',
                 'slot_set': {'type': 'custom', 'value': 'Bangalore'}},
                {'ask_questions': ['seats required?'], 'slot': 'num_people',
                 'slot_set': {'type': 'current', 'value': 10}},
                {'ask_questions': ['type of cuisine?'], 'slot': 'cuisine',
                 'validation_semantic': "if (&& cuisine.contains('i') && cuisine.length() > 4 || "
                                        "!cuisine.contains(" ")) {return true;} else {return false;}",
                 'slot_set': {'type': 'current', 'value': 'Indian Cuisine'}},
                {'ask_questions': ['outdoor seating required?'], 'slot': 'outdoor_seating',
                 'slot_set': {'type': 'custom', 'value': True}},
                {'ask_questions': ['any preferences?'], 'slot': 'preferences',
                 'slot_set': {'type': 'current'}},
                {'ask_questions': ['do you want to go with an AC room?'], 'slot': 'ac_required',
                 'slot_set': {'type': 'slot', 'value': 'ac_required'}},
                {'ask_questions': ['Please give your feedback on your experience so far'], 'slot': 'feedback',
                 'slot_set': {'type': 'custom', 'value': 'Very Nice!'}}]
        bot = 'test'
        user = 'user'
        slot = {"slot": "ac_required",
                'mapping': {'type': 'from_intent', 'intent': ['affirm'], 'value': True}}
        slot2 = {"slot": "ac_required",
                  'mapping': {'type': 'from_intent', 'intent': ['deny'], 'value': False}}
        processor.add_slot({"name": "ac_required", "type": "any", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)
        processor.add_slot_mapping(slot, bot, user)
        processor.add_slot_mapping(slot2, bot, user)

        with pytest.raises(AppException, match="form will not accept any type slots: {'ac_required'}"):
            processor.edit_form('restaurant_form', path, bot, user)

    def test_edit_form_remove_and_add_slots(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['which location would you prefer?'], 'slot': 'location',
                 'slot_set': {'type': 'custom', 'value': 'Bangalore'}},
                {'ask_questions': ['seats required?'], 'slot': 'num_people',
                 'slot_set': {'type': 'current', 'value': 10}},
                {'ask_questions': ['type of cuisine?'], 'slot': 'cuisine',
                 'validation_semantic': "if (&& cuisine.contains('i') && cuisine.length() > 4 || "
                                        "!cuisine.contains(" ")) {return true;} else {return false;}",
                 'slot_set': {'type': 'current', 'value': 'Indian Cuisine'}},
                {'ask_questions': ['outdoor seating required?'], 'slot': 'outdoor_seating',
                 'slot_set': {'type': 'custom', 'value': True}},
                {'ask_questions': ['any preferences?'], 'slot': 'preferences',
                 'slot_set': {'type': 'current'}},
                {'ask_questions': ['do you want to go with an AC room?'], 'slot': 'ac_required',
                 'slot_set': {'type': 'slot', 'value': 'ac_required'}},
                {'ask_questions': ['Please give your feedback on your experience so far'], 'slot': 'feedback',
                 'slot_set': {'type': 'custom', 'value': 'Very Nice!'}}]
        bot = 'test'
        user = 'user'
        slot = {"slot": "ac_required",
                'mapping': {'type': 'from_intent', 'intent': ['affirm'], 'value': True}}
        slot2 = {"slot": "ac_required",
                'mapping':{'type': 'from_intent', 'intent': ['deny'], 'value': False}}
        processor.add_slot({"name": "ac_required", "type": "text", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)
        processor.delete_slot_mapping('ac_required', bot, user)
        processor.add_slot_mapping(slot, bot, user)
        processor.add_slot_mapping(slot2, bot, user)

        processor.edit_form('restaurant_form', path, bot, user)
        form = Forms.objects(name='restaurant_form', bot=bot, status=True).get()
        assert form.required_slots == ['location', 'num_people', 'cuisine', 'outdoor_seating', 'preferences',
                                       'ac_required', 'feedback']
        assert Utterances.objects(name='utter_ask_restaurant_form_location', bot=bot,
                                  status=True).get().form_attached == 'restaurant_form'
        assert Utterances.objects(name='utter_ask_restaurant_form_num_people', bot=bot,
                                  status=True).get().form_attached == 'restaurant_form'
        assert Utterances.objects(name='utter_ask_restaurant_form_cuisine', bot=bot,
                                  status=True).get().form_attached == 'restaurant_form'
        assert Utterances.objects(name='utter_ask_restaurant_form_outdoor_seating', bot=bot,
                                  status=True).get().form_attached == 'restaurant_form'
        assert Utterances.objects(name='utter_ask_restaurant_form_preferences', bot=bot,
                                  status=True).get().form_attached == 'restaurant_form'
        assert Utterances.objects(name='utter_ask_restaurant_form_feedback', bot=bot,
                                  status=True).get().form_attached == 'restaurant_form'
        assert Utterances.objects(name='utter_ask_restaurant_form_ac_required', bot=bot,
                                  status=True).get().form_attached == 'restaurant_form'
        with pytest.raises(DoesNotExist):
            Utterances.objects(name='utter_ask_restaurant_form_name', bot=bot, status=True).get()
        with pytest.raises(DoesNotExist):
            Responses.objects(name='utter_ask_restaurant_form_name', bot=bot, status=True).get()
        assert Responses.objects(name='utter_ask_restaurant_form_location',
                                 bot=bot, status=True).get().text.text == 'which location would you prefer?'
        assert Responses.objects(name='utter_ask_restaurant_form_num_people',
                                 bot=bot, status=True).get().text.text == 'seats required?'
        assert Responses.objects(name='utter_ask_restaurant_form_cuisine',
                                 bot=bot, status=True).get().text.text == 'type of cuisine?'
        assert Responses.objects(name='utter_ask_restaurant_form_outdoor_seating',
                                 bot=bot, status=True).get().text.text == 'outdoor seating required?'
        assert Responses.objects(name='utter_ask_restaurant_form_preferences',
                                 bot=bot, status=True).get().text.text == 'any preferences?'
        assert Responses.objects(name='utter_ask_restaurant_form_ac_required',
                                 bot=bot, status=True).get().text.text == 'do you want to go with an AC room?'
        assert Responses.objects(name='utter_ask_restaurant_form_feedback',
                                 bot=bot,
                                 status=True).get().text.text == 'Please give your feedback on your experience so far'

        validations_added = list(FormValidationAction.objects(name='validate_restaurant_form', bot=bot, status=True))
        assert len(validations_added) == 7
        assert validations_added[1].slot == 'cuisine'
        assert validations_added[1].validation_semantic == \
               "if (&& cuisine.contains('i') && cuisine.length() > 4 || !cuisine.contains(" ")) " \
               "{return true;} else {return false;}"
        assert validations_added[1].slot_set.type == 'current'
        assert validations_added[1].slot_set.value == 'Indian Cuisine'

    def test_edit_form_not_exists(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Form does not exists'):
            processor.edit_form('form_not_present', [], 'test', 'test')

    def test_edit_form_utterance_not_exists(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['provide your age?'], 'slot': 'age',
                 'slot_set': {'type': 'current', 'value': 27}},
                {'ask_questions': ['provide your location?'], 'slot': 'location',
                 'slot_set': {'type': 'custom', 'value': 'Delhi'}}]

        bot = 'test'
        user = 'user'
        utterance = Utterances.objects(name='utter_ask_know_user_name', bot=bot).get()
        utterance.delete()
        for response in Responses.objects(name='utter_ask_know_user_name', bot=bot):
            response.delete()

        processor.edit_form('know_user', path, bot, user)
        assert Forms.objects(name='know_user', bot=bot, status=True).get()
        assert Utterances.objects(name='utter_ask_know_user_age', bot=bot,
                                  status=True).get().form_attached == 'know_user'
        assert Utterances.objects(name='utter_ask_know_user_location', bot=bot,
                                  status=True).get().form_attached == 'know_user'
        assert len(Responses.objects(name='utter_ask_know_user_age', bot=bot, status=True)) == 2
        assert Responses.objects(name='utter_ask_know_user_location', bot=bot,
                                 status=True).get().text.text == 'provide your location?'
        validations_added = list(FormValidationAction.objects(name='validate_know_user', bot=bot, status=True))
        assert validations_added[0].is_required
        assert validations_added[0].slot_set.type == 'current'
        assert validations_added[0].slot_set.value == 27
        assert validations_added[1].is_required
        assert validations_added[1].slot_set.type == 'custom'
        assert validations_added[1].slot_set.value == 'Delhi'

    def test_delete_form_with_validations(self):
        bot = 'test'
        user = 'user'
        processor = MongoProcessor()
        processor.delete_form('know_user_form', bot, user)
        with pytest.raises(DoesNotExist):
            Forms.objects(name='know_user_form', bot=bot, status=True).get()
        form_validations = list(FormValidationAction.objects(name='know_user_form', bot=bot, status=True))
        assert not form_validations

    def test_delete_form_not_exists(self):
        bot = 'test'
        user = 'user'
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Form "get_user" does not exists'):
            processor.delete_form('get_user', bot, user)
        with pytest.raises(AppException, match='Form "form_not_present" does not exists'):
            processor.delete_form('form_not_present', bot, user)

    def test_delete_empty_form(self):
        bot = 'test'
        user = 'user'
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Form " " does not exists'):
            processor.delete_form(' ', bot, user)

    def test_delete_form_attached_to_rule(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        form_name = 'know_user'
        story_name = "stop form - continue"
        with pytest.raises(AppException,
                           match=re.escape(f'Cannot remove action "{form_name}" linked to flow "{story_name}"')):
            processor.delete_form(form_name, bot, user)

    def test_delete_rule_with_form(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        processor.delete_complex_story(pytest.activate_form_story_id, 'RULE', bot, user)
        with pytest.raises(DoesNotExist):
            Rules.objects(block_name="activate form", bot=bot, events__name='know_user', status=True).get()

    def test_delete_rule_with_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        processor.delete_complex_story(pytest.form_continue_story_id, 'STORY', bot, user)
        processor.delete_complex_story(pytest.form_stop_story_id, 'STORY', bot, user)
        with pytest.raises(DoesNotExist):
            Stories.objects(block_name="stop form - continue", bot=bot, events__name='know_user', status=True).get()
        with pytest.raises(DoesNotExist):
            Stories.objects(block_name="stop form - stop", bot=bot, events__name='know_user', status=True).get()

    def test_delete_form_utterance_deleted(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        utterance = Utterances.objects(name='utter_ask_know_user_age', bot=bot).get()
        utterance.delete()
        processor.delete_form('know_user', bot, user)
        with pytest.raises(DoesNotExist):
            Forms.objects(name='know_user', bot=bot, status=True).get()
        with pytest.raises(DoesNotExist):
            Utterances.objects(name='utter_ask_know_user_name', bot=bot, status=True).get()
        with pytest.raises(DoesNotExist):
            Responses.objects(name='utter_ask_know_user_name', bot=bot, status=True).get()
        with pytest.raises(DoesNotExist):
            Utterances.objects(name='utter_ask_know_user_location', bot=bot, status=True).get()
        with pytest.raises(DoesNotExist):
            Responses.objects(name='utter_ask_know_user_location', bot=bot, status=True).get()

    def test_delete_utterance_linked_to_form(self):
        processor = MongoProcessor()
        bot = 'test'
        with pytest.raises(AppException,
                           match='Utterance cannot be deleted as it is linked to form: restaurant_form'):
            processor.delete_utterance('utter_ask_restaurant_form_cuisine', bot, "test")
        assert Utterances.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()
        assert Responses.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()

    def test_delete_response_linked_to_form(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        response = Responses.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()
        with pytest.raises(AppException,
                           match='Utterance cannot be deleted as it is linked to form: restaurant_form'):
            processor.delete_response(str(response.id), bot)
        assert Utterances.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()
        assert Responses.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()

    def test_edit_utterance_for_form(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        response = Responses.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()
        processor.edit_text_response(str(response.id), 'what cuisine are you interested in?',
                                     'utter_ask_restaurant_form_cuisine', bot, user)
        assert Responses.objects(name='utter_ask_restaurant_form_cuisine', bot=bot,
                                 status=True).get().text.text == 'what cuisine are you interested in?'

    def test_delete_response_linked_to_form_validation_false(self):
        processor = MongoProcessor()
        bot = 'test'
        processor.delete_utterance('utter_ask_restaurant_form_cuisine', bot, False, user="test")
        with pytest.raises(DoesNotExist):
            Utterances.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()
        with pytest.raises(DoesNotExist):
            Responses.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()

    def test_add_utterance_to_story_that_is_attached_to_form(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_ask_restaurant_form_outdoor_seating", "type": "BOT"},
        ]
        story_dict = {'name': "story with form utterance", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(AppException,
                           match='utterance "utter_ask_restaurant_form_outdoor_seating" is attached to a form'):
            processor.add_complex_story(story_dict, bot, user)

    def test_delete_intent_attached_to_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        with pytest.raises(AppException, match='Cannot remove intent "greet" linked to flow "greet"'):
            processor.delete_intent('greet', bot, user, False)

    def test_add_story_with_form(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "restaurant_form", "type": "FORM_ACTION"},
            {"name": "utter_thanks", "type": "ACTION"},
        ]
        story_dict = {'name': "story with form", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        pytest.form_story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with form", bot=bot,
                                events__name='restaurant_form', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'story with form']
        assert story_with_form[0]['steps'] == [
            {'name': 'greet', 'type': 'INTENT'},
            {'name': 'restaurant_form', 'type': 'FORM_ACTION'},
            {'name': 'utter_thanks', 'type': 'BOT'}
        ]

    def test_get_story_with_form(self):
        processor = MongoProcessor()
        bot = 'test'
        stories = list(processor.get_stories(bot))
        assert stories[20]['name'] == 'story with form'
        assert stories[20]['type'] == 'STORY'
        assert stories[20]['steps'][0]['name'] == 'greet'
        assert stories[20]['steps'][0]['type'] == 'INTENT'
        assert stories[20]['steps'][1]['name'] == 'restaurant_form'
        assert stories[20]['steps'][1]['type'] == 'FORM_ACTION'
        assert stories[20]['template_type'] == 'CUSTOM'

    def test_delete_form_attached_to_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        with pytest.raises(AppException,
                           match='Cannot remove action "restaurant_form" linked to flow "story with form"'):
            processor.delete_form("restaurant_form", bot, user)

    def test_delete_story_with_form(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        processor.delete_complex_story(pytest.form_story_id, 'STORY', bot, user)
        assert not Stories.objects(block_name="story with form", bot=bot,
                                   events__name='restaurant_form')

    def test_update_story_step_that_is_attached_to_form(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        story_dict = {'name': "story without action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        pytest.story_id = processor.add_complex_story(story_dict, bot, user)

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_ask_restaurant_form_outdoor_seating", "type": "BOT"},
        ]
        story_dict = {'name': "story without action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(AppException,
                           match='utterance "utter_ask_restaurant_form_outdoor_seating" is attached to a form'):
            processor.update_complex_story(pytest.story_id, story_dict, bot, user)

    def test_add_slot_set_action_from_value_no_value_passed(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        Slots(name='name', type='text', bot=bot, user=user).save()
        action = {'name': 'action_set_slot', 'set_slots': [{'name': 'name', 'type': SLOT_SET_TYPE.FROM_VALUE.value}]}
        processor.add_slot_set_action(action, bot, user)
        assert Actions.objects(name='action_set_slot', type=ActionType.slot_set_action.value,
                               bot=bot, user=user, status=True).get()
        assert SlotSetAction.objects(name='action_set_slot', bot=bot, user=user, status=True).get()

    def test_add_story_with_slot_set_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "action_set_slot", "type": "SLOT_SET_ACTION"},
        ]
        story_dict = {'name': "story with slot_set_action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        pytest.slot_set_action_story_id = processor.add_complex_story(story_dict, bot, user)
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'story with slot_set_action']
        assert story_with_form[0]['steps'] == [
            {'name': 'greet', 'type': 'INTENT'},
            {'name': 'action_set_slot', 'type': 'SLOT_SET_ACTION'},
        ]

    def test_fetch_story_with_slot_set_action(self):
        processor = MongoProcessor()
        data = list(processor.get_stories("test"))
        slot_set_story = next(item for item in data if item['name'] == 'story with slot_set_action')
        assert slot_set_story['steps'] == [{'name': 'greet', 'type': 'INTENT'},
                                           {'name': 'action_set_slot', 'type': 'SLOT_SET_ACTION'}]
        assert slot_set_story['template_type'] == 'CUSTOM'
        assert slot_set_story['type'] == 'STORY'

    def test_add_slot_set_action_from_value(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': 'action_set_name_slot',
                  'set_slots': [{'name': 'name', 'type': SLOT_SET_TYPE.FROM_VALUE.value, 'value': '5'}]}
        processor.add_slot_set_action(action, bot, user)
        assert Actions.objects(name='action_set_name_slot', type=ActionType.slot_set_action.value,
                               bot=bot, user=user, status=True).get()
        assert SlotSetAction.objects(name='action_set_name_slot', bot=bot, user=user, status=True).get()

    def test_add_slot_set_action_reset(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        Slots(name='location', type='text', bot=bot, user=user).save()
        action = {'name': 'action_set_location_slot',
                  'set_slots': [{'name': 'location', 'type': SLOT_SET_TYPE.RESET_SLOT.value}]}
        processor.add_slot_set_action(action, bot, user)
        assert Actions.objects(name='action_set_location_slot', type=ActionType.slot_set_action.value,
                               bot=bot, user=user, status=True).get()
        assert SlotSetAction.objects(name='action_set_location_slot', bot=bot, user=user, status=True).get()

    def test_add_slot_set_action_already_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': 'action_set_name_slot', 'set_slots': [{'name': 'name', 'type': SLOT_SET_TYPE.FROM_VALUE.value,
                                                                 'value': '5'}]}
        with pytest.raises(AppException, match='Action exists!'):
            processor.add_slot_set_action(action, bot, user)

    def test_add_slot_set_action_name_empty(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': ' ', 'set_slots': [{'name': 'name', 'type': SLOT_SET_TYPE.FROM_VALUE.value, 'value': '5'}]}
        with pytest.raises(AppException, match='name cannot be empty or spaces'):
            processor.add_slot_set_action(action, bot, user)

        action = {'name': None, 'set_slots': [{'name': 'name', 'type': SLOT_SET_TYPE.FROM_VALUE.value, 'value': '5'}]}
        with pytest.raises(AppException, match='name cannot be empty or spaces'):
            processor.add_slot_set_action(action, bot, user)

    def test_add_slot_set_action_slot_empty(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': 'action_set_slot_name',
                  'set_slots': [{'name': ' ', 'type': SLOT_SET_TYPE.FROM_VALUE.value, 'value': '5'}]}
        with pytest.raises(AppException, match='slot name cannot be empty or spaces'):
            processor.add_slot_set_action(action, bot, user)

        action = {'name': 'action_set_slot_name',
                  'set_slots': [{'name': None, 'type': SLOT_SET_TYPE.FROM_VALUE.value, 'value': '5'}]}
        with pytest.raises(AppException, match='slot name cannot be empty or spaces'):
            processor.add_slot_set_action(action, bot, user)

    def test_add_slot_set_action_slot_not_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': 'action_set_slot_non_existant', 'set_slots': [{'name': 'non_existant',
                                                                         'type': SLOT_SET_TYPE.FROM_VALUE.value,
                                                                         'value': '5'}]}
        with pytest.raises(AppException, match='Slot with name "non_existant" not found'):
            processor.add_slot_set_action(action, bot, user)

    def test_add_slot_set_action_simple_action_with_same_name_present(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        Actions(name='action_trigger_some_api', bot=bot, user=user).save()
        action = {'name': 'action_trigger_some_api', 'set_slots': [{'name': 'some_api',
                                                                    'type': SLOT_SET_TYPE.FROM_VALUE.value,
                                                                    'value': '5'}]}
        with pytest.raises(AppException, match='Action exists!'):
            processor.add_slot_set_action(action, bot, user)

    def test_list_slot_set_actions(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = processor.list_slot_set_actions(bot)
        for action in actions:
            assert type(action['_id']) is str
        [action.pop('_id') for action in actions]
        assert actions == [{'name': 'action_set_slot', 'set_slots': [{'name': 'name', 'type': 'from_value'}]},
                           {'name': 'action_set_name_slot',
                            'set_slots': [{'name': 'name', 'type': 'from_value', 'value': '5'}]},
                           {'name': 'action_set_location_slot',
                            'set_slots': [{'name': 'location', 'type': 'reset_slot'}]}]

    def test_list_slot_set_actions_with_false(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = processor.list_slot_set_actions(bot, False)
        for action in actions:
            assert action.get('_id') is None
        assert actions == [{'name': 'action_set_slot', 'set_slots': [{'name': 'name', 'type': 'from_value'}]},
                           {'name': 'action_set_name_slot',
                            'set_slots': [{'name': 'name', 'type': 'from_value', 'value': '5'}]},
                           {'name': 'action_set_location_slot',
                            'set_slots': [{'name': 'location', 'type': 'reset_slot'}]}]

    def test_list_slot_set_actions_not_present(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        actions = processor.list_slot_set_actions(bot)
        assert len(actions) == 0

    def test_edit_slot_set_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        Slots(name='name_new', type='text', bot=bot, user=user).save()
        action = {'name': 'action_set_name_slot',
                  'set_slots': [{'name': 'name_new', 'type': SLOT_SET_TYPE.RESET_SLOT.value,
                                 'value': 'name'}]}
        processor.edit_slot_set_action(action, bot, user)
        assert Actions.objects(name='action_set_name_slot', type=ActionType.slot_set_action.value,
                               bot=bot, user=user, status=True).get()
        assert SlotSetAction.objects(name='action_set_name_slot', bot=bot, user=user, status=True).get()

    def test_edit_slot_set_action_not_present(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': 'action_non_existant',
                  'set_slots': [{'name': 'name_new', 'type': SLOT_SET_TYPE.FROM_VALUE.value,
                                 'value': 'name'}]}
        with pytest.raises(AppException, match=f'Slot setting action with name "{action["name"]}" not found'):
            processor.edit_slot_set_action(action, bot, user)

    def test_edit_slot_set_action_slot_not_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': 'action_set_name_slot',
                  'set_slots': [{'name': 'slot_non_existant', 'type': SLOT_SET_TYPE.FROM_VALUE.value,
                                 'value': 'name'}]}
        with pytest.raises(AppException, match=f'Slot with name "slot_non_existant" not found'):
            processor.edit_slot_set_action(action, bot, user)

    def test_edit_slot_set_action_name_not_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': 'not_exists', 'set_slots': [{'name': 'name', 'type': SLOT_SET_TYPE.FROM_VALUE.value,
                                              'value': 'name'}]}
        with pytest.raises(AppException, match=f'Slot setting action with name "{action["name"]}" not found'):
            processor.edit_slot_set_action(action, bot, user)

    def test_edit_slot_set_action_slot_empty(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': 'action_set_name_slot', 'set_slots': [{'name': ' ', 'type': SLOT_SET_TYPE.FROM_VALUE.value,
                                                                 'value': 'name'}]}
        with pytest.raises(AppException, match="slot name cannot be empty or spaces"):
            processor.edit_slot_set_action(action, bot, user)

    def test_delete_slot_set_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        processor.delete_action('action_set_name_slot', bot, user)

    def test_delete_slot_set_action_already_deleted(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        with pytest.raises(AppException, match=f'Action with name "action_set_name_slot" not found'):
            processor.delete_action('action_set_name_slot', bot, user)

    def test_delete_slot_set_action_not_present(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        with pytest.raises(AppException, match=f'Action with name "action_non_existant" not found'):
            processor.delete_action('action_non_existant', bot, user)

    def test_delete_slot_set_action_linked_to_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        Slots(name='age', type='text', bot=bot, user=user).save()
        action = {'name': 'action_set_age_slot', 'set_slots': [{'name': 'age', 'type': SLOT_SET_TYPE.RESET_SLOT.value}]}
        processor.add_slot_set_action(action, bot, user)
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "action_set_age_slot", "type": "SLOT_SET_ACTION"},
        ]
        story_dict = {'name': "story with slot set action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.add_complex_story(story_dict, bot, user)
        with pytest.raises(AppException,
                           match=f'Cannot remove action "action_set_age_slot" linked to flow "story with slot set action"'):
            processor.delete_action('action_set_age_slot', bot, user)

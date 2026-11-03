from tests.unit_test.data_processor.data_processor_support import *  # noqa: F403
from tests.unit_test.data_processor.data_processor_support import (
    MongoProcessorTestBase,
    fast_rasa_training,
)

class TestMongoProcessor(MongoProcessorTestBase):
    def test_add_complex_story_with_slot(self):
        processor = MongoProcessor()
        story_name = "story with slot"
        bot = "test_slot"
        user = "test_user"
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "is_new_user", "type": "SLOT", "value": None},
            {"name": "utter_welcome_user", "type": "BOT"},
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        pytest.story_id = processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name=story_name, bot=bot).get()
        assert len(story.events) == 3

        steps.insert(2, {"name": "persona", "type": "SLOT", "value": "positive"})
        processor.update_complex_story(pytest.story_id, story_dict, bot, user)
        story = Stories.objects(block_name=story_name, bot=bot).get()
        assert story.to_mongo().to_dict()["events"] == [{'name': 'greet', 'type': 'user'},
                                                        {'name': 'is_new_user', 'type': 'slot'},
                                                        {'name': 'persona', 'type': 'slot', 'value': 'positive'},
                                                        {'name': 'utter_welcome_user', 'type': 'action'}]
        stories = list(processor.get_stories(bot))
        assert stories[0]["steps"] == [{'name': 'greet', 'type': 'INTENT'},
                                       {'name': 'is_new_user', 'type': 'SLOT', 'value': None},
                                       {'name': 'persona', 'type': 'SLOT', 'value': 'positive'},
                                       {'name': 'utter_welcome_user', 'type': 'BOT'}]

    def test_add_prompt_action_with_gpt_feature_disabled(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='keyvalue',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()

        request = {"system_prompt": DEFAULT_SYSTEM_PROMPT, "context_prompt": DEFAULT_CONTEXT_PROMPT,
                   "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
                   "num_bot_responses": 5}
        with pytest.raises(AppException, match="Faq feature is disabled for the bot! Please contact support."):
            processor.add_prompt_action(request, bot, user)

        LLMSecret.objects.delete()

    def test_add_prompt_action_with_invalid_slots(self):
        processor = MongoProcessor()
        bot = 'testing_bot'
        user = 'testing_user'
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()

        CognitionSchema(
            metadata=[
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            collection_name="test",
            user=user,
            bot=bot,
            timestamp=utc_now(),
            schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
        ).save()
        request = {'name': 'test_add_prompt_action_with_invalid_slots', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4.1-mini',
                                       'top_p': 0.0,
                                       'n': 1, 'stop': None, 'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.',
                                    'instructions': 'Answer question based on the context below.', 'type': 'system',
                                    'source': 'static',
                                    'is_enabled': True},
                                   {'name': 'Similarity Prompt',
                                    "data": "test",
                                    'hyperparameters': {'top_results': 10,
                                                        'similarity_threshold': 1.70},
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Identification Prompt',
                                    'data': 'info',
                                    'instructions': 'Answer according to the context', 'type': 'user', 'source': 'slot',
                                    'is_enabled': True}]}
        with pytest.raises(AppException, match="Slot with name info not found!"):
            processor.add_prompt_action(request, bot, user)

        LLMSecret.objects.delete()

    def test_add_prompt_action_with_invalid_http_action(self):
        processor = MongoProcessor()
        bot = 'testt_bot'
        user = 'testt_user'
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()
        CognitionSchema(
            metadata=[
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            collection_name="test_collection",
            user=user,
            bot=bot,
            timestamp=utc_now(),
            schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
        ).save()
        request = {'name': 'test_add_prompt_action_with_invalid_http_action', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4.1-mini',
                                       'top_p': 0.0,
                                       'n': 1, 'stop': None, 'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.',
                                    'instructions': 'Answer question based on the context below.', 'type': 'system',
                                    'source': 'static',
                                    'is_enabled': True},
                                   {'name': 'Similarity Prompt',
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True,
                                    "data": "test_collection",
                                    'hyperparameters': {'top_results': 10,
                                                        'similarity_threshold': 1.70}},
                                   {'name': 'Http action Prompt',
                                    'data': 'test_http_action',
                                    'instructions': 'Answer according to the context', 'type': 'user',
                                    'source': 'action',
                                    'is_enabled': True}]}
        with pytest.raises(AppException, match="Action with name test_http_action not found!"):
            processor.add_prompt_action(request, bot, user)

        LLMSecret.objects.delete()

    def test_add_prompt_action_with_invalid_similarity_threshold(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()
        CognitionSchema(
            metadata=[
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            collection_name="test_collection",
            user=user,
            bot=bot,
            timestamp=utc_now(),
            schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
        ).save()
        request = {'name': 'test_prompt_action_similarity', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4.1-mini',
                                       'top_p': 0.0,
                                       'n': 1, 'stop': None, 'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Similarity Prompt',
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True,
                                    "data": "test_collection",
                                    'hyperparameters': {'top_results': 10,
                                                        'similarity_threshold': 1.70},
                                    },
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}]}
        with pytest.raises(ValidationError, match="similarity_threshold should be within 0.3 and 1"):

            processor.add_prompt_action(request, bot, user)

        LLMSecret.objects.delete()

    def test_add_prompt_action_with_invalid_top_results(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        CognitionSchema(
            metadata=[
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            collection_name="test_collection",
            user=user,
            bot=bot,
            timestamp=utc_now(),
            schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
        ).save()

        request = {'name': 'test_prompt_action_invalid_top_results', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4.1-mini',
                                       'top_p': 0.0,
                                       'n': 1, 'stop': None, 'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Similarity Prompt',
                                    "data": "test_collection",
                                    'hyperparameters': {'top_results': 40,
                                                        'similarity_threshold': 0.3},
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}]}
        with pytest.raises(ValidationError, match="top_results should not be greater than 30"):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_utter(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        request = {'name': 'utter_test_add_prompt_action',
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        with pytest.raises(AppException, match='Action name cannot start with utter_'):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_empty_collection_for_bot_content_prompt(self):
        processor = MongoProcessor()
        bot = 'bot'
        user = 'user'
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()
        CognitionSchema(
            metadata=[
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            collection_name="",
            user=user,
            bot=bot,
            timestamp=utc_now(),
            schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
        ).save()
        request = {'name': 'test_add_prompt_action_with_empty_collection_for_bot_content_prompt',
                   'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Similarity Prompt',
                                    'data': '',
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}]}
        processor.add_prompt_action(request, bot, user)
        prompt_action = processor.get_prompt_action(bot)
        prompt_action[0].pop("_id")
        assert not DeepDiff(prompt_action[0], {
            'name': 'test_add_prompt_action_with_empty_collection_for_bot_content_prompt',  # corrected name
            'num_bot_responses': 5,
            'failure_message': "I'm sorry, I didn't quite understand that. Could you rephrase?",
            'user_question': {'type': 'from_user_message'},
            'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4.1-mini', 'top_p': 0.0,
                                'n': 1, 'stop': None, 'presence_penalty': 0.0,
                                'frequency_penalty': 0.0, 'logit_bias': {}},
            'llm_type': 'openai',
            "process_media": False,
            'llm_prompts': [
                    {'name': 'System Prompt', 'data': 'You are a personal assistant.',
                     'type': 'system', 'source': 'static', 'is_enabled': True},

                    {'name': 'Similarity Prompt', 'data': 'default',
                     'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                     'type': 'user', 'source': 'bot_content', 'is_enabled': True},

                    {'name': 'Query Prompt',
                     'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                     'instructions': 'Answer according to the context', 'type': 'query', 'source': 'static',
                     'is_enabled': True},

                    {'name': 'Query Prompt',
                     'data': 'If there is no specific query, assume that user is aking about java programming.',
                     'instructions': 'Answer according to the context', 'type': 'query', 'source': 'static',
                     'is_enabled': True}
                ],
            'instructions': [], 'set_slots': [], 'dispatch_response': True, 'status': True
        }, ignore_order=True)

        LLMSecret.objects.delete()

    def test_add_prompt_action_with_bot_content_prompt(self):
        processor = MongoProcessor()
        bot = 'bot'
        user = 'user'
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()
        CognitionSchema(
            metadata=[
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            collection_name="test_collection",
            user=user,
            bot=bot,
            timestamp=utc_now(),
            schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
        ).save()
        request = {'name': 'test_add_prompt_action_with_bot_content_prompt',
                   'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   "process_media": False,
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Similarity Prompt',
                                    'data': 'test_collection',
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}]}
        processor.add_prompt_action(request, bot, user)
        prompt_action = processor.get_prompt_action(bot)
        prompt_action[1].pop("_id")
        assert not DeepDiff(prompt_action[1], {
            'name': 'test_add_prompt_action_with_bot_content_prompt',
            'num_bot_responses': 5,
            'failure_message': "I'm sorry, I didn't quite understand that. Could you rephrase?",
            'user_question': {'type': 'from_user_message'},
            'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4.1-mini', 'top_p': 0.0,
                                'n': 1, 'stop': None, 'presence_penalty': 0.0,
                                'frequency_penalty': 0.0, 'logit_bias': {}},
            'llm_type': 'openai',
            "process_media": False,
            'llm_prompts': [
                {'name': 'System Prompt', 'data': 'You are a personal assistant.',
                 'type': 'system', 'source': 'static', 'is_enabled': True},
                {'name': 'Similarity Prompt', 'data': 'test_collection',
                 'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                 'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                {'name': 'Query Prompt',
                 'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                 'instructions': 'Answer according to the context', 'type': 'query', 'source': 'static',
                 'is_enabled': True},
                {'name': 'Query Prompt',
                 'data': 'If there is no specific query, assume that user is aking about java programming.',
                 'instructions': 'Answer according to the context', 'type': 'query', 'source': 'static',
                 'is_enabled': True}
            ],
            'instructions': [], 'set_slots': [], 'dispatch_response': True, 'status': True
        }, ignore_order=True)

        LLMSecret.objects.delete()

    def test_add_prompt_action_with_invalid_query_prompt(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        CognitionSchema(
            metadata=[
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            collection_name="test_collection",
            user=user,
            bot=bot,
            timestamp=utc_now(),
            schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
        ).save()
        request = {'name': 'test_add_prompt_action_with_invalid_query_prompt',
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Similarity Prompt', "data": "test_collection",
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'history', 'is_enabled': True}],
                   "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
                   "num_bot_responses": 5}
        with pytest.raises(ValidationError, match="Query prompt must have static source!"):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_invalid_num_bot_responses(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        CognitionSchema(
            metadata=[
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            collection_name="test_collection",
            user=user,
            bot=bot,
            timestamp=utc_now(),
            schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
        ).save()
        request = {'name': 'test_add_prompt_action_with_invalid_num_bot_responses',
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Similarity Prompt', "data": "test_collection",
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}],
                   "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
                   "num_bot_responses": 15}
        with pytest.raises(ValidationError, match="num_bot_responses should not be greater than 5"):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_invalid_system_prompt_source(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        CognitionSchema(
            metadata=[
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            collection_name="test_collection",
            user=user,
            bot=bot,
            timestamp=utc_now(),
            schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
        ).save()
        request = {'name': 'test_add_prompt_action_with_invalid_system_prompt_source',
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'history',
                                    'is_enabled': True},
                                   {'name': 'Similarity Prompt', "data": "test_collection",
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}],
                   "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE, "num_bot_responses": 5}
        with pytest.raises(ValidationError, match="System prompt must have static source!"):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_multiple_system_prompt(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        CognitionSchema(
            metadata=[
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            collection_name="test_collection",
            user=user,
            bot=bot,
            timestamp=utc_now(),
            schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
        ).save()
        request = {'name': 'test_add_prompt_action_with_multiple_system_prompt',
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'System Prompt', 'data': 'You are a personal assistant.',
                                    'instructions': 'Answer question based on the context below.', 'type': 'system',
                                    'source': 'static',
                                    'is_enabled': True},
                                   {'name': 'Similarity Prompt', "data": "test_collection",
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}],
                   "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE, "num_bot_responses": 5}
        with pytest.raises(ValidationError, match="Only one system prompt can be present!"):
            processor.add_prompt_action(request, bot, user)

    def test_validate_llm_prompts_bot_content_provider_mismatch(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        collection_name = "test_collection_mismatch"

        CognitionSchema(
            metadata=[
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True}
            ],
            collection_name=collection_name,
            user=user,
            bot=bot,
            timestamp=utc_now(),
            schema_metadata=SchemaMetadata(
                training_needed=False,
                provider="openai",
                model_id="text-embedding-3-large"
            )
        ).save()

        request = {
            'name': 'test_llm_mismatch_action',
            'llm_type': 'anthropic',
            'llm_prompts': [
                {'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                 'source': 'static', 'is_enabled': True},
                {
                    'name': 'Similarity Prompt',
                    'data': collection_name,
                    'instructions': 'Search this collection',
                    'type': 'user',
                    'source': 'bot_content',
                    'is_enabled': True
                }
            ],
            "failure_message": "Error",
            "num_bot_responses": 1
        }

        # 3. Assert that AppException is raised due to the provider mismatch
        expected_error = "LLM Type must be openai for the chosen faq table"
        with pytest.raises(AppException, match=expected_error):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_empty_llm_prompt_name(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        CognitionSchema(
            metadata=[
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            collection_name="test_collection",
            user=user,
            bot=bot,
            timestamp=utc_now(),
            schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
        ).save()
        request = {'name': 'test_add_prompt_action_with_empty_llm_prompt_name',
                   'llm_prompts': [{'name': '', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Similarity Prompt', "data": "test_collection",
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}],
                   "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE, "num_bot_responses": 5}
        with pytest.raises(ValidationError, match="Name cannot be empty!"):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_empty_data_for_static_prompt(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        CognitionSchema(
            metadata=[
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            collection_name="test_collection",
            user=user,
            bot=bot,
            timestamp=utc_now(),
            schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
        ).save()
        request = {'name': 'test_add_prompt_action_with_empty_data_for_static_prompt',
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Similarity Prompt', "data": "test_collection",
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': '', 'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}],
                   "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE, "num_bot_responses": 5}
        with pytest.raises(ValidationError, match="data is required for static prompts!"):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_multiple_history_source_prompts(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        CognitionSchema(
            metadata=[
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            collection_name="test_collection",
            user=user,
            bot=bot,
            timestamp=utc_now(),
            schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
        ).save()
        request = {'name': 'test_add_prompt_action_with_multiple_history_source_prompts',
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True},
                                   {'name': 'Analytical Prompt', 'type': 'user', 'source': 'history',
                                    'is_enabled': True},
                                   {'name': 'Similarity Prompt', "data": "test_collection",
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}],
                   "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE, "num_bot_responses": 5}
        with pytest.raises(ValidationError, match="Only one history source can be present!"):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_no_system_prompts(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        CognitionSchema(
            metadata=[
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            collection_name="test_collection_1",
            user=user,
            bot=bot,
            timestamp=utc_now(),
            schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
        ).save()
        CognitionSchema(
            metadata=[
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            collection_name="test_collection_2",
            user=user,
            bot=bot,
            timestamp=utc_now(),
            schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
        ).save()
        request = {'name': 'test_add_prompt_action_with_no_system_prompts',
                   'llm_prompts': [
                       {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True},
                       {'name': 'Similarity Prompt', "data": "test_collection_1",
                        'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                        'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                       {'name': 'Another Similarity Prompt', "data": "test_collection_2",
                        'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                        'type': 'user', 'source': 'bot_content', 'is_enabled': True}
                   ],
                   "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE, "num_bot_responses": 5}
        with pytest.raises(ValidationError, match="System prompt is required!"):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_with_empty_llm_prompts(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'

        request = {'name': 'test_add_prompt_action_with_empty_llm_prompts', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4.1-mini',
                                       'top_p': 0.0,
                                       'n': 1, 'stop': None, 'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': []}
        with pytest.raises(ValidationError, match="llm_prompts are required!"):
            processor.add_prompt_action(request, bot, user)

    def test_add_prompt_action_faq_action_with_default_values_and_instructions(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()
        request = {'name': 'test_add_prompt_action_faq_action_with_default_values',
                   'user_question': {'type': 'from_slot', 'value': 'prompt_question'},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}],
                   'instructions': ['Answer in a short manner.', 'Keep it simple.'],
                   "set_slots": [{"name": "gpt_result", "value": "${data}", "evaluation_type": "expression"},
                                 {"name": "gpt_result_type", "value": "${data.type}", "evaluation_type": "script"}],
                   "dispatch_response": False
                   }
        pytest.action_id = processor.add_prompt_action(request, bot, user)
        action = list(processor.get_prompt_action(bot))
        action[0].pop("_id")

        assert not DeepDiff(action, [{
            'name': 'test_add_prompt_action_faq_action_with_default_values',
            'num_bot_responses': 5,
            'failure_message': "I'm sorry, I didn't quite understand that. Could you rephrase?",
            'user_question': {'type': 'from_slot', 'value': 'prompt_question'},
            'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4.1-mini',
                                'top_p': 0.0, 'n': 1, 'stop': None,
                                'presence_penalty': 0.0, 'frequency_penalty': 0.0, 'logit_bias': {}},
            'llm_type': 'openai',
            'process_media': False,
            'llm_prompts': [
                {'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                 'source': 'static', 'is_enabled': True},
                {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}
            ],
            'instructions': ['Answer in a short manner.', 'Keep it simple.'],
            'set_slots': [{'name': 'gpt_result', 'value': '${data}', 'evaluation_type': 'expression'},
                          {'name': 'gpt_result_type', 'value': '${data.type}', 'evaluation_type': 'script'}],
            'dispatch_response': False,
            'status': True
        }], ignore_order=True)

        LLMSecret.objects.delete()

    def test_add_prompt_action_with_invalid_temperature_hyperparameter(self):
        processor = MongoProcessor()
        bot = 'test_bot_one'
        user = 'test_user_one'
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()

        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'test_add_prompt_action_with_invalid_temperature_hyperparameter', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 3.0, 'max_tokens': 300, 'model': 'gpt-4.1-mini',
                                       'top_p': 0.0,
                                       'n': 1, 'stop': None, 'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        with pytest.raises(ValidationError, match=re.escape("['temperature']: 3.0 is greater than the maximum of 2.0")):
            processor.add_prompt_action(request, bot, user)

        LLMSecret.objects.delete()

    def test_add_prompt_action_with_invalid_stop_hyperparameter(self):
        processor = MongoProcessor()
        bot = 'test_bot_two'
        user = 'test_user_two'
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'test_add_prompt_action_with_invalid_stop_hyperparameter', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4.1-mini',
                                       'top_p': 0.0,
                                       'n': 1, 'stop': ["\n", ".", "?", "!", ";"],
                                       'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        with pytest.raises(ValidationError,
                           match=re.escape('[\'stop\']: ["\\n",".","?","!",";"] is not valid under any of the schemas listed in the \'anyOf\' keyword')):
            processor.add_prompt_action(request, bot, user)

        LLMSecret.objects.delete()

    def test_add_prompt_action_with_invalid_presence_penalty_hyperparameter(self):
        processor = MongoProcessor()
        bot = 'test_bot_three'
        user = 'test_user_three'
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'test_add_prompt_action_with_invalid_presence_penalty_hyperparameter',
                   'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4.1-mini',
                                       'top_p': 0.0,
                                       'n': 1, 'stop': '?', 'presence_penalty': -3.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        with pytest.raises(ValidationError, match=re.escape("['presence_penalty']: -3.0 is less than the minimum of -2.0")):
            processor.add_prompt_action(request, bot, user)

        LLMSecret.objects.delete()

    def test_add_prompt_action_with_invalid_frequency_penalty_hyperparameter(self):
        processor = MongoProcessor()
        bot = 'test_bot_four'
        user = 'test_user_four'
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'test_add_prompt_action_with_invalid_frequency_penalty_hyperparameter',
                   'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4.1-mini',
                                       'top_p': 0.0,
                                       'n': 1, 'stop': '?', 'presence_penalty': 0.0,
                                       'frequency_penalty': 3.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        with pytest.raises(ValidationError, match=re.escape("['frequency_penalty']: 3.0 is greater than the maximum of 2.0")):
            processor.add_prompt_action(request, bot, user)

        LLMSecret.objects.delete()

    def test_add_prompt_action_with_invalid_max_tokens_hyperparameter(self):
        processor = MongoProcessor()
        bot = 'test_bot_five'
        user = 'test_user_five'
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'test_add_prompt_action_with_invalid_max_tokens_hyperparameter', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 2, 'model': 'gpt-4.1-mini',
                                       'top_p': 0.0,
                                       'n': 1, 'stop': '?', 'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        with pytest.raises(ValidationError, match=re.escape("['max_tokens']: 2 is less than the minimum of 5")):
            processor.add_prompt_action(request, bot, user)

        LLMSecret.objects.delete()

    def test_add_prompt_action_with_zero_max_tokens_hyperparameter(self):
        processor = MongoProcessor()
        bot = 'test_bot_six'
        user = 'test_user_six'
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'test_add_prompt_action_with_zero_max_tokens_hyperparameter', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 0, 'model': 'gpt-4.1-mini',
                                       'top_p': 0.0,
                                       'n': 1, 'stop': '?', 'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        with pytest.raises(ValidationError, match=re.escape("['max_tokens']: 0 is less than the minimum of 5")):
            processor.add_prompt_action(request, bot, user)

        LLMSecret.objects.delete()

    def test_add_prompt_action_with_invalid_top_p_hyperparameter(self):
        processor = MongoProcessor()
        bot = 'test_bot_seven'
        user = 'test_user_seven'
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'test_add_prompt_action_with_invalid_top_p_hyperparameter', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 256, 'model': 'gpt-4.1-mini',
                                       'top_p': 3.0,
                                       'n': 1, 'stop': '?', 'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        with pytest.raises(ValidationError, match=re.escape("['top_p']: 3.0 is greater than the maximum of 1.0")):
            processor.add_prompt_action(request, bot, user)

        LLMSecret.objects.delete()

    def test_add_prompt_action_with_invalid_n_hyperparameter(self):
        processor = MongoProcessor()
        bot = 'test_bot_eight'
        user = 'test_user_eight'
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'test_add_prompt_action_with_invalid_n_hyperparameter', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 200, 'model': 'gpt-4.1-mini',
                                       'top_p': 0.0,
                                       'n': 7, 'stop': '?', 'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        with pytest.raises(ValidationError, match=re.escape("['n']: 7 is greater than the maximum of 5")):
            processor.add_prompt_action(request, bot, user)

        LLMSecret.objects.delete()

    def test_add_prompt_action_with_zero_n_hyperparameter(self):
        processor = MongoProcessor()
        bot = 'test_bot_nine'
        user = 'test_user_nine'
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'test_add_prompt_action_with_zero_n_hyperparameter', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 200, 'model': 'gpt-4.1-mini',
                                       'top_p': 0.0,
                                       'n': 0, 'stop': '?', 'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': {}},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        with pytest.raises(ValidationError, match=re.escape("['n']: 0 is less than the minimum of 1")):
            processor.add_prompt_action(request, bot, user)

        LLMSecret.objects.delete()

    def test_add_prompt_action_with_invalid_logit_bias_hyperparameter(self):
        processor = MongoProcessor()
        bot = 'test_bot_ten'
        user = 'test_user_ten'
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        request = {'name': 'test_add_prompt_action_with_invalid_logit_bias_hyperparameter', 'num_bot_responses': 5,
                   'failure_message': DEFAULT_NLU_FALLBACK_RESPONSE,
                   'hyperparameters': {'temperature': 0.0, 'max_tokens': 200, 'model': 'gpt-4.1-mini',
                                       'top_p': 0.0,
                                       'n': 2, 'stop': '?', 'presence_penalty': 0.0,
                                       'frequency_penalty': 0.0, 'logit_bias': 'a'},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        with pytest.raises(ValidationError, match=re.escape('[\'logit_bias\']: "a" is not of type "object"')):
            processor.add_prompt_action(request, bot, user)

        LLMSecret.objects.delete()

    def test_add_prompt_action_faq_action_already_exist(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()
        request = {'name': 'test_add_prompt_action_faq_action_with_default_values',
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]}
        with pytest.raises(AppException, match='Action exists!'):
            processor.add_prompt_action(request, bot, user)

        LLMSecret.objects.delete()

    def test_edit_prompt_action_does_not_exist(self):
        processor = MongoProcessor()
        bot = 'invalid_bot'
        user = 'test_user'
        action_id = '646344d6f7fa1a62db69cceb'
        request = {'name': 'test_edit_prompt_action_does_not_exist',
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Similarity Prompt', "data": "Bot_collection",
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}],
                   "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
                   "num_bot_responses": 5}
        with pytest.raises(AppException, match="Action not found"):
            processor.edit_prompt_action(action_id, request, bot, user)

    def test_edit_prompt_action_faq_action(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()
        CognitionSchema(
            metadata=[
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            collection_name="test_collection",
            user=user,
            bot=bot,
            timestamp=utc_now(),
            schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
        ).save()

        request = {'name': 'test_edit_prompt_action_faq_action',
                   'user_question': {'type': 'from_user_message'},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Similarity Prompt', 'data': 'test_collection',
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}],
                   "failure_message": "updated_failure_message",
                   "use_query_prompt": True, "use_bot_responses": True, "query_prompt": "updated_query_prompt",
                   "num_bot_responses": 5, "hyperparameters": Utility.get_llm_hyperparameters('openai'),
                   "set_slots": [{"name": "gpt_result", "value": "${data}", "evaluation_type": "expression"},
                                 {"name": "gpt_result_type", "value": "${data.type}", "evaluation_type": "script"}],
                   "dispatch_response": False
                   }
        processor.edit_prompt_action(pytest.action_id, request, bot, user)
        action = list(processor.get_prompt_action(bot))
        action[0].pop("_id")
        assert not DeepDiff(action, [{
            'name': 'test_edit_prompt_action_faq_action',
            'num_bot_responses': 5,
            'failure_message': 'updated_failure_message',
            'user_question': {'type': 'from_user_message'},
            'hyperparameters': {
                'temperature': 0.0,
                'max_tokens': 300,
                'model': 'gpt-4.1-mini',
                'top_p': 0.0,
                'n': 1,
                'stop': None,
                'presence_penalty': 0.0,
                'frequency_penalty': 0.0,
                'logit_bias': {}
            },
            'llm_type': 'openai',
            'process_media': False,
            'llm_prompts': [
                {
                    'name': 'System Prompt',
                    'data': 'You are a personal assistant.',
                    'type': 'system',
                    'source': 'static',
                    'is_enabled': True
                },
                {
                    'name': 'Similarity Prompt',
                    'data': 'test_collection',
                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                    'type': 'user',
                    'source': 'bot_content',
                    'is_enabled': True
                },
                {
                    'name': 'Query Prompt',
                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                    'instructions': 'Answer according to the context',
                    'type': 'query',
                    'source': 'static',
                    'is_enabled': True
                },
                {
                    'name': 'Query Prompt',
                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                    'instructions': 'Answer according to the context',
                    'type': 'query',
                    'source': 'static',
                    'is_enabled': True
                }
            ],
            'instructions': [],
            'set_slots': [
                {'name': 'gpt_result', 'value': '${data}', 'evaluation_type': 'expression'},
                {'name': 'gpt_result_type', 'value': '${data.type}', 'evaluation_type': 'script'}
            ],
            'dispatch_response': False,
            'status': True
        }], ignore_order=True)

        request = {'name': 'test_edit_prompt_action_faq_action_again',
               'user_question': {'type': 'from_slot', 'value': 'prompt_question'},
               'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                'source': 'static'}],
               'instructions': ['Answer in a short manner.', 'Keep it simple.']}
        processor.edit_prompt_action(pytest.action_id, request, bot, user)
        action = list(processor.get_prompt_action(bot))
        action[0].pop("_id")
        assert not DeepDiff(action, [{
            'name': 'test_edit_prompt_action_faq_action_again',
            'num_bot_responses': 5,
            'failure_message': "I'm sorry, I didn't quite understand that. Could you rephrase?",
            'user_question': {'type': 'from_slot', 'value': 'prompt_question'},
            'llm_type': 'openai',
            "process_media": False,
            'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4.1-mini',
                                'top_p': 0.0, 'n': 1, 'stop': None,
                                'presence_penalty': 0.0, 'frequency_penalty': 0.0, 'logit_bias': {}},
            'llm_prompts': [
                {'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                 'source': 'static', 'is_enabled': True}],
            'instructions': ['Answer in a short manner.', 'Keep it simple.'], 'set_slots': [],
            'dispatch_response': True, 'status': True}], ignore_order=True)

        LLMSecret.objects.delete()

    def test_edit_prompt_action_faq_action_llm_type_and_hyperparameters(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'

        llm_secret = LLMSecret(
            llm_type="anthropic",
            api_key='value',
            models=["claude-3-7-sonnet-20250219"],
            bot=bot,
            user=user
        )
        llm_secret.save()
        CognitionSchema(
            metadata=[
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            collection_name="test_collection",
            user=user,
            bot=bot,
            timestamp=utc_now(),
            schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
        ).save()

        request = {'name': 'test_edit_prompt_action_faq_action',
                   'user_question': {'type': 'from_user_message'},
                   'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Similarity Prompt', 'data': 'test_collection',
                                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True},
                                   {'name': 'Query Prompt',
                                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                                    'instructions': 'Answer according to the context', 'type': 'query',
                                    'source': 'static', 'is_enabled': True}],
                   "failure_message": "updated_failure_message",
                   "llm_type": "anthropic",
                   "hyperparameters": Utility.get_llm_hyperparameters('anthropic'),
                   "use_query_prompt": True, "use_bot_responses": True, "query_prompt": "updated_query_prompt",
                   "num_bot_responses": 5,
                   "set_slots": [{"name": "gpt_result", "value": "${data}", "evaluation_type": "expression"},
                                 {"name": "gpt_result_type", "value": "${data.type}", "evaluation_type": "script"}],
                   "dispatch_response": False
                   }
        processor.edit_prompt_action(pytest.action_id, request, bot, user)
        action = list(processor.get_prompt_action(bot))
        action[0].pop("_id")
        assert not DeepDiff(action, [{
            'name': 'test_edit_prompt_action_faq_action',
            'num_bot_responses': 5,
            'failure_message': 'updated_failure_message',
            'user_question': {'type': 'from_user_message'},
            'hyperparameters': {'max_tokens': 1024, 'model': 'claude-3-7-sonnet-20250219'},
            'llm_type': 'anthropic',
            "process_media": False,
            'llm_prompts': [
                {'name': 'System Prompt',
                 'data': 'You are a personal assistant.',
                 'type': 'system',
                 'source': 'static',
                 'is_enabled': True
                 },
                {'name': 'Similarity Prompt',
                 'data': 'test_collection',
                 'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                 'type': 'user',
                 'source': 'bot_content',
                 'is_enabled': True
                 },
                {'name': 'Query Prompt',
                 'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                 'instructions': 'Answer according to the context',
                 'type': 'query',
                 'source': 'static',
                 'is_enabled': True
                 },
                {'name': 'Query Prompt',
                 'data': 'If there is no specific query, assume that user is aking about java programming.',
                 'instructions': 'Answer according to the context',
                 'type': 'query',
                 'source': 'static',
                 'is_enabled': True
                 }
            ],
            'instructions': [],
            'set_slots': [
                {'name': 'gpt_result', 'value': '${data}', 'evaluation_type': 'expression'},
                {'name': 'gpt_result_type', 'value': '${data.type}', 'evaluation_type': 'script'}
            ],
            'dispatch_response': False,
            'status': True
        }], ignore_order=True)

        LLMSecret.objects.delete()

    def test_edit_prompt_action_with_less_hyperparameters(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()
        CognitionSchema(
            metadata=[
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            collection_name="test_collection",
            user=user,
            bot=bot,
            timestamp=utc_now(),
            schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
        ).save()

        request = {'name': 'test_edit_prompt_action_with_less_hyperparameters',
               'user_question': {'type': 'from_slot', 'value': 'prompt_question'},
               "process_media": False,
               'llm_prompts': [
                   {'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                    'source': 'static', 'is_enabled': True},
                   {'name': 'Similarity Prompt', 'data': 'test_collection',
                    'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                    'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                   {'name': 'Query Prompt',
                    'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                    'instructions': 'Answer according to the context', 'type': 'query', 'source': 'static',
                    'is_enabled': True},
                   {'name': 'Query Prompt',
                    'data': 'If there is no specific query, assume that user is aking about java programming.',
                    'instructions': 'Answer according to the context', 'type': 'query',
                    'source': 'static', 'is_enabled': True}],
               "failure_message": "updated_failure_message", "top_results": 10, "similarity_threshold": 0.70,
               "use_query_prompt": True, "use_bot_responses": True, "query_prompt": "updated_query_prompt",
               "num_bot_responses": 5, "hyperparameters": {"temperature": 0.0,
                                                           "max_tokens": 300,
                                                           "model": "gpt-4.1-mini",
                                                           "top_p": 0.0,
                                                           "n": 1}}

        processor.edit_prompt_action(pytest.action_id, request, bot, user)
        action = list(processor.get_prompt_action(bot))
        action[0].pop("_id")
        assert not DeepDiff(action, [{
            'name': 'test_edit_prompt_action_with_less_hyperparameters',
            'num_bot_responses': 5,
            'failure_message': 'updated_failure_message',
            'user_question': {'type': 'from_slot', 'value': 'prompt_question'},
            'hyperparameters': {
                'temperature': 0.0,
                'max_tokens': 300,
                'model': 'gpt-4.1-mini',
                'top_p': 0.0,
                'n': 1,
                'stop': None,
                'presence_penalty': 0.0,
                'frequency_penalty': 0.0,
                'logit_bias': {}
            },
            'llm_type': 'openai',
            "process_media": False,
            'llm_prompts': [
                {'name': 'System Prompt',
                 'data': 'You are a personal assistant.',
                 'type': 'system',
                 'source': 'static',
                 'is_enabled': True
                 },
                {'name': 'Similarity Prompt',
                 'data': 'test_collection',
                 'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                 'type': 'user',
                 'source': 'bot_content',
                 'is_enabled': True
                 },
                {'name': 'Query Prompt',
                 'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                 'instructions': 'Answer according to the context',
                 'type': 'query',
                 'source': 'static',
                 'is_enabled': True
                 },
                {'name': 'Query Prompt',
                 'data': 'If there is no specific query, assume that user is aking about java programming.',
                 'instructions': 'Answer according to the context',
                 'type': 'query',
                 'source': 'static',
                 'is_enabled': True
                 }
            ],
            'instructions': [],
            'set_slots': [],
            'dispatch_response': True,
            'status': True
        }], ignore_order=True)

        LLMSecret.objects.delete()

    def test_get_prompt_action_does_not_exist(self):
        processor = MongoProcessor()
        bot = 'invalid_bot'
        action = list(processor.get_prompt_action(bot))
        assert action == []

    def test_get_prompt_faq_action(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = "test+user"
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()
        CognitionSchema(
            metadata=[
                {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
                {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            collection_name="test_collection",
            user=user,
            bot=bot,
            timestamp=utc_now(),
            schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
        ).save()

        action = list(processor.get_prompt_action(bot))
        action[0].pop("_id")
        assert not DeepDiff(action, [{
            'name': 'test_edit_prompt_action_with_less_hyperparameters',
            'num_bot_responses': 5,
            'failure_message': 'updated_failure_message',
            'user_question': {'type': 'from_slot', 'value': 'prompt_question'},
            'hyperparameters': {
                'temperature': 0.0,
                'max_tokens': 300,
                'model': 'gpt-4.1-mini',
                'top_p': 0.0,
                'n': 1,
                'stop': None,
                'presence_penalty': 0.0,
                'frequency_penalty': 0.0,
                'logit_bias': {}
            },
            'llm_type': 'openai',
            "process_media": False,
            'llm_prompts': [
                {'name': 'System Prompt',
                 'data': 'You are a personal assistant.',
                 'type': 'system',
                 'source': 'static',
                 'is_enabled': True
                 },
                {'name': 'Similarity Prompt',
                 'data': 'test_collection',
                 'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                 'type': 'user',
                 'source': 'bot_content',
                 'is_enabled': True
                 },
                {'name': 'Query Prompt',
                 'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                 'instructions': 'Answer according to the context',
                 'type': 'query',
                 'source': 'static',
                 'is_enabled': True
                 },
                {'name': 'Query Prompt',
                 'data': 'If there is no specific query, assume that user is aking about java programming.',
                 'instructions': 'Answer according to the context',
                 'type': 'query',
                 'source': 'static',
                 'is_enabled': True
                 }
            ],
            'instructions': [],
            'set_slots': [],
            'dispatch_response': True,
            'status': True
        }], ignore_order=True)

        LLMSecret.objects.delete()

    def test_delete_prompt_action(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        processor.delete_action("test_add_prompt_action_faq_action_with_default_values", bot, user)

    def test_delete_prompt_action_already_deleted(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        with pytest.raises(AppException,
                           match=f'Action with name "test_add_prompt_action_faq_action_with_default_values" not found'):
            processor.delete_action('test_add_prompt_action_faq_action_with_default_values', bot, user)

    def test_delete_prompt_action_not_present(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        with pytest.raises(AppException, match=f'Action with name "non_existent_kairon_faq_action" not found'):
            processor.delete_action('non_existent_kairon_faq_action', bot, user)

from tests.unit_test.data_processor.data_processor_support import *  # noqa: F403
from tests.unit_test.data_processor.data_processor_support import (
    MongoProcessorTestBase,
    fast_rasa_training,
)

class TestMongoProcessor(MongoProcessorTestBase):
    def test_save_faq_csv(self):
        processor = MongoProcessor()
        bot = 'tests'
        user = 'tester'
        file = UploadFile(filename="upload.csv", file=open("./tests/testing_data/upload_faq/upload.csv", "rb"))
        df = Utility.read_faq(file)
        component_count, error_summary = processor.save_faq(bot, user, df)
        assert component_count == {'intents': 0, 'utterances': 5, 'stories': 0, 'rules': 0, 'training_examples': 5,
                                   'domain': {'intents': 0, 'utterances': 0}}
        assert error_summary == {'intents': [], 'utterances': ['Utterance text cannot be empty or blank spaces'],
                                 'training_examples': ['Training Example cannot be empty or blank spaces:    ']}

    def test_save_faq_xlsx(self):
        processor = MongoProcessor()
        bot = 'test_faq'
        user = 'tester'
        file = UploadFile(filename="upload.xlsx", file=open("./tests/testing_data/upload_faq/upload.xlsx", "rb"))
        df = Utility.read_faq(file)
        component_count, error_summary = processor.save_faq(bot, user, df)
        assert component_count == {'intents': 0, 'utterances': 5, 'stories': 0, 'rules': 0, 'training_examples': 5,
                                   'domain': {'intents': 0, 'utterances': 0}}
        assert error_summary == {'intents': [], 'utterances': ['Utterance text cannot be empty or blank spaces',
                                                               'Utterance already exists!'],
                                 'training_examples': ['Training Example cannot be empty or blank spaces: ']}

    def test_save_faq_delete_data(self):
        processor = MongoProcessor()
        bot = 'test_save_faq_delete_data'
        user = 'tester'

        def __mock_exception(*args, **kwargs):
            raise Exception("Failed to add story")

        df = pd.DataFrame([{"questions": "what is digite?", "answer": "IT company"}])
        with patch("kairon.shared.data.processor.MongoProcessor.add_complex_story") as mock_failure:
            mock_failure.side_effect = __mock_exception
            component_count, error_summary = processor.save_faq(bot, user, df)
        assert component_count == {'intents': 0, 'utterances': 1, 'stories': 0, 'rules': 0, 'training_examples': 1,
                                   'domain': {'intents': 0, 'utterances': 0}}
        assert error_summary == {'intents': [], 'utterances': ['Failed to add story'], 'training_examples': []}

    def test_validate_faq_training_file(self, monkeypatch):
        processor = MongoProcessor()
        bot = 'tests_faq'
        utterance = "test_delete_utterance"
        user = 'testUser'
        file = UploadFile(filename="validate.csv", file=open("./tests/testing_data/upload_faq/validate.csv", "rb"))
        df = Utility.read_faq(file)
        processor.add_response({"text": "I am good here!!"}, utterance, bot, user)
        training_examples_expected = {'hi': 'greet', 'hello': 'greet', 'ok': 'affirm', 'no': 'deny'}

        def _mongo_aggregation(*args, **kwargs):
            return training_examples_expected

        monkeypatch.setattr(MongoProcessor, 'get_training_examples_as_dict', _mongo_aggregation)
        error_summary, component_count = DataUtility.validate_faq_training_data(bot, df)
        assert len(error_summary['utterances']) == 3
        assert len(error_summary['training_examples']) == 4
        assert component_count == {'intents': 0, 'utterances': 8, 'stories': 0, 'rules': 0, 'training_examples': 10,
                                   'domain': {'intents': 0, 'utterances': 0}}

    def test_validate_faq_training_file_empty(self):
        bot = 'tests'
        df = pd.DataFrame()
        with pytest.raises(AppException, match="No data found!"):
            DataUtility.validate_faq_training_data(bot, df)

    def test_delete_all_faq(self, monkeypatch):
        processor = MongoProcessor()
        utterances_query_counter = 0
        intents_query_counter = 0
        first_list = ['Hi', 'Hey', 'hello']
        second_list = ['unhappy', 'sad']
        var = ['good morning', 'morning']
        first_steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        first_rule_dict = {'name': "first rule", 'steps': first_steps, 'type': 'RULE', 'template_type': 'Q&A'}
        second_steps = [
            {"name": "sad", "type": "INTENT"},
            {"name": "utter_sad", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        second_rule_dict = {'name': "second rule", 'steps': second_steps, 'type': 'RULE', 'template_type': 'Q&A'}

        list(processor.add_training_example(first_list, 'greet', 'test', 'test_user', False))
        list(processor.add_training_example(second_list, 'sad', 'test', 'test_user', False))
        list(processor.add_training_example(var, 'message', 'test', 'test_user', False))
        processor.add_text_response('I am good', 'utter_greet', 'test', 'test_user')
        processor.add_text_response('I am sad', 'utter_sad', 'test', 'test_user')
        processor.add_text_response('What are your questions?', 'utter_ask', 'test', 'test_user')
        processor.add_complex_story(first_rule_dict, 'test', 'test_user')
        processor.add_complex_story(second_rule_dict, 'test', 'test_user')

        def _mock_aggregation(*args, **kwargs):
            nonlocal utterances_query_counter, intents_query_counter

            get_intents_pipelines = [
                {'$unwind': {'path': '$events'}},
                {'$match': {'events.type': 'user'}},
                {'$group': {'_id': None, 'intents': {'$push': '$events.name'}}},
                {"$project": {'_id': 0, 'intents': 1}}
            ]
            get_utterances_pipelines = [
                {'$unwind': {'path': '$events'}},
                {'$match': {'events.type': 'action', 'events.name': {'$regex': '^utter_'}}},
                {'$group': {'_id': None, 'utterances': {'$push': '$events.name'}}},
                {"$project": {'_id': 0, 'utterances': 1}}
            ]
            print(args[1])
            print(args[0]._mongo_query)
            if args[0]._collection_obj.name == 'stories':
                print("stories")
                yield {'intents': [], 'utterances': []}
            elif args[1] == get_intents_pipelines and intents_query_counter == 0:
                intents_query_counter += 1
                print("intents")
                yield {'intents': ['greet', 'sad']}
            elif args[1] == get_utterances_pipelines and utterances_query_counter == 0:
                utterances_query_counter += 1
                print("utterances")
                yield {'utterances': ['utter_greet', 'utter_sad']}
            else:
                print("else")
                yield {'intents': [], 'utterances': []}

        monkeypatch.setattr(BaseQuerySet, 'aggregate', _mock_aggregation)
        processor.delete_all_faq('test')
        assert not Utility.is_exist(TrainingExamples, raise_error=False, intent='greet', bot='test')
        assert not Utility.is_exist(TrainingExamples, raise_error=False, intent='sad', bot='test')
        assert not Utility.is_exist(Intents, raise_error=False, name='greet', bot='test')
        assert not Utility.is_exist(Intents, raise_error=False, name='sad', bot='test')
        assert not Utility.is_exist(Utterances, raise_error=False, name='utter_greet', bot='test')
        assert not Utility.is_exist(Utterances, raise_error=False, name='utter_sad', bot='test')
        assert not Utility.is_exist(Responses, raise_error=False, name='utter_greet', bot='test')
        assert not Utility.is_exist(Responses, raise_error=False, name='utter_sad', bot='test')
        assert not Utility.is_exist(Rules, raise_error=False, block_name='first rule', bot='test')
        assert not Utility.is_exist(Rules, raise_error=False, block_name='second rule', bot='test')
        assert Utility.is_exist(TrainingExamples, raise_error=False, intent='message', bot='test')
        assert Utility.is_exist(Intents, raise_error=False, name='message', bot='test')
        assert Utility.is_exist(Utterances, raise_error=False, name='utter_ask', bot='test')
        assert Utility.is_exist(Responses, raise_error=False, name='utter_ask', bot='test')

    def test_save_payload_metadata(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        settings = BotSettings.objects(bot=bot).get()
        settings.llm_settings = LLMSettings(enable_faq=True)
        settings.cognition_collections_limit = 5
        settings.save()
        schema = {
            "metadata": [
                {"column_name": "details", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "Details_collection",
            "bot": bot,
            "user": user
        }
        pytest.schema_id = processor.save_cognition_schema(schema, user, bot)

        cognition_schema = CognitionSchema.objects(bot=bot, id=pytest.schema_id).get()
        assert cognition_schema['collection_name'] == 'details_collection'
        assert cognition_schema['metadata'][0]['column_name'] == 'details'
        assert cognition_schema['metadata'][0]['data_type'] == "str"

        payload = {
            "data": {"details": "Pune"},
            "collection": "Details_collection",
            "content_type": "json"}
        processor.save_cognition_data(payload, user, bot)
        pytest.cognition_id = processor.save_cognition_data(payload, user, bot)

        cognition_data = CognitionData.objects(bot=bot, id=pytest.cognition_id).get()
        assert cognition_data['data'] == {"details": "Pune"}
        assert cognition_data['collection'] == 'details_collection'
        assert cognition_data['content_type'] == CognitionDataType.json.value

        schema_one = {
            "metadata": [
                {"column_name": "metadata_one", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "metadata_one",
            "bot": bot,
            "user": user
        }
        pytest.schema_id_one = processor.save_cognition_schema(schema_one, user, bot)

        schema_two = {
            "metadata": [
                {"column_name": "metadata_two", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "metadata_two",
            "bot": bot,
            "user": user
        }
        pytest.schema_id_two = processor.save_cognition_schema(schema_two, user, bot)

        schema_three = {
            "metadata": [
                {"column_name": "metadata_three", "data_type": "str", "enable_search": True,
                 "create_embeddings": True}],
            "collection_name": "metadata_three",
            "bot": bot,
            "user": user
        }
        with pytest.raises(AppException, match="Collection limit exceeded!"):
            processor.save_cognition_schema(schema_three, user, bot)
        processor.delete_cognition_schema(pytest.schema_id_one, bot, user=user)
        processor.delete_cognition_schema(pytest.schema_id_two, bot, user=user)
        schema_four = {
            "metadata": [
                {"column_name": "details", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "details_collection",
            "bot": bot,
            "user": user
        }
        with pytest.raises(AppException, match="Collection already exists!"):
            processor.save_cognition_schema(schema, user, bot)

        data = list(processor.list_cognition_schema(bot))

        # Fetch all schema IDs
        schema_ids = [schema['_id'] for schema in processor.list_cognition_schema(bot)]

        # Fetch all collection names
        collection_names = [schema['collection_name'] for schema in processor.list_cognition_schema(bot)]

        # Delete all collection except the last one
        for collection_name in collection_names[:-1]:
            for data in CognitionData.objects(bot=bot, collection=collection_name):
                data.delete()

        # Delete all schema except the last one
        for schema_id in schema_ids[:-1]:
            processor.delete_cognition_schema(schema_id, bot, user=user)

        data = list(processor.list_cognition_schema(bot))
        settings = BotSettings.objects(bot=bot).get()
        settings.llm_settings = LLMSettings(enable_faq=False)
        settings.save()

    def test_list_cognition_schema_with_embedding_metadata(self):
        bot = "test_bot"

        mock_doc = MagicMock()
        schema_data = {
            "_id": "123",
            "metadata": [{"key": "value"}],
            "collection_name": "test_collection",
            "schema_metadata": {
                "training_needed": False,
                "model_id": "custom-model",
                "size": 512,
                "provider": "openai"
            }
        }

        mock_doc.to_mongo.return_value.to_dict.return_value = schema_data

        with patch("kairon.shared.cognition.data_objects.CognitionSchema.objects") as mock_cognition_objects:
            mock_cognition_objects.return_value = [mock_doc]

            obj = CognitionDataProcessor()
            result = list(obj.list_cognition_schema(bot))

            assert len(result) == 1
            data = result[0]

            assert data["_id"] == "123"
            assert data["metadata"] == [{"key": "value"}]
            assert data["collection_name"] == "test_collection"

            assert data["schema_metadata"]["model_id"] == "custom-model"
            assert data["schema_metadata"]["size"] == 512

    def test_save_payload_metadata_column_limit_exceeded(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        schema = {
            "metadata": [
                {"column_name": "tech", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "age", "data_type": "int", "enable_search": True, "create_embeddings": False},
                {"column_name": "color", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "name", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "gender", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "experience", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            "collection_name": "test_save_payload_metadata_column_limit_exceeded",
            "bot": bot,
            "user": user
        }
        with pytest.raises(AppException, match="Column limit exceeded for collection!"):
            processor.save_cognition_schema(schema, user, bot)

    def test_save_payload_metadata_same_columns(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        schema = {
            "metadata": [
                {"column_name": "tech", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "tech", "data_type": "int", "enable_search": True, "create_embeddings": False}],
            "collection_name": "details_collect",
            "bot": bot,
            "user": user
        }
        with pytest.raises(AppException, match="Columns cannot be same in the schema!"):
            processor.save_cognition_schema(schema, user, bot)

    def test_save_payload_metadata_column_name_empty(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        schema = {
            "metadata": [{"column_name": "", "data_type": "int", "enable_search": True,
                          "create_embeddings": True}],
            "collection_name": "column_name_empty",
            "bot": bot,
            "user": user}
        with pytest.raises(ValidationError, match="Column name cannot be empty"):
            CognitionSchema(**schema).save()

    def test_save_payload_metadata_data_type_invalid(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        schema = {
            "metadata": [{"column_name": "name", "data_type": "bool", "enable_search": True,
                          "create_embeddings": True}],
            "collection_name": "test_save_payload_metadata_data_type_invalid",
            "bot": bot,
            "user": user
        }
        with pytest.raises(ValidationError, match="Only str,int and float data types are supported"):
            CognitionSchema(**schema).save()

    def test_get_payload_metadata(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        data = list(processor.list_cognition_schema(bot))
        print(data)
        assert data[0]
        assert data[0]['_id']
        assert data[0]['metadata'][0] == {'column_name': 'details', 'data_type': 'str', 'enable_search': True,
                                          'create_embeddings': True}
        assert data[0]['collection_name'] == 'details_collection'

    def test_delete_payload_metadata(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        processor.delete_cognition_schema(pytest.schema_id, bot, user=user)

    def test_delete_cognition_schema_with_data(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        schema = {
            "metadata": [
                {"column_name": "employee", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "details_collection_with_data",
            "bot": bot,
            "user": user
        }

        schema_id = processor.save_cognition_schema(schema, user, bot)

        CognitionData(collection=schema['collection_name'], bot=bot, user=user, data={"employee": "John Doe"}, content_type="json",).save()
        CognitionData(collection=schema['collection_name'], bot=bot, user=user, data={"employee": "Jane Smith"}, content_type="json",).save()

        assert CognitionData.objects(collection=schema['collection_name'], bot=bot).count() == 2

        processor.delete_cognition_schema(schema_id, bot, user=user)

        assert CognitionData.objects(collection=schema['collection_name'], bot=bot).count() == 0

    def test_save_payload_metadata_and_delete_with_no_cognition_data(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        schema = {
            "metadata": [
                {"column_name": "employee", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "details_collection",
            "bot": bot,
            "user": user
        }
        pytest.schema_id_final = processor.save_cognition_schema(schema, user, bot)
        processor.delete_cognition_schema(pytest.schema_id_final, bot, user=user)

    def test_delete_payload_metadata_does_not_exists(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        with pytest.raises(AppException, match="Schema does not exists!"):
            processor.delete_cognition_schema("507f191e050c19729de760ea", bot, user=user)

    def test_get_payload_metadata_not_exists(self):
        processor = CognitionDataProcessor()
        bot = 'testing'
        assert list(processor.list_cognition_schema(bot)) == []

    def test_delete_schema_attached_to_prompt_action(self):
        processor = CognitionDataProcessor()
        processor_two = MongoProcessor()
        bot = 'test'
        user = 'testUser'
        settings = BotSettings.objects(bot=bot).get()
        settings.llm_settings = LLMSettings(enable_faq=True)
        settings.save()

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()

        schema = {
            "metadata": None,
            "collection_name": "Python",
            "bot": bot,
            "user": user
        }
        pytest.delete_schema_id = processor.save_cognition_schema(schema, user, bot)
        request = {'name': 'test_delete_schema_attached_to_prompt_action',
                   'user_question': {'type': 'from_slot', 'value': 'prompt_question'},
                   'llm_prompts': [
                       {'name': 'System Prompt',
                        'data': 'You are a personal assistant. Answer question based on the context below.',
                        'type': 'system', 'source': 'static', 'is_enabled': True},
                       {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True},
                       {'name': 'Query Prompt', 'data': "What kind of language is python?",
                        'instructions': 'Rephrase the query.',
                        'type': 'query', 'source': 'static', 'is_enabled': False},
                       {'name': 'Similarity Prompt', "data": "python",
                        'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                        'type': 'user', 'source': 'bot_content',
                        'is_enabled': True}
                   ],
                   'instructions': ['Answer in a short manner.', 'Keep it simple.'],
                   "set_slots": [{"name": "gpt_result", "value": "${data}", "evaluation_type": "expression"},
                                 {"name": "gpt_result_type", "value": "${data.type}", "evaluation_type": "script"}],
                   "dispatch_response": False
                   }
        processor_two.add_prompt_action(request, bot, user)
        with pytest.raises(AppException,
                           match='Cannot remove collection python linked to action "test_delete_schema_attached_to_prompt_action"!'):
            processor.delete_cognition_schema(pytest.delete_schema_id, bot, user=user)
        processor_two.delete_action('test_delete_schema_attached_to_prompt_action', bot, user)
        processor.delete_cognition_schema(pytest.delete_schema_id, bot, user=user)
        LLMSecret.objects.delete()

    def test_save_content_with_gpt_feature_disabled(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        settings = BotSettings.objects(bot=bot).get()
        settings.llm_settings = LLMSettings(enable_faq=False)
        settings.save()
        collection = "Bot"
        content = 'A bot, short for robot, is a program or software application designed to automate certain tasks or ' \
                  'perform specific functions, usually in an automated or semi-automated manner. Bots can be programmed' \
                  ' to perform a wide range of tasks, from simple tasks like answering basic questions or sending ' \
                  'automated messages to complex tasks like performing data analysis, playing games, or even controlling ' \
                  'physical machines.'
        payload = {
            "data": content,
            "content_type": "text",
            "collection": collection}
        with pytest.raises(AppException, match="Faq feature is disabled for the bot! Please contact support."):
            processor.save_cognition_data(payload, user, bot)

        settings = BotSettings.objects(bot=bot).get()
        settings.llm_settings = LLMSettings(enable_faq=True)
        settings.save()

    def test_save_content_atleast_ten_words(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        collection = 'Bot'
        content = 'A bot, short for robot, is a program.'
        payload = {
            "data": content,
            "content_type": "text",
            "collection": collection}
        with pytest.raises(AppException, match="Content should contain atleast 10 words."):
            processor.save_cognition_data(payload, user, bot)

    def test_save_content_collection_does_not_exist(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        collection = 'Bot'
        content = 'A bot, short for robot, is a program. Bots can be programmed to perform a wide range of tasks.'
        payload = {
            "data": content,
            "content_type": "text",
            "collection": collection}
        with pytest.raises(AppException, match="Collection does not exist!"):
            processor.save_cognition_data(payload, user, bot)

    def test_save_content_text_with_metadata_invalid(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        collection = "test_save_content_text_with_metadata_invalid"
        content = 'A large language model is a type of artificial intelligence system designed to understand and generate human language.'
        payload = {
            "data": content,
            "content_type": "text",
            "collection": collection}
        metadata = {
            "metadata": [
                {"column_name": "LLM", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": collection,
            "bot": bot,
            "user": user
        }
        processor.save_cognition_schema(metadata, user, bot)
        with pytest.raises(AppException, match="Text content type does not have schema!"):
            processor.save_cognition_data(payload, user, bot)

    def test_save_content(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        collection = "Bot"
        content = 'A bot, short for robot, is a program or software application designed to automate certain tasks or ' \
                  'perform specific functions, usually in an automated or semi-automated manner. Bots can be programmed' \
                  ' to perform a wide range of tasks, from simple tasks like answering basic questions or sending ' \
                  'automated messages to complex tasks like performing data analysis, playing games, or even controlling ' \
                  'physical machines.'
        payload = {
            "data": content,
            "content_type": "text",
            "collection": collection}
        metadata = {
            "metadata": None,
            "collection_name": collection,
            "bot": bot,
            "user": user
        }
        pytest.save_content_collection = processor.save_cognition_schema(metadata, user, bot)
        pytest.content_id = processor.save_cognition_data(payload, user, bot)
        content_id = '5349b4ddd2791d08c09890f3'
        with pytest.raises(AppException, match="Payload data already exists!"):
            processor.update_cognition_data(content_id, payload, user, bot)

    def test_update_content_atleast_ten_words(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        collection = 'Bot'
        content = 'Bots are commonly used in various industries.'
        payload = {
            "data": content,
            "content_type": "text",
            "collection": collection}
        with pytest.raises(AppException, match="Content should contain atleast 10 words."):
            processor.update_cognition_data(pytest.content_id, payload, user, bot)

    def test_update_content_collection_does_not_exists(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        collection = 'test_update_content_collection_does_not_exists'
        content = 'LLMs can be used for a wide range of applications, including chatbots, language translation, content generation, sentiment analysis, and many other natural language processing tasks. '
        payload = {
            "data": content,
            "content_type": "text",
            "collection": collection}
        with pytest.raises(AppException, match="Collection does not exist!"):
            processor.update_cognition_data(pytest.content_id, payload, user, bot)

    def test_update_content(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        collection = 'Bot'
        content = 'Bots are commonly used in various industries, such as e-commerce, customer service, gaming, ' \
                  'and social media. Some bots are designed to interact with humans in a conversational manner and are ' \
                  'called chatbots or virtual assistants.'
        payload = {
            "data": content,
            "content_type": "text",
            "collection": collection}
        processor.update_cognition_data(pytest.content_id, payload, user, bot)

    def test_update_content_not_found(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        content_id = '5349b4ddd2781d08c09890f3'
        collection = 'Bot'
        content = 'MongoDB is a source-available cross-platform document-oriented database program. ' \
                  'Classified as a NoSQL database program, MongoDB uses JSON-like documents with optional schemas. ' \
                  'MongoDB is developed by MongoDB Inc. and licensed under the Server Side Public License which is ' \
                  'deemed non-free by several distributions.'
        payload = {
            "data": content,
            "content_type": "text",
            "collection": collection}
        with pytest.raises(AppException, match="Payload with given id not found!"):
            processor.update_cognition_data(content_id, payload, user, bot)

    def test_delete_content(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        processor.delete_cognition_data(pytest.content_id, bot, user=user)

    def test_delete_content_does_not_exists(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        with pytest.raises(AppException, match="Payload does not exists!"):
            processor.delete_cognition_data("507f191e810c19729de860ea", bot)

    @patch("kairon.shared.cognition.processor.CognitionDataProcessor.list_cognition_data", autospec=True)
    def test_list_cognition_data_not_exists(self, mock_list_cognition_data):
        def _list_cognition_data(*args, **kwargs):
            return []

        mock_list_cognition_data.return_value = _list_cognition_data()
        kwargs = {}
        processor = CognitionDataProcessor()
        bot = 'test'
        assert list(processor.list_cognition_data(bot, **kwargs)) == []

    @patch("kairon.shared.cognition.processor.CognitionDataProcessor.list_cognition_data", autospec=True)
    @patch("kairon.shared.cognition.processor.CognitionDataProcessor.get_cognition_data", autospec=True)
    def test_list_cognition_data(self, mock_get_cognition_data, mock_list_cognition_data):
        cognition_data = [{'vector_id': 1,
                           'row_id': '65266ff16f0190ca4fd09898',
                           'data': 'Unit testing is a software testing technique in which individual units or components of a software application are tested in isolation to ensure that each unit functions as expected. ',
                           'content_type': 'text',
                           'collection': 'bot', 'user': 'testUser', 'bot': 'test'}]
        row_count = 1

        def _list_cognition_data(*args, **kwargs):
            return cognition_data

        mock_list_cognition_data.return_value = _list_cognition_data()

        def _get_cognition_data(*args, **kwargs):
            return cognition_data, row_count

        mock_get_cognition_data.return_value = _get_cognition_data()
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        content = 'Unit testing is a software testing technique in which individual units or components of a software ' \
                  'application are tested in isolation to ensure that each unit functions as expected. '
        payload = {
            "data": content,
            "content_type": "text",
            "collection": "Bot"}
        pytest.content_id_unit = processor.save_cognition_data(payload, user, bot)
        kwargs = {'collection': 'bot', 'data': 'Unit testing'}
        data = list(processor.list_cognition_data(bot, **kwargs))
        print(data)
        assert data[0][
                   'data'] == 'Unit testing is a software testing technique in which individual units or components of a ' \
                              'software application are tested in isolation to ensure that each unit functions as expected. '
        assert data[0]['row_id']
        assert data[0]['collection'] == 'bot'
        kwargs = {'collection': 'Bot', 'data': 'Unit testing'}
        log, count = processor.get_cognition_data(bot, **kwargs)
        assert log[0][
                   'data'] == 'Unit testing is a software testing technique in which individual units or components of a ' \
                              'software application are tested in isolation to ensure that each unit functions as expected. '
        assert log[0]['row_id']
        assert log[0]['collection'] == 'bot'
        assert count == 1
        kwargs = {}
        actual = list(processor.list_cognition_data(bot, **kwargs))
        print(actual)
        assert actual[0][
                   'data'] == 'Unit testing is a software testing technique in which individual units or components of a ' \
                              'software application are tested in isolation to ensure that each unit functions as expected. '
        assert actual[0]['row_id']
        assert actual[0]['collection'] == 'bot'
        cognition_data, row_count = processor.get_cognition_data(bot, **kwargs)
        assert cognition_data[0][
                   'data'] == 'Unit testing is a software testing technique in which individual units or components of a ' \
                              'software application are tested in isolation to ensure that each unit functions as expected. '
        assert cognition_data[0]['row_id']
        assert cognition_data[0]['collection'] == 'bot'
        assert row_count == 1

    def test_delete_content_for_action(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        processor.delete_cognition_data(pytest.content_id_unit, bot, user=user)

    def test_delete_payload_content_collection(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        processor.delete_cognition_schema(pytest.save_content_collection, bot, user=user)

    def test_save_payload_content_with_gpt_feature_disabled(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        payload = {
            "data": {"name": "Sita", "engineer": "yes"},
            "content_type": "json",
            "collection": "test_save_payload_content_with_gpt_feature_disabled",
            "bot": bot,
            "user": user
        }
        settings = BotSettings.objects(bot=bot).get()
        settings.llm_settings = LLMSettings(enable_faq=False)
        settings.save()
        with pytest.raises(AppException, match="Faq feature is disabled for the bot! Please contact support."):
            processor.save_cognition_data(payload, user, bot)

        settings = BotSettings.objects(bot=bot).get()
        settings.llm_settings = LLMSettings(enable_faq=True)
        settings.save()

    def test_save_payload_content_collection_does_not_exists(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        payload = {
            "data": {"name": "Nupur", "city": "Pune"},
            "collection": "test_save_payload_content_collection_does_not_exists",
            "content_type": "json"}
        with pytest.raises(AppException, match="Collection does not exist!"):
            processor.save_cognition_data(payload, user, bot)

    def test_save_payload_content(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        metadata = {
            "metadata": [
                {"column_name": "name", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "city", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "test_save_payload_content",
            "bot": bot,
            "user": user
        }
        processor.save_cognition_schema(metadata, user, bot)

        payload = {
            "data": {"name": "Nupur", "city": "Pune"},
            "collection": "test_save_payload_content",
            "content_type": "json"}
        pytest.payload_id = processor.save_cognition_data(payload, user, bot)
        payload_id = '64b0f2e66707e9282a13f6cd'
        with pytest.raises(AppException, match="Payload data already exists!"):
            processor.update_cognition_data(payload_id, payload, user, bot)

    def test_save_payload_content_metadata_does_not_exists(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        payload = {
            "data": {"number": 15, "group": "a"},
            "collection": "test_save_payload_content",
            "content_type": "json"}
        with pytest.raises(AppException, match="Columns do not exist in the schema!"):
            processor.save_cognition_data(payload, user, bot)

    def test_save_payload_content_invalid_data_type(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        metadata = {
            "metadata": [
                {"column_name": "number", "data_type": "int", "enable_search": True, "create_embeddings": True}],
            "collection_name": "test_save_payload_content_invalid_data_type",
            "bot": bot,
            "user": user
        }
        processor.save_cognition_schema(metadata, user, bot)
        payload = {
            "data": {"number": "Twenty-three"},
            "content_type": "json",
            "collection": "test_save_payload_content_invalid_data_type"}
        with pytest.raises(AppException, match="Invalid data type for 'number': Expected integer value"):
            processor.save_cognition_data(payload, user, bot)

    def test_save_payload_content_data_empty(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        payload = {
            "data": {},
            "content_type": "json",
            "bot": bot,
            "user": user
        }
        with pytest.raises(ValidationError, match="data cannot be empty"):
            CognitionData(**payload).save()

    def test_update_payload_content_not_found(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        payload_id = '5349b4ddd2719d08c09890f3'
        payload = {
            "data": {"city": "Pune", "color": "red"},
            "content_type": "json",
            "bot": bot,
            "user": user
        }
        with pytest.raises(AppException, match="Payload with given id not found!"):
            processor.update_cognition_data(payload_id, payload, user, bot)

    def test_save_payload_content_type_text_data_json_invalid(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        payload = {
            "data": {'color': 'red'},
            "content_type": "text",
            "bot": bot,
            "user": user
        }
        with pytest.raises(ValidationError, match="content type and type of data do not match!"):
            CognitionData(**payload).save()

    def test_update_payload_content_collection_does_not_exists(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        payload = {
            "data": {"city": "Pune", "color": "red"},
            "content_type": "json",
            "collection": "test_update_payload_content_collection_does_not_exists",
            "bot": bot,
            "user": user
        }
        with pytest.raises(AppException, match="Collection does not exist!"):
            processor.update_cognition_data(pytest.payload_id, payload, user, bot)

    def test_update_payload_content(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        payload = {
            "data": {"name": "Digite", "city": "Mumbai"},
            "content_type": "json",
            "collection": "test_save_payload_content",
            "bot": bot,
            "user": user
        }
        processor.update_cognition_data(pytest.payload_id, payload, user, bot)

    def test_get_payload_content(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        kwargs = {'collection': 'test_save_payload_content'}
        data, row_count = list(processor.get_cognition_data(bot, **kwargs))
        print(data)
        assert row_count == 1
        assert data[0][
                   'data'] == {"name": "Digite", "city": "Mumbai"}
        assert data[0]['row_id']
        assert data[0]['collection'] == 'test_save_payload_content'

    def test_delete_payload_content(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        processor.delete_cognition_data(pytest.payload_id, bot, user=user)

    def test_delete_payload_content_does_not_exists(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        with pytest.raises(AppException, match="Payload does not exists!"):
            processor.delete_cognition_data("507f191e050c19729de860ea", bot)

    def test_get_payload_content_not_exists(self):
        processor = CognitionDataProcessor()
        bot = 'testing'
        assert list(processor.list_cognition_data(bot)) == []

    def test_delete_multiple_payload_content(self):
        processor = CognitionDataProcessor()
        bot = 'test'
        user = 'testUser'
        collection = "multiple_delete_clear"

        metadata = {
            "metadata": None,
            "collection_name": collection,
            "bot": bot,
            "user": user
        }
        processor.save_cognition_schema(metadata, user, bot)
        contents = [
            "A bot is a software application designed to automate tasks.",
            "Bots can perform tasks like answering questions or analyzing data.",
            "Some bots control physical machines, craeate leads or play games."
        ]
        content_ids = []
        for content in contents:
            payload = {
                "data": content,
                "content_type": "text",
                "collection": collection
            }

            content_id = processor.save_cognition_data(payload, user, bot)
            content_ids.append(content_id)

        processor.delete_multiple_cognition_data(content_ids, bot, user)
        remaining_docs = CognitionData.objects(id__in=content_ids)
        assert remaining_docs.count() == 0

from tests.unit_test.data_processor.data_processor_support import *  # noqa: F403
from tests.unit_test.data_processor.data_processor_support import (
    MongoProcessorTestBase,
    fast_rasa_training,
)

class TestMongoProcessor(MongoProcessorTestBase):
    def test_validate_data_push_menu_success(self):
        bot = 'test_bot'
        user = 'test_user'
        collection_name = 'groceries'
        primary_key_col = "id"
        sync_type = 'push_menu'

        metadata = [
            {
                "column_name": "id",
                "data_type": "int",
                "enable_search": True,
                "create_embeddings": True
            },
            {
                "column_name": "item",
                "data_type": "str",
                "enable_search": True,
                "create_embeddings": True
            },
            {
                "column_name": "price",
                "data_type": "float",
                "enable_search": True,
                "create_embeddings": True
            },
            {
                "column_name": "quantity",
                "data_type": "int",
                "enable_search": True,
                "create_embeddings": True
            }
        ]

        cognition_schema = CognitionSchema(
            metadata=[ColumnMetadata(**item) for item in metadata],
            collection_name=collection_name,
            user=user,
            bot=bot,
            timestamp=utc_now()
        )
        cognition_schema.validate(clean=True)
        cognition_schema.save()

        data = [
            {"id": 1, "item": "Juice", "price": 2.50, "quantity": 10},
            {"id": 2, "item": "Apples", "price": 1.20, "quantity": 20},
            {"id": 3, "item": "Bananas", "price": 0.50, "quantity": 15},
        ]

        processor = CognitionDataProcessor()
        validation_summary = processor.validate_data(
            primary_key_col=primary_key_col,
            collection_name=collection_name,
            sync_type=sync_type,
            data=data,
            bot=bot
        )

        assert validation_summary == {}
        CognitionSchema.objects(bot=bot, collection_name="groceries").delete()

    def test_validate_data_item_toggle_success(self):
        bot = 'test_bot'
        user = 'test_user'
        collection_name = 'groceries'
        primary_key_col = "id"
        sync_type = "item_toggle"

        metadata = [
            {
                "column_name": "id",
                "data_type": "int",
                "enable_search": True,
                "create_embeddings": True
            },
            {
                "column_name": "item",
                "data_type": "str",
                "enable_search": True,
                "create_embeddings": True
            },
            {
                "column_name": "price",
                "data_type": "float",
                "enable_search": True,
                "create_embeddings": True
            },
            {
                "column_name": "quantity",
                "data_type": "int",
                "enable_search": True,
                "create_embeddings": True
            }
        ]

        cognition_schema = CognitionSchema(
            metadata=[ColumnMetadata(**item) for item in metadata],
            collection_name=collection_name,
            user=user,
            bot=bot,
            timestamp=utc_now()
        )
        cognition_schema.validate(clean=True)
        cognition_schema.save()

        dummy_data_one = {
            "id": 1,
            "item": "Juice",
            "price": 2.80,
            "quantity": 5
        }

        existing_document = CognitionData(
            data=dummy_data_one,
            content_type="json",
            collection=collection_name,
            user=user,
            bot=bot,
            timestamp=utc_now()
        )
        existing_document.save()

        dummy_data_two = {
            "id": 2,
            "item": "Milk",
            "price": 2.80,
            "quantity": 50
        }
        existing_document = CognitionData(
            data=dummy_data_two,
            content_type="json",
            collection=collection_name,
            user=user,
            bot=bot,
            timestamp=utc_now()
        )
        existing_document.save()

        data = [
            {"id": 1, "price": 2.50},
            {"id": 2, "price": 1.20}
        ]

        processor = CognitionDataProcessor()
        validation_summary = processor.validate_data(
            primary_key_col=primary_key_col,
            collection_name=collection_name,
            sync_type=sync_type,
            data=data,
            bot=bot
        )

        assert validation_summary == {}
        CognitionSchema.objects(bot=bot, collection_name="groceries").delete()
        CognitionData.objects(bot=bot, collection="groceries").delete()

    def test_validate_data_pydantic_validation_error(self):
        bot = 'test_bot'
        user = 'test_user'
        collection_name = 'groceries'
        primary_key_col = "id"
        sync_type = 'push_menu'

        metadata = [
            {
                "column_name": "id",
                "data_type": "int",
                "enable_search": True,
                "create_embeddings": True
            },
            {
                "column_name": "item",
                "data_type": "str",
                "enable_search": True,
                "create_embeddings": True
            },
            {
                "column_name": "price",
                "data_type": "float",
                "enable_search": True,
                "create_embeddings": True
            },
            {
                "column_name": "quantity",
                "data_type": "int",
                "enable_search": True,
                "create_embeddings": True
            }
        ]

        cognition_schema = CognitionSchema(
            metadata=[ColumnMetadata(**item) for item in metadata],
            collection_name=collection_name,
            user=user,
            bot=bot,
            timestamp=utc_now()
        )
        cognition_schema.validate(clean=True)
        cognition_schema.save()

        data = [
            {"id": 1, "item": "", "quantity": 10},
        ]

        processor = CognitionDataProcessor()
        validation_summary = processor.validate_data(
            primary_key_col=primary_key_col,
            collection_name=collection_name,
            sync_type=sync_type,
            data=data,
            bot=bot
        )

        assert isinstance(validation_summary, dict)
        assert 1 in validation_summary
        errors = validation_summary[1]
        assert isinstance(errors, list)
        assert len(errors) == 1

        error = errors[0]
        assert error["status"] == "Column length mismatch"
        assert error["expected_columns"] == ["id", "item", "price", "quantity"]
        assert error["actual_columns"] == ["id", "item", "quantity"]

        CognitionSchema.objects(bot=bot, collection_name="groceries").delete()
        CognitionData.objects(bot=bot, collection="groceries").delete()

    def test_validate_data_sync_type_does_not_exist(self):
        bot = 'test_bot'
        collection_name = 'groceries'
        primary_key_col = "id"
        data = [{"id": 1, "item": "Juice", "price": 2.50, "quantity": 10}]
        sync_type = 'non_existent_sync_type'

        processor = CognitionDataProcessor()

        with pytest.raises(AppException, match=f"Sync type does not exist"):
            processor.validate_data(
                primary_key_col=primary_key_col,
                collection_name=collection_name,
                sync_type=sync_type,
                data=data,
                bot=bot
            )

    def test_validate_data_missing_collection(self):
        bot = 'test_bot'
        collection_name = 'nonexistent_collection'
        primary_key_col = "id"
        data = [{"id": 1, "item": "Juice", "price": 2.50, "quantity": 10}]
        sync_type = 'push_menu'

        processor = CognitionDataProcessor()

        with pytest.raises(AppException, match=f"Collection '{collection_name}' does not exist."):
            processor.validate_data(
                primary_key_col=primary_key_col,
                collection_name=collection_name,
                sync_type=sync_type,
                data=data,
                bot=bot
            )

    def test_validate_data_missing_primary_key(self):
        bot = 'test_bot'
        user = 'test_user'
        collection_name = 'groceries'
        primary_key_col = "id"
        sync_type = 'push_menu'

        metadata = [
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True},
            {"column_name": "price", "data_type": "float", "enable_search": True, "create_embeddings": True},
            {"column_name": "quantity", "data_type": "int", "enable_search": True, "create_embeddings": True}
        ]

        cognition_schema = CognitionSchema(
            metadata=[ColumnMetadata(**item) for item in metadata],
            collection_name=collection_name,
            user=user,
            bot=bot,
            timestamp=utc_now()
        )
        cognition_schema.validate(clean=True)
        cognition_schema.save()

        data = [
            {"item": "Juice", "price": 2.50, "quantity": 10}
        ]

        processor = CognitionDataProcessor()

        with pytest.raises(AppException, match=f"Primary key '{primary_key_col}' must exist in each row."):
            processor.validate_data(
                primary_key_col=primary_key_col,
                collection_name=collection_name,
                data=data,
                sync_type=sync_type,
                bot=bot
            )
        CognitionSchema.objects(bot=bot, collection_name="groceries").delete()

    def test_validate_data_column_length_mismatch(self):
        bot = 'test_bot'
        user = 'test_user'
        collection_name = 'groceries'
        primary_key_col = "id"
        sync_type = 'push_menu'

        metadata = [
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True},
            {"column_name": "price", "data_type": "float", "enable_search": True, "create_embeddings": True},
            {"column_name": "quantity", "data_type": "int", "enable_search": True, "create_embeddings": True}
        ]

        cognition_schema = CognitionSchema(
            metadata=[ColumnMetadata(**item) for item in metadata],
            collection_name=collection_name,
            user=user,
            bot=bot,
            timestamp=utc_now()
        )
        cognition_schema.validate(clean=True)
        cognition_schema.save()

        data = [
            {"id": 1, "item": "Milk", "quantity": 10}
        ]

        processor = CognitionDataProcessor()
        validation_summary = processor.validate_data(
            primary_key_col=primary_key_col,
            collection_name=collection_name,
            sync_type=sync_type,
            data=data,
            bot=bot
        )
        assert 1 in validation_summary
        assert validation_summary[1][0]["status"] == "Column length mismatch"
        assert validation_summary[1][0]["expected_columns"] == ["id", "item", "price", "quantity"]
        assert validation_summary[1][0]["actual_columns"] == ["id", "item", "quantity"]
        CognitionSchema.objects(bot=bot, collection_name=collection_name).delete()

    def test_validate_data_invalid_columns(self):
        bot = 'test_bot'
        user = 'test_user'
        collection_name = 'groceries'
        primary_key_col = "id"
        sync_type = 'push_menu'

        metadata = [
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True},
            {"column_name": "price", "data_type": "float", "enable_search": True, "create_embeddings": True},
            {"column_name": "quantity", "data_type": "int", "enable_search": True, "create_embeddings": True}
        ]

        cognition_schema = CognitionSchema(
            metadata=[ColumnMetadata(**item) for item in metadata],
            collection_name=collection_name,
            user=user,
            bot=bot,
            timestamp=utc_now()
        )
        cognition_schema.validate(clean=True)
        cognition_schema.save()

        data = [
            {"id": 1, "item": "Juice", "quantity": 10, "discount": 0.10}
        ]

        processor = CognitionDataProcessor()
        validation_summary = processor.validate_data(
            primary_key_col=primary_key_col,
            collection_name=collection_name,
            sync_type=sync_type,
            data=data,
            bot=bot
        )
        assert 1 in validation_summary
        assert validation_summary[1][0]["status"] == "Invalid columns in input data"
        assert validation_summary[1][0]["expected_columns"] == ["id", "item", "price", "quantity"]
        assert validation_summary[1][0]["actual_columns"] == ["id", "item", "quantity", "discount"]
        CognitionSchema.objects(bot=bot, collection_name=collection_name).delete()

    def test_validate_data_document_non_existence(self):
        bot = 'test_bot'
        user = 'test_user'
        collection_name = 'groceries'
        primary_key_col = "id"
        sync_type = 'item_toggle'

        metadata = [
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True},
            {"column_name": "price", "data_type": "float", "enable_search": True, "create_embeddings": True},
            {"column_name": "quantity", "data_type": "int", "enable_search": True, "create_embeddings": True}
        ]

        cognition_schema = CognitionSchema(
            metadata=[ColumnMetadata(**item) for item in metadata],
            collection_name=collection_name,
            user=user,
            bot=bot,
            timestamp=utc_now()
        )
        cognition_schema.validate(clean=True)
        cognition_schema.save()

        dummy_data = {
            "id": 1,
            "item": "Juice",
            "price": 2.80,
            "quantity": 5
        }
        existing_document = CognitionData(
            data=dummy_data,
            content_type="json",
            collection=collection_name,
            user=user,
            bot=bot,
            timestamp=utc_now()
        )
        existing_document.save()

        data = [
            {"id": 2, "price": 27.0}
        ]

        processor = CognitionDataProcessor()
        validation_summary = processor.validate_data(
            primary_key_col=primary_key_col,
            collection_name=collection_name,
            sync_type=sync_type,
            data=data,
            bot=bot
        )
        assert 2 in validation_summary
        assert validation_summary[2][0]["status"] == "Document does not exist"
        assert validation_summary[2][0]["primary_key"] == 2

        CognitionSchema.objects(bot=bot, collection_name="groceries").delete()
        CognitionData.objects(bot=bot, collection="groceries").delete()

    @pytest.mark.asyncio
    @patch.object(LLMProcessor, "__collection_exists__", autospec=True)
    @patch.object(LLMProcessor, "__create_collection__", autospec=True)
    @patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
    @mock.patch(
        "kairon.shared.actions.utils.ActionUtility.execute_request_async",
        new_callable=AsyncMock
    )
    async def test_upsert_data_push_menu_success(self, mock_embedding, mock_collection_upsert, mock_create_collection,
                                                 mock_collection_exists):
        bot = 'test_bot'
        user = 'test_user'
        collection_name = 'groceries'
        primary_key_col = 'id'
        sync_type = 'push_menu'

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )

        llm_secret.save()

        metadata = [
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True},
            {"column_name": "price", "data_type": "float", "enable_search": True, "create_embeddings": True},
            {"column_name": "quantity", "data_type": "int", "enable_search": True, "create_embeddings": True},
        ]

        cognition_schema = CognitionSchema(
            metadata=[ColumnMetadata(**item) for item in metadata],
            collection_name=collection_name,
            user=user,
            bot=bot,
            timestamp=utc_now()
        )
        cognition_schema.validate(clean=True)
        cognition_schema.save()

        dummy_data = {
            "id": 2,
            "item": "Milk",
            "price": 2.80,
            "quantity": 5
        }
        existing_document = CognitionData(
            data=dummy_data,
            content_type="json",
            collection=collection_name,
            user=user,
            bot=bot,
            timestamp=utc_now()
        )
        existing_document.save()

        upsert_data = [
            {"id": 1, "item": "Juice", "price": 2.50, "quantity": 10},  # New entry
            {"id": 2, "item": "Milk", "price": 3.00, "quantity": 5}  # Existing entry to be updated
        ]

        mock_collection_exists.return_value = False
        mock_create_collection.return_value = None
        mock_collection_upsert.return_value = None

        embedding = list(np.random.random(1532))
        embedding = [[0.1] * 1532,[0.1] * 1532]
        mock_embedding.return_value = (
            embedding,
            200,
            0.05,
            {}
        )
        processor = CognitionDataProcessor()

        result = await processor.upsert_data(
            primary_key_col=primary_key_col,
            collection_name=collection_name,
            sync_type=sync_type,
            data=upsert_data,
            bot=bot,
            user=user
        )

        upserted_data = list(CognitionData.objects(bot=bot, collection=collection_name))

        assert result["message"] == "Upsert complete!"
        assert len(upserted_data) == 2

        inserted_record = next((item for item in upserted_data if item.data["id"] == 1), None)
        assert inserted_record is not None
        assert inserted_record.data["item"] == "Juice"
        assert inserted_record.data["price"] == 2.50
        assert inserted_record.data["quantity"] == 10

        updated_record = next((item for item in upserted_data if item.data["id"] == 2), None)
        assert updated_record is not None
        assert updated_record.data["item"] == "Milk"
        assert updated_record.data["price"] == 3.00  # Updated price
        assert updated_record.data["quantity"] == 5

        call_kwargs = mock_embedding.call_args.kwargs

        assert call_kwargs["request_method"] == "POST"
        assert call_kwargs["http_url"].endswith("/test_bot/aembedding/openai")

        body = call_kwargs["request_body"]

        assert body["user"] == "test_user"
        assert body["kwargs"]["api_key"] == "value"
        assert body["kwargs"]["invocation"] == "knowledge_vault_sync"

        assert body["kwargs"]["truncated_texts"] == [
            '{"id":1,"item":"Juice","price":2.5,"quantity":10}',
            '{"id":2,"item":"Milk","price":3.0,"quantity":5}'
        ]

        CognitionSchema.objects(bot=bot, collection_name="groceries").delete()
        CognitionData.objects(bot=bot, collection="groceries").delete()
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    @patch.object(LLMProcessor, "__collection_exists__", autospec=True)
    @patch.object(LLMProcessor, "__create_collection__", autospec=True)
    @patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
    @mock.patch(
        "kairon.shared.actions.utils.ActionUtility.execute_request_async",
        new_callable=AsyncMock
    )
    async def test_upsert_data_item_toggle_success(self, mock_embedding, mock_collection_upsert,
                                                    mock_create_collection,
                                                    mock_collection_exists):
        bot = 'test_bot'
        user = 'test_user'
        collection_name = 'groceries'
        primary_key_col = 'id'
        sync_type = 'item_toggle'

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            bot=bot,
            user=user
        )
        llm_secret.save()

        metadata = [
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True},
            {"column_name": "price", "data_type": "float", "enable_search": True, "create_embeddings": True},
            {"column_name": "quantity", "data_type": "int", "enable_search": True, "create_embeddings": True},
        ]

        cognition_schema = CognitionSchema(
            metadata=[ColumnMetadata(**item) for item in metadata],
            collection_name=collection_name,
            user=user,
            bot=bot,
            timestamp=utc_now()
        )
        cognition_schema.validate(clean=True)
        cognition_schema.save()

        dummy_data_one = {
            "id": 1,
            "item": "Juice",
            "price": 2.80,
            "quantity": 56
        }
        existing_document = CognitionData(
            data=dummy_data_one,
            content_type="json",
            collection=collection_name,
            user=user,
            bot=bot,
            timestamp=utc_now()
        )
        existing_document.save()

        dummy_data_two = {
            "id": 2,
            "item": "Milk",
            "price": 2.80,
            "quantity": 12
        }
        existing_document = CognitionData(
            data=dummy_data_two,
            content_type="json",
            collection=collection_name,
            user=user,
            bot=bot,
            timestamp=utc_now()
        )
        existing_document.save()

        upsert_data = [
            {"id": 1, "price": 80.50},
            {"id": 2, "price": 27.00}
        ]

        mock_collection_exists.return_value = False
        mock_create_collection.return_value = None
        mock_collection_upsert.return_value = None

        embedding = [[0.1] * 1532,[0.1] * 1532]
        mock_embedding.return_value = (
            embedding,
            200,
            0.05,
            {}
        )
        processor = CognitionDataProcessor()

        result = await processor.upsert_data(
            primary_key_col=primary_key_col,
            collection_name=collection_name,
            sync_type=sync_type,
            data=upsert_data,
            bot=bot,
            user=user
        )

        upserted_data = list(CognitionData.objects(bot=bot, collection=collection_name))

        assert result["message"] == "Upsert complete!"
        assert len(upserted_data) == 2

        inserted_record = next((item for item in upserted_data if item.data["id"] == 1), None)
        assert inserted_record is not None
        assert inserted_record.data["item"] == "Juice"
        assert inserted_record.data["price"] == 80.50
        assert inserted_record.data["quantity"] == 56

        updated_record = next((item for item in upserted_data if item.data["id"] == 2), None)
        assert updated_record is not None
        assert updated_record.data["item"] == "Milk"
        assert updated_record.data["price"] == 27.00  # Updated price
        assert updated_record.data["quantity"] == 12


        call_kwargs = mock_embedding.call_args.kwargs

        assert call_kwargs["request_method"] == "POST"
        assert call_kwargs["http_url"].endswith("/test_bot/aembedding/openai")

        body = call_kwargs["request_body"]

        assert body["user"] == "test_user"
        assert body["kwargs"]["api_key"] == "value"
        assert body["kwargs"]["invocation"] == "knowledge_vault_sync"

        assert body["kwargs"]["truncated_texts"] == [
            '{"id":1,"item":"Juice","price":80.5,"quantity":56}',
            '{"id":2,"item":"Milk","price":27.0,"quantity":12}'
        ]

        CognitionSchema.objects(bot=bot, collection_name="groceries").delete()
        CognitionData.objects(bot=bot, collection="groceries").delete()
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    @patch.object(LLMProcessor, "__collection_exists__", autospec=True)
    @patch.object(LLMProcessor, "__create_collection__", autospec=True)
    @patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
    @patch.object(LLMProcessor, "__delete_collection_points__", autospec=True)
    @mock.patch(
        "kairon.shared.actions.utils.ActionUtility.execute_request_async",
        new_callable=AsyncMock
    )
    async def test_upsert_data_empty_data_list(self, mock_embedding, mock_delete_collection_points,
                                               mock_collection_upsert, mock_create_collection,
                                               mock_collection_exists):
        bot = 'test_bot'
        user = 'test_user'
        collection_name = 'groceries'
        primary_key_col = 'id'
        sync_type = 'push_menu'

        metadata = [
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True},
            {"column_name": "price", "data_type": "float", "enable_search": True, "create_embeddings": True},
            {"column_name": "quantity", "data_type": "int", "enable_search": True, "create_embeddings": True},
        ]

        cognition_schema = CognitionSchema(
            metadata=[ColumnMetadata(**item) for item in metadata],
            collection_name=collection_name,
            user=user,
            bot=bot,
            timestamp=utc_now()
        )
        cognition_schema.validate(clean=True)
        cognition_schema.save()

        dummy_data = {
            "id": 2,
            "item": "Milk",
            "price": 2.80,
            "quantity": 5
        }
        existing_document = CognitionData(
            data=dummy_data,
            content_type="json",
            collection=collection_name,
            user=user,
            bot=bot,
            timestamp=utc_now()
        )
        existing_document.save()

        upsert_data = []

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key="openai_key",
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        mock_collection_exists.return_value = False
        mock_create_collection.return_value = None
        mock_collection_upsert.return_value = None
        mock_delete_collection_points.return_value = None

        embedding = [[0.1] * 1532,[0.1] * 1532]
        mock_embedding.return_value = (
            embedding,
            200,
            0.05,
            {}
        )
        processor = CognitionDataProcessor()
        result = await processor.upsert_data(
            primary_key_col=primary_key_col,
            collection_name=collection_name,
            sync_type=sync_type,
            data=upsert_data,
            bot=bot,
            user=user
        )

        data = list(CognitionData.objects(bot=bot, collection=collection_name))

        assert result["message"] == "Upsert complete!"
        assert len(data) == 0


        CognitionSchema.objects(bot=bot, collection_name=collection_name).delete()
        CognitionData.objects(bot=bot, collection=collection_name).delete()
        LLMSecret.objects.delete()


    def test_get_llm_metadata_coverage(self):
        bot = "test_bot"
        llm_type = "openai"

        LLMSecret.objects(bot=bot, llm_type=llm_type).delete()
        LLMSecret.objects(bot__exists=False, llm_type=llm_type).delete()

        secret1 = LLMSecret(bot=bot, llm_type=llm_type, api_key="value", models=["model1", "model2"], user="user")
        secret1.save()

        models = LLMProcessor.get_llm_metadata(bot, llm_type)
        assert models == ["model1", "model2"]

        secret1.delete()

        secret2 = LLMSecret(bot=None, llm_type=llm_type, api_key="value", models=["fallback_model"], user="user")
        secret2.save()

        models = LLMProcessor.get_llm_metadata(bot, llm_type)
        assert models == ["fallback_model"]

        secret2.delete()

        models = LLMProcessor.get_llm_metadata(bot, llm_type)
        assert models == []
    def test_get_pydantic_type_int(self):
        result = CognitionDataProcessor().get_pydantic_type('int')
        expected = (int, ...)
        assert result == expected

    def test_get_pydantic_type_float(self):
        result = CognitionDataProcessor.get_pydantic_type('float')
        expected = (float, ...)
        assert result == expected

    def test_get_pydantic_type_invalid(self):
        with pytest.raises(ValueError, match="Unsupported data type: unknown"):
            CognitionDataProcessor.get_pydantic_type('unknown')

    def test_validate_sync_type_valid(self):
        processor = CognitionDataProcessor()
        valid_sync_type = list(VaultSyncType.__members__.keys())[0]
        processor._validate_sync_type(valid_sync_type)

    def test_validate_sync_type_invalid(self):
        processor = CognitionDataProcessor()
        invalid_sync_type = "invalid_event"
        with pytest.raises(AppException, match="Sync type does not exist"):
            processor._validate_sync_type(invalid_sync_type)

    def test_validate_collection_exists_valid(self):
        bot = 'test_bot'
        user = 'test_user'
        collection_name = 'groceries'
        metadata = [
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True}
        ]

        cognition_schema = CognitionSchema(
            metadata=[ColumnMetadata(**item) for item in metadata],
            collection_name=collection_name,
            user=user,
            bot=bot,
            timestamp=utc_now()
        )
        cognition_schema.validate(clean=True)
        cognition_schema.save()

        processor = CognitionDataProcessor()
        processor._validate_collection_exists(collection_name)

        CognitionSchema.objects(collection_name=collection_name).delete()

    def test_validate_collection_exists_invalid(self):
        processor = CognitionDataProcessor()
        invalid_collection_name = "non_existent_collection"
        with pytest.raises(AppException, match=f"Collection '{invalid_collection_name}' does not exist."):
            processor._validate_collection_exists(invalid_collection_name)

    def test_save_and_validate_success(self):
        bot = 'test_bot'
        user = 'test_user'
        table_name = 'test_table'

        metadata = [
            {
                "column_name": "order_id",
                "data_type": "int",
                "enable_search": True,
                "create_embeddings": True
            },
            {
                "column_name": "order_priority",
                "data_type": "str",
                "enable_search": True,
                "create_embeddings": True
            },
            {
                "column_name": "sales",
                "data_type": "float",
                "enable_search": True,
                "create_embeddings": True
            },
            {
                "column_name": "profit",
                "data_type": "float",
                "enable_search": True,
                "create_embeddings": True
            }
        ]

        cognition_schema = CognitionSchema(
            metadata=[ColumnMetadata(**item) for item in metadata],
            collection_name=table_name,
            user=user,
            bot=bot,
            timestamp=utc_now()
        )
        cognition_schema.validate(clean=True)  # Validate before saving
        cognition_schema.save()

        file_content = b"order_id,order_priority,sales,profit\n1,High,100.0,50.0\n"
        doc_content = UploadFile(filename="Salesstore.csv", file=BytesIO(file_content))

        processor = MongoProcessor()

        error_message = processor.save_and_validate(bot, user, doc_content, table_name)
        content_dir = os.path.join('doc_content_upload_records', bot)
        file_path = os.path.join(content_dir, doc_content.filename)

        assert os.path.exists(file_path)

        assert error_message == {}
        shutil.rmtree(os.path.dirname(file_path))

    def test_save_and_validate_header_mismatch_missing_columns(self):
        bot = 'test_bot'
        user = 'test_user'
        table_name = 'test_table'

        file_content = b"order_id,order_priority,sales\n1,High,100.0\n"
        doc_content = UploadFile(filename="Salesstore_header_mismatch.csv", file=BytesIO(file_content))

        processor = MongoProcessor()

        error_message = processor.save_and_validate(bot, user, doc_content, table_name)
        content_dir = os.path.join('doc_content_upload_records', bot)
        file_path = os.path.join(content_dir, doc_content.filename)

        assert os.path.exists(file_path)

        assert 'Header mismatch' in error_message
        assert "Expected headers ['order_id', 'order_priority', 'sales', 'profit'] but found ['order_id', 'order_priority', 'sales']" in \
               error_message['Header mismatch']
        assert 'Missing columns' in error_message
        assert "{'profit'}" in error_message['Missing columns']

        shutil.rmtree(os.path.dirname(file_path))

    def test_save_and_validate_header_mismatch_extra_columns(self):
        bot = 'test_bot'
        user = 'test_user'
        table_name = 'test_table'

        file_content = b"order_id,order_priority,sales,profit,order_quantity\n1,High,100.0,50.0,87\n"
        doc_content = UploadFile(filename="Salesstore_extra_columns.csv", file=BytesIO(file_content))

        processor = MongoProcessor()

        error_message = processor.save_and_validate(bot, user, doc_content, table_name)
        content_dir = os.path.join('doc_content_upload_records', bot)
        file_path = os.path.join(content_dir, doc_content.filename)

        assert os.path.exists(file_path)

        assert 'Header mismatch' in error_message
        assert "Expected headers ['order_id', 'order_priority', 'sales', 'profit'] but found ['order_id', 'order_priority', 'sales', 'profit', 'order_quantity']" in \
               error_message['Header mismatch']
        assert 'Extra columns' in error_message
        assert "{'order_quantity'}" in error_message['Extra columns']

        shutil.rmtree(os.path.dirname(file_path))

    def test_validate_schema_and_log_success(self):
        bot = 'test_bot'
        user = 'test_user'
        table_name = 'test_table'

        file_content = b"order_id,order_priority,sales,profit\n1,High,100.0,50.0\n"
        doc_content = UploadFile(filename="Salesstore.csv", file=BytesIO(file_content))

        processor = MongoProcessor()

        result = processor.validate_schema_and_log(bot, user, doc_content, table_name)

        assert result is True

        log = ContentValidationLogs.objects(bot=bot).first()
        assert log is not None
        assert log.is_data_uploaded is True
        assert log.file_received == doc_content.filename
        assert log.validation_errors == {}
        assert log.status is None
        assert log.event_status == EVENT_STATUS.INITIATED.value
        ContentValidationLogs.objects.delete()

    def test_validate_schema_and_log_failure(self):
        bot = 'test_bot'
        user = 'test_user'
        table_name = 'test_table'

        file_content = b"order_id,order_priority,sales\n1,High,100.0\n"
        doc_content = UploadFile(filename="Salesstore_header_mismatch.csv", file=BytesIO(file_content))

        processor = MongoProcessor()

        result = processor.validate_schema_and_log(bot, user, doc_content, table_name)

        assert result is False, "Schema validation should fail due to header mismatch."

        log = ContentValidationLogs.objects(bot=bot).first()
        print(log.to_mongo())
        assert log is not None
        assert log.is_data_uploaded is True
        assert log.file_received == doc_content.filename
        assert log.validation_errors is not None
        assert log.end_timestamp is not None
        assert log.status == STATUSES.FAIL.value
        assert log.event_status == EVENT_STATUS.COMPLETED.value

    def test_validate_doc_content_success(self):
        """
        Test case for valid content where all rows pass validation.
        """

        column_dict = {
            'order_id': 'int',
            'order_priority': 'str',
            'sales': 'float'
        }

        doc_content = [
            {'order_id': '1', 'order_priority': 'High', 'sales': '100.0'},
            {'order_id': '2', 'order_priority': 'Low', 'sales': '200.5'},
            {'order_id': '3', 'order_priority': 'Medium', 'sales': '150.75'}
        ]
        processor = MongoProcessor()
        summary = processor.validate_doc_content(column_dict, doc_content)

        assert summary == {}

    def test_validate_doc_content_invalid_datatype(self):
        """
        Test case for content where a row has invalid data type.
        """

        column_dict = {
            'order_id': 'int',
            'order_priority': 'str',
            'sales': 'float'
        }

        doc_content = [
            {'order_id': '1', 'order_priority': 'High', 'sales': '100.0'},
            {'order_id': '2', 'order_priority': 'Low', 'sales': 'invalid_sales'},
            {'order_id': '3', 'order_priority': 'Medium', 'sales': '150.75'}
        ]

        processor = MongoProcessor()
        summary = processor.validate_doc_content(column_dict, doc_content)

        assert len(summary) == 1
        assert "Row 3" in summary
        assert summary["Row 3"][0]['column_name'] == 'sales'
        assert summary["Row 3"][0]['status'] == 'Invalid DataType'

    def test_validate_doc_content_missing_required_field(self):
        """
        Test case for content where a row is missing a required field.
        """

        column_dict = {
            'order_id': 'int',
            'order_priority': 'str',
            'sales': 'float'
        }

        doc_content = [
            {'order_id': '1', 'order_priority': 'High', 'sales': '100.0'},
            {'order_id': '2', 'order_priority': 'Low', 'sales': ''},
            {'order_id': '3', 'order_priority': 'Medium', 'sales': '150.75'}
        ]

        processor = MongoProcessor()
        summary = processor.validate_doc_content(column_dict, doc_content)

        assert len(summary) == 1
        assert "Row 3" in summary
        assert summary["Row 3"][0]['column_name'] == 'sales'
        assert summary["Row 3"][0]['status'] == 'Required Field is Empty'

    def test_validate_doc_content_multiple_errors(self):
        """
        Test case for content where multiple rows have errors.
        """

        column_dict = {
            'order_id': 'int',
            'order_priority': 'str',
            'sales': 'float'
        }

        doc_content = [
            {'order_id': 'invalid_id', 'order_priority': 'High', 'sales': '100.0'},
            {'order_id': '', 'order_priority': 'Low', 'sales': 'invalid_sales'},
            {'order_id': '3', 'order_priority': 'Medium', 'sales': '150.75'}
        ]

        processor = MongoProcessor()
        summary = processor.validate_doc_content(column_dict, doc_content)

        assert len(summary) == 2

        assert "Row 2" in summary
        assert summary["Row 2"][0]['column_name'] == 'order_id'
        assert summary["Row 2"][0]['status'] == 'Invalid DataType'

        assert "Row 3" in summary
        assert len(summary["Row 3"]) == 2
        assert summary["Row 3"][0]['column_name'] == 'order_id'
        assert summary["Row 3"][0]['status'] == 'Required Field is Empty'
        assert summary["Row 3"][1]['column_name'] == 'sales'
        assert summary["Row 3"][1]['status'] == 'Invalid DataType'

    def test_get_error_report_file_path_success(self):
        bot = "test_bot"
        event_id = "12345"

        base_dir = os.path.join('content_upload_summary', bot)
        os.makedirs(base_dir, exist_ok=True)
        expected_path = os.path.join(base_dir, f'failed_rows_with_errors_{event_id}.csv')

        with open(expected_path, 'w') as f:
            f.write("dummy content")

        processor = MongoProcessor()
        result = processor.get_error_report_file_path(bot, event_id)
        assert result == expected_path

    def test_get_error_report_file_path_file_not_found(self):
        """ Test case where the file does not exist """
        bot = "test_bot"
        event_id = "67890"

        processor = MongoProcessor()
        try:
            processor.get_error_report_file_path(bot, event_id)
        except HTTPException as e:
            assert e.status_code == 404
            assert e.detail == "Error Report not found"

    def test_get_error_report_file_path_invalid_event_id(self):
        """ Test case for invalid event ID """
        bot = "test_bot"
        event_id = "invalid!@"

        processor = MongoProcessor()
        try:
            processor.get_error_report_file_path(bot, event_id)
        except HTTPException as e:
            assert e.status_code == 400, f"Expected status code 400, but got {e.status_code}"
            assert e.detail == "Invalid event ID"

    @pytest.fixture()
    def save_actions(self):
        from unittest import mock
        import textwrap
        from kairon.shared.actions.data_objects import SetSlots, CustomActionParameters

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            user='test-user',
        )
        llm_secret.save()

        llm_secret = LLMSecret(
            llm_type="anthropic",
            api_key='value',
            models=[ "claude-3-7-sonnet-20250219"],
            user='test-user'
        )
        llm_secret.save()

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
            bot="testing_bot",
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
            bot="testing_bot",
            user="user"
        ).save()

        SlotSetAction(
            name="slot_set_action_1",
            set_slots=[SetSlots(name="location", type="reset_slot", value="location"),
                       SetSlots(name="name", type="from_value", value="end_user"),
                       SetSlots(name="age", type="reset_slot")],
            bot="testing_bot",
            user="user"
        ).save()
        SlotSetAction(
            name="slot_set_action_2",
            set_slots=[SetSlots(name="name", type="reset_slot", value="")],
            bot="testing_bot",
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
                bot="testing_bot",
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
                bot="testing_bot",
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
                bot="testing_bot",
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
                bot="testing_bot",
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
                bot="testing_bot",
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
                bot="testing_bot",
                user="user"
            ).save()

        GoogleSearchAction(
            name="google_action_1",
            api_key=CustomActionRequestParameters(value='1234567890'),
            search_engine_id='asdfg::123456',
            bot="testing_bot",
            user="user",
            dispatch_response=False,
            num_results=3,
            set_slot="name"
        ).save()
        GoogleSearchAction(
            name="google_action_2",
            api_key=CustomActionRequestParameters(key='name', parameter_type="slot", value='name'),
            search_engine_id='asdfg::123456',
            bot="testing_bot",
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
                bot="testing_bot",
                user="user"
            ).save()
            ZendeskAction(
                name="zendesk_action_2",
                subdomain='digite751',
                user_name='udit.pandey@digite.com',
                api_token=CustomActionRequestParameters(key="name", parameter_type="slot", value='name'),
                subject='new ticket',
                response='ticket created',
                bot="testing_bot",
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
                bot="testing_bot",
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
                bot="testing_bot",
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
                bot="testing_bot",
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
                bot="testing_bot",
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
            bot="testing_bot",
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
            bot="testing_bot",
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
            bot="testing_bot",
            user="user"
        ).save()
        WebSearchAction(
            name="web_search_action_1",
            website="https://www.w3schools.com/",
            topn=1,
            set_slot='location',
            bot="testing_bot",
            user="user"
        ).save()
        WebSearchAction(
            name="web_search_action_2",
            website="https://www.w3schools.com/",
            topn=1,
            set_slot='name',
            bot="testing_bot",
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
            bot="testing_bot",
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
            bot="testing_bot",
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
            bot="testing_bot",
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
            bot="testing_bot",
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
            bot="testing_bot",
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
            bot="testing_bot",
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
            bot="testing_bot",
            user="user"
        ).save()
        CallbackActionConfig(
            name="callback_action2",
            callback_name="callback_script2",
            dynamic_url_slot_name="name",
            metadata_list=[],
            bot_response="Hello",
            dispatch_bot_response=True,
            bot="testing_bot",
            user="user"
        ).save()
        ScheduleAction(
            name="schedule_action_1",
            bot="testing_bot",
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
            bot="testing_bot",
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
            bot="testing_bot",
            user="user",
        ).save()
        KaironTwoStageFallbackAction(
            name="two_stage_fallback_action",
            text_recommendations={
                "count": 3,
                "use_intent_ranking": True
            },
            bot="testing_bot",
            user="user",
        ).save()
        semantic_expression = "if ((location in ['Mumbai', 'Bangalore'] && location.startsWith('M') " \
                              "&& location.endsWith('i')) || location.length() > 20) " \
                              "{return true;} else {return false;}"
        FormValidationAction(
            name="form_validation_action",
            slot="location",
            validation_semantic=semantic_expression,
            bot="testing_bot",
            user="user"
        ).save()

        LLMSecret.objects.delete()

    def test_get_slot_actions(self, save_actions):
        processor = MongoProcessor()
        bot = 'testing_bot'
        user = 'test_user'
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key='value',
            models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
            user=user,
            bot=bot
        )

        llm_secret.save()
        actions = processor.get_slot_mapped_actions('testing_bot', 'name')
        assert actions == {
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

        actions = processor.get_slot_mapped_actions('testing_bot', 'bot')
        assert actions == {
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

        actions = processor.get_slot_mapped_actions('testing_bot', 'location')
        assert actions == {
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
        LLMSecret.objects.delete()

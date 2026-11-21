from tests.unit_test.data_processor.data_processor_support import *  # noqa: F403
from tests.unit_test.data_processor.data_processor_support import (
    MongoProcessorTestBase,
    fast_rasa_training,
)

class TestMongoProcessor(MongoProcessorTestBase):
    def test_preprocess_push_menu_data_success(self):
        bot = "test_bot"
        user = "test_user"
        provider = "petpooja"

        push_menu_payload_path = Path("tests/testing_data/catalog_sync/catalog_sync_push_menu_payload.json")
        with push_menu_payload_path.open("r", encoding="utf-8") as f:
            push_menu_payload = json.load(f)

        CatalogProviderMapping(
            provider=provider,
            meta_mappings={
                "name": {"source": "itemname", "default": "No title"},
                "description": {"source": "itemdescription", "default": "No description available"},
                "price": {"source": "price", "default": 0.0},
                "availability": {"source": "in_stock", "default": "out of stock"},
                "image_url": {"source": "item_image_url", "default": "https://www.kairon.com/default-image.jpg"},
                "url": {"source": None, "default": "https://www.kairon.com/"},
                "brand": {"source": None, "default": "Sattva"},
                "condition": {"source": None, "default": "new"}
            },
            kv_mappings={
                "title": {"source": "itemname", "default": "No title"},
                "description": {"source": "itemdescription", "default": "No description available"},
                "price": {"source": "price", "default": 0.0},
                "facebook_product_category": {"source": "item_categoryid", "default": "Food and drink > General"},
                "availability": {"source": "in_stock", "default": "out of stock"}
            }
        ).save()

        POSIntegrations(
            bot=bot,
            user=user,
            provider = provider,
            config = {
                "restaurant_name": "restaurant1",
                "branch_name": "branch1",
                "restaurant_id": "98765"
            },
            meta_config= {
                "access_token": "dummy_access_token",
                "catalog_id": "12345"
            },
            sync_type = "push_menu",
            smart_catalog_enabled= False,
            meta_enabled = False,
            sync_options = PetpoojaSyncConfig(
                process_push_menu=True,
                process_item_toggle=False
            )
        ).save()

        restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(bot)
        catalog_images_collection = f"{restaurant_name}_{branch_name}_catalog_images"
        fallback_data = {
            "image_type": "global",
            "image_url": "https://picsum.photos/id/237/200/300",
            "image_base64": ""
        }
        CollectionData(
            collection_name=catalog_images_collection,
            data=fallback_data,
            user=user,
            bot=bot,
            status=True,
            timestamp=utc_now()
        ).save()

        result = CognitionDataProcessor.preprocess_push_menu_data(bot, push_menu_payload, provider)

        expected_result = {
            "meta": [
                {
                    "id": "10539634",
                    "name": "Potter 4",
                    "description": "Chicken fillet in a bun  with coleslaw,lettuce, pickles and our  spicy cocktail sauce. This sandwich is made with care to make sure that each and every bite is packed with Mmmm",
                    "price": 8700,
                    "availability": "in stock",
                    "image_url": "https://picsum.photos/id/237/200/300",
                    "url": "https://www.kairon.com/",
                    "brand": "Sattva",
                    "condition": "new"
                },
                {
                    "id": "10539699",
                    "name": "Potter 99",
                    "description": "Chicken fillet in a bun  with coleslaw,lettuce, pickles and our  spicy cocktail sauce. This sandwich is made with care to make sure that each and every bite is packed with Mmmm",
                    "price": 3426,
                    "availability": "in stock",
                    "image_url": "https://picsum.photos/id/237/200/300",
                    "url": "https://www.kairon.com/",
                    "brand": "Sattva",
                    "condition": "new"
                },
                {
                    "id": "10539580",
                    "name": "Potter 5",
                    "description": "chicken fillet  nuggets come with a sauce of your choice (nugget/garlic sauce). Bite-sized pieces of tender all breast chicken fillets, marinated in our unique & signature blend, breaded and seasoned to perfection, then deep-fried until deliciously tender, crispy with a golden crust",
                    "price": 3159,
                    "availability": "in stock",
                    "image_url": "https://picsum.photos/id/237/200/300",
                    "url": "https://www.kairon.com/",
                    "brand": "Sattva",
                    "condition": "new"
                }
            ],
            "kv": [
                {
                    "id": "10539634",
                    "title": "Potter 4",
                    "description": "Chicken fillet in a bun  with coleslaw,lettuce, pickles and our  spicy cocktail sauce. This sandwich is made with care to make sure that each and every bite is packed with Mmmm",
                    "price": 8700,
                    "facebook_product_category": "Food and drink > Chicken Meal",
                    "availability": "in stock"
                },
                {
                    "id": "10539699",
                    "title": "Potter 99",
                    "description": "Chicken fillet in a bun  with coleslaw,lettuce, pickles and our  spicy cocktail sauce. This sandwich is made with care to make sure that each and every bite is packed with Mmmm",
                    "price": 3426,
                    "facebook_product_category": "Food and drink > Chicken Meal",
                    "availability": "in stock"
                },
                {
                    "id": "10539580",
                    "title": "Potter 5",
                    "description": "chicken fillet  nuggets come with a sauce of your choice (nugget/garlic sauce). Bite-sized pieces of tender all breast chicken fillets, marinated in our unique & signature blend, breaded and seasoned to perfection, then deep-fried until deliciously tender, crispy with a golden crust",
                    "price": 3159,
                    "facebook_product_category": "Food and drink > Chicken Meal",
                    "availability": "in stock"
                }
            ]
        }

        assert result == expected_result
        CatalogProviderMapping.objects.delete()
        POSIntegrations.objects(bot=bot, provider="petpooja").delete()
        CollectionData.objects(collection_name=catalog_images_collection).delete()

    def test_preprocess_push_menu_data_no_provider_mapping(self):
        bot = "test_bot"
        provider = "nonexistent_provider"
        push_menu_payload_path = Path("tests/testing_data/catalog_sync/catalog_sync_push_menu_payload.json")
        with push_menu_payload_path.open("r", encoding="utf-8") as f:
            push_menu_payload = json.load(f)

        with pytest.raises(Exception, match="Metadata mappings not found for provider=nonexistent_provider"):
            CognitionDataProcessor.preprocess_push_menu_data(bot, push_menu_payload, provider)

    def test_preprocess_item_toggle_data_success(self):
        bot = "test_bot"
        provider = "petpooja"

        CatalogProviderMapping(
            provider=provider,
            meta_mappings={
                "name": {"source": "itemname", "default": "No title"},
                "description": {"source": "itemdescription", "default": "No description available"},
                "price": {"source": "price", "default": 0.0},
                "availability": {"source": "in_stock", "default": "out of stock"},
                "image_url": {"source": "item_image_url", "default": "https://www.kairon.com/default-image.jpg"},
                "url": {"source": None, "default": "https://www.kairon.com/"},
                "brand": {"source": None, "default": "Sattva"},
                "condition": {"source": None, "default": "new"}
            },
            kv_mappings={
                "title": {"source": "itemname", "default": "No title"},
                "description": {"source": "itemdescription", "default": "No description available"},
                "price": {"source": "price", "default": 0.0},
                "facebook_product_category": {"source": "item_categoryid", "default": "Food and drink > General"},
                "availability": {"source": "in_stock", "default": "out of stock"}
            }
        ).save()

        json_data_path = Path("tests/testing_data/catalog_sync/catalog_sync_item_toggle_payload.json")
        with json_data_path.open("r", encoding="utf-8") as f:
            json_data = json.load(f)

        result = CognitionDataProcessor.preprocess_item_toggle_data(bot, json_data, provider)

        expected_result = {
            "meta": [
                {"id": "10539580", "availability": "out of stock"}
            ],
            "kv": [
                {"id": "10539580", "availability": "out of stock"}
            ]
        }

        assert result == expected_result
        CatalogProviderMapping.objects.delete()

    def test_preprocess_item_toggle_data_no_provider_mapping(self):
        bot = "test_bot"
        provider = "nonexistent_provider"
        json_data_path = Path("tests/testing_data/catalog_sync/catalog_sync_item_toggle_payload.json")
        with json_data_path.open("r", encoding="utf-8") as f:
            json_data = json.load(f)

        with pytest.raises(Exception, match="Metadata mappings not found for provider=nonexistent_provider"):
            CognitionDataProcessor.preprocess_item_toggle_data(bot, json_data, provider)

    def test_resolve_image_link_global(self):
        bot = "test_bot"
        user = "test_user"
        item_id = "12345"
        provider = "petpooja"

        POSIntegrations(
            bot=bot,
            user=user,
            provider=provider,
            config={
                "restaurant_name": "restaurant1",
                "branch_name": "branch1",
                "restaurant_id": "98765"
            },
            meta_config={
                "access_token": "dummy_access_token",
                "catalog_id": "12345"
            },
            sync_type="push_menu",
            smart_catalog_enabled=False,
            meta_enabled=False,
            sync_options=PetpoojaSyncConfig(
                process_push_menu=True,
                process_item_toggle=False
            )
        ).save()

        restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(bot)
        catalog_images_collection = f"{restaurant_name}_{branch_name}_catalog_images"
        fallback_data = {
            "image_type": "global",
            "image_url": "http://global_image_url.com",
            "image_base64": ""
        }
        CollectionData(
            collection_name=catalog_images_collection,
            data=fallback_data,
            user=user,
            bot=bot,
            status=True,
            timestamp=utc_now()
        ).save()

        result = CognitionDataProcessor.resolve_image_link(bot, item_id)

        expected_result = "http://global_image_url.com"
        assert result == expected_result

        POSIntegrations.objects(bot=bot, provider="petpooja").delete()
        CollectionData.objects(collection_name=catalog_images_collection).delete()

    def test_resolve_image_link_local(self):
        bot = "test_bot"
        user = "test_user"
        item_id = "12345"
        provider = "petpooja"

        POSIntegrations(
            bot=bot,
            user=user,
            provider=provider,
            config={
                "restaurant_name": "restaurant1",
                "branch_name": "branch1",
                "restaurant_id": "98765"
            },
            meta_config={
                "access_token": "dummy_access_token",
                "catalog_id": "12345"
            },
            sync_type="push_menu",
            smart_catalog_enabled=False,
            meta_enabled=False,
            sync_options=PetpoojaSyncConfig(
                process_push_menu=True,
                process_item_toggle=False
            )
        ).save()

        restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(bot)
        catalog_images_collection = f"{restaurant_name}_{branch_name}_catalog_images"
        fallback_data = {
            "image_type": "global",
            "image_url": "http://global_image_url.com",
            "image_base64": ""
        }
        CollectionData(
            collection_name=catalog_images_collection,
            data=fallback_data,
            user=user,
            bot=bot,
            status=True,
            timestamp=utc_now()
        ).save()

        local_image_data = {
            "image_type": "local",
            "item_id": int(item_id),
            "image_url": "http://local_image_url.com",
            "image_base64": ""
        }
        CollectionData(
            collection_name=catalog_images_collection,
            data=local_image_data,
            user=user,
            bot=bot,
            status=True,
            timestamp=utc_now()
        ).save()

        result = CognitionDataProcessor.resolve_image_link(bot, item_id)

        expected_result = "http://local_image_url.com"
        assert result == expected_result

        POSIntegrations.objects(bot=bot, provider="petpooja").delete()
        CollectionData.objects(collection_name=catalog_images_collection).delete()

    def test_resolve_image_link_no_image(self):
        bot = "test_bot"
        user = "test_user"
        item_id = "12345"
        provider = "petpooja"

        POSIntegrations(
            bot=bot,
            user=user,
            provider=provider,
            config={
                "restaurant_name": "restaurant1",
                "branch_name": "branch1",
                "restaurant_id": "98765"
            },
            meta_config={
                "access_token": "dummy_access_token",
                "catalog_id": "12345"
            },
            sync_type="push_menu",
            smart_catalog_enabled=False,
            meta_enabled=False,
            sync_options=PetpoojaSyncConfig(
                process_push_menu=True,
                process_item_toggle=False
            )
        ).save()

        restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(bot)
        catalog_images_collection = f"{restaurant_name}_{branch_name}_catalog_images"

        with pytest.raises(Exception,
                           match=f"Image URL not found for {item_id} in {catalog_images_collection}"):
            CognitionDataProcessor.resolve_image_link(bot, item_id)

        POSIntegrations.objects(bot=bot, provider="petpooja").delete()
        CollectionData.objects(collection_name=catalog_images_collection).delete()

    @pytest.mark.asyncio
    @patch("kairon.shared.auth.AccountProcessor.get_bot")
    async def test_save_pos_integration_config_success(self, mock_get_bot):
        bot = "test_bot"
        user = "test_user"
        provider = "petpooja"
        sync_type = "push_menu"

        configuration = {
          "provider": "petpooja",
          "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765",
           },
          "meta_config": {
            "access_token": "dummy_access_token",
            "catalog_id": "12345"
           },
           "smart_catalog_enabled": True,
           "meta_enabled": True,
           "sync_options": {
                "process_push_menu": True,
                "process_item_toggle": True
            }
        }

        mock_get_bot.return_value = {"account": "test_account_id"}
        processor = CognitionDataProcessor()
        result = await processor.save_pos_integration_config(configuration, bot, user, sync_type)
        print(result)

        assert "ey" in result
        assert provider in result
        assert bot in result
        assert sync_type in result

        integration = POSIntegrations.objects(bot=bot, provider=provider, sync_type=sync_type).first()
        assert integration is not None

        assert integration.config["restaurant_id"] == "98765"
        assert integration.config["restaurant_name"] == "restaurant1"
        assert integration.config["branch_name"] == "branch1"

        assert integration.meta_config == {
            "access_token": "dummy_access_token",
            "catalog_id": "12345"
        }

        assert integration.meta_enabled is True
        assert integration.smart_catalog_enabled is True

        assert integration.sync_options.process_push_menu is True
        assert integration.sync_options.process_item_toggle is True
        POSIntegrations.objects(bot=bot, provider=provider).delete()

    @pytest.mark.asyncio
    @patch("kairon.shared.auth.AccountProcessor.get_bot")
    async def test_save_pos_integration_config_updates_existing_record(self, mock_get_bot):
        bot = "test_bot"
        user = "test_user"
        provider = "petpooja"
        sync_type = "push_menu"

        configuration = {
            "provider": provider,
            "config": {
                "restaurant_name": "restaurant1",
                "branch_name": "branch1",
                "restaurant_id": "12345",
            },
            "meta_config": {
                "access_token": "token1",
                "catalog_id": "abc"
            },
            "smart_catalog_enabled": False,
            "meta_enabled": False,
            "sync_options": {
                "process_push_menu": False,
                "process_item_toggle": False
            }
        }

        mock_get_bot.return_value = {"account": "test_account_id"}

        processor = CognitionDataProcessor()
        await processor.save_pos_integration_config(configuration, bot, user, sync_type)
        updated_config = configuration.copy()
        updated_config["config"]["restaurant_id"] = "99999"
        updated_config["smart_catalog_enabled"] = True
        updated_config["sync_options"] = {
            "process_push_menu": True,
            "process_item_toggle": True
        }

        await processor.save_pos_integration_config(updated_config, bot, user, sync_type)

        integration = POSIntegrations.objects(bot=bot, provider=provider, sync_type=sync_type).first()
        assert integration.config["restaurant_id"] == "99999"
        assert integration.smart_catalog_enabled is True
        assert integration.sync_options.process_push_menu is True

        POSIntegrations.objects(bot=bot, provider=provider).delete()

    @pytest.mark.asyncio
    @patch("kairon.shared.auth.AccountProcessor.get_bot")
    @mock.patch.object(MetaProcessor, "delete_meta_catalog", autospec=True)
    async def test_save_pos_integration_config_triggers_meta_cleanup(self, mock_delete_meta_catalog, mock_get_bot):
        bot = "test_bot"
        user = "test_user"
        provider = "petpooja"
        sync_type = "push_menu"
        mock_delete_meta_catalog.return_value = None

        processor = CognitionDataProcessor()

        configuration = {
            "provider": provider,
            "config": {
                "restaurant_name": "restaurant1",
                "branch_name": "branch1",
                "restaurant_id": "12345",
            },
            "meta_config": {
                "access_token": "token1",
                "catalog_id": "abc"
            },
            "ai_enabled": True,
            "meta_enabled": True,
            "sync_options": {
                "process_push_menu": True,
                "process_item_toggle": True
            }
        }

        catalog_data_collection = "restaurant1_branch1_catalog_data"

        CollectionData(
            collection_name=catalog_data_collection,
            data={"meta": {"id": "meta123"}},
            user=user,
            bot=bot,
            status=True
        ).save()

        CollectionData(
            collection_name=catalog_data_collection,
            data={"meta": {"id": "meta124"}},
            user=user,
            bot=bot,
            status=True
        ).save()

        mock_get_bot.return_value = {"account": "test_account_id"}

        await processor.save_pos_integration_config(configuration, bot, user, sync_type)
        configuration["meta_enabled"] = False
        await processor.save_pos_integration_config(configuration, bot, user, sync_type)

        mock_delete_meta_catalog.assert_called_once()
        POSIntegrations.objects(bot=bot, provider=provider).delete()

    @pytest.mark.asyncio
    @patch("kairon.shared.auth.AccountProcessor.get_bot")
    @mock.patch.object(LLMProcessor, "_delete_single_collection", autospec=True)
    async def test_save_pos_integration_config_triggers_kv_cleanup(self, mock_delete_single_collection, mock_get_bot):
        bot = "test_bot"
        user = "test_user"
        provider = "petpooja"
        sync_type = "push_menu"
        mock_delete_single_collection.return_value = None

        secrets = [
            {
                "llm_type": "openai",
                "api_key": "common_openai_key",
                "models": ["common_openai_model1", "common_openai_model2"],
                "user": "123",
                "timestamp": utc_now()
            },
        ]

        for secret in secrets:
            LLMSecret(**secret).save()

        processor = CognitionDataProcessor()

        configuration = {
            "provider": provider,
            "config": {
                "restaurant_name": "restaurant1",
                "branch_name": "branch1",
                "restaurant_id": "12345"
            },
            "smart_catalog_enabled": True,
            "meta_enabled": True,
            "sync_options": {
                "process_push_menu": True,
                "process_item_toggle": True
            }
        }

        restaurant_name = "restaurant1"
        branch_name = "branch1"
        catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"
        catalog_collection = f"{restaurant_name}_{branch_name}_catalog"

        metadata = [
            {
                "column_name": "id",
                "data_type": "int",
                "enable_search": True,
                "create_embeddings": True
            }
        ]

        cognition_schema = CognitionSchema(
            metadata=[ColumnMetadata(**item) for item in metadata],
            collection_name=catalog_collection,
            user=user,
            bot=bot,
            timestamp=utc_now()
        )
        cognition_schema.validate(clean=True)
        cognition_schema.save()

        CognitionData(
            data={"id": "kv123"},
            vector_id=99,
            content_type="json",
            collection=catalog_collection,
            user=user,
            bot=bot
        ).save()

        CognitionData(
            data={"id": "kv124"},
            vector_id=99,
            content_type="json",
            collection=catalog_collection,
            user=user,
            bot=bot
        ).save()

        mock_get_bot.return_value = {"account": "test_account_id"}

        assert CognitionData.objects(bot=bot, collection=catalog_collection, data__id="kv123").count() == 1
        assert CognitionData.objects(bot=bot, collection=catalog_collection, data__id="kv124").count() == 1
        assert CognitionSchema.objects(bot=bot, collection_name=catalog_collection).count() == 1

        await processor.save_pos_integration_config(configuration, bot, user, sync_type)

        assert CognitionData.objects(bot=bot, collection=catalog_collection, data__id="kv123").count() == 1
        assert CognitionData.objects(bot=bot, collection=catalog_collection, data__id="kv124").count() == 1
        assert CognitionSchema.objects(bot=bot, collection_name=catalog_collection).count() == 1

        configuration["smart_catalog_enabled"] = False
        await processor.save_pos_integration_config(configuration, bot, user, sync_type)

        assert CognitionData.objects(bot=bot, collection=catalog_collection, data__id="kv123").count() == 0
        assert CognitionData.objects(bot=bot, collection=catalog_collection, data__id="kv124").count() == 0
        assert CognitionSchema.objects(bot=bot, collection_name=catalog_collection).count() == 0

        mock_delete_single_collection.assert_called_once()

        POSIntegrations.objects(bot=bot, provider=provider).delete()
        CollectionData.objects(bot=bot, collection_name=catalog_data_collection).delete()
        CognitionData.objects(bot=bot, collection=catalog_collection).delete()
        CognitionSchema.objects(bot=bot, collection_name=catalog_collection).delete()
        LLMSecret.objects().delete()

    def test_list_pos_integration_configs_success(self):
        bot = "test_bot"
        user = "test_user"
        provider = "petpooja"
        POSIntegrations(
            bot=bot,
            user=user,
            provider=provider,
            config={
                "branch_name": "Bangalore",
                "restaurant_id": "123"
            },
            meta_config = {
                "access_token": "dummy_access_token",
                "catalog_id": "12345"
            },
            sync_type="push_menu",
            smart_catalog_enabled=False,
            meta_enabled=False,
            sync_options=PetpoojaSyncConfig(
                process_push_menu=True,
                process_item_toggle=False
            )
        ).save()

        POSIntegrations(
            bot=bot,
            user=user,
            provider=provider,
            config={
                "branch_name": "Bangalore",
                "restaurant_id": "123"
            },
            meta_config = {
                "access_token": "dummy_access_token",
                "catalog_id": "12345"
            },
            sync_type="item_toggle",
            smart_catalog_enabled=False,
            meta_enabled=False,
            sync_options=PetpoojaSyncConfig(
                process_push_menu=True,
                process_item_toggle=False
            )
        ).save()

        result = CognitionDataProcessor.list_pos_integration_configs(bot)

        assert isinstance(result, list)
        assert len(result) == 1

        config = result[0]
        assert config["bot"] == bot
        assert config["provider"] == provider
        assert config["config"] == {"restaurant_id": "123", "branch_name": "Bangalore"}
        assert set(config["sync_type"]) == {"push_menu", "item_toggle"}
        assert config["user"] == user
        assert "timestamp" in config
        assert config["meta_config"] == {"access_token": "dummy_access_token", "catalog_id": "12345"}
        POSIntegrations.objects(provider= "petpooja").delete()

    def test_list_pos_integration_configs_empty(self):
        bot = "test_bot_no_data"

        POSIntegrations.objects(bot=bot).delete()

        result = CognitionDataProcessor.list_pos_integration_configs(bot)

        assert isinstance(result, list)
        assert result == []

    def test_delete_pos_integration_config_success(self):
        bot = "test_bot"
        user = "test_user"
        provider = "petpooja"
        sync_type = "push_menu"

        POSIntegrations(
            bot=bot,
            user=user,
            provider=provider,
            config={
                "branch_name": "Bangalore",
                "restaurant_id": "123"
            },
            sync_type="push_menu",
            smart_catalog_enabled=False,
            meta_enabled=False,
            sync_options=PetpoojaSyncConfig(
                process_push_menu=True,
                process_item_toggle=False
            )
        ).save()

        POSIntegrations(
            bot=bot,
            user=user,
            provider=provider,
            config={
                "branch_name": "Bangalore",
                "restaurant_id": "123"
            },
            sync_type="item_toggle",
            smart_catalog_enabled=False,
            meta_enabled=False,
            sync_options=PetpoojaSyncConfig(
                process_push_menu=True,
                process_item_toggle=False
            )
        ).save()

        assert POSIntegrations.objects(bot=bot, provider=provider).count() == 2

        result = CognitionDataProcessor.delete_pos_integration_config(bot, provider, sync_type)

        assert result == {"provider": provider, "deleted_count": 1, "sync_type": sync_type}
        assert POSIntegrations.objects(bot=bot, provider=provider).count() == 1
        POSIntegrations.objects(provider= "petpooja").delete()

    def test_delete_pos_integration_config_no_sync_type_provided_success(self):
        bot = "test_bot"
        user = "test_user"
        provider = "petpooja"
        sync_type = "push_menu"

        POSIntegrations(
            bot=bot,
            user=user,
            provider=provider,
            config={
                "branch_name": "Bangalore",
                "restaurant_id": "123"
            },
            sync_type="push_menu",
            smart_catalog_enabled=False,
            meta_enabled=False,
            sync_options=PetpoojaSyncConfig(
                process_push_menu=True,
                process_item_toggle=False
            )
        ).save()

        POSIntegrations(
            bot=bot,
            user=user,
            provider=provider,
            config={
                "branch_name": "Bangalore",
                "restaurant_id": "123"
            },
            sync_type="item_toggle",
            smart_catalog_enabled=False,
            meta_enabled=False,
            sync_options=PetpoojaSyncConfig(
                process_push_menu=True,
                process_item_toggle=False
            )
        ).save()

        assert POSIntegrations.objects(bot=bot, provider=provider).count() == 2

        result = CognitionDataProcessor.delete_pos_integration_config(bot, provider)

        assert result == {"provider": provider, "deleted_count": 2}
        assert POSIntegrations.objects(bot=bot, provider=provider).count() == 0
        POSIntegrations.objects(provider= "petpooja").delete()

    def test_delete_pos_integration_config_failure(self):
        bot = "test_bot"
        user = "test_user"
        provider = "petpooja"
        sync_type = "push_menu"
        with pytest.raises(AppException, match="Integration config not found"):
            CognitionDataProcessor.delete_pos_integration_config(provider, bot, sync_type)

    @patch("kairon.shared.auth.AccountProcessor.get_bot")
    def test_get_pos_integration_endpoint_push_menu_success(self, mock_get_bot):
        bot = "test_bot"
        user = "test_user"
        provider = "petpooja"
        sync_type = "push_menu"

        POSIntegrations(
            bot=bot,
            user=user,
            provider=provider,
            config={
                "branch_name": "Bangalore",
                "restaurant_id": "123"
            },
            sync_type=sync_type,
            smart_catalog_enabled=False,
            meta_enabled=False,
            sync_options=PetpoojaSyncConfig(
                process_push_menu=True,
                process_item_toggle=False
            )
        ).save()

        mock_get_bot.return_value = {"account": "test_account_id"}

        result = CognitionDataProcessor.get_pos_integration_endpoint(bot, provider, sync_type)

        assert f"/{provider}/{sync_type}/{bot}/" in result
        POSIntegrations.objects(provider="petpooja").delete()

    @patch("kairon.shared.auth.AccountProcessor.get_bot")
    def test_get_pos_integration_endpoint_item_toggle(self, mock_get_bot):
        bot = "test_bot"
        user = "test_user"
        provider = "petpooja"
        sync_type = "item_toggle"

        POSIntegrations(
            bot=bot,
            user=user,
            provider=provider,
            config={
                "branch_name": "Bangalore",
                "restaurant_id": "123"
            },
            sync_type=sync_type,
            smart_catalog_enabled=False,
            meta_enabled=False,
            sync_options=PetpoojaSyncConfig(
                process_push_menu=True,
                process_item_toggle=False
            )
        ).save()

        mock_get_bot.return_value = {"account": "test_account_id"}

        result = CognitionDataProcessor.get_pos_integration_endpoint(bot, provider, sync_type)

        assert f"/{provider}/{sync_type}/{bot}/" in result
        POSIntegrations.objects(provider="petpooja").delete()
        CollectionData.objects().delete()

    def test_get_restaurant_and_branch_name_success(self):
        bot = "test_bot"
        user = "test_user"

        POSIntegrations(
            bot=bot,
            user=user,
            provider="petpooja",
            config={
                "restaurant_name": "my_test_restaurant",
                "branch_name": "main_branch",
                "restaurant_id": "123"
            },
            sync_type="push_menu",
            smart_catalog_enabled=False,
            meta_enabled=False,
            sync_options=PetpoojaSyncConfig(
                process_push_menu=True,
                process_item_toggle=False
            )
        ).save()

        restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(bot)

        assert restaurant_name == "my_test_restaurant"
        assert branch_name == "main_branch"

        POSIntegrations.objects(bot=bot).delete()

    def test_get_restaurant_and_branch_name_no_config(self):
        bot = "bot_without_config"
        POSIntegrations.objects(bot=bot).delete()

        with pytest.raises(Exception, match=f"No POS integration config found for bot: {bot}"):
            CognitionDataProcessor.get_restaurant_and_branch_name(bot)

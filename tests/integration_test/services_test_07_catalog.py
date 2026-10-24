from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training


@responses.activate
def test_add_pos_integration_config_success():
    payload = {
      "connector_type": "petpooja",
      "config": {
        "restaurant_name": "restaurant1",
        "branch_name": "branch1",
        "restaurant_id": "98765"
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

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=push_menu",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/push_menu" in actual["data"]
    assert str(pytest.bot) in actual["data"]

    provider_mapping = CatalogProviderMapping.objects(provider="petpooja").first()
    assert provider_mapping is not None
    assert provider_mapping.meta_mappings is not None
    assert provider_mapping.kv_mappings is not None

    pos_integration = POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").first()
    assert pos_integration is not None
    assert pos_integration.config["restaurant_id"] == "98765"
    assert pos_integration.meta_config["access_token"] == "dummy_access_token"

    CatalogProviderMapping.objects(provider="petpooja").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").delete()


@responses.activate
def test_get_pos_endpoint_push_menu():
    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
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

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=push_menu",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/push_menu" in actual["data"]
    assert str(pytest.bot) in actual["data"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/petpooja/push_menu/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert "integration/petpooja/push_menu" in actual["data"]
    assert actual["message"] == "Endpoint fetched"
    assert actual["error_code"] == 0
    assert actual["success"]


@responses.activate
def test_get_pos_endpoint_item_toggle():
    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
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

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=item_toggle",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/item_toggle" in actual["data"]
    assert str(pytest.bot) in actual["data"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/petpooja/item_toggle/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    print(actual)
    assert "integration/petpooja/item_toggle" in actual["data"]
    assert actual["message"] == "Endpoint fetched"
    assert actual["error_code"] == 0
    assert actual["success"]

@responses.activate
def test_list_pos_integration_configs_success():
    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
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

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=push_menu",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/push_menu" in actual["data"]
    assert str(pytest.bot) in actual["data"]

    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
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

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=item_toggle",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/item_toggle" in actual["data"]
    assert str(pytest.bot) in actual["data"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/integrations",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()
    assert actual["message"] == "POS Integration config fetched"
    assert actual["error_code"] == 0
    assert actual["success"] is True
    assert isinstance(actual["data"], list)

    petpooja_config = next((item for item in actual["data"] if item.get("provider") == "petpooja"), None)
    assert petpooja_config is not None

    assert petpooja_config["bot"] == str(pytest.bot)
    assert petpooja_config["provider"] == "petpooja"
    assert set(petpooja_config["sync_type"]) == {"push_menu", "item_toggle"}
    assert petpooja_config["config"]["restaurant_name"] == "restaurant1"
    assert petpooja_config["config"]["branch_name"] == "branch1"
    assert petpooja_config["config"]["restaurant_id"] == "98765"
    assert petpooja_config["meta_config"]["access_token"] == "dummy_access_token"
    assert petpooja_config["meta_config"]["catalog_id"] == "12345"

    CatalogProviderMapping.objects(provider="petpooja").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja").delete()

@responses.activate
def test_list_pos_integration_configs_empty():
    """
    Test fetching POS integration configs when no configs exist for the bot.
    """

    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/integrations",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()
    assert actual["message"] == "POS Integration config fetched"
    assert actual["error_code"] == 0
    assert actual["success"] is True
    assert isinstance(actual["data"], list)
    assert actual["data"] == []

@responses.activate
def test_delete_pos_integration_config_success():
    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
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

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=push_menu",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/push_menu" in actual["data"]
    assert str(pytest.bot) in actual["data"]

    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
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

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=item_toggle",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/item_toggle" in actual["data"]
    assert str(pytest.bot) in actual["data"]

    assert POSIntegrations.objects(bot=pytest.bot, provider="petpooja").count() == 2

    response = client.delete(
        url=f"/api/bot/{pytest.bot}/data/integrations?provider=petpooja&sync_type=push_menu",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()
    assert actual["success"] is True
    assert actual["error_code"] == 0
    assert actual["message"] == "POS Integration config deleted"
    assert POSIntegrations.objects(bot=pytest.bot, provider="petpooja").count() == 1
    assert actual["data"]["provider"] == "petpooja"
    assert actual["data"]["sync_type"] == "push_menu"
    assert actual["data"]["deleted_count"] == 1
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja").delete()

@responses.activate
def test_delete_pos_integration_config_no_sync_type_provided_success():
    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
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

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=push_menu",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/push_menu" in actual["data"]
    assert str(pytest.bot) in actual["data"]

    payload = {
      "connector_type": "petpooja",
      "config": {
        "restaurant_name": "restaurant1",
        "branch_name": "branch1",
        "restaurant_id": "98765"
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

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=item_toggle",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/item_toggle" in actual["data"]
    assert str(pytest.bot) in actual["data"]

    assert POSIntegrations.objects(bot=pytest.bot, provider="petpooja").count() == 2

    response = client.delete(
        url=f"/api/bot/{pytest.bot}/data/integrations?provider=petpooja",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()
    assert actual["success"] is True
    assert actual["error_code"] == 0
    assert actual["message"] == "POS Integration config deleted"
    assert POSIntegrations.objects(bot=pytest.bot, provider="petpooja").count() == 0
    assert actual["data"]["provider"] == "petpooja"
    assert actual["data"]["deleted_count"] == 2
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja").delete()

@responses.activate
def test_delete_pos_integration_config_not_found():
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/data/integrations?provider=invalid_provider&sync_type=invalid_sync",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()
    assert actual["success"] is False
    assert actual["message"] == "Integration config not found"
    assert actual["error_code"] == 422

@responses.activate
def test_get_pos_params():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/pos/params",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()
    assert response.status_code == 200
    assert actual["success"] is True
    assert actual["message"] is None
    assert actual["error_code"] == 0

    assert "petpooja" in actual["data"]
    petpooja_data = actual["data"]["petpooja"]

    assert "required_fields" in petpooja_data
    assert petpooja_data["required_fields"] == ['restaurant_name', 'branch_name', 'restaurant_id', {'sync_type': ['push_menu', 'item_toggle']} ]

    assert "optional_fields" in petpooja_data
    assert petpooja_data["optional_fields"] == ['process_push_menu', 'process_item_toggle', 'meta_enabled',  'smart_catalog_enabled', 'access_token', 'catalog_id']

    assert "disabled_fields" in petpooja_data
    assert petpooja_data["disabled_fields"] == ["provider"]


@responses.activate
def test_add_pos_integration_config_invalid_provider():
    payload = {
        "connector_type": "invalid_provider",
        "config": {
            "restaurant_name": "invalid",
            "branch_name": "invalid",
            "restaurant_id": "00000",
        },
        "meta_config": {
            "access_token": "invalid",
            "catalog_id": "000"
        },
        "smart_catalog_enabled": True,
        "meta_enabled": True,
        "sync_options": {
            "process_push_menu": True,
            "process_item_toggle": True
        }
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=push_menu",
        json=payload,
        headers={"Authorization": f"{pytest.token_type} {pytest.access_token}"}
    )

    actual = response.json()
    assert actual["message"] == "Invalid Provider"
    assert actual["error_code"] == 422
    assert not actual["success"]

    CatalogProviderMapping.objects(provider="invalid_provider").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="invalid_provider", sync_type="push_menu").delete()


@responses.activate
def test_add_pos_integration_config_invalid_sync_type():
    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
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

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=invalid_sync",
        json=payload,
        headers={"Authorization": f"{pytest.token_type} {pytest.access_token}"}
    )

    actual = response.json()
    assert actual["message"] == "Sync type does not exist"
    assert actual["error_code"] == 422
    assert not actual["success"]

    CatalogProviderMapping.objects(provider="petpooja").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="invalid_sync").delete()


@responses.activate
@mock.patch.object(LLMProcessor, "__collection_exists__", autospec=True)
@mock.patch.object(LLMProcessor, "__create_collection__", autospec=True)
@mock.patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
@mock.patch.object(MailUtility,"format_and_send_mail", autospec=True)
@mock.patch.object(MetaProcessor, "push_meta_catalog", autospec=True)
@mock.patch.object(MetaProcessor, "delete_meta_catalog", autospec=True)
@patch(
    "kairon.shared.actions.utils.ActionUtility.execute_request_async",
    new_callable=AsyncMock
)
def test_catalog_sync_push_menu_success(mock_embedding, mock_collection_exists, mock_create_collection,
                                        mock_collection_upsert, mock_format_and_send_mail, mock_delete_meta_catalog, mock_push_meta_catalog):
    mock_collection_exists.return_value = False
    mock_create_collection.return_value = None
    mock_collection_upsert.return_value = None
    mock_format_and_send_mail.return_value = None
    mock_push_meta_catalog.return_value = None
    mock_delete_meta_catalog.return_value = None

    embedding = list(np.random.random(LLMProcessor.__embedding__))
    embedding = [[0.1] * 3072, [0.1] * 3072, [0.1] * 3072]
    mock_embedding.return_value = (
        embedding,
        200,
        0.05,
        {}
    )
    LLMSecret.objects.delete()
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

    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
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

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=push_menu",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/push_menu" in actual["data"]
    assert str(pytest.bot) in actual["data"]
    sync_url = actual["data"]
    token = sync_url.split(str(pytest.bot) + "/")[1]

    provider_mapping = CatalogProviderMapping.objects(provider="petpooja").first()
    assert provider_mapping is not None
    assert provider_mapping.meta_mappings is not None
    assert provider_mapping.kv_mappings is not None

    pos_integration = POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").first()
    assert pos_integration is not None
    assert pos_integration.config["restaurant_id"] == "98765"
    assert pos_integration.meta_config["access_token"] == "dummy_access_token"

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.catalog_integration}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_images_collection = f"{restaurant_name}_{branch_name}_catalog_images"
    fallback_data = {
        "image_type": "global",
        "image_url": "https://picsum.photos/id/237/200/300",
        "image_base64": ""
    }
    CollectionData(
        collection_name=catalog_images_collection,
        data=fallback_data,
        user="integration@demo.ai",
        bot=pytest.bot,
        status=True,
        timestamp=utc_now()
    ).save()

    push_menu_payload_path = Path("tests/testing_data/catalog_sync/catalog_sync_push_menu_payload.json")

    with push_menu_payload_path.open("r", encoding="utf-8") as f:
        push_menu_payload = json.load(f)

    response = client.post(
        url=sync_url,
        json=push_menu_payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()
    assert actual["message"] == "Sync in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    sync_ref_id = str(latest_log.id)

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.catalog_integration, sync_type="push_menu", token = token,
        provider = "petpooja", sync_ref_id = sync_ref_id
    )

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    assert latest_log is not None
    assert latest_log.execution_id
    assert latest_log.sync_status == EVENT_STATUS.COMPLETED.value
    assert latest_log.status == STATUSES.SUCCESS.value
    assert hasattr(latest_log, "exception")
    assert latest_log.exception == ""


    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"
    catalog_data_docs = CollectionData.objects(collection_name=catalog_data_collection, bot=pytest.bot)
    catalog_item_summaries = [
        {"id": doc.data["kv"]["id"], "price": doc.data["kv"]["price"]}
        for doc in catalog_data_docs
    ]

    expected_items = [
        {"id": "10539634", "price": 8700.0},
        {"id": "10539699", "price": 3426.0},
        {"id": "10539580", "price": 3159.0},
    ]

    assert all(item in catalog_item_summaries for item in expected_items)

    cognition_data_docs = CognitionData.objects(bot=str(pytest.bot))
    cognition_map = {doc.data["id"]: doc.data["price"] for doc in cognition_data_docs if
                     "id" in doc.data and "price" in doc.data}
    for item in expected_items:
        assert item["id"] in cognition_map
        assert cognition_map[item["id"]] == item["price"]

def test_get_catalog_sync_logs():
    response = client.get(
        f"/api/bot/{pytest.bot}/catalog/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = client.get(
        f"/api/bot/{pytest.bot}/logs/catalog?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    log = actual['data']['logs'][0]

    assert 'execution_id' in log and log['execution_id']
    assert 'raw_payload' in log and isinstance(log['raw_payload'], dict)
    assert 'start_timestamp' in log and log['start_timestamp']
    assert 'end_timestamp' in log and log['end_timestamp']
    assert 'validation_errors' in log and log['validation_errors'] == {}
    assert log['provider'] == 'petpooja'
    assert log['sync_type'] == 'push_menu'
    assert log['status'] == STATUSES.SUCCESS.value
    assert log['sync_status'] == EVENT_STATUS.COMPLETED.value
    print(response)
    from_date = date.today()
    to_date = from_date + timedelta(days=1)

    search_response = client.get(
        f"/api/bot/{pytest.bot}/logs/catalog/search?from_date={from_date}&to_date={to_date}&sync_status=Completed",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response_json = search_response.json()
    print(response_json)
    assert response_json["success"] is True
    assert response_json["error_code"] == 0

    data = response_json["data"]
    assert "logs" in data
    assert isinstance(data["logs"], list)

@responses.activate
@mock.patch.object(LLMProcessor, "__collection_exists__", autospec=True)
@mock.patch.object(LLMProcessor, "__create_collection__", autospec=True)
@mock.patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
@mock.patch.object(LLMProcessor, "__delete_collection_points__", autospec=True)
@mock.patch.object(MailUtility,"format_and_send_mail", autospec=True)
@mock.patch.object(MetaProcessor, "push_meta_catalog", autospec=True)
@mock.patch.object(MetaProcessor, "delete_meta_catalog", autospec=True)
@patch(
    "kairon.shared.actions.utils.ActionUtility.execute_request_async",
    new_callable=AsyncMock
)
def test_catalog_sync_push_menu_success_with_delete_data(mock_embedding, mock_collection_exists, mock_create_collection,
                                        mock_collection_upsert, mock_format_and_send_mail, mock_delete_collection_points,
                                                         mock_delete_meta_catalog, mock_push_meta_catalog):
    mock_collection_exists.return_value = False
    mock_create_collection.return_value = None
    mock_collection_upsert.return_value = None
    mock_format_and_send_mail.return_value = None
    mock_push_meta_catalog.return_value = None
    mock_delete_meta_catalog.return_value = None
    mock_delete_collection_points.return_value = None

    embedding = list(np.random.random(LLMProcessor.__embedding__))
    embedding = [[0.1] * 3072, [0.1] * 3072]
    mock_embedding.return_value = (
        embedding,
        200,
        0.05,
        {}
    )
    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
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

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=push_menu",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/push_menu" in actual["data"]
    assert str(pytest.bot) in actual["data"]
    sync_url = actual["data"]
    token = sync_url.split(str(pytest.bot) + "/")[1]

    provider_mapping = CatalogProviderMapping.objects(provider="petpooja").first()
    assert provider_mapping is not None
    assert provider_mapping.meta_mappings is not None
    assert provider_mapping.kv_mappings is not None

    pos_integration = POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").first()
    assert pos_integration is not None
    assert pos_integration.config["restaurant_id"] == "98765"
    assert pos_integration.meta_config["access_token"] == "dummy_access_token"

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.catalog_integration}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    push_menu_payload_path = Path("tests/testing_data/catalog_sync/catalog_sync_push_menu_payload_with_delete_data.json")

    with push_menu_payload_path.open("r", encoding="utf-8") as f:
        push_menu_payload = json.load(f)

    response = client.post(
        url=sync_url,
        json=push_menu_payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()
    assert actual["message"] == "Sync in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    sync_ref_id = str(latest_log.id)

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.catalog_integration, sync_type="push_menu", token = token,
        provider = "petpooja", sync_ref_id = sync_ref_id
    )

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    assert latest_log is not None
    assert latest_log.execution_id
    assert latest_log.sync_status == EVENT_STATUS.COMPLETED.value
    assert latest_log.status == STATUSES.SUCCESS.value
    assert hasattr(latest_log, "exception")
    assert latest_log.exception == ""


    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"
    catalog_data_docs = CollectionData.objects(collection_name=catalog_data_collection, bot=pytest.bot)
    catalog_item_summaries = [
        {"id": doc.data["kv"]["id"], "price": doc.data["kv"]["price"]}
        for doc in catalog_data_docs
    ]
    expected_items = [
        {"id": "10539699", "price": 123.0},
        {"id": "10539580", "price": 3159.0},
    ]

    assert all(item in catalog_item_summaries for item in expected_items)

    cognition_data_docs = CognitionData.objects(bot=str(pytest.bot))
    cognition_map = {doc.data["id"]: doc.data["price"] for doc in cognition_data_docs if
                     "id" in doc.data and "price" in doc.data}
    for item in expected_items:
        assert item["id"] in cognition_map
        assert cognition_map[item["id"]] == item["price"]


@responses.activate
@mock.patch.object(LLMProcessor, "__collection_exists__", autospec=True)
@mock.patch.object(LLMProcessor, "__create_collection__", autospec=True)
@mock.patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
@mock.patch.object(MailUtility,"format_and_send_mail", autospec=True)
@mock.patch.object(MetaProcessor, "update_meta_catalog", autospec=True)
@patch(
    "kairon.shared.actions.utils.ActionUtility.execute_request_async",
    new_callable=AsyncMock
)
def test_catalog_sync_item_toggle_success(mock_embedding, mock_collection_exists, mock_create_collection,
                                        mock_collection_upsert, mock_format_and_send_mail, mock_update_meta_catalog):
    mock_collection_exists.return_value = False
    mock_create_collection.return_value = None
    mock_collection_upsert.return_value = None
    mock_format_and_send_mail.return_value = None
    mock_update_meta_catalog.return_value = None

    embedding = list(np.random.random(LLMProcessor.__embedding__))
    embedding = [[0.1] * 3072, [0.1] * 3072]
    mock_embedding.return_value = (
        embedding,
        200,
        0.05,
        {}
    )
    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
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
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=item_toggle",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/item_toggle" in actual["data"]
    assert str(pytest.bot) in actual["data"]
    sync_url = actual["data"]
    token = sync_url.split(str(pytest.bot) + "/")[1]

    provider_mapping = CatalogProviderMapping.objects(provider="petpooja").first()
    assert provider_mapping is not None
    assert provider_mapping.meta_mappings is not None
    assert provider_mapping.kv_mappings is not None

    pos_integration = POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="item_toggle").first()
    assert pos_integration is not None
    assert pos_integration.config["restaurant_id"] == "98765"
    assert pos_integration.meta_config["access_token"] == "dummy_access_token"

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.catalog_integration}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    item_toggle_payload_path = Path("tests/testing_data/catalog_sync/catalog_sync_item_toggle_payload.json")

    with item_toggle_payload_path.open("r", encoding="utf-8") as f:
        item_toggle_payload = json.load(f)

    response = client.post(
        url=sync_url,
        json=item_toggle_payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()
    assert actual["message"] == "Sync in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    sync_ref_id = str(latest_log.id)

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.catalog_integration, sync_type="item_toggle", token = token,
        provider = "petpooja", sync_ref_id = sync_ref_id
    )

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    assert latest_log is not None
    assert latest_log.execution_id
    assert latest_log.sync_status == EVENT_STATUS.COMPLETED.value
    assert latest_log.status == STATUSES.SUCCESS.value
    assert hasattr(latest_log, "exception")
    assert latest_log.exception == ""

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"
    catalog_data_docs = CollectionData.objects(collection_name=catalog_data_collection, bot=pytest.bot)
    catalog_item_summaries = [
        {"id": doc.data["kv"]["id"], "availability": doc.data["kv"]["availability"]}
        for doc in catalog_data_docs
    ]
    expected_items = [
        {"id": "10539699", "availability": "in stock"},
        {"id": "10539580", "availability": "out of stock"},
    ]

    assert all(item in catalog_item_summaries for item in expected_items)

    cognition_data_docs = CognitionData.objects(bot=str(pytest.bot))
    cognition_map = {doc.data["id"]: doc.data["availability"] for doc in cognition_data_docs if
                     "id" in doc.data and "availability" in doc.data}
    for item in expected_items:
        assert item["id"] in cognition_map
        assert cognition_map[item["id"]] == item["availability"]


    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_images_collection = f"{restaurant_name}_{branch_name}_catalog_images"

    CatalogProviderMapping.objects(provider="petpooja").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="item_toggle").delete()
    LLMSecret.objects.delete()
    CollectionData.objects(collection_name=catalog_data_collection).delete()
    CollectionData.objects(collection_name=catalog_images_collection).delete()
    CatalogSyncLogs.objects.delete()
    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()

@responses.activate
@mock.patch.object(LLMProcessor, "__collection_exists__", autospec=True)
@mock.patch.object(LLMProcessor, "__create_collection__", autospec=True)
@mock.patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
@mock.patch.object(MailUtility,"format_and_send_mail", autospec=True)
@mock.patch.object(MetaProcessor, "push_meta_catalog", autospec=True)
@mock.patch.object(MetaProcessor, "delete_meta_catalog", autospec=True)
@patch(
    "kairon.shared.actions.utils.ActionUtility.execute_request_async",
    new_callable=AsyncMock
)
def test_catalog_sync_push_menu_process_push_menu_disabled(mock_embedding, mock_collection_exists, mock_create_collection,
                                        mock_collection_upsert, mock_format_and_send_mail, mock_delete_meta_catalog, mock_push_meta_catalog):
    mock_collection_exists.return_value = False
    mock_create_collection.return_value = None
    mock_collection_upsert.return_value = None
    mock_format_and_send_mail.return_value = None
    mock_push_meta_catalog.return_value = None
    mock_delete_meta_catalog.return_value = None

    embedding = list(np.random.random(LLMProcessor.__embedding__))
    embedding = [[0.1] * 3072, [0.1] * 3072, [0.1] * 3072]
    mock_embedding.return_value = (
        embedding,
        200,
        0.05,
        {}
    )
    LLMSecret.objects.delete()
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

    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
        },
        "meta_config": {
            "access_token": "dummy_access_token",
            "catalog_id": "12345"
        },
        "smart_catalog_enabled": False,
        "meta_enabled": False,
        "sync_options": {
            "process_push_menu": False,
            "process_item_toggle": False
        }
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=push_menu",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/push_menu" in actual["data"]
    assert str(pytest.bot) in actual["data"]
    sync_url = actual["data"]
    token = sync_url.split(str(pytest.bot) + "/")[1]

    provider_mapping = CatalogProviderMapping.objects(provider="petpooja").first()
    assert provider_mapping is not None
    assert provider_mapping.meta_mappings is not None
    assert provider_mapping.kv_mappings is not None

    pos_integration = POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").first()
    assert pos_integration is not None
    assert pos_integration.config["restaurant_id"] == "98765"
    assert pos_integration.meta_config["access_token"] == "dummy_access_token"

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.catalog_integration}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    push_menu_payload_path = Path("tests/testing_data/catalog_sync/catalog_sync_push_menu_payload.json")

    with push_menu_payload_path.open("r", encoding="utf-8") as f:
        push_menu_payload = json.load(f)

    response = client.post(
        url=sync_url,
        json=push_menu_payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()
    assert actual["message"] == "Push menu processing is disabled for this bot"
    assert actual["error_code"] == 422
    assert not actual["success"]

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    assert latest_log is not None
    assert latest_log.execution_id
    assert latest_log.sync_status == "Failed"
    assert latest_log.status == STATUSES.FAIL.value
    assert hasattr(latest_log, "exception")
    assert latest_log.exception == "Push menu processing is disabled for this bot"

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"
    catalog_data_docs = CollectionData.objects(collection_name=catalog_data_collection, bot=pytest.bot)
    assert catalog_data_docs.count() == 0
    cognition_data_docs = CognitionData.objects(bot=str(pytest.bot))
    assert cognition_data_docs.count() == 0

    CatalogProviderMapping.objects(provider="petpooja").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").delete()
    LLMSecret.objects.delete()
    CollectionData.objects(collection_name=catalog_data_collection).delete()
    # CollectionData.objects(collection_name=catalog_images_collection).delete()
    CatalogSyncLogs.objects.delete()
    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()


@responses.activate
@mock.patch.object(LLMProcessor, "__collection_exists__", autospec=True)
@mock.patch.object(LLMProcessor, "__create_collection__", autospec=True)
@mock.patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
@mock.patch.object(MailUtility,"format_and_send_mail", autospec=True)
@mock.patch.object(MetaProcessor, "update_meta_catalog", autospec=True)
@patch(
    "kairon.shared.actions.utils.ActionUtility.execute_request_async",
    new_callable=AsyncMock
)
def test_catalog_sync_item_toggle_process_item_toggle_disabled(mock_embedding, mock_collection_exists, mock_create_collection,
                                        mock_collection_upsert, mock_format_and_send_mail, update_meta_catalog):
    mock_collection_exists.return_value = False
    mock_create_collection.return_value = None
    mock_collection_upsert.return_value = None
    mock_format_and_send_mail.return_value = None
    update_meta_catalog.return_value = None

    embedding = list(np.random.random(LLMProcessor.__embedding__))
    embedding = [[0.1] * 3072, [0.1] * 3072, [0.1] * 3072]
    mock_embedding.return_value = (
        embedding,
        200,
        0.05,
        {}
    )
    LLMSecret.objects.delete()
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

    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
        },
        "meta_config": {
            "access_token": "dummy_access_token",
            "catalog_id": "12345"
        },
        "smart_catalog_enabled": False,
        "meta_enabled": False,
        "sync_options": {
            "process_push_menu": False,
            "process_item_toggle": False
        }
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=item_toggle",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/item_toggle" in actual["data"]
    assert str(pytest.bot) in actual["data"]
    sync_url = actual["data"]
    token = sync_url.split(str(pytest.bot) + "/")[1]

    provider_mapping = CatalogProviderMapping.objects(provider="petpooja").first()
    assert provider_mapping is not None
    assert provider_mapping.meta_mappings is not None
    assert provider_mapping.kv_mappings is not None

    pos_integration = POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="item_toggle").first()
    assert pos_integration is not None
    assert pos_integration.config["restaurant_id"] == "98765"
    assert pos_integration.meta_config["access_token"] == "dummy_access_token"

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.catalog_integration}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    item_toggle_payload_path = Path("tests/testing_data/catalog_sync/catalog_sync_item_toggle_payload.json")

    with item_toggle_payload_path.open("r", encoding="utf-8") as f:
        item_toggle_payload = json.load(f)

    response = client.post(
        url=sync_url,
        json=item_toggle_payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()
    assert actual["message"] == "Item toggle is disabled for this bot"
    assert actual["error_code"] == 422
    assert not actual["success"]

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    assert latest_log is not None
    assert latest_log.execution_id
    assert latest_log.sync_status == "Failed"
    assert latest_log.status == STATUSES.FAIL.value
    assert hasattr(latest_log, "exception")
    assert latest_log.exception == "Item toggle is disabled for this bot"

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"
    catalog_data_docs = CollectionData.objects(collection_name=catalog_data_collection, bot=pytest.bot)
    assert catalog_data_docs.count() == 0
    cognition_data_docs = CognitionData.objects(bot=str(pytest.bot))
    assert cognition_data_docs.count() == 0

    CatalogProviderMapping.objects(provider="petpooja").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="item_toggle").delete()
    LLMSecret.objects.delete()
    CollectionData.objects(collection_name=catalog_data_collection).delete()
    # CollectionData.objects(collection_name=catalog_images_collection).delete()
    CatalogSyncLogs.objects.delete()
    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()


@responses.activate
@mock.patch.object(LLMProcessor, "__collection_exists__", autospec=True)
@mock.patch.object(LLMProcessor, "__create_collection__", autospec=True)
@mock.patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
@mock.patch.object(MailUtility,"format_and_send_mail", autospec=True)
@mock.patch.object(MetaProcessor, "push_meta_catalog", autospec=True)
@mock.patch.object(MetaProcessor, "delete_meta_catalog", autospec=True)
@patch(
    "kairon.shared.actions.utils.ActionUtility.execute_request_async",
    new_callable=AsyncMock
)
def test_catalog_sync_push_menu_smart_catalog_disabled_meta_disabled(mock_embedding, mock_collection_exists, mock_create_collection,
                                        mock_collection_upsert, mock_format_and_send_mail, mock_delete_meta_catalog, mock_push_meta_catalog):
    mock_collection_exists.return_value = False
    mock_create_collection.return_value = None
    mock_collection_upsert.return_value = None
    mock_format_and_send_mail.return_value = None
    mock_push_meta_catalog.return_value = None
    mock_delete_meta_catalog.return_value = None

    embedding = list(np.random.random(LLMProcessor.__embedding__))
    embedding = [[0.1] * 3072, [0.1] * 3072, [0.1] * 3072]
    mock_embedding.return_value = (
        embedding,
        200,
        0.05,
        {}
    )
    LLMSecret.objects.delete()
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

    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
        },
        "meta_config": {
            "access_token": "dummy_access_token",
            "catalog_id": "12345"
        },
        "smart_catalog_enabled": False,
        "meta_enabled": False,
        "sync_options": {
            "process_push_menu": True,
            "process_item_toggle": False
        }
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=push_menu",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/push_menu" in actual["data"]
    assert str(pytest.bot) in actual["data"]
    sync_url = actual["data"]
    token = sync_url.split(str(pytest.bot) + "/")[1]

    provider_mapping = CatalogProviderMapping.objects(provider="petpooja").first()
    assert provider_mapping is not None
    assert provider_mapping.meta_mappings is not None
    assert provider_mapping.kv_mappings is not None

    pos_integration = POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").first()
    assert pos_integration is not None
    assert pos_integration.config["restaurant_id"] == "98765"
    assert pos_integration.meta_config["access_token"] == "dummy_access_token"

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.catalog_integration}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_images_collection = f"{restaurant_name}_{branch_name}_catalog_images"
    fallback_data = {
        "image_type": "global",
        "image_url": "https://picsum.photos/id/237/200/300",
        "image_base64": ""
    }
    CollectionData(
        collection_name=catalog_images_collection,
        data=fallback_data,
        user="integration@demo.ai",
        bot=pytest.bot,
        status=True,
        timestamp=utc_now()
    ).save()

    push_menu_payload_path = Path("tests/testing_data/catalog_sync/catalog_sync_push_menu_payload.json")

    with push_menu_payload_path.open("r", encoding="utf-8") as f:
        push_menu_payload = json.load(f)

    response = client.post(
        url=sync_url,
        json=push_menu_payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "Sync in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    sync_ref_id = str(latest_log.id)

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.catalog_integration, sync_type="push_menu", token=token,
        provider="petpooja", sync_ref_id = sync_ref_id
    )

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    assert latest_log is not None
    assert latest_log.execution_id
    assert latest_log.sync_status == EVENT_STATUS.COMPLETED.value
    assert latest_log.status == STATUSES.SUCCESS.value
    assert hasattr(latest_log, "exception")
    assert latest_log.exception == "Sync to knowledge vault and Meta is not allowed for this bot. Contact Support!!"

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"
    catalog_data_docs = CollectionData.objects(collection_name=catalog_data_collection, bot=pytest.bot)
    catalog_item_summaries = [
        {"id": doc.data["kv"]["id"], "price": doc.data["kv"]["price"]}
        for doc in catalog_data_docs
    ]

    expected_items = [
        {"id": "10539634", "price": 8700.0},
        {"id": "10539699", "price": 3426.0},
        {"id": "10539580", "price": 3159.0},
    ]

    assert all(item in catalog_item_summaries for item in expected_items)

    cognition_data_docs = CognitionData.objects(bot=str(pytest.bot))
    assert cognition_data_docs.count() == 0

    CatalogProviderMapping.objects(provider="petpooja").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").delete()
    LLMSecret.objects.delete()
    # CollectionData.objects(collection_name=catalog_data_collection).delete()
    CollectionData.objects(collection_name=catalog_images_collection).delete()
    CatalogSyncLogs.objects.delete()
    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()



@responses.activate
@mock.patch.object(LLMProcessor, "__collection_exists__", autospec=True)
@mock.patch.object(LLMProcessor, "__create_collection__", autospec=True)
@mock.patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
@mock.patch.object(MailUtility,"format_and_send_mail", autospec=True)
@mock.patch.object(MetaProcessor, "update_meta_catalog", autospec=True)
@patch(
    "kairon.shared.actions.utils.ActionUtility.execute_request_async",
    new_callable=AsyncMock
)
def test_catalog_sync_item_toggle_smart_catalog_disabled_meta_disabled(mock_embedding, mock_collection_exists, mock_create_collection,
                                        mock_collection_upsert, mock_format_and_send_mail, mock_update_meta_catalog):
    mock_collection_exists.return_value = False
    mock_create_collection.return_value = None
    mock_collection_upsert.return_value = None
    mock_format_and_send_mail.return_value = None
    mock_update_meta_catalog.return_value = None

    embedding = list(np.random.random(LLMProcessor.__embedding__))
    embedding = [[0.1] * 3072, [0.1] * 3072, [0.1] * 3072]
    mock_embedding.return_value = (
        embedding,
        200,
        0.05,
        {}
    )
    LLMSecret.objects.delete()
    secrets = [
        {
            "llm_type": "openai",
            "api_key": "common_openai_key",
            "models": ["common_openai_model1", "common_openai_model2"],
            "user": "123",
            "timestamp": utc_now()
        },
    ]

    documents = [
        {
            '_id': ObjectId('68777e450cbc4ce07e8a814e'),
            'vector_id': '468c609c-1313-4e47-8629-e26c20bf0e1b',
            'data': {
                'id': '10539580',
                'title': 'Potter 5',
                'description': 'chicken fillet  nuggets come with a sauce of your choice (nugget/garlic sauce). Bite-sized pieces of tender all breast chicken fillets, marinated in our unique & signature blend, breaded and seasoned to perfection, then deep-fried until deliciously tender, crispy with a golden crust',
                'price': 3159.0,
                'facebook_product_category': 'Food and drink > Chicken Meal',
                'availability': 'in stock'
            },
            'content_type': 'json',
            'collection': 'restaurant1_branch1_catalog',
            'user': 'integration@demo.ai',
            'bot': '68777e320cbc4ce07e8a7bb2',
            'timestamp': datetime(2025, 7, 16, 10, 26, 13, 986000)
        }
    ]

    for doc in documents:
        CognitionData(
            data=doc["data"],
            content_type=doc["content_type"],
            collection=doc["collection"],
            user=doc["user"],
            bot=pytest.bot
        ).save()

    document = {
        '_id': ObjectId('68777f6c9c7c306038d1b056'),
        'collection_name': 'restaurant1_branch1_catalog_data',
        'is_secure': [],
        'is_non_editable': [],
        'data': {
            'kv': {
                'id': '10539580',
                'title': 'Potter 5',
                'description': 'chicken fillet  nuggets come with a sauce of your choice (nugget/garlic sauce). '
                               'Bite-sized pieces of tender all breast chicken fillets, marinated in our unique & '
                               'signature blend, breaded and seasoned to perfection, then deep-fried until '
                               'deliciously tender, crispy with a golden crust',
                'price': 3159.0,
                'facebook_product_category': 'Food and drink > Chicken Meal',
                'availability': 'in stock'
            },
            'meta': {
                'id': '10539580',
                'name': 'Potter 5',
                'description': 'chicken fillet  nuggets come with a sauce of your choice (nugget/garlic sauce). '
                               'Bite-sized pieces of tender all breast chicken fillets, marinated in our unique & '
                               'signature blend, breaded and seasoned to perfection, then deep-fried until '
                               'deliciously tender, crispy with a golden crust',
                'price': 3159.0,
                'availability': 'in stock',
                'image_url': 'https://picsum.photos/id/237/200/300',
                'url': 'https://www.kairon.com/',
                'brand': 'Test Restaurant',
                'condition': 'new'
            }
        },
        'user': 'integration@demo.ai',
        'status': True
    }

    CollectionData(
        collection_name=document['collection_name'],
        is_secure=document['is_secure'],
        is_non_editable=document['is_non_editable'],
        data=document['data'],
        user=document['user'],
        bot=pytest.bot,
        status=document['status']
    ).save()

    for secret in secrets:
        LLMSecret(**secret).save()

    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
        },
        "meta_config": {
            "access_token": "dummy_access_token",
            "catalog_id": "12345"
        },
        "smart_catalog_enabled": False,
        "meta_enabled": False,
        "sync_options": {
            "process_push_menu": False,
            "process_item_toggle": True
        }
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=item_toggle",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/item_toggle" in actual["data"]
    assert str(pytest.bot) in actual["data"]
    sync_url = actual["data"]
    token = sync_url.split(str(pytest.bot) + "/")[1]

    provider_mapping = CatalogProviderMapping.objects(provider="petpooja").first()
    assert provider_mapping is not None
    assert provider_mapping.meta_mappings is not None
    assert provider_mapping.kv_mappings is not None

    pos_integration = POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="item_toggle").first()
    assert pos_integration is not None
    assert pos_integration.config["restaurant_id"] == "98765"
    assert pos_integration.meta_config["access_token"] == "dummy_access_token"

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.catalog_integration}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    item_toggle_payload_path = Path("tests/testing_data/catalog_sync/catalog_sync_item_toggle_payload.json")

    with item_toggle_payload_path.open("r", encoding="utf-8") as f:
        item_toggle_payload = json.load(f)

    response = client.post(
        url=sync_url,
        json=item_toggle_payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "Sync in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    sync_ref_id = str(latest_log.id)

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.catalog_integration, sync_type="item_toggle", token=token,
        provider="petpooja", sync_ref_id = sync_ref_id
    )

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    assert latest_log is not None
    assert latest_log.execution_id
    assert latest_log.sync_status == EVENT_STATUS.COMPLETED.value
    assert latest_log.status == STATUSES.SUCCESS.value
    assert hasattr(latest_log, "exception")
    assert latest_log.exception == "Sync to knowledge vault and Meta is not allowed for this bot. Contact Support!!"

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"
    catalog_data_docs = CollectionData.objects(collection_name=catalog_data_collection, bot=pytest.bot)
    catalog_item_summaries = [
        {"id": doc.data["kv"]["id"], "availability": doc.data["kv"]["availability"]}
        for doc in catalog_data_docs
    ]

    expected_items = [
        {"id": "10539634", "availability": "in stock"},
        {"id": "10539699", "availability": "in stock"},
        {"id": "10539580", "availability": "out of stock"},
    ]

    assert all(item in catalog_item_summaries for item in expected_items)

    CatalogProviderMapping.objects(provider="petpooja").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="item_toggle").delete()
    LLMSecret.objects.delete()
    CollectionData.objects(collection_name=catalog_data_collection).delete()
    # CollectionData.objects(collection_name=catalog_images_collection).delete()
    CatalogSyncLogs.objects.delete()
    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()


@responses.activate
@mock.patch.object(LLMProcessor, "__collection_exists__", autospec=True)
@mock.patch.object(LLMProcessor, "__create_collection__", autospec=True)
@mock.patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
@mock.patch.object(MailUtility,"format_and_send_mail", autospec=True)
@mock.patch.object(MetaProcessor, "push_meta_catalog", autospec=True)
@mock.patch.object(MetaProcessor, "delete_meta_catalog", autospec=True)
@patch(
    "kairon.shared.actions.utils.ActionUtility.execute_request_async",
    new_callable=AsyncMock
)
def test_catalog_sync_push_menu_smart_catalog_enabled_meta_disabled(mock_embedding, mock_collection_exists, mock_create_collection,
                                        mock_collection_upsert, mock_format_and_send_mail, mock_delete_meta_catalog, mock_push_meta_catalog):
    mock_collection_exists.return_value = False
    mock_create_collection.return_value = None
    mock_collection_upsert.return_value = None
    mock_format_and_send_mail.return_value = None
    mock_push_meta_catalog.return_value = None
    mock_delete_meta_catalog.return_value = None

    embedding = list(np.random.random(LLMProcessor.__embedding__))
    embedding = [[0.1] * 3072, [0.1] * 3072, [0.1] * 3072]
    mock_embedding.return_value = (
        embedding,
        200,
        0.05,
        {}
    )
    LLMSecret.objects.delete()
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

    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
        },
        "meta_config": {
            "access_token": "dummy_access_token",
            "catalog_id": "12345"
        },
        "smart_catalog_enabled": True,
        "meta_enabled": False,
        "sync_options": {
            "process_push_menu": True,
            "process_item_toggle": False
        }
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=push_menu",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/push_menu" in actual["data"]
    assert str(pytest.bot) in actual["data"]
    sync_url = actual["data"]
    token = sync_url.split(str(pytest.bot) + "/")[1]

    provider_mapping = CatalogProviderMapping.objects(provider="petpooja").first()
    assert provider_mapping is not None
    assert provider_mapping.meta_mappings is not None
    assert provider_mapping.kv_mappings is not None

    pos_integration = POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").first()
    assert pos_integration is not None
    assert pos_integration.config["restaurant_id"] == "98765"
    assert pos_integration.meta_config["access_token"] == "dummy_access_token"

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.catalog_integration}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_images_collection = f"{restaurant_name}_{branch_name}_catalog_images"
    fallback_data = {
        "image_type": "global",
        "image_url": "https://picsum.photos/id/237/200/300",
        "image_base64": ""
    }
    CollectionData(
        collection_name=catalog_images_collection,
        data=fallback_data,
        user="integration@demo.ai",
        bot=pytest.bot,
        status=True,
        timestamp=utc_now()
    ).save()

    push_menu_payload_path = Path("tests/testing_data/catalog_sync/catalog_sync_push_menu_payload.json")

    with push_menu_payload_path.open("r", encoding="utf-8") as f:
        push_menu_payload = json.load(f)

    response = client.post(
        url=sync_url,
        json=push_menu_payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "Sync in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    sync_ref_id = str(latest_log.id)

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.catalog_integration, sync_type="push_menu", token=token,
        provider="petpooja", sync_ref_id = sync_ref_id
    )

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    assert latest_log is not None
    assert latest_log.execution_id
    assert latest_log.sync_status == EVENT_STATUS.COMPLETED.value
    assert latest_log.status == STATUSES.SUCCESS.value
    assert hasattr(latest_log, "exception")
    assert latest_log.exception == "Sync to Meta is not allowed for this bot. Contact Support!!"

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"
    catalog_data_docs = CollectionData.objects(collection_name=catalog_data_collection, bot=pytest.bot)
    catalog_item_summaries = [
        {"id": doc.data["kv"]["id"], "price": doc.data["kv"]["price"]}
        for doc in catalog_data_docs
    ]

    expected_items = [
        {"id": "10539634", "price": 8700.0},
        {"id": "10539699", "price": 3426.0},
        {"id": "10539580", "price": 3159.0},
    ]

    assert all(item in catalog_item_summaries for item in expected_items)

    cognition_data_docs = CognitionData.objects(bot=str(pytest.bot))
    assert cognition_data_docs.count() == 3

    cognition_map = {doc.data["id"]: doc.data["price"] for doc in cognition_data_docs if
                     "id" in doc.data and "price" in doc.data}
    for item in expected_items:
        assert item["id"] in cognition_map
        assert cognition_map[item["id"]] == item["price"]

    CatalogProviderMapping.objects(provider="petpooja").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").delete()
    LLMSecret.objects.delete()
    # CollectionData.objects(collection_name=catalog_data_collection).delete()
    CollectionData.objects(collection_name=catalog_images_collection).delete()
    CatalogSyncLogs.objects.delete()
    # CognitionData.objects(bot=pytest.bot).delete()
    # CognitionSchema.objects(bot=pytest.bot).delete()

@responses.activate
@mock.patch.object(LLMProcessor, "__collection_exists__", autospec=True)
@mock.patch.object(LLMProcessor, "__create_collection__", autospec=True)
@mock.patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
@mock.patch.object(MailUtility,"format_and_send_mail", autospec=True)
@mock.patch.object(MetaProcessor, "update_meta_catalog", autospec=True)
@patch(
    "kairon.shared.actions.utils.ActionUtility.execute_request_async",
    new_callable=AsyncMock
)
def test_catalog_sync_item_toggle_smart_catalog_enabled_meta_disabled(mock_embedding, mock_collection_exists, mock_create_collection,
                                        mock_collection_upsert, mock_format_and_send_mail, mock_update_meta_catalog):
    mock_collection_exists.return_value = False
    mock_create_collection.return_value = None
    mock_collection_upsert.return_value = None
    mock_format_and_send_mail.return_value = None
    mock_update_meta_catalog.return_value = None

    embedding = list(np.random.random(LLMProcessor.__embedding__))
    embedding = [[0.1] * 3072, [0.1] * 3072, [0.1] * 3072]
    mock_embedding.return_value = (
        embedding,
        200,
        0.05,
        {}
    )
    LLMSecret.objects.delete()
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

    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
        },
        "meta_config": {
            "access_token": "dummy_access_token",
            "catalog_id": "12345"
        },
        "smart_catalog_enabled": True,
        "meta_enabled": False,
        "sync_options": {
            "process_push_menu": False,
            "process_item_toggle": True
        }
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=item_toggle",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/item_toggle" in actual["data"]
    assert str(pytest.bot) in actual["data"]
    sync_url = actual["data"]
    token = sync_url.split(str(pytest.bot) + "/")[1]

    provider_mapping = CatalogProviderMapping.objects(provider="petpooja").first()
    assert provider_mapping is not None
    assert provider_mapping.meta_mappings is not None
    assert provider_mapping.kv_mappings is not None

    pos_integration = POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="item_toggle").first()
    assert pos_integration is not None
    assert pos_integration.config["restaurant_id"] == "98765"
    assert pos_integration.meta_config["access_token"] == "dummy_access_token"

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.catalog_integration}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    item_toggle_payload_path = Path("tests/testing_data/catalog_sync/catalog_sync_item_toggle_payload.json")

    with item_toggle_payload_path.open("r", encoding="utf-8") as f:
        item_toggle_payload = json.load(f)

    response = client.post(
        url=sync_url,
        json=item_toggle_payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "Sync in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    sync_ref_id = str(latest_log.id)

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.catalog_integration, sync_type="item_toggle", token=token,
        provider="petpooja", sync_ref_id = sync_ref_id
    )

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    assert latest_log is not None
    assert latest_log.execution_id
    assert latest_log.sync_status == EVENT_STATUS.COMPLETED.value
    assert latest_log.status == STATUSES.SUCCESS.value
    assert hasattr(latest_log, "exception")
    assert latest_log.exception == "Sync to Meta is not allowed for this bot. Contact Support!!"

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"
    catalog_data_docs = CollectionData.objects(collection_name=catalog_data_collection, bot=pytest.bot)
    catalog_item_summaries = [
        {"id": doc.data["kv"]["id"], "availability": doc.data["kv"]["availability"]}
        for doc in catalog_data_docs
    ]

    expected_items = [
        {"id": "10539634", "availability": "in stock"},
        {"id": "10539699", "availability": "in stock"},
        {"id": "10539580", "availability": "out of stock"},
    ]

    assert all(item in catalog_item_summaries for item in expected_items)

    cognition_data_docs = CognitionData.objects(bot=str(pytest.bot))
    assert cognition_data_docs.count() == 3

    cognition_map = {doc.data["id"]: doc.data["availability"] for doc in cognition_data_docs if
                     "id" in doc.data and "availability" in doc.data}
    for item in expected_items:
        assert item["id"] in cognition_map
        assert cognition_map[item["id"]] == item["availability"]

    CatalogProviderMapping.objects(provider="petpooja").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="item_toggle").delete()
    LLMSecret.objects.delete()
    CollectionData.objects(collection_name=catalog_data_collection).delete()
    # CollectionData.objects(collection_name=catalog_images_collection).delete()
    CatalogSyncLogs.objects.delete()
    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()



@responses.activate
@mock.patch.object(LLMProcessor, "__collection_exists__", autospec=True)
@mock.patch.object(LLMProcessor, "__create_collection__", autospec=True)
@mock.patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
@mock.patch.object(MailUtility,"format_and_send_mail", autospec=True)
@mock.patch.object(MetaProcessor, "push_meta_catalog", autospec=True)
@mock.patch.object(MetaProcessor, "delete_meta_catalog", autospec=True)
@patch(
    "kairon.shared.actions.utils.ActionUtility.execute_request_async",
    new_callable=AsyncMock
)
def test_catalog_sync_push_menu_smart_catalog_disabled_meta_enabled(mock_embedding, mock_collection_exists, mock_create_collection,
                                        mock_collection_upsert, mock_format_and_send_mail, mock_delete_meta_catalog, mock_push_meta_catalog):
    mock_collection_exists.return_value = False
    mock_create_collection.return_value = None
    mock_collection_upsert.return_value = None
    mock_format_and_send_mail.return_value = None
    mock_push_meta_catalog.return_value = None
    mock_delete_meta_catalog.return_value = None

    embedding = list(np.random.random(LLMProcessor.__embedding__))
    embedding = [[0.1] * 3072, [0.1] * 3072, [0.1] * 3072]
    mock_embedding.return_value = (
        embedding,
        200,
        0.05,
        {}
    )
    LLMSecret.objects.delete()
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

    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
        },
        "meta_config": {
            "access_token": "dummy_access_token",
            "catalog_id": "12345"
        },
        "smart_catalog_enabled": False,
        "meta_enabled": True,
        "sync_options": {
            "process_push_menu": True,
            "process_item_toggle": False
        }
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=push_menu",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/push_menu" in actual["data"]
    assert str(pytest.bot) in actual["data"]
    sync_url = actual["data"]
    token = sync_url.split(str(pytest.bot) + "/")[1]

    provider_mapping = CatalogProviderMapping.objects(provider="petpooja").first()
    assert provider_mapping is not None
    assert provider_mapping.meta_mappings is not None
    assert provider_mapping.kv_mappings is not None

    pos_integration = POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").first()
    assert pos_integration is not None
    assert pos_integration.config["restaurant_id"] == "98765"
    assert pos_integration.meta_config["access_token"] == "dummy_access_token"

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.catalog_integration}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_images_collection = f"{restaurant_name}_{branch_name}_catalog_images"
    fallback_data = {
        "image_type": "global",
        "image_url": "https://picsum.photos/id/237/200/300",
        "image_base64": ""
    }
    CollectionData(
        collection_name=catalog_images_collection,
        data=fallback_data,
        user="integration@demo.ai",
        bot=pytest.bot,
        status=True,
        timestamp=utc_now()
    ).save()

    push_menu_payload_path = Path("tests/testing_data/catalog_sync/catalog_sync_push_menu_payload.json")

    with push_menu_payload_path.open("r", encoding="utf-8") as f:
        push_menu_payload = json.load(f)

    response = client.post(
        url=sync_url,
        json=push_menu_payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "Sync in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    sync_ref_id = str(latest_log.id)

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.catalog_integration, sync_type="push_menu", token=token,
        provider="petpooja", sync_ref_id = sync_ref_id
    )

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    assert latest_log is not None
    assert latest_log.execution_id
    assert latest_log.sync_status == EVENT_STATUS.COMPLETED.value
    assert latest_log.status == STATUSES.SUCCESS.value
    assert hasattr(latest_log, "exception")
    assert latest_log.exception == "Sync to knowledge vault is not allowed for this bot. Contact Support!!"

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"
    catalog_data_docs = CollectionData.objects(collection_name=catalog_data_collection, bot=pytest.bot)
    catalog_item_summaries = [
        {"id": doc.data["kv"]["id"], "price": doc.data["kv"]["price"]}
        for doc in catalog_data_docs
    ]

    expected_items = [
        {"id": "10539634", "price": 8700.0},
        {"id": "10539699", "price": 3426.0},
        {"id": "10539580", "price": 3159.0},
    ]

    assert all(item in catalog_item_summaries for item in expected_items)

    cognition_data_docs = CognitionData.objects(bot=str(pytest.bot))
    assert cognition_data_docs.count() == 0

    CatalogProviderMapping.objects(provider="petpooja").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").delete()
    LLMSecret.objects.delete()
    CollectionData.objects(collection_name=catalog_data_collection).delete()
    CollectionData.objects(collection_name=catalog_images_collection).delete()
    CatalogSyncLogs.objects.delete()
    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()

@responses.activate
@mock.patch.object(LLMProcessor, "__collection_exists__", autospec=True)
@mock.patch.object(LLMProcessor, "__create_collection__", autospec=True)
@mock.patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
@mock.patch.object(MailUtility,"format_and_send_mail", autospec=True)
@mock.patch.object(MetaProcessor, "push_meta_catalog", autospec=True)
@mock.patch.object(MetaProcessor, "delete_meta_catalog", autospec=True)
@patch(
    "kairon.shared.actions.utils.ActionUtility.execute_request_async",
    new_callable=AsyncMock
)
def test_catalog_sync_push_menu_global_image_not_found(mock_embedding, mock_collection_exists, mock_create_collection,
                                        mock_collection_upsert, mock_format_and_send_mail, mock_delete_meta_catalog, mock_push_meta_catalog):
    mock_collection_exists.return_value = False
    mock_create_collection.return_value = None
    mock_collection_upsert.return_value = None
    mock_format_and_send_mail.return_value = None
    mock_push_meta_catalog.return_value = None
    mock_delete_meta_catalog.return_value = None

    embedding = list(np.random.random(LLMProcessor.__embedding__))
    embedding = [[0.1] * 3072, [0.1] * 3072, [0.1] * 3072]
    mock_embedding.return_value = (
        embedding,
        200,
        0.05,
        {}
    )
    LLMSecret.objects.delete()
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

    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
        },
        "meta_config": {
            "access_token": "dummy_access_token",
            "catalog_id": "12345"
        },
        "smart_catalog_enabled": False,
        "meta_enabled": True,
        "sync_options": {
            "process_push_menu": True,
            "process_item_toggle": False
        }
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=push_menu",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/push_menu" in actual["data"]
    assert str(pytest.bot) in actual["data"]
    sync_url = actual["data"]
    token = sync_url.split(str(pytest.bot) + "/")[1]

    provider_mapping = CatalogProviderMapping.objects(provider="petpooja").first()
    assert provider_mapping is not None
    assert provider_mapping.meta_mappings is not None
    assert provider_mapping.kv_mappings is not None

    pos_integration = POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").first()
    assert pos_integration is not None
    assert pos_integration.config["restaurant_id"] == "98765"
    assert pos_integration.meta_config["access_token"] == "dummy_access_token"

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.catalog_integration}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    push_menu_payload_path = Path("tests/testing_data/catalog_sync/catalog_sync_push_menu_payload.json")

    with push_menu_payload_path.open("r", encoding="utf-8") as f:
        push_menu_payload = json.load(f)

    response = client.post(
        url=sync_url,
        json=push_menu_payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "Global fallback image URL not found"
    assert actual["error_code"] == 422
    assert not actual["success"]

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    assert latest_log is not None
    assert latest_log.execution_id
    assert latest_log.sync_status == "Failed"
    assert latest_log.status == STATUSES.FAIL.value
    assert hasattr(latest_log, "exception")
    assert latest_log.exception == "Global fallback image URL not found"

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"
    catalog_data_docs = CollectionData.objects(collection_name=catalog_data_collection, bot=pytest.bot)
    assert catalog_data_docs.count() == 0
    cognition_data_docs = CognitionData.objects(bot=str(pytest.bot))
    assert cognition_data_docs.count() == 0

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_images_collection = f"{restaurant_name}_{branch_name}_catalog_images"

    CatalogProviderMapping.objects(provider="petpooja").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").delete()
    LLMSecret.objects.delete()
    CollectionData.objects(collection_name=catalog_data_collection).delete()
    CollectionData.objects(collection_name=catalog_images_collection).delete()
    CatalogSyncLogs.objects.delete()
    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()


@responses.activate
@mock.patch.object(LLMProcessor, "__collection_exists__", autospec=True)
@mock.patch.object(LLMProcessor, "__create_collection__", autospec=True)
@mock.patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
@mock.patch.object(MailUtility,"format_and_send_mail", autospec=True)
@mock.patch.object(MetaProcessor, "push_meta_catalog", autospec=True)
@mock.patch.object(MetaProcessor, "delete_meta_catalog", autospec=True)
@patch(
    "kairon.shared.actions.utils.ActionUtility.execute_request_async",
    new_callable=AsyncMock
)
def test_catalog_sync_push_menu_global_local_images_success(mock_embedding, mock_collection_exists, mock_create_collection,
                                        mock_collection_upsert, mock_format_and_send_mail, mock_delete_meta_catalog, mock_push_meta_catalog):
    mock_collection_exists.return_value = False
    mock_create_collection.return_value = None
    mock_collection_upsert.return_value = None
    mock_format_and_send_mail.return_value = None
    mock_push_meta_catalog.return_value = None
    mock_delete_meta_catalog.return_value = None

    embedding = list(np.random.random(LLMProcessor.__embedding__))
    embedding = [[0.1] * 3072, [0.1] * 3072, [0.1] * 3072]
    mock_embedding.return_value = (
        embedding,
        200,
        0.05,
        {}
    )
    LLMSecret.objects.delete()
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

    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
        },
        "meta_config": {
            "access_token": "dummy_access_token",
            "catalog_id": "12345"
        },
        "smart_catalog_enabled": True,
        "meta_enabled": True,
        "sync_options": {
            "process_push_menu": True,
            "process_item_toggle": False
        }
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=push_menu",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/push_menu" in actual["data"]
    assert str(pytest.bot) in actual["data"]
    sync_url = actual["data"]
    token = sync_url.split(str(pytest.bot) + "/")[1]

    provider_mapping = CatalogProviderMapping.objects(provider="petpooja").first()
    assert provider_mapping is not None
    assert provider_mapping.meta_mappings is not None
    assert provider_mapping.kv_mappings is not None

    pos_integration = POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").first()
    assert pos_integration is not None
    assert pos_integration.config["restaurant_id"] == "98765"
    assert pos_integration.meta_config["access_token"] == "dummy_access_token"

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.catalog_integration}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_images_collection = f"{restaurant_name}_{branch_name}_catalog_images"
    fallback_data = {
        "image_type": "global",
        "image_url": "https://picsum.photos/id/237/200/300",
        "image_base64": ""
    }
    CollectionData(
        collection_name=catalog_images_collection,
        data=fallback_data,
        user="integration@demo.ai",
        bot=pytest.bot,
        status=True,
        timestamp=utc_now()
    ).save()

    local_image_data = {
        "image_type": "local",
        "item_id": 10539634,
        "image_url": "https://picsum.photos/id/local/237/200/300",
        "image_base64": ""
    }
    CollectionData(
        collection_name=catalog_images_collection,
        data=local_image_data,
        user="integration@demo.ai",
        bot=pytest.bot,
        status=True,
        timestamp=utc_now()
    ).save()

    push_menu_payload_path = Path("tests/testing_data/catalog_sync/catalog_sync_push_menu_payload.json")

    with push_menu_payload_path.open("r", encoding="utf-8") as f:
        push_menu_payload = json.load(f)

    response = client.post(
        url=sync_url,
        json=push_menu_payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()
    assert actual["message"] == "Sync in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    sync_ref_id = str(latest_log.id)

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.catalog_integration, sync_type="push_menu", token=token,
        provider="petpooja", sync_ref_id = sync_ref_id
    )

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    assert latest_log is not None
    assert latest_log.execution_id
    assert latest_log.sync_status == EVENT_STATUS.COMPLETED.value
    assert latest_log.status == STATUSES.SUCCESS.value
    assert hasattr(latest_log, "exception")
    assert latest_log.exception == ""

    expected_id_image_map = {
        '10539634': 'https://picsum.photos/id/local/237/200/300',
        '10539699': 'https://picsum.photos/id/237/200/300',
        '10539580': 'https://picsum.photos/id/237/200/300'
    }
    latest_log_dict = latest_log.to_mongo().to_dict()
    meta_items = latest_log_dict["processed_payload"]["meta"]
    id_image_map = {item["id"]: item["image_url"] for item in meta_items}

    assert id_image_map == expected_id_image_map

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"
    catalog_data_docs = CollectionData.objects(collection_name=catalog_data_collection, bot=pytest.bot)
    catalog_item_summaries = [
        {"id": doc.data["kv"]["id"], "price": doc.data["kv"]["price"]}
        for doc in catalog_data_docs
    ]

    expected_items = [
        {"id": "10539634", "price": 8700.0},
        {"id": "10539699", "price": 3426.0},
        {"id": "10539580", "price": 3159.0},
    ]

    assert all(item in catalog_item_summaries for item in expected_items)

    cognition_data_docs = CognitionData.objects(bot=str(pytest.bot))
    cognition_map = {doc.data["id"]: doc.data["price"] for doc in cognition_data_docs if
                     "id" in doc.data and "price" in doc.data}
    for item in expected_items:
        assert item["id"] in cognition_map
        assert cognition_map[item["id"]] == item["price"]

    CatalogProviderMapping.objects(provider="petpooja").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").delete()
    LLMSecret.objects.delete()
    CollectionData.objects(collection_name=catalog_data_collection).delete()
    CollectionData.objects(collection_name=catalog_images_collection).delete()
    CatalogSyncLogs.objects.delete()
    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()


@responses.activate
@mock.patch.object(LLMProcessor, "__collection_exists__", autospec=True)
@mock.patch.object(LLMProcessor, "__create_collection__", autospec=True)
@mock.patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
@mock.patch.object(MailUtility,"format_and_send_mail", autospec=True)
@mock.patch.object(MetaProcessor, "push_meta_catalog", autospec=True)
@mock.patch.object(MetaProcessor, "delete_meta_catalog", autospec=True)
@patch(
    "kairon.shared.actions.utils.ActionUtility.execute_request_async",
    new_callable=AsyncMock
)
def test_catalog_rerun_sync_push_menu_success(mock_embedding, mock_collection_exists, mock_create_collection,
                                        mock_collection_upsert, mock_format_and_send_mail, mock_delete_meta_catalog, mock_push_meta_catalog):
    mock_collection_exists.return_value = False
    mock_create_collection.return_value = None
    mock_collection_upsert.return_value = None
    mock_format_and_send_mail.return_value = None
    mock_push_meta_catalog.return_value = None
    mock_delete_meta_catalog.return_value = None

    embedding = list(np.random.random(LLMProcessor.__embedding__))
    embedding = [[0.1] * 3072, [0.1] * 3072, [0.1] * 3072]
    mock_embedding.return_value = (
        embedding,
        200,
        0.05,
        {}
    )
    LLMSecret.objects.delete()
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

    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
        },
        "meta_config": {
            "access_token": "dummy_access_token",
            "catalog_id": "12345"
        },
        "smart_catalog_enabled": False,
        "meta_enabled": False,
        "sync_options": {
            "process_push_menu": False,
            "process_item_toggle": False
        }
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=push_menu",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/push_menu" in actual["data"]
    assert str(pytest.bot) in actual["data"]
    sync_url = actual["data"]
    token = sync_url.split(str(pytest.bot) + "/")[1]

    provider_mapping = CatalogProviderMapping.objects(provider="petpooja").first()
    assert provider_mapping is not None
    assert provider_mapping.meta_mappings is not None
    assert provider_mapping.kv_mappings is not None

    pos_integration = POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").first()
    assert pos_integration is not None
    assert pos_integration.config["restaurant_id"] == "98765"
    assert pos_integration.meta_config["access_token"] == "dummy_access_token"

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.catalog_integration}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    push_menu_payload_path = Path("tests/testing_data/catalog_sync/catalog_sync_push_menu_payload.json")

    with push_menu_payload_path.open("r", encoding="utf-8") as f:
        push_menu_payload = json.load(f)

    response = client.post(
        url=sync_url,
        json=push_menu_payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()
    assert actual["message"] == "Push menu processing is disabled for this bot"
    assert actual["error_code"] == 422
    assert not actual["success"]

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    assert latest_log is not None
    assert latest_log.execution_id
    assert latest_log.sync_status == "Failed"
    assert latest_log.status == STATUSES.FAIL.value
    assert hasattr(latest_log, "exception")
    assert latest_log.exception == "Push menu processing is disabled for this bot"
    rerun_execution_id = latest_log.execution_id

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"
    catalog_data_docs = CollectionData.objects(collection_name=catalog_data_collection, bot=pytest.bot)
    assert catalog_data_docs.count() == 0
    cognition_data_docs = CognitionData.objects(bot=str(pytest.bot))
    assert cognition_data_docs.count() == 0

    integration_docs = POSIntegrations.objects(bot=pytest.bot, provider="petpooja")

    for doc in integration_docs:
        doc.smart_catalog_enabled = True
        doc.meta_enabled = True
        doc.sync_options["process_push_menu"] = True
        doc.sync_options["process_item_toggle"] = True
        doc.save()

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_images_collection = f"{restaurant_name}_{branch_name}_catalog_images"
    fallback_data = {
        "image_type": "global",
        "image_url": "https://picsum.photos/id/237/200/300",
        "image_base64": ""
    }
    CollectionData(
        collection_name=catalog_images_collection,
        data=fallback_data,
        user="integration@demo.ai",
        bot=pytest.bot,
        status=True,
        timestamp=utc_now()
    ).save()

    rerun_sync_url = f"{sync_url}/{rerun_execution_id}"

    response = client.post(
        url=rerun_sync_url,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()
    assert actual["message"] == "Sync in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    sync_ref_id = str(latest_log.id)

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.catalog_integration, sync_type="push_menu", token=token,
        provider="petpooja", sync_ref_id = sync_ref_id
    )

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    assert latest_log is not None
    assert latest_log.execution_id
    assert latest_log.sync_status == EVENT_STATUS.COMPLETED.value
    assert latest_log.status == STATUSES.SUCCESS.value
    assert hasattr(latest_log, "exception")
    assert latest_log.exception == ""

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"
    catalog_data_docs = CollectionData.objects(collection_name=catalog_data_collection, bot=pytest.bot)
    catalog_item_summaries = [
        {"id": doc.data["kv"]["id"], "price": doc.data["kv"]["price"]}
        for doc in catalog_data_docs
    ]

    expected_items = [
        {"id": "10539634", "price": 8700.0},
        {"id": "10539699", "price": 3426.0},
        {"id": "10539580", "price": 3159.0},
    ]

    assert all(item in catalog_item_summaries for item in expected_items)

    cognition_data_docs = CognitionData.objects(bot=str(pytest.bot))
    cognition_map = {doc.data["id"]: doc.data["price"] for doc in cognition_data_docs if
                     "id" in doc.data and "price" in doc.data}
    for item in expected_items:
        assert item["id"] in cognition_map
        assert cognition_map[item["id"]] == item["price"]

    CatalogProviderMapping.objects(provider="petpooja").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").delete()
    LLMSecret.objects.delete()
    CollectionData.objects(collection_name=catalog_data_collection).delete()
    CollectionData.objects(collection_name=catalog_images_collection).delete()
    CatalogSyncLogs.objects.delete()
    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()

@responses.activate
@mock.patch.object(LLMProcessor, "__collection_exists__", autospec=True)
@mock.patch.object(LLMProcessor, "__create_collection__", autospec=True)
@mock.patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
@mock.patch.object(MailUtility,"format_and_send_mail", autospec=True)
@mock.patch.object(MetaProcessor, "push_meta_catalog", autospec=True)
@mock.patch.object(MetaProcessor, "delete_meta_catalog", autospec=True)
@patch(
    "kairon.shared.actions.utils.ActionUtility.execute_request_async",
    new_callable=AsyncMock
)
def test_catalog_sync_missing_sync_ref_id(mock_embedding, mock_collection_exists, mock_create_collection,
                                        mock_collection_upsert, mock_format_and_send_mail, mock_delete_meta_catalog, mock_push_meta_catalog):
    mock_collection_exists.return_value = False
    mock_create_collection.return_value = None
    mock_collection_upsert.return_value = None
    mock_format_and_send_mail.return_value = None
    mock_push_meta_catalog.return_value = None
    mock_delete_meta_catalog.return_value = None

    embedding = list(np.random.random(LLMProcessor.__embedding__))
    embedding = [[0.1] * 3072, [0.1] * 3072, [0.1] * 3072]
    mock_embedding.return_value = (
        embedding,
        200,
        0.05,
        {}
    )
    LLMSecret.objects.delete()
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

    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
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

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=push_menu",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/push_menu" in actual["data"]
    assert str(pytest.bot) in actual["data"]
    sync_url = actual["data"]
    token = sync_url.split(str(pytest.bot) + "/")[1]

    provider_mapping = CatalogProviderMapping.objects(provider="petpooja").first()
    assert provider_mapping is not None
    assert provider_mapping.meta_mappings is not None
    assert provider_mapping.kv_mappings is not None

    pos_integration = POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").first()
    assert pos_integration is not None
    assert pos_integration.config["restaurant_id"] == "98765"
    assert pos_integration.meta_config["access_token"] == "dummy_access_token"

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.catalog_integration}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_images_collection = f"{restaurant_name}_{branch_name}_catalog_images"
    fallback_data = {
        "image_type": "global",
        "image_url": "https://picsum.photos/id/237/200/300",
        "image_base64": ""
    }
    CollectionData(
        collection_name=catalog_images_collection,
        data=fallback_data,
        user="integration@demo.ai",
        bot=pytest.bot,
        status=True,
        timestamp=utc_now()
    ).save()

    push_menu_payload_path = Path("tests/testing_data/catalog_sync/catalog_sync_push_menu_payload.json")

    with push_menu_payload_path.open("r", encoding="utf-8") as f:
        push_menu_payload = json.load(f)

    response = client.post(
        url=sync_url,
        json=push_menu_payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()
    assert actual["message"] == "Sync in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    sync_ref_id = str(latest_log.id)

    with pytest.raises(ValueError, match="Missing sync_ref_id in event payload"):
        complete_end_to_end_event_execution(
            pytest.bot, "integration@demo.ai", EventClass.catalog_integration, sync_type="push_menu", token = token,
            provider = "petpooja", sync_ref_id = ""
        )

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"

    CatalogProviderMapping.objects(provider="petpooja").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="item_toggle").delete()
    LLMSecret.objects.delete()
    CollectionData.objects(collection_name=catalog_data_collection).delete()
    CollectionData.objects(collection_name=catalog_images_collection).delete()
    CatalogSyncLogs.objects.delete()
    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()

@responses.activate
@mock.patch.object(LLMProcessor, "__collection_exists__", autospec=True)
@mock.patch.object(LLMProcessor, "__create_collection__", autospec=True)
@mock.patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
@mock.patch.object(MailUtility,"format_and_send_mail", autospec=True)
@mock.patch.object(MetaProcessor, "push_meta_catalog", autospec=True)
@mock.patch.object(MetaProcessor, "delete_meta_catalog", autospec=True)
@patch(
    "kairon.shared.actions.utils.ActionUtility.execute_request_async",
    new_callable=AsyncMock
)
def test_catalog_sync_validation_errors_exist(mock_embedding, mock_collection_exists, mock_create_collection,
                                        mock_collection_upsert, mock_format_and_send_mail, mock_delete_meta_catalog, mock_push_meta_catalog):
    mock_collection_exists.return_value = False
    mock_create_collection.return_value = None
    mock_collection_upsert.return_value = None
    mock_format_and_send_mail.return_value = None
    mock_push_meta_catalog.return_value = None
    mock_delete_meta_catalog.return_value = None

    embedding = list(np.random.random(LLMProcessor.__embedding__))
    embedding = [[0.1] * 3072, [0.1] * 3072, [0.1] * 3072]
    mock_embedding.return_value = (
        embedding,
        200,
        0.05,
        {}
    )
    LLMSecret.objects.delete()
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

    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
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

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=push_menu",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/push_menu" in actual["data"]
    assert str(pytest.bot) in actual["data"]
    sync_url = actual["data"]
    token = sync_url.split(str(pytest.bot) + "/")[1]

    provider_mapping = CatalogProviderMapping.objects(provider="petpooja").first()
    assert provider_mapping is not None
    assert provider_mapping.meta_mappings is not None
    assert provider_mapping.kv_mappings is not None

    pos_integration = POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").first()
    assert pos_integration is not None
    assert pos_integration.config["restaurant_id"] == "98765"
    assert pos_integration.meta_config["access_token"] == "dummy_access_token"

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.catalog_integration}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_images_collection = f"{restaurant_name}_{branch_name}_catalog_images"
    fallback_data = {
        "image_type": "global",
        "image_url": "https://picsum.photos/id/237/200/300",
        "image_base64": ""
    }
    CollectionData(
        collection_name=catalog_images_collection,
        data=fallback_data,
        user="integration@demo.ai",
        bot=pytest.bot,
        status=True,
        timestamp=utc_now()
    ).save()

    push_menu_validation_errors_payload_path = Path("tests/testing_data/catalog_sync/catalog_sync_push_menu_validation_errors.json")

    with push_menu_validation_errors_payload_path.open("r", encoding="utf-8") as f:
        push_menu_validation_errors_payload = json.load(f)

    response = client.post(
        url=sync_url,
        json=push_menu_validation_errors_payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()
    assert actual["message"] == "Sync in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    sync_ref_id = str(latest_log.id)

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.catalog_integration, sync_type="push_menu", token = token,
        provider = "petpooja", sync_ref_id = sync_ref_id
    )

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    assert latest_log.sync_status == "Failed"
    assert latest_log.status == STATUSES.FAIL.value

    assert latest_log.validation_errors is not None
    assert "10539634" in latest_log.validation_errors
    assert latest_log.validation_errors["10539634"][0]["column_name"] == "title"
    assert latest_log.validation_errors["10539634"][0]["input"] == 45
    assert latest_log.validation_errors["10539634"][0]["status"] == "Invalid DataType"

    assert "Validation Failed. Check logs" in latest_log.exception

    cognition_data_docs = CognitionData.objects(bot=str(pytest.bot)).count()
    assert cognition_data_docs == 0

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"

    CatalogProviderMapping.objects(provider="petpooja").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="item_toggle").delete()
    LLMSecret.objects.delete()
    CollectionData.objects(collection_name=catalog_data_collection).delete()
    CollectionData.objects(collection_name=catalog_images_collection).delete()
    CatalogSyncLogs.objects.delete()
    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()


@responses.activate
@mock.patch.object(LLMProcessor, "__collection_exists__", autospec=True)
@mock.patch.object(LLMProcessor, "__create_collection__", autospec=True)
@mock.patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
@mock.patch.object(MailUtility,"format_and_send_mail", autospec=True)
@mock.patch.object(MetaProcessor, "push_meta_catalog", autospec=True)
@mock.patch.object(MetaProcessor, "delete_meta_catalog", autospec=True)
@mock.patch.object(CognitionDataProcessor, "preprocess_push_menu_data", side_effect=Exception("Simulated preprocess error"))
@patch(
    "kairon.shared.actions.utils.ActionUtility.execute_request_async",
    new_callable=AsyncMock
)
def test_catalog_sync_preprocess_exception(mock_embedding, mock_preprocess, mock_collection_exists, mock_create_collection,
                                        mock_collection_upsert, mock_format_and_send_mail, mock_delete_meta_catalog, mock_push_meta_catalog):
    mock_collection_exists.return_value = False
    mock_create_collection.return_value = None
    mock_collection_upsert.return_value = None
    mock_format_and_send_mail.return_value = None
    mock_push_meta_catalog.return_value = None
    mock_delete_meta_catalog.return_value = None

    embedding = list(np.random.random(LLMProcessor.__embedding__))
    embedding = [[0.1] * 3072, [0.1] * 3072, [0.1] * 3072]
    mock_embedding.return_value = (
        embedding,
        200,
        0.05,
        {}
    )
    LLMSecret.objects.delete()
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

    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
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

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=push_menu",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/push_menu" in actual["data"]
    assert str(pytest.bot) in actual["data"]
    sync_url = actual["data"]
    token = sync_url.split(str(pytest.bot) + "/")[1]

    provider_mapping = CatalogProviderMapping.objects(provider="petpooja").first()
    assert provider_mapping is not None
    assert provider_mapping.meta_mappings is not None
    assert provider_mapping.kv_mappings is not None

    pos_integration = POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").first()
    assert pos_integration is not None
    assert pos_integration.config["restaurant_id"] == "98765"
    assert pos_integration.meta_config["access_token"] == "dummy_access_token"

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.catalog_integration}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_images_collection = f"{restaurant_name}_{branch_name}_catalog_images"
    fallback_data = {
        "image_type": "global",
        "image_url": "https://picsum.photos/id/237/200/300",
        "image_base64": ""
    }
    CollectionData(
        collection_name=catalog_images_collection,
        data=fallback_data,
        user="integration@demo.ai",
        bot=pytest.bot,
        status=True,
        timestamp=utc_now()
    ).save()

    push_menu_validation_errors_payload_path = Path("tests/testing_data/catalog_sync/catalog_sync_push_menu_validation_errors.json")

    with push_menu_validation_errors_payload_path.open("r", encoding="utf-8") as f:
        push_menu_validation_errors_payload = json.load(f)

    response = client.post(
        url=sync_url,
        json=push_menu_validation_errors_payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()
    assert actual["message"] == "Sync in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    sync_ref_id = str(latest_log.id)

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.catalog_integration, sync_type="push_menu", token = token,
        provider = "petpooja", sync_ref_id = sync_ref_id
    )

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    assert latest_log.sync_status == "Failed"
    assert latest_log.status == STATUSES.FAIL.value
    assert "Simulated preprocess error" in latest_log.exception

    assert not latest_log.processed_payload

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"

    CatalogProviderMapping.objects(provider="petpooja").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="item_toggle").delete()
    LLMSecret.objects.delete()
    CollectionData.objects(collection_name=catalog_data_collection).delete()
    CollectionData.objects(collection_name=catalog_images_collection).delete()
    CatalogSyncLogs.objects.delete()
    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()


@responses.activate
@mock.patch.object(LLMProcessor, "__collection_exists__", autospec=True)
@mock.patch.object(LLMProcessor, "__create_collection__", autospec=True)
@mock.patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
@mock.patch.object(MailUtility,"format_and_send_mail", autospec=True)
@mock.patch.object(MetaProcessor, "push_meta_catalog", autospec=True)
@mock.patch.object(MetaProcessor, "delete_meta_catalog", autospec=True)
@patch(
    "kairon.shared.actions.utils.ActionUtility.execute_request_async",
    new_callable=AsyncMock
)
def test_catalog_sync_push_menu_sync_already_in_progress(mock_embedding, mock_collection_exists, mock_create_collection,
                                        mock_collection_upsert, mock_format_and_send_mail, mock_delete_meta_catalog, mock_push_meta_catalog):

    mock_collection_exists.return_value = False
    mock_create_collection.return_value = None
    mock_collection_upsert.return_value = None
    mock_format_and_send_mail.return_value = None
    mock_push_meta_catalog.return_value = None
    mock_delete_meta_catalog.return_value = None

    embedding = list(np.random.random(LLMProcessor.__embedding__))
    embedding = [[0.1] * 3072, [0.1] * 3072, [0.1] * 3072]
    mock_embedding.return_value = (
        embedding,
        200,
        0.05,
        {}
    )
    LLMSecret.objects.delete()
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

    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
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

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=push_menu",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/push_menu" in actual["data"]
    assert str(pytest.bot) in actual["data"]
    sync_url = actual["data"]
    token = sync_url.split(str(pytest.bot) + "/")[1]

    provider_mapping = CatalogProviderMapping.objects(provider="petpooja").first()
    assert provider_mapping is not None
    assert provider_mapping.meta_mappings is not None
    assert provider_mapping.kv_mappings is not None

    pos_integration = POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").first()
    assert pos_integration is not None
    assert pos_integration.config["restaurant_id"] == "98765"
    assert pos_integration.meta_config["access_token"] == "dummy_access_token"

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.catalog_integration}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_images_collection = f"{restaurant_name}_{branch_name}_catalog_images"
    fallback_data = {
        "image_type": "global",
        "image_url": "https://picsum.photos/id/237/200/300",
        "image_base64": ""
    }
    CollectionData(
        collection_name=catalog_images_collection,
        data=fallback_data,
        user="integration@demo.ai",
        bot=pytest.bot,
        status=True,
        timestamp=utc_now()
    ).save()

    CatalogSyncLogs(
        execution_id=str(ObjectId()),
        raw_payload={"test":"test"},
        processed_payload={},
        validation_errors={},
        bot=pytest.bot,
        user="test_user",
        provider="petpooja",
        sync_type="push_menu",
        start_timestamp=utc_now(),
        sync_status="Initiated",
        status=EVENT_STATUS.INPROGRESS.value
    ).save()

    push_menu_payload_path = Path("tests/testing_data/catalog_sync/catalog_sync_push_menu_payload.json")

    with push_menu_payload_path.open("r", encoding="utf-8") as f:
        push_menu_payload = json.load(f)

    response  = client.post(
        url=sync_url,
        json=push_menu_payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "Sync already in progress! Check logs."
    assert actual["error_code"] == 422
    assert not actual["success"]

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"

    CatalogProviderMapping.objects(provider="petpooja").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="item_toggle").delete()
    LLMSecret.objects.delete()
    CollectionData.objects(collection_name=catalog_data_collection).delete()
    CollectionData.objects(collection_name=catalog_images_collection).delete()
    CatalogSyncLogs.objects.delete()
    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()

@responses.activate
@mock.patch.object(LLMProcessor, "__collection_exists__", autospec=True)
@mock.patch.object(LLMProcessor, "__create_collection__", autospec=True)
@mock.patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
@mock.patch.object(MailUtility,"format_and_send_mail", autospec=True)
@mock.patch.object(MetaProcessor, "push_meta_catalog", autospec=True)
@mock.patch.object(MetaProcessor, "delete_meta_catalog", autospec=True)
@patch(
    "kairon.shared.actions.utils.ActionUtility.execute_request_async",
    new_callable=AsyncMock
)
def test_catalog_sync_push_menu_daily_limit_exceeded(mock_embedding, mock_collection_exists, mock_create_collection,
                                        mock_collection_upsert, mock_format_and_send_mail, mock_delete_meta_catalog, mock_push_meta_catalog):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.catalog_sync_limit_per_day = 0
    bot_settings.save()

    mock_collection_exists.return_value = False
    mock_create_collection.return_value = None
    mock_collection_upsert.return_value = None
    mock_format_and_send_mail.return_value = None
    mock_push_meta_catalog.return_value = None
    mock_delete_meta_catalog.return_value = None

    embedding = list(np.random.random(LLMProcessor.__embedding__))
    embedding = [[0.1] * 3072, [0.1] * 3072, [0.1] * 3072]
    mock_embedding.return_value = (
        embedding,
        200,
        0.05,
        {}
    )
    LLMSecret.objects.delete()
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

    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
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

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=push_menu",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/push_menu" in actual["data"]
    assert str(pytest.bot) in actual["data"]
    sync_url = actual["data"]
    token = sync_url.split(str(pytest.bot) + "/")[1]

    provider_mapping = CatalogProviderMapping.objects(provider="petpooja").first()
    assert provider_mapping is not None
    assert provider_mapping.meta_mappings is not None
    assert provider_mapping.kv_mappings is not None

    pos_integration = POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").first()
    assert pos_integration is not None
    assert pos_integration.config["restaurant_id"] == "98765"
    assert pos_integration.meta_config["access_token"] == "dummy_access_token"

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.catalog_integration}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_images_collection = f"{restaurant_name}_{branch_name}_catalog_images"
    fallback_data = {
        "image_type": "global",
        "image_url": "https://picsum.photos/id/237/200/300",
        "image_base64": ""
    }
    CollectionData(
        collection_name=catalog_images_collection,
        data=fallback_data,
        user="integration@demo.ai",
        bot=pytest.bot,
        status=True,
        timestamp=utc_now()
    ).save()

    push_menu_payload_path = Path("tests/testing_data/catalog_sync/catalog_sync_push_menu_payload.json")

    with push_menu_payload_path.open("r", encoding="utf-8") as f:
        push_menu_payload = json.load(f)

    response  = client.post(
        url=sync_url,
        json=push_menu_payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "Daily limit exceeded."
    assert actual["error_code"] == 422
    assert not actual["success"]

    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.catalog_sync_limit_per_day = 5
    bot_settings.save()

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"

    CatalogProviderMapping.objects(provider="petpooja").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="item_toggle").delete()
    LLMSecret.objects.delete()
    CollectionData.objects(collection_name=catalog_data_collection).delete()
    CollectionData.objects(collection_name=catalog_images_collection).delete()
    CatalogSyncLogs.objects.delete()
    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()

@responses.activate
@mock.patch.object(LLMProcessor, "__collection_exists__", autospec=True)
@mock.patch.object(LLMProcessor, "__create_collection__", autospec=True)
@mock.patch.object(LLMProcessor, "__collection_upsert__", autospec=True)
@mock.patch.object(MailUtility,"format_and_send_mail", autospec=True)
@mock.patch.object(MetaProcessor, "push_meta_catalog", autospec=True)
@mock.patch.object(MetaProcessor, "delete_meta_catalog", autospec=True)
@patch(
    "kairon.shared.actions.utils.ActionUtility.execute_request_async",
    new_callable=AsyncMock
)
def test_catalog_sync_push_menu_smart_catalog_disabled_meta_enabled_with_validation_errors(mock_embedding, mock_collection_exists, mock_create_collection,
                                        mock_collection_upsert, mock_format_and_send_mail, mock_delete_meta_catalog, mock_push_meta_catalog):
    mock_collection_exists.return_value = False
    mock_create_collection.return_value = None
    mock_collection_upsert.return_value = None
    mock_format_and_send_mail.return_value = None
    mock_push_meta_catalog.return_value = None
    mock_delete_meta_catalog.return_value = None

    embedding = list(np.random.random(LLMProcessor.__embedding__))
    embedding = [[0.1] * 3072, [0.1] * 3072, [0.1] * 3072]
    mock_embedding.return_value = (
        embedding,
        200,
        0.05,
        {}
    )
    LLMSecret.objects.delete()
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

    payload = {
        "connector_type": "petpooja",
        "config": {
            "restaurant_name": "restaurant1",
            "branch_name": "branch1",
            "restaurant_id": "98765"
        },
        "meta_config": {
            "access_token": "dummy_access_token",
            "catalog_id": "12345"
        },
        "smart_catalog_enabled": False,
        "meta_enabled": True,
        "sync_options": {
            "process_push_menu": True,
            "process_item_toggle": False
        }
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/integrations/add?sync_type=push_menu",
        json = payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "POS Integration Complete"
    assert actual["error_code"] == 0
    assert actual["success"]
    assert "integration/petpooja/push_menu" in actual["data"]
    assert str(pytest.bot) in actual["data"]
    sync_url = actual["data"]
    token = sync_url.split(str(pytest.bot) + "/")[1]

    provider_mapping = CatalogProviderMapping.objects(provider="petpooja").first()
    assert provider_mapping is not None
    assert provider_mapping.meta_mappings is not None
    assert provider_mapping.kv_mappings is not None

    pos_integration = POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").first()
    assert pos_integration is not None
    assert pos_integration.config["restaurant_id"] == "98765"
    assert pos_integration.meta_config["access_token"] == "dummy_access_token"

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.catalog_integration}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_images_collection = f"{restaurant_name}_{branch_name}_catalog_images"
    fallback_data = {
        "image_type": "global",
        "image_url": "https://picsum.photos/id/237/200/300",
        "image_base64": ""
    }
    CollectionData(
        collection_name=catalog_images_collection,
        data=fallback_data,
        user="integration@demo.ai",
        bot=pytest.bot,
        status=True,
        timestamp=utc_now()
    ).save()

    push_menu_validation_errors_payload_path = Path(
        "tests/testing_data/catalog_sync/catalog_sync_push_menu_validation_errors.json")

    with push_menu_validation_errors_payload_path.open("r", encoding="utf-8") as f:
        push_menu_validation_errors_payload = json.load(f)

    response = client.post(
        url=sync_url,
        json=push_menu_validation_errors_payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "Sync in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    sync_ref_id = str(latest_log.id)

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.catalog_integration, sync_type="push_menu", token=token,
        provider="petpooja", sync_ref_id = sync_ref_id
    )

    latest_log = CatalogSyncLogs.objects(bot=str(pytest.bot)).order_by("-start_timestamp").first()
    assert latest_log is not None
    assert latest_log.execution_id
    assert latest_log.sync_status == "Failed"
    assert latest_log.status == STATUSES.FAIL.value
    assert hasattr(latest_log, "exception")
    assert latest_log.exception == "Validation Failed. Check logs"

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"
    catalog_data_docs = CollectionData.objects(collection_name=catalog_data_collection, bot=pytest.bot)
    assert catalog_data_docs.count() == 0

    cognition_data_docs = CognitionData.objects(bot=str(pytest.bot))
    assert cognition_data_docs.count() == 0

    mock_push_meta_catalog.assert_not_called()

    restaurant_name, branch_name = CognitionDataProcessor.get_restaurant_and_branch_name(pytest.bot)
    catalog_data_collection = f"{restaurant_name}_{branch_name}_catalog_data"

    CatalogProviderMapping.objects(provider="petpooja").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="push_menu").delete()
    POSIntegrations.objects(bot=pytest.bot, provider="petpooja", sync_type="item_toggle").delete()
    LLMSecret.objects.delete()
    CollectionData.objects(collection_name=catalog_data_collection).delete()
    CollectionData.objects(collection_name=catalog_images_collection).delete()
    CatalogSyncLogs.objects.delete()
    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()

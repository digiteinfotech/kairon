from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training




def test_get_client_name_with_no_configuration():
    response = client.get(
        f"/api/bot/{pytest.bot}/pos/odoo/client_name",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert not actual["success"]
    assert not actual["data"]
    assert actual["message"] == 'No POS client configuration found for this bot.'
    assert actual["error_code"] == 422


def test_pos_register_pos_not_enabled():
    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/register",
        json={"client_name": "Test Client"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "point of sale is not enabled"
    assert not actual["data"]
    assert actual["error_code"] == 422


@responses.activate
def test_pos_register_with_client_name_exists():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.pos_enabled = True
    bot_settings.save()

    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    jsonrpc = f"{base}/jsonrpc"
    auth = f"{base}/web/session/authenticate"
    call_kw = re.compile(f"{base}/web/dataset/call_kw")

    responses.add(responses.POST, jsonrpc, json={"result": ["Test Client", "Kairon Client"]}, status=200)

    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/register",
        json={"client_name": "Test Client"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert not actual["success"]
    assert actual["message"] == "Client Test Client already exists"
    assert not actual["data"]
    assert actual["error_code"] == 422


@responses.activate
def test_pos_register():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.pos_enabled = True
    bot_settings.save()

    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    jsonrpc = f"{base}/jsonrpc"
    auth = f"{base}/web/session/authenticate"
    call_kw = re.compile(f"{base}/web/dataset/call_kw")

    responses.add(responses.POST, jsonrpc, json={"result": ["Kairon Client"]}, status=200)
    responses.add(responses.POST, auth, json={"result": {"uid": 1}},
                  headers={"Set-Cookie": "session_id=fake-session-id-123; Path=/;"}, status=200)

    responses.add(responses.POST, call_kw, json={"result": True}, status=200,)
    responses.add(responses.POST, call_kw, json={"result": [10]}, status=200,)
    responses.add(responses.POST, call_kw, json={"result": [{"state": "to install"}]}, status=200,)
    responses.add(responses.POST, call_kw, json={"result": True}, status=200,)
    responses.add(responses.POST, call_kw, json={"result": [20]}, status=200,)
    responses.add(responses.POST, call_kw, json={"result": [{"state": "to install"}]}, status=200,)
    responses.add(responses.POST, call_kw, json={"result": True}, status=200,)

    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/register",
        json={"client_name": "Test Client"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert actual["success"]
    assert actual["data"]["message"] == "Client 'Test Client' created and POS Activated"
    assert actual["error_code"] == 0


def test_pos_login_pos_not_enabled():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.pos_enabled = False
    bot_settings.save()
    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/login",
        json={"client_name": "Test Client"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "point of sale is not enabled"
    assert not actual["data"]
    assert actual["error_code"] == 422


@responses.activate
def test_pos_login_with_page_type_pos_orders():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.pos_enabled = True
    bot_settings.save()

    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    auth = f"{base}/web/session/authenticate"

    responses.add(responses.POST, auth, json={"result": {"uid": 1}},
                  headers={"Set-Cookie": "session_id=fake-session-id-123; Path=/;"}, status=200)

    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/login",
        json={"client_name": "Test Client", "page_type": "pos_orders"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert actual["uid"] == 1
    assert actual["session_id"] == "fake-session-id-123"
    assert actual["url"] == 'http://localhost:8080/web#action=380&model=pos.order&view_type=list&cids=1&menu_id=231'


@responses.activate
def test_pos_login():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.pos_enabled = True
    bot_settings.save()

    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    auth = f"{base}/web/session/authenticate"

    responses.add(responses.POST, auth, json={"result": {"uid": 1}},
                  headers={"Set-Cookie": "session_id=fake-session-id-123; Path=/;"}, status=200)

    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/login",
        json={"client_name": "Test Client"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert actual["uid"] == 1
    assert actual["session_id"] == "fake-session-id-123"
    pytest.session_id = actual["session_id"]
    assert actual["url"] == 'http://localhost:8080/web#action=388&model=product.template&view_type=kanban&cids=1&menu_id=233'

@responses.activate
def test_pos_login_with_cid():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.pos_enabled = True
    bot_settings.save()

    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    auth = f"{base}/web/session/authenticate"

    responses.add(responses.POST, auth, json={"result": {"uid": 1}},
                  headers={"Set-Cookie": "session_id=fake-session-id-123; Path=/;"}, status=200)

    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/login",
        json={"client_name": "Test Client", "company_id": 2},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert actual["uid"] == 1
    assert actual["session_id"] == "fake-session-id-123"
    pytest.session_id = actual["session_id"]
    assert actual["url"] == 'http://localhost:8080/web#action=388&model=product.template&view_type=kanban&cids=2&menu_id=233'


def test_create_branch():
    with patch("kairon.shared.pos.processor.POSProcessor.create_branch") as mock_create_branch:
        mock_create_branch.return_value = {
            "name": "Test branch"
        }

        payload = {
            "branch_name": "Test branch",
            "street": "Andheri East",
            "city": "Mumbai",
            "state": "Maharashtra"
        }

        session_id = "dummy_session_id"

        # Act
        response = client.post(
            url=f"/api/bot/{pytest.bot}/pos/odoo/create/branch?session_id={session_id}",
            json=payload,
            headers={
                "Authorization": pytest.token_type + " " + pytest.access_token
            },
        )

        actual = response.json()

        # Assert
        assert response.status_code == 200
        assert actual["message"] == "Branch created"
        assert actual["data"] == {
            "name": "Test branch"
        }

        mock_create_branch.assert_called_once_with(
            session_id=session_id,
            branch_name="Test branch",
            street="Andheri East",
            city="Mumbai",
            state="Maharashtra",
            bot=pytest.bot,
            user='integration@demo.ai'
        )


@pytest.mark.asyncio
async def test_vector_data_insertion_full_flow():
    """
    Test the full flow from API to upsert_vector_data,
    ensuring stale data deletion and metadata handling.
    """
    import uuid

    LLMSecret.objects.delete()
    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()


    schema_meta = SchemaMetadata(training_needed=False, model_id="text-embedding-3-large", size=3072)

    schema = CognitionSchema(
        collection_name="groceries",
        bot=pytest.bot,
        user="test_user",
        metadata=[
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
        ],
        schema_metadata=schema_meta
    )
    schema.save()

    LLMSecret(
        llm_type="openrouter",
        api_key="sk-test-key",
        user="test_user",
        models=["gpt-4o", "gpt-4"],
        timestamp=utc_now()
    ).save()
    LLMSecret(
        llm_type="openai",
        api_key="sk-test-key-2",
        user="test_user",
        models=["gpt-4o", "gpt-4"],
        timestamp=utc_now()
    ).save()

    stale_vector_id = str(uuid.uuid4())
    CognitionData(
        data={"id": 99, "item": "Old Milk"},
        vector_id=stale_vector_id,
        content_type="json",
        collection="groceries",
        bot=pytest.bot,
        user="test_user"
    ).save()

    with mock.patch("kairon.shared.actions.utils.ActionUtility.execute_request_async",
                    new_callable=AsyncMock) as mock_exe, \
            mock.patch("kairon.shared.llm.processor.LLMProcessor.__collection_exists__",
                       new_callable=AsyncMock) as mock_exists, \
            mock.patch("kairon.shared.llm.processor.LLMProcessor.__collection_upsert__",
                       new_callable=AsyncMock) as mock_upsert, \
            mock.patch("kairon.shared.llm.processor.LLMProcessor.__delete_collection_points__",
                       new_callable=AsyncMock) as mock_delete:
        mock_exe.return_value = ([[0.1] * 3072], 200, 0.01, {})
        mock_exists.return_value = True
        mock_upsert.return_value = None
        mock_delete.return_value = None

        sync_data = [{"id": 1, "item": "Apple"}]

        response = client.post(
            url=f"/api/bot/{pytest.bot}/data/vector/insert?primary_key_col=id&collection_name=groceries",
            json=sync_data,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token}
        )

        res_json = response.json()
        print(res_json)
        assert res_json["success"] is True
        assert res_json["message"] == "Processing completed successfully"

        assert CognitionData.objects(bot=pytest.bot, collection="groceries").count() == 1
        assert CognitionData.objects(bot=pytest.bot, data__id=1).first() is not None
        assert CognitionData.objects(bot=pytest.bot, data__id=99).first() is None

        mock_delete.assert_called_once()
        assert stale_vector_id in mock_delete.call_args[0][1]

        assert mock_upsert.called
    CognitionData.objects(bot=pytest.bot, collection="groceries",).delete()
    CognitionSchema.objects(bot=pytest.bot, collection_name="groceries",).delete()
    LLMSecret.objects.delete()

def test_get_client_name_and_branch():
    with patch("kairon.shared.pos.processor.POSProcessor.get_client_details") as mock_get_client_details:
        mock_get_client_details.return_value = {
            "client_name": "Demo Client",
            "branches": [
                {
                    "branch_name": "Mumbai Branch",
                    "company_id": 10
                },
                {
                    "branch_name": "Pune Branch",
                    "company_id": 11
                }
            ]
        }

        response = client.get(
            url=f"/api/bot/{pytest.bot}/pos/odoo/client_name",
            headers={
                "Authorization": pytest.token_type + " " + pytest.access_token
            },
        )

        actual = response.json()

        assert response.status_code == 200
        assert actual["data"] == {
            "client_name": "Demo Client",
            "branches": [
                {
                    "branch_name": "Mumbai Branch",
                    "company_id": 10
                },
                {
                    "branch_name": "Pune Branch",
                    "company_id": 11
                }
            ]
        }

        mock_get_client_details.assert_called_once_with(pytest.bot)

def test_create_branch_failure():
    with patch("kairon.shared.pos.processor.POSProcessor.create_branch") as mock_create_branch:
        mock_create_branch.side_effect = HTTPException(
            status_code=404,
            detail="Error in creating branch"
        )

        payload = {
            "branch_name": "Test branch",
            "street": "Andheri East",
            "city": "Mumbai",
            "state": "Maharashtra"
        }

        session_id = "dummy_session_id"

        response = client.post(
            url=f"/api/bot/{pytest.bot}/pos/odoo/create/branch?session_id={session_id}",
            json=payload,
            headers={
                "Authorization": pytest.token_type + " " + pytest.access_token
            },
        )

        actual = response.json()
        assert actual["message"] == "Error in creating branch"

def test_get_client_name():
    response = client.get(
        f"/api/bot/{pytest.bot}/pos/odoo/client_name",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert actual["success"]
    assert not actual["message"]
    assert actual["data"] == {'client_name': 'Test Client', 'branches': []}
    assert actual["error_code"] == 0


@responses.activate
def test_delete_client_without_client():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    jsonrpc = f"{base}/jsonrpc"

    responses.add(responses.POST, jsonrpc, json={"result": ["Kairon Client"]}, status=200)
    responses.add(responses.POST, jsonrpc, json={"result": True}, status=200)

    response = client.request(
        "DELETE",
        f"/api/bot/{pytest.bot}/pos/odoo/client/delete",
        json={"client_name": "Test Client"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Client 'Test Client' not found"
    assert not actual["data"]
    assert actual["error_code"] == 400


@responses.activate
def test_delete_client():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    jsonrpc = f"{base}/jsonrpc"

    responses.add(responses.POST, jsonrpc, json={"result": ["Kairon Client", "Test Client"]}, status=200)
    responses.add(responses.POST, jsonrpc, json={"result": True}, status=200)

    response = client.request(
        "DELETE",
        f"/api/bot/{pytest.bot}/pos/odoo/client/delete",
        json={"client_name": "Test Client"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert actual["success"]
    assert actual["data"]["message"] == "Client 'Test Client' deleted successfully"
    assert actual["error_code"] == 0


@responses.activate
def test_toggle_product():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/dataset/call_kw"

    product_id = 1
    responses.add(
        responses.POST,
        url,
        json={"result": [{
            "id": product_id,
            "name": "Test Product",
            "available_in_pos": False
        }]},
        status=200
    )
    responses.add(
        responses.POST,
        url,
        json={"result": True},
        status=200
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/toggle_product/1?session_id={pytest.session_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert actual["success"]
    assert actual["data"]["product_id"] == 1
    assert actual["data"]["name"] == "Test Product"
    assert actual["data"]["available_in_pos"] is True
    assert actual["message"] == "Product toggled to ON"
    assert actual["error_code"] == 0


@responses.activate
def test_toggle_product_write_failure():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/dataset/call_kw"

    product_id = 1

    responses.add(
        responses.POST,
        url,
        json={"result": [{
            "id": product_id,
            "name": "Faulty Product",
            "available_in_pos": True
        }]},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        body=Exception("Simulated write failure"),
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/toggle_product/{product_id}?session_id={pytest.session_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    print(actual)
    
    assert not actual["success"]
    assert "Error toggling product" in actual["message"]
    assert "Simulated write failure" in actual["message"]
    assert not actual["data"]
    assert actual["error_code"] == 500


@responses.activate
def test_toggle_product_not_found():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/dataset/call_kw"

    product_id = 999

    responses.add(
        responses.POST,
        url,
        json={"result": []},
        status=200
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/toggle_product/{product_id}?session_id={pytest.session_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    print(actual)
    
    assert not actual["success"]
    assert actual["message"] == f"Product {product_id} not found"
    assert not actual["data"]
    assert actual["error_code"] == 404


@responses.activate
def test_list_pos_orders_invalid_status():
    response = client.get(
        f"/api/bot/{pytest.bot}/pos/odoo/pos_order?session_id={pytest.session_id}&status=invalid_state",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    data = response.json()
    print(data)

    assert data["message"] == "Invalid status value"
    assert not data["success"]
    assert not data["data"]
    assert data["error_code"] == 400


@responses.activate
def test_list_pos_orders_empty():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/dataset/call_kw"

    responses.add(
        responses.POST,
        url,
        json={"result": []},
        status=200
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/pos/odoo/pos_order?session_id={pytest.session_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    data = response.json()
    print(data)

    assert data["data"]["data"] == []
    assert data["data"]["count"] == 0
    assert data["success"]
    assert data["message"] == "POS orders fetched"
    assert data["error_code"] == 0


@responses.activate
def test_list_pos_orders_success():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/dataset/call_kw"

    responses.add(
        responses.POST,
        url,
        json={"result": [10]},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": [
            {
                "id": 10,
                "name": "POS/0001",
                "amount_total": 450,
                "state": "paid",
                "partner_id": [1, "Test"],
                "company_id": [1, "My Company"],
                "session_id": [1, "Session A"],
                "date_order": "2025-01-01 10:00:00"
            }
        ]},
        status=200
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/pos/odoo/pos_order?session_id={pytest.session_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    data = response.json()
    print(data)

    assert data["data"]["count"] == 1
    assert data["data"] == {
        'data': [
            {
                'id': 10,
                'name': 'POS/0001',
                'amount_total': 450,
                'state': 'paid',
                'partner_id': [1, 'Test'],
                'company_id': [1, 'My Company'],
                'session_id': [1, 'Session A'],
                'date_order': '2025-01-01 10:00:00'}
        ],
        'count': 1
    }
    assert data["success"]
    assert data["message"] == "POS orders fetched"
    assert data["error_code"] == 0


@responses.activate
def test_create_pos_order_product_not_found():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/dataset/call_kw"

    responses.add(responses.POST, url, json={"result": []}, status=200)

    responses.add(responses.POST, url, json={"result": 99}, status=200)

    responses.add(responses.POST, url, json={"result": []}, status=200)

    payload = {
        "products": [{"product_id": 111, "qty": 1, "unit_price": 20.0}],
        "partner_id": None
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/pos_order?session_id={pytest.session_id}",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    data = response.json()
    print(data)

    assert not data["success"]
    assert data["message"] == "Product 111 not found"
    assert not data["data"]
    assert data["error_code"] == 404


@responses.activate
def test_create_pos_order_product_not_available():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/dataset/call_kw"
    
    responses.add(responses.POST, url, json={"result": []}, status=200)

    responses.add(responses.POST, url, json={"result": 98}, status=200)

    responses.add(
        responses.POST,
        url,
        json={"result": [{
            "name": "Hidden Item",
            "display_name": "Hidden",
            "lst_price": 100,
            "available_in_pos": False,
            "uom_id": [1, "Units"],
            "taxes_id": []
        }]},
        status=200
    )

    payload = {
        "products": [{"product_id": 99, "qty": 1, "unit_price": 20.0}]
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/pos_order?session_id={pytest.session_id}",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    data = response.json()
    print(data)
    assert not data["success"]
    assert not data["data"]
    assert data["message"] == "Product Hidden Item not available in POS"
    assert data["error_code"] == 400


@responses.activate
def test_create_pos_order_no_pos_config():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/dataset/call_kw"
    
    responses.add(responses.POST, url, json={"result": []}, status=200)

    responses.add(responses.POST, url, json={"result": 99}, status=200)

    responses.add(
        responses.POST,
        url,
        json={"result": [{
            "name": "Tea",
            "display_name": "Tea",
            "lst_price": 20,
            "available_in_pos": True,
            "uom_id": [1, "Units"],
            "taxes_id": []
        }]},
        status=200
    )

    responses.add(responses.POST, url, json={"result": []}, status=200)

    payload = {
        "products": [{"product_id": 1, "qty": 1, "unit_price": 20.0}]
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/pos_order?session_id={pytest.session_id}",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    data = response.json()
    print(data)
    assert not data["success"]
    assert data["message"] == "No POS Config found"
    assert not data["data"]
    assert data["error_code"] == 422


@responses.activate
def test_create_pos_order_no_payment_method():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/dataset/call_kw"
    
    responses.add(responses.POST, url, json={"result": []}, status=200)

    responses.add(responses.POST, url, json={"result": 99}, status=200)

    responses.add(
        responses.POST,
        url,
        json={"result": [{
            "name": "Coffee",
            "display_name": "Coffee Cup",
            "lst_price": 40,
            "available_in_pos": True,
            "uom_id": [1, "Units"],
            "taxes_id": []
        }]},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": [{"id": 1, "company_id": [1, "My Company"]}]},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": [{"id": 10, "sequence_number": 1}]},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": []},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": []},
        status=200
    )

    payload = {
        "products": [{"product_id": 1, "qty": 1, "unit_price": 20.0}]
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/pos_order?session_id={pytest.session_id}",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    data = response.json()
    print(data)
    assert not data["success"]
    assert data["message"] == "No POS payment methods found"
    assert not data["data"]
    assert data["error_code"]


@responses.activate
def test_create_pos_order_without_partner():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/dataset/call_kw"
    
    responses.add(responses.POST, url, json={"result": []}, status=200)

    responses.add(responses.POST, url, json={"result": 500}, status=200)

    responses.add(
        responses.POST,
        url,
        json={"result": [{
            "name": "Burger",
            "display_name": "Burger Meal",
            "lst_price": 150,
            "available_in_pos": True,
            "uom_id": [1, "Units"],
            "taxes_id": []
        }]},
        status=200
    )

    responses.add(responses.POST, url, json={"result": [{"id": 1, "company_id": [1, "Comp"]}]}, status=200)

    responses.add(responses.POST, url, json={"result": [{"id": 10, "sequence_number": 7}]}, status=200)

    responses.add(responses.POST, url, json={"result": [{"id": 22}]}, status=200)

    responses.add(responses.POST, url, json={"result": [555]}, status=200)

    responses.add(responses.POST, url, json={"result": {
            "id": 555,
            "pos_reference": "POS/1777892348",
            "account_move": False
        }}, status=200)

    payload = {"company_id": 10, "products": [{"product_id": 1, "qty": 2, "unit_price": 20.0}]}

    with patch(
            "kairon.shared.pos.processor.POSProcessor.get_client_details",
            return_value={
                "client_name": "Test Client",
                "branches": [
                    {"company_id": 10, "branch_name": "kairon Branch"}
                ]
            }
    ):
        res = client.post(
            f"/api/bot/{pytest.bot}/pos/odoo/pos_order?session_id={pytest.session_id}",
            json=payload,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )

    data = res.json()
    print(data)
    assert data["success"]
    assert data["message"] == "POS order created"
    assert data["data"]["order_id"] == {'account_move': False, 'id': 555, 'pos_reference': 'POS/1777892348'}
    assert data["error_code"] == 0


@responses.activate
def test_create_pos_order_success():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/dataset/call_kw"

    responses.add(
        responses.POST,
        url,
        json={"result": [{
            "name": "Pepsi",
            "display_name": "Pepsi 500ml",
            "lst_price": 50,
            "available_in_pos": True,
            "uom_id": [1, "Units"],
            "taxes_id": []
        }]},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": [{"id": 1, "company_id": [1, "My Company"]}]},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": [{"id": 10, "sequence_number": 1}]},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": [{"id": 5}]},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": [123]},
        status=200
    )

    responses.add(responses.POST, url, json={"result": {
            "id": 555,
            "pos_reference": "POS/1777892348",
            "account_move": False
        }}, status=200)

    payload = {
        "products": [{"product_id": 1, "qty": 2, "unit_price": 20.0}],
        "partner_id": 3
    }

    with patch(
            "kairon.shared.pos.processor.POSProcessor.get_client_details",
            return_value={
                "client_name": "Test Client",
                "branches": [
                    {"company_id": 10, "branch_name": "Main Branch"}
                ]
            }
    ):
        response = client.post(
            f"/api/bot/{pytest.bot}/pos/odoo/pos_order?session_id={pytest.session_id}",
            json=payload,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )

    data = response.json()
    print(data)

    assert data["success"]
    assert data["message"] == "POS order created"
    assert data["data"]["order_id"] == {'account_move': False, 'id': 555, 'pos_reference': 'POS/1777892348'}
    assert data["data"]["status"] == "created"
    assert data["error_code"] == 0
    assert "kot" in data["data"]
    assert "items" in data["data"]["kot"]
    assert len(data["data"]["kot"]["items"]) == 1
    assert data["data"]["kot"]["items"][0]["name"] == "Pepsi 500ml"
    assert data["data"]["kot"]["items"][0]["qty"] == 2

@responses.activate
def test_create_pos_order_success_with_cid():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/dataset/call_kw"

    responses.add(
        responses.POST,
        url,
        json={"result": [{
            "name": "Pepsi",
            "display_name": "Pepsi 500ml",
            "lst_price": 50,
            "available_in_pos": True,
            "uom_id": [1, "Units"],
            "taxes_id": [],
            "company_id": 2
        }]},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": [{"id": 1, "company_id": [1, "My Company"]}]},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": [{"id": 10, "sequence_number": 1}]},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": [{"id": 5}]},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": [123]},
        status=200
    )

    responses.add(responses.POST, url, json={"result": {
            "id": 555,
            "pos_reference": "POS/1777892348",
            "account_move": False
        }}, status=200)


    payload = {
        "products": [{"product_id": 1, "qty": 2, "unit_price": 20.0}],
        "partner_id": 3
    }

    with patch(
            "kairon.shared.pos.processor.POSProcessor.get_client_details",
            return_value={
                "client_name": "Test Client",
                "branches": [
                    {"company_id": 10, "branch_name": "Main Branch"}
                ]
            }
    ):
        response = client.post(
            f"/api/bot/{pytest.bot}/pos/odoo/pos_order?session_id={pytest.session_id}",
            json=payload,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )

    data = response.json()
    print(data)

    assert data["success"]
    assert data["message"] == "POS order created"
    assert data["data"]["order_id"] == {'account_move': False, 'id': 555, 'pos_reference': 'POS/1777892348'}
    assert data["data"]["status"] == "created"
    assert data["error_code"] == 0
    assert "kot" in data["data"]
    assert "items" in data["data"]["kot"]
    assert len(data["data"]["kot"]["items"]) == 1
    assert data["data"]["kot"]["items"][0]["name"] == "Pepsi 500ml"
    assert data["data"]["kot"]["items"][0]["qty"] == 2

@responses.activate
def test_create_pos_order_create_new_session():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/dataset/call_kw"

    responses.add(
        responses.POST,
        url,
        json={"result": [{
            "name": "Pepsi",
            "display_name": "Pepsi 500ml",
            "lst_price": 50,
            "available_in_pos": True,
            "uom_id": [1, "Units"],
            "taxes_id": []
        }]},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": [
            {"id": 1, "company_id": [1, "My Company"]}
        ]},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": []},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": 99},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": True},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": [{
            "id": 99,
            "sequence_number": 1,
            "payment_method_ids": [5]
        }]},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": [2]},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": [{
            "id": 555,
            "pos_reference": "POS/1777892348",
            "account_move": False
        }]},
        status=200
    )

    payload = {
        "products": [
            {
                "product_id": 1,
                "qty": 2,
                "unit_price": 20.0
            }
        ],
        "partner_id": 3
    }

    with patch(
        "kairon.shared.pos.processor.POSProcessor.get_client_details",
        return_value={
            "client_name": "Test Client",
            "branches": [
                {
                    "company_id": 10,
                    "branch_name": "Main Branch"
                }
            ]
        }
    ):
        response = client.post(
            f"/api/bot/{pytest.bot}/pos/odoo/pos_order?session_id={pytest.session_id}",
            json=payload,
            headers={
                "Authorization": pytest.token_type + " " + pytest.access_token
            },
        )

    data = response.json()

    print(data)

    assert data["success"]
    assert data["message"] == "POS order created"
    assert data["data"]["status"] == "created"
    assert data["data"]["order_id"] == {
        "id": 555,
        "pos_reference": "POS/1777892348",
        "account_move": False
    }
    assert data["error_code"] == 0
    assert "kot" in data["data"]
    assert "items" in data["data"]["kot"]
    assert len(data["data"]["kot"]["items"]) == 1
    assert data["data"]["kot"]["items"][0]["name"] == "Pepsi 500ml"
    assert data["data"]["kot"]["items"][0]["qty"] == 2

@responses.activate
def test_accept_pos_order_invalid_state():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/dataset/call_kw"

    order_id = 12

    responses.add(
        responses.POST,
        url,
        json={"result": [{
            "id": order_id,
            "amount_total": 120,
            "state": "cancel",
            "partner_id": [1, "Test"],
            "session_id": [1, "Session A"]
        }]},
        status=200
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/pos_order/accept/{order_id}?session_id={pytest.session_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    data = response.json()
    print(data)
    assert not data["success"]
    assert data["message"] == "Cannot accept order. order already in 'cancel' state."
    assert not data["data"]
    assert data["error_code"] == 400


@responses.activate
def test_accept_pos_order_not_found():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/dataset/call_kw"

    order_id = 999

    responses.add(responses.POST, url, json={"result": []}, status=200)

    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/pos_order/accept/{order_id}?session_id={pytest.session_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    data = response.json()
    print(data)

    assert not data["success"]
    assert data["message"] == "Order not found"
    assert not data["data"]
    assert data["error_code"] == 404

@responses.activate
def test_accept_pos_order_unexpected_error():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/dataset/call_kw"

    order_id = 14

    responses.add(
        responses.POST,
        url,
        body="Bad Request",
        status=400
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/pos_order/accept/{order_id}?session_id={pytest.session_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    data = response.json()
    print(data)
    assert not data["success"]
    assert data["message"] == "JSON-RPC pos.order.read: HTTP 400 - Bad Request"
    assert not data["data"]
    assert data["error_code"] == 400


def test_accept_pos_order_invoice_failure():
    order_id = 11

    order_data = {
        "id": order_id,
        "amount_total": 200,
        "partner_id": [1, "John"],
        "state": "draft",
        "session_id": [1, "Session A"]
    }

    with patch("kairon.shared.pos.processor.POSProcessor.jsonrpc_call") as mock_jsonrpc:

        mock_jsonrpc.side_effect = [
            [order_data],
            Exception("Invoice failed")
        ]

        response = client.post(
            f"/api/bot/{pytest.bot}/pos/odoo/pos_order/accept/{order_id}?session_id={pytest.session_id}",
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )

        data = response.json()

        assert data["success"]
        assert data["message"] == "Order accepted"
        assert data["data"] == {
            "order_id": order_id,
            "accepted": True,
            "invoiced": False
        }
        assert data["error_code"] == 0

@responses.activate
def test_accept_pos_order_success():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/dataset/call_kw"

    order_id = 10

    responses.add(
        responses.POST,
        url,
        json={"result": [{
            "id": order_id,
            "amount_total": 500,
            "partner_id": [1, "Test"],
            "state": "draft",
            "session_id": [1, "Session A"]
        }]},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": [{"journal_id": [20, "Cash"]}]},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": 55},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": True},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": True},
        status=200
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/pos_order/accept/{order_id}?session_id={pytest.session_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    data = response.json()
    print(data)

    assert data["success"]
    assert data["message"] == "Order accepted"
    assert data["data"] == {"order_id": order_id, "accepted": True}
    assert data["error_code"] == 0


@responses.activate
def test_reject_pos_order_invalid_state():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/dataset/call_kw"

    order_id = 15

    responses.add(
        responses.POST,
        url,
        json={"result": [{
            "id": order_id,
            "state": "cancel"
        }]},
        status=200
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/pos_order/reject/{order_id}?session_id={pytest.session_id}",
        headers={"Authorization": pytest.token_type + ' ' + pytest.access_token},
    )

    data = response.json()
    print(data)

    assert not data["success"]
    assert data["message"] == "Cannot cancel order. order already in 'cancel' state."
    assert not data["data"]
    assert data["error_code"] == 400


@responses.activate
def test_reject_pos_order_not_found():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/dataset/call_kw"

    order_id = 999

    responses.add(
        responses.POST,
        url,
        json={"result": []},
        status=200
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/pos_order/reject/{order_id}?session_id={pytest.session_id}",
        headers={"Authorization": pytest.token_type + ' ' + pytest.access_token},
    )

    data = response.json()
    print(data)

    assert not data["success"]
    assert data["message"] == "Order not found"
    assert data["error_code"] == 404
    assert not data["data"]
    
    
@responses.activate
def test_reject_pos_order_success():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/dataset/call_kw"

    order_id = 10

    responses.add(
        responses.POST,
        url,
        json={"result": [{
            "id": order_id,
            "state": "draft"
        }]},
        status=200
    )

    responses.add(
        responses.POST,
        url,
        json={"result": True},
        status=200
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/pos_order/reject/{order_id}?session_id={pytest.session_id}",
        headers={"Authorization": pytest.token_type + ' ' + pytest.access_token},
    )

    data = response.json()
    print(data)

    assert data["success"]
    assert data["message"] == "Order rejected"
    assert data["data"] == {"order_id": order_id, "status": "cancelled"}
    assert data["error_code"] == 0


@responses.activate
def test_get_pos_products_odoo_error():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/dataset/call_kw"

    responses.add(
        responses.POST,
        url,
        body="Bad Request",
        status=400
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/pos/odoo/product?session_id={pytest.session_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    data = response.json()
    print(data)

    assert not data["success"]
    assert "Odoo error" in data["message"]
    assert data["message"] == 'Odoo error: 400: JSON-RPC product.template.search_read: HTTP 400 - Bad Request'
    assert not data["data"]


@responses.activate
def test_get_pos_products_success():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/dataset/call_kw"

    products = [
        {
            "product_variant_id": 1,
            "name": "Product A",
            "list_price": 100,
            "barcode": "123456",
            "available_in_pos": True,
            "categ_id": [1, "Snacks"],
            "description_sale": "Crunchy Fries Available!"
        },
        {
            "product_variant_id": 2,
            "name": "Product B",
            "list_price": 200,
            "barcode": "789012",
            "available_in_pos": True,
            "categ_id": [2, "Beverages"],
            "description_sale": False
        }
    ]

    responses.add(
        responses.POST,
        url,
        json={"result": products},
        status=200
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/pos/odoo/product?session_id={pytest.session_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    data = response.json()
    print(data)

    assert data["success"]
    assert data["data"]["count"] == 2
    assert data["data"]["data"] == products
    assert data["error_code"] == 0
    assert not data["message"]

@responses.activate
def test_get_user_access_success():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/jsonrpc"

    mock_odoo_response = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": [
            {
                "id": 1,
                "name": "Admin",
                "login": "admin",
                "company_id": [1, "Main Company"],
                "company_ids": [1]
            }
        ]
    }

    responses.add(
        responses.POST,
        url,
        json=mock_odoo_response,
        status=200
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/user/access?session_id={pytest.session_id}",
        json={
            "db_name": "test_db",
            "password": "admin"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    data = response.json()

    assert data["success"]
    assert data["data"] == mock_odoo_response

@responses.activate
def test_get_user_access_odoo_error():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/jsonrpc"

    responses.add(
        responses.POST,
        url,
        json={
            "error": {
                "code": 400,
                "message": "Bad Request"
            }
        },
        status=400
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/user/access?session_id={pytest.session_id}",
        json={
            "db_name": "test_db",
            "password": "admin"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    data = response.json()
    print(data)

    assert "error" in data["data"]


@responses.activate
def test_invalidate_session_success():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/session/destroy"

    responses.add(
        responses.POST,
        url,
        json={"result": True},
        status=200
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/invalidate/session?session_id={pytest.session_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    data = response.json()
    print(data)

    assert data["success"] is True
    assert data["message"] == "Session invalidated successfully"
    assert not data["data"]
    assert data["error_code"] == 0


@responses.activate
def test_invalidate_session_odoo_error_response():
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/session/destroy"

    responses.add(
        responses.POST,
        url,
        json={
            "error": {
                "code": 200,
                "message": "Session expired"
            }
        },
        status=200
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/invalidate/session?session_id=invalid-session",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    data = response.json()
    print(data)

    assert data["success"] is True
    assert data["error_code"] == 0
    assert not data["data"]
    assert data["message"] == "Session invalidated successfully"


@responses.activate
def test_invalidate_session_request_failure():
    import requests
    base = Utility.environment["pos"]["odoo"]["odoo_url"]
    url = f"{base}/web/session/destroy"

    responses.add(
        responses.POST,
        url,
        body=requests.exceptions.ConnectionError("Connection refused"),
        status=400
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/pos/odoo/invalidate/session?session_id={pytest.session_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    data = response.json()
    print(data)

    assert not data["success"]
    assert "Connection refused" in data["message"]
    assert not data["data"]
    assert data["error_code"] == 400

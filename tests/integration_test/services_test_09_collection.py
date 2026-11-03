from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training



def test_get_collection_data_with_no_collection_data():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/collection",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]
    assert actual["data"] == []


def test_save_collection_data_with_keys_not_present():
    request_body = {
        "collection_name": "user",
        "is_secure": ["name", "mobile_number", "aadhar"],
        "data": {
            "name": "Mahesh",
            "age": 24,
            "mobile_number": "9876543210",
            "location": "Bangalore"
        }
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/collection",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["data"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', '__root__'],
                                  'msg': 'is_secure contains keys that are not present in data',
                                  'type': 'value_error'}]
    assert not actual["success"]


def test_save_collection_data_with_collection_name_empty():
    request_body = {
        "collection_name": "",
        "is_secure": ["name", "mobile_number"],
        "data": {
            "name": "Mahesh",
            "age": 24,
            "mobile_number": "9876543210",
            "location": "Bangalore"
        }
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/collection",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["data"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', '__root__'],
                                  'msg': 'collection_name should not be empty!', 'type': 'value_error'}]
    assert not actual["success"]


def test_save_collection_data_with_invalid_is_secure():
    request_body = {
        "collection_name": "user",
        "is_secure": "name, mobile_number",
        "data": {
            "name": "Mahesh",
            "age": 24,
            "mobile_number": "9876543210",
            "location": "Bangalore"
        }
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/collection",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["data"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'is_secure'],
                                  'msg': 'value is not a valid list', 'type': 'type_error.list'},
                                 {'loc': ['body', '__root__'], 'msg': 'is_secure should be list of keys!',
                                  'type': 'value_error'}]
    assert not actual["success"]


def test_save_collection_data_with_invalid_data():
    request_body = {
        "collection_name": "user",
        "is_secure": ["name", "mobile_number"],
        "data": "Mahesh"
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/collection",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["data"]
    assert actual["error_code"] == 422
    assert actual["message"] ==  [{'loc': ['body', 'data'],
                                   'msg': 'value is not a valid dict', 'type': 'type_error.dict'},
                                  {'loc': ['body', '__root__'],
                                   'msg': 'data cannot be empty and should be of type dict!',
                                   'type': 'value_error'}]
    assert not actual["success"]

def test_save_collection_data_with_non_editable_keys_not_present():
    request_body = {
        "collection_name": "user",
        "is_secure": ["name", "mobile_number"],
        "is_non_editable": ["name", "aadhar"],  # 'aadhar' not in data
        "data": {
            "name": "Mahesh",
            "age": 24,
            "mobile_number": "9876543210",
            "location": "Bangalore"
        }
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/collection",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["data"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', '__root__'],
                                  'msg': 'is_non_editable contains keys that are not present in data',
                                  'type': 'value_error'}]
    assert not actual["success"]

def test_save_collection_data():
    request_body = {
        "collection_name": "user",
        "is_secure": ["name", "mobile_number"],
        "data": {
            "name": "Mahesh",
            "age": 24,
            "mobile_number": "9876543210",
            "location": "Bangalore"
        }
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/collection",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"]
    assert actual["error_code"] == 0
    assert actual["message"] == 'Record saved!'
    assert actual["success"]
    pytest.collection_id = actual["data"]["_id"]


def test_save_collection_data_with_collection_name_already_exist():
    request_body = {
        "collection_name": "user",
        "is_secure": [],
        "data": {
            "name": "Hitesh",
            "age": 25,
            "mobile_number": "989284928928",
            "location": "Mumbai"
        }
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/collection",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"]
    assert actual["error_code"] == 0
    assert actual["message"] == 'Record saved!'
    assert actual["success"]


def test_save_collection_data_with_valid_data():
    request_body = {
        "collection_name": "bank_details",
        "is_secure": ["account_number", "mobile_number", "ifsc"],
        "data": {
            "account_holder_name": "Mahesh",
            "account_number": "636283263288232",
            "mobile_number": "9876543210",
            "location": "Bangalore",
            "ifsc": "SBIN0000000"
        }
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/collection",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"]
    assert actual["error_code"] == 0
    assert actual["message"] == 'Record saved!'
    assert actual["success"]


def test_list_collection_data():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/collection",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]
    data = actual["data"]
    for coll_data in data:
        coll_data.pop("_id")
    assert data == [
        {
            'collection_name': 'user',
            'is_secure': ['name', 'mobile_number'],
            'is_non_editable': [],
            'data': {
                'name': 'Mahesh',
                'age': 24,
                'mobile_number': '9876543210',
                'location': 'Bangalore'
            }
        },
        {
            'collection_name': 'user',
            'is_secure': [],
            'is_non_editable': [],
            'data': {
                'name': 'Hitesh',
                'age': 25,
                'mobile_number': '989284928928',
                'location': 'Mumbai'
            }
        },
        {
            'collection_name': 'bank_details',
            'is_secure': ['account_number', 'mobile_number', 'ifsc'],
            'is_non_editable': [],

            'data': {
                'account_holder_name': 'Mahesh',
                'account_number': '636283263288232',
                'mobile_number': '9876543210',
                'location': 'Bangalore',
                'ifsc': 'SBIN0000000'
            }
        }
    ]


def test_get_collection_data_with_mismatch_filter_length():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/collection/user?key=name&value=Hitesh&key=location",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == 'Keys and values lists must be of the same length.'
    assert not actual["success"]


def test_get_collection_data():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/collection/user?key=name&value=Hitesh",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]
    data = actual["data"]["logs"]
    for coll_data in data:
        coll_data.pop("_id")
    assert data == [
        {
            'collection_name': 'user',
            'is_secure': [],
            'is_non_editable': [],

            'data': {
                'name': 'Hitesh',
                'age': 25,
                'mobile_number': '989284928928',
                'location': 'Mumbai'
            }
        }
    ]
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/collection/user?key=location&value=Bangalore",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]
    data = actual["data"]["logs"]
    for coll_data in data:
        coll_data.pop("_id")
    assert data == [
        {
            'collection_name': 'user',
            'is_secure': ['name', 'mobile_number'],
            'is_non_editable': [],
            'data': {
                'name': 'Mahesh',
                'age': 24,
                'mobile_number': '9876543210',
                'location': 'Bangalore'
            }
        }
    ]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/collection/bank_details",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]
    data = actual["data"]["logs"]
    for coll_data in data:
        coll_data.pop("_id")
    assert data == [
        {
            'collection_name': 'bank_details',
            'is_secure': ['account_number', 'mobile_number', 'ifsc'],
            'is_non_editable': [],

            'data': {
                'account_holder_name': 'Mahesh',
                'account_number': '636283263288232',
                'mobile_number': '9876543210',
                'location': 'Bangalore',
                'ifsc': 'SBIN0000000'
            }
        }
    ]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/collection/user",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]
    data = actual["data"]["logs"]
    for coll_data in data:
        coll_data.pop("_id")
    assert data == [
        {
            'collection_name': 'user',
            'is_secure': [],
            'is_non_editable': [],

            'data': {
                'name': 'Hitesh',
                'age': 25,
                'mobile_number': '989284928928',
                'location': 'Mumbai'
            }
        },
        {
            'collection_name': 'user',
            'is_secure': ['name', 'mobile_number'],
            'is_non_editable': [],
            'data': {
                'name': 'Mahesh',
                'age': 24,
                'mobile_number': '9876543210',
                'location': 'Bangalore'
            }
        }
    ]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/collection/user?key=name&value=Hitesh&key=location&value=Bangalore",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]
    data = actual["data"]["logs"]
    for coll_data in data:
        coll_data.pop("_id")
    assert data == []

    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/collection/user?key=name&value=Hitesh&key=location&value=Mumbai",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]
    data = actual["data"]["logs"]
    for coll_data in data:
        coll_data.pop("_id")
    assert data == [
        {
            'collection_name': 'user',
            'is_secure': [],
            'is_non_editable': [],
            'data': {
                'name': 'Hitesh',
                'age': 25,
                'mobile_number': '989284928928',
                'location': 'Mumbai'
            }
        }
    ]


def test_get_collection_data_pagination():
    full_response = client.get(
        url=f"/api/bot/{pytest.bot}/data/collection/user",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    assert full_response.status_code == 200
    full_data = full_response.json()["data"]["logs"]
    assert isinstance(full_data, list)
    assert len(full_data) >= 1
    total_expected = len(full_data)

    page_size = 1
    start_idx = 0
    expected_slice = full_data[start_idx : start_idx + page_size]

    paginated_response = client.get(
        url=(
            f"/api/bot/{pytest.bot}/data/collection/user"
            f"?page_size={page_size}&start_idx={start_idx}"
        ),
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = paginated_response.json()

    assert paginated_response.status_code == 200
    assert actual["error_code"] == 0
    assert actual["success"]
    assert isinstance(actual["data"]["logs"], list)
    assert actual["data"]["logs"] == expected_slice
    assert actual["data"]["total"] == total_expected

def test_get_collection_data_with_collection_id():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/collection/data/{pytest.collection_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]
    data = actual["data"]
    print(data)
    assert data == {
        '_id': pytest.collection_id,
        'collection_name': 'user',
        'is_secure': ['name', 'mobile_number'],
        'is_non_editable': [],
        'data': {
            'name': 'Mahesh',
            'age': 24,
            'mobile_number': '9876543210',
            'location': 'Bangalore'
        }
    }

def test_get_collection_data_with_filter():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/collection/user/filter",
        params={"filters": json.dumps({"name": "Hitesh"})},
        headers={"Authorization": f"{pytest.token_type} {pytest.access_token}"},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]
    data = actual["data"]
    for coll_data in data:
        coll_data.pop("_id")
    assert data == [
        {
            'collection_name': 'user',
            'is_secure': [],
            'is_non_editable': [],
            'data': {
                'name': 'Hitesh',
                'age': 25,
                'mobile_number': '989284928928',
                'location': 'Mumbai'
            }
        }
    ]

def test_get_collection_data_with_collection_id_doesnot_exists():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/collection/data/{pytest.bot}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Collection data does not exists!"
    assert not actual["data"]


def test_update_collection_data_with_collection_name_empty():
    request_body = {
        "collection_name": "",
        "is_secure": ["name", "mobile_number"],
        "data": {
            "name": "Mahesh",
            "age": 24,
            "mobile_number": "9876543210",
            "location": "Bangalore"
        }
    }

    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/collection/{pytest.collection_id}",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["data"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', '__root__'],
                                  'msg': 'collection_name should not be empty!', 'type': 'value_error'}]
    assert not actual["success"]


def test_update_collection_data_with_keys_not_present():
    request_body = {
        "collection_name": "user",
        "is_secure": ["name", "mobile_number", "address"],
        "data": {
            "name": "Mahesh",
            "age": 24,
            "mobile_number": "9876543210",
            "location": "Bangalore"
        }
    }

    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/collection/{pytest.collection_id}",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["data"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', '__root__'],
                                  'msg': 'is_secure contains keys that are not present in data',
                                  'type': 'value_error'}]
    assert not actual["success"]


def test_update_collection_data_with_invalid_is_secure():
    request_body = {
        "collection_name": "user",
        "is_secure": "name, mobile_number",
        "data": {
            "name": "Mahesh",
            "age": 24,
            "mobile_number": "9876543210",
            "location": "Bangalore"
        }
    }

    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/collection/{pytest.collection_id}",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["data"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'is_secure'],
                                  'msg': 'value is not a valid list', 'type': 'type_error.list'},
                                 {'loc': ['body', '__root__'], 'msg': 'is_secure should be list of keys!',
                                  'type': 'value_error'}]
    assert not actual["success"]

def test_update_collection_data_with_non_editable_keys_not_present():
    request_body = {
        "collection_name": "user",
        "is_secure": ["name", "mobile_number"],
        "is_non_editable": ["name", "aadhar"],  # 'aadhar' not in data
        "data": {
            "name": "Mahesh",
            "age": 24,
            "mobile_number": "9876543210",
            "location": "Bangalore"
        }
    }

    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/collection/{pytest.collection_id}",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["data"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', '__root__'],
                                  'msg': 'is_non_editable contains keys that are not present in data',
                                  'type': 'value_error'}]
    assert not actual["success"]

def test_update_collection_data_with_invalid_is_non_editable():
    request_body = {
        "collection_name": "user",
        "is_secure": ["name", "mobile_number"],
        "is_non_editable": "name, aadhar",  # Invalid: should be a list
        "data": {
            "name": "Mahesh",
            "age": 24,
            "mobile_number": "9876543210",
            "location": "Bangalore"
        }
    }

    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/collection/{pytest.collection_id}",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["data"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'is_non_editable'],
                                  'msg': 'value is not a valid list', 'type': 'type_error.list'},
                                 {'loc': ['body', '__root__'],
                                  'msg': 'is_non_editable should be a list of keys!',
                                  'type': 'value_error'}]
    assert not actual["success"]

def test_update_collection_data_with_invalid_data():
    request_body = {
        "collection_name": "user",
        "is_secure": ["name", "mobile_number"],
        "data": "Mahesh"
    }

    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/collection/{pytest.collection_id}",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["data"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'data'],
                                  'msg': 'value is not a valid dict', 'type': 'type_error.dict'},
                                 {'loc': ['body', '__root__'],
                                  'msg': 'data cannot be empty and should be of type dict!',
                                  'type': 'value_error'}]
    assert not actual["success"]


def test_update_collection_data():
    request_body = {
        "collection_name": "user",
        "is_secure": ["mobile_number", "location"],
        "data": {
            "name": "Mahesh",
            "age": 24,
            "mobile_number": "9876543210",
            "location": "Bangalore"
        }
    }

    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/collection/{pytest.collection_id}",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"]
    assert actual["error_code"] == 0
    assert actual["message"] == 'Record updated!'
    assert actual["success"]


def test_update_collection_data_doesnot_exist():
    request_body = {
        "collection_name": "user_details",
        "is_secure": ["mobile_number", "location"],
        "data": {
            "name": "Mahesh",
            "age": 24,
            "mobile_number": "9876543210",
            "location": "Bangalore"
        }
    }

    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/collection/{pytest.collection_id}",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["data"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Collection Data with given id and collection_name not found!'
    assert not actual["success"]


def test_get_collection_data_after_update():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/collection",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]
    data = actual["data"]
    for coll_data in data:
        coll_data.pop("_id")
    assert data == [
        {
            'collection_name': 'user',
            'is_secure': ['mobile_number', 'location'],
            'is_non_editable': [],
            'data': {
                'name': 'Mahesh',
                'age': 24,
                'mobile_number': '9876543210',
                'location': 'Bangalore'
            }
        },
        {
            'collection_name': 'user',
            'is_secure': [],
            'is_non_editable': [],
            'data': {
                'name': 'Hitesh',
                'age': 25,
                'mobile_number': '989284928928',
                'location': 'Mumbai'
            }
        },
        {
            'collection_name': 'bank_details',
            'is_secure': ['account_number', 'mobile_number', 'ifsc'],
            'is_non_editable': [],
            'data': {
                'account_holder_name': 'Mahesh',
                'account_number': '636283263288232',
                'mobile_number': '9876543210',
                'location': 'Bangalore',
                'ifsc': 'SBIN0000000'
            }
        }
    ]


def test_get_collection_metadata():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/collection/user/metadata",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    print(actual)
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]
    data = actual["data"]
    assert data['properties'] == {
        'name': {'type': 'string'},
        'age': {'type': 'integer'},
        'mobile_number': {'type': 'string'},
        'location': {'type': 'string'}
    }
    assert data['required'] == ['age', 'location', 'mobile_number', 'name']

    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/collection/bank_details/metadata",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    print(actual)
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]
    data = actual["data"]
    assert data['properties'] == {
        'account_holder_name': {'type': 'string'},
        'account_number': {'type': 'string'},
        'mobile_number': {'type': 'string'},
        'location': {'type': 'string'},
        'ifsc': {'type': 'string'}
    }


def test_delete_collection_data_doesnot_exist():
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/data/collection/{pytest.bot}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["data"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Collection Data does not exists!'
    assert not actual["success"]


def test_delete_collection_data():
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/data/collection/{pytest.collection_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["data"]
    assert actual["error_code"] == 0
    assert actual["message"] == 'Record deleted!'
    assert actual["success"]


def test_get_collection_data_after_delete():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/collection",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]
    data = actual["data"]
    for coll_data in data:
        coll_data.pop("_id")
    assert data == [
        {
            'collection_name': 'user',
            'is_secure': [],
            'is_non_editable': [],
            'data': {
                'name': 'Hitesh',
                'age': 25,
                'mobile_number': '989284928928',
                'location': 'Mumbai'
            }
        },
        {
            'collection_name': 'bank_details',
            'is_secure': ['account_number', 'mobile_number', 'ifsc'],
            'is_non_editable': [],
            'data': {
                'account_holder_name': 'Mahesh',
                'account_number': '636283263288232',
                'mobile_number': '9876543210',
                'location': 'Bangalore',
                'ifsc': 'SBIN0000000'
            }
        }
    ]


def test_get_live_agent_with_no_live_agent():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/live_agent",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"] == []
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]


def test_enable_live_agent():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.live_agent_enabled = True
    bot_settings.save()

    request_body = {
        "bot_response": "connecting to live agent",
        "dispatch_bot_response": False,
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/live_agent",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == 'Live Agent Action enabled!'
    assert actual["success"]


def test_get_live_agent_after_enabled_no_bot_settings_enabled():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.live_agent_enabled = False
    bot_settings.save()
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/live_agent",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"] == []
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]


def test_get_live_agent_after_enabled():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.live_agent_enabled = True
    bot_settings.save()
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/live_agent",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"] == {'name': 'live_agent_action', 'bot_response': 'connecting to live agent',
                              'agent_connect_response': 'Connected to live agent',
                              'agent_disconnect_response': 'Agent has closed the conversation',
                              'agent_not_available_response': 'No agents available at this moment. An agent will reply to you shortly.',
                              'dispatch_bot_response': False, 'dispatch_agent_connect_response': True,
                              'dispatch_agent_disconnect_response': True, 'dispatch_agent_not_available_response': True}
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]


def test_enable_live_agent_already_exist():
    request_body = {
        "bot_response": "connecting to live agent",
        "dispatch_bot_response": False,
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/live_agent",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == 'Live Agent Action already enabled!'
    assert actual["success"]


def test_update_live_agent():
    BotSettings(bot=pytest.bot, user="integration@demo.ai", live_agent_enabled=True)
    request_body = {
        "bot_response": "connecting to different live agent...",
        "dispatch_bot_response": True,
    }

    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/live_agent",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == 'Action updated!'
    assert actual["success"]


def test_get_live_agent_after_updated():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/live_agent",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"] == {'name': 'live_agent_action',
                              'bot_response': 'connecting to different live agent...',
                              'agent_connect_response': 'Connected to live agent',
                              'agent_disconnect_response': 'Agent has closed the conversation',
                              'agent_not_available_response': 'No agents available at this moment. An agent will reply to you shortly.',
                              'dispatch_bot_response': True,
                              'dispatch_agent_connect_response': True,
                              'dispatch_agent_disconnect_response': True,
                              'dispatch_agent_not_available_response': True}
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]


def test_disable_live_agent():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/live_agent/disable",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["data"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Live Agent Action disabled!"
    assert actual["success"]


def test_update_live_agent_does_not_exist():
    request_body = {
        "bot_response": "connecting to different live agent",
        "dispatch_bot_response": True,
    }

    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/live_agent",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == 'Live agent not enabled for the bot'
    assert not actual["success"]


def test_get_live_agent_after_disabled():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/live_agent",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["data"]
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]

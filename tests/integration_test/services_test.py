import json
import os
import re
import shutil
import tarfile
import tempfile
from io import BytesIO
from zipfile import ZipFile

import mongomock
import pytest
import responses
from fastapi.testclient import TestClient
from mongoengine import connect
from rasa.shared.utils.io import read_config_file

from kairon.api.app.main import app
from kairon.api.auth import Authentication
from kairon.api.models import StoryEventType, User
from kairon.api.processor import AccountProcessor
from kairon.data_processor.constant import UTTERANCE_TYPE, EVENT_STATUS
from kairon.data_processor.data_objects import Stories, Intents, TrainingExamples, Responses
from kairon.data_processor.model_processor import ModelProcessor
from kairon.data_processor.processor import MongoProcessor
from kairon.data_processor.training_data_generation_processor import TrainingDataGenerationProcessor
from kairon.exceptions import AppException
from kairon.importer.data_objects import ValidationLogs
from kairon.shared.actions.data_objects import HttpActionLog
from kairon.utils import Utility

os.environ["system_file"] = "./tests/testing_data/system.yaml"
client = TestClient(app)
access_token = None
token_type = None


@pytest.fixture(autouse=True)
def setup():
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    Utility.load_evironment()
    connect(host=Utility.environment['database']["url"])


def pytest_configure():
    return {'token_type': None,
            'access_token': None,
            'username': None,
            'bot': None
            }


def test_api_wrong_login():
    response = client.post(
        "/api/auth/login", data={"username": "test@demo.ai", "password": "Welcome@1"}
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["success"]
    assert actual["message"] == "User does not exist!"


def test_account_registration_error():
    response = client.post(
        "/api/account/registration",
        json={
            "email": "integration@demo.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "welcome@1",
            "confirm_password": "welcome@1",
            "account": "integration",
            "bot": "integration",
        },
    )
    actual = response.json()
    assert actual["message"] == [
        {'loc': ['body', 'password'], 'msg': 'Missing 1 uppercase letter', 'type': 'value_error'}]
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None


def test_account_registration():
    response = client.post(
        "/api/account/registration",
        json={
            "email": "integration@demo.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@1",
            "confirm_password": "Welcome@1",
            "account": "integration",
            "bot": "integration",
        },
    )
    actual = response.json()
    assert actual["message"] == "Account Registered!"
    response = client.post(
        "/api/account/registration",
        json={
            "email": "integration2@demo.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@1",
            "confirm_password": "Welcome@1",
            "account": "integration2",
            "bot": "integration2",
        },
    )
    actual = response.json()
    assert actual["message"] == "Account Registered!"


def test_api_wrong_password():
    response = client.post(
        "/api/auth/login", data={"username": "integration@demo.ai", "password": "welcome@1"}
    )
    actual = response.json()
    assert actual["error_code"] == 401
    assert not actual["success"]
    assert actual["message"] == "Incorrect username or password"


def test_api_login():
    email = "integration@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@1"},
    )
    actual = response.json()
    assert all(
        [
            True if actual["data"][key] else False
            for key in ["access_token", "token_type"]
        ]
    )
    assert actual["success"]
    assert actual["error_code"] == 0
    pytest.access_token = actual["data"]["access_token"]
    pytest.token_type = actual["data"]["token_type"]
    pytest.username = email
    response = client.get(
        "/api/user/details",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response['data']['user']['_id']
    assert response['data']['user']['email'] == 'integration@demo.ai'
    assert response['data']['user']['role'] == 'admin'
    assert response['data']['user']['bot']
    assert response['data']['user']['timestamp']
    assert response['data']['user']['status']
    assert response['data']['user']['bot_name']
    assert response['data']['user']['account_name'] == 'integration'
    assert response['data']['user']['first_name'] == 'Demo'
    assert response['data']['user']['last_name'] == 'User'


def test_add_bot():
    response = client.post(
        "/api/account/bot",
        json={"data": "covid-bot"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response['message'] == 'Bot created'
    assert response['error_code'] == 0
    assert response['success']


def test_list_bots():
    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert len(response['data']) == 2
    pytest.bot = response['data'][0]['_id']
    assert response['data'][0]['name'] == 'Hi-Hello'
    assert response['data'][1]['name'] == 'covid-bot'


def test_update_bot_name():
    response = client.put(
        f"/api/account/bot/{pytest.bot}",
        json={"data": "Hi-Hello-bot"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response['message'] == 'Bot name updated'
    assert response['error_code'] == 0
    assert response['success']

    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert len(response['data']) == 2
    pytest.bot = response['data'][0]['_id']
    assert response['data'][0]['name'] == 'Hi-Hello-bot'
    assert response['data'][1]['name'] == 'covid-bot'


@pytest.fixture()
def resource_test_upload_zip():
    data_path = 'tests/testing_data/yml_training_files'
    tmp_dir = tempfile.gettempdir()
    zip_file = os.path.join(tmp_dir, 'test')
    shutil.make_archive(zip_file, 'zip', data_path)
    pytest.zip = open(zip_file + '.zip', 'rb').read()
    yield "resource_test_upload_zip"
    os.remove(zip_file + '.zip')
    shutil.rmtree(os.path.join('training_data', pytest.bot))


def test_upload_zip(resource_test_upload_zip):
    files = (('training_files', ("data.zip", pytest.zip)),
             ('training_files', ("domain.yml", open("tests/testing_data/all/domain.yml", "rb"))))
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=false",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]


def test_upload():
    files = (('training_files', ("nlu.md", open("tests/testing_data/all/data/nlu.md", "rb"))),
              ('training_files', ("domain.yml", open("tests/testing_data/all/domain.yml", "rb"))),
              ('training_files', ("stories.md", open("tests/testing_data/all/data/stories.md", "rb"))),
              ('training_files', ("config.yml", open("tests/testing_data/all/config.yml", "rb"))))
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]


def test_upload_yml():
    files = (('training_files', ("nlu.yml", open("tests/testing_data/valid_yml/data/nlu.yml", "rb"))),
             ('training_files', ("domain.yml", open("tests/testing_data/valid_yml/domain.yml", "rb"))),
             ('training_files', ("stories.yml", open("tests/testing_data/valid_yml/data/stories.yml", "rb"))),
             ('training_files', ("config.yml", open("tests/testing_data/valid_yml/config.yml", "rb"))),
             (
             'training_files', ("http_action.yml", open("tests/testing_data/valid_yml/http_action.yml", "rb")))
             )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]


def test_train(monkeypatch):
    def mongo_store(*arge, **kwargs):
        return None

    def _mock_training_limit(*arge, **kwargs):
        return False

    monkeypatch.setattr(Utility, "get_local_mongo_store", mongo_store)
    monkeypatch.setattr(ModelProcessor, "is_daily_training_limit_exceeded", _mock_training_limit)

    response = client.post(
        f"/api/bot/{pytest.bot}/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Model training started."


def test_upload_limit_exceeded(monkeypatch):
    monkeypatch.setitem(Utility.environment['model']['data_importer'], 'limit_per_day', 2)
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=false",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files={'training_files': ("nlu.yml", open("tests/testing_data/yml_training_files/data/nlu.yml", "rb"))}
    )
    actual = response.json()
    assert actual["message"] == 'Daily limit exceeded.'
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert not actual["success"]


@responses.activate
def test_upload_using_event_overwrite(monkeypatch):
    token = Authentication.create_access_token(data={'sub': pytest.username})
    responses.add(
        responses.POST,
        "http://localhost/upload",
        status=200,
        match=[
        responses.json_params_matcher([{'name': 'BOT', 'value': pytest.bot}, {'name': 'USER', 'value': pytest.username}, {'name': 'IMPORT_DATA', 'value': '--import-data'}, {'name': 'OVERWRITE', 'value': '--overwrite'}])],
    )

    monkeypatch.setitem(Utility.environment['model']['data_importer'], 'event_url', "http://localhost/upload")

    def get_token(*args, **kwargs):
        return token

    monkeypatch.setattr(Authentication, "create_access_token", get_token)
    monkeypatch.setitem(Utility.environment['model']['data_importer'], "event_url", "http://localhost/upload")
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=(('training_files', ("nlu.yml", open("tests/testing_data/yml_training_files/data/nlu.yml", "rb"))),
               ('training_files', ("domain.yml", open("tests/testing_data/yml_training_files/domain.yml", "rb"))),
               (
               'training_files', ("stories.yml", open("tests/testing_data/yml_training_files/data/stories.yml", "rb"))),
               ('training_files', ("config.yml", open("tests/testing_data/yml_training_files/config.yml", "rb"))),
               (
                   'training_files',
                   ("http_action.yml", open("tests/testing_data/yml_training_files/http_action.yml", "rb")))
               )
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Upload in progress! Check logs."

    # update status
    log = ValidationLogs.objects(event_status=EVENT_STATUS.TASKSPAWNED.value).get()
    log.event_status = EVENT_STATUS.COMPLETED.value
    log.save()


@responses.activate
def test_upload_using_event_append(monkeypatch):
    token = Authentication.create_access_token(data={'sub': pytest.username})
    responses.add(
        responses.POST,
        "http://localhost/upload",
        status=200,
        match=[
        responses.json_params_matcher([{'name': 'BOT', 'value': pytest.bot}, {'name': 'USER', 'value': pytest.username}, {'name': 'IMPORT_DATA', 'value': '--import-data'}, {'name': 'OVERWRITE', 'value': ''}])],
    )

    monkeypatch.setitem(Utility.environment['model']['data_importer'], 'event_url', "http://localhost/upload")

    def get_token(*args, **kwargs):
        return token

    monkeypatch.setattr(Authentication, "create_access_token", get_token)
    monkeypatch.setitem(Utility.environment['model']['data_importer'], "event_url", "http://localhost/upload")
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=false",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=(('training_files', ("nlu.yml", open("tests/testing_data/yml_training_files/data/nlu.yml", "rb"))),
               ('training_files', ("domain.yml", open("tests/testing_data/yml_training_files/domain.yml", "rb"))),
               (
               'training_files', ("stories.yml", open("tests/testing_data/yml_training_files/data/stories.yml", "rb"))),
               ('training_files', ("config.yml", open("tests/testing_data/yml_training_files/config.yml", "rb"))),
               (
                   'training_files',
                   ("http_action.yml", open("tests/testing_data/yml_training_files/http_action.yml", "rb")))
               )
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Upload in progress! Check logs."


def test_get_data_importer_logs():
    response = client.get(
        f"/api/bot/{pytest.bot}/importer/logs",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 5
    assert actual['data'][0]['event_status'] == EVENT_STATUS.TASKSPAWNED.value
    assert set(actual['data'][0]['files_received']) == {'stories', 'nlu', 'domain', 'config', 'http_actions'}
    assert actual['data'][0]['is_data_uploaded']
    assert actual['data'][0]['start_timestamp']
    assert actual['data'][2]['start_timestamp']
    assert actual['data'][2]['end_timestamp']
    assert set(actual['data'][2]['files_received']) == {'stories', 'nlu', 'domain', 'config', 'http_actions'}
    del actual['data'][2]['start_timestamp']
    del actual['data'][2]['end_timestamp']
    del actual['data'][2]['files_received']
    assert actual['data'][2] == {'intents': {'count': 14, 'data': []}, 'utterances': {'count': 0, 'data': []},
                                 'rules': {'count': 1, 'data': []},
                                 'stories': {'count': 16, 'data': []}, 'training_examples': {'count': 192, 'data': []},
                                 'domain': {'intents_count': 19, 'actions_count': 26, 'slots_count': 9,
                                            'utterances_count': 13, 'forms_count': 2, 'entities_count': 8, 'data': []},
                                 'config': {'count': 0, 'data': []}, 'http_actions': {'count': 5, 'data': []},
                                 'is_data_uploaded': True, 'status': 'Success', 'exception': '', 'event_status': 'Completed'}
    assert actual['data'][3]['intents']['count'] == 16
    assert actual['data'][3]['intents']['data']
    assert actual['data'][3]['utterances']['count'] == 0
    assert actual['data'][3]['stories']['count'] == 16
    assert actual['data'][3]['stories']['data']
    assert actual['data'][3]['training_examples'] == {'count': 292, 'data': []}
    assert actual['data'][3]['domain'] == {'intents_count': 29, 'actions_count': 38, 'slots_count': 8, 'utterances_count': 25, 'forms_count': 2, 'entities_count': 8, 'data': []}
    assert actual['data'][3]['config'] == {'count': 0, 'data': []}
    assert actual['data'][3]['http_actions'] == {'count': 0, 'data': []}
    assert actual['data'][3]['is_data_uploaded']
    assert set(actual['data'][3]['files_received']) == {'stories', 'domain', 'config', 'nlu'}
    assert actual['data'][3]['status'] == 'Failure'
    assert actual['data'][3]['event_status'] == 'Completed'
    assert actual['data'][4]['rules']['count'] == 3
    assert not actual["message"]

    # update status for upload event
    log = ValidationLogs.objects(event_status=EVENT_STATUS.TASKSPAWNED.value).get()
    log.event_status = EVENT_STATUS.COMPLETED.value
    log.save()


def test_get_slots():
    response = client.get(
        f"/api/bot/{pytest.bot}/slots",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 9
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_get_intents():
    response = client.get(
        f"/api/bot/{pytest.bot}/intents",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 19
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_get_all_intents():
    response = client.get(
        f"/api/bot/{pytest.bot}/intents/all",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    print(actual['data'])
    assert len(actual["data"]) == 19
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_add_intents():
    response = client.post(
        f"/api/bot/{pytest.bot}/intents",
        json={"data": "happier"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Intent added successfully!"


def test_add_intents_duplicate():
    response = client.post(
        f"/api/bot/{pytest.bot}/intents",
        json={"data": "happier"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Intent already exists!"


def test_add_empty_intents():
    response = client.post(
        f"/api/bot/{pytest.bot}/intents",
        json={"data": ""},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Intent Name cannot be empty or blank spaces"


def test_get_training_examples():
    response = client.get(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 8
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_get_training_examples_empty_intent():
    response = client.get(
        f"/api/bot/{pytest.bot}/training_examples/ ",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 0
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_add_training_examples():
    response = client.post(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        json={"data": ["How do you do?"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"][0]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    response = client.get(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 9


def test_add_training_examples_duplicate():
    response = client.post(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        json={"data": ["How do you do?"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"][0]["message"] == "Training Example already exists!"
    assert actual["data"][0]["_id"] is None


def test_add_empty_training_examples():
    response = client.post(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        json={"data": [""]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert (
            actual["data"][0]["message"]
            == "Training Example cannot be empty or blank spaces"
    )
    assert actual["data"][0]["_id"] is None


def test_remove_training_examples():
    training_examples = client.get(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    assert len(training_examples["data"]) == 9
    response = client.delete(
        f"/api/bot/{pytest.bot}/training_examples",
        json={"data": training_examples["data"][0]["_id"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Training Example removed!"
    training_examples = client.get(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    assert len(training_examples["data"]) == 8


def test_remove_training_examples_empty_id():
    response = client.delete(
        f"/api/bot/{pytest.bot}/training_examples",
        json={"data": ""},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Unable to remove document"


def test_edit_training_examples():
    training_examples = client.get(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    response = client.put(
        f"/api/bot/{pytest.bot}/training_examples/greet/" + training_examples["data"][0]["_id"],
        json={"data": "hey, there"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Training Example updated!"


def test_get_responses():
    response = client.get(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 1
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_get_all_responses():
    response = client.get(
        f"/api/bot/{pytest.bot}/response/all",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual["data"])
    assert len(actual["data"]) == 13
    assert actual["data"][0]['name']
    assert actual["data"][0]['texts'][0]['text']
    assert not actual["data"][0]['customs']
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_add_response():
    response = client.post(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        json={"data": "Wow! How are you?"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Utterance added!"
    response = client.get(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 2


def test_add_response_upper_case():
    response = client.post(
        f"/api/bot/{pytest.bot}/response/Utter_Greet",
        json={"data": "Upper Greet Response"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Utterance added!"


def test_get_response_upper_case():
    response = client.get(
        f"/api/bot/{pytest.bot}/response/Utter_Greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 3

    response_lower = client.get(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual_lower = response_lower.json()
    assert len(actual_lower["data"]) == 3
    assert actual_lower["data"] == actual["data"]


def test_add_response_duplicate():
    response = client.post(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        json={"data": "Wow! How are you?"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Utterance already exists!"


def test_add_empty_response():
    response = client.post(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        json={"data": ""},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Utterance text cannot be empty or blank spaces"


def test_remove_response():
    training_examples = client.get(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    assert len(training_examples["data"]) == 3
    response = client.delete(
        f"/api/bot/{pytest.bot}/response/False",
        json={"data": training_examples["data"][0]["_id"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Utterance removed!"
    training_examples = client.get(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    assert len(training_examples["data"]) == 2


def test_remove_utterance_attached_to_story():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_remove_utterance_attached_to_story",
            "type": "STORY",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow added successfully"
    response = client.delete(
        f"/api/bot/{pytest.bot}/response/True",
        json={"data": "utter_greet"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Cannot remove utterance linked to story"


def test_remove_utterance():
    client.post(
        f"/api/bot/{pytest.bot}/response/utter_remove_utterance",
        json={"data": "this will be removed"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = client.delete(
        f"/api/bot/{pytest.bot}/response/True",
        json={"data": "utter_remove_utterance"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Utterance removed!"


def test_remove_utterance_non_existing():
    response = client.delete(
        f"/api/bot/{pytest.bot}/response/True",
        json={"data": "utter_delete_non_existing"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Utterance does not exists"


def test_remove_utterance_empty():
    response = client.delete(
        f"/api/bot/{pytest.bot}/response/True",
        json={"data": " "},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Utterance cannot be empty or spaces"


def test_remove_response_empty_id():
    response = client.delete(
        f"/api/bot/{pytest.bot}/response/False",
        json={"data": ""},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Utterance Id cannot be empty or spaces"


def test_remove_response_():
    training_examples = client.get(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    response = client.put(
        f"/api/bot/{pytest.bot}/response/utter_greet/" + training_examples["data"][0]["_id"],
        json={"data": "Hello, How are you!"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Utterance updated!"


def test_add_story():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "STORY",
            "steps": [
                {"name": "test_greet", "type": "INTENT"},
                {"name": "utter_test_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_story_invalid_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "TEST",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'ctx': {'enum_values': ['STORY', 'RULE']}, 'loc': ['body', 'type'],
                                  'msg': "value is not a valid enumeration member; permitted: 'STORY', 'RULE'",
                                  'type': 'type_error.enum'}]


def test_add_story_empty_event():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={"name": "test_add_story_empty_event", "type": "STORY", "steps": []},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {'loc': ['body', 'steps'], 'msg': 'Steps are required to form Flow', 'type': 'value_error'}]


def test_add_story_lone_intent():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_story_lone_intent",
            "type": "STORY",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
                {"name": "greet_again", "type": "INTENT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {'loc': ['body', 'steps'], 'msg': 'Intent should be followed by utterance or action', 'type': 'value_error'}]


def test_add_story_consecutive_intents():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_story_consecutive_intents",
            "type": "STORY",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {'loc': ['body', 'steps'], 'msg': 'Found 2 consecutive intents', 'type': 'value_error'}]


def test_add_story_multiple_actions():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_story_consecutive_actions",
            "type": "STORY",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "HTTP_ACTION"},
                {"name": "utter_greet_again", "type": "HTTP_ACTION"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow added successfully"


def test_add_story_utterance_as_first_step():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_story_consecutive_intents",
            "type": "STORY",
            "steps": [
                {"name": "greet", "type": "BOT"},
                {"name": "utter_greet", "type": "HTTP_ACTION"},
                {"name": "utter_greet_again", "type": "HTTP_ACTION"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {'loc': ['body', 'steps'], 'msg': 'First step should be an intent', 'type': 'value_error'}]


def test_add_story_missing_event_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "STORY",
            "steps": [{"name": "greet"}, {"name": "utter_greet", "type": "BOT"}],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"]
            == [{'loc': ['body', 'steps', 0, 'type'], 'msg': 'field required', 'type': 'value_error.missing'}]
    )


def test_add_story_invalid_event_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "STORY",
            "steps": [
                {"name": "greet", "type": "data"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"]
            == [{'ctx': {'enum_values': ['INTENT', 'BOT', 'HTTP_ACTION', 'ACTION']},
                 'loc': ['body', 'steps', 0, 'type'],
                 'msg': "value is not a valid enumeration member; permitted: 'INTENT', 'BOT', 'HTTP_ACTION', 'ACTION'",
                 'type': 'type_error.enum'}]
    )


def test_update_story():
    response = client.put(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "STORY",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_nonsense", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow updated successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_update_story_invalid_event_type():
    response = client.put(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "STORY",
            "steps": [
                {"name": "greet", "type": "data"},
                {"name": "utter_nonsense", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"]
            == [{'ctx': {'enum_values': ['INTENT', 'BOT', 'HTTP_ACTION', 'ACTION']},
                 'loc': ['body', 'steps', 0, 'type'],
                 'msg': "value is not a valid enumeration member; permitted: 'INTENT', 'BOT', 'HTTP_ACTION', 'ACTION'",
                 'type': 'type_error.enum'}]
    )


def test_delete_story():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path1",
            "type": "STORY",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet_delete", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow added successfully"
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.delete(
        f"/api/bot/{pytest.bot}/stories/test_path1/STORY",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow deleted successfully"


def test_delete_non_existing_story():
    response = client.delete(
        f"/api/bot/{pytest.bot}/stories/test_path2/STORY",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Flow does not exists"


def test_get_stories():
    response = client.get(
        f"/api/bot/{pytest.bot}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])


def test_get_utterance_from_intent():
    response = client.get(
        f"/api/bot/{pytest.bot}/utterance_from_intent/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["name"] == "utter_offer_help"
    assert actual["data"]["type"] == UTTERANCE_TYPE.BOT
    assert Utility.check_empty_string(actual["message"])


def test_get_utterance_from_not_exist_intent():
    response = client.get(
        f"/api/bot/{pytest.bot}/utterance_from_intent/greeting",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["name"] is None
    assert actual["data"]["type"] is None
    assert Utility.check_empty_string(actual["message"])


def test_train_on_updated_data(monkeypatch):
    def mongo_store(*arge, **kwargs):
        return None

    def _mock_training_limit(*arge, **kwargs):
        return False

    monkeypatch.setattr(Utility, "get_local_mongo_store", mongo_store)
    monkeypatch.setattr(ModelProcessor, "is_daily_training_limit_exceeded", _mock_training_limit)

    response = client.post(
        f"/api/bot/{pytest.bot}/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Model training started."


@pytest.fixture
def mock_is_training_inprogress_exception(monkeypatch):
    def _inprogress_execption_response(*args, **kwargs):
        raise AppException("Previous model training in progress.")

    monkeypatch.setattr(ModelProcessor, "is_training_inprogress", _inprogress_execption_response)


def test_train_inprogress(mock_is_training_inprogress_exception):
    response = client.post(
        f"/api/bot/{pytest.bot}/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"] == False
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == "Previous model training in progress."


@pytest.fixture
def mock_is_training_inprogress(monkeypatch):
    def _inprogress_response(*args, **kwargs):
        return False

    monkeypatch.setattr(ModelProcessor, "is_training_inprogress", _inprogress_response)


def test_train_daily_limit_exceed(mock_is_training_inprogress):
    response = client.post(
        f"/api/bot/{pytest.bot}/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == "Daily model training limit exceeded."


def test_get_model_training_history():
    response = client.get(
        f"/api/bot/{pytest.bot}/train/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"] is True
    assert actual["error_code"] == 0
    assert actual["data"]
    assert "training_history" in actual["data"]


def test_get_file_training_history():
    response = client.get(
        f"/api/bot/{pytest.bot}/data/generation/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"] is True
    assert actual["error_code"] == 0
    assert actual["data"]
    assert "training_history" in actual["data"]


def test_chat(monkeypatch):
    def mongo_store(*arge, **kwargs):
        return None

    monkeypatch.setattr(Utility, "get_local_mongo_store", mongo_store)
    monkeypatch.setitem(Utility.environment['action'], "url", None)
    response = client.post(
        f"/api/bot/{pytest.bot}/chat",
        json={"data": "Hi"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])


def test_chat_fetch_from_cache(monkeypatch):
    def mongo_store(*arge, **kwargs):
        return None

    monkeypatch.setattr(Utility, "get_local_mongo_store", mongo_store)
    monkeypatch.setitem(Utility.environment['action'], "url", None)
    response = client.post(
        f"/api/bot/{pytest.bot}/chat",
        json={"data": "Hi"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])


def test_chat_model_not_trained():
    response = client.post(
        "/api/auth/login",
        data={"username": "integration2@demo.ai", "password": "Welcome@1"},
    )

    token = response.json()
    response = client.get(
        "/api/account/bot",
        headers={"Authorization": token["data"]["token_type"] + " " + token["data"]["access_token"]},
    ).json()
    assert len(response['data']) == 1
    bot = response['data'][0]['_id']

    response = client.post(
        f"/api/bot/{bot}/chat",
        json={"data": "Hi"},
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"]
        },
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == "Bot has not been trained yet !"


def test_deploy_missing_configuration():
    response = client.post(
        f"/api/bot/{pytest.bot}/deploy",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Please configure the bot endpoint for deployment!"


def endpoint_response(*args, **kwargs):
    return {"bot_endpoint": {"url": "http://localhost:5000"}}


@pytest.fixture
def mock_endpoint(monkeypatch):
    monkeypatch.setattr(MongoProcessor, "get_endpoints", endpoint_response)


@pytest.fixture
def mock_endpoint_with_token(monkeypatch):
    def _endpoint_response(*args, **kwargs):
        return {
            "bot_endpoint": {
                "url": "http://localhost:5000",
                "token": "AGTSUDH!@#78JNKLD",
                "token_type": "Bearer",
            }
        }

    monkeypatch.setattr(MongoProcessor, "get_endpoints", _endpoint_response)


def test_deploy_connection_error(mock_endpoint):
    response = client.post(
        f"/api/bot/{pytest.bot}/deploy",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Host is not reachable"


@responses.activate
def test_deploy(mock_endpoint):
    responses.add(
        responses.PUT,
        "http://localhost:5000/model",
        status=204,
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/deploy",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Model was successfully replaced."


@responses.activate
def test_deployment_history():
    response = client.get(
        f"/api/bot/{pytest.bot}/deploy/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]['deployment_history']) == 3
    assert actual["message"] is None


@responses.activate
def test_deploy_with_token(mock_endpoint_with_token):
    responses.add(
        responses.PUT,
        "http://localhost:5000/model",
        json="Model was successfully replaced.",
        headers={"Content-type": "application/json",
                 "Accept": "text/plain",
                 "Authorization": "Bearer AGTSUDH!@#78JNKLD"},
        status=200,
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/deploy",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Model was successfully replaced."


@responses.activate
def test_deploy_bad_request(mock_endpoint):
    responses.add(
        responses.PUT,
        "http://localhost:5000/model",
        json={
            "version": "1.0.0",
            "status": "failure",
            "reason": "BadRequest",
            "code": 400,
        },
        status=200,
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/deploy",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "BadRequest"


@responses.activate
def test_deploy_server_error(mock_endpoint):
    responses.add(
        responses.PUT,
        "http://localhost:5000/model",
        json={
            "version": "1.0.0",
            "status": "ServerError",
            "message": "An unexpected error occurred.",
            "code": 500,
        },
        status=200,
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/deploy",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "An unexpected error occurred."


def test_integration_token():
    response = client.get(
        f"/api/auth/{pytest.bot}/integration/token",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    token = response.json()
    assert token["success"]
    assert token["error_code"] == 0
    assert token["data"]["access_token"]
    assert token["data"]["token_type"]
    assert (
            token["message"]
            == """It is your responsibility to keep the token secret.
        If leaked then other may have access to your system."""
    )
    response = client.get(
        f"/api/bot/{pytest.bot}/intents",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration",
        },
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 20
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])
    response = client.post(
        f"/api/bot/{pytest.bot}/intents",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration",
        },
        json={"data": "integration"},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Intent added successfully!"


def test_integration_token_missing_x_user():
    response = client.get(
        f"/api/auth/{pytest.bot}/integration/token",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["access_token"]
    assert actual["data"]["token_type"]
    assert (
            actual["message"]
            == """It is your responsibility to keep the token secret.
        If leaked then other may have access to your system."""
    )
    response = client.get(
        f"/api/bot/{pytest.bot}/intents",
        headers={
            "Authorization": actual["data"]["token_type"]
                             + " "
                             + actual["data"]["access_token"]
        },
    )
    actual = response.json()
    assert actual["data"] is None
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Alias user missing for integration"


@mongomock.patch(servers=(('localhost', 27019),))
def test_predict_intent(monkeypatch):
    monkeypatch.setitem(Utility.environment['database'], "url", "mongodb://localhost:27019")
    monkeypatch.setitem(Utility.environment['action'], "url", None)
    response = client.post(
        f"/api/bot/{pytest.bot}/intents/predict",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "Hi"},
    )

    actual = response.json()
    assert actual.get("data").get("intent")
    assert actual.get("data").get("confidence")


def test_predict_intent_error():
    response = client.post(
        "/api/auth/login",
        data={"username": "integration2@demo.ai", "password": "Welcome@1"},
    )
    token = response.json()

    response = client.get(
        "/api/account/bot",
        headers={"Authorization": token["data"]["token_type"] + " " + token["data"]["access_token"]},
    ).json()
    bot = response['data'][0]['_id']

    response = client.post(
        f"/api/bot/{bot}/intents/predict",
        json={"data": "Hi"},
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"]
        },
    )
    actual = response.json()
    assert actual["data"] is None
    assert actual["success"] is False
    assert actual["error_code"] == 422
    assert actual["message"] == "Bot has not been trained yet !"


@responses.activate
def test_augment_paraphrase_gpt():
    responses.add(
        responses.POST,
        url="http://localhost:8000/paraphrases/gpt",
        match=[responses.json_params_matcher(
            {"api_key": "MockKey", "data": ["Where is digite located?"], "engine": "davinci", "temperature": 0.75,
             "max_tokens": 100, "num_responses": 10})],
        json={
            "success": True,
            "data": {
                "paraphrases": ['Where is digite located?',
                                'Where is digite situated?']
            },
            "message": None,
            "error_code": 0,
        },
        status=200
    )
    response = client.post(
        "/api/augment/paraphrases/gpt",
        json={"data": ["Where is digite located?"], "api_key": "MockKey"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == {
        "paraphrases": ['Where is digite located?',
                        'Where is digite situated?']
    }
    assert Utility.check_empty_string(actual["message"])


def test_augment_paraphrase_gpt_validation():
    response = client.post(
        "/api/augment/paraphrases/gpt",
        json={"data": [], "api_key": "MockKey"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == [{'loc': ['body', 'data'], 'msg': 'Question Please!', 'type': 'value_error'}]

    response = client.post(
        "/api/augment/paraphrases/gpt",
        json={"data": ["hi", "hello", "thanks", "hello", "bye", "how are you"], "api_key": "MockKey"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == [
        {'loc': ['body', 'data'], 'msg': 'Max 5 Questions are allowed!', 'type': 'value_error'}]


@responses.activate
def test_augment_paraphrase_gpt_fail():
    key_error_message = "Incorrect API key provided: InvalidKey. You can find your API key at https://beta.openai.com."
    responses.add(
        responses.POST,
        url="http://localhost:8000/paraphrases/gpt",
        match=[responses.json_params_matcher(
            {"api_key": "InvalidKey", "data": ["Where is digite located?"], "engine": "davinci", "temperature": 0.75,
             "max_tokens": 100, "num_responses": 10})],
        json={
            "success": False,
            "data": None,
            "message": key_error_message,
        },
        status=200,
    )
    response = client.post(
        "/api/augment/paraphrases/gpt",
        json={"data": ["Where is digite located?"], "api_key": "InvalidKey"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert not actual["success"]
    assert actual["data"] is None
    assert actual["message"] == key_error_message


@responses.activate
def test_augment_paraphrase():
    responses.add(
        responses.POST,
        "http://localhost:8000/paraphrases",
        json={
            "success": True,
            "data": {
                "questions": ['Where is digite located?',
                              'Where is digite?',
                              'What is the location of digite?',
                              'Where is the digite located?',
                              'Where is it located?',
                              'What location is digite located?',
                              'Where is the digite?',
                              'where is digite located?',
                              'Where is digite situated?',
                              'digite is located where?']
            },
            "message": None,
            "error_code": 0,
        },
        status=200,
        match=[responses.json_params_matcher(["where is digite located?"])]
    )
    response = client.post(
        "/api/augment/paraphrases",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": ["where is digite located?"]},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])


def test_augment_paraphrase_no_of_questions():
    response = client.post(
        "/api/augment/paraphrases",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": []},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == [{'loc': ['body', 'data'], 'msg': 'Question Please!', 'type': 'value_error'}]

    response = client.post(
        "/api/augment/paraphrases",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": ["Hi", "Hello", "How are you", "Bye", "Thanks", "Welcome"]},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == [
        {'loc': ['body', 'data'], 'msg': 'Max 5 Questions are allowed!', 'type': 'value_error'}]


def test_get_user_details():
    response = client.get(
        "/api/user/details",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])


def test_download_data():
    response = client.get(
        f"/api/bot/{pytest.bot}/download/data",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    file_bytes = BytesIO(response.content)
    zip_file = ZipFile(file_bytes, mode='r')
    assert zip_file.filelist.__len__()
    zip_file.close()
    file_bytes.close()


def test_download_model():
    response = client.get(
        f"/api/bot/{pytest.bot}/download/model",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    d = response.headers['content-disposition']
    fname = re.findall("filename=(.+)", d)[0]
    file_bytes = BytesIO(response.content)
    tar = tarfile.open(fileobj=file_bytes, mode='r', name=fname)
    assert tar.members.__len__()
    tar.close()
    file_bytes.close()


def test_get_endpoint():
    response = client.get(
        f"/api/bot/{pytest.bot}/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual['data']
    assert actual['error_code'] == 0
    assert actual['message'] is None
    assert actual['success']


def test_save_endpoint_error():
    response = client.put(
        f"/api/bot/{pytest.bot}/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 422
    assert actual['message'] == [{'loc': ['body'], 'msg': 'field required', 'type': 'value_error.missing'}]
    assert not actual['success']


def test_save_empty_endpoint():
    response = client.put(
        f"/api/bot/{pytest.bot}/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={}
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 0
    assert actual['message'] == 'Endpoint saved successfully!'
    assert actual['success']


def test_save_endpoint(monkeypatch):
    def mongo_store(*arge, **kwargs):
        return None

    monkeypatch.setattr(Utility, "get_local_mongo_store", mongo_store)
    monkeypatch.setitem(Utility.environment['action'], "url", None)
    response = client.put(
        f"/api/bot/{pytest.bot}/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"bot_endpoint": {"url": "http://localhost:5005/"},
              "action_endpoint": {"url": "http://localhost:5000/"},
              "tracker_endpoint": {"url": "mongodb://localhost:27017", "db": "rasa"}}
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 0
    assert actual['message'] == 'Endpoint saved successfully!'
    assert actual['success']
    response = client.get(
        f"/api/bot/{pytest.bot}/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual['data']['endpoint'].get('bot_endpoint')
    assert actual['data']['endpoint'].get('action_endpoint')
    assert actual['data']['endpoint'].get('tracker_endpoint')


def test_get_templates():
    response = client.get(
        f"/api/bot/{pytest.bot}/templates/use-case",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert "Hi-Hello" in actual['data']['use-cases']
    assert actual['error_code'] == 0
    assert actual['message'] is None
    assert actual['success']


def test_set_templates():
    response = client.post(
        f"/api/bot/{pytest.bot}/templates/use-case",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "Hi-Hello"}
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 0
    assert actual['message'] == "Data applied!"
    assert actual['success']


def test_set_templates_invalid():
    response = client.post(
        f"/api/bot/{pytest.bot}/templates/use-case",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "Hi"}
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 422
    assert actual['message'] == "Invalid template!"
    assert not actual['success']


def test_reload_model(monkeypatch):
    def mongo_store(*arge, **kwargs):
        return None

    monkeypatch.setattr(Utility, "get_local_mongo_store", mongo_store)
    monkeypatch.setitem(Utility.environment['action'], "url", None)
    response = client.get(
        f"/api/bot/{pytest.bot}/model/reload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 0
    assert actual['message'] == "Reloading Model!"
    assert actual['success']


def test_get_config_templates():
    response = client.get(
        f"/api/bot/{pytest.bot}/templates/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert any("default" == template['name'] for template in actual['data']['config-templates'])
    assert actual['error_code'] == 0
    assert actual['message'] is None
    assert actual['success']


def test_set_config_templates():
    response = client.post(
        f"/api/bot/{pytest.bot}/templates/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "default"}
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 0
    assert actual['message'] == "Config applied!"
    assert actual['success']


def test_set_config_templates_invalid():
    response = client.post(
        f"/api/bot/{pytest.bot}/templates/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "test"}
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 422
    assert actual['message'] == "Invalid config!"
    assert not actual['success']


def test_get_config():
    response = client.get(
        f"/api/bot/{pytest.bot}/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert all(key in ["language", "pipeline", "policies"] for key in actual['data']['config'].keys())
    assert actual['error_code'] == 0
    assert actual['message'] is None
    assert actual['success']


def test_set_config():
    response = client.put(
        f"/api/bot/{pytest.bot}/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=read_config_file('./template/config/default.yml')
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 0
    assert actual['message'] == "Config saved!"
    assert actual['success']


def test_set_config_policy_error():
    data = read_config_file('./template/config/default.yml')
    data['policies'].append({"name": "TestPolicy"})
    response = client.put(
        f"/api/bot/{pytest.bot}/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=data
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 422
    assert actual[
               'message'] == "Invalid policy TestPolicy"
    assert not actual['success']


def test_set_config_pipeline_error():
    data = read_config_file('./template/config/default.yml')
    data['pipeline'].append({"name": "TestFeaturizer"})
    response = client.put(
        f"/api/bot/{pytest.bot}/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=data
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 422
    assert str(actual['message']).__contains__("Invalid component TestFeaturizer")
    assert not actual['success']


def test_set_config_pipeline_error_empty_policies():
    data = read_config_file('./template/config/default.yml')
    data['policies'] = []
    response = client.put(
        f"/api/bot/{pytest.bot}/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=data
    )

    actual = response.json()
    assert actual['data'] is None
    assert str(actual['message']).__contains__("You didn't define any policies")
    assert actual['error_code'] == 422
    assert not actual['success']


def test_delete_intent():
    client.post(
        f"/api/bot/{pytest.bot}/intents",
        json={"data": "happier"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = client.delete(
        f"/api/bot/{pytest.bot}/intents/happier/True",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 0
    assert actual['message'] == "Intent deleted!"
    assert actual['success']


def test_api_login_with_account_not_verified():
    AccountProcessor.EMAIL_ENABLED = True
    response = client.post(
        "/api/auth/login",
        data={"username": "integration@demo.ai", "password": "Welcome@1"},
    )
    actual = response.json()
    AccountProcessor.EMAIL_ENABLED = False

    assert not actual['success']
    assert actual['error_code'] == 422
    assert actual['data'] is None
    assert actual['message'] == 'Please verify your mail'


async def mock_smtp(*args, **kwargs):
    return None


def test_account_registration_with_confirmation(monkeypatch):
    monkeypatch.setattr(Utility, 'trigger_smtp', mock_smtp)
    AccountProcessor.EMAIL_ENABLED = True
    response = client.post(
        "/api/account/registration",
        json={
            "email": "integ1@gmail.com",
            "first_name": "Dem",
            "last_name": "User22",
            "password": "Welcome@1",
            "confirm_password": "Welcome@1",
            "account": "integration33",
            "bot": "integration33",
        },
    )
    actual = response.json()
    assert actual["message"] == "Account Registered! A confirmation link has been sent to your mail"
    assert actual['success']
    assert actual['error_code'] == 0
    assert actual['data'] is None

    response = client.post("/api/account/email/confirmation",
                           json={
                               'data': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtYWlsX2lkIjoiaW50ZWcxQGdtYWlsLmNvbSJ9.Ycs1ROb1w6MMsx2WTA4vFu3-jRO8LsXKCQEB3fkoU20'},
                           )
    actual = response.json()
    AccountProcessor.EMAIL_ENABLED = False

    assert actual['message'] == "Account Verified!"
    assert actual['data'] is None
    assert actual['success']
    assert actual['error_code'] == 0


def test_invalid_token_for_confirmation():
    response = client.post("/api/account/email/confirmation",
                           json={
                               'data': 'hello'},
                           )
    actual = response.json()

    assert actual['message'] == "Invalid token"
    assert actual['data'] is None
    assert not actual['success']
    assert actual['error_code'] == 422


def test_chat_with_different_bot_not_trained():
    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    pytest.bot_2 = response['data'][1]['_id']

    response = client.post(
        f"/api/bot/{pytest.bot_2}/chat",
        json={"data": "Hi"},
        headers={
            "Authorization": pytest.token_type + " " + pytest.access_token
        },
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == "Bot has not been trained yet !"


def test_add_intents_no_bot():
    response = client.post(
        "/api/bot/ /intents",
        json={"data": "greet"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Bot is required'


def test_add_intents_not_authorised():
    response = client.post(
        "/api/bot/5ea8127db7c285f4055129a4/intents",
        json={"data": "greet"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Access denied for bot'


def test_add_intents_inactive_bot(monkeypatch):
    def _mock_bot(*args, **kwargs):
        return {'status': False}

    async def _mock_user(*args, **kwargs):
        return User(
            email='test',
            first_name='test',
            last_name='test',
            account=2,
            status=True,
            is_integration_user=False,
            bot=['5ea8127db7c285f4055129a4', '5ea8127db7c285f4055129a5'])

    monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot)
    monkeypatch.setattr(Authentication, 'get_current_user', _mock_user)

    response = client.post(
        "/api/bot/5ea8127db7c285f4055129a4/intents",
        json={"data": "greet"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Inactive Bot Please contact system admin!'


def test_add_intents_invalid_auth_token():
    token = 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJuYW1lIjoiSm9obiBEb2UiLCJpYXQiOjE1MTYyMzkwMjJ9.hqWGSaFpvbrXkOWc6lrnffhNWR19W_S1YKFBx2arWBk'
    response = client.post(
        "/api/bot/ /intents",
        json={"data": "greet"},
        headers={"Authorization": token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 401
    assert actual["message"] == "Could not validate credentials"


def test_add_intents_invalid_auth_token_2():
    token = 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9'
    response = client.post(
        "/api/bot/ /intents",
        json={"data": "greet"},
        headers={"Authorization": token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 401
    assert actual["message"] == "Could not validate credentials"


def test_add_intents_to_different_bot():
    response = client.post(
        f"/api/bot/{pytest.bot_2}/intents",
        json={"data": "greet"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Intent added successfully!"


def test_add_training_examples_to_different_bot():
    response = client.post(
        f"/api/bot/{pytest.bot_2}/training_examples/greet",
        json={"data": ["Hi"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"][0]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    response = client.get(
        f"/api/bot/{pytest.bot_2}/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 1


def test_add_response_different_bot():
    response = client.post(
        f"/api/bot/{pytest.bot_2}/response/utter_greet",
        json={"data": "Hi! How are you?"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Utterance added!"
    response = client.get(
        f"/api/bot/{pytest.bot_2}/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 1


def test_add_story_to_different_bot():
    response = client.post(
        f"/api/bot/{pytest.bot_2}/stories",
        json={
            "name": "greet user",
            "type": "STORY",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_train_on_different_bot(monkeypatch):
    def mongo_store(*arge, **kwargs):
        return None

    def _mock_training_limit(*arge, **kwargs):
        return False

    monkeypatch.setattr(Utility, "get_local_mongo_store", mongo_store)
    monkeypatch.setattr(ModelProcessor, "is_daily_training_limit_exceeded", _mock_training_limit)

    response = client.post(
        f"/api/bot/{pytest.bot_2}/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Model training started."


def test_chat_different_bot(monkeypatch):
    def mongo_store(*arge, **kwargs):
        return None

    monkeypatch.setattr(Utility, "get_local_mongo_store", mongo_store)
    monkeypatch.setitem(Utility.environment['action'], "url", None)
    response = client.post(
        f"/api/bot/{pytest.bot_2}/chat",
        json={"data": "Hi"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])


def test_delete_bot():
    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    bot = response['data'][1]['_id']

    response = client.delete(
        f"/api/account/bot/{bot}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response['message'] == 'Bot removed'
    assert response['error_code'] == 0
    assert response['success']


def test_login_for_verified():
    AccountProcessor.EMAIL_ENABLED = True
    response = client.post(
        "/api/auth/login",
        data={"username": "integ1@gmail.com", "password": "Welcome@1"},
    )
    actual = response.json()
    AccountProcessor.EMAIL_ENABLED = False

    assert actual["success"]
    assert actual["error_code"] == 0
    pytest.access_token = actual["data"]["access_token"]
    pytest.token_type = actual["data"]["token_type"]


def test_list_bots_for_different_user():
    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert len(response['data']) == 1
    pytest.bot = response['data'][0]['_id']


def test_reset_password_for_valid_id(monkeypatch):
    monkeypatch.setattr(Utility, 'trigger_smtp', mock_smtp)
    AccountProcessor.EMAIL_ENABLED = True
    response = client.post(
        "/api/account/password/reset",
        json={"data": "integ1@gmail.com"},
    )
    actual = response.json()
    AccountProcessor.EMAIL_ENABLED = False
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Success! A password reset link has been sent to your mail id"
    assert actual['data'] is None


def test_reset_password_for_invalid_id():
    AccountProcessor.EMAIL_ENABLED = True
    response = client.post(
        "/api/account/password/reset",
        json={"data": "sasha.41195@gmail.com"},
    )
    actual = response.json()
    AccountProcessor.EMAIL_ENABLED = False
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Error! There is no user with the following mail id"
    assert actual['data'] is None


def test_overwrite_password_for_matching_passwords(monkeypatch):
    monkeypatch.setattr(Utility, 'trigger_smtp', mock_smtp)
    response = client.post(
        "/api/account/password/change",
        json={
            "data": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtYWlsX2lkIjoiaW50ZWcxQGdtYWlsLmNvbSJ9.Ycs1ROb1w6MMsx2WTA4vFu3-jRO8LsXKCQEB3fkoU20",
            "password": "Welcome@2",
            "confirm_password": "Welcome@2"},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Success! Your password has been changed"
    assert actual['data'] is None


def test_login_new_password():
    response = client.post(
        "/api/auth/login",
        data={"username": "integ1@gmail.com", "password": "Welcome@2"},
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    pytest.access_token = actual["data"]["access_token"]
    pytest.token_type = actual["data"]["token_type"]


def test_list_bots_for_different_user_2():
    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert len(response['data']) == 1
    pytest.bot = response['data'][0]['_id']


def test_login_old_password():
    response = client.post(
        "/api/auth/login",
        data={"username": "integ1@gmail.com", "password": "Welcome@1"},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 401
    assert actual["message"] == 'Incorrect username or password'
    assert actual['data'] is None


def test_send_link_for_valid_id(monkeypatch):
    monkeypatch.setattr(Utility, 'trigger_smtp', mock_smtp)
    AccountProcessor.EMAIL_ENABLED = True
    response = client.post("/api/account/email/confirmation/link",
                           json={
                               'data': 'integration@demo.ai'},
                           )
    actual = response.json()
    AccountProcessor.EMAIL_ENABLED = False
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == 'Success! Confirmation link sent'
    assert actual['data'] is None


def test_send_link_for_confirmed_id():
    AccountProcessor.EMAIL_ENABLED = True
    response = client.post("/api/account/email/confirmation/link",
                           json={
                               'data': 'integ1@gmail.com'},
                           )
    actual = response.json()
    AccountProcessor.EMAIL_ENABLED = False
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Email already confirmed!'
    assert actual['data'] is None


def test_overwrite_password_for_non_matching_passwords():
    AccountProcessor.EMAIL_ENABLED = True
    response = client.post(
        "/api/account/password/change",
        json={
            "data": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtYWlsX2lkIjoiaW50ZWcxQGdtYWlsLmNvbSJ9.Ycs1ROb1w6MMsx2WTA4vFu3-jRO8LsXKCQEB3fkoU20",
            "password": "Welcome@2",
            "confirm_password": "Welcume@2"},
    )
    actual = response.json()
    AccountProcessor.EMAIL_ENABLED = False
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual['data'] is None


def test_add_and_delete_intents_by_integration_user():
    response = client.get(
        f"/api/auth/{pytest.bot}/integration/token",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    token = response.json()
    print(token)
    assert token["success"]
    assert token["error_code"] == 0
    assert token["data"]["access_token"]
    assert token["data"]["token_type"]

    response = client.post(
        f"/api/bot/{pytest.bot}/intents",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration",
        },
        json={"data": "integration_intent"},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Intent added successfully!"

    response = client.delete(
        f"/api/bot/{pytest.bot}/intents/integration_intent/True",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration1",
        },
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 0
    assert actual['message'] == "Intent deleted!"
    assert actual['success']


def test_add_non_Integration_Intent_and_delete_intent_by_integration_user():
    response = client.get(
        f"/api/auth/{pytest.bot}/integration/token",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    token = response.json()
    assert token["success"]
    assert token["error_code"] == 0
    assert token["data"]["access_token"]
    assert token["data"]["token_type"]

    response = client.post(
        f"/api/bot/{pytest.bot}/intents",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "non_integration_intent"},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Intent added successfully!"

    response = client.delete(
        f"/api/bot/{pytest.bot}/intents/non_integration_intent/True",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration1",
        },
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 422
    assert actual['message'] == "This intent cannot be deleted by an integration user"
    assert not actual['success']


def test_add_http_action_malformed_url():
    request_body = {
        "auth_token": "",
        "action_name": "new_http_action",
        "response": "",
        "http_url": "192.168.104.1/api/test",
        "request_method": "GET",
        "http_params_list": [{
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testValue1"
        }]
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_add_http_action_missing_parameters():
    request_body = {
        "auth_token": "",
        "action_name": "new_http_action2",
        "response": "",
        "http_url": "http://www.google.com",
        "request_method": "put",
        "http_params_list": [{
            "key": "",
            "parameter_type": "",
            "value": ""
        }]
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_add_http_action_invalid_req_method():
    request_body = {
        "auth_token": "",
        "action_name": "new_http_action",
        "response": "",
        "http_url": "http://www.google.com",
        "request_method": "TUP",
        "http_params_list": [{
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testValue1"
        }]
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_add_http_action_no_action_name():
    request_body = {
        "auth_token": "",
        "action_name": "",
        "response": "string",
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": [{
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testValue1"
        }]
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_add_http_action_no_token():
    request_body = {
        "auth_token": "",
        "action_name": "test_add_http_action_no_token",
        "response": "string",
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": [{
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testValue1"
        }]
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]


def test_add_http_action_with_sender_id_parameter_type():
    request_body = {
        "auth_token": "",
        "action_name": "test_add_http_action_with_sender_id_parameter_type",
        "response": "string",
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": [{
            "key": "testParam1",
            "parameter_type": "sender_id",
            "value": "testValue1"
        }, {
            "key": "testParam2",
            "parameter_type": "slot",
            "value": "testValue2"
        }]
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]


def test_add_http_action_invalid_parameter_type():
    request_body = {
        "auth_token": "",
        "action_name": "test_add_http_action_with_sender_id_parameter_type",
        "response": "string",
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": [{
            "key": "testParam1",
            "parameter_type": "val",
            "value": "testValue1"
        }]
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    print(actual)
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_add_http_action_with_token():
    request_body = {
        "auth_token": "bearer dfiuhdfishifoshfoishnfoshfnsifjfs",
        "action_name": "test_add_http_action_with_token_and_story",
        "response": "string",
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": [{
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testValue1"
        }, {
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testValue1"
        }, {
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testValue1"
        }]
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/httpaction/test_add_http_action_with_token_and_story",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual['data']["response"] == "string"
    assert actual['data']["auth_token"] == "bearer dfiuhdfishifoshfoishnfoshfnsifjfs"
    assert actual['data']["http_url"] == "http://www.google.com"
    assert actual['data']["request_method"] == "GET"
    assert len(actual['data']["params_list"]) == 3
    assert actual["success"]


def test_add_http_action_no_params():
    request_body = {
        "auth_token": "",
        "action_name": "test_add_http_action_no_params",
        "response": "string",
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": []
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]


def test_add_http_action_existing():
    request_body = {
        "auth_token": "",
        "action_name": "test_add_http_action_existing",
        "response": "string",
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": [{
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testValue1"
        }]
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_get_http_action_non_exisitng():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/httpaction/never_added",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] is not None
    assert not actual["success"]


def test_update_http_action():
    request_body = {
        "auth_token": "",
        "action_name": "test_update_http_action",
        "response": "",
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": [{
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testValue1"
        }]
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    request_body = {
        "auth_token": "bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf",
        "action_name": "test_update_http_action",
        "response": "json",
        "http_url": "http://www.alphabet.com",
        "request_method": "POST",
        "http_params_list": [{
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testValue1"
        }, {
            "key": "testParam2",
            "parameter_type": "slot",
            "value": "testValue1"
        }]
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/httpaction/test_update_http_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual['data']["response"] == "json"
    assert actual['data']["auth_token"] == "bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf"
    assert actual['data']["http_url"] == "http://www.alphabet.com"
    assert actual['data']["request_method"] == "POST"
    assert len(actual['data']["params_list"]) == 2
    assert actual['data']["params_list"][0]['key'] == 'testParam1'
    assert actual['data']["params_list"][0]['parameter_type'] == 'value'
    assert actual['data']["params_list"][0]['value'] == 'testValue1'
    assert actual["success"]


def test_update_http_action_wrong_parameter():
    request_body = {
        "auth_token": "",
        "action_name": "test_update_http_action_6",
        "response": "",
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": [{
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testValue1"
        }]
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    request_body = {
        "auth_token": "bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf",
        "action_name": "test_update_http_action_6",
        "response": "json",
        "http_url": "http://www.alphabet.com",
        "request_method": "POST",
        "http_params_list": [{
            "key": "testParam1",
            "parameter_type": "val",
            "value": "testValue1"
        }, {
            "key": "testParam2",
            "parameter_type": "slot",
            "value": "testValue1"
        }]
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_update_http_action_non_existing():
    request_body = {
        "auth_token": "",
        "action_name": "test_update_http_action_non_existing",
        "response": "",
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": []
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    request_body = {
        "auth_token": "bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf",
        "action_name": "test_update_http_action_non_existing_new",
        "response": "json",
        "http_url": "http://www.alphabet.com",
        "request_method": "POST",
        "http_params_list": [{
            "key": "param1",
            "value": "value1",
            "parameter_type": "value"},
            {
                "key": "param2",
                "value": "value2",
                "parameter_type": "slot"}]
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_delete_http_action():
    request_body = {
        "auth_token": "",
        "action_name": "test_delete_http_action",
        "response": "",
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": []
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = client.delete(
        url=f"/api/bot/{pytest.bot}/action/httpaction/test_delete_http_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]


def test_delete_http_action_non_existing():
    request_body = {
        "auth_token": "",
        "action_name": "new_http_action4",
        "response": "",
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": []
    }

    client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = client.delete(
        url=f"/api/bot/{pytest.bot}/action/httpaction/new_http_action_never_added",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_list_actions():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path_action",
            "type": "STORY",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "action_greet", "type": "ACTION"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow added successfully"
    assert actual['data']["_id"]
    assert actual["success"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/actions",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])
    assert actual['data'] == ["action_greet"]
    assert actual["success"]


@responses.activate
def test_train_using_event(monkeypatch):
    responses.add(
        responses.POST,
        "http://localhost/train",
        status=200
    )
    monkeypatch.setitem(Utility.environment['model']['train'], "event_url", "http://localhost/train")
    response = client.post(
        f"/api/bot/{pytest.bot}/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Model training started."


def test_update_training_data_generator_status(monkeypatch):
    request_body = {
        "status": EVENT_STATUS.INITIATED
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/update/data/generator/status",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Status updated successfully!"


def test_get_training_data_history(monkeypatch):
    response = client.get(
        f"/api/bot/{pytest.bot}/data/generation/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    response = actual["data"]
    assert response is not None
    response['status'] = 'Initiated'
    assert actual["message"] is None


def test_update_training_data_generator_status_completed(monkeypatch):
    training_data = [{
        "intent": "intent1_test_add_training_data",
        "training_examples": ["example1", "example2"],
        "response": "response1"},
        {"intent": "intent2_test_add_training_data",
         "training_examples": ["example3", "example4"],
         "response": "response2"}]
    request_body = {
        "status": EVENT_STATUS.COMPLETED,
        "response": training_data
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/update/data/generator/status",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Status updated successfully!"


def test_update_training_data_generator_wrong_status(monkeypatch):
    training_data = [{
        "intent": "intent1_test_add_training_data",
        "training_examples": ["example1", "example2"],
        "response": "response1"},
        {"intent": "intent2_test_add_training_data",
         "training_examples": ["example3", "example4"],
         "response": "response2"}]
    request_body = {
        "status": "test",
        "response": training_data
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/update/data/generator/status",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 422
    assert str(actual['message']).__contains__("value is not a valid enumeration member")
    assert not actual['success']


def test_add_training_data(monkeypatch):
    response = client.get(
        f"/api/bot/{pytest.bot}/data/generation/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    response = actual["data"]
    assert response is not None
    response['status'] = 'Initiated'
    assert actual["message"] is None
    print(response)
    doc_id = response['training_history'][0]['_id']
    training_data = {
        "history_id": doc_id,
        "training_data": [{
            "intent": "intent1_test_add_training_data",
            "training_examples": ["example1", "example2"],
            "response": "response1"},
            {"intent": "intent2_test_add_training_data",
             "training_examples": ["example3", "example4"],
             "response": "response2"}]}
    response = client.post(
        f"/api/bot/{pytest.bot}/data/bulk",
        json=training_data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is not None
    assert actual["message"] == "Training data added successfully!"

    assert Intents.objects(name="intent1_test_add_training_data").get() is not None
    assert Intents.objects(name="intent2_test_add_training_data").get() is not None
    training_examples = list(TrainingExamples.objects(intent="intent1_test_add_training_data"))
    assert training_examples is not None
    assert len(training_examples) == 2
    training_examples = list(TrainingExamples.objects(intent="intent2_test_add_training_data"))
    assert len(training_examples) == 2
    assert Responses.objects(name="utter_intent1_test_add_training_data") is not None
    assert Responses.objects(name="utter_intent2_test_add_training_data") is not None
    story = Stories.objects(block_name="path_intent1_test_add_training_data").get()
    assert story is not None
    assert story['events'][0]['name'] == 'intent1_test_add_training_data'
    assert story['events'][0]['type'] == StoryEventType.user
    assert story['events'][1]['name'] == "utter_intent1_test_add_training_data"
    assert story['events'][1]['type'] == StoryEventType.action
    story = Stories.objects(block_name="path_intent2_test_add_training_data").get()
    assert story is not None
    assert story['events'][0]['name'] == 'intent2_test_add_training_data'
    assert story['events'][0]['type'] == StoryEventType.user
    assert story['events'][1]['name'] == "utter_intent2_test_add_training_data"
    assert story['events'][1]['type'] == StoryEventType.action


def test_get_training_data_history_1(monkeypatch):
    response = client.get(
        f"/api/bot/{pytest.bot}/data/generation/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    training_data = actual["data"]['training_history'][0]

    assert training_data['status'] == EVENT_STATUS.COMPLETED.value
    end_timestamp = training_data['end_timestamp']
    assert end_timestamp is not None
    assert training_data['last_update_timestamp'] == end_timestamp
    response = training_data['response']
    assert response is not None
    assert response[0]['intent'] == 'intent1_test_add_training_data'
    assert response[0]['training_examples'][0]['training_example'] == "example1"
    assert response[0]['training_examples'][0]['is_persisted']
    assert response[0]['training_examples'][1]['training_example'] == "example2"
    assert response[0]['training_examples'][1]['is_persisted']
    assert response[0]['response'] == 'response1'
    assert response[1]['intent'] == 'intent2_test_add_training_data'
    assert response[1]['training_examples'][0]['training_example'] == "example3"
    assert response[1]['training_examples'][0]['is_persisted']
    assert response[1]['training_examples'][1]['training_example'] == "example4"
    assert response[1]['training_examples'][1]['is_persisted']
    assert response[1]['response'] == 'response2'


def test_update_training_data_generator_status_exception(monkeypatch):
    request_body = {
        "status": EVENT_STATUS.INITIATED,
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/update/data/generator/status",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Status updated successfully!"

    request_body = {
        "status": EVENT_STATUS.FAIL,
        "exception": 'Exception message'
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/update/data/generator/status",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Status updated successfully!"


def test_get_training_data_history_2(monkeypatch):
    response = client.get(
        f"/api/bot/{pytest.bot}/data/generation/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    training_data = actual["data"]['training_history'][0]
    assert training_data['status'] == EVENT_STATUS.FAIL.value
    end_timestamp = training_data['end_timestamp']
    assert end_timestamp is not None
    assert training_data['last_update_timestamp'] == end_timestamp
    assert training_data['exception'] == 'Exception message'


def test_fetch_latest(monkeypatch):
    request_body = {
        "status": EVENT_STATUS.INITIATED,
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/update/data/generator/status",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/data/generation/latest",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    print(actual["data"])
    assert actual["data"]['status'] == EVENT_STATUS.INITIATED.value
    assert actual["message"] is None


async def mock_upload(doc):
    if not (doc.filename.lower().endswith('.pdf') or doc.filename.lower().endswith('.docx')):
        raise AppException("Invalid File Format")


@pytest.fixture
def mock_file_upload(monkeypatch):
    def _in_progress_mock(*args, **kwargs):
        return None

    def _daily_limit_mock(*args, **kwargs):
        return None

    def _set_status_mock(*args, **kwargs):
        return None

    def _train_data_gen(*args, **kwargs):
        return None

    monkeypatch.setattr(TrainingDataGenerationProcessor, "is_in_progress", _in_progress_mock)
    monkeypatch.setattr(TrainingDataGenerationProcessor, "check_data_generation_limit", _daily_limit_mock)
    monkeypatch.setattr(TrainingDataGenerationProcessor, "set_status", _set_status_mock)
    monkeypatch.setattr(Utility, "trigger_data_generation_event", _train_data_gen)


def test_file_upload_docx(mock_file_upload, monkeypatch):
    monkeypatch.setattr(Utility, "upload_document", mock_upload)

    response = client.post(
        f"/api/bot/{pytest.bot}/upload/data_generation/file",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files={"doc": (
            "tests/testing_data/file_data/sample1.docx",
            open("tests/testing_data/file_data/sample1.docx", "rb"))})

    actual = response.json()
    assert actual["message"] == "File uploaded successfully and training data generation has begun"
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]


def test_file_upload_pdf(mock_file_upload, monkeypatch):
    monkeypatch.setattr(Utility, "upload_document", mock_upload)

    response = client.post(
        f"/api/bot/{pytest.bot}/upload/data_generation/file",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files={"doc": (
            "tests/testing_data/file_data/sample1.pdf",
            open("tests/testing_data/file_data/sample1.pdf", "rb"))})

    actual = response.json()
    assert actual["message"] == "File uploaded successfully and training data generation has begun"
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]


def test_file_upload_error(mock_file_upload, monkeypatch):
    monkeypatch.setattr(Utility, "upload_document", mock_upload)

    response = client.post(
        f"/api/bot/{pytest.bot}/upload/data_generation/file",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files={"doc": (
            "nlu.md",
            open("tests/testing_data/all/data/nlu.md", "rb"))})

    actual = response.json()
    assert actual["message"] == "Invalid File Format"
    assert actual["error_code"] == 422
    assert not actual["success"]


def test_list_action_server_logs_empty():
    response = client.get(
        f"/api/bot/{pytest.bot}/actions/logs",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token})

    actual = response.json()
    assert actual['data']['logs'] == []
    assert actual['data']['total'] == 0


def test_list_action_server_logs():
    bot = pytest.bot
    bot_2 = "integration2"
    request_params = {"key": "value", "key2": "value2"}
    expected_intents = ["intent13", "intent11", "intent9", "intent8", "intent7", "intent6", "intent5",
                        "intent4", "intent3", "intent2"]
    HttpActionLog(intent="intent1", action="http_action", sender="sender_id", timestamp='2021-04-05T07:59:08.771000',
                  request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot).save()
    HttpActionLog(intent="intent2", action="http_action", sender="sender_id",
                  url="http://kairon-api.digite.com/api/bot",
                  request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot,
                  status="FAILURE").save()
    HttpActionLog(intent="intent1", action="http_action", sender="sender_id",
                  request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot_2).save()
    HttpActionLog(intent="intent3", action="http_action", sender="sender_id",
                  request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot,
                  status="FAILURE").save()
    HttpActionLog(intent="intent4", action="http_action", sender="sender_id",
                  request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot).save()
    HttpActionLog(intent="intent5", action="http_action", sender="sender_id",
                  request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot,
                  status="FAILURE").save()
    HttpActionLog(intent="intent6", action="http_action", sender="sender_id",
                  request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot).save()
    HttpActionLog(intent="intent7", action="http_action", sender="sender_id",
                  request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot).save()
    HttpActionLog(intent="intent8", action="http_action", sender="sender_id",
                  request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot).save()
    HttpActionLog(intent="intent9", action="http_action", sender="sender_id",
                  request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot).save()
    HttpActionLog(intent="intent10", action="http_action", sender="sender_id",
                  request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot_2).save()
    HttpActionLog(intent="intent11", action="http_action", sender="sender_id",
                  request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot).save()
    HttpActionLog(intent="intent12", action="http_action", sender="sender_id",
                  request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot_2,
                  status="FAILURE").save()
    HttpActionLog(intent="intent13", action="http_action", sender="sender_id_13",
                  request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot,
                  status="FAILURE").save()
    response = client.get(
        f"/api/bot/{pytest.bot}/actions/logs",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token})

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"]
    print(actual['data'])
    assert len(actual['data']['logs']) == 10
    assert actual['data']['total'] == 11
    assert [log['intent'] in expected_intents for log in actual['data']['logs']]
    assert actual['data']['logs'][0]['action'] == "http_action"
    assert any([log['request_params'] == request_params for log in actual['data']['logs']])
    assert any([log['sender'] == "sender_id_13" for log in actual['data']['logs']])
    assert any([log['bot_response'] == "Bot Response" for log in actual['data']['logs']])
    assert any([log['api_response'] == "Response" for log in actual['data']['logs']])
    assert any([log['status'] == "FAILURE" for log in actual['data']['logs']])
    assert any([log['status'] == "SUCCESS" for log in actual['data']['logs']])

    response = client.get(
        f"/api/bot/{pytest.bot}/actions/logs?start_idx=0&page_size=15",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token})
    actual = response.json()
    assert len(actual['data']['logs']) == 11
    assert actual['data']['total'] == 11

    response = client.get(
        f"/api/bot/{pytest.bot}/actions/logs?start_idx=10&page_size=1",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token})
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"]
    assert len(actual['data']['logs']) == 1
    assert actual['data']['total'] == 11


def test_add_training_data_invalid_id(monkeypatch):
    request_body = {
        "status": EVENT_STATUS.INITIATED
    }
    client.put(
        f"/api/bot/{pytest.bot}/update/data/generator/status",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = client.get(
        f"/api/bot/{pytest.bot}/data/generation/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    response = actual["data"]
    assert response is not None
    response['status'] = 'Initiated'
    assert actual["message"] is None
    doc_id = response['training_history'][0]['_id']
    training_data = {
        "history_id": doc_id,
        "training_data": [{
            "intent": "intent1_test_add_training_data",
            "training_examples": ["example1", "example2"],
            "response": "response1"},
            {"intent": "intent2_test_add_training_data",
             "training_examples": ["example3", "example4"],
             "response": "response2"}]}
    response = client.post(
        f"/api/bot/{pytest.bot}/data/bulk",
        json=training_data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == "No Training Data Generated"


def test_feedback():
    request = {
        'rating': 5.0, 'scale': 5.0, 'feedback': 'The product is better than rasa.'
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/feedback",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["data"]
    assert actual["message"] == 'Thanks for your feedback!'


def test_add_rule():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "RULE",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow added successfully"
    assert actual["data"]["_id"]


def test_add_rule_invalid_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "TEST",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'ctx': {'enum_values': ['STORY', 'RULE']}, 'loc': ['body', 'type'],
                                  'msg': "value is not a valid enumeration member; permitted: 'STORY', 'RULE'",
                                  'type': 'type_error.enum'}]


def test_add_rule_empty_event():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={"name": "test_add_rule_empty_event", "type": "RULE", "steps": []},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {'loc': ['body', 'steps'], 'msg': 'Steps are required to form Flow', 'type': 'value_error'}]


def test_add_rule_lone_intent():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_rule_lone_intent",
            "type": "RULE",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
                {"name": "greet_again", "type": "INTENT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {'loc': ['body', 'steps'], 'msg': 'Intent should be followed by utterance or action', 'type': 'value_error'}]


def test_add_rule_consecutive_intents():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_rule_consecutive_intents",
            "type": "RULE",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {'loc': ['body', 'steps'], 'msg': 'Found 2 consecutive intents', 'type': 'value_error'}]


def test_add_rule_multiple_actions():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_rule_consecutive_actions",
            "type": "RULE",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "HTTP_ACTION"},
                {"name": "utter_greet_again", "type": "HTTP_ACTION"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow added successfully"


def test_add_rule_utterance_as_first_step():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_rule_consecutive_intents",
            "type": "RULE",
            "steps": [
                {"name": "greet", "type": "BOT"},
                {"name": "utter_greet", "type": "HTTP_ACTION"},
                {"name": "utter_greet_again", "type": "HTTP_ACTION"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {'loc': ['body', 'steps'], 'msg': 'First step should be an intent', 'type': 'value_error'}]


def test_add_rule_missing_event_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "RULE",
            "steps": [{"name": "greet"}, {"name": "utter_greet", "type": "BOT"}],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"]
            == [{'loc': ['body', 'steps', 0, 'type'], 'msg': 'field required', 'type': 'value_error.missing'}]
    )


def test_add_rule_invalid_event_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "RULE",
            "steps": [
                {"name": "greet", "type": "data"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"]
            == [{'ctx': {'enum_values': ['INTENT', 'BOT', 'HTTP_ACTION', 'ACTION']},
                 'loc': ['body', 'steps', 0, 'type'],
                 'msg': "value is not a valid enumeration member; permitted: 'INTENT', 'BOT', 'HTTP_ACTION', 'ACTION'",
                 'type': 'type_error.enum'}]
    )


def test_update_rule():
    response = client.put(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "RULE",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_nonsense", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow updated successfully"
    assert actual["data"]["_id"]


def test_update_rule_invalid_event_type():
    response = client.put(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "RULE",
            "steps": [
                {"name": "greet", "type": "data"},
                {"name": "utter_nonsense", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"]
            == [{'ctx': {'enum_values': ['INTENT', 'BOT', 'HTTP_ACTION', 'ACTION']},
                 'loc': ['body', 'steps', 0, 'type'],
                 'msg': "value is not a valid enumeration member; permitted: 'INTENT', 'BOT', 'HTTP_ACTION', 'ACTION'",
                 'type': 'type_error.enum'}]
    )


def test_delete_rule():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path1",
            "type": "RULE",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow added successfully"

    response = client.delete(
        f"/api/bot/{pytest.bot}/stories/test_path1/RULE",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow deleted successfully"


def test_delete_non_existing_rule():
    response = client.delete(
        f"/api/bot/{pytest.bot}/stories/test_path2/RULE",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Flow does not exists"


def test_add_rule_with_multiple_intents():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "RULE",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
                {"name": "location", "type": "INTENT"},
                {"name": "utter_location", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'steps'], 'msg': "Found rules 'test_path' that contain more than intent.\nPlease use stories for this case", 'type': 'value_error'}]
    assert actual["data"] is None


def test_validate():
    response = client.post(
        f"/api/bot/{pytest.bot}/validate",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["data"]
    assert actual["message"] == 'Event triggered! Check logs.'


def test_upload_missing_data():
    files = (('training_files', ("domain.yml", BytesIO(open("tests/testing_data/all/domain.yml", "rb").read()))),
             ('training_files', ("stories.md", BytesIO(open("tests/testing_data/all/data/stories.md", "rb").read()))),
             ('training_files', ("config.yml", BytesIO(open("tests/testing_data/all/config.yml", "rb").read()))),
            )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == 'Upload in progress! Check logs.'
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]


def test_upload_valid_and_invalid_data():
    files = (('training_files', ("nlu_1.md", None)),
             ('training_files', ("domain_5.yml", open("tests/testing_data/all/domain.yml", "rb"))),
             ('training_files', ("stories.md", open("tests/testing_data/all/data/stories.md", "rb"))),
             ('training_files', ("config_6.yml", open("tests/testing_data/all/config.yml", "rb"))))
    response = client.post(
        f"/api/bot/{pytest.bot}/upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == 'Upload in progress! Check logs.'
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]


def test_upload_with_http_error():
    config = Utility.load_yaml("./tests/testing_data/yml_training_files/config.yml")
    config.get('pipeline').append({'name': "XYZ"})
    files = (('training_files', ("config.yml", json.dumps(config).encode())),
             ('training_files', ("http_action.yml", open("tests/testing_data/error/http_action.yml", "rb"))))

    response = client.post(
        f"/api/bot/{pytest.bot}/upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    response = client.get(
        f"/api/bot/{pytest.bot}/importer/logs",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 4
    assert actual['data'][0]['status'] == 'Failure'
    assert actual['data'][0]['event_status'] == EVENT_STATUS.COMPLETED.value
    assert actual['data'][0]['is_data_uploaded']
    assert actual['data'][0]['start_timestamp']
    assert actual['data'][0]['start_timestamp']
    assert actual['data'][0]['start_timestamp']
    assert actual['data'][0]['http_actions']['data'] == ['Required http action fields not found']
    assert actual['data'][0]['config']['data'] == ['Invalid component XYZ']


def test_upload_actions_and_config():
    files = (('training_files', ("config.yml", open("tests/testing_data/yml_training_files/config.yml", "rb"))),
             ('training_files', ("http_action.yml", open("tests/testing_data/yml_training_files/http_action.yml", "rb"))))

    response = client.post(
        f"/api/bot/{pytest.bot}/upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    response = client.get(
        f"/api/bot/{pytest.bot}/importer/logs",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 5
    assert actual['data'][0]['status'] == 'Success'
    assert actual['data'][0]['event_status'] == EVENT_STATUS.COMPLETED.value
    assert actual['data'][0]['is_data_uploaded']
    assert actual['data'][0]['start_timestamp']
    assert actual['data'][0]['start_timestamp']
    assert actual['data'][0]['start_timestamp']
    assert actual['data'][0]['http_actions']['count'] == 5
    assert not actual['data'][0]['http_actions']['data']
    assert not actual['data'][0]['config']['data']

    response = client.get(
        f"/api/bot/{pytest.bot}/action/httpaction",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 5


def test_get_editable_config():
    response = client.get(f"/api/bot/{pytest.bot}/config/properties",
                          headers={"Authorization": pytest.token_type + " " + pytest.access_token})
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual['data'] == {'nlu_confidence_threshold': 0.7, 'action_fallback': 'action_default_fallback', 'ted_epochs': 5, 'nlu_epochs': 5, 'response_epochs': 5}


def test_set_epoch_and_fallback():
    request = {"nlu_epochs": 200,
               "response_epochs": 300,
               "ted_epochs": 400,
               "nlu_confidence_threshold": 70,
               "action_fallback": "action_default_fallback"}
    response = client.post(
        f"/api/bot/{pytest.bot}/response/utter_default",
        json={"data": "Sorry I didnt get that. Can you rephrase?"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Utterance added!"

    response = client.put(f"/api/bot/{pytest.bot}/config/properties",
                          headers={"Authorization": pytest.token_type + " " + pytest.access_token},
                          json=request)
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == 'Config saved'


def test_get_config_all():
    response = client.get(f"/api/bot/{pytest.bot}/config/properties",
                          headers={"Authorization": pytest.token_type + " " + pytest.access_token})
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual['data']


def test_set_epoch_and_fallback_modify_action_only():
    request = {"nlu_confidence_threshold": 30,
               "action_fallback": "utter_default"}
    response = client.put(f"/api/bot/{pytest.bot}/config/properties",
                          headers={"Authorization": pytest.token_type + " " + pytest.access_token},
                          json=request)
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == 'Config saved'


def test_set_epoch_and_fallback_empty_pipeline_and_policies():
    request = {"nlu_confidence_threshold": 20}
    response = client.put(f"/api/bot/{pytest.bot}/config/properties",
                          headers={"Authorization": pytest.token_type + " " + pytest.access_token},
                          json=request)
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'nlu_confidence_threshold'], 'msg': 'Please choose a threshold between 30 and 90', 'type': 'value_error'}]


def test_set_epoch_and_fallback_empty_request():
    response = client.put(f"/api/bot/{pytest.bot}/config/properties",
                          headers={"Authorization": pytest.token_type + " " + pytest.access_token},
                          json={})
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'At least one field is required'


def test_set_epoch_and_fallback_negative_epochs():
    response = client.put(f"/api/bot/{pytest.bot}/config/properties",
                          headers={"Authorization": pytest.token_type + " " + pytest.access_token},
                          json={'nlu_epochs': 0})
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    print(actual["message"])
    assert actual["message"] == [{'loc': ['body', 'nlu_epochs'], 'msg': 'Choose a positive number as epochs', 'type': 'value_error'}]

    response = client.put(f"/api/bot/{pytest.bot}/config/properties",
                          headers={"Authorization": pytest.token_type + " " + pytest.access_token},
                          json={'response_epochs': -1, 'ted_epochs': 0, 'nlu_epochs': 200})
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"][0] == {'loc': ['body', 'response_epochs'], 'msg': 'Choose a positive number as epochs', 'type': 'value_error'}
    assert actual["message"][1] == {'loc': ['body', 'ted_epochs'], 'msg': 'Choose a positive number as epochs', 'type': 'value_error'}


def test_get_synonyms():
    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonyms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 0
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_add_synonyms():
    response = client.post(
        f"/api/bot/{pytest.bot}/entity/synonyms",
        json={"synonym": "bot_add", "value": ["any"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Synonym and values added successfully!"

    client.post(
        f"/api/bot/{pytest.bot}/entity/synonyms",
        json={"synonym": "bot_add", "value": ["any1"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = client.get(
            f"/api/bot/{pytest.bot}/entity/synonyms",
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )

    actual = response.json()
    assert actual['data'] == [{"any": "bot_add"}, {"any1": "bot_add"}]


def test_add_synonyms_duplicate():
    response = client.post(
        f"/api/bot/{pytest.bot}/entity/synonyms",
        json={"synonym": "bot_add", "value": ["any"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Synonym value already exists"


def test_add_synonyms_empty():
    response = client.post(
        f"/api/bot/{pytest.bot}/entity/synonyms",
        json={"synonym": "bot_add", "value": []},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"][0]['msg'] == "value field cannot be empty"


def test_edit_synonyms():
    response = client.put(
        f"/api/bot/{pytest.bot}/entity/synonyms",
        json={"synonym": "bot_add", "value": ["any4"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Synonym modified successfully!"

    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonyms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual['data'] == [{"any4": "bot_add"}]


def test_edit__empty_synonyms():
    response = client.put(
        f"/api/bot/{pytest.bot}/entity/synonyms",
        json={"synonym": "", "value": ["any4"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"][0]['msg'] == "synonym cannot be empty"


def test_delete_synonym():
    response = client.delete(
        f"/api/bot/{pytest.bot}/entity/synonyms/bot_add",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Synonym deleted!"

    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonyms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual['data'] == []


def test_add_synonyms_empty_value_element():
    response = client.post(
        f"/api/bot/{pytest.bot}/entity/synonyms",
        json={"synonym": "bot_add", "value": ['df','']},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"][0]['msg'] == "value cannot be an empty string"

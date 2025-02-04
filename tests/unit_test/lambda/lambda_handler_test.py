import os
import textwrap
from unittest.mock import patch

import pytest
import responses
from mongoengine import connect

from kairon import Utility

os.environ["system_file"] = "./tests/testing_data/system.yaml"
Utility.load_environment()
connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

from kairon.async_callback.lambda_function import lambda_handler


@pytest.fixture(scope="function")
def email_config():
    from pymongo import MongoClient

    client = MongoClient("mongodb://localhost/test")
    platform_db = client.get_database()

    email_config = platform_db.get_collection("email_action_config")

    email_config.insert_one({
        "action_name": "email_action",
        "smtp_url": "smtp.gmail.com",
        "smtp_port": 293,
        "smtp_password": {"value": "test"},
        "smtp_userid": {"value": "abcsdsldksl"},
        "from_email": {"value": "testadmin@test.com", "parameter_type": "value"},
        "subject": "test",
        "to_email": {"value": ["test@test.com", "test1@test.com"], "parameter_type": "value"},
        "response": "Email Triggered",
        "tls": True,
        "bot": "test_bot",
        "user": "test_user"
    })
    return email_config


@pytest.fixture(scope="function")
def callback_config():
    from pymongo import MongoClient
    from kairon.shared.callback.data_objects import encrypt_secret

    client = MongoClient("mongodb://localhost/test")
    platform_db = client.get_database()

    callback_config = platform_db.get_collection("callback_config")

    callback_action_config = {
        "name": "mng2",
        "pyscript_code": "state += 1\nbot_response = f'state -> {state}'",
        "validation_secret": encrypt_secret("0191703078f779199d90c1a91fe9839f"),
        "execution_mode": "sync",
        "expire_in": 0,
        "shorten_token": True,
        "token_hash": "0191703078f87a039906afc0a219dd5c",
        "standalone": True,
        "standalone_id_path": "data.id",
        "bot": "test_bot",
        "token_value": "gAAAAABmxKl5tT0UKwkqYi2n9yV1lFAAJKsZEM0G9w7kmN8NIYR9JKF1F9ecZoUY6P9kClUC_QnLXXGLa3T4Xugdry84ioaDtGF9laXcQl_82Fvs9KmKX8xfa4-rJs1cto1Jd6fqeGIT7mR3kn56_EliP83aGoCl_sk9B0-2gPDgt-EJZQ20l-3OaT-rhFoFanjKvRiE8e4xp9sdxxjgDWLbCF3kCtTqTtg6Wovw3mXZoVzxzNEUmd2OGZiO6IsIJJaU202w3CZ2rPnmK8I2aRGg8tMi_-ObOg=="
    }
    callback_config.insert_one(callback_action_config)
    return callback_config



def test_lambda_handler_with_simple_pyscript():
    source_code = '''
    from datetime import datetime, timedelta

    # Calculate the job trigger time 5 minutes from now
    trigger_time1 = datetime.utcnow() + timedelta(minutes=30)
    trigger_time2 = datetime.utcnow() + timedelta(minutes=2)

    id = generate_id()

    # Function to add the scheduled job (with the adjusted trigger time)
    # add_schedule_job('mng2', trigger_time1, {'user_rajan': 'test rajan sep 12'}, 'UTC', id, kwargs={'task_type': 'Callback'})
    # add_schedule_job('del_job1', trigger_time2, {'event_id': id}, 'UTC', kwargs={'task_type': 'Callback'})

    add_schedule_job('mng2', trigger_time1, {'user_rajan': 'test rajan sep 12'}, 'UTC', id)
    add_schedule_job('del_job1', trigger_time2, {'event_id': id}, 'UTC')
    '''
    source_code = '''
    bot_response = "This is testing pyscript"
    '''
    source_code = textwrap.dedent(source_code)
    event = {'source_code': source_code,
             'predefined_objects':
                 {'bot': '6744733ec16e7cda801e9783', 'sender_id': '917506075263',
                  'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
                  'slot': {},
                  'intent': 'k_multimedia_msg'
                  }
             }
    data = lambda_handler(event, None)
    print(data)
    assert data['body']['bot_response'] == 'This is testing pyscript'
    assert data == {
        'statusCode': 200,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': {
            'bot': '6744733ec16e7cda801e9783',
            'sender_id': '917506075263',
            'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
            'slot': {},
            'intent': 'k_multimedia_msg',
            'bot_response': 'This is testing pyscript'
        }
    }


def test_lambda_handler_without_predefined_objects():
    source_code = '''
    bot_response = "This is testing pyscript without predefined objects"
    '''
    source_code = textwrap.dedent(source_code)
    event = {'source_code': source_code}
    data = lambda_handler(event, None)
    print(data)
    assert data['body']['bot_response'] == "This is testing pyscript without predefined objects"
    assert data == {
        'statusCode': 200,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': {'bot_response': 'This is testing pyscript without predefined objects'}
    }


def test_lambda_handler_with_invalid_import():
    source_code = '''
    import numpy as np
    bot_response = "This is testing pyscript"
    '''
    source_code = textwrap.dedent(source_code)
    event = {'source_code': source_code,
             'predefined_objects':
                 {'bot': '6744733ec16e7cda801e9783', 'sender_id': '917506075263',
                  'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
                  'slot': {},
                  'intent': 'k_multimedia_msg'
                  }
             }
    data = lambda_handler(event, None)
    print(data)
    assert data['body'] == "import of 'numpy' is unauthorized"
    assert data == {
        'statusCode': 422,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': "import of 'numpy' is unauthorized"
    }


def test_lambda_handler_list_of_event_data():
    source_code = '''
    bot_response = "This is testing pyscript for list of event data"
    '''
    source_code = textwrap.dedent(source_code)
    event = [
        {"name": "SOURCE_CODE", "value": source_code},
        {"name": "PREDEFINED_OBJECTS", "value": {
            'bot': '6744733ec16e7cda801e9783', 'sender_id': '917506075263',
            'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
            'slot': {},
            'intent': 'k_multimedia_msg'
        }}
    ]
    data = lambda_handler(event, None)
    print(data)
    assert data['body']["bot_response"] == "This is testing pyscript for list of event data"
    assert data == {
        'statusCode': 200,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': {
            'bot': '6744733ec16e7cda801e9783',
            'sender_id': '917506075263',
            'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
            'slot': {},
            'intent': 'k_multimedia_msg',
            'bot_response': 'This is testing pyscript for list of event data'
        }
    }


def test_lambda_handler_with_datetime_in_event_data():
    from datetime import datetime

    source_code = '''
    bot_response = "This is testing pyscript with datetime in event data"
    '''
    source_code = textwrap.dedent(source_code)
    event = [
        {"name": "SOURCE_CODE", "value": source_code},
        {"name": "PREDEFINED_OBJECTS", "value": {
            'bot': '6744733ec16e7cda801e9783',
            'sender_id': '917506075263',
            'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
            'slot': {},
            'intent': 'k_multimedia_msg',
            'timestamp': datetime(2024, 2, 1, 15, 30, 0)
        }}
    ]
    data = lambda_handler(event, None)
    print(data)
    assert data['body']["bot_response"] == "This is testing pyscript with datetime in event data"
    assert data == {
        'statusCode': 200,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': {
            'bot': '6744733ec16e7cda801e9783',
            'sender_id': '917506075263',
            'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
            'slot': {},
            'intent': 'k_multimedia_msg',
            'timestamp': '02/01/2024, 15:30:00',
            'bot_response': 'This is testing pyscript with datetime in event data'
        }
    }


def test_lambda_handler_with_date_in_event_data():
    from datetime import date

    source_code = '''
    bot_response = "This is testing pyscript with date in event data"
    '''
    source_code = textwrap.dedent(source_code)
    event = [
        {"name": "SOURCE_CODE", "value": source_code},
        {"name": "PREDEFINED_OBJECTS", "value": {
            'bot': '6744733ec16e7cda801e9783',
            'sender_id': '917506075263',
            'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
            'slot': {},
            'intent': 'k_multimedia_msg',
            'date': date(2024, 2, 1)
        }}
    ]
    data = lambda_handler(event, None)
    print(data)
    assert data['body']["bot_response"] == "This is testing pyscript with date in event data"
    assert data == {
        'statusCode': 200,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': {
            'bot': '6744733ec16e7cda801e9783',
            'sender_id': '917506075263',
            'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
            'slot': {},
            'intent': 'k_multimedia_msg',
            'date': '2024-02-01',
            'bot_response': 'This is testing pyscript with date in event data'
        }
    }


def test_lambda_handler_with_response_in_event_data():
    from requests.models import Response

    response = Response()
    response.status_code = 200
    response._content = b'{"success": true, "message": "Data fetched successfully", "data": {}}'
    response.encoding = 'utf-8'

    source_code = '''
    bot_response = "This is testing pyscript with RESPONSE in event data"
    '''
    source_code = textwrap.dedent(source_code)
    event = [
        {"name": "SOURCE_CODE", "value": source_code},
        {"name": "PREDEFINED_OBJECTS", "value": {
            'bot': '6744733ec16e7cda801e9783',
            'sender_id': '917506075263',
            'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
            'slot': {},
            'intent': 'k_multimedia_msg',
            'response': response
        }}
    ]
    data = lambda_handler(event, None)
    print(data)
    assert data['body']["bot_response"] == "This is testing pyscript with RESPONSE in event data"
    assert data == {
        'statusCode': 200,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': {
            'bot': '6744733ec16e7cda801e9783',
            'sender_id': '917506075263',
            'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
            'slot': {},
            'intent': 'k_multimedia_msg',
            'response': '{"success": true, "message": "Data fetched successfully", "data": {}}',
            'bot_response': 'This is testing pyscript with RESPONSE in event data'
        }
    }


@patch("kairon.async_callback.mail.SMTP", autospec=True)
def test_lambda_handler_for_send_email(mock_smtp, email_config):
    source_code = '''
    send_email("email_action",    #email action name should be same as email action
           "hghuge@digite.com",          # from email
           "mahesh.sattala@digite.com",  # to email
           "New Order Placed",    #Subject
           "THIS IS EMAIL BODY"     #body
    )
    bot_response = "Email sent successfully!"
    '''
    source_code = textwrap.dedent(source_code)
    event = {'source_code': source_code,
             'predefined_objects':
                 {'bot': 'test_bot', 'sender_id': '917506075263',
                  'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
                  'slot': {},
                  'intent': 'k_multimedia_msg'
                  }
             }
    data = lambda_handler(event, None)
    assert data['body']['bot_response'] == 'Email sent successfully!'
    assert data == {
        'statusCode': 200,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': {
            'bot': 'test_bot',
            'sender_id': '917506075263',
            'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
            'slot': {},
            'intent': 'k_multimedia_msg',
            'bot_response': 'Email sent successfully!'
        }
    }
    email_config.delete_many({"bot": "test_bot", "action_name": "email_action"})


@patch("kairon.async_callback.mail.SMTP", autospec=True)
def test_lambda_handler_for_send_email_without_bot(mock_smtp, email_config):
    source_code = '''
    send_email("email_action",    #email action name should be same as email action
           "hghuge@digite.com",          # from email
           "mahesh.sattala@digite.com",  # to email
           "New Order Placed",    #Subject
           "THIS IS EMAIL BODY"     #body
    )
    bot_response = "Email sent successfully!"
    '''
    source_code = textwrap.dedent(source_code)
    event = {'source_code': source_code,
             'predefined_objects':
                 {'sender_id': '917506075263',
                  'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
                  'slot': {},
                  'intent': 'k_multimedia_msg'
                  }
             }
    data = lambda_handler(event, None)
    assert data['body'] == 'Missing bot id'
    assert data == {
        'statusCode': 422,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': 'Missing bot id'
    }
    email_config.delete_many({"bot": "test_bot", "action_name": "email_action"})


@responses.activate
@patch("kairon.async_callback.scheduler.uuid7")
def test_lambda_handler_with_add_schedule_job(mock_uuid7, callback_config):
    from uuid6 import uuid7

    test_generate_id = uuid7()
    mock_uuid7.return_value = test_generate_id
    server_url = Utility.environment["events"]["server_url"]
    pytest.test_generate_id = test_generate_id.hex
    http_url = f"{server_url}/api/events/dispatch/{pytest.test_generate_id}"
    responses.add(
        method=responses.GET,
        url=http_url,
        json={"data": "state -> 1", "message": "OK"},
        status=200
    )

    source_code = '''
    from datetime import datetime, timedelta

    # Calculate the job trigger time 5 minutes from now
    trigger_time1 = datetime.utcnow() + timedelta(minutes=30)
    trigger_time2 = datetime.utcnow() + timedelta(minutes=2)

    id = generate_id()

    # Function to add the scheduled job (with the adjusted trigger time)
    # add_schedule_job('mng2', trigger_time1, {'user_rajan': 'test rajan sep 12'}, 'UTC', id, kwargs={'task_type': 'Callback'})
    # add_schedule_job('del_job1', trigger_time2, {'event_id': id}, 'UTC', kwargs={'task_type': 'Callback'})

    add_schedule_job('mng2', trigger_time1, {'user_rajan': 'test rajan sep 12'}, 'UTC', id)
    add_schedule_job('del_job1', trigger_time2, {'event_id': id}, 'UTC')
    '''
    source_code = '''
    from datetime import datetime, timedelta

    # Calculate the job trigger time 5 minutes from now
    trigger_time1 = datetime(2025, 2, 4, 15, 30, 0)

    id = generate_id()

    # Function to add the scheduled job (with the adjusted trigger time)
    add_schedule_job('mng2', trigger_time1, {'user_rajan': 'test rajan sep 12'}, 'UTC', id)
    bot_response = "scheduled successfully!"
    '''
    source_code = textwrap.dedent(source_code)
    event = {'source_code': source_code,
             'predefined_objects':
                 {'bot': 'test_bot', 'sender_id': '917506075263',
                  'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
                  'slot': {},
                  'intent': 'k_multimedia_msg'
                  }
             }
    data = lambda_handler(event, None)
    print(data)
    assert data['body']['bot_response'] == 'scheduled successfully!'
    assert data == {
        'statusCode': 200,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': {
            'bot': 'test_bot',
            'sender_id': '917506075263',
            'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
            'slot': {},
            'intent': 'k_multimedia_msg',
            'bot_response': 'scheduled successfully!',
            'trigger_time1': '02/04/2025, 15:30:00',
            'id': pytest.test_generate_id
        }
    }
    callback_config.delete_many({"bot": "test_bot", "name": "mng2"})


@responses.activate
@patch("kairon.async_callback.scheduler.uuid7")
def test_lambda_handler_with_add_schedule_job_without_bot(mock_uuid7, callback_config):
    from uuid6 import uuid7

    test_generate_id = uuid7()
    mock_uuid7.return_value = test_generate_id
    server_url = Utility.environment["events"]["server_url"]
    pytest.test_generate_id = test_generate_id.hex
    http_url = f"{server_url}/api/events/dispatch/{pytest.test_generate_id}"
    responses.add(
        method=responses.GET,
        url=http_url,
        json={"data": "state -> 1", "message": "OK"},
        status=200
    )

    source_code = '''
    from datetime import datetime, timedelta

    # Calculate the job trigger time 5 minutes from now
    trigger_time1 = datetime.utcnow() + timedelta(minutes=30)
    trigger_time2 = datetime.utcnow() + timedelta(minutes=2)

    id = generate_id()

    # Function to add the scheduled job (with the adjusted trigger time)
    # add_schedule_job('mng2', trigger_time1, {'user_rajan': 'test rajan sep 12'}, 'UTC', id, kwargs={'task_type': 'Callback'})
    # add_schedule_job('del_job1', trigger_time2, {'event_id': id}, 'UTC', kwargs={'task_type': 'Callback'})

    add_schedule_job('mng2', trigger_time1, {'user_rajan': 'test rajan sep 12'}, 'UTC', id)
    add_schedule_job('del_job1', trigger_time2, {'event_id': id}, 'UTC')
    '''
    source_code = '''
    from datetime import datetime, timedelta

    # Calculate the job trigger time 5 minutes from now
    trigger_time1 = datetime(2025, 2, 4, 15, 30, 0)

    id = generate_id()

    # Function to add the scheduled job (with the adjusted trigger time)
    add_schedule_job('mng2', trigger_time1, {'user_rajan': 'test rajan sep 12'}, 'UTC', id)
    bot_response = "scheduled successfully!"
    '''
    source_code = textwrap.dedent(source_code)
    event = {'source_code': source_code,
             'predefined_objects':
                 {'sender_id': '917506075263',
                  'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
                  'slot': {},
                  'intent': 'k_multimedia_msg'
                  }
             }
    data = lambda_handler(event, None)
    print(data)
    assert data['body'] == 'Missing bot id'
    assert data == {
        'statusCode': 422,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': 'Missing bot id'
    }


@responses.activate
def test_lambda_handler_with_delete_schedule_job_without_bot():
    server_url = Utility.environment["events"]["server_url"]
    http_url = f"{server_url}/api/events/e8b5a51d4c8a4e6db26e290e5d1d6f94"
    responses.add(
        method=responses.DELETE,
        url=http_url,
        json={"data": "Deleted Successfully", "message": "OK"},
        status=200
    )

    source_code = '''
    # Function to delete the scheduled job (with the adjusted trigger time)
    delete_schedule_job('e8b5a51d4c8a4e6db26e290e5d1d6f94')
    bot_response = "deleted successfully!"
    '''
    source_code = textwrap.dedent(source_code)
    event = {'source_code': source_code,
             'predefined_objects':
                 {'sender_id': '917506075263',
                  'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
                  'slot': {},
                  'intent': 'k_multimedia_msg'
                  }
             }
    data = lambda_handler(event, None)
    print(data)
    assert data['body'] == 'Missing bot id'
    assert data == {
        'statusCode': 422,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': 'Missing bot id'
    }


@responses.activate
def test_lambda_handler_with_delete_schedule_job_without_event_id():
    server_url = Utility.environment["events"]["server_url"]
    http_url = f"{server_url}/api/events/e8b5a51d4c8a4e6db26e290e5d1d6f94"
    responses.add(
        method=responses.DELETE,
        url=http_url,
        json={"data": "Deleted Successfully", "message": "OK"},
        status=200
    )

    source_code = '''
    # Function to delete the scheduled job (with the adjusted trigger time)
    delete_schedule_job(False)
    bot_response = "deleted successfully!"
    '''
    source_code = textwrap.dedent(source_code)
    event = {'source_code': source_code,
             'predefined_objects':
                 {'bot': 'test_bot', 'sender_id': '917506075263',
                  'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
                  'slot': {},
                  'intent': 'k_multimedia_msg'
                  }
             }
    data = lambda_handler(event, None)
    print(data)
    assert data['body'] == 'Missing event id'
    assert data == {
        'statusCode': 422,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': 'Missing event id'
    }


@responses.activate
def test_lambda_handler_with_delete_schedule_job():
    server_url = Utility.environment["events"]["server_url"]
    http_url = f"{server_url}/api/events/e8b5a51d4c8a4e6db26e290e5d1d6f94"
    responses.add(
        method=responses.DELETE,
        url=http_url,
        json={"data": "Deleted Successfully", "message": "OK"},
        status=200
    )

    source_code = '''
    # Function to delete the scheduled job (with the adjusted trigger time)
    delete_schedule_job('e8b5a51d4c8a4e6db26e290e5d1d6f94')
    bot_response = "deleted successfully!"
    '''
    source_code = textwrap.dedent(source_code)
    event = {'source_code': source_code,
             'predefined_objects':
                 {'bot': 'test_bot', 'sender_id': '917506075263',
                  'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
                  'slot': {},
                  'intent': 'k_multimedia_msg'
                  }
             }
    data = lambda_handler(event, None)
    print(data)
    assert data['body']['bot_response'] == 'deleted successfully!'
    assert data == {
        'statusCode': 200,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': {
            'bot': 'test_bot',
            'sender_id': '917506075263',
            'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
            'slot': {},
            'intent': 'k_multimedia_msg',
            'bot_response': 'deleted successfully!',
        }
    }

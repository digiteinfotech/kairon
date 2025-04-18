import os
import re
import textwrap
from calendar import timegm
from datetime import datetime, timezone, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from unittest.mock import patch, MagicMock

import pytest
import responses
from apscheduler.triggers.date import DateTrigger
from apscheduler.util import obj_to_ref
from deepdiff import DeepDiff
from mongoengine import connect
from pymongo import MongoClient

from kairon import Utility
from kairon.events.executors.factory import ExecutorFactory
from kairon.shared.actions.data_objects import EmailActionConfig
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.callback.data_objects import CallbackConfig
from kairon.shared.utils import MailUtility

os.environ["system_file"] = "./tests/testing_data/system.yaml"
Utility.load_environment()
connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

from kairon.async_callback.utils import CallbackUtility


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
    data = CallbackUtility.pyscript_handler(event, None)
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
    data = CallbackUtility.pyscript_handler(event, None)
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
    data = CallbackUtility.pyscript_handler(event, None)
    print(data)
    assert data['body'] == "Script execution error: import of 'numpy' is unauthorized"
    assert data == {
        'statusCode': 422,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': "Script execution error: import of 'numpy' is unauthorized"
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
    data = CallbackUtility.pyscript_handler(event, None)
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
    data = CallbackUtility.pyscript_handler(event, None)
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
    data = CallbackUtility.pyscript_handler(event, None)
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
            'response': str(response)
        }}
    ]
    data = CallbackUtility.pyscript_handler(event, None)
    print(data)
    expected_response_str = str(response)
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
            'response': expected_response_str,
            'bot_response': 'This is testing pyscript with RESPONSE in event data'
        }
    }


@patch("kairon.async_callback.utils.SMTP", autospec=True)
def test_lambda_handler_for_send_email(mock_smtp):
    EmailActionConfig(
        action_name="email_action",
        smtp_url="smtp.gmail.com",
        smtp_port=587,
        smtp_password={"value": "test"},
        smtp_userid={"value": "abcsdsldksl"},
        from_email={"value": "testadmin@test.com", "parameter_type": "value"},
        subject="test",
        to_email={"value": ["test@test.com", "test1@test.com"], "parameter_type": "value"},
        response="Email Triggered",
        tls=True,
        bot="test_bot",
        user="test_user"
    ).save()

    source_code = '''
    send_email("email_action",    # email action name should be same as email action
           "hghuge@digite.com",          # from email
           "mahesh.sattala@digite.com",  # to email
           "New Order Placed",    # Subject
           "THIS IS EMAIL BODY"     # body
    )
    bot_response = "Email sent successfully!"
    '''
    source_code = textwrap.dedent(source_code)
    event = {
        'source_code': source_code,
        'predefined_objects': {
            'bot': 'test_bot',
            'sender_id': '917506075263',
            'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
            'slot': {},
            'intent': 'k_multimedia_msg'
        }
    }
    data = CallbackUtility.pyscript_handler(event, None)
    print(data)
    assert data['body']['bot_response'] == 'Email sent successfully!'
    expected = {
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
    assert data == expected


@patch("kairon.async_callback.utils.SMTP", autospec=True)
def test_lambda_handler_for_send_email_without_bot(mock_smtp):
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
    data = CallbackUtility.pyscript_handler(event, None)
    assert data['body'] == 'Script execution error: Missing bot id'
    assert data == {
        'statusCode': 422,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': 'Script execution error: Missing bot id'
    }


@responses.activate
@patch("kairon.async_callback.utils.CallbackUtility.add_schedule_job", autospec=True)
@patch("kairon.async_callback.utils.uuid7")
@patch("pymongo.collection.Collection.insert_one", autospec=True)
def test_lambda_handler_with_add_schedule_job(mock_insert_one, mock_uuid7, mock_add_job):
    from kairon.shared.callback.data_objects import CallbackConfig
    from kairon.shared.callback.data_objects import encrypt_secret
    from uuid6 import uuid7

    with patch.dict(Utility.environment["events"]["executor"], {"type": "aws_lambda"}):
        CallbackConfig(
            name="mng2",
            pyscript_code="state += 1\nbot_response = f'state -> {state}'",
            validation_secret=encrypt_secret("0191703078f779199d90c1a91fe9839f"),
            execution_mode="sync",
            expire_in=0,
            shorten_token=True,
            token_hash="0191703078f87a039906afc0a219dd5c",
            standalone=True,
            standalone_id_path="data.id",
            bot="test_bot",
            token_value="gAAAAABmxKl5tT0UKwkqYi2n9yV1lFAAJKsZEM0G9w7kmN8NIYR9JKF1F9ecZoUY6P9kClUC_QnLXXGLa3T4Xugdry84ioaDtGF9laXcQl_82Fvs9KmKX8xfa4-rJs1cto1Jd6fqeGIT7mR3kn56_EliP83aGoCl_sk9B0-2gPDgt-EJZQ20l-3OaT-rhFoFanjKvRiE8e4xp9sdxxjgDWLbCF3kCtTqTtg6Wovw3mXZoVzxzNEUmd2OGZiO6IsIJJaU202w3CZ2rPnmK8I2aRGg8tMi_-ObOg=="
        ).save()

        test_generate_id = uuid7()
        mock_uuid7.return_value = test_generate_id
        server_url = Utility.environment["events"]["server_url"]
        pytest.test_generate_id = test_generate_id.hex
        http_url = f"{server_url}/api/events/dispatch/{pytest.test_generate_id}"
        responses.add(
            method=responses.GET,
            url=http_url,
            json={"data": "state -> 1", "message": "OK", "success": True, "error_code": 0},
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
        add_schedule_job('mng2', trigger_time1, {'user': 'test user sep 12'}, 'UTC', id)
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
        data = CallbackUtility.pyscript_handler(event, None)
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


@responses.activate
@patch("kairon.async_callback.utils.uuid7")
def test_lambda_handler_with_add_schedule_job_without_bot(mock_uuid7):
    from uuid6 import uuid7

    test_generate_id = uuid7()
    mock_uuid7.return_value = test_generate_id
    server_url = Utility.environment["events"]["server_url"]
    pytest.test_generate_id = test_generate_id.hex
    http_url = f"{server_url}/api/events/dispatch/{pytest.test_generate_id}"
    responses.add(
        method=responses.GET,
        url=http_url,
        json={"data": "state -> 1", "message": "OK", "success": True, "error_code": 0},
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
    data = CallbackUtility.pyscript_handler(event, None)
    print(data)
    assert data['body'] == 'Script execution error: Missing bot id'
    assert data == {
        'statusCode': 422,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': 'Script execution error: Missing bot id'
    }


@responses.activate
def test_lambda_handler_with_delete_schedule_job_without_bot():
    server_url = Utility.environment["events"]["server_url"]
    http_url = f"{server_url}/api/events/e8b5a51d4c8a4e6db26e290e5d1d6f94"
    responses.add(
        method=responses.DELETE,
        url=http_url,
        json={"data": "Deleted Successfully", "message": "OK", "success": True, "error_code": 0},
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
    data = CallbackUtility.pyscript_handler(event, None)
    print(data)
    assert data['body'] == 'Script execution error: Missing bot id'
    assert data == {
        'statusCode': 422,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': 'Script execution error: Missing bot id'
    }


@responses.activate
def test_lambda_handler_with_delete_schedule_job_without_event_id():
    server_url = Utility.environment["events"]["server_url"]
    http_url = f"{server_url}/api/events/e8b5a51d4c8a4e6db26e290e5d1d6f94"
    responses.add(
        method=responses.DELETE,
        url=http_url,
        json={"data": "Deleted Successfully", "message": "OK", "success": True, "error_code": 0},
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
    data = CallbackUtility.pyscript_handler(event, None)
    print(data)
    assert data['body'] == 'Script execution error: Missing event id'
    assert data == {
        'statusCode': 422,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': 'Script execution error: Missing event id'
    }


@responses.activate
def test_lambda_handler_with_delete_schedule_job():
    server_url = Utility.environment["events"]["server_url"]
    http_url = f"{server_url}/api/events/e8b5a51d4c8a4e6db26e290e5d1d6f94"
    responses.add(
        method=responses.DELETE,
        url=http_url,
        json={"data": "Deleted Successfully", "message": "OK", "success": True, "error_code": 0},
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
    data = CallbackUtility.pyscript_handler(event, None)
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


def test_pyscript_handler_for_add_data():
    source_code = '''
    json_data = {
            "collection_name": "testing_crud_api",
            # "is_secure": ["mobile_number"],
            "is_secure": [],
            "data": {
                "mobile_number": "919876543210",
                "name": "Mahesh",
            }
        }

    sender_id = "919876543210"

    resp = add_data(sender_id,json_data)
    # resp = get_data("testing_crud_api",sender_id,{"name":"Mahesh", "mobile_number":"7760368805"})
    # resp = delete_data("67aafc787f4e6043f050496e",sender_id)
    # resp = update_data("67aafc787f4e6043f050496e",sender_id,json_data)
    bot_response = resp
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
    data = CallbackUtility.pyscript_handler(event, None)
    print(data)
    bot_response = data['body']['bot_response']
    pytest.collection_id = bot_response['data']['_id']
    assert data == {
        'statusCode': 200,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': {
            'bot': 'test_bot',
            'sender_id': '919876543210',
            'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
            'slot': {},
            'intent': 'k_multimedia_msg',
            'bot_response': bot_response,
            'json_data': {'collection_name': 'testing_crud_api', 'is_secure': [],
                          'data': {'mobile_number': '919876543210', 'name': 'Mahesh'}},
            'resp': bot_response
        }
    }


def test_pyscript_handler_for_add_data_without_bot():
    source_code = '''
    json_data = {
            "collection_name": "testing_crud_api",
            # "is_secure": ["mobile_number"],
            "is_secure": [],
            "data": {
                "mobile_number": "919876543210",
                "name": "Mahesh",
            }
        }

    sender_id = "919876543210"

    resp = add_data(sender_id,json_data)
    # resp = get_data("testing_crud_api",sender_id,{"name":"Mahesh", "mobile_number":"7760368805"})
    # resp = delete_data("67aafc787f4e6043f050496e",sender_id)
    # resp = update_data("67aafc787f4e6043f050496e",sender_id,json_data)
    bot_response = resp
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
    data = CallbackUtility.pyscript_handler(event, None)
    print(data)
    assert data == {
        'statusCode': 422,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': 'Script execution error: Missing bot id'
    }


def test_pyscript_handler_for_get_data():
    source_code = '''
    json_data = {
            "collection_name": "testing_crud_api",
            # "is_secure": ["mobile_number"],
            "is_secure": [],
            "data": {
                "mobile_number": "919876543210",
                "name": "Mahesh",
            }
        }

    sender_id = "919876543210"

    resp = add_data(sender_id,json_data)
    resp = get_data("testing_crud_api",sender_id,{"name":"Mahesh", "mobile_number":"919876543210"})
    # resp = delete_data("67aafc787f4e6043f050496e",sender_id)
    # resp = update_data("67aafc787f4e6043f050496e",sender_id,json_data)
    bot_response = resp
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
    data = CallbackUtility.pyscript_handler(event, None)
    print(data)
    bot_response = data['body']['bot_response']
    print(bot_response)
    assert bot_response['data'][0]['collection_name'] == 'testing_crud_api'
    assert bot_response['data'][0]['is_secure'] == []
    assert bot_response['data'][0]['data'] == {'mobile_number': '919876543210', 'name': 'Mahesh'}
    assert data == {
        'statusCode': 200,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': {
            'bot': 'test_bot',
            'sender_id': '919876543210',
            'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
            'slot': {},
            'intent': 'k_multimedia_msg',
            'bot_response': bot_response,
            'json_data': {'collection_name': 'testing_crud_api', 'is_secure': [],
                          'data': {'mobile_number': '919876543210', 'name': 'Mahesh'}},
            'resp': bot_response
        }
    }


def test_pyscript_handler_for_get_data_without_bot():
    source_code = '''
    json_data = {
            "collection_name": "testing_crud_api",
            # "is_secure": ["mobile_number"],
            "is_secure": [],
            "data": {
                "mobile_number": "919876543210",
                "name": "Mahesh",
            }
        }

    sender_id = "919876543210"

    # resp = add_data(sender_id,json_data)
    resp = get_data("testing_crud_api",sender_id,{"name":"Mahesh", "mobile_number":"919876543210"})
    # resp = delete_data("67aafc787f4e6043f050496e",sender_id)
    # resp = update_data("67aafc787f4e6043f050496e",sender_id,json_data)
    bot_response = resp
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
    data = CallbackUtility.pyscript_handler(event, None)
    print(data)
    assert data == {
        'statusCode': 422,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': 'Script execution error: Missing bot id'
    }


def test_pyscript_handler_for_update_data():
    source_code = '''
    json_data = {
            "collection_name": "testing_crud_api",
            # "is_secure": ["mobile_number"],
            "is_secure": [],
            "data": {
                "mobile_number": "919876543210",
                "name": "Mahesh",
            }
        }
    update_json_data = {
        "collection_name": "testing_crud_api",
        "is_secure": [],
        "data": {
            "mobile_number": "919876543210",
            "name": "Mahesh SV",
        }
    }
    sender_id = "919876543210"

    resp = add_data(sender_id,json_data)
    collection_id=str(resp['data']['_id'])
    resp = update_data(collection_id, sender_id, update_json_data)
    bot_response = resp
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
    data = CallbackUtility.pyscript_handler(event, None)
    bot_response = data['body']['bot_response']
    print(data)
    bot_response_id = (
        data['body']['bot_response']['data']['_id']
        if data.get('body', {}).get('bot_response', {}).get('data')
        else None
    )
    assert bot_response == {'message': 'Record updated!', 'data': {'_id': bot_response_id}}


def test_pyscript_handler_for_update_data_without_bot():
    json_data = {
        "collection_name": "testing_crud_api",
        "is_secure": [],
        "data": {
            "mobile_number": "919876543210",
            "name": "Mahesh SV",
        }
    }
    sender_id = "919876543210"
    source_code = f'''
        json_data = {json_data}
        sender_id = {sender_id!r}
        collection_id = {pytest.collection_id!r}  

        # Uncomment based on the operation you want to perform
        # resp = add_data(sender_id, json_data)
        # resp = get_data("testing_crud_api", sender_id, {{"name": "Mahesh", "mobile_number": "7760368805"}})
        # resp = delete_data(collection_id, sender_id)
        resp = update_data(collection_id, sender_id, json_data)

        bot_response = resp
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
    data = CallbackUtility.pyscript_handler(event, None)
    print(data)
    assert data == {
        'statusCode': 422,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': 'Script execution error: Missing bot id'
    }


def test_pyscript_handler_for_get_data_after_update():
    source_code = '''
    json_data = {
            "collection_name": "testing_crud_api",
            # "is_secure": ["mobile_number"],
            "is_secure": [],
            "data": {
                "mobile_number": "919876543210",
                "name": "Mahesh",
            }
        }
    update_json_data = {
        "collection_name": "testing_crud_api",
        "is_secure": [],
        "data": {
            "mobile_number": "919876543210",
            "name": "Mahesh SV",
        }
    }
    sender_id = "919876543210"

    resp = add_data(sender_id,json_data)
    collection_id=str(resp['data']['_id'])
    update_resp = update_data(collection_id,sender_id,update_json_data)
    resp = get_data("testing_crud_api",sender_id,{"name":"Mahesh SV", "mobile_number":"919876543210"})

    bot_response = resp
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
    data = CallbackUtility.pyscript_handler(event, None)
    print(data)
    bot_response = data['body']['bot_response']
    print(bot_response)
    assert bot_response['data'][0]['collection_name'] == 'testing_crud_api'
    assert bot_response['data'][0]['is_secure'] == []
    assert bot_response['data'][0]['data'] == {'mobile_number': '919876543210', 'name': 'Mahesh SV'}


def test_pyscript_handler_for_delete_data():
    source_code = '''
    json_data = {
            "collection_name": "testing_crud_api1",
            # "is_secure": ["mobile_number"],
            "is_secure": [],
            "data": {
                "mobile_number": "919876543210",
                "name": "Mahesh",
            }
        }

    sender_id = "919876543210"

    resp = add_data(sender_id,json_data)
    collection_id=str(resp['data']['_id'])
    resp = delete_data(collection_id,sender_id) 
    bot_response = resp
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
    data = CallbackUtility.pyscript_handler(event, None)
    bot_response = data['body']['bot_response']
    collection_id = bot_response['data']['_id']
    print(bot_response)
    assert bot_response == {'message': f'Collection with ID {collection_id} has been successfully deleted.',
                            'data': {'_id': collection_id}}


def test_pyscript_handler_for_delete_data_without_bot():
    json_data = {
        "collection_name": "testing_crud_api",
        "is_secure": [],
        "data": {
            "mobile_number": "919876543210",
            "name": "Mahesh SV",
        }
    }
    sender_id = "919876543210"
    source_code = f'''
        json_data = {json_data}
        sender_id = {sender_id!r}
        collection_id = {pytest.collection_id!r}  

        # Uncomment based on the operation you want to perform
        # resp = add_data(sender_id, json_data)
        # resp = get_data("testing_crud_api", sender_id, {{"name": "Mahesh", "mobile_number": "7760368805"}})
        resp = delete_data(collection_id, sender_id)
        # resp = update_data(collection_id, sender_id, json_data)

        bot_response = resp
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
    data = CallbackUtility.pyscript_handler(event, None)
    print(data)
    assert data == {
        'statusCode': 422,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': 'Script execution error: Missing bot id'
    }


def test_pyscript_handler_for_get_data_after_delete():
    source_code = '''
    json_data = {
            "collection_name": "testing_crud_api",
            # "is_secure": ["mobile_number"],
            "is_secure": [],
            "data": {
                "mobile_number": "919876543210",
                "name": "Mahesh",
            }
        }

    sender_id = "919876543210"

    # resp = add_data(sender_id,json_data)
    resp = get_data("testing_crud_api",sender_id,{"name":"Mahesh SV", "mobile_number":"919876543210"})
    # resp = delete_data("67aafc787f4e6043f050496e",sender_id)
    # resp = update_data("67aafc787f4e6043f050496e",sender_id,json_data)
    bot_response = resp
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
    data = CallbackUtility.pyscript_handler(event, None)
    print(data)
    bot_response = data['body']['bot_response']
    print(bot_response)
    assert bot_response == {'data': []}
    assert data == {
        'statusCode': 200,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': {
            'bot': 'test_bot',
            'sender_id': '919876543210',
            'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
            'slot': {},
            'intent': 'k_multimedia_msg',
            'bot_response': bot_response,
            'json_data': {'collection_name': 'testing_crud_api', 'is_secure': [],
                          'data': {'mobile_number': '919876543210', 'name': 'Mahesh'}},
            'resp': bot_response
        }
    }


def test_generate_id():
    uuid1 = CallbackUtility.generate_id()
    uuid2 = CallbackUtility.generate_id()

    assert isinstance(uuid1, str)
    assert isinstance(uuid2, str)
    assert len(uuid1) == 32
    assert len(uuid2) == 32
    assert uuid1 != uuid2


def test_datetime_to_utc_timestamp():
    dt = datetime(2024, 3, 27, 12, 30, 45, 123456, tzinfo=timezone.utc)
    expected_timestamp = timegm(dt.utctimetuple()) + dt.microsecond / 1000000

    assert CallbackUtility.datetime_to_utc_timestamp(dt) == expected_timestamp


def test_datetime_to_utc_timestamp_none():
    assert CallbackUtility.datetime_to_utc_timestamp(None) is None


def test_get_data_missing_bot():
    with pytest.raises(Exception, match="Missing bot id"):
        CallbackUtility.get_data("TestCollection", "user1", {"field": "value"}, bot=None)


@patch.object(CallbackUtility, "fetch_collection_data", return_value=[{"dummy": "data"}])
def test_get_data_success(mock_fetch):
    collection_name = "TestCollection"
    user = "user1"
    data_filter = {"field": "value"}
    bot = "TestBot"

    result = CallbackUtility.get_data(collection_name, user, data_filter, bot=bot)

    expected_query = {
        "bot": bot,
        "collection_name": collection_name.lower(),
        "data__field": "value"
    }

    mock_fetch.assert_called_once_with(expected_query)

    assert result == {"data": [{"dummy": "data"}]}


def test_fetch_collection_data_success():
    """Test fetch_collection_data with valid query returning data."""

    mock_data = {
        "_id": "12345",
        "collection_name": "test_collection",
        "is_secure": True,
        "data": "encrypted_data"
    }

    mock_object = MagicMock()
    mock_object.to_mongo.return_value.to_dict.return_value = mock_data

    with patch("kairon.shared.cognition.data_objects.CollectionData.objects", return_value=[mock_object]), \
            patch("kairon.shared.cognition.processor.CognitionDataProcessor.prepare_decrypted_data",
                  return_value="decrypted_data"):
        results = list(CallbackUtility.fetch_collection_data({"some_field": "some_value"}))

    assert len(results) == 1
    assert results[0].pop("timestamp")
    assert results[0] == {
        "_id": "12345",
        "collection_name": "test_collection",
        "is_secure": True,
        "data": "decrypted_data"
    }


def test_fetch_collection_data_empty_result():
    """Test fetch_collection_data when no matching documents exist."""

    with patch("kairon.shared.cognition.data_objects.CollectionData.objects", return_value=[]):
        results = list(CallbackUtility.fetch_collection_data({"some_field": "no_match"}))

    assert results == []


def test_fetch_collection_data_without_collection_name():
    """Test fetch_collection_data when collection_name is missing in the document."""

    mock_data = {
        "_id": "67890",
        "is_secure": False,
        "data": "encrypted_data"
    }

    mock_object = MagicMock()
    mock_object.to_mongo.return_value.to_dict.return_value = mock_data

    with patch("kairon.shared.cognition.data_objects.CollectionData.objects", return_value=[mock_object]), \
            patch("kairon.shared.cognition.processor.CognitionDataProcessor.prepare_decrypted_data",
                  return_value="decrypted_data"):
        results = list(CallbackUtility.fetch_collection_data({"some_field": "some_value"}))

    assert len(results) == 1
    assert results[0].pop("timestamp")
    assert results[0] == {
        "_id": "67890",
        "collection_name": None,  # collection_name is missing
        "is_secure": False,
        "data": "decrypted_data"
    }


def test_fetch_collection_data_handles_exceptions():
    """Test fetch_collection_data when an exception occurs during iteration."""

    mock_object = MagicMock()
    mock_object.to_mongo.side_effect = Exception("Database error")

    with patch("kairon.shared.cognition.data_objects.CollectionData.objects", return_value=[mock_object]):
        with pytest.raises(Exception, match="Database error"):
            list(CallbackUtility.fetch_collection_data({"some_field": "some_value"}))


def test_add_data_missing_bot():
    with pytest.raises(Exception, match="Missing bot id"):
        CallbackUtility.add_data("test_user", {"key": "value"}, bot=None)


@patch('kairon.shared.cognition.processor.CognitionDataProcessor.save_collection_data')
def test_add_data_success(mock_save):
    mock_save.return_value = "collection_id_123"
    result = CallbackUtility.add_data("test_user", {"key": "value"}, bot="test_bot")

    mock_save.assert_called_once_with({"key": "value"}, "test_user", "test_bot")

    expected = {
        "message": "Record saved!",
        "data": {"_id": "collection_id_123"}
    }
    assert result == expected


def test_update_data_missing_bot():
    with pytest.raises(Exception, match="Missing bot id"):
        CallbackUtility.update_data("id_123", "test_user", {"key": "value"}, bot=None)


@patch('kairon.shared.cognition.processor.CognitionDataProcessor.update_collection_data')
def test_update_data_success(mock_update):
    mock_update.return_value = "updated_id_123"
    result = CallbackUtility.update_data("id_123", "test_user", {"key": "value"}, bot="test_bot")

    mock_update.assert_called_once_with("id_123", {"key": "value"}, "test_user", "test_bot")

    expected = {
        "message": "Record updated!",
        "data": {"_id": "updated_id_123"}
    }
    assert result == expected


def test_delete_data_missing_bot():
    with pytest.raises(Exception, match="Missing bot id"):
        CallbackUtility.delete_data("id_123", "test_user", bot=None)


@patch('kairon.shared.cognition.processor.CognitionDataProcessor.delete_collection_data')
def test_delete_data_success(mock_delete):
    result = CallbackUtility.delete_data("id_123", "test_user", bot="test_bot")

    mock_delete.assert_called_once_with("id_123", "test_bot", "test_user")

    expected = {
        "message": "Collection with ID id_123 has been successfully deleted.",
        "data": {"_id": "id_123"}
    }
    assert result == expected


def test_perform_cleanup():
    local_vars = {
        "a": lambda x: x,
        "b": __import__("math"),
        "c": datetime(2025, 3, 28, 14, 30, 0),
        "d": date(2025, 3, 28),
        "f": "normal string",
        "g": 123,
    }

    # Call the function under test.
    result = CallbackUtility.perform_cleanup(local_vars)

    # Expected result after filtering and formatting.
    expected = {
        "c": "03/28/2025, 14:30:00",
        "d": "2025-03-28",
        "f": "normal string",
        "g": 123,
    }

    assert result == expected


def test_send_email_direct():
    mock_email_config = MagicMock()
    mock_email_config.to_mongo.return_value.to_dict.return_value = {
        "smtp_url": "smtp.gmail.com",
        "smtp_port": 587,
        "tls": True,
        "smtp_userid": {"value": "user@example.com"},
        "smtp_password": {"value": "password123"}
    }
    with patch.object(EmailActionConfig, "objects",
                      return_value=MagicMock(first=MagicMock(return_value=mock_email_config))) as mock_objects, \
            patch.object(CallbackUtility, "trigger_email") as mock_trigger_email:
        CallbackUtility.send_email(
            email_action="send_mail",
            from_email="from@example.com",
            to_email="to@example.com",
            subject="Test Subject",
            body="Test Body",
            bot="bot123"
        )
        mock_objects.assert_called_once_with(bot="bot123", action_name="send_mail")
        mock_trigger_email.assert_called_once_with(
            email=["to@example.com"],
            subject="Test Subject",
            body="Test Body",
            smtp_url="smtp.gmail.com",
            smtp_port=587,
            sender_email="from@example.com",
            smtp_password="password123",
            smtp_userid="user@example.com",
            tls=True
        )


def test_send_email_missing_bot_direct():
    with pytest.raises(Exception, match="Missing bot id"):
        CallbackUtility.send_email(
            email_action="send_mail",
            from_email="from@example.com",
            to_email="to@example.com",
            subject="Test Subject",
            body="Test Body",
            bot=""
        )


def dummy_uuid7():
    return type("DummyUUID", (), {"hex": "fixed_uuid"})


def dummy_execute_task(*args, **kwargs):
    return "executed"


class DummyDateTrigger:
    def __init__(self, run_date, timezone):
        self.run_date = run_date
        self.timezone = timezone

    def get_next_fire_time(self, prev_fire_time, now):
        return datetime(2025, 1, 2, tzinfo=timezone.utc)


class DummyCollection:
    def __init__(self):
        self.inserted = None

    def insert_one(self, doc):
        self.inserted = doc


class DummyDB:
    def __init__(self, collection):
        self._collection = collection

    def get_collection(self, name):
        return self._collection


class DummyMongoClient:
    def __init__(self, url):
        self.url = url

    def get_database(self, name):
        return DummyDB(DummyCollection())


def test_add_schedule_job_missing_bot():
    with pytest.raises(Exception, match="Missing bot id"):
        CallbackUtility.add_schedule_job(
            schedule_action="test_action",
            date_time=datetime.now(timezone.utc),
            data={},
            timezone="UTC",
            _id="any_id",
            bot=None,
        )


def test_add_schedule_job_http_failure(monkeypatch):
    schedule_action = "test_action"
    date_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    data = {"initial": "value"}
    tz = "UTC"
    _id = "provided_id"
    bot = "test_bot"
    kwargs_in = {"extra": "info"}

    monkeypatch.setattr("kairon.async_callback.utils.uuid7", dummy_uuid7)

    monkeypatch.setattr(CallbackConfig, "get_entry", lambda bot, name: {"pyscript_code": "dummy_code"})

    dummy_executor = type("DummyExecutor", (), {"execute_task": dummy_execute_task})
    monkeypatch.setattr(ExecutorFactory, "get_executor", lambda: dummy_executor)

    monkeypatch.setattr(obj_to_ref, "__call__", lambda self, func: func)

    monkeyatch_target = "apscheduler.util.obj_to_ref"
    monkeypatch.setattr(monkeyatch_target, lambda x: x)

    monkeypatch.setattr(DateTrigger, "__init__", lambda self, run_date, **kwargs: setattr(self, "run_date", run_date))
    monkeypatch.setattr(DateTrigger, "get_next_fire_time", lambda self, a, b: datetime(2025, 1, 2, tzinfo=timezone.utc))

    monkeypatch.setattr(Utility, "environment", {
        'database': {'url': 'mongodb://dummy'},
        'events': {
            'queue': {'name': 'dummy_db'},
            'scheduler': {'collection': 'dummy_collection'},
            'server_url': 'http://dummy_server'
        }
    })

    monkeypatch.setattr(MongoClient, "__init__", lambda self, url: None)
    monkeypatch.setattr(MongoClient, "get_database", lambda self, name: DummyDB(DummyCollection()))

    monkeypatch.setattr(ActionUtility, "execute_http_request",
                        lambda url, method: {"success": False, "error": "error message"})

    monkeypatch.setattr(CallbackUtility, "datetime_to_utc_timestamp", lambda dt: 1234567890)

    with pytest.raises(Exception) as exc_info:
        CallbackUtility.add_schedule_job(schedule_action, date_time, data, tz, _id=_id, bot=bot, kwargs=kwargs_in)
    assert "error message" in str(exc_info.value)


def test_add_schedule_job_success(monkeypatch):
    schedule_action = "test_action"
    date_time = datetime(2025, 1, 1, tzinfo=timezone.utc)

    data = None
    tz = "UTC"
    _id = None
    bot = "test_bot"
    kwargs_in = None
    monkeypatch.setattr("kairon.async_callback.utils.uuid7", dummy_uuid7)

    monkeypatch.setattr(CallbackConfig, "get_entry", lambda bot, name: {"pyscript_code": "dummy_code"})

    dummy_executor = type("DummyExecutor", (), {"execute_task": dummy_execute_task})
    monkeypatch.setattr(ExecutorFactory, "get_executor", lambda: dummy_executor)

    monkeypatch.setattr(obj_to_ref, "__call__", lambda self, func: func)

    monkeyatch_target = "apscheduler.util.obj_to_ref"
    monkeypatch.setattr(monkeyatch_target, lambda x: x)

    monkeypatch.setattr(DateTrigger, "__init__", lambda self, run_date, **kwargs: setattr(self, "run_date", run_date))
    fixed_next_run_time = datetime(2025, 1, 2, tzinfo=timezone.utc)
    monkeypatch.setattr(DateTrigger, "get_next_fire_time", lambda self, a, b: fixed_next_run_time)

    monkeypatch.setattr(Utility, "environment", {
        'database': {'url': 'mongodb://dummy'},
        'events': {
            'queue': {'name': 'dummy_db'},
            'scheduler': {'collection': 'dummy_collection'},
            'server_url': 'http://dummy_server'
        }
    })

    dummy_collection = DummyCollection()
    dummy_db = DummyDB(dummy_collection)

    monkeypatch.setattr(MongoClient, "__init__", lambda self, url: None)
    monkeypatch.setattr(MongoClient, "get_database", lambda self, name: dummy_db)

    monkeypatch.setattr(ActionUtility, "execute_http_request", lambda url, method: {"success": True})

    monkeypatch.setattr(CallbackUtility, "datetime_to_utc_timestamp", lambda dt: 1234567890)

    result = CallbackUtility.add_schedule_job(schedule_action, date_time, data, tz, _id=_id, bot=bot, kwargs=kwargs_in)

    inserted_doc = dummy_collection.inserted
    assert inserted_doc is not None
    assert inserted_doc['_id'] == "fixed_uuid"
    assert inserted_doc['next_run_time'] == 1234567890


def test_delete_schedule_job_success(monkeypatch):
    event_id = "test_event"
    bot = "test_bot"

    mock_execute_http_request = MagicMock(return_value={"success": True})
    monkeypatch.setattr(ActionUtility, "execute_http_request", mock_execute_http_request)

    mock_env = {"events": {"server_url": "http://mockserver.com"}}
    monkeypatch.setattr(Utility, "environment", mock_env)

    CallbackUtility.delete_schedule_job(event_id, bot)

    mock_execute_http_request.assert_called_once_with("http://mockserver.com/api/events/test_event", "DELETE")


def test_delete_schedule_job_missing_bot():
    event_id = "test_event"
    bot = ""

    with pytest.raises(Exception, match="Missing bot id"):
        CallbackUtility.delete_schedule_job(event_id, bot)


def test_delete_schedule_job_missing_event():
    event_id = ""
    bot = "test_bot"

    with pytest.raises(Exception, match="Missing event id"):
        CallbackUtility.delete_schedule_job(event_id, bot)


def test_delete_schedule_job_failure(monkeypatch):
    event_id = "test_event"
    bot = "test_bot"

    mock_execute_http_request = MagicMock(return_value={"success": False, "error": "Failed to delete"})
    monkeypatch.setattr(ActionUtility, "execute_http_request", mock_execute_http_request)

    mock_env = {"events": {"server_url": "http://mockserver.com"}}
    monkeypatch.setattr(Utility, "environment", mock_env)

    with pytest.raises(Exception, match="{'success': False, 'error': 'Failed to delete'}"):
        CallbackUtility.delete_schedule_job(event_id, bot)

    mock_execute_http_request.assert_called_once_with("http://mockserver.com/api/events/test_event", "DELETE")


def test_pyscript_handler_for_decrypt_request_success():
    source_code = '''
        request_body = {
            "encrypted_flow_data":"frFiM1lZY7G1Z8mWfNyOGiMlKWNchq2enKn7dh5AEG8O+ehfOomnri3ETNumsW/16ExT8V+6FSWAAtHJtWSN6cJWLMDuqYxHwde9RYAzIHhmhqt8b0X28MGowIGc3/PTj5cuFoxtxZgh6+4i/+2/eX4f8Zul0z4n41BqPOHzDrGaHxJpdytjLGfgWwcg38GxRpU7DKTvJxrGnNmpzqaV1FWFR+J0iXBi+NW5gdBKi3SGq3ScFkE89Trx/ZZGWuy/XW7I24PiL0I0cbGhh4UtBegJlblmA44lOM/CMMswIb6G4Yk9WjsCKddVxz6LeCJx5bUSrEGzcDM/A8FrnDrrfiY8j8SSLJMCfixW",
            "encrypted_aes_key": "EspHuQs4dUOGh++ZoLRM54yRf2eghH2kPyI6YT8U8WgPP8L7eYZxZOVN2O6LAglGlt6yi8jGaDgdIKwmtNbr7ceaQiwHE+hxpiG6xzLiceSonn0ZSx2GVRHp6kvkn4kADWQypvfmOPizvJ5saGf7Lsep0Krh50vJ//HuYNK7MQUz7B2wpSRa+iI1/TaHjZMFHF1Fo31YHDXwdwb3A+7hToIfYy9mdqycPvbqqgVBxJ8WvgUzz/+Am05URQaUfw+jxxqonIYjZrmbCO4zkmAVO9EYQ/Xtli0e0iZtabqy7ePO2mSt8qgkyRrAgFkrSRobq7vxuOOmgAcYm498JKScAw==",
            "initial_vector": "Gi/cmYgQJXQ0AWpo0M5X5w=="
        }

        private_key_pem = """-----BEGIN RSA PRIVATE KEY-----
        MIIEpAIBAAKCAQEAtABM+j40C3PwaKKrOScmbzkXs30OcACwlEP916N3gnQScFsH
        xbyKUP8xUd+KxvzljpXUwNcL8qLBPsgkXxS5jhe58tW9QV4dgddt7HBTMh3Qiv9y
        4h8Yp/gAEU/g0R1LSeNgm800vGrmeSe1TpciNoMMoAsAKosTcGNJ+ISh2WZk4NK+
        s9o/Dt6X1Ww51LX2NvTzsgGlNNb5iIqQbFQhGD9LnJfYbqkuEDukaBKoEVM8857E
        YugyJvq+pjVtg46p75wKZBUaAUxLyAp7NQiTZfPt2nWuRTa0xTKYaqV3fsWKNSJa
        w8iWt9v0TZV0WPfk3AybzGDKrU5UkDftlNw13QIDAQABAoIBAB1TYDcz66xDARO3
        DuDSm00rFsywDupZ/mrFcgWQFRAso3VpK0jAqSM9lFYzrosxWCAFEqKxVnm7IPM+
        zcgs2vdGr82bm4gbEoEdLUREX5WObHO83wVujgiNm8s2QZkoJeQ9lneDtPgOjYqH
        GN+bOWB6tNOdPzNvMaVRk9NYnnrJ0O3FzBOhYw3cl3sfXXLOHvP/cEHqRySX2NJE
        /wdM3C4CcsKvMh1GRiJzJXI+d4yAwJ9lmer3A4vK5cU1bOIRrzvU/JHddF76e0Q5
        8Hmm/CIrEAxFFf1v3JdHgyKyOe0KexDb09VFwnZTinHFHy/mMSpH5nFArHX8sO1d
        jcSrZBECgYEA6SBxp8POQH29k78soHPLkV7HewUeO09JuvSmh4SN4imn6o5zLPIm
        GT5M//85OCIfqHkKcpnSUyFDZy6BeyI2mARjY6mqU4mY5PY7cESwEOjC4OanzC6O
        KGXYQ1XQnq+qP0Oe38dpYgMSE4N36Dqgj68FNZDgVNKG3/jzsVwf4XECgYEAxal5
        /53W29NOSW1NwunM1MAk4byS7JN8xlux5LTHmE/8UYiRG2uHDryZP1iyjYQIV4WP
        pH7vROt80HFpFDFdsngZqIxGN8ZXHgjoOxxhBsMZ/gZy0j7k3y7UGoO07Pdy5jYR
        9FbKOuVgVZUJV6h3Ciq+XMnDCYUuLv4Z2RxQZS0CgYEAuFqxxktvpUxKSLZboh8w
        EitzcHNhruFKmw+xSWWnlfv/D9vKdPag7kF4PtEj/KHvixj9DBdcXeTmGoiKWEd8
        CMcfmcaoLRuYzydxZZzL5vNKePOuKid+v6+aT9Vi/rpH1XOyBaD6U0m+V7QVdI44
        PqfXZL7GyA0cH64NeGozw+ECgYEAvqAnjCHI6M/snFvRtryMUlHMP/gBKi9DEnm0
        IoFGTNo22NsANpWI9ulkUfdUm65N7TpdwaK5VppVESGO2W6Skl/JPwepYHjj449r
        iDZiTIc0Ngw6CBGn4KXk4H1Mq4wpP2O+BQr+lbZJJcBJ9kP+Kcv3Mr1SX4gVdjSQ
        8RWhYzECgYAkv/C9mw8Cpxiymut3pvFkG+23ajlLXUa8xtHHcS1VO3JJX9MHPmzU
        XXKh1F2rEYtq6DIU8Y9ppbLZC9mh2T9VNL/Zxz8VoSQb6gampPoig0CFNvhTszhw
        f3KNyeUpI8pQXdf8MbjeluH9Zrto/HlxAYROVwhHmRCfTecWrwasXA==
        -----END RSA PRIVATE KEY-----
        """

        resp = decrypt_request(request_body, private_key_pem)
        bot_response = resp
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
    data = CallbackUtility.pyscript_handler(event, None)
    bot_response = data['body']['bot_response']
    assert data['statusCode'] == 200
    assert data['statusDescription'] == '200 OK'
    assert bot_response == {
        'decryptedBody': {
            'data': {
                'department': 'home',
                'location': '3',
                'date': '2024-01-03',
                'time': '11:30',
                'name': 'dsa',
                'email': 'fsd@fsd.cds',
                'phone': '84512',
                'more_details': 'sdfa'
            },
            'flow_token': 'flows-builder-f174c96d',
            'screen': 'SUMMARY',
            'action': 'data_exchange',
            'version': '3.0'
        },
        'aesKeyBuffer': b'\xbb\xccV\x98\xb2\xe8A\xb2\xe6j\xd8ob\x17\xa6\xeb',
        'initialVectorBuffer': b'\x1a/\xdc\x99\x88\x10%t4\x01jh\xd0\xceW\xe7'
    }


def test_pyscript_handler_for_decrypt_request_missing_fields():
    source_code = '''
        request_body = {
            "encrypted_flow_data":"frFiM1lZY7G1Z8mWfNyOGiMlKWNchq2enKn7dh5AEG8O+ehfOomnri3ETNumsW/16ExT8V+6FSWAAtHJtWSN6cJWLMDuqYxHwde9RYAzIHhmhqt8b0X28MGowIGc3/PTj5cuFoxtxZgh6+4i/+2/eX4f8Zul0z4n41BqPOHzDrGaHxJpdytjLGfgWwcg38GxRpU7DKTvJxrGnNmpzqaV1FWFR+J0iXBi+NW5gdBKi3SGq3ScFkE89Trx/ZZGWuy/XW7I24PiL0I0cbGhh4UtBegJlblmA44lOM/CMMswIb6G4Yk9WjsCKddVxz6LeCJx5bUSrEGzcDM/A8FrnDrrfiY8j8SSLJMCfixW",
            "encrypted_aes_key": "EspHuQs4dUOGh++ZoLRM54yRf2eghH2kPyI6YT8U8WgPP8L7eYZxZOVN2O6LAglGlt6yi8jGaDgdIKwmtNbr7ceaQiwHE+hxpiG6xzLiceSonn0ZSx2GVRHp6kvkn4kADWQypvfmOPizvJ5saGf7Lsep0Krh50vJ//HuYNK7MQUz7B2wpSRa+iI1/TaHjZMFHF1Fo31YHDXwdwb3A+7hToIfYy9mdqycPvbqqgVBxJ8WvgUzz/+Am05URQaUfw+jxxqonIYjZrmbCO4zkmAVO9EYQ/Xtli0e0iZtabqy7ePO2mSt8qgkyRrAgFkrSRobq7vxuOOmgAcYm498JKScAw==",
        }

        private_key_pem = """-----BEGIN RSA PRIVATE KEY-----
        MIIEpAIBAAKCAQEAtABM+j40C3PwaKKrOScmbzkXs30OcACwlEP916N3gnQScFsH
        xbyKUP8xUd+KxvzljpXUwNcL8qLBPsgkXxS5jhe58tW9QV4dgddt7HBTMh3Qiv9y
        4h8Yp/gAEU/g0R1LSeNgm800vGrmeSe1TpciNoMMoAsAKosTcGNJ+ISh2WZk4NK+
        s9o/Dt6X1Ww51LX2NvTzsgGlNNb5iIqQbFQhGD9LnJfYbqkuEDukaBKoEVM8857E
        YugyJvq+pjVtg46p75wKZBUaAUxLyAp7NQiTZfPt2nWuRTa0xTKYaqV3fsWKNSJa
        w8iWt9v0TZV0WPfk3AybzGDKrU5UkDftlNw13QIDAQABAoIBAB1TYDcz66xDARO3
        DuDSm00rFsywDupZ/mrFcgWQFRAso3VpK0jAqSM9lFYzrosxWCAFEqKxVnm7IPM+
        zcgs2vdGr82bm4gbEoEdLUREX5WObHO83wVujgiNm8s2QZkoJeQ9lneDtPgOjYqH
        GN+bOWB6tNOdPzNvMaVRk9NYnnrJ0O3FzBOhYw3cl3sfXXLOHvP/cEHqRySX2NJE
        /wdM3C4CcsKvMh1GRiJzJXI+d4yAwJ9lmer3A4vK5cU1bOIRrzvU/JHddF76e0Q5
        8Hmm/CIrEAxFFf1v3JdHgyKyOe0KexDb09VFwnZTinHFHy/mMSpH5nFArHX8sO1d
        jcSrZBECgYEA6SBxp8POQH29k78soHPLkV7HewUeO09JuvSmh4SN4imn6o5zLPIm
        GT5M//85OCIfqHkKcpnSUyFDZy6BeyI2mARjY6mqU4mY5PY7cESwEOjC4OanzC6O
        KGXYQ1XQnq+qP0Oe38dpYgMSE4N36Dqgj68FNZDgVNKG3/jzsVwf4XECgYEAxal5
        /53W29NOSW1NwunM1MAk4byS7JN8xlux5LTHmE/8UYiRG2uHDryZP1iyjYQIV4WP
        pH7vROt80HFpFDFdsngZqIxGN8ZXHgjoOxxhBsMZ/gZy0j7k3y7UGoO07Pdy5jYR
        9FbKOuVgVZUJV6h3Ciq+XMnDCYUuLv4Z2RxQZS0CgYEAuFqxxktvpUxKSLZboh8w
        EitzcHNhruFKmw+xSWWnlfv/D9vKdPag7kF4PtEj/KHvixj9DBdcXeTmGoiKWEd8
        CMcfmcaoLRuYzydxZZzL5vNKePOuKid+v6+aT9Vi/rpH1XOyBaD6U0m+V7QVdI44
        PqfXZL7GyA0cH64NeGozw+ECgYEAvqAnjCHI6M/snFvRtryMUlHMP/gBKi9DEnm0
        IoFGTNo22NsANpWI9ulkUfdUm65N7TpdwaK5VppVESGO2W6Skl/JPwepYHjj449r
        iDZiTIc0Ngw6CBGn4KXk4H1Mq4wpP2O+BQr+lbZJJcBJ9kP+Kcv3Mr1SX4gVdjSQ
        8RWhYzECgYAkv/C9mw8Cpxiymut3pvFkG+23ajlLXUa8xtHHcS1VO3JJX9MHPmzU
        XXKh1F2rEYtq6DIU8Y9ppbLZC9mh2T9VNL/Zxz8VoSQb6gampPoig0CFNvhTszhw
        f3KNyeUpI8pQXdf8MbjeluH9Zrto/HlxAYROVwhHmRCfTecWrwasXA==
        -----END RSA PRIVATE KEY-----
        """

        resp = decrypt_request(request_body, private_key_pem)
        bot_response = resp
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
    data = CallbackUtility.pyscript_handler(event, None)
    assert data == {
        'statusCode': 422,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': 'Script execution error: decryption failed-Missing required encrypted data fields'
    }


def test_pyscript_handler_for_encrypt_response_success():
    source_code = '''
        response_body = {
            "APPOINTMENT": {
                "screen": "APPOINTMENT",
                "data": {
                    "department": [
                        {"id": "shopping", "title": "Shopping & Groceries"},
                        {"id": "clothing", "title": "Clothing & Apparel"},
                        {"id": "home", "title": "Home Goods & Decor"},
                        {"id": "electronics", "title": "Electronics & Appliances"},
                        {"id": "beauty", "title": "Beauty & Personal Care"},
                    ]
                }
            }
        }        
        aes_key_buffer = bytes.fromhex("bbcc5698b2e841b2e66ad86f6217a6eb")
        initial_vector_buffer = bytes.fromhex("1a2fdc998810257434016a68d0ce57e7")

        encrypted_data = encrypt_response(response_body, aes_key_buffer, initial_vector_buffer)
        bot_response = encrypted_data
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
    data = CallbackUtility.pyscript_handler(event, None)
    assert data["statusCode"] == 200
    assert data["statusDescription"] == "200 OK"
    assert data["isBase64Encoded"] is False
    assert data["headers"]["Content-Type"] == "text/html; charset=utf-8"

    assert data["body"]["aes_key_buffer"] == b'\xbb\xccV\x98\xb2\xe8A\xb2\xe6j\xd8ob\x17\xa6\xeb'
    assert data["body"]["initial_vector_buffer"] == b'\x1a/\xdc\x99\x88\x10%t4\x01jh\xd0\xceW\xe7'

    assert "encrypted_data" in data["body"]
    assert "bot_response" in data["body"]
    assert data["body"]["encrypted_data"] == data["body"]["bot_response"]


def test_pyscript_handler_for_encrypt_response_missing_aes_key_buffer():
    source_code = '''
        response_body = {
            "APPOINTMENT": {
                "screen": "APPOINTMENT",
                "data": {
                    "department": [
                        {"id": "shopping", "title": "Shopping & Groceries"},
                        {"id": "clothing", "title": "Clothing & Apparel"},
                        {"id": "home", "title": "Home Goods & Decor"},
                        {"id": "electronics", "title": "Electronics & Appliances"},
                        {"id": "beauty", "title": "Beauty & Personal Care"},
                    ]
                }
            }
        }        
        aes_key_buffer = None
        initial_vector_buffer = bytes.fromhex("1a2fdc998810257434016a68d0ce57e7")

        encrypted_data = encrypt_response(response_body, aes_key_buffer, initial_vector_buffer)
        bot_response = encrypted_data
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
    data = CallbackUtility.pyscript_handler(event, None)
    assert data == {
        'statusCode': 422,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': 'Script execution error: encryption failed-AES key cannot be None'
    }


def test_pyscript_handler_for_encrypt_response_missing_initial_vector_buffer():
    source_code = '''
        response_body = {
            "APPOINTMENT": {
                "screen": "APPOINTMENT",
                "data": {
                    "department": [
                        {"id": "shopping", "title": "Shopping & Groceries"},
                        {"id": "clothing", "title": "Clothing & Apparel"},
                        {"id": "home", "title": "Home Goods & Decor"},
                        {"id": "electronics", "title": "Electronics & Appliances"},
                        {"id": "beauty", "title": "Beauty & Personal Care"},
                    ]
                }
            }
        }
        aes_key_buffer = bytes.fromhex("bbcc5698b2e841b2e66ad86f6217a6eb")
        initial_vector_buffer = None

        encrypted_data = encrypt_response(response_body, aes_key_buffer, initial_vector_buffer)
        bot_response = encrypted_data
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
    data = CallbackUtility.pyscript_handler(event, None)
    assert data == {
        'statusCode': 422,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': 'Script execution error: encryption failed-Initialization vector (IV) cannot be None'
    }


@patch("kairon.shared.callback.data_objects.CallbackData.save", MagicMock())
@patch("kairon.shared.callback.data_objects.CallbackConfig.get_auth_token",
       MagicMock(return_value=("auth_token", False)))
def test_pyscript_handler_create_callback():
    data = {
        "name": "test_action",
        "callback_name": "test_callback",
        "bot": "test_bot",
        "sender_id": "sender_123",
        "channel": "test_channel",
        "metadata": {}
    }
    url = CallbackUtility.create_callback(**data)
    assert "/callback/d" in url
    assert "/auth_token" in url


@patch("kairon.shared.callback.data_objects.CallbackData.save", MagicMock())
@patch("kairon.shared.callback.data_objects.CallbackConfig.get_auth_token",
       MagicMock(return_value=("auth_token", True)))
def test_pyscript_handler_create_callback_standalone():
    data = {
        "name": "test_action",
        "callback_name": "test_callback",
        "bot": "test_bot",
        "sender_id": "sender_123",
        "channel": "test_channel",
        "metadata": {}
    }
    identifier = CallbackUtility.create_callback(**data)
    assert bool(re.fullmatch(r"[0-9a-f]{12}7[0-9a-f]{3}[89ab][0-9a-f]{15}", identifier, re.IGNORECASE))
    assert len(identifier) == 32
    assert not "/callback/d" in identifier


def test_pyscript_handler_create_callback_in_pyscript():
    CallbackConfig.create_entry(bot='test_bot', name='callback_py_1', pyscript_code='bot_response="hello world"')
    source_code = '''
    bot_response = create_callback('callback_py_1', {'name': 'spandan', 'age': 20})
    '''
    source_code = textwrap.dedent(source_code)
    event = {'source_code': source_code,
             'predefined_objects':
                 {'bot': 'test_bot',
                  'sender_id': '917506075263',
                  'channel': 'whatsapp',
                  'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
                  'slot': {},
                  'intent': 'k_multimedia_msg'
                  }
             }
    data = CallbackUtility.pyscript_handler(event, None)
    assert data['statusCode'] == 200
    bot_response = data['body']['bot_response']
    assert "/callback/d" in bot_response
    assert len(bot_response) > 32
    CallbackConfig.objects(bot='test_bot', name='callback_py_1').delete()


def test_pyscript_handler_create_callback_in_pyscript_standalone():
    CallbackConfig.create_entry(bot='test_bot',
                                name='callback_py_1',
                                pyscript_code='bot_response="hello world"',
                                standalone=True,
                                standalone_id_path='id')
    source_code = '''
    bot_response = create_callback('callback_py_1', {'name': 'spandan', 'age': 20})
    '''
    source_code = textwrap.dedent(source_code)
    event = {'source_code': source_code,
             'predefined_objects':
                 {'bot': 'test_bot',
                  'sender_id': '917506075263',
                  'channel': 'whatsapp',
                  'user_message': '/k_multimedia_msg{"latitude": "25.2435955", "longitude": "82.9430092"}',
                  'slot': {},
                  'intent': 'k_multimedia_msg'
                  }
             }
    data = CallbackUtility.pyscript_handler(event, None)
    assert data['statusCode'] == 200
    bot_response = data['body']['bot_response']
    assert not "/callback/d" in bot_response
    assert len(bot_response) == 32

    def is_hex(s: str) -> bool:
        try:
            int(s, 16)
            return True
        except ValueError:
            return False

    assert is_hex(bot_response)
    CallbackConfig.objects(bot='test_bot', name='callback_py_1').delete()


def test_trigger_email():
    with patch("kairon.async_callback.utils.SMTP", autospec=True) as mock:
        content_type = "html"
        to_email = "test@demo.com"
        subject = "Test"
        body = "Test"
        smtp_url = "localhost"
        smtp_port = 293
        sender_email = "dummy@test.com"
        smtp_password = "test"
        smtp_userid = None
        tls = False

        CallbackUtility.trigger_email(
            [to_email],
            subject,
            body,
            content_type=content_type,
            smtp_url=smtp_url,
            smtp_port=smtp_port,
            sender_email=sender_email,
            smtp_userid=smtp_userid,
            smtp_password=smtp_password,
            tls=tls,
        )

        mbody = MIMEText(body, content_type)
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender_email
        msg["To"] = to_email
        msg.attach(mbody)

        name, args, kwargs = mock.method_calls.pop(0)
        assert name == "().connect"
        assert {} == kwargs

        host, port = args
        assert host == smtp_url
        assert port == port

        name, args, kwargs = mock.method_calls.pop(0)
        assert name == "().login"
        assert {} == kwargs

        from_email, password = args
        assert from_email == sender_email
        assert password == smtp_password

        name, args, kwargs = mock.method_calls.pop(0)
        assert name == "().sendmail"
        assert {} == kwargs

        assert args[0] == sender_email
        assert args[1] == [to_email]
        assert str(args[2]).__contains__(subject)
        assert str(args[2]).__contains__(body)


def test_trigger_email_tls():
    with patch("kairon.async_callback.utils.SMTP", autospec=True) as mock:
        content_type = "html"
        to_email = "test@demo.com"
        subject = "Test"
        body = "Test"
        smtp_url = "localhost"
        smtp_port = 293
        sender_email = "dummy@test.com"
        smtp_password = "test"
        smtp_userid = None
        tls = True

        CallbackUtility.trigger_email(
            [to_email],
            subject,
            body,
            content_type=content_type,
            smtp_url=smtp_url,
            smtp_port=smtp_port,
            sender_email=sender_email,
            smtp_userid=smtp_userid,
            smtp_password=smtp_password,
            tls=tls,
        )

        name, args, kwargs = mock.method_calls.pop(0)
        assert name == "().connect"
        assert {} == kwargs

        host, port = args
        assert host == smtp_url
        assert port == port

        name, args, kwargs = mock.method_calls.pop(0)
        assert name == "().starttls"
        assert {} == kwargs

        name, args, kwargs = mock.method_calls.pop(0)
        assert name == "().login"
        assert {} == kwargs

        from_email, password = args
        assert from_email == sender_email
        assert password == smtp_password

        name, args, kwargs = mock.method_calls.pop(0)
        assert name == "().sendmail"
        assert {} == kwargs

        assert args[0] == sender_email
        assert args[1] == [to_email]
        assert str(args[2]).__contains__(subject)
        assert str(args[2]).__contains__(body)


def test_trigger_email_using_smtp_userid():
    with patch("kairon.async_callback.utils.SMTP", autospec=True) as mock:
        content_type = "html"
        to_email = "test@demo.com"
        subject = "Test"
        body = "Test"
        smtp_url = "localhost"
        smtp_port = 293
        sender_email = "dummy@test.com"
        smtp_password = "test"
        smtp_userid = "test_user"
        tls = True

        CallbackUtility.trigger_email(
            [to_email],
            subject,
            body,
            content_type=content_type,
            smtp_url=smtp_url,
            smtp_port=smtp_port,
            sender_email=sender_email,
            smtp_userid=smtp_userid,
            smtp_password=smtp_password,
            tls=tls,
        )

        name, args, kwargs = mock.method_calls.pop(0)
        assert name == "().connect"
        assert {} == kwargs

        host, port = args
        assert host == smtp_url
        assert port == port

        name, args, kwargs = mock.method_calls.pop(0)
        assert name == "().starttls"
        assert {} == kwargs

        name, args, kwargs = mock.method_calls.pop(0)
        assert name == "().login"
        assert {} == kwargs

        from_email, password = args
        assert from_email == smtp_userid
        assert password == smtp_password

        name, args, kwargs = mock.method_calls.pop(0)
        assert name == "().sendmail"
        assert {} == kwargs

        assert args[0] == sender_email
        assert args[1] == [to_email]
        assert str(args[2]).__contains__(subject)
        assert str(args[2]).__contains__(body)
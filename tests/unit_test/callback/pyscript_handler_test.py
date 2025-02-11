import os
import textwrap
from unittest.mock import patch

import pytest
import responses
from deepdiff import DeepDiff
from mongoengine import connect

from kairon import Utility

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
            'response': response
        }}
    ]
    data = CallbackUtility.pyscript_handler(event, None)
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


@patch("kairon.async_callback.utils.SMTP", autospec=True)
@patch("kairon.shared.utils.SMTP", autospec=True)
def test_lambda_handler_for_send_email(mock_utils_smtp, mock_smtp):
    from kairon.shared.actions.data_objects import EmailActionConfig
    EmailActionConfig(
        action_name="email_action",
        smtp_url="smtp.gmail.com",
        smtp_port=293,
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
    data = CallbackUtility.pyscript_handler(event, None)
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
    assert data['body'] == 'Missing bot id'
    assert data == {
        'statusCode': 422,
        'statusDescription': '200 OK',
        'isBase64Encoded': False,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': 'Missing bot id'
    }


@responses.activate
@patch("pymongo.collection.Collection.insert_one", autospec=True)
@patch("kairon.async_callback.utils.uuid7")
def test_lambda_handler_with_add_schedule_job(mock_uuid7, mock_add_job):
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
        args, kwargs = mock_add_job.call_args
        print(args, kwargs)
        assert args[1]['_id']
        assert args[1]['next_run_time']
        assert args[1]['job_state']
        import pickle
        job_state = pickle.loads(args[1]['job_state'])
        print(job_state)
        assert job_state['args'][1] == 'scheduler_evaluator'
        assert not DeepDiff(list(job_state['args'][2]['predefined_objects'].keys()), ['user', 'bot', 'event'],
                            ignore_order=True)
        assert job_state['args'][2]['predefined_objects']['bot'] == 'test_bot'
        assert job_state['args'][2]['predefined_objects']['user'] == 'test user sep 12'
        assert 'event' in job_state['args'][2]['predefined_objects']


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
        'body': 'Missing bot id'
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

    # resp = add_data(sender_id,json_data)
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
        'body': 'Missing bot id'
    }


def test_pyscript_handler_for_update_data():
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
    assert bot_response == {'message': 'Record updated!', 'data': {'_id': pytest.collection_id}}
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
                          'data': {'mobile_number': '919876543210', 'name': 'Mahesh SV'}},
            'resp': bot_response,
            'collection_id': pytest.collection_id,

        }
    }


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
        'body': 'Missing bot id'
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
    assert bot_response['data'][0]['collection_name'] == 'testing_crud_api'
    assert bot_response['data'][0]['is_secure'] == []
    assert bot_response['data'][0]['data'] == {'mobile_number': '919876543210', 'name': 'Mahesh SV'}
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


def test_pyscript_handler_for_delete_data():
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
    assert bot_response == {'message': f'Collection with ID {pytest.collection_id} has been successfully deleted.',
                            'data': {'_id': pytest.collection_id}}
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
                          'data': {'mobile_number': '919876543210', 'name': 'Mahesh SV'}},
            'resp': bot_response,
            'collection_id': pytest.collection_id,

        }
    }


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
        'body': 'Missing bot id'
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

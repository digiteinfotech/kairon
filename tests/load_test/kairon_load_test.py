import inspect
import logging
import os

from locust import HttpUser, between, SequentialTaskSet, events, task, runners
from locust.exception import StopUser
from mongoengine import connect, disconnect
from rasa.utils.io import read_config_file
from smart_config import ConfigLoader

from tests.load_test.data_objects import User, Account, Bot

USERS_INFO = []


def create_test_data(num_users=1000):
    global USERS_INFO
    logging.info('Creating test data..')
    USERS_INFO = []
    for i in range(1, num_users):
        email = 'user{0}@demo.ai'.format(i)
        first_name = 'load'
        last_name = 'test'
        password = 'Welcome@1'
        account = 'user{0}'.format(i)
        bot = 'user{0}'.format(i)
        USERS_INFO.append((email, first_name, last_name, password, account, bot))


@events.test_start.add_listener
def on_test_start(**kwargs):
    global USERS_INFO
    if len(USERS_INFO) == 0:
        create_test_data(2)


def stop_user():
    raise StopUser()


class ExecuteTask(SequentialTaskSet):
    wait_time = between(1, 2)

    @task
    class Register(SequentialTaskSet):

        @task
        def register(self):
            user_info = USERS_INFO.pop()
            self.user.username = user_info[0]
            self.user.password = user_info[3]
            self.user.account = user_info[4]
            self.user.bot = user_info[5]
            request_body = {
                "email": user_info[0],
                "first_name": user_info[1],
                "last_name": user_info[2],
                "password": user_info[3],
                "confirm_password": user_info[3],
                "account": user_info[4],
                "bot": user_info[5],
            }
            with self.client.post("/api/account/registration",
                                  json=request_body,
                                  catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])
            self.interrupt()

    @task
    class Login(SequentialTaskSet):

        @task
        def login(self):
            header = {"username": self.user.username, "password": self.user.password}
            with self.client.post("/api/auth/login",
                                  data=header,
                                  catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                    else:
                        self.user.auth_token = response_data["data"]["token_type"] + " " + response_data["data"][
                            "access_token"]
            self.interrupt()

    @task
    class HttpAction(SequentialTaskSet):

        @task
        def add_http_action(self):
            request_body = {
                "intent": "slap",
                "auth_token": "bearer dfiuhdfishifoshfoishnfoshfnsifjfs",
                "action_name": "action_" + self.user.username,
                "response": "string",
                "http_url": "http://www.google.com",
                "request_method": "GET",
                "http_params_list": [{
                    "key": "testParam1",
                    "parameter_type": "value",
                    "value": "testValue1"
                }]
            }

            with self.client.post("/api/bot/action/httpaction",
                                  json=request_body,
                                  headers={"Authorization": self.user.auth_token},
                                  catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])

        @task
        def get_http_action(self):
            with self.client.get("/api/bot/action/httpaction/action_" + self.user.username,
                                 headers={"Authorization": self.user.auth_token},
                                 catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])

        @task
        def update_http_action(self):
            request_body = {
                "intent": "greet_test_update_http_action",
                "auth_token": "",
                "action_name": "action_" + self.user.username,
                "response": "",
                "http_url": "http://www.google.com",
                "request_method": "GET",
                "http_params_list": [{
                    "key": "testParam1",
                    "parameter_type": "value",
                    "value": "testValue1"
                }]
            }

            with self.client.put("/api/bot/action/httpaction",
                                 json=request_body,
                                 headers={"Authorization": self.user.auth_token},
                                 catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])

        @task
        def delete_http_action(self):
            with self.client.delete("/api/bot/action/httpaction/action_" + self.user.username,
                                    headers={"Authorization": self.user.auth_token},
                                    catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])
            self.interrupt()

    @task
    class Intents(SequentialTaskSet):

        @task
        def add_intents(self):
            with self.client.post("/api/bot/intents",
                                  json={"data": "happier"},
                                  headers={"Authorization": self.user.auth_token},
                                  catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])

        @task
        def get_intents(self):
            with self.client.get("/api/bot/intents",
                                 headers={"Authorization": self.user.auth_token},
                                 catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])

        @task
        def delete_intent(self):
            with self.client.delete("/api/bot/intents/happier/True",
                                    headers={"Authorization": self.user.auth_token},
                                    catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])
            self.interrupt()

    @task
    class TrainingExamples(SequentialTaskSet):

        @task
        def add_training_example(self):
            with self.client.post("/api/bot/training_examples/greet",
                                  json={"data": ["How do you do?"]},
                                  headers={"Authorization": self.user.auth_token},
                                  catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])

        @task
        def get_training_example(self):
            with self.client.get("/api/bot/training_examples/greet",
                                 headers={"Authorization": self.user.auth_token},
                                 catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])

        @task
        def update_training_example(self):
            with self.client.get("/api/bot/training_examples/greet",
                                 headers={"Authorization": self.user.auth_token},
                                 catch_response=True) as training_examples:
                if training_examples.text is None or not training_examples.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    training_examples.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + training_examples.text)
                    response_data = training_examples.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        training_examples.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        return

            with self.client.put("/api/bot/training_examples/greet/" + response_data["data"][0]["_id"],
                                 json={"data": "hey, there"},
                                 headers={"Authorization": self.user.auth_token},
                                 catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])

        @task
        def delete_training_example(self):
            with self.client.get("/api/bot/training_examples/greet",
                                 headers={"Authorization": self.user.auth_token},
                                 catch_response=True) as training_examples:
                if training_examples.text is None or not training_examples.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    training_examples.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + training_examples.text)
                    response_data = training_examples.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        training_examples.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        return

            with self.client.delete("/api/bot/training_examples",
                                    json={"data": response_data["data"][0]["_id"]},
                                    headers={"Authorization": self.user.auth_token},
                                    catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])
            self.interrupt()

    @task
    class Responses(SequentialTaskSet):

        @task
        def add_response(self):
            with self.client.post("/api/bot/response/utter_greet",
                                  json={"data": "Wow! How are you?"},
                                  headers={"Authorization": self.user.auth_token},
                                  catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])

        @task
        def get_response(self):
            with self.client.get("/api/bot/response/utter_greet",
                                 headers={"Authorization": self.user.auth_token},
                                 catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])

        @task
        def update_response(self):
            with self.client.get("/api/bot/response/utter_greet",
                                 headers={"Authorization": self.user.auth_token},
                                 catch_response=True) as training_examples:
                if training_examples.text is None or not training_examples.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    training_examples.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + training_examples.text)
                    response_data = training_examples.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        training_examples.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])

            with self.client.put("/api/bot/response/utter_greet/" + response_data["data"][0]["_id"],
                                 json={"data": "Hello, How are you!"},
                                 headers={"Authorization": self.user.auth_token},
                                 catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])

        @task
        def delete_response(self):
            with self.client.get("/api/bot/response/utter_greet",
                                 headers={"Authorization": self.user.auth_token},
                                 catch_response=True) as training_examples:
                if training_examples.text is None or not training_examples.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    training_examples.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + training_examples.text)
                    response_data = training_examples.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        training_examples.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])

            with self.client.delete("/api/bot/response",
                                    json={"data": response_data["data"][0]["_id"]},
                                    headers={"Authorization": self.user.auth_token},
                                    catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])
            self.interrupt()

    @task
    class Stories(SequentialTaskSet):

        @task
        def add_story(self):
            request = {
                "name": "test_path",
                "events": [
                    {"name": "greet", "type": "user"},
                    {"name": "utter_greet", "type": "action"},
                ],
            }
            with self.client.post("/api/bot/stories",
                                  json=request,
                                  headers={"Authorization": self.user.auth_token},
                                  catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])

        @task
        def get_story(self):
            with self.client.get("/api/bot/stories",
                                 headers={"Authorization": self.user.auth_token},
                                 catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])

        @task
        def get_utterance_from_intent(self):
            with self.client.get("/api/bot/utterance_from_intent/greet",
                                 headers={"Authorization": self.user.auth_token},
                                 catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])
            self.interrupt()

    @task
    class Endpoint(SequentialTaskSet):

        @task
        def set_endpoint(self):
            with self.client.put("/api/bot/endpoint",
                                 json={"bot_endpoint": {"url": "http://localhost:5005/"},
                                       "action_endpoint": {"url": "http://localhost:5000/"},
                                       "tracker_endpoint": {"url": "mongodb://localhost:27017", "db": "rasa"}},
                                 headers={"Authorization": self.user.auth_token},
                                 catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])

        @task
        def get_endpoint(self):
            with self.client.get("/api/bot/endpoint",
                                 headers={"Authorization": self.user.auth_token},
                                 catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])
            self.interrupt()

    @task
    class Configurations(SequentialTaskSet):

        @task
        def set_config(self):
            with self.client.put("/api/bot/config",
                                 json=read_config_file('./template/config/default.yml'),
                                 headers={"Authorization": self.user.auth_token},
                                 catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])

        @task
        def get_config(self):
            with self.client.get("/api/bot/config",
                                 headers={"Authorization": self.user.auth_token},
                                 catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])
            self.interrupt()

    @task
    class Templates(SequentialTaskSet):

        @task
        def set_templates(self):
            with self.client.post("/api/bot/templates/use-case",
                                  json={"data": "Hi-Hello"},
                                  headers={"Authorization": self.user.auth_token},
                                  catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])

        @task
        def get_templates(self):
            with self.client.get("/api/bot/templates/use-case",
                                 headers={"Authorization": self.user.auth_token},
                                 catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])

        @task
        def set_config_templates(self):
            with self.client.post("/api/bot/templates/config",
                                  json={"data": "default"},
                                  headers={"Authorization": self.user.auth_token},
                                  catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])

        @task
        def get_config_templates(self):
            with self.client.get("/api/bot/templates/config",
                                 headers={"Authorization": self.user.auth_token},
                                 catch_response=True) as response:
                if response.text is None or not response.text.strip():
                    logging.error(inspect.stack()[0][3] + " Failed: response is None")
                    response.failure(inspect.stack()[0][3] + " Failed: response is None")
                else:
                    logging.info(inspect.stack()[0][3] + ": " + response.text)
                    response_data = response.json()
                    if not response_data["success"]:
                        logging.error(inspect.stack()[0][3] + " Failed: " + response_data['message'])
                        response.failure(inspect.stack()[0][3] + " Failed: " + response_data['message'])
            raise StopUser()


class KaironUser(HttpUser):
    tasks = [ExecuteTask]
    wait_time = between(1, 2)

    auth_token = None
    username = None
    account = None
    bot = None

    def on_stop(self):
        logging.info("Cleaning up database..")
        try:
            os.environ["system_file"] = "./tests/testing_data/system.yaml"
            env = ConfigLoader(os.getenv("system_file", "./system.yaml")).get_config()
            logging.info("Connecting to: " + env['database']["load_test"])
            connect(host=env['database']["load_test"])
            User.objects(email=self.username).delete()
            Bot.objects(name=self.bot).delete()
            Account.objects(name=self.account).delete()
            logging.info("Cleanup complete")
            disconnect()
        except Exception as e:
            logging.error(e)


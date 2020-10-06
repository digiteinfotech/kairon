import inspect
import logging

from locust import HttpUser, SequentialTaskSet, between, task
from locust.exception import StopUser


class ExecuteTask(SequentialTaskSet):

    """
    Load test for questions service.

    locust -f stress_test/questions_stress_test.py --headless -u 1000 -r 100 --host=http://localhost:8000
    u: number of users
    r: rate at which users are spawned
    host: base url where requests are hit
    headless: run with CLI only

    To run from UI:
    locust -f stress_test/questions_stress_test.py -u 1000 -r 100 --host=http://localhost:8000
    """
    wait_time = between(1, 2)

    @task
    def get_questions_1(self):
        request_body = {"data": "where is digite located?"}
        with self.client.post("/questions",
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

    @task
    def get_questions_2(self):
        request_body = {"data": "Can i get a glass of water?"}
        with self.client.post("/questions",
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

    @task
    def get_questions_3(self):
        request_body = {"data": "This bag is full of apples. What about peaches?"}
        with self.client.post("/questions",
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

    @task
    def get_questions_4(self):
        request_body = {"data": "I dont feel like doing any work because I am too lazy!!"}
        with self.client.post("/questions",
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

    @task
    def get_questions_5(self):
        request_body = {
            "data": "The weather is very humid today. Let's get to some place cooler. Can you tell me if its snowing?"}
        with self.client.post("/questions",
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

    @task
    def get_questions_6(self):
        request_body = {"data": "I wake up at 3:00am. What time to you wake up daily?"}
        with self.client.post("/questions",
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

    @task
    def get_questions_7(self):
        request_body = {
            "data": "Today is 21st Aug 2020. I think he celebrates his birthday on 11th Dec. Maybe his father's anniversory is on 5-11-1995"}
        with self.client.post("/questions",
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

    @task
    def get_questions_8(self):
        request_body = {
            "data": "Give me $5 and i will give you ten notes of Rs. 500, rupees 2000, 100 rupees and ten dollars."}
        with self.client.post("/questions",
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

    @task
    def get_questions_9(self):
        request_body = {"data": "cannot believe my internet speed went from 200kb/s to 0.2MBps!!"}
        with self.client.post("/questions",
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

    @task
    def get_questions_10(self):
        request_body = {
            "data": "jan is my favorite month because it snows heavily and thats the reason i named my daughter jan"}
        with self.client.post("/questions",
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

    @task
    def get_questions_11(self):
        request_body = {
            "data": "How far away is SUN from earth ? 149,600,000 kilometers (km) or 92,900,000 miles !! whoaaa!!"}
        with self.client.post("/questions",
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

    @task
    def get_questions_12(self):
        request_body = {"data": "Planning to go to uranous coz it has rains diamonds there."}
        with self.client.post("/questions",
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

    @task
    def get_questions_13(self):
        request_body = {
            "data": "astrophotography is beautiful to see but not a child's play when actually doing it. correct?"}
        with self.client.post("/questions",
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

    @task
    def get_questions_14(self):
        request_body = {
            "data": "If two pieces of the same type of metal touch in space, they will bond and be permanently stuck together"}
        with self.client.post("/questions",
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

    @task
    def get_questions_15(self):
        request_body = {"data": "water and mercury can exist in all the three states of matter"}
        with self.client.post("/questions",
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

    @task
    def get_questions_16(self):
        request_body = {"data": "Going to work is more dangerous than going to war."}

        with self.client.post("/questions",
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
        raise StopUser()


class QuestioningUser(HttpUser):
    tasks = [ExecuteTask]

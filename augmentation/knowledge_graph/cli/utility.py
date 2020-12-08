import json
from typing import Dict
from urllib.parse import urljoin

import requests


class TrainingDataGeneratorUtil:

    @staticmethod
    def http_request(method: str, url: str, token: str, user: str, json_body: Dict = None):
        headers = {'content-type': 'application/json', 'X-USER': user}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        response = requests.request(method, url, headers=headers, json=json_body)
        return json.loads(response.text)

    @staticmethod
    def set_training_data_status(kairon_url: str, status: Dict, user: str, token: str):
        return TrainingDataGeneratorUtil.http_request('PUT', urljoin(kairon_url, "/api/bot/processing-status"), token,
                                                      user, status)

    @staticmethod
    def fetch_latest_data_generator_status(kairon_url: str, user: str, token: str):
        response = TrainingDataGeneratorUtil.http_request('GET',
                                                          urljoin(kairon_url, "/api/bot/data/generation/latest"),
                                                          token,
                                                          user)
        return response['data']

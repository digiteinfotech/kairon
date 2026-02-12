import asyncio
import json
import urllib

from datetime import datetime
from http import HTTPStatus
from loguru import logger as logging
from typing import Text, List, Union, Dict
from urllib import parse

import requests
from loguru import logger
from orjson import orjson
from tiktoken import get_encoding
from urllib.parse import urljoin

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.actions.data_objects import DatabaseAction, HttpActionConfig
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.admin.processor import Sysadmin
from kairon.shared.channels.whatsapp.bsp.dialog360 import BSP360Dialog
from kairon.shared.data.constant import DEFAULT_LLM, QDRANT_SUFFIX
from kairon.shared.data.data_objects import UserMediaData
from kairon.shared.models import UserMediaUploadStatus, UserMediaUploadType


class PyscriptUtility:

    @staticmethod
    def srtptime(date_string: str, formate: str):
        return datetime.strptime(date_string, formate)

    @staticmethod
    def srtftime(date_string: datetime, formate: str):
        return date_string.strftime(formate)

    @staticmethod
    def url_parse_quote_plus(string, safe='', encoding=None, errors=None):
        return parse.quote_plus(string, safe, encoding, errors)

    @staticmethod
    def get_embedding(texts: Union[Text, List[Text]], user: str, bot: str,
                      invocation: str) -> Union[List[float], List[List[float]]]:
        """
        Get embeddings for a batch of texts using LiteLLM.

        Args:
            texts (Union[Text, List[Text]]): Text or list of texts to generate embeddings for.
            user (str): User information for embedding metadata.
            bot (str): Bot identifier for embedding metadata.
            invocation (str): Invocation identifier for embedding metadata.

        Returns:
            Union[List[float], List[List[float]]]: A single embedding or a list of embeddings.
        """
        tokenizer = get_encoding("cl100k_base")
        embedding_ctx_length = 8191

        is_single_text = isinstance(texts, str)
        if is_single_text:
            texts = [texts]

        truncated_texts = []
        for text in texts:
            tokens = tokenizer.encode(text)[:embedding_ctx_length]
            truncated_texts.append(tokenizer.decode(tokens))

        llm_secret = Sysadmin.get_llm_secret(llm_type=DEFAULT_LLM, bot=bot)

        body = {
            "text": texts,
            "user": user,
            "kwargs": {
                "truncated_texts": truncated_texts,
                "api_key": llm_secret.get("api_key"),
                "invocation": invocation,
            }
        }

        timeout = Utility.environment["llm"].get("request_timeout", 30)
        url = f"{Utility.environment['llm']['url']}/{urllib.parse.quote(bot)}/aembedding/{DEFAULT_LLM}"
        response = requests.request(
            method="POST",
            url=url,
            json=body,
            timeout=timeout
        )

        logging.info(f"LLM request completed with status {response.status_code} for bot: {bot}")
        if response.status_code not in [200, 201, 202, 203, 204]:
            raise Exception(HTTPStatus(response.status_code).phrase)

        http_response = response.json()
        if is_single_text and isinstance(http_response, list):
            return http_response[0]
        return http_response

    @staticmethod
    def perform_operation(data: dict, user: str, **kwargs):
        request = {}
        vector_db_url = Utility.environment['vector']['db']
        url = urljoin(vector_db_url, f"/collections/{kwargs.pop('collection_name')}/points/scroll")
        if "embedding_search" in data:
            user_msg = data.get("embedding_search")
            if user_msg and isinstance(user_msg, str):
                vector = PyscriptUtility.get_embedding(user_msg, user, invocation='db_action_qdrant', **kwargs)
                request['query'] = vector

        if "payload_search" in data:
            payload = data.get("payload_search")
            if payload:
                request.update(**payload)

        if request:
            request.update(**{'with_payload': True})
            if 'limit' not in request:
                request['limit'] = 10
            response = requests.post(url, json=request)
            result = response.json()
        else:
            raise Exception('No Operation to perform')
        return result

    @staticmethod
    def get_payload(payload: List[Dict], predefined_objects: dict):
        request_payload = {}
        for item in payload:
            query_type = item.get('query_type')
            if item.get('type') == "from_slot":
                value = predefined_objects.get("slot", {}).get(item.get('value'))
            elif item.get('type') == "from_user_message":
                value = predefined_objects.get("latest_message", {}).get("text")
                if not ActionUtility.is_empty(value) and value.startswith("/"):
                    msg = next(
                        (entity["value"] for entity in predefined_objects.get("latest_message", {}).get("entities", [])
                         if entity["entity"] == "kairon_user_msg"),
                        None
                    )
                    if not ActionUtility.is_empty(msg):
                        value = msg
            else:
                value = item.get('value')

            if query_type == "payload_search":
                try:
                    if isinstance(value, str):
                        request_payload["payload_search"] = json.loads(value)
                    else:
                        request_payload["payload_search"] = value
                except json.JSONDecodeError as e:
                    logger.debug(e)
                    raise Exception(f"Error converting payload to JSON: {value}")
            else:
                if "embedding_search" not in request_payload:
                    request_payload["embedding_search"] = value
                else:
                    request_payload["embedding_search"] += f" {value}"
        return request_payload

    @staticmethod
    def get_db_action_data(action_name: str, user: str, payload_dict: dict, bot: str, predefined_objects: dict):
        print(action_name, user, payload_dict, bot)
        database_action_config = DatabaseAction.objects(bot=bot, name=action_name,
                                                        status=True).get().to_mongo().to_dict()
        print(database_action_config)

        collection_name = f"{bot}_{database_action_config['collection']}{QDRANT_SUFFIX}"
        payload = database_action_config["payload"]
        query_type = payload[0]["query_type"]
        print(payload, query_type)
        data = {query_type: payload_dict} if payload_dict else PyscriptUtility.get_payload(payload, predefined_objects)
        response = PyscriptUtility.perform_operation(data, user=user, bot=bot, collection_name=collection_name)
        return response

    @staticmethod
    def api_call(action_name: str, user: str, payload: dict, headers: dict, bot: str, predefined_objects: dict):
        http_action_config = HttpActionConfig.objects.get(bot=bot,
                                                          action_name=action_name, status=True).to_mongo().to_dict()
        request_method = http_action_config['request_method']
        http_url = http_action_config['http_url']
        request_body = payload
        http_url = ActionUtility.prepare_url(http_url=http_url, tracker_data=predefined_objects)
        headers = headers if headers else ActionUtility.prepare_request(predefined_objects,
                                                                        http_action_config.get('headers'), bot)

        http_response = requests.request(
            request_method.upper(), http_url, headers=headers, json=request_body
        )
        if http_response.status_code != 200:
            response = http_response.text
            raise Exception(response)
        else:
            response = http_response.json()
            logger.info(response)
        print(http_response)
        return response

    @staticmethod
    def send_waba_message(payload: dict, key: Text, bot: str, predefined_objects: dict):
        waba_url = "https://waba-v2.360dialog.io/messages"
        headers = {"D360-API-KEY": key, "Content-TYpe": "application/json"}
        return requests.post(url=waba_url, headers=headers, data=orjson.dumps(payload)).json

    @staticmethod
    def upload_media_to_360dialog(bot: str, bsp_type: str, media_id: str):
        external_media_id = asyncio.run(BSP360Dialog.upload_media(bot, bsp_type, media_id))
        return external_media_id

    @staticmethod
    def fetch_media_ids(bot: str):
        try:
            media_data = UserMediaData.objects(
                bot = bot,
                upload_status = UserMediaUploadStatus.completed.value,
                media_id__ne = "",
                upload_type__in = [UserMediaUploadType.user_uploaded.value, UserMediaUploadType.system_uploaded.value]
            ).only("filename", "media_id")

            if not media_data:
                return []

            return [{"filename": doc.filename, "media_id": doc.media_id} for doc in media_data]

        except Exception as e:
            raise AppException(f"Error while fetching media ids for bot '{bot}': {str(e)}")
import asyncio
import ujson as json
from unittest import mock

import pytest

from kairon.exceptions import AppException
from kairon.shared.rest_client import AioRestClient


class TestAioRestClient:

    @pytest.mark.asyncio
    async def test_aio_rest_client_get_request(self, aioresponses):
        url = 'http://kairon.com'
        aioresponses.get("http://kairon.com/?loc=blr&name=udit.pandey", status=200, payload=dict(data='hi!'))
        resp = await AioRestClient().request("get", url, request_body={"name": "udit.pandey", "loc": "blr"},
                                             headers={"Authorization": "Bearer sasdfghjkytrtyui"})
        assert resp == {"data": "hi!"}

        aioresponses.get(url, status=200, payload=dict(data='hi!'))
        resp = await AioRestClient().request("get", url)
        assert resp == {"data": "hi!"}

    @pytest.mark.asyncio
    async def test_aio_rest_client_no_headers(self, aioresponses):
        url = 'http://kairon.com'
        aioresponses.get("http://kairon.com/?loc=blr&name=udit.pandey", status=200, payload=dict(data='hi!'))
        resp = await AioRestClient().request("get", url, request_body={"name": "udit.pandey", "loc": "blr"})
        assert resp == {"data": "hi!"}
        assert list(aioresponses.requests.values())[0][0].kwargs == {'allow_redirects': True, 'timeout': None,
                                                                     "headers": {},
                                                                     'params': {'loc': 'blr', 'name': 'udit.pandey'},
                                                                     'trace_request_ctx': {'current_attempt': 1}}

    @pytest.mark.asyncio
    async def test_aio_rest_client_connection_error(self, aioresponses):
        url = 'http://kairon.com'
        aioresponses.get(url, status=200, payload={"data": "hi!"})
        with pytest.raises(AppException, match="Failed to connect to service: kairon.com"):
            await AioRestClient().request("get", url, request_body={"name": "udit.pandey", "loc": "blr"},
                                          headers={"Authorization": "Bearer sasdfghjkytrtyui"})

        with pytest.raises(AppException, match="Failed to connect to service: kairon.com"):
            await AioRestClient().request("get", url, request_body={"name": "udit.pandey", "loc": "blr"},
                                          headers={"Authorization": "Bearer sasdfghjkytrtyui"}, max_retries=3)

    @pytest.mark.asyncio
    async def test_aio_rest_client_put_request(self, aioresponses):
        url = 'http://kairon.com'
        aioresponses.put("http://kairon.com", status=200, payload=dict(data='hi!'))
        resp = await AioRestClient().request("put", url, request_body={"name": "pandey.udit", "loc": "del"},
                                             headers={"Authorization": "Bearer sasdfghjkytrtyui"})
        assert resp == {"data": "hi!"}
        assert list(aioresponses.requests.values())[0][0].kwargs == {'allow_redirects': True, 'headers': {
            'Authorization': 'Bearer sasdfghjkytrtyui'}, 'json': {'loc': 'del', 'name': 'pandey.udit'}, 'timeout': None,
                                                                     'trace_request_ctx': {'current_attempt': 1}}

    @pytest.mark.asyncio
    async def test_aio_rest_client_post_request(self, aioresponses):
        url = 'http://kairon.com'
        aioresponses.post("http://kairon.com", status=200, payload=dict(data='hi!'))
        resp = await AioRestClient().request("post", url, request_body={"name": "udit.pandey", "loc": "blr"},
                                             headers={"Authorization": "Bearer sasdfghjkytrtyui"})
        assert resp == {"data": "hi!"}
        assert list(aioresponses.requests.values())[0][0].kwargs == {'allow_redirects': True, 'headers': {
            'Authorization': 'Bearer sasdfghjkytrtyui'}, 'json': {'loc': 'blr', 'name': 'udit.pandey'}, 'timeout': None,
                                                                     'data': None,
                                                                     'trace_request_ctx': {'current_attempt': 1}}

        aioresponses.post(url, status=200, payload=dict(data='hi!'))
        resp = await AioRestClient().request("post", url)
        assert resp == {"data": "hi!"}
        assert list(aioresponses.requests.values())[0][1].kwargs == {'allow_redirects': True, 'headers': {},
                                                                     'timeout': None, 'data': None, 'json': {},
                                                                     'trace_request_ctx': {'current_attempt': 1}}

    @pytest.mark.asyncio
    async def test_aio_rest_client_delete_request(self, aioresponses):
        url = 'http://kairon.com'
        aioresponses.delete("http://kairon.com/?loc=blr&name=udit.pandey", status=200, body="Deletion success!")
        resp = await AioRestClient().request("delete", url, request_body={"name": "udit.pandey", "loc": "blr"},
                                             headers={"Authorization": "Bearer sasdfghjkytrtyui"}, return_json=False)
        text = await resp.text()
        assert text == "Deletion success!"

    @pytest.mark.asyncio
    async def test_aio_rest_client_unsupported_request(self):
        url = 'http://kairon.com'
        with pytest.raises(AppException, match="Invalid request method!"):
            await AioRestClient().request("options", url, request_body={"name": "udit.pandey", "loc": "blr"},
                                          headers={"Authorization": "Bearer sasdfghjkytrtyui"})

    @pytest.mark.asyncio
    async def test_aio_rest_client_timeout_error(self, aioresponses):
        url = 'http://kairon.com'
        aioresponses.get(url, status=200, payload={"data": "hi!"})
        with mock.patch("kairon.shared.rest_client.AioRestClient._AioRestClient__trigger", side_effect=asyncio.TimeoutError("Request timed out")):
            with pytest.raises(AppException, match="Request timed out: Request timed out"):
                await AioRestClient().request("get", url, request_body={"name": "udit.pandey", "loc": "blr"},
                                              headers={"Authorization": "Bearer sasdfghjkytrtyui"})
            with pytest.raises(AppException, match="Request timed out: Request timed out"):
                await AioRestClient().request("get", url, request_body={"name": "udit.pandey", "loc": "blr"},
                                              headers={"Authorization": "Bearer sasdfghjkytrtyui"}, max_retries=3)

    @pytest.mark.asyncio
    async def test_aio_rest_client_post_request_stream(self, aioresponses):
        url = 'http://kairon.com'
        aioresponses.post("http://kairon.com", status=200, body=json.dumps({'data': 'hi!'}))
        resp = await AioRestClient().request("post", url, request_body={"name": "udit.pandey", "loc": "blr"},
                                         headers={"Authorization": "Bearer sasdfghjkytrtyui"}, is_streaming_resp=True)
        response = ''
        async for content in resp.content:
            response += content.decode()

        assert json.loads(response) == {"data": "hi!"}
        assert list(aioresponses.requests.values())[0][0].kwargs == {'allow_redirects': True, 'headers': {
            'Authorization': 'Bearer sasdfghjkytrtyui'}, 'json': {'loc': 'blr', 'name': 'udit.pandey'}, 'timeout': None,
                                                                     'data': None,
                                                                     'trace_request_ctx': {'current_attempt': 1}}
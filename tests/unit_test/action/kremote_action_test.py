import pytest
from aioresponses import aioresponses
from yarl import URL

from kairon.chat.actions import KRemoteAction
from rasa.utils.endpoints import EndpointConfig
from rasa.utils.endpoints import ClientResponseError


@pytest.mark.asyncio
async def test_multi_try_rasa_request_success():
    endpoint_config = EndpointConfig(url="http://test.com", headers={"Authorization": "Bearer token"})
    subpath = "path/to/resource"
    method = "post"
    response_data = {"key": "value"}

    with aioresponses() as mock:
        mock.post(f"http://test.com/{subpath}", payload=response_data, status=200)

        result = await KRemoteAction.multi_try_rasa_request(
            endpoint_config=endpoint_config, method=method, subpath=subpath
        )

        assert result == response_data

@pytest.mark.asyncio
async def test_multi_try_rasa_request_failure():
    endpoint_config = EndpointConfig(url="http://test.com")
    subpath = "invalid/path"
    method = "post"

    with aioresponses() as mock:
        # Simulate a 404 error response with a JSON body as bytes
        mock.post(
            f"http://test.com/{subpath}",
            status=404,
            body=b'{"error": "Not Found"}'
        )

        with pytest.raises(ClientResponseError) as exc_info:
            await KRemoteAction.multi_try_rasa_request(
                endpoint_config=endpoint_config, method=method, subpath=subpath
            )
        assert exc_info.value.status == 404
        assert exc_info.value.message == "Not Found"



@pytest.mark.asyncio
async def test_multi_try_rasa_request_ssl_error():
    endpoint_config = EndpointConfig(url="https://test.com", cafile="invalid/path/to/cafile")
    subpath = "path/to/resource"
    method = "post"

    with pytest.raises(FileNotFoundError):
        await KRemoteAction.multi_try_rasa_request(
            endpoint_config=endpoint_config, method=method, subpath=subpath
        )


@pytest.mark.asyncio
async def test_multi_try_rasa_request_retry_success():
    endpoint_config = EndpointConfig(url="http://test.com", headers={"Authorization": "Bearer token"})
    subpath = "path/to/resource"
    method = "post"
    success_response_data = {"key": "value"}

    with aioresponses() as mock:
        mock.post(f"http://test.com/{subpath}", status=500)
        mock.post(f"http://test.com/{subpath}", status=200, payload=success_response_data)

        result = await KRemoteAction.multi_try_rasa_request(
            endpoint_config=endpoint_config,
            method=method,
            subpath=subpath,
            retry_attempts=2
        )

        assert result == success_response_data

@pytest.mark.asyncio
async def test_multi_try_rasa_request_retry_fail():
    endpoint_config = EndpointConfig(url="http://test.com", headers={"Authorization": "Bearer token"})
    subpath = "path/to/resource"
    method = "post"
    success_response_data = {"key": "value"}

    with aioresponses() as mock:
        mock.post(f"http://test.com/{subpath}", status=500)
        mock.post(f"http://test.com/{subpath}", status=500)
        mock.post(f"http://test.com/{subpath}", status=500)
        mock.post(f"http://test.com/{subpath}", status=200, payload=success_response_data)

        with pytest.raises(ClientResponseError) as exc_info:
            result = await KRemoteAction.multi_try_rasa_request(
                endpoint_config=endpoint_config,
                method=method,
                subpath=subpath,
                retry_attempts=2
            )

        assert exc_info.value.status == 500


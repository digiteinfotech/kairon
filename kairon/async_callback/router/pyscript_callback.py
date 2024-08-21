from typing import Optional

from fastapi import APIRouter, Request

from loguru import logger
from kairon.api.models import Response
from kairon.async_callback.processor import CallbackProcessor
from kairon.exceptions import AppException

router = APIRouter()


async def process_router_message(token: str, identifier: Optional[str] = None, req_type: str = 'GET', request: Request = None):
    if not request:
        raise AppException("Request is not valid!")
    data = {
        'type': req_type,
        'body': None,
        'params': {},
    }
    if request.query_params:
        data['params'].update({key: request.query_params[key] for key in request.query_params})
    try:
        req_data = None
        try:
            req_data = await request.json()
            logger.info('Request Body type: json')
        except Exception as e:
            logger.info('Request Body type: text')
            req_data = await request.body()
            if req_data and len(req_data) > 0:
                req_data = req_data.decode('utf-8')
            else:
                req_data = None
        if req_data:
            data.update({"body": req_data})
        request_source = request.client.host
        logger.info(f"data from request: ${data}")
        data, message, error_code = await CallbackProcessor.process_async_callback_request(token,
                                                                                           identifier,
                                                                                           data,
                                                                                           request_source)

        return Response(message=message, data=data, error_code=error_code, success=error_code == 0)
    except AppException as ae:
        return Response(message=str(ae), error_code=400, success=False)
    except Exception as e:
        return Response(message=str(e), error_code=400, success=False)


@router.get('/callback/d/{identifier}/{token}', response_model=Response)
async def execute_async_action_get(identifier: str, token: str, request: Request):
    return await process_router_message(token, identifier, 'GET', request)


@router.post('/callback/d/{identifier}/{token}', response_model=Response)
async def execute_async_action_post(identifier: str, token: str, request: Request):
    return await process_router_message(token, identifier, 'POST', request)


@router.put('/callback/d/{identifier}/{token}', response_model=Response)
async def execute_async_action_put(identifier: str, token: str, request: Request):
    return await process_router_message(token, identifier, 'PUT', request)


@router.patch('/callback/d/{identifier}/{token}', response_model=Response)
async def execute_async_action_patch(identifier: str, token: str, request: Request):
    return await process_router_message(token, identifier, 'PATCH', request)


@router.delete('/callback/d/{identifier}/{token}', response_model=Response)
async def execute_async_action_delete(identifier: str, token: str, request: Request):
    return await process_router_message(token, identifier, 'DELETE', request)


@router.post('/callback/s/{token}', response_model=Response)
async def execute_async_action_standalone_post(token: str, request: Request):
    return await process_router_message(token, None, 'POST', request)


@router.put('/callback/s/{token}', response_model=Response)
async def execute_async_action_standalone_put(token: str, request: Request):
    return await process_router_message(token, None, 'POST', request)


@router.patch('/callback/s/{token}', response_model=Response)
async def execute_async_action_standalone_patch(token: str, request: Request):
    return await process_router_message(token, None, 'POST', request)

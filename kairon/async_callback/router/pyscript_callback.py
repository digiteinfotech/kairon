
from fastapi import APIRouter, Request

from loguru import logger
from kairon.api.models import Response
from kairon.async_callback.processor import CallbackProcessor
from kairon.exceptions import AppException

router = APIRouter()


async def process_router_message(bot: str, name: str, dynamic_param, req_type: str = 'GET', request: Request = None):
    if not request:
        raise AppException("Request is not valid!")
    data = {
        'type': req_type,
        'dynamic_param': dynamic_param,
        'data': None
    }
    if request.query_params:
        data.update({key: request.query_params[key] for key in request.query_params})
    token = data.get('token')
    try:
        req_data = None
        try:
            req_data = await request.json()
        except Exception as e:
            logger.exception(e)
            req_data = await request.body()
            req_data = req_data.decode('utf-8') if len(req_data) > 0 else None
        if req_data:
            data.update({"data": req_data})
            if isinstance(req_data, dict):
                data['type'] = 'dict'
            elif isinstance(req_data, list):
                data['type'] = 'list'
            elif isinstance(req_data, str):
                data['type'] = 'str'
        request_source = request.client.host
        data, message, error_code = await CallbackProcessor.process_async_callback_request(bot,
                                                                                           name,
                                                                                           dynamic_param,
                                                                                           token,
                                                                                           data,
                                                                                           request_source)

        return Response(message=message, data=data, error_code=error_code, success=error_code == 0)
    except AppException as ae:
        return Response(message=str(ae), error_code=400, success=False)
    except Exception as e:
        return Response(message=str(e), error_code=400, success=False)


@router.get('/callback/{bot}/{name}/{dynamic_param}', response_model=Response)
async def execute_async_action(bot: str, name: str, dynamic_param: str, request: Request):
    return await process_router_message(bot, name, dynamic_param, 'GET', request)


@router.post('/callback/{bot}/{name}/{dynamic_param}', response_model=Response)
async def execute_async_action_post(bot: str, name: str, dynamic_param: str, request: Request):
    return await process_router_message(bot, name, dynamic_param, 'POST', request)


@router.put('/callback/{bot}/{name}/{dynamic_param}', response_model=Response)
async def execute_async_action_put(bot: str, name: str, dynamic_param: str, request: Request):
    return await process_router_message(bot, name, dynamic_param, 'PUT', request)


@router.patch('/callback/{bot}/{name}/{dynamic_param}', response_model=Response)
async def execute_async_action_patch(bot: str, name: str, dynamic_param: str, request: Request):
    return await process_router_message(bot, name, dynamic_param, 'PATCH', request)


@router.delete('/callback/{bot}/{name}/{dynamic_param}', response_model=Response)
async def execute_async_action_delete(bot: str, name: str, dynamic_param: str, request: Request):
    return await process_router_message(bot, name, dynamic_param, 'DELETE', request)

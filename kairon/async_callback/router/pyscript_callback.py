from typing import Optional
from blacksheep import Router, Request, Response as BSResponse
from blacksheep.contents import JSONContent

from loguru import logger
from kairon.async_callback.processor import CallbackProcessor
from kairon.exceptions import AppException

router = Router()


async def process_router_message(token: str, identifier: Optional[str] = None, req_type: str = 'GET', request: Request = None) -> BSResponse:
    """Process the incoming request for the callback."""
    if not request:
        raise AppException("Request is not valid!")

    data = {
        'type': req_type,
        'body': None,
        'params': {},
    }

    if request.query:
        data['params'].update({key: request.query.get(key) for key in request.query.keys()})

    try:
        req_data = None

        try:
            req_data = await request.json()
            logger.info('Request Body type: json')
        except Exception as e:
            logger.info('Request Body type: text')
            req_data = await request.read()
            if req_data and len(req_data) > 0:
                req_data = req_data.decode('utf-8')
            else:
                req_data = None

        if req_data:
            data.update({"body": req_data})

        request_source = request.scope.get("client", ["unknown"])[0]
        logger.info(f"Request source IP: {request_source}")
        logger.info(f"Data from request: {data}")
        print(request_source)

        data, message, error_code = await CallbackProcessor.process_async_callback_request(
            token, identifier, data, request_source
        )
        # return Response(message=message, data=data, error_code=error_code, success=error_code == 0)

        return BSResponse(
            status=200,
            content=JSONContent({
                "message": message,
                "data": data,
                "error_code": error_code,
                "success": error_code == 0,
            })
        )
    except AppException as ae:
        logger.error(f"AppException: {ae}")
        # return Response(message=str(ae), error_code=400, success=False)
        return BSResponse(
            status=400,
            content=JSONContent({
                "message": str(ae),
                "error_code": 400,
                "data": None,
                "success": False,
            })
        )
    except Exception as e:
        logger.exception(e)
        # return Response(message=str(e), error_code=400, success=False)
        return BSResponse(
            status=500,
            content=JSONContent({
                "message": str(e),
                "error_code": 400,
                "data": None,
                "success": False
            })
        )


@router.get("/callback/d/{identifier}/{token}")
async def execute_async_action_get(request: Request, identifier: str, token: str) -> BSResponse:
    print(token, identifier)
    return await process_router_message(token, identifier, 'GET', request)


@router.post("/callback/d/{identifier}/{token}")
async def execute_async_action_post(request: Request, identifier: str, token: str) -> BSResponse:
    return await process_router_message(token, identifier, 'POST', request)


@router.put("/callback/d/{identifier}/{token}")
async def execute_async_action_put(request: Request, identifier: str, token: str) -> BSResponse:
    return await process_router_message(token, identifier, 'PUT', request)


@router.patch("/callback/d/{identifier}/{token}")
async def execute_async_action_patch(request: Request, identifier: str, token: str) -> BSResponse:
    return await process_router_message(token, identifier, 'PATCH', request)


@router.delete("/callback/d/{identifier}/{token}")
async def execute_async_action_delete(request: Request, identifier: str, token: str) -> BSResponse:
    return await process_router_message(token, identifier, 'DELETE', request)


@router.post("/callback/s/{token}")
async def execute_async_action_standalone_post(request: Request, token: str) -> BSResponse:
    return await process_router_message(token, None, 'POST', request)


@router.put("/callback/s/{token}")
async def execute_async_action_standalone_put(request: Request, token: str) -> BSResponse:
    return await process_router_message(token, None, 'PUT', request)


@router.patch("/callback/s/{token}")
async def execute_async_action_standalone_patch(request: Request, token: str) -> BSResponse:
    return await process_router_message(token, None, 'PATCH', request)

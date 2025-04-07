from typing import Optional
from blacksheep import Router, Request, Response as BSResponse, TextContent
from blacksheep.contents import JSONContent

from loguru import logger
from kairon.async_callback.processor import CallbackProcessor
from kairon.exceptions import AppException
from kairon.shared.callback.data_objects import CallbackResponseType

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

        data, message, error_code, response_type = await CallbackProcessor.process_async_callback_request(
            token, identifier, data, request_source
        )

        resp_status_code = 200 if error_code == 0 else 422
        if response_type == CallbackResponseType.KAIRON_JSON.value:
            return BSResponse(
                status=resp_status_code,
                content=JSONContent({
                    "message": message,
                    "data": data,
                    "error_code": error_code,
                    "success": error_code == 0,
                })
            )
        elif response_type == CallbackResponseType.JSON.value:
            return BSResponse(
                status=resp_status_code,
                content=JSONContent(data)
            )
        elif response_type == CallbackResponseType.TEXT.value:
            return BSResponse(
                status=resp_status_code,
                content=TextContent(str(data))
            )
    except AppException as ae:
        logger.error(f"AppException: {ae}")
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
        return BSResponse(
            status=500,
            content=JSONContent({
                "message": str(e),
                "error_code": 400,
                "data": None,
                "success": False
            })
        )


@router.route("/callback/d/{identifier}/{token}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def execute_async_action(request: Request, identifier: str, token: str) -> BSResponse:
    return await process_router_message(token, identifier, request.method, request)


@router.route("/callback/s/{token}", methods=["POST", "PUT", "PATCH"])
async def execute_async_action_standalone(request: Request, token: str) -> BSResponse:
    return await process_router_message(token, None, request.method, request)
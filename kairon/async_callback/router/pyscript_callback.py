from typing import Optional
from blacksheep import Router, Request, Response as BSResponse, json
from blacksheep.contents import JSONContent

from loguru import logger
from kairon.async_callback.processor import CallbackProcessor
from kairon.async_callback.utils import CallbackUtility
from kairon.exceptions import AppException
from kairon.shared.callback.data_objects import PyscriptPayload
from kairon.shared.callback.data_objects import CallbackRequest

router = Router()


async def process_router_message(token: str, identifier: Optional[str] = None, req_type: str = 'GET', request: Request = None) -> BSResponse:
    """Process the incoming request for the callback."""
    if not request:
        raise AppException("Request is not valid!")

    data = {
        'type': req_type,
        'body': None,
        'params': {},
        'headers': {}
    }

    if request.query:
        data['params'].update({key: request.query.get(key) for key in request.query.keys()})

    try:
        data['headers'] = {key.decode(): value.decode() for key, value in request.headers.items()}
    except Exception as e:
        logger.exception('could not parse headers')

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

        return CallbackUtility.return_response(data, message, error_code, response_type)
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

@router.post("/main_pyscript/execute-python")
async def trigger_restricted_python(payload: PyscriptPayload):
    try:
        result = CallbackUtility.main_pyscript_handler({
            "source_code": payload.source_code,
            "predefined_objects": payload.predefined_objects or {}
        }, None)
        return {"success": True, **result}
    except Exception as e:
        return json({"success": False, "error": str(e)}, status=422)

@router.post("/callback/handle_event")
async def handle_callback(body: CallbackRequest):
    try:
        payload = body.data
        source_code = payload.get("source_code")
        predefined_objects = payload.get("predefined_objects", {})
        result = CallbackUtility.execute_script(source_code, predefined_objects)
        return {
            "statusCode": 200,
            "body": result
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": str(e)
        }
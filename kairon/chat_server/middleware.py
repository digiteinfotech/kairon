from loguru import logger
from quart import request, g

from kairon.chat_server.exceptions import AuthenticationException, ChatServerException
from kairon.chat_server.processor import AuthenticationProcessor


async def authenticate_and_get_request(class_=None):
    logger.info('endpoint: %s, url: %s, path: %s' % (request.endpoint,
                                                     request.url,
                                                     request.path))
    req = await request.get_json()
    logger.info("request: ", req)
    logger.info("class_: ", class_)

    req_obj = req
    try:
        if class_:
            req_obj = class_(**req)
            req_obj.validate()
    except TypeError as e:
        logger.error(e)
        raise ChatServerException("Invalid request body!")

    auth_header = request.headers.get('Authorization')
    alias_user = request.headers.get("X-USER")
    if auth_header and len(auth_header.split(" ")) == 2:
        auth_token = auth_header.split(" ")[1]
    else:
        raise AuthenticationException("Could not validate credentials!")
    user_info = AuthenticationProcessor.validate_user_and_get_info(auth_token, alias_user)
    g.username = user_info['email']
    g.bot = user_info['bot']
    g.request = req_obj


async def authenticate_telegram_requests(auth_token):
    logger.info('endpoint: %s, url: %s, path: %s' % (request.endpoint,
                                                     request.url,
                                                     request.path))
    req = await request.get_json()
    logger.info("request: ", req)

    if auth_token and len(auth_token.split(" ")) == 2:
        auth_token = auth_token.split(" ")[1]
    else:
        raise AuthenticationException("Could not validate credentials!")
    user_info = AuthenticationProcessor.validate_user_and_get_info(auth_token)
    g.username = user_info['email']
    g.bot = user_info['bot']
    g.request = req

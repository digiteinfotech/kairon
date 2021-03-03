from mongoengine import connect, disconnect
from quart import Quart, g
from quart.exceptions import HTTPException

from kairon.chat_server.channels.channels import KaironChannels, ChannelFactory, ChannelClientDictionary
from kairon.chat_server.channels.telegram import KaironTelegramClient
from kairon.chat_server.chat_server_utils import ChatServerUtils
from kairon.chat_server.exceptions import ChatServerException
from kairon.chat_server.middleware import authenticate_and_get_request, authenticate_telegram_requests
from kairon.chat_server.models import ChatRequest, CreateClientRequest, ChatServerResponse
from kairon.chat_server.processor import KaironMessageProcessor, ChannelCredentialsProcessor

app = Quart(__name__)
clients = ChannelClientDictionary()


@app.before_serving
def initiate_app():
    ChatServerUtils.load_evironment()
    connect(host=ChatServerUtils.environment['database']["url"])


@app.after_serving
def finalize_app():
    disconnect()
    # atexit to close connection


@app.errorhandler(HTTPException)
def handle_error(error):
    app.logger.error(error)
    resp = ChatServerResponse(message=str(error), success=False).get_json()
    return resp, 422


@app.errorhandler(ChatServerException)
def handle_exception(error):
    app.logger.error(error)
    resp = ChatServerResponse(message=str(error), success=False).get_json()
    return resp, 422


@app.route("/")
async def ping():
    return "hello"


@app.route("/chat/channel", methods=["POST"])
async def add_channel():
    try:
        await authenticate_and_get_request(CreateClientRequest)
        clients.is_present(g.bot, g.request.channel, True)
        channel_client = ChannelFactory.create_client(g.request)
        ChannelCredentialsProcessor.add_credentials(g.bot, g.username, g.request.channel, g.request.credentials)
        clients.put(g.bot, g.request.channel, channel_client)
        response = ChatServerResponse(message="Credentials registered successfully").get_json()
        return response, 200
    except Exception as e:
        raise ChatServerException(e)


@app.route("/chat/channel", methods=["PUT"])
async def update_channel():
    try:
        await authenticate_and_get_request(CreateClientRequest)
        channel_client = ChannelFactory.create_client(g.request)
        ChannelCredentialsProcessor.update_credentials(g.bot, g.username, g.request.channel, g.request.credentials)
        clients.put(g.bot, g.request.channel, channel_client)
        response = ChatServerResponse(message="Credentials updated successfully").get_json()
        return response, 200
    except Exception as e:
        raise ChatServerException(e)


@app.route("/chat/channel/<channel>", methods=["GET"])
async def get_channel(channel):
    try:
        await authenticate_and_get_request()
        resp = ChannelCredentialsProcessor.get_credentials(g.bot, g.username, channel)
        response = ChatServerResponse(message="Credentials retrieved successfully", data=resp).get_json()
        return response, 200
    except Exception as e:
        raise ChatServerException(e)


@app.route("/chat/channel/all", methods=["GET"])
async def list_channels():
    try:
        await authenticate_and_get_request()
        resp = list(ChannelCredentialsProcessor.list_credentials(g.bot, g.username))
        response = ChatServerResponse(message="Credentials retrieved successfully", data=resp).get_json()
        return response, 200
    except Exception as e:
        raise ChatServerException(e)


@app.route("/chat/channel/<channel>", methods=["DELETE"])
async def delete_channel(channel):
    try:
        await authenticate_and_get_request()
        ChannelCredentialsProcessor.delete_credentials(g.bot, g.username, channel)
        clients.remove(g.bot, channel)
        response = ChatServerResponse(message="Credentials removed successfully").get_json()
        return response, 200
    except Exception as e:
        raise ChatServerException(e)


@app.route("/chat", methods=["POST"])
async def chat():
    try:
        await authenticate_and_get_request(ChatRequest)
        if not g.request or not g.request.text:
            raise ChatServerException("Invalid request body!")
        resp = await KaironMessageProcessor().process_text_message(g.bot, g.request.text, g.username)
        app.logger.info("done")
        resp = ChatServerResponse(message=resp).get_json()
        return resp, 200
    except Exception as e:
        raise ChatServerException(e)


@app.route("/telegram/<bot>/<auth_token>", methods=["POST"])
async def telegram(bot: str, auth_token: str):
    try:
        await authenticate_telegram_requests(auth_token)
        telegram_client: KaironTelegramClient = clients.get(bot, KaironChannels.TELEGRAM)
        telegram_client.handle_message(g.request)
        response = ChatServerResponse(message="Message sent Successfully").get_json()
        return response, 200
    except Exception as e:
        raise ChatServerException(e)


if __name__ == "__main__":
    app.run()

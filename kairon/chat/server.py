from tornado.ioloop import IOLoop
from tornado.web import Application
from tornado.options import parse_command_line

from kairon.chat.handlers.channels.whatsapp import WhatsappHandler
from kairon.chat.handlers.channels.msteams import MSTeamsHandler
from kairon.shared.tornado.handlers.index import IndexHandler
from .handlers.action import ChatHandler, ReloadHandler, LiveAgentHandler, SessionConversationHandler
from .handlers.channels.slack import SlackHandler
from .handlers.channels.telegram import TelegramHandler
from .handlers.channels.hangouts import HangoutHandler
from .handlers.channels.messenger import MessengerHandler, InstagramHandler
from ..shared.utils import Utility
from loguru import logger
from mongoengine import connect
Utility.load_environment()


def make_app():
    return Application([
        (r"/", IndexHandler),
        (r"/api/bot/([^/]+)/chat", ChatHandler),
        (r"/api/bot/([^/]+)/conversation", SessionConversationHandler),
        (r"/api/bot/([^/]+)/agent/live/([^/]+)", LiveAgentHandler),
        (r"/api/bot/slack/([^/]+)/([^/]+)", SlackHandler),
        (r"/api/bot/telegram/([^/]+)/([^/]+)", TelegramHandler),
        (r"/api/bot/hangouts/([^/]+)/([^/]+)", HangoutHandler),
        (r"/api/bot/messenger/([^/]+)/([^/]+)", MessengerHandler),
        (r"/api/bot/([^/]+)/reload", ReloadHandler),
        (r"/api/bot/instagram/([^/]+)/([^/]+)", InstagramHandler),
        (r"/api/bot/whatsapp/([^/]+)/([^/]+)", WhatsappHandler),
        (r"/api/bot/msteams/([^/]+)/([^/]+)", MSTeamsHandler),
    ], compress_response=True, debug=False)


if __name__ == "__main__":
    connect(**Utility.mongoengine_connection())
    app = make_app()
    Utility.initiate_tornado_apm_client(app)
    app.listen(5000)
    parse_command_line()
    logger.info("Server Started")
    IOLoop.current().start()

from tornado.ioloop import IOLoop
from tornado.web import Application
from tornado.options import parse_command_line

from kairon.events.handlers.event import EventHandler
from kairon.shared.tornado.handlers.index import IndexHandler
from ..shared.utils import Utility
from loguru import logger
from mongoengine import connect
Utility.load_environment()


def make_app():
    return Application([
        (r"/", IndexHandler),
        (r"/api/events/execute/([^/]+)", EventHandler)
    ], compress_response=True, debug=False)


if __name__ == "__main__":
    connect(**Utility.mongoengine_connection())
    app = make_app()
    Utility.initiate_tornado_apm_client(app)
    app.listen(5056)
    parse_command_line()
    logger.info("Server Started")
    IOLoop.current().start()

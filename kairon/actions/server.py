from tornado.ioloop import IOLoop
from tornado.web import Application
from tornado.options import parse_command_line
from .handlers.index import MainHandler
from .handlers.action import ActionHandler
from ..shared.actions.utils import ActionUtility
from loguru import logger

def make_app():
    return Application([
        (r"/", MainHandler),
        (r"/webhook", ActionHandler),
    ], compress_response=True)


if __name__ == "__main__":
    ActionUtility.connect_db()
    app = make_app()
    app.listen(5055)
    parse_command_line()
    logger.info("Server Started")
    IOLoop.current().start()
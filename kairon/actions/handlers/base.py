from tornado.web import RequestHandler


class BaseHandler(RequestHandler):

    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "x-requested-with")
        self.set_header('Access-Control-Allow-Methods', ' PUT, DELETE, OPTIONS')
        self.set_header("Content-Type", 'application/json')

    def options(self):
        # no body
        self.set_status(204)
        self.finish()
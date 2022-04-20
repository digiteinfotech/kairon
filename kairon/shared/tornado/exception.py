class ServiceHandlerException(Exception):

    def __init__(self, message, status_code=422, headers: dict = None):
        self.message = message
        self.status_code = status_code
        if not headers:
            headers = {}
        self.headers = headers
        super().__init__(message)

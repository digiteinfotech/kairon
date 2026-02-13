class CallbackException(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.error_message = message
        self.status_code = status_code

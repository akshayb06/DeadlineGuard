class AppError(Exception):
    """One error type for the whole backend. main.py turns it into a JSON response."""

    def __init__(self, status_code, message, extra=None):
        self.status_code = status_code
        self.message = message
        self.extra = extra or {}

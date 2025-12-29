class BaseException(Exception):
    """Base exception for all exceptions in the project."""
    pass

class DisallowedHostException(BaseException):
    """HTTP_HOST header contains invalid value."""

    def __init__(self, host: str) -> None:
        self.host = host
        self.message = f"Maybe '{host}' needs to be added in the allowed hosts?"
        super().__init__(self.message)

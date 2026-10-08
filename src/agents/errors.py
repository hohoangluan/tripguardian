"""Public tool failures preserve HTTP semantics without leaking module internals."""


class ToolError(ValueError):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)

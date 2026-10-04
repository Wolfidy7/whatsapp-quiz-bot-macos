"""Errors safe to display at the HTTP and operator boundaries."""


class QuizError(RuntimeError):
    """A classified incident, never an instruction to silently retry a send."""

    def __init__(self, code: str, message: str) -> None:
        """Initialize an operator-readable code and explanation."""
        super().__init__(message)
        self.code = code

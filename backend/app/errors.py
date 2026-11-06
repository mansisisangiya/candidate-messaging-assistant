"""Domain errors. Routes (a later step) map these to the API error envelope."""


class AppError(Exception):
    code = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class RecordNotFoundError(AppError):
    code = "not_found"


class ToolInputError(AppError):
    """The model supplied arguments that fail the tool's input schema."""

    code = "invalid_tool_input"


class UnknownToolError(AppError):
    code = "unknown_tool"


class ToolUnavailableError(AppError):
    """A tool's backing system is down. Reserved for the injected failure in a later step."""

    code = "tool_unavailable"


class FixtureError(AppError):
    """Fixture data is malformed or has dangling references."""

    code = "invalid_fixture"

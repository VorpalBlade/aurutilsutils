from prompt_toolkit.formatted_text import (
    AnyFormattedText,
    StyleAndTextTuples,
    to_formatted_text,
)


class FormattedException(Exception):
    def __pt_formatted_text__(self) -> StyleAndTextTuples:
        return [("", repr(self))]


class UserErrorMessage(FormattedException):
    """Error message to be formatted nicely to user with no backtrace shown"""

    def __init__(self, message: AnyFormattedText, *args):
        self.message = message
        super().__init__(*args)

    def __pt_formatted_text__(self) -> StyleAndTextTuples:
        return to_formatted_text(self.message)


class InternalError(FormattedException):
    """Unexpected error, formatted nicely but include a backtrace"""

    def __init__(self, message: AnyFormattedText, *args):
        self.message = message
        super().__init__(*args)

    def __pt_formatted_text__(self) -> StyleAndTextTuples:
        return to_formatted_text(self.message)


class CommandException(FormattedException):
    """Error for a command execution failing"""

    def __init__(self, cmd, ret_code, stderr, *args):
        super().__init__(*args)
        self.cmd = cmd
        self.ret_code = ret_code
        self.stderr = stderr

    def __str__(self):
        return f"Unexpected return code {self.ret_code} when running {self.cmd}, stderr: {self.stderr}"

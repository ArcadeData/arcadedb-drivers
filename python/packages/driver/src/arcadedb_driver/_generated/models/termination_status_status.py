from enum import Enum


class TerminationStatusStatus(str, Enum):
    COMPLETED = "completed"
    NOT_FOUND = "not found"
    TERMINATED = "terminated"
    TERMINATING = "terminating"

    def __str__(self) -> str:
        return str(self.value)

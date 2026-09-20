from enum import Enum


class ClusterAuthSessionRequestAction(str, Enum):
    REVOKE = "revoke"
    VALIDATE = "validate"

    def __str__(self) -> str:
        return str(self.value)

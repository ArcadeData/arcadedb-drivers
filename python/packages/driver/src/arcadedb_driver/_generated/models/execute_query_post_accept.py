from enum import Enum


class ExecuteQueryPostAccept(str, Enum):
    APPLICATIONJSON = "application/json"
    APPLICATIONX_NDJSON = "application/x-ndjson"

    def __str__(self) -> str:
        return str(self.value)

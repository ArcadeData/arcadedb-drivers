from enum import Enum


class ExecuteQueryGetAccept(str, Enum):
    APPLICATIONJSON = "application/json"
    APPLICATIONX_NDJSON = "application/x-ndjson"

    def __str__(self) -> str:
        return str(self.value)

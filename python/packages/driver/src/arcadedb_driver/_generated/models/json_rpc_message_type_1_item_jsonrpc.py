from enum import Enum


class JsonRpcMessageType1ItemJsonrpc(str, Enum):
    VALUE_0 = "2.0"

    def __str__(self) -> str:
        return str(self.value)

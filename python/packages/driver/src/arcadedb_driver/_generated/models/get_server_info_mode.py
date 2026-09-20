from enum import Enum


class GetServerInfoMode(str, Enum):
    BASIC = "basic"
    CLUSTER = "cluster"
    DEFAULT = "default"

    def __str__(self) -> str:
        return str(self.value)

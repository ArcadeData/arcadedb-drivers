from enum import Enum


class BatchEdgeLineType(str, Enum):
    E = "e"
    EDGE = "edge"

    def __str__(self) -> str:
        return str(self.value)

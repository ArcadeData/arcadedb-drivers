from enum import Enum


class BatchVertexLineType(str, Enum):
    V = "v"
    VERTEX = "vertex"

    def __str__(self) -> str:
        return str(self.value)

from enum import Enum


class FacetResultSource(str, Enum):
    INDEX = "index"
    SCAN = "scan"
    UNAVAILABLE = "unavailable"

    def __str__(self) -> str:
        return str(self.value)

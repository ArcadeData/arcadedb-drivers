from enum import Enum


class HybridSearchRequestFusionStrategy(str, Enum):
    DBSF = "DBSF"
    LINEAR = "LINEAR"
    RRF = "RRF"

    def __str__(self) -> str:
        return str(self.value)

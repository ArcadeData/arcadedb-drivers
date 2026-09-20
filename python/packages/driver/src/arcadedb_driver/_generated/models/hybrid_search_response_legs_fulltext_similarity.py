from enum import Enum


class HybridSearchResponseLegsFulltextSimilarity(str, Enum):
    BM25 = "BM25"
    CLASSIC = "CLASSIC"

    def __str__(self) -> str:
        return str(self.value)

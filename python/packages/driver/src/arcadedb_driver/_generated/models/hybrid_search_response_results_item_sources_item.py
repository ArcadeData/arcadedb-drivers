from enum import Enum


class HybridSearchResponseResultsItemSourcesItem(str, Enum):
    EXPAND = "expand"
    FULLTEXT = "fulltext"
    VECTOR = "vector"

    def __str__(self) -> str:
        return str(self.value)

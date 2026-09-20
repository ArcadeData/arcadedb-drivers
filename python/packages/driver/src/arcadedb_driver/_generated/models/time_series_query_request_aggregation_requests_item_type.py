from enum import Enum


class TimeSeriesQueryRequestAggregationRequestsItemType(str, Enum):
    AVG = "AVG"
    COUNT = "COUNT"
    MAX = "MAX"
    MIN = "MIN"
    SUM = "SUM"

    def __str__(self) -> str:
        return str(self.value)

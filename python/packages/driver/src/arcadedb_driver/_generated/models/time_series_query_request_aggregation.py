from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.time_series_query_request_aggregation_requests_item import (
        TimeSeriesQueryRequestAggregationRequestsItem,
    )


T = TypeVar("T", bound="TimeSeriesQueryRequestAggregation")


@_attrs_define
class TimeSeriesQueryRequestAggregation:
    """Bucketed aggregation. Present only when the caller wants buckets rather than raw rows.

    Attributes:
        bucket_interval (int): Bucket width in the same unit as the timestamps. Required, and must be a positive WHOLE
            number: a value of zero or less is refused with 400 rather than read as a single bucket over the whole range,
            and one with a fractional part is refused rather than truncated, because a bucket width is exactly the sort of
            value a client computes by division.
        requests (list[TimeSeriesQueryRequestAggregationRequestsItem]): Aggregations to compute. Must name at least one;
            an empty array is refused with 400.
        bucket_origin (int | Unset): Where the bucket grid starts, in epoch milliseconds. Buckets are multiples of
            'bucketInterval' counted from this instant. Optional; the default is the Unix epoch, which was a Thursday at
            00:00 UTC, so a one-week bucket starts on a Thursday and a one-day bucket at 00:00 UTC. A Monday origin gives
            Monday weeks and a local-midnight origin gives local days.
    """

    bucket_interval: int
    requests: list[TimeSeriesQueryRequestAggregationRequestsItem]
    bucket_origin: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        bucket_interval = self.bucket_interval

        requests = []
        for requests_item_data in self.requests:
            requests_item = requests_item_data.to_dict()
            requests.append(requests_item)

        bucket_origin = self.bucket_origin

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "bucketInterval": bucket_interval,
                "requests": requests,
            }
        )
        if bucket_origin is not UNSET:
            field_dict["bucketOrigin"] = bucket_origin

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.time_series_query_request_aggregation_requests_item import (
            TimeSeriesQueryRequestAggregationRequestsItem,
        )

        d = dict(src_dict)
        bucket_interval = d.pop("bucketInterval")

        requests = []
        _requests = d.pop("requests")
        for requests_item_data in _requests:
            requests_item = TimeSeriesQueryRequestAggregationRequestsItem.from_dict(requests_item_data)

            requests.append(requests_item)

        bucket_origin = d.pop("bucketOrigin", UNSET)

        time_series_query_request_aggregation = cls(
            bucket_interval=bucket_interval,
            requests=requests,
            bucket_origin=bucket_origin,
        )

        time_series_query_request_aggregation.additional_properties = d
        return time_series_query_request_aggregation

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties

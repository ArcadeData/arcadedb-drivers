from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.time_series_aggregated_response_buckets_item import TimeSeriesAggregatedResponseBucketsItem


T = TypeVar("T", bound="TimeSeriesAggregatedResponse")


@_attrs_define
class TimeSeriesAggregatedResponse:
    """Aggregated samples

    Attributes:
        aggregations (list[str]): Aliases of the computed aggregations, in bucket value order
        buckets (list[TimeSeriesAggregatedResponseBucketsItem]): Buckets, ordered by timestamp
        count (int): Number of buckets returned
        type_ (str): Time-series type name
    """

    aggregations: list[str]
    buckets: list[TimeSeriesAggregatedResponseBucketsItem]
    count: int
    type_: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        aggregations = self.aggregations

        buckets = []
        for buckets_item_data in self.buckets:
            buckets_item = buckets_item_data.to_dict()
            buckets.append(buckets_item)

        count = self.count

        type_ = self.type_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "aggregations": aggregations,
                "buckets": buckets,
                "count": count,
                "type": type_,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.time_series_aggregated_response_buckets_item import TimeSeriesAggregatedResponseBucketsItem

        d = dict(src_dict)
        aggregations = cast(list[str], d.pop("aggregations"))

        buckets = []
        _buckets = d.pop("buckets")
        for buckets_item_data in _buckets:
            buckets_item = TimeSeriesAggregatedResponseBucketsItem.from_dict(buckets_item_data)

            buckets.append(buckets_item)

        count = d.pop("count")

        type_ = d.pop("type")

        time_series_aggregated_response = cls(
            aggregations=aggregations,
            buckets=buckets,
            count=count,
            type_=type_,
        )

        time_series_aggregated_response.additional_properties = d
        return time_series_aggregated_response

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

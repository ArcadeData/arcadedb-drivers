from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="TimeSeriesAggregatedResponseBucketsItem")


@_attrs_define
class TimeSeriesAggregatedResponseBucketsItem:
    """One aggregation bucket

    Attributes:
        timestamp (int): Bucket start timestamp
        values (list[Any]): Aggregated values, positionally aligned with 'aggregations'
    """

    timestamp: int
    values: list[Any]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        timestamp = self.timestamp

        values = self.values

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "timestamp": timestamp,
                "values": values,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        timestamp = d.pop("timestamp")

        values = cast(list[Any], d.pop("values"))

        time_series_aggregated_response_buckets_item = cls(
            timestamp=timestamp,
            values=values,
        )

        time_series_aggregated_response_buckets_item.additional_properties = d
        return time_series_aggregated_response_buckets_item

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

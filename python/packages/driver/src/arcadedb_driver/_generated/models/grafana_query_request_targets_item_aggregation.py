from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.grafana_query_request_targets_item_aggregation_requests_item import (
        GrafanaQueryRequestTargetsItemAggregationRequestsItem,
    )


T = TypeVar("T", bound="GrafanaQueryRequestTargetsItemAggregation")


@_attrs_define
class GrafanaQueryRequestTargetsItemAggregation:
    """Bucketed aggregation. Omit for raw samples.

    Attributes:
        requests (list[GrafanaQueryRequestTargetsItemAggregationRequestsItem]): Aggregations to compute. Must name at
            least one; an empty array is refused with an error frame.
        bucket_interval (int | Unset): Bucket width in the same unit as the timestamps. Derived from 'maxDataPoints' and
            the time range when omitted. When stated it must be positive: a value of zero or less is refused with an error
            frame for this target rather than replaced by a derived interval.
    """

    requests: list[GrafanaQueryRequestTargetsItemAggregationRequestsItem]
    bucket_interval: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        requests = []
        for requests_item_data in self.requests:
            requests_item = requests_item_data.to_dict()
            requests.append(requests_item)

        bucket_interval = self.bucket_interval

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "requests": requests,
            }
        )
        if bucket_interval is not UNSET:
            field_dict["bucketInterval"] = bucket_interval

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.grafana_query_request_targets_item_aggregation_requests_item import (
            GrafanaQueryRequestTargetsItemAggregationRequestsItem,
        )

        d = dict(src_dict)
        requests = []
        _requests = d.pop("requests")
        for requests_item_data in _requests:
            requests_item = GrafanaQueryRequestTargetsItemAggregationRequestsItem.from_dict(requests_item_data)

            requests.append(requests_item)

        bucket_interval = d.pop("bucketInterval", UNSET)

        grafana_query_request_targets_item_aggregation = cls(
            requests=requests,
            bucket_interval=bucket_interval,
        )

        grafana_query_request_targets_item_aggregation.additional_properties = d
        return grafana_query_request_targets_item_aggregation

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

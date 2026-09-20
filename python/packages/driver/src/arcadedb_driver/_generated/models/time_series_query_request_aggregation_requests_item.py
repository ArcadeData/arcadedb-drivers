from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.time_series_query_request_aggregation_requests_item_type import (
    TimeSeriesQueryRequestAggregationRequestsItemType,
)
from ..types import UNSET, Unset

T = TypeVar("T", bound="TimeSeriesQueryRequestAggregationRequestsItem")


@_attrs_define
class TimeSeriesQueryRequestAggregationRequestsItem:
    """One aggregation to compute over a bucket

    Attributes:
        field (str): Field name to aggregate
        type_ (TimeSeriesQueryRequestAggregationRequestsItemType): Aggregation function, matched case-insensitively. The
            same vocabulary the Grafana query endpoint accepts, because both resolve it through the same parser.
        alias (str | Unset): Output name. Defaults to the field name suffixed with the lower-cased aggregation type.
    """

    field: str
    type_: TimeSeriesQueryRequestAggregationRequestsItemType
    alias: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        field = self.field

        type_ = self.type_.value

        alias = self.alias

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "field": field,
                "type": type_,
            }
        )
        if alias is not UNSET:
            field_dict["alias"] = alias

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        field = d.pop("field")

        type_ = TimeSeriesQueryRequestAggregationRequestsItemType(d.pop("type"))

        alias = d.pop("alias", UNSET)

        time_series_query_request_aggregation_requests_item = cls(
            field=field,
            type_=type_,
            alias=alias,
        )

        time_series_query_request_aggregation_requests_item.additional_properties = d
        return time_series_query_request_aggregation_requests_item

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

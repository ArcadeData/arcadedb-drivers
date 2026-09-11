from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="GrafanaQueryRequestTargetsItemAggregationRequestsItem")


@_attrs_define
class GrafanaQueryRequestTargetsItemAggregationRequestsItem:
    """One aggregation to compute

    Attributes:
        alias (str | Unset): Output field name. Defaults to the field name suffixed with the lower-cased aggregation
            type.
        field (str | Unset): Field name to aggregate
        type_ (str | Unset): Aggregation function. Required, one of SUM, AVG, MIN, MAX, COUNT, matched case-
            insensitively. A value that matches none is reported as an error frame on this target, leaving the other targets
            served.
    """

    alias: str | Unset = UNSET
    field: str | Unset = UNSET
    type_: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        alias = self.alias

        field = self.field

        type_ = self.type_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if alias is not UNSET:
            field_dict["alias"] = alias
        if field is not UNSET:
            field_dict["field"] = field
        if type_ is not UNSET:
            field_dict["type"] = type_

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        alias = d.pop("alias", UNSET)

        field = d.pop("field", UNSET)

        type_ = d.pop("type", UNSET)

        grafana_query_request_targets_item_aggregation_requests_item = cls(
            alias=alias,
            field=field,
            type_=type_,
        )

        grafana_query_request_targets_item_aggregation_requests_item.additional_properties = d
        return grafana_query_request_targets_item_aggregation_requests_item

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

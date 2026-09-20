from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="GrafanaQueryResponseResultsAdditionalPropertyFramesItemData")


@_attrs_define
class GrafanaQueryResponseResultsAdditionalPropertyFramesItemData:
    """Frame data

    Attributes:
        values (list[list[Any]]): Column-major values, one array per field
    """

    values: list[list[Any]]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        values = []
        for values_item_data in self.values:
            values_item = values_item_data

            values.append(values_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "values": values,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        values = []
        _values = d.pop("values")
        for values_item_data in _values:
            values_item = cast(list[Any], values_item_data)

            values.append(values_item)

        grafana_query_response_results_additional_property_frames_item_data = cls(
            values=values,
        )

        grafana_query_response_results_additional_property_frames_item_data.additional_properties = d
        return grafana_query_response_results_additional_property_frames_item_data

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

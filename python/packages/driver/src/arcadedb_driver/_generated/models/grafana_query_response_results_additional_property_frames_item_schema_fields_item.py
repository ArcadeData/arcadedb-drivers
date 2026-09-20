from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="GrafanaQueryResponseResultsAdditionalPropertyFramesItemSchemaFieldsItem")


@_attrs_define
class GrafanaQueryResponseResultsAdditionalPropertyFramesItemSchemaFieldsItem:
    """One frame field

    Attributes:
        name (str): Field name, 'time' for the time column
        type_ (str): Grafana field type, for example time or number
    """

    name: str
    type_: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        type_ = self.type_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "type": type_,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        type_ = d.pop("type")

        grafana_query_response_results_additional_property_frames_item_schema_fields_item = cls(
            name=name,
            type_=type_,
        )

        grafana_query_response_results_additional_property_frames_item_schema_fields_item.additional_properties = d
        return grafana_query_response_results_additional_property_frames_item_schema_fields_item

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

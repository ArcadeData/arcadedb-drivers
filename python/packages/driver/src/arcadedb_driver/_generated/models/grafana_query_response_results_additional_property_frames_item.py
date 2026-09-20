from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.grafana_query_response_results_additional_property_frames_item_data import (
        GrafanaQueryResponseResultsAdditionalPropertyFramesItemData,
    )
    from ..models.grafana_query_response_results_additional_property_frames_item_schema import (
        GrafanaQueryResponseResultsAdditionalPropertyFramesItemSchema,
    )


T = TypeVar("T", bound="GrafanaQueryResponseResultsAdditionalPropertyFramesItem")


@_attrs_define
class GrafanaQueryResponseResultsAdditionalPropertyFramesItem:
    """One DataFrame

    Attributes:
        data (GrafanaQueryResponseResultsAdditionalPropertyFramesItemData): Frame data
        schema (GrafanaQueryResponseResultsAdditionalPropertyFramesItemSchema): Frame schema
    """

    data: GrafanaQueryResponseResultsAdditionalPropertyFramesItemData
    schema: GrafanaQueryResponseResultsAdditionalPropertyFramesItemSchema
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = self.data.to_dict()

        schema = self.schema.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "data": data,
                "schema": schema,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.grafana_query_response_results_additional_property_frames_item_data import (
            GrafanaQueryResponseResultsAdditionalPropertyFramesItemData,
        )
        from ..models.grafana_query_response_results_additional_property_frames_item_schema import (
            GrafanaQueryResponseResultsAdditionalPropertyFramesItemSchema,
        )

        d = dict(src_dict)
        data = GrafanaQueryResponseResultsAdditionalPropertyFramesItemData.from_dict(d.pop("data"))

        schema = GrafanaQueryResponseResultsAdditionalPropertyFramesItemSchema.from_dict(d.pop("schema"))

        grafana_query_response_results_additional_property_frames_item = cls(
            data=data,
            schema=schema,
        )

        grafana_query_response_results_additional_property_frames_item.additional_properties = d
        return grafana_query_response_results_additional_property_frames_item

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

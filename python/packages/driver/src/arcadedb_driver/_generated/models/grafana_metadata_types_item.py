from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.grafana_metadata_types_item_fields_item import GrafanaMetadataTypesItemFieldsItem
    from ..models.grafana_metadata_types_item_tags_item import GrafanaMetadataTypesItemTagsItem


T = TypeVar("T", bound="GrafanaMetadataTypesItem")


@_attrs_define
class GrafanaMetadataTypesItem:
    """One queryable time-series type

    Attributes:
        fields (list[GrafanaMetadataTypesItemFieldsItem]): Value columns
        name (str): Type name
        tags (list[GrafanaMetadataTypesItemTagsItem]): Tag columns available as filters
    """

    fields: list[GrafanaMetadataTypesItemFieldsItem]
    name: str
    tags: list[GrafanaMetadataTypesItemTagsItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        fields = []
        for fields_item_data in self.fields:
            fields_item = fields_item_data.to_dict()
            fields.append(fields_item)

        name = self.name

        tags = []
        for tags_item_data in self.tags:
            tags_item = tags_item_data.to_dict()
            tags.append(tags_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "fields": fields,
                "name": name,
                "tags": tags,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.grafana_metadata_types_item_fields_item import GrafanaMetadataTypesItemFieldsItem
        from ..models.grafana_metadata_types_item_tags_item import GrafanaMetadataTypesItemTagsItem

        d = dict(src_dict)
        fields = []
        _fields = d.pop("fields")
        for fields_item_data in _fields:
            fields_item = GrafanaMetadataTypesItemFieldsItem.from_dict(fields_item_data)

            fields.append(fields_item)

        name = d.pop("name")

        tags = []
        _tags = d.pop("tags")
        for tags_item_data in _tags:
            tags_item = GrafanaMetadataTypesItemTagsItem.from_dict(tags_item_data)

            tags.append(tags_item)

        grafana_metadata_types_item = cls(
            fields=fields,
            name=name,
            tags=tags,
        )

        grafana_metadata_types_item.additional_properties = d
        return grafana_metadata_types_item

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

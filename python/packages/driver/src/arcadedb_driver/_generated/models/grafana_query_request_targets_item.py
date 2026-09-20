from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.grafana_query_request_targets_item_aggregation import GrafanaQueryRequestTargetsItemAggregation
    from ..models.grafana_query_request_targets_item_tags import GrafanaQueryRequestTargetsItemTags


T = TypeVar("T", bound="GrafanaQueryRequestTargetsItem")


@_attrs_define
class GrafanaQueryRequestTargetsItem:
    """One panel query

    Attributes:
        type_ (str): Time-series type name
        aggregation (GrafanaQueryRequestTargetsItemAggregation | Unset): Bucketed aggregation. Omit for raw samples.
        fields (list[str] | Unset): Fields to project on a raw (non-aggregated) query. All fields when omitted. Ignored
            when 'aggregation' is present. A name that is no column of the type is refused with an error frame for this
            target rather than ignored.
        ref_id (str | Unset): Identifier echoed back as the result key. Defaults to 'A'.
        tags (GrafanaQueryRequestTargetsItemTags | Unset): Tag filter as name to value pairs. All pairs must match
    """

    type_: str
    aggregation: GrafanaQueryRequestTargetsItemAggregation | Unset = UNSET
    fields: list[str] | Unset = UNSET
    ref_id: str | Unset = UNSET
    tags: GrafanaQueryRequestTargetsItemTags | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        aggregation: dict[str, Any] | Unset = UNSET
        if not isinstance(self.aggregation, Unset):
            aggregation = self.aggregation.to_dict()

        fields: list[str] | Unset = UNSET
        if not isinstance(self.fields, Unset):
            fields = self.fields

        ref_id = self.ref_id

        tags: dict[str, Any] | Unset = UNSET
        if not isinstance(self.tags, Unset):
            tags = self.tags.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "type": type_,
            }
        )
        if aggregation is not UNSET:
            field_dict["aggregation"] = aggregation
        if fields is not UNSET:
            field_dict["fields"] = fields
        if ref_id is not UNSET:
            field_dict["refId"] = ref_id
        if tags is not UNSET:
            field_dict["tags"] = tags

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.grafana_query_request_targets_item_aggregation import GrafanaQueryRequestTargetsItemAggregation
        from ..models.grafana_query_request_targets_item_tags import GrafanaQueryRequestTargetsItemTags

        d = dict(src_dict)
        type_ = d.pop("type")

        _aggregation = d.pop("aggregation", UNSET)
        aggregation: GrafanaQueryRequestTargetsItemAggregation | Unset
        if isinstance(_aggregation, Unset):
            aggregation = UNSET
        else:
            aggregation = GrafanaQueryRequestTargetsItemAggregation.from_dict(_aggregation)

        fields = cast(list[str], d.pop("fields", UNSET))

        ref_id = d.pop("refId", UNSET)

        _tags = d.pop("tags", UNSET)
        tags: GrafanaQueryRequestTargetsItemTags | Unset
        if isinstance(_tags, Unset):
            tags = UNSET
        else:
            tags = GrafanaQueryRequestTargetsItemTags.from_dict(_tags)

        grafana_query_request_targets_item = cls(
            type_=type_,
            aggregation=aggregation,
            fields=fields,
            ref_id=ref_id,
            tags=tags,
        )

        grafana_query_request_targets_item.additional_properties = d
        return grafana_query_request_targets_item

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

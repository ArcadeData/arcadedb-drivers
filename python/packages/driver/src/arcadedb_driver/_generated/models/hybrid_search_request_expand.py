from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="HybridSearchRequestExpand")


@_attrs_define
class HybridSearchRequestExpand:
    """Optional graph expansion leg, seeded from the union of the retrieval legs and ranked by breadth-first discovery
    order.

        Attributes:
            direction (str | Unset): out, in, or both
            edge_types (list[str] | Unset): Edge types to walk
            max_depth (int | Unset): Hops to walk from a seed Default: 1.
    """

    direction: str | Unset = UNSET
    edge_types: list[str] | Unset = UNSET
    max_depth: int | Unset = 1
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        direction = self.direction

        edge_types: list[str] | Unset = UNSET
        if not isinstance(self.edge_types, Unset):
            edge_types = self.edge_types

        max_depth = self.max_depth

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if direction is not UNSET:
            field_dict["direction"] = direction
        if edge_types is not UNSET:
            field_dict["edgeTypes"] = edge_types
        if max_depth is not UNSET:
            field_dict["maxDepth"] = max_depth

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        direction = d.pop("direction", UNSET)

        edge_types = cast(list[str], d.pop("edgeTypes", UNSET))

        max_depth = d.pop("maxDepth", UNSET)

        hybrid_search_request_expand = cls(
            direction=direction,
            edge_types=edge_types,
            max_depth=max_depth,
        )

        hybrid_search_request_expand.additional_properties = d
        return hybrid_search_request_expand

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

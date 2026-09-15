from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="HybridSearchResponseLegsExpand")


@_attrs_define
class HybridSearchResponseLegsExpand:
    """The graph expansion leg, present whenever the request carried 'expand'

    Attributes:
        count (int): Rows the expansion leg contributed to fusion
        direction (str): Direction walked: out, in or both
        edge_types (list[str]): Edge types walked; empty when the request named none, which walks them all
        max_depth (int): Hops walked from a seed
        seed_count (int): Seeds the retrieval legs supplied
        seeds_truncated (bool): True when the seed budget capped the seed list, so a thin neighborhood is the cap's
            doing rather than the graph's.
        truncated (bool): True when the expansion hit its fan-out cap
    """

    count: int
    direction: str
    edge_types: list[str]
    max_depth: int
    seed_count: int
    seeds_truncated: bool
    truncated: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        count = self.count

        direction = self.direction

        edge_types = self.edge_types

        max_depth = self.max_depth

        seed_count = self.seed_count

        seeds_truncated = self.seeds_truncated

        truncated = self.truncated

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "count": count,
                "direction": direction,
                "edgeTypes": edge_types,
                "maxDepth": max_depth,
                "seedCount": seed_count,
                "seedsTruncated": seeds_truncated,
                "truncated": truncated,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        count = d.pop("count")

        direction = d.pop("direction")

        edge_types = cast(list[str], d.pop("edgeTypes"))

        max_depth = d.pop("maxDepth")

        seed_count = d.pop("seedCount")

        seeds_truncated = d.pop("seedsTruncated")

        truncated = d.pop("truncated")

        hybrid_search_response_legs_expand = cls(
            count=count,
            direction=direction,
            edge_types=edge_types,
            max_depth=max_depth,
            seed_count=seed_count,
            seeds_truncated=seeds_truncated,
            truncated=truncated,
        )

        hybrid_search_response_legs_expand.additional_properties = d
        return hybrid_search_response_legs_expand

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

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="FacetBucket")


@_attrs_define
class FacetBucket:
    """One bucket of a facet. A term bucket carries 'value'; a range or histogram bucket carries 'key' and its bounds; the
    bucket of the records without a value carries 'value' null and 'missing' true. Open: a facet kind may add attributes
    of its own (a hierarchy bucket carries 'parent', 'depth' and 'orphan').

        Attributes:
            count (int): Number of matching records in the bucket
            default (bool | Unset): True on the bucket of the values that fall in no range
            depth (int | Unset): Hierarchy facets: the shortest distance from a root, 0 for a root and for an orphan, -1 for
                a node no root reaches (it lies on or under a cycle of the hierarchy)
            from_ (Any | Unset): Inclusive lower bound of a range or histogram bucket; absent when unbounded
            key (str | Unset): Label of a range or histogram bucket
            missing (bool | Unset): True on the bucket of the records without a value
            orphan (bool | Unset): Hierarchy facets: true on a value that has no vertex in the hierarchy; it is counted as
                its own root bucket. Absent otherwise
            parent (Any | Unset): Hierarchy facets: the key of the node's first parent (parents ordered by key), null for a
                root and for an orphan
            to (Any | Unset): Exclusive upper bound of a range or histogram bucket; absent when unbounded
            value (Any | Unset): The term, written as a row's value of the faceted property is (a date in the database's
                date format, a date-time in its date-time format, a non-finite number by its name); null for the missing bucket
    """

    count: int
    default: bool | Unset = UNSET
    depth: int | Unset = UNSET
    from_: Any | Unset = UNSET
    key: str | Unset = UNSET
    missing: bool | Unset = UNSET
    orphan: bool | Unset = UNSET
    parent: Any | Unset = UNSET
    to: Any | Unset = UNSET
    value: Any | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        count = self.count

        default = self.default

        depth = self.depth

        from_ = self.from_

        key = self.key

        missing = self.missing

        orphan = self.orphan

        parent = self.parent

        to = self.to

        value = self.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "count": count,
            }
        )
        if default is not UNSET:
            field_dict["default"] = default
        if depth is not UNSET:
            field_dict["depth"] = depth
        if from_ is not UNSET:
            field_dict["from"] = from_
        if key is not UNSET:
            field_dict["key"] = key
        if missing is not UNSET:
            field_dict["missing"] = missing
        if orphan is not UNSET:
            field_dict["orphan"] = orphan
        if parent is not UNSET:
            field_dict["parent"] = parent
        if to is not UNSET:
            field_dict["to"] = to
        if value is not UNSET:
            field_dict["value"] = value

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        count = d.pop("count")

        default = d.pop("default", UNSET)

        depth = d.pop("depth", UNSET)

        from_ = d.pop("from", UNSET)

        key = d.pop("key", UNSET)

        missing = d.pop("missing", UNSET)

        orphan = d.pop("orphan", UNSET)

        parent = d.pop("parent", UNSET)

        to = d.pop("to", UNSET)

        value = d.pop("value", UNSET)

        facet_bucket = cls(
            count=count,
            default=default,
            depth=depth,
            from_=from_,
            key=key,
            missing=missing,
            orphan=orphan,
            parent=parent,
            to=to,
            value=value,
        )

        facet_bucket.additional_properties = d
        return facet_bucket

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

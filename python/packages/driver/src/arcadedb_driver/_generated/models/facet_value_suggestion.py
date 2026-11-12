from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="FacetValueSuggestion")


@_attrs_define
class FacetValueSuggestion:
    """A row of SELECT expand(facet.searchValues(type, property, prefix, limit)): a value of a COLUMNAR dictionary property
    that starts with the prefix (case-sensitive, in value order) and the number of documents of the type carrying it
    now. Values come only from the applied dictionaries of indexed buckets: a value held only by a type without the
    COLUMNAR index, or only by the caller's own uncommitted writes, is not suggested. A value no live document carries
    any more is not returned.

        Attributes:
            count (int): Number of documents of the type carrying the value, as a facet counts it
            value (str): The suggested value
            exact (bool | Unset): Present, and false, only when the count of the batch the value came from may lag the
                committed data (the patch budget was exceeded); absent when the count is exact
    """

    count: int
    value: str
    exact: bool | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        count = self.count

        value = self.value

        exact = self.exact

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "count": count,
                "value": value,
            }
        )
        if exact is not UNSET:
            field_dict["exact"] = exact

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        count = d.pop("count")

        value = d.pop("value")

        exact = d.pop("exact", UNSET)

        facet_value_suggestion = cls(
            count=count,
            value=value,
            exact=exact,
        )

        facet_value_suggestion.additional_properties = d
        return facet_value_suggestion

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

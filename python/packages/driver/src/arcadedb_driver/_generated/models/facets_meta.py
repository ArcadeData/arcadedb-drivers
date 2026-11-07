from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="FacetsMeta")


@_attrs_define
class FacetsMeta:
    """How exact the facets of this response are

    Attributes:
        exact (bool): False when the counts may lag the committed data because the patch budget was exceeded, or when a
            DISTINCT facet is approximate. True when every count is exact.
        lag_ms (int): How many milliseconds the columnar projection was behind the committed data
        patched (int): Number of records read from the record itself to correct the columnar projection
    """

    exact: bool
    lag_ms: int
    patched: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        exact = self.exact

        lag_ms = self.lag_ms

        patched = self.patched

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "exact": exact,
                "lagMs": lag_ms,
                "patched": patched,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        exact = d.pop("exact")

        lag_ms = d.pop("lagMs")

        patched = d.pop("patched")

        facets_meta = cls(
            exact=exact,
            lag_ms=lag_ms,
            patched=patched,
        )

        facets_meta.additional_properties = d
        return facets_meta

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

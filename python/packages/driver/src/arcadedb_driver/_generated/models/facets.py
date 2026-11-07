from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.facet_result import FacetResult
    from ..models.facets_meta import FacetsMeta


T = TypeVar("T", bound="Facets")


@_attrs_define
class Facets:
    """The facets of a SELECT with a FACETS clause: one entry per facet alias, plus 'meta'. Present only when the statement
    asked for facets. Facets cover the full WHERE match set, not the LIMIT page: 'returned' and 'truncated' describe the
    rows only, the facets always count every match. Inside a REPEATABLE_READ transaction the facets count the latest
    committed data, corrected by patching for the records written since the projection was applied (and for the
    transaction's own writes), not the transaction's snapshot.

        Attributes:
            meta (FacetsMeta): How exact the facets of this response are
    """

    meta: FacetsMeta
    additional_properties: dict[str, FacetResult] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        meta = self.meta.to_dict()

        field_dict: dict[str, Any] = {}
        for prop_name, prop in self.additional_properties.items():
            field_dict[prop_name] = prop.to_dict()

        field_dict.update(
            {
                "meta": meta,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.facet_result import FacetResult
        from ..models.facets_meta import FacetsMeta

        d = dict(src_dict)
        meta = FacetsMeta.from_dict(d.pop("meta"))

        facets = cls(
            meta=meta,
        )

        additional_properties = {}
        for prop_name, prop_dict in d.items():
            additional_property = FacetResult.from_dict(prop_dict)

            additional_properties[prop_name] = additional_property

        facets.additional_properties = additional_properties
        return facets

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> FacetResult:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: FacetResult) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties

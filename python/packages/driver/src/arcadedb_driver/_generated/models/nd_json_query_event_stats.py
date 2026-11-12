from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.facets import Facets


T = TypeVar("T", bound="NdJsonQueryEventStats")


@_attrs_define
class NdJsonQueryEventStats:
    """Trailer, always the last line of a complete stream. Carries the same three numbers the buffered response reports at
    top level, and the facets of a SELECT with a FACETS clause.

        Attributes:
            facets (Facets | Unset): The facets of a SELECT with a FACETS clause: one entry per facet alias, plus 'meta'.
                Present only when the statement asked for facets. Facets cover the full WHERE match set, not the LIMIT page:
                'returned' and 'truncated' describe the rows only, the facets always count every match. Inside a REPEATABLE_READ
                transaction the facets count the latest committed data, corrected by patching for the records written since the
                projection was applied (and for the transaction's own writes), not the transaction's snapshot.
            limit (int | Unset): Effective row cap applied while streaming, -1 when uncapped
            returned (int | Unset): Number of rows that reached the client
            truncated (bool | Unset): True when the cap stopped the stream with rows still pending, so the result is
                incomplete
    """

    facets: Facets | Unset = UNSET
    limit: int | Unset = UNSET
    returned: int | Unset = UNSET
    truncated: bool | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        facets: dict[str, Any] | Unset = UNSET
        if not isinstance(self.facets, Unset):
            facets = self.facets.to_dict()

        limit = self.limit

        returned = self.returned

        truncated = self.truncated

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if facets is not UNSET:
            field_dict["facets"] = facets
        if limit is not UNSET:
            field_dict["limit"] = limit
        if returned is not UNSET:
            field_dict["returned"] = returned
        if truncated is not UNSET:
            field_dict["truncated"] = truncated

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.facets import Facets

        d = dict(src_dict)
        _facets = d.pop("facets", UNSET)
        facets: Facets | Unset
        if isinstance(_facets, Unset):
            facets = UNSET
        else:
            facets = Facets.from_dict(_facets)

        limit = d.pop("limit", UNSET)

        returned = d.pop("returned", UNSET)

        truncated = d.pop("truncated", UNSET)

        nd_json_query_event_stats = cls(
            facets=facets,
            limit=limit,
            returned=returned,
            truncated=truncated,
        )

        nd_json_query_event_stats.additional_properties = d
        return nd_json_query_event_stats

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

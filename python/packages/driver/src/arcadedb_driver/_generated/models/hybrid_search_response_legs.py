from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.hybrid_search_response_legs_expand import HybridSearchResponseLegsExpand
    from ..models.hybrid_search_response_legs_fulltext import HybridSearchResponseLegsFulltext
    from ..models.hybrid_search_response_legs_vector import HybridSearchResponseLegsVector


T = TypeVar("T", bound="HybridSearchResponseLegs")


@_attrs_define
class HybridSearchResponseLegs:
    """Per-leg accounting: how many rows each leg contributed, and whether the expansion hit its seed or fan-out cap.

    Attributes:
        vector (HybridSearchResponseLegsVector): The vector leg, which every hybrid search runs
        expand (HybridSearchResponseLegsExpand | Unset): The graph expansion leg, present whenever the request carried
            'expand'
        fulltext (HybridSearchResponseLegsFulltext | Unset): The full-text leg, present whenever it ran - including when
            it matched nothing
    """

    vector: HybridSearchResponseLegsVector
    expand: HybridSearchResponseLegsExpand | Unset = UNSET
    fulltext: HybridSearchResponseLegsFulltext | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        vector = self.vector.to_dict()

        expand: dict[str, Any] | Unset = UNSET
        if not isinstance(self.expand, Unset):
            expand = self.expand.to_dict()

        fulltext: dict[str, Any] | Unset = UNSET
        if not isinstance(self.fulltext, Unset):
            fulltext = self.fulltext.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "vector": vector,
            }
        )
        if expand is not UNSET:
            field_dict["expand"] = expand
        if fulltext is not UNSET:
            field_dict["fulltext"] = fulltext

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.hybrid_search_response_legs_expand import HybridSearchResponseLegsExpand
        from ..models.hybrid_search_response_legs_fulltext import HybridSearchResponseLegsFulltext
        from ..models.hybrid_search_response_legs_vector import HybridSearchResponseLegsVector

        d = dict(src_dict)
        vector = HybridSearchResponseLegsVector.from_dict(d.pop("vector"))

        _expand = d.pop("expand", UNSET)
        expand: HybridSearchResponseLegsExpand | Unset
        if isinstance(_expand, Unset):
            expand = UNSET
        else:
            expand = HybridSearchResponseLegsExpand.from_dict(_expand)

        _fulltext = d.pop("fulltext", UNSET)
        fulltext: HybridSearchResponseLegsFulltext | Unset
        if isinstance(_fulltext, Unset):
            fulltext = UNSET
        else:
            fulltext = HybridSearchResponseLegsFulltext.from_dict(_fulltext)

        hybrid_search_response_legs = cls(
            vector=vector,
            expand=expand,
            fulltext=fulltext,
        )

        hybrid_search_response_legs.additional_properties = d
        return hybrid_search_response_legs

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

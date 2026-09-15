from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="HybridSearchRequestWeights")


@_attrs_define
class HybridSearchRequestWeights:
    """Per-leg weight applied to every rank contribution. The only accepted keys are 'vector', 'fulltext' and 'expand', and
    a weight for a leg the request does not ask for is refused rather than ignored.

        Attributes:
            expand (float | Unset): Weight of the graph expansion leg. Refused unless the request also carries 'expand'
                Default: 0.5.
            fulltext (float | Unset): Weight of the full-text leg. Refused unless the request also carries
                'fulltextQuery'/'fulltextIndexName' Default: 1.0.
            vector (float | Unset): Weight of the vector leg Default: 1.0.
    """

    expand: float | Unset = 0.5
    fulltext: float | Unset = 1.0
    vector: float | Unset = 1.0

    def to_dict(self) -> dict[str, Any]:
        expand = self.expand

        fulltext = self.fulltext

        vector = self.vector

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if expand is not UNSET:
            field_dict["expand"] = expand
        if fulltext is not UNSET:
            field_dict["fulltext"] = fulltext
        if vector is not UNSET:
            field_dict["vector"] = vector

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        expand = d.pop("expand", UNSET)

        fulltext = d.pop("fulltext", UNSET)

        vector = d.pop("vector", UNSET)

        hybrid_search_request_weights = cls(
            expand=expand,
            fulltext=fulltext,
            vector=vector,
        )

        return hybrid_search_request_weights

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.hybrid_search_response_legs import HybridSearchResponseLegs
    from ..models.hybrid_search_response_results_item import HybridSearchResponseResultsItem


T = TypeVar("T", bound="HybridSearchResponse")


@_attrs_define
class HybridSearchResponse:
    """Fused results and per-leg accounting

    Attributes:
        count (int | Unset): Number of results returned
        fulltext_index_name (str | Unset): Full-text index that was searched, present whenever the full-text leg ran -
            including when it matched nothing
        fused (bool | Unset): False when only one leg produced rows: fusion needs at least two sources, so the response
            carries that leg's native distance or score instead of a fused one.
        fusion_strategy (str | Unset): Strategy actually applied; absent when 'fused' is false
        legs (HybridSearchResponseLegs | Unset): Per-leg accounting: how many rows each leg contributed, and whether the
            expansion hit its seed or fan-out cap
        results (list[HybridSearchResponseResultsItem] | Unset): Fused hits, best first
        scoring (str | Unset): Scoring direction of the vector leg
        sparse (bool | Unset): Whether the vector leg took the sparse path
        truncated (bool | Unset): True when the result window was filled
        vector_index_name (str | Unset): Vector index that was searched
    """

    count: int | Unset = UNSET
    fulltext_index_name: str | Unset = UNSET
    fused: bool | Unset = UNSET
    fusion_strategy: str | Unset = UNSET
    legs: HybridSearchResponseLegs | Unset = UNSET
    results: list[HybridSearchResponseResultsItem] | Unset = UNSET
    scoring: str | Unset = UNSET
    sparse: bool | Unset = UNSET
    truncated: bool | Unset = UNSET
    vector_index_name: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        count = self.count

        fulltext_index_name = self.fulltext_index_name

        fused = self.fused

        fusion_strategy = self.fusion_strategy

        legs: dict[str, Any] | Unset = UNSET
        if not isinstance(self.legs, Unset):
            legs = self.legs.to_dict()

        results: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.results, Unset):
            results = []
            for results_item_data in self.results:
                results_item = results_item_data.to_dict()
                results.append(results_item)

        scoring = self.scoring

        sparse = self.sparse

        truncated = self.truncated

        vector_index_name = self.vector_index_name

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if count is not UNSET:
            field_dict["count"] = count
        if fulltext_index_name is not UNSET:
            field_dict["fulltextIndexName"] = fulltext_index_name
        if fused is not UNSET:
            field_dict["fused"] = fused
        if fusion_strategy is not UNSET:
            field_dict["fusionStrategy"] = fusion_strategy
        if legs is not UNSET:
            field_dict["legs"] = legs
        if results is not UNSET:
            field_dict["results"] = results
        if scoring is not UNSET:
            field_dict["scoring"] = scoring
        if sparse is not UNSET:
            field_dict["sparse"] = sparse
        if truncated is not UNSET:
            field_dict["truncated"] = truncated
        if vector_index_name is not UNSET:
            field_dict["vectorIndexName"] = vector_index_name

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.hybrid_search_response_legs import HybridSearchResponseLegs
        from ..models.hybrid_search_response_results_item import HybridSearchResponseResultsItem

        d = dict(src_dict)
        count = d.pop("count", UNSET)

        fulltext_index_name = d.pop("fulltextIndexName", UNSET)

        fused = d.pop("fused", UNSET)

        fusion_strategy = d.pop("fusionStrategy", UNSET)

        _legs = d.pop("legs", UNSET)
        legs: HybridSearchResponseLegs | Unset
        if isinstance(_legs, Unset):
            legs = UNSET
        else:
            legs = HybridSearchResponseLegs.from_dict(_legs)

        _results = d.pop("results", UNSET)
        results: list[HybridSearchResponseResultsItem] | Unset = UNSET
        if _results is not UNSET:
            results = []
            for results_item_data in _results:
                results_item = HybridSearchResponseResultsItem.from_dict(results_item_data)

                results.append(results_item)

        scoring = d.pop("scoring", UNSET)

        sparse = d.pop("sparse", UNSET)

        truncated = d.pop("truncated", UNSET)

        vector_index_name = d.pop("vectorIndexName", UNSET)

        hybrid_search_response = cls(
            count=count,
            fulltext_index_name=fulltext_index_name,
            fused=fused,
            fusion_strategy=fusion_strategy,
            legs=legs,
            results=results,
            scoring=scoring,
            sparse=sparse,
            truncated=truncated,
            vector_index_name=vector_index_name,
        )

        hybrid_search_response.additional_properties = d
        return hybrid_search_response

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

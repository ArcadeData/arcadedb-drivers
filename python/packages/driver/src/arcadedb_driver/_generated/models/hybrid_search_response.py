from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.hybrid_search_response_fusion_strategy import HybridSearchResponseFusionStrategy
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.hybrid_search_response_legs import HybridSearchResponseLegs
    from ..models.hybrid_search_response_results_item import HybridSearchResponseResultsItem


T = TypeVar("T", bound="HybridSearchResponse")


@_attrs_define
class HybridSearchResponse:
    """Fused results and per-leg accounting

    Attributes:
        count (int): Number of results returned
        fused (bool): False when only one leg produced rows: fusion needs at least two sources, so the response carries
            that leg's native distance or score instead of a fused one.
        legs (HybridSearchResponseLegs): Per-leg accounting: how many rows each leg contributed, and whether the
            expansion hit its seed or fan-out cap.
        results (list[HybridSearchResponseResultsItem]): Fused hits, best first
        scoring (str): Scoring direction of the vector leg
        sparse (bool): Whether the vector leg took the sparse path
        truncated (bool): True when the result window was filled
        vector_index_name (str): Vector index that was searched
        fulltext_index_name (str | Unset): Full-text index that was searched, present whenever the full-text leg ran -
            including when it matched nothing
        fusion_strategy (HybridSearchResponseFusionStrategy | Unset): Strategy actually applied, upper-cased; absent
            when 'fused' is false
    """

    count: int
    fused: bool
    legs: HybridSearchResponseLegs
    results: list[HybridSearchResponseResultsItem]
    scoring: str
    sparse: bool
    truncated: bool
    vector_index_name: str
    fulltext_index_name: str | Unset = UNSET
    fusion_strategy: HybridSearchResponseFusionStrategy | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        count = self.count

        fused = self.fused

        legs = self.legs.to_dict()

        results = []
        for results_item_data in self.results:
            results_item = results_item_data.to_dict()
            results.append(results_item)

        scoring = self.scoring

        sparse = self.sparse

        truncated = self.truncated

        vector_index_name = self.vector_index_name

        fulltext_index_name = self.fulltext_index_name

        fusion_strategy: str | Unset = UNSET
        if not isinstance(self.fusion_strategy, Unset):
            fusion_strategy = self.fusion_strategy.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "count": count,
                "fused": fused,
                "legs": legs,
                "results": results,
                "scoring": scoring,
                "sparse": sparse,
                "truncated": truncated,
                "vectorIndexName": vector_index_name,
            }
        )
        if fulltext_index_name is not UNSET:
            field_dict["fulltextIndexName"] = fulltext_index_name
        if fusion_strategy is not UNSET:
            field_dict["fusionStrategy"] = fusion_strategy

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.hybrid_search_response_legs import HybridSearchResponseLegs
        from ..models.hybrid_search_response_results_item import HybridSearchResponseResultsItem

        d = dict(src_dict)
        count = d.pop("count")

        fused = d.pop("fused")

        legs = HybridSearchResponseLegs.from_dict(d.pop("legs"))

        results = []
        _results = d.pop("results")
        for results_item_data in _results:
            results_item = HybridSearchResponseResultsItem.from_dict(results_item_data)

            results.append(results_item)

        scoring = d.pop("scoring")

        sparse = d.pop("sparse")

        truncated = d.pop("truncated")

        vector_index_name = d.pop("vectorIndexName")

        fulltext_index_name = d.pop("fulltextIndexName", UNSET)

        _fusion_strategy = d.pop("fusionStrategy", UNSET)
        fusion_strategy: HybridSearchResponseFusionStrategy | Unset
        if isinstance(_fusion_strategy, Unset):
            fusion_strategy = UNSET
        else:
            fusion_strategy = HybridSearchResponseFusionStrategy(_fusion_strategy)

        hybrid_search_response = cls(
            count=count,
            fused=fused,
            legs=legs,
            results=results,
            scoring=scoring,
            sparse=sparse,
            truncated=truncated,
            vector_index_name=vector_index_name,
            fulltext_index_name=fulltext_index_name,
            fusion_strategy=fusion_strategy,
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

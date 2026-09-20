from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.query_response_result_type_1_edges_item import QueryResponseResultType1EdgesItem
    from ..models.query_response_result_type_1_records_item import QueryResponseResultType1RecordsItem
    from ..models.query_response_result_type_1_vertices_item import QueryResponseResultType1VerticesItem


T = TypeVar("T", bound="QueryResponseResultType1")


@_attrs_define
class QueryResponseResultType1:
    """The 'graph' and 'studio' serializers answer with one object instead of a row list: the elements every row
    referenced, deduplicated across the whole result.

        Attributes:
            edges (list[QueryResponseResultType1EdgesItem]): Edges, deduplicated
            vertices (list[QueryResponseResultType1VerticesItem]): Vertices, deduplicated
            records (list[QueryResponseResultType1RecordsItem] | Unset): Non-element rows. Written by the 'studio'
                serializer only
    """

    edges: list[QueryResponseResultType1EdgesItem]
    vertices: list[QueryResponseResultType1VerticesItem]
    records: list[QueryResponseResultType1RecordsItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        edges = []
        for edges_item_data in self.edges:
            edges_item = edges_item_data.to_dict()
            edges.append(edges_item)

        vertices = []
        for vertices_item_data in self.vertices:
            vertices_item = vertices_item_data.to_dict()
            vertices.append(vertices_item)

        records: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.records, Unset):
            records = []
            for records_item_data in self.records:
                records_item = records_item_data.to_dict()
                records.append(records_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "edges": edges,
                "vertices": vertices,
            }
        )
        if records is not UNSET:
            field_dict["records"] = records

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.query_response_result_type_1_edges_item import QueryResponseResultType1EdgesItem
        from ..models.query_response_result_type_1_records_item import QueryResponseResultType1RecordsItem
        from ..models.query_response_result_type_1_vertices_item import QueryResponseResultType1VerticesItem

        d = dict(src_dict)
        edges = []
        _edges = d.pop("edges")
        for edges_item_data in _edges:
            edges_item = QueryResponseResultType1EdgesItem.from_dict(edges_item_data)

            edges.append(edges_item)

        vertices = []
        _vertices = d.pop("vertices")
        for vertices_item_data in _vertices:
            vertices_item = QueryResponseResultType1VerticesItem.from_dict(vertices_item_data)

            vertices.append(vertices_item)

        _records = d.pop("records", UNSET)
        records: list[QueryResponseResultType1RecordsItem] | Unset = UNSET
        if _records is not UNSET:
            records = []
            for records_item_data in _records:
                records_item = QueryResponseResultType1RecordsItem.from_dict(records_item_data)

                records.append(records_item)

        query_response_result_type_1 = cls(
            edges=edges,
            vertices=vertices,
            records=records,
        )

        query_response_result_type_1.additional_properties = d
        return query_response_result_type_1

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

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="FullTextSearchRequest")


@_attrs_define
class FullTextSearchRequest:
    """Full-text search over a FULL_TEXT index

    Attributes:
        query_text (str): Lucene-syntax query, e.g. 'java' or '+java -python'. Must not be blank
        index_name (str | Unset): Full-text index to search; wins over 'typeName' when both are given
        limit (int | Unset): Maximum number of results to return Default: 10.
        properties (list[str] | Unset): Indexed properties, to pick between several full-text indexes on the same type
        type_name (str | Unset): Type whose full-text index to search. Usable alone only when the type carries exactly
            one
    """

    query_text: str
    index_name: str | Unset = UNSET
    limit: int | Unset = 10
    properties: list[str] | Unset = UNSET
    type_name: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        query_text = self.query_text

        index_name = self.index_name

        limit = self.limit

        properties: list[str] | Unset = UNSET
        if not isinstance(self.properties, Unset):
            properties = self.properties

        type_name = self.type_name

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "queryText": query_text,
            }
        )
        if index_name is not UNSET:
            field_dict["indexName"] = index_name
        if limit is not UNSET:
            field_dict["limit"] = limit
        if properties is not UNSET:
            field_dict["properties"] = properties
        if type_name is not UNSET:
            field_dict["typeName"] = type_name

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        query_text = d.pop("queryText")

        index_name = d.pop("indexName", UNSET)

        limit = d.pop("limit", UNSET)

        properties = cast(list[str], d.pop("properties", UNSET))

        type_name = d.pop("typeName", UNSET)

        full_text_search_request = cls(
            query_text=query_text,
            index_name=index_name,
            limit=limit,
            properties=properties,
            type_name=type_name,
        )

        full_text_search_request.additional_properties = d
        return full_text_search_request

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

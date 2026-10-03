from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="SupportPeerQueryRequest")


@_attrs_define
class SupportPeerQueryRequest:
    """A read-only query to run on other cluster nodes

    Attributes:
        database (str | Unset): The database name
        language (str | Unset): sql or opencypher
        nodes (str | Unset): 'all' or the name of one cluster node (default all)
        statement (str | Unset): The statement (1 to 2000 characters)
    """

    database: str | Unset = UNSET
    language: str | Unset = UNSET
    nodes: str | Unset = UNSET
    statement: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        database = self.database

        language = self.language

        nodes = self.nodes

        statement = self.statement

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if database is not UNSET:
            field_dict["database"] = database
        if language is not UNSET:
            field_dict["language"] = language
        if nodes is not UNSET:
            field_dict["nodes"] = nodes
        if statement is not UNSET:
            field_dict["statement"] = statement

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        database = d.pop("database", UNSET)

        language = d.pop("language", UNSET)

        nodes = d.pop("nodes", UNSET)

        statement = d.pop("statement", UNSET)

        support_peer_query_request = cls(
            database=database,
            language=language,
            nodes=nodes,
            statement=statement,
        )

        support_peer_query_request.additional_properties = d
        return support_peer_query_request

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

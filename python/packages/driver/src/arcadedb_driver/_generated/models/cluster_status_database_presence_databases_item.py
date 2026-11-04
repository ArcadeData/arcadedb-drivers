from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ClusterStatusDatabasePresenceDatabasesItem")


@_attrs_define
class ClusterStatusDatabasePresenceDatabasesItem:
    """One database of the presence matrix

    Attributes:
        missing (list[str] | Unset): Reachable nodes that do not hold it. An unreachable node is in neither list
        name (str | Unset): Database name
        present (list[str] | Unset): Reachable nodes that hold the database
    """

    missing: list[str] | Unset = UNSET
    name: str | Unset = UNSET
    present: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        missing: list[str] | Unset = UNSET
        if not isinstance(self.missing, Unset):
            missing = self.missing

        name = self.name

        present: list[str] | Unset = UNSET
        if not isinstance(self.present, Unset):
            present = self.present

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if missing is not UNSET:
            field_dict["missing"] = missing
        if name is not UNSET:
            field_dict["name"] = name
        if present is not UNSET:
            field_dict["present"] = present

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        missing = cast(list[str], d.pop("missing", UNSET))

        name = d.pop("name", UNSET)

        present = cast(list[str], d.pop("present", UNSET))

        cluster_status_database_presence_databases_item = cls(
            missing=missing,
            name=name,
            present=present,
        )

        cluster_status_database_presence_databases_item.additional_properties = d
        return cluster_status_database_presence_databases_item

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

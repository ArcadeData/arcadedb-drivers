from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.group_list_result_databases import GroupListResultDatabases


T = TypeVar("T", bound="GroupListResult")


@_attrs_define
class GroupListResult:
    """The group document as stored

    Attributes:
        databases (GroupListResultDatabases): Group definitions per database, keyed by database name. '*' is a legal key
            and covers every database
        version (int): Schema version of the group document
    """

    databases: GroupListResultDatabases
    version: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        databases = self.databases.to_dict()

        version = self.version

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "databases": databases,
                "version": version,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.group_list_result_databases import GroupListResultDatabases

        d = dict(src_dict)
        databases = GroupListResultDatabases.from_dict(d.pop("databases"))

        version = d.pop("version")

        group_list_result = cls(
            databases=databases,
            version=version,
        )

        group_list_result.additional_properties = d
        return group_list_result

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

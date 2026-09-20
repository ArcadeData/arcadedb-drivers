from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.user_list_result_item_databases import UserListResultItemDatabases


T = TypeVar("T", bound="UserListResultItem")


@_attrs_define
class UserListResultItem:
    """One server user. The password hash is never returned

    Attributes:
        databases (UserListResultItemDatabases): Database assignments, keyed by database name. '*' means every database
        name (str): User name
    """

    databases: UserListResultItemDatabases
    name: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        databases = self.databases.to_dict()

        name = self.name

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "databases": databases,
                "name": name,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.user_list_result_item_databases import UserListResultItemDatabases

        d = dict(src_dict)
        databases = UserListResultItemDatabases.from_dict(d.pop("databases"))

        name = d.pop("name")

        user_list_result_item = cls(
            databases=databases,
            name=name,
        )

        user_list_result_item.additional_properties = d
        return user_list_result_item

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

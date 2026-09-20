from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.update_user_request_databases import UpdateUserRequestDatabases


T = TypeVar("T", bound="UpdateUserRequest")


@_attrs_define
class UpdateUserRequest:
    """Changes to apply to an existing user, named by the 'name' QUERY parameter rather than by the body. Both members are
    optional and an omitted one is left alone; a body carrying neither is accepted and changes nothing.

        Attributes:
            databases (UpdateUserRequestDatabases | Unset): Database assignments, keyed by database name. '*' means every
                database
            password (str | Unset): New plaintext password. Omit to leave the current one in place
    """

    databases: UpdateUserRequestDatabases | Unset = UNSET
    password: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        databases: dict[str, Any] | Unset = UNSET
        if not isinstance(self.databases, Unset):
            databases = self.databases.to_dict()

        password = self.password

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if databases is not UNSET:
            field_dict["databases"] = databases
        if password is not UNSET:
            field_dict["password"] = password

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.update_user_request_databases import UpdateUserRequestDatabases

        d = dict(src_dict)
        _databases = d.pop("databases", UNSET)
        databases: UpdateUserRequestDatabases | Unset
        if isinstance(_databases, Unset):
            databases = UNSET
        else:
            databases = UpdateUserRequestDatabases.from_dict(_databases)

        password = d.pop("password", UNSET)

        update_user_request = cls(
            databases=databases,
            password=password,
        )

        update_user_request.additional_properties = d
        return update_user_request

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

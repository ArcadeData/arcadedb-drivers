from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.create_user_request_databases import CreateUserRequestDatabases


T = TypeVar("T", bound="CreateUserRequest")


@_attrs_define
class CreateUserRequest:
    """A user to create

    Attributes:
        name (str): User name. Must not be blank and must not start with 'apitoken:', which is the prefix reserved for
            the synthetic principals API tokens authenticate as.
        password (str): Plaintext password, hashed by the server before it is stored
        databases (CreateUserRequestDatabases | Unset): Database assignments, keyed by database name. '*' means every
            database
    """

    name: str
    password: str
    databases: CreateUserRequestDatabases | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        password = self.password

        databases: dict[str, Any] | Unset = UNSET
        if not isinstance(self.databases, Unset):
            databases = self.databases.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "password": password,
            }
        )
        if databases is not UNSET:
            field_dict["databases"] = databases

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.create_user_request_databases import CreateUserRequestDatabases

        d = dict(src_dict)
        name = d.pop("name")

        password = d.pop("password")

        _databases = d.pop("databases", UNSET)
        databases: CreateUserRequestDatabases | Unset
        if isinstance(_databases, Unset):
            databases = UNSET
        else:
            databases = CreateUserRequestDatabases.from_dict(_databases)

        create_user_request = cls(
            name=name,
            password=password,
            databases=databases,
        )

        create_user_request.additional_properties = d
        return create_user_request

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

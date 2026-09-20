from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.create_api_token_request_permissions import CreateApiTokenRequestPermissions


T = TypeVar("T", bound="CreateApiTokenRequest")


@_attrs_define
class CreateApiTokenRequest:
    """A token to issue

    Attributes:
        name (str): Token name. Must not already be in use
        database (str | Unset): Database to scope the token to. Defaults to '*', every database, which an empty value
            also means
        expires_at (int | Unset): Expiry as epoch milliseconds. Defaults to 0, which does not expire
        permissions (CreateApiTokenRequestPermissions | Unset): Permissions to grant, in the same shape a group's
            'types' map takes. Defaults to none
    """

    name: str
    database: str | Unset = UNSET
    expires_at: int | Unset = UNSET
    permissions: CreateApiTokenRequestPermissions | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        database = self.database

        expires_at = self.expires_at

        permissions: dict[str, Any] | Unset = UNSET
        if not isinstance(self.permissions, Unset):
            permissions = self.permissions.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
            }
        )
        if database is not UNSET:
            field_dict["database"] = database
        if expires_at is not UNSET:
            field_dict["expiresAt"] = expires_at
        if permissions is not UNSET:
            field_dict["permissions"] = permissions

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.create_api_token_request_permissions import CreateApiTokenRequestPermissions

        d = dict(src_dict)
        name = d.pop("name")

        database = d.pop("database", UNSET)

        expires_at = d.pop("expiresAt", UNSET)

        _permissions = d.pop("permissions", UNSET)
        permissions: CreateApiTokenRequestPermissions | Unset
        if isinstance(_permissions, Unset):
            permissions = UNSET
        else:
            permissions = CreateApiTokenRequestPermissions.from_dict(_permissions)

        create_api_token_request = cls(
            name=name,
            database=database,
            expires_at=expires_at,
            permissions=permissions,
        )

        create_api_token_request.additional_properties = d
        return create_api_token_request

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

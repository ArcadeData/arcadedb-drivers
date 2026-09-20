from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.create_api_token_response_result_permissions import CreateApiTokenResponseResultPermissions


T = TypeVar("T", bound="CreateApiTokenResponseResult")


@_attrs_define
class CreateApiTokenResponseResult:
    """The issued token: every field the listing carries, plus the plaintext 'token'. Read it now - the server stores only
    the hash, so this is the one and only time that value exists outside the caller's hands.

        Attributes:
            created_at (int): Issue time as epoch milliseconds
            database (str): Database the token is scoped to. '*' means every database
            expires_at (int): Expiry as epoch milliseconds. 0 means the token does not expire
            name (str): Token name, unique among issued tokens
            permissions (CreateApiTokenResponseResultPermissions): Permissions the token carries, in the same shape a
                group's 'types' map takes
            token (str): The plaintext token, presented as a bearer credential. Returned exactly once, here; it cannot be
                read back from the listing and cannot be recovered if lost.
            token_hash (str): SHA-256 hex of the token. The handle DELETE names; the only one the server keeps
            token_suffix (str): Last characters of the plaintext token, so an operator can tell two entries apart
            expired (bool | Unset): Whether this token's expiry has passed. Carried by the listing only. An expired token
                authenticates nobody, but it stays listed until the next token change retires it
    """

    created_at: int
    database: str
    expires_at: int
    name: str
    permissions: CreateApiTokenResponseResultPermissions
    token: str
    token_hash: str
    token_suffix: str
    expired: bool | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        created_at = self.created_at

        database = self.database

        expires_at = self.expires_at

        name = self.name

        permissions = self.permissions.to_dict()

        token = self.token

        token_hash = self.token_hash

        token_suffix = self.token_suffix

        expired = self.expired

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "createdAt": created_at,
                "database": database,
                "expiresAt": expires_at,
                "name": name,
                "permissions": permissions,
                "token": token,
                "tokenHash": token_hash,
                "tokenSuffix": token_suffix,
            }
        )
        if expired is not UNSET:
            field_dict["expired"] = expired

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.create_api_token_response_result_permissions import CreateApiTokenResponseResultPermissions

        d = dict(src_dict)
        created_at = d.pop("createdAt")

        database = d.pop("database")

        expires_at = d.pop("expiresAt")

        name = d.pop("name")

        permissions = CreateApiTokenResponseResultPermissions.from_dict(d.pop("permissions"))

        token = d.pop("token")

        token_hash = d.pop("tokenHash")

        token_suffix = d.pop("tokenSuffix")

        expired = d.pop("expired", UNSET)

        create_api_token_response_result = cls(
            created_at=created_at,
            database=database,
            expires_at=expires_at,
            name=name,
            permissions=permissions,
            token=token,
            token_hash=token_hash,
            token_suffix=token_suffix,
            expired=expired,
        )

        create_api_token_response_result.additional_properties = d
        return create_api_token_response_result

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

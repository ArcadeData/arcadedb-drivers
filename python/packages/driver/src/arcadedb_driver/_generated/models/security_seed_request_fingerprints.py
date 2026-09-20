from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="SecuritySeedRequestFingerprints")


@_attrs_define
class SecuritySeedRequestFingerprints:
    """The caller's own document digests. When all three match the leader's, nothing is submitted and the answer is
    upToDate. Omit them to have every document seeded, which is what an admission does - the admitting node does not
    hold the joining peer's copies.

        Attributes:
            api_tokens (str | Unset): Digest of server-api-tokens.json as the caller holds it
            groups (str | Unset): Digest of server-groups.json as the caller holds it
            users (str | Unset): Digest of server-users.jsonl as the caller holds it
    """

    api_tokens: str | Unset = UNSET
    groups: str | Unset = UNSET
    users: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        api_tokens = self.api_tokens

        groups = self.groups

        users = self.users

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if api_tokens is not UNSET:
            field_dict["apiTokens"] = api_tokens
        if groups is not UNSET:
            field_dict["groups"] = groups
        if users is not UNSET:
            field_dict["users"] = users

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        api_tokens = d.pop("apiTokens", UNSET)

        groups = d.pop("groups", UNSET)

        users = d.pop("users", UNSET)

        security_seed_request_fingerprints = cls(
            api_tokens=api_tokens,
            groups=groups,
            users=users,
        )

        security_seed_request_fingerprints.additional_properties = d
        return security_seed_request_fingerprints

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

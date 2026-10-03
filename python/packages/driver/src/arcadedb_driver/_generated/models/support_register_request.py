from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="SupportRegisterRequest")


@_attrs_define
class SupportRegisterRequest:
    """Credentials of the customer portal

    Attributes:
        client_id (str): The Client ID (workspace id) of the portal
        key (str): The Client key ('wsk_...') created in the portal. Never returned by any API
        verify_only (bool | Unset): true to check the credentials with the portal without storing them: answers
            {verified, workspaceName, plan, sla, keyLabel, scopes}
    """

    client_id: str
    key: str
    verify_only: bool | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        client_id = self.client_id

        key = self.key

        verify_only = self.verify_only

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "clientId": client_id,
                "key": key,
            }
        )
        if verify_only is not UNSET:
            field_dict["verifyOnly"] = verify_only

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        client_id = d.pop("clientId")

        key = d.pop("key")

        verify_only = d.pop("verifyOnly", UNSET)

        support_register_request = cls(
            client_id=client_id,
            key=key,
            verify_only=verify_only,
        )

        support_register_request.additional_properties = d
        return support_register_request

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

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.cluster_auth_session_request_action import ClusterAuthSessionRequestAction
from ..types import UNSET, Unset

T = TypeVar("T", bound="ClusterAuthSessionRequest")


@_attrs_define
class ClusterAuthSessionRequest:
    """A session token and the action to apply to it

    Attributes:
        token (str): The session token, 'AU-<server name>-<uuid>'
        action (ClusterAuthSessionRequestAction | Unset): What to do with the token. 'validate' answers with the session
            the issuer holds; 'revoke' drops it. Defaults to 'validate'. Anything else is refused with a 400 naming it.
    """

    token: str
    action: ClusterAuthSessionRequestAction | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        token = self.token

        action: str | Unset = UNSET
        if not isinstance(self.action, Unset):
            action = self.action.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "token": token,
            }
        )
        if action is not UNSET:
            field_dict["action"] = action

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        token = d.pop("token")

        _action = d.pop("action", UNSET)
        action: ClusterAuthSessionRequestAction | Unset
        if isinstance(_action, Unset):
            action = UNSET
        else:
            action = ClusterAuthSessionRequestAction(_action)

        cluster_auth_session_request = cls(
            token=token,
            action=action,
        )

        cluster_auth_session_request.additional_properties = d
        return cluster_auth_session_request

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

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="PeerCapabilitiesResponse")


@_attrs_define
class PeerCapabilitiesResponse:
    """The wire-format sections one peer can decode

    Attributes:
        capabilities (list[str] | Unset): Capability tokens this peer can decode, sorted
        peer_id (str | Unset): Peer that answered. A caller must check this against the peer it meant to ask: on a
            cluster that declares no explicit 'http' ports several peers can resolve to one address.
        version (str | Unset): Server version of the answering peer, for operators; nothing decides on it
    """

    capabilities: list[str] | Unset = UNSET
    peer_id: str | Unset = UNSET
    version: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        capabilities: list[str] | Unset = UNSET
        if not isinstance(self.capabilities, Unset):
            capabilities = self.capabilities

        peer_id = self.peer_id

        version = self.version

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if capabilities is not UNSET:
            field_dict["capabilities"] = capabilities
        if peer_id is not UNSET:
            field_dict["peerId"] = peer_id
        if version is not UNSET:
            field_dict["version"] = version

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        capabilities = cast(list[str], d.pop("capabilities", UNSET))

        peer_id = d.pop("peerId", UNSET)

        version = d.pop("version", UNSET)

        peer_capabilities_response = cls(
            capabilities=capabilities,
            peer_id=peer_id,
            version=version,
        )

        peer_capabilities_response.additional_properties = d
        return peer_capabilities_response

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

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ServerInfoPorts")


@_attrs_define
class ServerInfoPorts:
    """The client-facing listeners of the active plugins other than HTTP, by service name (for example 'gremlin'), with the
    port each one is bound to. Present with mode=cluster only, empty when no plugin listens. A remote client that must
    reach such a listener reads it here instead of assuming the protocol's default port (issue #8578). Service names are
    unique: a second plugin advertising a name already taken is ignored.

    """

    additional_properties: dict[str, int] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        server_info_ports = cls()

        server_info_ports.additional_properties = d
        return server_info_ports

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> int:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: int) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties

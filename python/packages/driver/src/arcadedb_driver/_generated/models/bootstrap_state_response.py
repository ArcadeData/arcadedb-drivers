from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.bootstrap_state_response_databases_item import BootstrapStateResponseDatabasesItem


T = TypeVar("T", bound="BootstrapStateResponse")


@_attrs_define
class BootstrapStateResponse:
    """Per-database bootstrap state of one peer

    Attributes:
        databases (list[BootstrapStateResponseDatabasesItem]): Databases on this peer. Empty when it holds none
        peer_id (str): Peer that reported the state
    """

    databases: list[BootstrapStateResponseDatabasesItem]
    peer_id: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        databases = []
        for databases_item_data in self.databases:
            databases_item = databases_item_data.to_dict()
            databases.append(databases_item)

        peer_id = self.peer_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "databases": databases,
                "peerId": peer_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.bootstrap_state_response_databases_item import BootstrapStateResponseDatabasesItem

        d = dict(src_dict)
        databases = []
        _databases = d.pop("databases")
        for databases_item_data in _databases:
            databases_item = BootstrapStateResponseDatabasesItem.from_dict(databases_item_data)

            databases.append(databases_item)

        peer_id = d.pop("peerId")

        bootstrap_state_response = cls(
            databases=databases,
            peer_id=peer_id,
        )

        bootstrap_state_response.additional_properties = d
        return bootstrap_state_response

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

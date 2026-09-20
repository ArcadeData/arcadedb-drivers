from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="VerifyDatabaseClusterResultPeersItemMismatchesItem")


@_attrs_define
class VerifyDatabaseClusterResultPeersItemMismatchesItem:
    """One file whose checksum differs between the leader and a peer

    Attributes:
        file (str): File name
        local_checksum (int): Leader's CRC for the file
        remote_checksum (str): Peer's CRC for the file, or 'MISSING' when the peer does not have it
        type_ (str): File category
    """

    file: str
    local_checksum: int
    remote_checksum: str
    type_: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        file = self.file

        local_checksum = self.local_checksum

        remote_checksum = self.remote_checksum

        type_ = self.type_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "file": file,
                "localChecksum": local_checksum,
                "remoteChecksum": remote_checksum,
                "type": type_,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        file = d.pop("file")

        local_checksum = d.pop("localChecksum")

        remote_checksum = d.pop("remoteChecksum")

        type_ = d.pop("type")

        verify_database_cluster_result_peers_item_mismatches_item = cls(
            file=file,
            local_checksum=local_checksum,
            remote_checksum=remote_checksum,
            type_=type_,
        )

        verify_database_cluster_result_peers_item_mismatches_item.additional_properties = d
        return verify_database_cluster_result_peers_item_mismatches_item

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

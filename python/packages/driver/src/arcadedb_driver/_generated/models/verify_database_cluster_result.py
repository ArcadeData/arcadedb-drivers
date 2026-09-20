from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.verify_database_cluster_result_files_item import VerifyDatabaseClusterResultFilesItem
    from ..models.verify_database_cluster_result_local_checksums import VerifyDatabaseClusterResultLocalChecksums
    from ..models.verify_database_cluster_result_peers_item import VerifyDatabaseClusterResultPeersItem


T = TypeVar("T", bound="VerifyDatabaseClusterResult")


@_attrs_define
class VerifyDatabaseClusterResult:
    """Leader-only cluster-wide comparison, fanned out to every peer

    Attributes:
        database (str): Database name
        files (list[VerifyDatabaseClusterResultFilesItem]): The leader's files with size and category
        local_checksums (VerifyDatabaseClusterResultLocalChecksums): Leader's file name to checksum map
        local_peer_id (str): Leader's peer identifier
        local_server (str): Leader server name
        overall_status (str): ALL_CONSISTENT when every peer was compared and agreed, INCONSISTENCY_DETECTED when a
            compared peer differs, VERIFICATION_INCOMPLETE when nothing diverged but at least one peer could not be verified
        peers (list[VerifyDatabaseClusterResultPeersItem]): Every other peer's comparison result
        incomplete_sealed_stores (bool | Unset): Present and true when the LEADER's own answer was short of a sealed
            store, so no peer comparison can be complete: the leader compares its own keys. Absent when its coverage was
            complete.
    """

    database: str
    files: list[VerifyDatabaseClusterResultFilesItem]
    local_checksums: VerifyDatabaseClusterResultLocalChecksums
    local_peer_id: str
    local_server: str
    overall_status: str
    peers: list[VerifyDatabaseClusterResultPeersItem]
    incomplete_sealed_stores: bool | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        database = self.database

        files = []
        for files_item_data in self.files:
            files_item = files_item_data.to_dict()
            files.append(files_item)

        local_checksums = self.local_checksums.to_dict()

        local_peer_id = self.local_peer_id

        local_server = self.local_server

        overall_status = self.overall_status

        peers = []
        for peers_item_data in self.peers:
            peers_item = peers_item_data.to_dict()
            peers.append(peers_item)

        incomplete_sealed_stores = self.incomplete_sealed_stores

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "database": database,
                "files": files,
                "localChecksums": local_checksums,
                "localPeerId": local_peer_id,
                "localServer": local_server,
                "overallStatus": overall_status,
                "peers": peers,
            }
        )
        if incomplete_sealed_stores is not UNSET:
            field_dict["incompleteSealedStores"] = incomplete_sealed_stores

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.verify_database_cluster_result_files_item import VerifyDatabaseClusterResultFilesItem
        from ..models.verify_database_cluster_result_local_checksums import VerifyDatabaseClusterResultLocalChecksums
        from ..models.verify_database_cluster_result_peers_item import VerifyDatabaseClusterResultPeersItem

        d = dict(src_dict)
        database = d.pop("database")

        files = []
        _files = d.pop("files")
        for files_item_data in _files:
            files_item = VerifyDatabaseClusterResultFilesItem.from_dict(files_item_data)

            files.append(files_item)

        local_checksums = VerifyDatabaseClusterResultLocalChecksums.from_dict(d.pop("localChecksums"))

        local_peer_id = d.pop("localPeerId")

        local_server = d.pop("localServer")

        overall_status = d.pop("overallStatus")

        peers = []
        _peers = d.pop("peers")
        for peers_item_data in _peers:
            peers_item = VerifyDatabaseClusterResultPeersItem.from_dict(peers_item_data)

            peers.append(peers_item)

        incomplete_sealed_stores = d.pop("incompleteSealedStores", UNSET)

        verify_database_cluster_result = cls(
            database=database,
            files=files,
            local_checksums=local_checksums,
            local_peer_id=local_peer_id,
            local_server=local_server,
            overall_status=overall_status,
            peers=peers,
            incomplete_sealed_stores=incomplete_sealed_stores,
        )

        verify_database_cluster_result.additional_properties = d
        return verify_database_cluster_result

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

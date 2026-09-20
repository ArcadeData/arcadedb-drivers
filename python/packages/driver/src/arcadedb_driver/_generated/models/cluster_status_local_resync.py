from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.cluster_status_local_resync_database_applied_floors import (
        ClusterStatusLocalResyncDatabaseAppliedFloors,
    )
    from ..models.cluster_status_local_resync_divergence_causes import ClusterStatusLocalResyncDivergenceCauses


T = TypeVar("T", bound="ClusterStatusLocalResync")


@_attrs_define
class ClusterStatusLocalResync:
    """This node's resync state. Present on every answer. The database names it carries are reduced to the ones the caller
    is authorized on, so a caller scoped to one database cannot learn another tenant's database name from a status poll.

        Attributes:
            database_applied_floors (ClusterStatusLocalResyncDatabaseAppliedFloors): Per-database applied floor, keyed by
                database name
            diverged_databases (list[str]): Databases quarantined because this node's WAL diverged from the leader's
            divergence_causes (ClusterStatusLocalResyncDivergenceCauses): Why each quarantined database was quarantined,
                keyed by database name. Same keys as 'divergedDatabases'
            in_progress (bool): True while a resync is holding this node out of the ready set. NOT the whole answer
                '/api/v1/ready' gives: a node halted by a critical error or wedged by a log-write failure has this false and
                answers 503 anyway, so read it together with 'criticalHalt' and 'raftLogFailure' (issue #7872).
            snapshot_applied_floor (int): Raft index the last installed snapshot brought this node to
            snapshot_download_in_progress (bool): A snapshot is being installed now
            snapshot_download_queued (bool): A snapshot install is waiting to start
    """

    database_applied_floors: ClusterStatusLocalResyncDatabaseAppliedFloors
    diverged_databases: list[str]
    divergence_causes: ClusterStatusLocalResyncDivergenceCauses
    in_progress: bool
    snapshot_applied_floor: int
    snapshot_download_in_progress: bool
    snapshot_download_queued: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        database_applied_floors = self.database_applied_floors.to_dict()

        diverged_databases = self.diverged_databases

        divergence_causes = self.divergence_causes.to_dict()

        in_progress = self.in_progress

        snapshot_applied_floor = self.snapshot_applied_floor

        snapshot_download_in_progress = self.snapshot_download_in_progress

        snapshot_download_queued = self.snapshot_download_queued

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "databaseAppliedFloors": database_applied_floors,
                "divergedDatabases": diverged_databases,
                "divergenceCauses": divergence_causes,
                "inProgress": in_progress,
                "snapshotAppliedFloor": snapshot_applied_floor,
                "snapshotDownloadInProgress": snapshot_download_in_progress,
                "snapshotDownloadQueued": snapshot_download_queued,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.cluster_status_local_resync_database_applied_floors import (
            ClusterStatusLocalResyncDatabaseAppliedFloors,
        )
        from ..models.cluster_status_local_resync_divergence_causes import ClusterStatusLocalResyncDivergenceCauses

        d = dict(src_dict)
        database_applied_floors = ClusterStatusLocalResyncDatabaseAppliedFloors.from_dict(
            d.pop("databaseAppliedFloors")
        )

        diverged_databases = cast(list[str], d.pop("divergedDatabases"))

        divergence_causes = ClusterStatusLocalResyncDivergenceCauses.from_dict(d.pop("divergenceCauses"))

        in_progress = d.pop("inProgress")

        snapshot_applied_floor = d.pop("snapshotAppliedFloor")

        snapshot_download_in_progress = d.pop("snapshotDownloadInProgress")

        snapshot_download_queued = d.pop("snapshotDownloadQueued")

        cluster_status_local_resync = cls(
            database_applied_floors=database_applied_floors,
            diverged_databases=diverged_databases,
            divergence_causes=divergence_causes,
            in_progress=in_progress,
            snapshot_applied_floor=snapshot_applied_floor,
            snapshot_download_in_progress=snapshot_download_in_progress,
            snapshot_download_queued=snapshot_download_queued,
        )

        cluster_status_local_resync.additional_properties = d
        return cluster_status_local_resync

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

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ClusterActionResponse")


@_attrs_define
class ClusterActionResponse:
    """Outcome of a cluster management action

    Attributes:
        result (str): Human-readable outcome
        applied_index (int | Unset): Last Raft index applied to the accepted copy, or -1 when none is recorded. Present
            on accept-copy and accept-diverged. On accept-stale-snapshot, the applied position now recorded for the node.
        database (str | Unset): Database the action applied to. Present on resync, accept-copy and accept-diverged.
        divergence_cause (str | Unset): Why the lifted quarantine had been raised (WAL_VERSION_GAP,
            UNDECODABLE_LOG_ENTRY, APPLY_ERROR, SNAPSHOT_INSTALL_INCOMPLETE, UNPUBLISHED_SCHEMA_CHANGE), when one stood.
            Present on accept-diverged.
        leader_id (str | Unset): Leader after the action. Present on leadership transfer.
        local_server (str | Unset): Server that performed the action. Present on resync, accept-copy, accept-diverged
            and accept-stale-snapshot.
        overridden_refusal (str | Unset): Why the leader had refused to reopen the copy, when a refusal was standing.
            Present on accept-copy.
        read_floor (int | Unset): The read floor that was lifted with the quarantine, when one stood. Present on accept-
            diverged, and on accept-stale-snapshot as the node-wide floor that was lifted.
        snapshot_index (int | Unset): The snapshot marker index the node-wide read floor was short of, or -1 when no
            marker was on disk. Present on accept-stale-snapshot.
    """

    result: str
    applied_index: int | Unset = UNSET
    database: str | Unset = UNSET
    divergence_cause: str | Unset = UNSET
    leader_id: str | Unset = UNSET
    local_server: str | Unset = UNSET
    overridden_refusal: str | Unset = UNSET
    read_floor: int | Unset = UNSET
    snapshot_index: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = self.result

        applied_index = self.applied_index

        database = self.database

        divergence_cause = self.divergence_cause

        leader_id = self.leader_id

        local_server = self.local_server

        overridden_refusal = self.overridden_refusal

        read_floor = self.read_floor

        snapshot_index = self.snapshot_index

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "result": result,
            }
        )
        if applied_index is not UNSET:
            field_dict["appliedIndex"] = applied_index
        if database is not UNSET:
            field_dict["database"] = database
        if divergence_cause is not UNSET:
            field_dict["divergenceCause"] = divergence_cause
        if leader_id is not UNSET:
            field_dict["leaderId"] = leader_id
        if local_server is not UNSET:
            field_dict["localServer"] = local_server
        if overridden_refusal is not UNSET:
            field_dict["overriddenRefusal"] = overridden_refusal
        if read_floor is not UNSET:
            field_dict["readFloor"] = read_floor
        if snapshot_index is not UNSET:
            field_dict["snapshotIndex"] = snapshot_index

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        result = d.pop("result")

        applied_index = d.pop("appliedIndex", UNSET)

        database = d.pop("database", UNSET)

        divergence_cause = d.pop("divergenceCause", UNSET)

        leader_id = d.pop("leaderId", UNSET)

        local_server = d.pop("localServer", UNSET)

        overridden_refusal = d.pop("overriddenRefusal", UNSET)

        read_floor = d.pop("readFloor", UNSET)

        snapshot_index = d.pop("snapshotIndex", UNSET)

        cluster_action_response = cls(
            result=result,
            applied_index=applied_index,
            database=database,
            divergence_cause=divergence_cause,
            leader_id=leader_id,
            local_server=local_server,
            overridden_refusal=overridden_refusal,
            read_floor=read_floor,
            snapshot_index=snapshot_index,
        )

        cluster_action_response.additional_properties = d
        return cluster_action_response

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

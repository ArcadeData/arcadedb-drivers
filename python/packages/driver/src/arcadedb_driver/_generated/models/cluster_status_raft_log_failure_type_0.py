from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ClusterStatusRaftLogFailureType0")


@_attrs_define
class ClusterStatusRaftLogFailureType0:
    """The persistent Raft log-write failure wedging this node, or null while the log writer is healthy. Present on every
    answer. A non-null value means Ratis is rejecting every append, so the node can neither catch up nor become caught
    up; the usual cause is a full Raft storage volume, and it clears by itself once the health monitor restarts the
    writer in place.

        Attributes:
            cause (str): The failure Ratis reported, as its own text, which routinely names the Raft storage path - so it is
                shown to the root user only: another caller reads a placeholder here while still getting 'index' and 'timestamp'
            index (int): The Raft index of the entry whose write failed, or -1 when the failure was on a log segment
            timestamp (int): When it was first reported, as epoch milliseconds
    """

    cause: str
    index: int
    timestamp: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        cause = self.cause

        index = self.index

        timestamp = self.timestamp

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "cause": cause,
                "index": index,
                "timestamp": timestamp,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        cause = d.pop("cause")

        index = d.pop("index")

        timestamp = d.pop("timestamp")

        cluster_status_raft_log_failure_type_0 = cls(
            cause=cause,
            index=index,
            timestamp=timestamp,
        )

        cluster_status_raft_log_failure_type_0.additional_properties = d
        return cluster_status_raft_log_failure_type_0

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

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ClusterStatusCriticalHaltType0")


@_attrs_define
class ClusterStatusCriticalHaltType0:
    """Why this node's replication state machine halted, or null while it is applying entries. Present on every answer. A
    non-null value means this node's databases are frozen at 'index' and will not advance again in this process: restart
    it.

        Attributes:
            index (int): The Raft index being applied when the halt tripped, or -1 when the entry carried none
            reason (str): One line naming what could not be applied. 'unknown Raft log entry type' means a newer peer is
                writing a format this build cannot read, and the answer is to upgrade this node; anything else is a bug. Raw
                exception text, so it is shown to the root user only: another caller reads a placeholder here while still
                getting 'index' and 'timestamp'
            timestamp (int): When it tripped, as epoch milliseconds
    """

    index: int
    reason: str
    timestamp: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        index = self.index

        reason = self.reason

        timestamp = self.timestamp

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "index": index,
                "reason": reason,
                "timestamp": timestamp,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        index = d.pop("index")

        reason = d.pop("reason")

        timestamp = d.pop("timestamp")

        cluster_status_critical_halt_type_0 = cls(
            index=index,
            reason=reason,
            timestamp=timestamp,
        )

        cluster_status_critical_halt_type_0.additional_properties = d
        return cluster_status_critical_halt_type_0

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

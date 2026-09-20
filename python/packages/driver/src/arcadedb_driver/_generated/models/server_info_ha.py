from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ServerInfoHa")


@_attrs_define
class ServerInfoHa:
    """Cluster topology and per-database replication state. Present with mode=cluster only, and only when this server runs
    an HA implementation. The per-database rows are scoped to the caller's authorized databases; the topology members
    are not.

    Its 'securityRefresh' member says whether the replicated group changes THIS node received have been enforced here,
    not merely received: entriesApplied, refreshesRequested, refreshesCoalesced, sweepsCompleted, sweepsFailed,
    databasesRefreshed, databaseRefreshFailures, and the epoch-millisecond lastEntryAppliedAt / lastSweepAt.
    entriesApplied rising while sweepsCompleted does not is a node enforcing permissions it has already been told to
    replace; the same numbers are scrapable as the arcadedb.ha.security.* meters.

    """

    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        server_info_ha = cls()

        server_info_ha.additional_properties = d
        return server_info_ha

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

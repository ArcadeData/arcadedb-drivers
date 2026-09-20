from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ClusterStatusPeersItem")


@_attrs_define
class ClusterStatusPeersItem:
    """One peer's replication health

    Attributes:
        address (str): Peer address
        id (str): Peer identifier
        role (str): LEADER or FOLLOWER
        capabilities (list[str] | Unset): Optional wire-format sections this peer can decode, as last observed by the
            leader (issue #7219). Absent on a follower, which does not poll, and on the leader for a peer it has not
            reached: an absent array means 'not known', which the leader treats exactly like 'cannot decode'.
        capabilities_unknown_reason (str | Unset): Why 'capabilities' is absent for this peer, when the leader knows
            why. An absent capabilities array otherwise reads the same whether the peer runs a build that predates the
            capability route or was never asked because its address identifies no single peer, and the two have nothing
            alike as remedies (issue #7256). Written by the leader only.
        http_address (str | Unset): Peer HTTP endpoint as resolved by this node. Absent when it cannot be resolved.
        http_address_ambiguous (bool | Unset): True when the HTTP endpoint above does not identify this peer alone: two
            or more peers resolve to it, which is what happens when 'http' ports are not declared in arcadedb.ha.serverList
            and the nodes differ by port rather than by host. Peer-to-peer operations (snapshot resync, cluster verify)
            refuse to dial such a peer. Absent when the address is unambiguous.
        lagging (bool | Unset): True when the lag exceeds the configured warning threshold. Absent for the leader's own
            entry and until a health sample exists.
        lagging_for_ms (int | Unset): How long this peer has been lagging, in milliseconds. Absent for the leader's own
            entry and until a health sample exists.
        last_contact_ms (int | Unset): Milliseconds since last contact. Absent for the leader's own entry and until a
            health sample exists.
        match_index (int | Unset): Highest log entry known replicated. Absent for the leader's own entry and until a
            health sample exists.
        next_index (int | Unset): Next log entry to send. Absent for the leader's own entry and until a health sample
            exists.
        replica_status (str | Unset): Replica health status. Absent for the leader's own entry and until a health sample
            exists.
        replication_lag (int | Unset): Entries behind the leader. Absent for the leader's own entry and until a health
            sample exists.
        replication_rtt_ms (int | Unset): Mean replication round-trip time. Absent when no sample exists.
        replication_rtt_p99_ms (int | Unset): 99th percentile replication round-trip time. Absent when no sample exists.
        version (str | Unset): Server version this peer reported alongside its capabilities. Absent when the leader has
            no fresh answer from it.
    """

    address: str
    id: str
    role: str
    capabilities: list[str] | Unset = UNSET
    capabilities_unknown_reason: str | Unset = UNSET
    http_address: str | Unset = UNSET
    http_address_ambiguous: bool | Unset = UNSET
    lagging: bool | Unset = UNSET
    lagging_for_ms: int | Unset = UNSET
    last_contact_ms: int | Unset = UNSET
    match_index: int | Unset = UNSET
    next_index: int | Unset = UNSET
    replica_status: str | Unset = UNSET
    replication_lag: int | Unset = UNSET
    replication_rtt_ms: int | Unset = UNSET
    replication_rtt_p99_ms: int | Unset = UNSET
    version: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        address = self.address

        id = self.id

        role = self.role

        capabilities: list[str] | Unset = UNSET
        if not isinstance(self.capabilities, Unset):
            capabilities = self.capabilities

        capabilities_unknown_reason = self.capabilities_unknown_reason

        http_address = self.http_address

        http_address_ambiguous = self.http_address_ambiguous

        lagging = self.lagging

        lagging_for_ms = self.lagging_for_ms

        last_contact_ms = self.last_contact_ms

        match_index = self.match_index

        next_index = self.next_index

        replica_status = self.replica_status

        replication_lag = self.replication_lag

        replication_rtt_ms = self.replication_rtt_ms

        replication_rtt_p99_ms = self.replication_rtt_p99_ms

        version = self.version

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "address": address,
                "id": id,
                "role": role,
            }
        )
        if capabilities is not UNSET:
            field_dict["capabilities"] = capabilities
        if capabilities_unknown_reason is not UNSET:
            field_dict["capabilitiesUnknownReason"] = capabilities_unknown_reason
        if http_address is not UNSET:
            field_dict["httpAddress"] = http_address
        if http_address_ambiguous is not UNSET:
            field_dict["httpAddressAmbiguous"] = http_address_ambiguous
        if lagging is not UNSET:
            field_dict["lagging"] = lagging
        if lagging_for_ms is not UNSET:
            field_dict["laggingForMs"] = lagging_for_ms
        if last_contact_ms is not UNSET:
            field_dict["lastContactMs"] = last_contact_ms
        if match_index is not UNSET:
            field_dict["matchIndex"] = match_index
        if next_index is not UNSET:
            field_dict["nextIndex"] = next_index
        if replica_status is not UNSET:
            field_dict["replicaStatus"] = replica_status
        if replication_lag is not UNSET:
            field_dict["replicationLag"] = replication_lag
        if replication_rtt_ms is not UNSET:
            field_dict["replicationRttMs"] = replication_rtt_ms
        if replication_rtt_p99_ms is not UNSET:
            field_dict["replicationRttP99Ms"] = replication_rtt_p99_ms
        if version is not UNSET:
            field_dict["version"] = version

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        address = d.pop("address")

        id = d.pop("id")

        role = d.pop("role")

        capabilities = cast(list[str], d.pop("capabilities", UNSET))

        capabilities_unknown_reason = d.pop("capabilitiesUnknownReason", UNSET)

        http_address = d.pop("httpAddress", UNSET)

        http_address_ambiguous = d.pop("httpAddressAmbiguous", UNSET)

        lagging = d.pop("lagging", UNSET)

        lagging_for_ms = d.pop("laggingForMs", UNSET)

        last_contact_ms = d.pop("lastContactMs", UNSET)

        match_index = d.pop("matchIndex", UNSET)

        next_index = d.pop("nextIndex", UNSET)

        replica_status = d.pop("replicaStatus", UNSET)

        replication_lag = d.pop("replicationLag", UNSET)

        replication_rtt_ms = d.pop("replicationRttMs", UNSET)

        replication_rtt_p99_ms = d.pop("replicationRttP99Ms", UNSET)

        version = d.pop("version", UNSET)

        cluster_status_peers_item = cls(
            address=address,
            id=id,
            role=role,
            capabilities=capabilities,
            capabilities_unknown_reason=capabilities_unknown_reason,
            http_address=http_address,
            http_address_ambiguous=http_address_ambiguous,
            lagging=lagging,
            lagging_for_ms=lagging_for_ms,
            last_contact_ms=last_contact_ms,
            match_index=match_index,
            next_index=next_index,
            replica_status=replica_status,
            replication_lag=replication_lag,
            replication_rtt_ms=replication_rtt_ms,
            replication_rtt_p99_ms=replication_rtt_p99_ms,
            version=version,
        )

        cluster_status_peers_item.additional_properties = d
        return cluster_status_peers_item

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

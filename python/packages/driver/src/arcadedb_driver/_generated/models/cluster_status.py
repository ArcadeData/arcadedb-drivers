from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.cluster_status_alerts_item import ClusterStatusAlertsItem
    from ..models.cluster_status_database_presence import ClusterStatusDatabasePresence
    from ..models.cluster_status_databases_item import ClusterStatusDatabasesItem
    from ..models.cluster_status_peers_item import ClusterStatusPeersItem


T = TypeVar("T", bound="ClusterStatus")


@_attrs_define
class ClusterStatus:
    """Cluster and replication status

    Attributes:
        alerts (list[ClusterStatusAlertsItem] | Unset): Conditions worth an operator's attention
        capabilities (list[str] | Unset): Optional wire-format sections THIS node can decode, sorted (issue #7219)
        cluster_name (str | Unset): Configured cluster name
        database_presence (ClusterStatusDatabasePresence | Unset): Which peer holds which database. Present only when
            this server is the leader and the request set '?presence=true'.
        databases (list[ClusterStatusDatabasesItem] | Unset): Replicated databases
        election_count (int | Unset): Elections observed since start
        implementation (str | Unset): Always 'raft'
        is_leader (bool | Unset): True when this server is the leader
        last_election_time (int | Unset): Last election as epoch milliseconds
        leader_http_address (None | str | Unset): Leader HTTP address, null when unknown
        leader_id (None | str | Unset): Current leader, null when unknown
        leader_ready (bool | Unset): True when the leader has finished the work that makes it safe to serve writes
        local_peer_id (str | Unset): This server's peer identifier
        peers (list[ClusterStatusPeersItem] | Unset): Known peers
        raft_state (str | Unset): Raft lifecycle state
        uptime (int | Unset): Milliseconds since the Raft server started
    """

    alerts: list[ClusterStatusAlertsItem] | Unset = UNSET
    capabilities: list[str] | Unset = UNSET
    cluster_name: str | Unset = UNSET
    database_presence: ClusterStatusDatabasePresence | Unset = UNSET
    databases: list[ClusterStatusDatabasesItem] | Unset = UNSET
    election_count: int | Unset = UNSET
    implementation: str | Unset = UNSET
    is_leader: bool | Unset = UNSET
    last_election_time: int | Unset = UNSET
    leader_http_address: str | Unset | None = UNSET
    leader_id: str | Unset | None = UNSET
    leader_ready: bool | Unset = UNSET
    local_peer_id: str | Unset = UNSET
    peers: list[ClusterStatusPeersItem] | Unset = UNSET
    raft_state: str | Unset = UNSET
    uptime: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        alerts: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.alerts, Unset):
            alerts = []
            for alerts_item_data in self.alerts:
                alerts_item = alerts_item_data.to_dict()
                alerts.append(alerts_item)

        capabilities: list[str] | Unset = UNSET
        if not isinstance(self.capabilities, Unset):
            capabilities = self.capabilities

        cluster_name = self.cluster_name

        database_presence: dict[str, Any] | Unset = UNSET
        if not isinstance(self.database_presence, Unset):
            database_presence = self.database_presence.to_dict()

        databases: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.databases, Unset):
            databases = []
            for databases_item_data in self.databases:
                databases_item = databases_item_data.to_dict()
                databases.append(databases_item)

        election_count = self.election_count

        implementation = self.implementation

        is_leader = self.is_leader

        last_election_time = self.last_election_time

        leader_http_address: str | Unset | None
        if isinstance(self.leader_http_address, Unset):
            leader_http_address = UNSET
        else:
            leader_http_address = self.leader_http_address

        leader_id: str | Unset | None
        if isinstance(self.leader_id, Unset):
            leader_id = UNSET
        else:
            leader_id = self.leader_id

        leader_ready = self.leader_ready

        local_peer_id = self.local_peer_id

        peers: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.peers, Unset):
            peers = []
            for peers_item_data in self.peers:
                peers_item = peers_item_data.to_dict()
                peers.append(peers_item)

        raft_state = self.raft_state

        uptime = self.uptime

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if alerts is not UNSET:
            field_dict["alerts"] = alerts
        if capabilities is not UNSET:
            field_dict["capabilities"] = capabilities
        if cluster_name is not UNSET:
            field_dict["clusterName"] = cluster_name
        if database_presence is not UNSET:
            field_dict["databasePresence"] = database_presence
        if databases is not UNSET:
            field_dict["databases"] = databases
        if election_count is not UNSET:
            field_dict["electionCount"] = election_count
        if implementation is not UNSET:
            field_dict["implementation"] = implementation
        if is_leader is not UNSET:
            field_dict["isLeader"] = is_leader
        if last_election_time is not UNSET:
            field_dict["lastElectionTime"] = last_election_time
        if leader_http_address is not UNSET:
            field_dict["leaderHttpAddress"] = leader_http_address
        if leader_id is not UNSET:
            field_dict["leaderId"] = leader_id
        if leader_ready is not UNSET:
            field_dict["leaderReady"] = leader_ready
        if local_peer_id is not UNSET:
            field_dict["localPeerId"] = local_peer_id
        if peers is not UNSET:
            field_dict["peers"] = peers
        if raft_state is not UNSET:
            field_dict["raftState"] = raft_state
        if uptime is not UNSET:
            field_dict["uptime"] = uptime

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.cluster_status_alerts_item import ClusterStatusAlertsItem
        from ..models.cluster_status_database_presence import ClusterStatusDatabasePresence
        from ..models.cluster_status_databases_item import ClusterStatusDatabasesItem
        from ..models.cluster_status_peers_item import ClusterStatusPeersItem

        d = dict(src_dict)
        _alerts = d.pop("alerts", UNSET)
        alerts: list[ClusterStatusAlertsItem] | Unset = UNSET
        if _alerts is not UNSET:
            alerts = []
            for alerts_item_data in _alerts:
                alerts_item = ClusterStatusAlertsItem.from_dict(alerts_item_data)

                alerts.append(alerts_item)

        capabilities = cast(list[str], d.pop("capabilities", UNSET))

        cluster_name = d.pop("clusterName", UNSET)

        _database_presence = d.pop("databasePresence", UNSET)
        database_presence: ClusterStatusDatabasePresence | Unset
        if isinstance(_database_presence, Unset):
            database_presence = UNSET
        else:
            database_presence = ClusterStatusDatabasePresence.from_dict(_database_presence)

        _databases = d.pop("databases", UNSET)
        databases: list[ClusterStatusDatabasesItem] | Unset = UNSET
        if _databases is not UNSET:
            databases = []
            for databases_item_data in _databases:
                databases_item = ClusterStatusDatabasesItem.from_dict(databases_item_data)

                databases.append(databases_item)

        election_count = d.pop("electionCount", UNSET)

        implementation = d.pop("implementation", UNSET)

        is_leader = d.pop("isLeader", UNSET)

        last_election_time = d.pop("lastElectionTime", UNSET)

        def _parse_leader_http_address(data: object) -> str | Unset | None:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        leader_http_address = _parse_leader_http_address(d.pop("leaderHttpAddress", UNSET))

        def _parse_leader_id(data: object) -> str | Unset | None:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        leader_id = _parse_leader_id(d.pop("leaderId", UNSET))

        leader_ready = d.pop("leaderReady", UNSET)

        local_peer_id = d.pop("localPeerId", UNSET)

        _peers = d.pop("peers", UNSET)
        peers: list[ClusterStatusPeersItem] | Unset = UNSET
        if _peers is not UNSET:
            peers = []
            for peers_item_data in _peers:
                peers_item = ClusterStatusPeersItem.from_dict(peers_item_data)

                peers.append(peers_item)

        raft_state = d.pop("raftState", UNSET)

        uptime = d.pop("uptime", UNSET)

        cluster_status = cls(
            alerts=alerts,
            capabilities=capabilities,
            cluster_name=cluster_name,
            database_presence=database_presence,
            databases=databases,
            election_count=election_count,
            implementation=implementation,
            is_leader=is_leader,
            last_election_time=last_election_time,
            leader_http_address=leader_http_address,
            leader_id=leader_id,
            leader_ready=leader_ready,
            local_peer_id=local_peer_id,
            peers=peers,
            raft_state=raft_state,
            uptime=uptime,
        )

        cluster_status.additional_properties = d
        return cluster_status

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

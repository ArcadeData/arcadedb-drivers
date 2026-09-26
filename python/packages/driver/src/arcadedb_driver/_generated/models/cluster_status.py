from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.cluster_status_alerts_item import ClusterStatusAlertsItem
    from ..models.cluster_status_bootstrap_installs import ClusterStatusBootstrapInstalls
    from ..models.cluster_status_critical_halt_type_0 import ClusterStatusCriticalHaltType0
    from ..models.cluster_status_database_presence import ClusterStatusDatabasePresence
    from ..models.cluster_status_databases_item import ClusterStatusDatabasesItem
    from ..models.cluster_status_local_resync import ClusterStatusLocalResync
    from ..models.cluster_status_peers_item import ClusterStatusPeersItem
    from ..models.cluster_status_raft_log_failure_type_0 import ClusterStatusRaftLogFailureType0


T = TypeVar("T", bound="ClusterStatus")


@_attrs_define
class ClusterStatus:
    """Cluster and replication status

    Attributes:
        alerts (list[ClusterStatusAlertsItem]): Conditions worth an operator's attention. Empty when the cluster is
            healthy: an absent array is not a state this endpoint produces
        bootstrap_installs (ClusterStatusBootstrapInstalls): The databases this node is installing from the leader's
            first-formation bootstrap snapshot. Present on every answer. While an install replaces a copy this node already
            holds, '/api/v1/ready' answers 503: that copy is the one the cluster's committed baseline decided against. Not a
            resync, so 'localResync' does not reflect it; the 'bootstrap-install-in-progress' alert does.
        capabilities (list[str]): Optional wire-format sections THIS node can decode, sorted (issue #7219)
        cluster_name (str): Configured cluster name
        crash_loop_escalated (bool): True once the health monitor has given up restarting this node's HA layer (issue
            #7622), including an escalation a previous run of this node recorded next to its Raft storage. The liveness
            counterpart of the two above: an escalation raised in this process makes '/api/v1/health' answer unhealthy,
            once, so the process is restarted a single time; an inherited one does not (issue #7736).
        critical_halt (ClusterStatusCriticalHaltType0 | None): Why this node's replication state machine halted, or null
            while it is applying entries. Present on every answer. A non-null value means this node's databases are frozen
            at 'index' and will not advance again in this process: restart it.
        databases (list[ClusterStatusDatabasesItem]): Replicated databases
        election_count (int): Elections observed since start
        implementation (str): Always 'raft'
        is_leader (bool): True when this server is the leader
        last_election_time (int): Last election as epoch milliseconds
        leader_commit_index (int): The commit index this follower's leader last reported, learned by the health monitor
            over a follower-to-leader call every arcadedb.ha.healthCheckInterval. -1 on the leader and on a follower that
            has not learned one yet
        leader_http_address (None | str): Leader HTTP address, null when unknown
        leader_id (None | str): Current leader, null when unknown
        leader_ready (bool): True when the leader has finished the work that makes it safe to serve writes
        local_applied_index (int): Last Raft index this node has applied. -1 when the division cannot be read, e.g.
            during an in-place restart
        local_commit_index (int): Last Raft index this node knows to be committed. -1 under the same condition
        local_peer_id (str): This server's peer identifier
        local_replication_lag (int): Entries this node has yet to apply: 'localCommitIndex' minus 'localAppliedIndex'.
            -1 rather than a fabricated difference whenever either side is unknown
        local_resync (ClusterStatusLocalResync): This node's resync state. Present on every answer. The database names
            it carries are reduced to the ones the caller is authorized on, so a caller scoped to one database cannot learn
            another tenant's database name from a status poll.
        local_stalled_behind_leader (bool): True when this follower is more than arcadedb.ha.replicationLagWarning
            entries behind 'leaderCommitIndex' and has applied nothing and received no log entry for the grace the leader
            uses to report a replica STALLED. It does not count toward quorum while this is true, even though
            'localReplicationLag' can read 0. See the 'follower-stalled-behind-leader' alert for the operator-facing
            explanation
        local_stuck_at_stale_term (bool): True when this node recognizes a leader at a newer term but keeps rejecting
            its current-term entries although it has applied everything it could locally commit. It does not count toward
            quorum while this is true, even though 'localReplicationLag' reads 0. See the 'follower-stuck-at-stale-term'
            alert for the operator-facing explanation
        peers (list[ClusterStatusPeersItem]): Known peers
        raft_log_failure (ClusterStatusRaftLogFailureType0 | None): The persistent Raft log-write failure wedging this
            node, or null while the log writer is healthy. Present on every answer. A non-null value means Ratis is
            rejecting every append, so the node can neither catch up nor become caught up; the usual cause is a full Raft
            storage volume, and it clears by itself once the health monitor restarts the writer in place.
        raft_state (str): Raft lifecycle state
        uptime (int): Milliseconds since the Raft server started
        database_presence (ClusterStatusDatabasePresence | Unset): Which peer holds which database, keyed by database
            name. Present only when this server is the leader and the request set '?presence=true'.
    """

    alerts: list[ClusterStatusAlertsItem]
    bootstrap_installs: ClusterStatusBootstrapInstalls
    capabilities: list[str]
    cluster_name: str
    crash_loop_escalated: bool
    critical_halt: ClusterStatusCriticalHaltType0 | None
    databases: list[ClusterStatusDatabasesItem]
    election_count: int
    implementation: str
    is_leader: bool
    last_election_time: int
    leader_commit_index: int
    leader_http_address: str | None
    leader_id: str | None
    leader_ready: bool
    local_applied_index: int
    local_commit_index: int
    local_peer_id: str
    local_replication_lag: int
    local_resync: ClusterStatusLocalResync
    local_stalled_behind_leader: bool
    local_stuck_at_stale_term: bool
    peers: list[ClusterStatusPeersItem]
    raft_log_failure: ClusterStatusRaftLogFailureType0 | None
    raft_state: str
    uptime: int
    database_presence: ClusterStatusDatabasePresence | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.cluster_status_critical_halt_type_0 import ClusterStatusCriticalHaltType0
        from ..models.cluster_status_raft_log_failure_type_0 import ClusterStatusRaftLogFailureType0

        alerts = []
        for alerts_item_data in self.alerts:
            alerts_item = alerts_item_data.to_dict()
            alerts.append(alerts_item)

        bootstrap_installs = self.bootstrap_installs.to_dict()

        capabilities = self.capabilities

        cluster_name = self.cluster_name

        crash_loop_escalated = self.crash_loop_escalated

        critical_halt: dict[str, Any] | None
        if isinstance(self.critical_halt, ClusterStatusCriticalHaltType0):
            critical_halt = self.critical_halt.to_dict()
        else:
            critical_halt = self.critical_halt

        databases = []
        for databases_item_data in self.databases:
            databases_item = databases_item_data.to_dict()
            databases.append(databases_item)

        election_count = self.election_count

        implementation = self.implementation

        is_leader = self.is_leader

        last_election_time = self.last_election_time

        leader_commit_index = self.leader_commit_index

        leader_http_address: str | None
        leader_http_address = self.leader_http_address

        leader_id: str | None
        leader_id = self.leader_id

        leader_ready = self.leader_ready

        local_applied_index = self.local_applied_index

        local_commit_index = self.local_commit_index

        local_peer_id = self.local_peer_id

        local_replication_lag = self.local_replication_lag

        local_resync = self.local_resync.to_dict()

        local_stalled_behind_leader = self.local_stalled_behind_leader

        local_stuck_at_stale_term = self.local_stuck_at_stale_term

        peers = []
        for peers_item_data in self.peers:
            peers_item = peers_item_data.to_dict()
            peers.append(peers_item)

        raft_log_failure: dict[str, Any] | None
        if isinstance(self.raft_log_failure, ClusterStatusRaftLogFailureType0):
            raft_log_failure = self.raft_log_failure.to_dict()
        else:
            raft_log_failure = self.raft_log_failure

        raft_state = self.raft_state

        uptime = self.uptime

        database_presence: dict[str, Any] | Unset = UNSET
        if not isinstance(self.database_presence, Unset):
            database_presence = self.database_presence.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "alerts": alerts,
                "bootstrapInstalls": bootstrap_installs,
                "capabilities": capabilities,
                "clusterName": cluster_name,
                "crashLoopEscalated": crash_loop_escalated,
                "criticalHalt": critical_halt,
                "databases": databases,
                "electionCount": election_count,
                "implementation": implementation,
                "isLeader": is_leader,
                "lastElectionTime": last_election_time,
                "leaderCommitIndex": leader_commit_index,
                "leaderHttpAddress": leader_http_address,
                "leaderId": leader_id,
                "leaderReady": leader_ready,
                "localAppliedIndex": local_applied_index,
                "localCommitIndex": local_commit_index,
                "localPeerId": local_peer_id,
                "localReplicationLag": local_replication_lag,
                "localResync": local_resync,
                "localStalledBehindLeader": local_stalled_behind_leader,
                "localStuckAtStaleTerm": local_stuck_at_stale_term,
                "peers": peers,
                "raftLogFailure": raft_log_failure,
                "raftState": raft_state,
                "uptime": uptime,
            }
        )
        if database_presence is not UNSET:
            field_dict["databasePresence"] = database_presence

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.cluster_status_alerts_item import ClusterStatusAlertsItem
        from ..models.cluster_status_bootstrap_installs import ClusterStatusBootstrapInstalls
        from ..models.cluster_status_critical_halt_type_0 import ClusterStatusCriticalHaltType0
        from ..models.cluster_status_database_presence import ClusterStatusDatabasePresence
        from ..models.cluster_status_databases_item import ClusterStatusDatabasesItem
        from ..models.cluster_status_local_resync import ClusterStatusLocalResync
        from ..models.cluster_status_peers_item import ClusterStatusPeersItem
        from ..models.cluster_status_raft_log_failure_type_0 import ClusterStatusRaftLogFailureType0

        d = dict(src_dict)
        alerts = []
        _alerts = d.pop("alerts")
        for alerts_item_data in _alerts:
            alerts_item = ClusterStatusAlertsItem.from_dict(alerts_item_data)

            alerts.append(alerts_item)

        bootstrap_installs = ClusterStatusBootstrapInstalls.from_dict(d.pop("bootstrapInstalls"))

        capabilities = cast(list[str], d.pop("capabilities"))

        cluster_name = d.pop("clusterName")

        crash_loop_escalated = d.pop("crashLoopEscalated")

        def _parse_critical_halt(data: object) -> ClusterStatusCriticalHaltType0 | None:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                critical_halt_type_0 = ClusterStatusCriticalHaltType0.from_dict(data)

                return critical_halt_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ClusterStatusCriticalHaltType0 | None, data)

        critical_halt = _parse_critical_halt(d.pop("criticalHalt"))

        databases = []
        _databases = d.pop("databases")
        for databases_item_data in _databases:
            databases_item = ClusterStatusDatabasesItem.from_dict(databases_item_data)

            databases.append(databases_item)

        election_count = d.pop("electionCount")

        implementation = d.pop("implementation")

        is_leader = d.pop("isLeader")

        last_election_time = d.pop("lastElectionTime")

        leader_commit_index = d.pop("leaderCommitIndex")

        def _parse_leader_http_address(data: object) -> str | None:
            if data is None:
                return data
            return cast(None | str, data)

        leader_http_address = _parse_leader_http_address(d.pop("leaderHttpAddress"))

        def _parse_leader_id(data: object) -> str | None:
            if data is None:
                return data
            return cast(None | str, data)

        leader_id = _parse_leader_id(d.pop("leaderId"))

        leader_ready = d.pop("leaderReady")

        local_applied_index = d.pop("localAppliedIndex")

        local_commit_index = d.pop("localCommitIndex")

        local_peer_id = d.pop("localPeerId")

        local_replication_lag = d.pop("localReplicationLag")

        local_resync = ClusterStatusLocalResync.from_dict(d.pop("localResync"))

        local_stalled_behind_leader = d.pop("localStalledBehindLeader")

        local_stuck_at_stale_term = d.pop("localStuckAtStaleTerm")

        peers = []
        _peers = d.pop("peers")
        for peers_item_data in _peers:
            peers_item = ClusterStatusPeersItem.from_dict(peers_item_data)

            peers.append(peers_item)

        def _parse_raft_log_failure(data: object) -> ClusterStatusRaftLogFailureType0 | None:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                raft_log_failure_type_0 = ClusterStatusRaftLogFailureType0.from_dict(data)

                return raft_log_failure_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ClusterStatusRaftLogFailureType0 | None, data)

        raft_log_failure = _parse_raft_log_failure(d.pop("raftLogFailure"))

        raft_state = d.pop("raftState")

        uptime = d.pop("uptime")

        _database_presence = d.pop("databasePresence", UNSET)
        database_presence: ClusterStatusDatabasePresence | Unset
        if isinstance(_database_presence, Unset):
            database_presence = UNSET
        else:
            database_presence = ClusterStatusDatabasePresence.from_dict(_database_presence)

        cluster_status = cls(
            alerts=alerts,
            bootstrap_installs=bootstrap_installs,
            capabilities=capabilities,
            cluster_name=cluster_name,
            crash_loop_escalated=crash_loop_escalated,
            critical_halt=critical_halt,
            databases=databases,
            election_count=election_count,
            implementation=implementation,
            is_leader=is_leader,
            last_election_time=last_election_time,
            leader_commit_index=leader_commit_index,
            leader_http_address=leader_http_address,
            leader_id=leader_id,
            leader_ready=leader_ready,
            local_applied_index=local_applied_index,
            local_commit_index=local_commit_index,
            local_peer_id=local_peer_id,
            local_replication_lag=local_replication_lag,
            local_resync=local_resync,
            local_stalled_behind_leader=local_stalled_behind_leader,
            local_stuck_at_stale_term=local_stuck_at_stale_term,
            peers=peers,
            raft_log_failure=raft_log_failure,
            raft_state=raft_state,
            uptime=uptime,
            database_presence=database_presence,
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

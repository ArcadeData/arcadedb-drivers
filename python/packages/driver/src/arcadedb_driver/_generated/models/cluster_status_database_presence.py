from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.cluster_status_database_presence_databases_item import ClusterStatusDatabasePresenceDatabasesItem


T = TypeVar("T", bound="ClusterStatusDatabasePresence")


@_attrs_define
class ClusterStatusDatabasePresence:
    """Which node holds which database. Present only when this server is the leader and the request set '?presence=true'.

    Attributes:
        databases (list[ClusterStatusDatabasePresenceDatabasesItem] | Unset): One row per database held by any reachable
            node
        nodes (list[str] | Unset): Every peer this node knows: the server list reconciled with the live Raft
            configuration, so a peer that joined at runtime is one of them
        not_in_configuration (list[str] | Unset): Declared nodes the live Raft configuration does not hold: the leader
            does not replicate to them, so a database they lack is not a replication gap
        unreachable (list[str] | Unset): Nodes of 'nodes' that did not answer, left out of the present/missing
            accounting so a transient failure is not read as a missing database
    """

    databases: list[ClusterStatusDatabasePresenceDatabasesItem] | Unset = UNSET
    nodes: list[str] | Unset = UNSET
    not_in_configuration: list[str] | Unset = UNSET
    unreachable: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        databases: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.databases, Unset):
            databases = []
            for databases_item_data in self.databases:
                databases_item = databases_item_data.to_dict()
                databases.append(databases_item)

        nodes: list[str] | Unset = UNSET
        if not isinstance(self.nodes, Unset):
            nodes = self.nodes

        not_in_configuration: list[str] | Unset = UNSET
        if not isinstance(self.not_in_configuration, Unset):
            not_in_configuration = self.not_in_configuration

        unreachable: list[str] | Unset = UNSET
        if not isinstance(self.unreachable, Unset):
            unreachable = self.unreachable

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if databases is not UNSET:
            field_dict["databases"] = databases
        if nodes is not UNSET:
            field_dict["nodes"] = nodes
        if not_in_configuration is not UNSET:
            field_dict["notInConfiguration"] = not_in_configuration
        if unreachable is not UNSET:
            field_dict["unreachable"] = unreachable

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.cluster_status_database_presence_databases_item import ClusterStatusDatabasePresenceDatabasesItem

        d = dict(src_dict)
        _databases = d.pop("databases", UNSET)
        databases: list[ClusterStatusDatabasePresenceDatabasesItem] | Unset = UNSET
        if _databases is not UNSET:
            databases = []
            for databases_item_data in _databases:
                databases_item = ClusterStatusDatabasePresenceDatabasesItem.from_dict(databases_item_data)

                databases.append(databases_item)

        nodes = cast(list[str], d.pop("nodes", UNSET))

        not_in_configuration = cast(list[str], d.pop("notInConfiguration", UNSET))

        unreachable = cast(list[str], d.pop("unreachable", UNSET))

        cluster_status_database_presence = cls(
            databases=databases,
            nodes=nodes,
            not_in_configuration=not_in_configuration,
            unreachable=unreachable,
        )

        cluster_status_database_presence.additional_properties = d
        return cluster_status_database_presence

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

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
        database (str | Unset): Database the action applied to. Present on resync.
        leader_id (str | Unset): Leader after the action. Present on leadership transfer.
        local_server (str | Unset): Server that performed the action. Present on resync.
    """

    result: str
    database: str | Unset = UNSET
    leader_id: str | Unset = UNSET
    local_server: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = self.result

        database = self.database

        leader_id = self.leader_id

        local_server = self.local_server

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "result": result,
            }
        )
        if database is not UNSET:
            field_dict["database"] = database
        if leader_id is not UNSET:
            field_dict["leaderId"] = leader_id
        if local_server is not UNSET:
            field_dict["localServer"] = local_server

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        result = d.pop("result")

        database = d.pop("database", UNSET)

        leader_id = d.pop("leaderId", UNSET)

        local_server = d.pop("localServer", UNSET)

        cluster_action_response = cls(
            result=result,
            database=database,
            leader_id=leader_id,
            local_server=local_server,
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

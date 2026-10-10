from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ClusterStatusLocalInPlaceRestarts")


@_attrs_define
class ClusterStatusLocalInPlaceRestarts:
    """How many times this node's Raft layer has been restarted in place since the process started, by what happened to its
    Raft storage. Both counts only grow, and both start again from 0 when the process restarts. Also published as the
    'arcadedb.ha.in_place_restarts.recovered' and '.reformatted' metrics.

        Attributes:
            recovered (int): Restarts that kept the Raft log: the health monitor's recovery of a CLOSED or EXCEPTION
                division, for example after a long JVM pause
            reformatted (int): Restarts that discarded the Raft storage, after which the node is refilled from a leader
                snapshot: the divergence reformat. An increase outside a known divergence is worth investigating
    """

    recovered: int
    reformatted: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        recovered = self.recovered

        reformatted = self.reformatted

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "recovered": recovered,
                "reformatted": reformatted,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        recovered = d.pop("recovered")

        reformatted = d.pop("reformatted")

        cluster_status_local_in_place_restarts = cls(
            recovered=recovered,
            reformatted=reformatted,
        )

        cluster_status_local_in_place_restarts.additional_properties = d
        return cluster_status_local_in_place_restarts

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

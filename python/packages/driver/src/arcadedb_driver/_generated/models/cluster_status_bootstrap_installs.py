from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ClusterStatusBootstrapInstalls")


@_attrs_define
class ClusterStatusBootstrapInstalls:
    """The databases this node is installing from the leader's first-formation bootstrap snapshot. Present on every answer.
    While an install replaces a copy this node already holds, '/api/v1/ready' answers 503: that copy is the one the
    cluster's committed baseline decided against. Not a resync, so 'localResync' does not reflect it; the 'bootstrap-
    install-in-progress' alert does.

        Attributes:
            count (int): How many databases are being installed, before the authorization filter below
            databases (list[str]): The databases being installed, reduced to the ones the caller is authorized on
            in_progress (bool): True while at least one bootstrap install is running
    """

    count: int
    databases: list[str]
    in_progress: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        count = self.count

        databases = self.databases

        in_progress = self.in_progress

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "count": count,
                "databases": databases,
                "inProgress": in_progress,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        count = d.pop("count")

        databases = cast(list[str], d.pop("databases"))

        in_progress = d.pop("inProgress")

        cluster_status_bootstrap_installs = cls(
            count=count,
            databases=databases,
            in_progress=in_progress,
        )

        cluster_status_bootstrap_installs.additional_properties = d
        return cluster_status_bootstrap_installs

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

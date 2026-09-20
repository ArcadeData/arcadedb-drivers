from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.cluster_status_local_resync_divergence_causes_additional_property import (
    ClusterStatusLocalResyncDivergenceCausesAdditionalProperty,
)

T = TypeVar("T", bound="ClusterStatusLocalResyncDivergenceCauses")


@_attrs_define
class ClusterStatusLocalResyncDivergenceCauses:
    """Why each quarantined database was quarantined, keyed by database name. Same keys as 'divergedDatabases'"""

    additional_properties: dict[str, ClusterStatusLocalResyncDivergenceCausesAdditionalProperty] = _attrs_field(
        init=False, factory=dict
    )

    def to_dict(self) -> dict[str, Any]:

        field_dict: dict[str, Any] = {}
        for prop_name, prop in self.additional_properties.items():
            field_dict[prop_name] = prop.value

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        cluster_status_local_resync_divergence_causes = cls()

        additional_properties = {}
        for prop_name, prop_dict in d.items():
            additional_property = ClusterStatusLocalResyncDivergenceCausesAdditionalProperty(prop_dict)

            additional_properties[prop_name] = additional_property

        cluster_status_local_resync_divergence_causes.additional_properties = additional_properties
        return cluster_status_local_resync_divergence_causes

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> ClusterStatusLocalResyncDivergenceCausesAdditionalProperty:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: ClusterStatusLocalResyncDivergenceCausesAdditionalProperty) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties

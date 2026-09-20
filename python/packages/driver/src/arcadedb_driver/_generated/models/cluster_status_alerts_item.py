from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.cluster_status_alerts_item_severity import ClusterStatusAlertsItemSeverity

if TYPE_CHECKING:
    from ..models.cluster_status_alerts_item_details import ClusterStatusAlertsItemDetails


T = TypeVar("T", bound="ClusterStatusAlertsItem")


@_attrs_define
class ClusterStatusAlertsItem:
    """One cluster alert

    Attributes:
        details (ClusterStatusAlertsItemDetails): The condition's own data - the peers involved, the databases behind,
            the lag figures. An open map because each 'id' carries its own keys; read it against the 'id', not blind.
        id (str): Stable identifier of the condition, e.g. 'lagging-followers' or 'local-resync-in-progress'. Key a
            monitoring rule on this rather than on 'title', which is prose and may be reworded.
        message (str): What is wrong, in full sentences
        recommendation (str): What an operator should do about it
        severity (ClusterStatusAlertsItemSeverity): How urgent the condition is. 'critical' means this node or the
            cluster is not serving correctly right now, 'warning' that it will not keep serving correctly, 'info' that a
            declared configuration and the live one differ without consequence yet.
        title (str): One line naming the condition, for a dashboard row
    """

    details: ClusterStatusAlertsItemDetails
    id: str
    message: str
    recommendation: str
    severity: ClusterStatusAlertsItemSeverity
    title: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        details = self.details.to_dict()

        id = self.id

        message = self.message

        recommendation = self.recommendation

        severity = self.severity.value

        title = self.title

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "details": details,
                "id": id,
                "message": message,
                "recommendation": recommendation,
                "severity": severity,
                "title": title,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.cluster_status_alerts_item_details import ClusterStatusAlertsItemDetails

        d = dict(src_dict)
        details = ClusterStatusAlertsItemDetails.from_dict(d.pop("details"))

        id = d.pop("id")

        message = d.pop("message")

        recommendation = d.pop("recommendation")

        severity = ClusterStatusAlertsItemSeverity(d.pop("severity"))

        title = d.pop("title")

        cluster_status_alerts_item = cls(
            details=details,
            id=id,
            message=message,
            recommendation=recommendation,
            severity=severity,
            title=title,
        )

        cluster_status_alerts_item.additional_properties = d
        return cluster_status_alerts_item

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

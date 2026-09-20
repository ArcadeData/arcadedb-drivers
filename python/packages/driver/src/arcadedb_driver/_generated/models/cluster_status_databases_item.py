from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ClusterStatusDatabasesItem")


@_attrs_define
class ClusterStatusDatabasesItem:
    """One database's cluster state

    Attributes:
        name (str): Database name
        acquire_error (str | Unset): Why the last acquisition failed. Absent on success.
        acquire_status (str | Unset): State of the last acquisition attempt. Absent when none was made.
        acquire_timestamp (int | Unset): When the last acquisition attempt ran, as epoch milliseconds. Absent when none
            was made.
        bootstrap_fingerprint (str | Unset): Fingerprint recorded at bootstrap. Absent when no baseline exists.
        bootstrap_last_tx_id (int | Unset): Last transaction id recorded at bootstrap. Absent when no baseline exists.
    """

    name: str
    acquire_error: str | Unset = UNSET
    acquire_status: str | Unset = UNSET
    acquire_timestamp: int | Unset = UNSET
    bootstrap_fingerprint: str | Unset = UNSET
    bootstrap_last_tx_id: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        acquire_error = self.acquire_error

        acquire_status = self.acquire_status

        acquire_timestamp = self.acquire_timestamp

        bootstrap_fingerprint = self.bootstrap_fingerprint

        bootstrap_last_tx_id = self.bootstrap_last_tx_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
            }
        )
        if acquire_error is not UNSET:
            field_dict["acquireError"] = acquire_error
        if acquire_status is not UNSET:
            field_dict["acquireStatus"] = acquire_status
        if acquire_timestamp is not UNSET:
            field_dict["acquireTimestamp"] = acquire_timestamp
        if bootstrap_fingerprint is not UNSET:
            field_dict["bootstrapFingerprint"] = bootstrap_fingerprint
        if bootstrap_last_tx_id is not UNSET:
            field_dict["bootstrapLastTxId"] = bootstrap_last_tx_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        acquire_error = d.pop("acquireError", UNSET)

        acquire_status = d.pop("acquireStatus", UNSET)

        acquire_timestamp = d.pop("acquireTimestamp", UNSET)

        bootstrap_fingerprint = d.pop("bootstrapFingerprint", UNSET)

        bootstrap_last_tx_id = d.pop("bootstrapLastTxId", UNSET)

        cluster_status_databases_item = cls(
            name=name,
            acquire_error=acquire_error,
            acquire_status=acquire_status,
            acquire_timestamp=acquire_timestamp,
            bootstrap_fingerprint=bootstrap_fingerprint,
            bootstrap_last_tx_id=bootstrap_last_tx_id,
        )

        cluster_status_databases_item.additional_properties = d
        return cluster_status_databases_item

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

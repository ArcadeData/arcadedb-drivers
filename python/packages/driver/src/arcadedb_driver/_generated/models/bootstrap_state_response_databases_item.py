from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="BootstrapStateResponseDatabasesItem")


@_attrs_define
class BootstrapStateResponseDatabasesItem:
    """One database's bootstrap state

    Attributes:
        fingerprint (str): Content fingerprint, empty when the database could not be read
        last_tx_id (int): Last transaction id, -1 when the database could not be read
        name (str): Database name
        error (str | Unset): Why the database could not be read. Absent on success.
    """

    fingerprint: str
    last_tx_id: int
    name: str
    error: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        fingerprint = self.fingerprint

        last_tx_id = self.last_tx_id

        name = self.name

        error = self.error

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "fingerprint": fingerprint,
                "lastTxId": last_tx_id,
                "name": name,
            }
        )
        if error is not UNSET:
            field_dict["error"] = error

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        fingerprint = d.pop("fingerprint")

        last_tx_id = d.pop("lastTxId")

        name = d.pop("name")

        error = d.pop("error", UNSET)

        bootstrap_state_response_databases_item = cls(
            fingerprint=fingerprint,
            last_tx_id=last_tx_id,
            name=name,
            error=error,
        )

        bootstrap_state_response_databases_item.additional_properties = d
        return bootstrap_state_response_databases_item

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

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.begin_request_isolation_level import BeginRequestIsolationLevel
from ..types import UNSET, Unset

T = TypeVar("T", bound="BeginRequest")


@_attrs_define
class BeginRequest:
    """Begin transaction request object

    Attributes:
        isolation_level (BeginRequestIsolationLevel | Unset): Isolation level of the transaction. Optional: when absent
            the transaction runs at the database's default isolation level. The value is case-sensitive, and any other value
            is refused with 400.
    """

    isolation_level: BeginRequestIsolationLevel | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        isolation_level: str | Unset = UNSET
        if not isinstance(self.isolation_level, Unset):
            isolation_level = self.isolation_level.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if isolation_level is not UNSET:
            field_dict["isolationLevel"] = isolation_level

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        _isolation_level = d.pop("isolationLevel", UNSET)
        isolation_level: BeginRequestIsolationLevel | Unset
        if isinstance(_isolation_level, Unset):
            isolation_level = UNSET
        else:
            isolation_level = BeginRequestIsolationLevel(_isolation_level)

        begin_request = cls(
            isolation_level=isolation_level,
        )

        begin_request.additional_properties = d
        return begin_request

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

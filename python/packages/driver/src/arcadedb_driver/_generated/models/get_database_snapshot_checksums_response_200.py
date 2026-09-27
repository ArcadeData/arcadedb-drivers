from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="GetDatabaseSnapshotChecksumsResponse200")


@_attrs_define
class GetDatabaseSnapshotChecksumsResponse200:
    """File name to checksum

    Attributes:
        unreadable_files (list[str] | Unset): Files listed in the database directory that were gone by the time this
            answer tried to read them, so it does not cover them. Absent when the answer is complete.
    """

    unreadable_files: list[str] | Unset = UNSET
    additional_properties: dict[str, int] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        unreadable_files: list[str] | Unset = UNSET
        if not isinstance(self.unreadable_files, Unset):
            unreadable_files = self.unreadable_files

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if unreadable_files is not UNSET:
            field_dict["/unreadableFiles"] = unreadable_files

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        unreadable_files = cast(list[str], d.pop("/unreadableFiles", UNSET))

        get_database_snapshot_checksums_response_200 = cls(
            unreadable_files=unreadable_files,
        )

        get_database_snapshot_checksums_response_200.additional_properties = d
        return get_database_snapshot_checksums_response_200

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> int:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: int) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties

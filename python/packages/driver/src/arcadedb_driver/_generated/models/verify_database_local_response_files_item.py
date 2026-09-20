from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="VerifyDatabaseLocalResponseFilesItem")


@_attrs_define
class VerifyDatabaseLocalResponseFilesItem:
    """One database file

    Attributes:
        checksum (int): CRC of the file's contents
        name (str): File name
        size (int): File size in bytes
        type_ (str): File category
    """

    checksum: int
    name: str
    size: int
    type_: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        checksum = self.checksum

        name = self.name

        size = self.size

        type_ = self.type_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "checksum": checksum,
                "name": name,
                "size": size,
                "type": type_,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        checksum = d.pop("checksum")

        name = d.pop("name")

        size = d.pop("size")

        type_ = d.pop("type")

        verify_database_local_response_files_item = cls(
            checksum=checksum,
            name=name,
            size=size,
            type_=type_,
        )

        verify_database_local_response_files_item.additional_properties = d
        return verify_database_local_response_files_item

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

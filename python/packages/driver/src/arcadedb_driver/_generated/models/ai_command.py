from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AiCommand")


@_attrs_define
class AiCommand:
    """One command the assistant proposes. Proposed only: the server never runs it, the caller does

    Attributes:
        command (str): The statement text
        language (str | Unset): Query language the statement is written in. Treated as 'sql' when absent
        purpose (str | Unset): One line saying what the statement is for, shown above it. Absent when the assistant gave
            none
    """

    command: str
    language: str | Unset = UNSET
    purpose: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        command = self.command

        language = self.language

        purpose = self.purpose

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "command": command,
            }
        )
        if language is not UNSET:
            field_dict["language"] = language
        if purpose is not UNSET:
            field_dict["purpose"] = purpose

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        command = d.pop("command")

        language = d.pop("language", UNSET)

        purpose = d.pop("purpose", UNSET)

        ai_command = cls(
            command=command,
            language=language,
            purpose=purpose,
        )

        ai_command.additional_properties = d
        return ai_command

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

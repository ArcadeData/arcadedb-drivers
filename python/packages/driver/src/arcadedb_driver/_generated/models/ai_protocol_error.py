from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AiProtocolError")


@_attrs_define
class AiProtocolError:
    """Rejected chat request. Carries the negotiation fields when the protocol version is at fault.

    Attributes:
        error (str): Why the request was rejected
        code (str | Unset): Machine-readable cause, 'protocol_unsupported' for a version mismatch
        current_protocol_version (int | Unset): Protocol version this server prefers
        supported_protocol_versions (list[int] | Unset): Every version this server accepts
    """

    error: str
    code: str | Unset = UNSET
    current_protocol_version: int | Unset = UNSET
    supported_protocol_versions: list[int] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        error = self.error

        code = self.code

        current_protocol_version = self.current_protocol_version

        supported_protocol_versions: list[int] | Unset = UNSET
        if not isinstance(self.supported_protocol_versions, Unset):
            supported_protocol_versions = self.supported_protocol_versions

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "error": error,
            }
        )
        if code is not UNSET:
            field_dict["code"] = code
        if current_protocol_version is not UNSET:
            field_dict["currentProtocolVersion"] = current_protocol_version
        if supported_protocol_versions is not UNSET:
            field_dict["supportedProtocolVersions"] = supported_protocol_versions

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        error = d.pop("error")

        code = d.pop("code", UNSET)

        current_protocol_version = d.pop("currentProtocolVersion", UNSET)

        supported_protocol_versions = cast(list[int], d.pop("supportedProtocolVersions", UNSET))

        ai_protocol_error = cls(
            error=error,
            code=code,
            current_protocol_version=current_protocol_version,
            supported_protocol_versions=supported_protocol_versions,
        )

        ai_protocol_error.additional_properties = d
        return ai_protocol_error

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

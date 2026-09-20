from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="JsonRpcMessageType0Error")


@_attrs_define
class JsonRpcMessageType0Error:
    """A JSON-RPC error, on a failed response

    Attributes:
        code (int): JSON-RPC error code
        message (str): Short description of the error
        data (Any | Unset): Further detail, when the method provides any
    """

    code: int
    message: str
    data: Any | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        code = self.code

        message = self.message

        data = self.data

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "code": code,
                "message": message,
            }
        )
        if data is not UNSET:
            field_dict["data"] = data

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        code = d.pop("code")

        message = d.pop("message")

        data = d.pop("data", UNSET)

        json_rpc_message_type_0_error = cls(
            code=code,
            message=message,
            data=data,
        )

        json_rpc_message_type_0_error.additional_properties = d
        return json_rpc_message_type_0_error

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

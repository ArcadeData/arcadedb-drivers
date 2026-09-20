from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.prom_ql_error_response_status import PromQLErrorResponseStatus

T = TypeVar("T", bound="PromQLErrorResponse")


@_attrs_define
class PromQLErrorResponse:
    """Prometheus error envelope

    Attributes:
        error (str): Human-readable message
        error_type (str): Prometheus error class, for example 'bad_data'
        status (PromQLErrorResponseStatus): Always 'error'
    """

    error: str
    error_type: str
    status: PromQLErrorResponseStatus
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        error = self.error

        error_type = self.error_type

        status = self.status.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "error": error,
                "errorType": error_type,
                "status": status,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        error = d.pop("error")

        error_type = d.pop("errorType")

        status = PromQLErrorResponseStatus(d.pop("status"))

        prom_ql_error_response = cls(
            error=error,
            error_type=error_type,
            status=status,
        )

        prom_ql_error_response.additional_properties = d
        return prom_ql_error_response

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

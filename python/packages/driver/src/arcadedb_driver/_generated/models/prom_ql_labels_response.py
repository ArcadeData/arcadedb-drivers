from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.prom_ql_labels_response_status import PromQLLabelsResponseStatus

T = TypeVar("T", bound="PromQLLabelsResponse")


@_attrs_define
class PromQLLabelsResponse:
    """Prometheus label response

    Attributes:
        data (list[str]): Sorted names or values. Empty when nothing matched
        status (PromQLLabelsResponseStatus): Always 'success' on a 200. The error envelope carries 'error' here instead
    """

    data: list[str]
    status: PromQLLabelsResponseStatus
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = self.data

        status = self.status.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "data": data,
                "status": status,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        data = cast(list[str], d.pop("data"))

        status = PromQLLabelsResponseStatus(d.pop("status"))

        prom_ql_labels_response = cls(
            data=data,
            status=status,
        )

        prom_ql_labels_response.additional_properties = d
        return prom_ql_labels_response

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

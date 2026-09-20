from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.prom_ql_series_response_status import PromQLSeriesResponseStatus

if TYPE_CHECKING:
    from ..models.prom_ql_series_response_data_item import PromQLSeriesResponseDataItem


T = TypeVar("T", bound="PromQLSeriesResponse")


@_attrs_define
class PromQLSeriesResponse:
    """Prometheus series response

    Attributes:
        data (list[PromQLSeriesResponseDataItem]): Matching series. Empty when nothing matched
        status (PromQLSeriesResponseStatus): Always 'success' on a 200. The error envelope carries 'error' here instead
    """

    data: list[PromQLSeriesResponseDataItem]
    status: PromQLSeriesResponseStatus
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = []
        for data_item_data in self.data:
            data_item = data_item_data.to_dict()
            data.append(data_item)

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
        from ..models.prom_ql_series_response_data_item import PromQLSeriesResponseDataItem

        d = dict(src_dict)
        data = []
        _data = d.pop("data")
        for data_item_data in _data:
            data_item = PromQLSeriesResponseDataItem.from_dict(data_item_data)

            data.append(data_item)

        status = PromQLSeriesResponseStatus(d.pop("status"))

        prom_ql_series_response = cls(
            data=data,
            status=status,
        )

        prom_ql_series_response.additional_properties = d
        return prom_ql_series_response

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

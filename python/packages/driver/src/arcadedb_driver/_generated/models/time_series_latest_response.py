from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="TimeSeriesLatestResponse")


@_attrs_define
class TimeSeriesLatestResponse:
    """Most recent sample of a series

    Attributes:
        columns (list[str]): Column names, in sample value order
        latest (list[Any] | None): Most recent sample, positionally aligned with 'columns'. Null when the series is
            empty.
        type_ (str): Time-series type name
    """

    columns: list[str]
    latest: list[Any] | None
    type_: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        columns = self.columns

        latest: list[Any] | None
        if isinstance(self.latest, list):
            latest = self.latest

        else:
            latest = self.latest

        type_ = self.type_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "columns": columns,
                "latest": latest,
                "type": type_,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        columns = cast(list[str], d.pop("columns"))

        def _parse_latest(data: object) -> list[Any] | None:
            if data is None:
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                latest_type_0 = cast(list[Any], data)

                return latest_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[Any] | None, data)

        latest = _parse_latest(d.pop("latest"))

        type_ = d.pop("type")

        time_series_latest_response = cls(
            columns=columns,
            latest=latest,
            type_=type_,
        )

        time_series_latest_response.additional_properties = d
        return time_series_latest_response

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

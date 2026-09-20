from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="TimeSeriesRawResponse")


@_attrs_define
class TimeSeriesRawResponse:
    """Raw samples

    Attributes:
        columns (list[str]): Column names, in the order the row values appear
        count (int): Number of rows returned
        rows (list[list[Any]]): Rows, each positionally aligned with 'columns'
        type_ (str): Time-series type name
    """

    columns: list[str]
    count: int
    rows: list[list[Any]]
    type_: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        columns = self.columns

        count = self.count

        rows = []
        for rows_item_data in self.rows:
            rows_item = rows_item_data

            rows.append(rows_item)

        type_ = self.type_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "columns": columns,
                "count": count,
                "rows": rows,
                "type": type_,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        columns = cast(list[str], d.pop("columns"))

        count = d.pop("count")

        rows = []
        _rows = d.pop("rows")
        for rows_item_data in _rows:
            rows_item = cast(list[Any], rows_item_data)

            rows.append(rows_item)

        type_ = d.pop("type")

        time_series_raw_response = cls(
            columns=columns,
            count=count,
            rows=rows,
            type_=type_,
        )

        time_series_raw_response.additional_properties = d
        return time_series_raw_response

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

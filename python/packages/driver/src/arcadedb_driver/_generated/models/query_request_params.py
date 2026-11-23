from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="QueryRequestParams")


@_attrs_define
class QueryRequestParams:
    """Query parameters. Values may be JSON primitives, arrays, or typed-marker objects: {"$bytes": "<base64>"} for byte[]
    (standard or URL-safe base64), {"$int8": [v0, v1, ...]} for byte[] from integers in [-128, 127] (used to send
    INT8-encoded vectors to LSM_VECTOR indexes without a float32 round-trip), {"$date": "2024-01-15"} for a DATE,
    {"$rid": "#12:0"} for a link to a record rather than its text, {"$decimal": "0.10"} for a DECIMAL with its scale
    kept rather than a double, {"$datetime": 1700000000123} for a DATETIME from epoch milliseconds, {"$localDateTime":
    "2024-02-29T13:14:15"}, {"$instant": "2023-11-14T22:13:20.123Z"} and {"$zonedDateTime":
    "2024-01-01T10:00:00+01:00[Europe/Rome]"} for the date-time types, as ISO-8601 text. A marker that does not decode,
    or a '$decimal' beyond the limits of a JSON number (1000 characters, an exponent up to 1000), is refused with 400
    before the statement runs.

    """

    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        query_request_params = cls()

        query_request_params.additional_properties = d
        return query_request_params

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

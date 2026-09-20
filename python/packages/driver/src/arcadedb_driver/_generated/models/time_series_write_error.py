from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="TimeSeriesWriteError")


@_attrs_define
class TimeSeriesWriteError:
    """Rejected ingestion, with partial counts

    Attributes:
        dropped (int): Samples discarded
        error (str): Why the request was rejected
        written (int): Samples successfully ingested
        non_time_series_types (list[str] | Unset): Measurements naming a type that exists but is not a time-series type
        request_id (str | Unset): Correlation id echoing X-Request-Id, for matching against server logs
        unavailable_types (list[str] | Unset): Measurements naming a time-series type whose storage engine failed to
            load; see the server log for why
        unknown_types (list[str] | Unset): Measurements naming a type that does not exist
    """

    dropped: int
    error: str
    written: int
    non_time_series_types: list[str] | Unset = UNSET
    request_id: str | Unset = UNSET
    unavailable_types: list[str] | Unset = UNSET
    unknown_types: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        dropped = self.dropped

        error = self.error

        written = self.written

        non_time_series_types: list[str] | Unset = UNSET
        if not isinstance(self.non_time_series_types, Unset):
            non_time_series_types = self.non_time_series_types

        request_id = self.request_id

        unavailable_types: list[str] | Unset = UNSET
        if not isinstance(self.unavailable_types, Unset):
            unavailable_types = self.unavailable_types

        unknown_types: list[str] | Unset = UNSET
        if not isinstance(self.unknown_types, Unset):
            unknown_types = self.unknown_types

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "dropped": dropped,
                "error": error,
                "written": written,
            }
        )
        if non_time_series_types is not UNSET:
            field_dict["nonTimeSeriesTypes"] = non_time_series_types
        if request_id is not UNSET:
            field_dict["requestId"] = request_id
        if unavailable_types is not UNSET:
            field_dict["unavailableTypes"] = unavailable_types
        if unknown_types is not UNSET:
            field_dict["unknownTypes"] = unknown_types

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        dropped = d.pop("dropped")

        error = d.pop("error")

        written = d.pop("written")

        non_time_series_types = cast(list[str], d.pop("nonTimeSeriesTypes", UNSET))

        request_id = d.pop("requestId", UNSET)

        unavailable_types = cast(list[str], d.pop("unavailableTypes", UNSET))

        unknown_types = cast(list[str], d.pop("unknownTypes", UNSET))

        time_series_write_error = cls(
            dropped=dropped,
            error=error,
            written=written,
            non_time_series_types=non_time_series_types,
            request_id=request_id,
            unavailable_types=unavailable_types,
            unknown_types=unknown_types,
        )

        time_series_write_error.additional_properties = d
        return time_series_write_error

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

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.nd_json_query_event_error import NdJsonQueryEventError
    from ..models.nd_json_query_event_record import NdJsonQueryEventRecord
    from ..models.nd_json_query_event_stats import NdJsonQueryEventStats


T = TypeVar("T", bound="NdJsonQueryEvent")


@_attrs_define
class NdJsonQueryEvent:
    """One line of a newline-delimited streaming response. Exactly one of 'record', 'stats' or 'error' is present.

    Attributes:
        error (NdJsonQueryEventError | Unset): A failure raised after the 200 had already been sent. The status code
            cannot be taken back at that point, so the failure is reported in band and no 'stats' line follows.
        record (NdJsonQueryEventRecord | Unset): One result row, identical to an element of the 'result' array of the
            buffered application/json response.
        stats (NdJsonQueryEventStats | Unset): Trailer, always the last line of a complete stream. Carries the same
            three numbers the buffered response reports at top level.
    """

    error: NdJsonQueryEventError | Unset = UNSET
    record: NdJsonQueryEventRecord | Unset = UNSET
    stats: NdJsonQueryEventStats | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        error: dict[str, Any] | Unset = UNSET
        if not isinstance(self.error, Unset):
            error = self.error.to_dict()

        record: dict[str, Any] | Unset = UNSET
        if not isinstance(self.record, Unset):
            record = self.record.to_dict()

        stats: dict[str, Any] | Unset = UNSET
        if not isinstance(self.stats, Unset):
            stats = self.stats.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if error is not UNSET:
            field_dict["error"] = error
        if record is not UNSET:
            field_dict["record"] = record
        if stats is not UNSET:
            field_dict["stats"] = stats

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.nd_json_query_event_error import NdJsonQueryEventError
        from ..models.nd_json_query_event_record import NdJsonQueryEventRecord
        from ..models.nd_json_query_event_stats import NdJsonQueryEventStats

        d = dict(src_dict)
        _error = d.pop("error", UNSET)
        error: NdJsonQueryEventError | Unset
        if isinstance(_error, Unset):
            error = UNSET
        else:
            error = NdJsonQueryEventError.from_dict(_error)

        _record = d.pop("record", UNSET)
        record: NdJsonQueryEventRecord | Unset
        if isinstance(_record, Unset):
            record = UNSET
        else:
            record = NdJsonQueryEventRecord.from_dict(_record)

        _stats = d.pop("stats", UNSET)
        stats: NdJsonQueryEventStats | Unset
        if isinstance(_stats, Unset):
            stats = UNSET
        else:
            stats = NdJsonQueryEventStats.from_dict(_stats)

        nd_json_query_event = cls(
            error=error,
            record=record,
            stats=stats,
        )

        nd_json_query_event.additional_properties = d
        return nd_json_query_event

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

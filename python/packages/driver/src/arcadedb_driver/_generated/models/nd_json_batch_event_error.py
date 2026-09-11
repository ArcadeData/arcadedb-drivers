from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="NdJsonBatchEventError")


@_attrs_define
class NdJsonBatchEventError:
    """Terminal line of a failed load: the same object the buffered encoding carries, plus the 'status' it would have been
    sent under. The status line cannot be taken back once the stream has started, so the status travels in band.

        Attributes:
            commit_index (int | Unset): Last applied Raft index, present on a replicated database. On a failed load it
                bookmarks the chunks that were committed before the failure
            status (int | Unset): HTTP status the buffered encoding would have used: 400, 408 or 500
            status_mapped (bool | Unset): Present and false when 'status' is the unclassified 500 fallback rather than the
                status the buffered encoding would have chosen - the case of an engine failure raised after the stream had
                already started. Key on 'exception' there, not on 'status'. Absent whenever 'status' is exact.
    """

    commit_index: int | Unset = UNSET
    status: int | Unset = UNSET
    status_mapped: bool | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        commit_index = self.commit_index

        status = self.status

        status_mapped = self.status_mapped

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if commit_index is not UNSET:
            field_dict["commitIndex"] = commit_index
        if status is not UNSET:
            field_dict["status"] = status
        if status_mapped is not UNSET:
            field_dict["statusMapped"] = status_mapped

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        commit_index = d.pop("commitIndex", UNSET)

        status = d.pop("status", UNSET)

        status_mapped = d.pop("statusMapped", UNSET)

        nd_json_batch_event_error = cls(
            commit_index=commit_index,
            status=status,
            status_mapped=status_mapped,
        )

        nd_json_batch_event_error.additional_properties = d
        return nd_json_batch_event_error

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

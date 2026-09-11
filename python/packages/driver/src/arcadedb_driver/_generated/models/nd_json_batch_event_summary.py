from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="NdJsonBatchEventSummary")


@_attrs_define
class NdJsonBatchEventSummary:
    """Terminal line of a successful load: the same object the buffered application/json response carries, plus
    'commitIndex' on a replicated database - the read-your-writes bookmark, which cannot be a response header here
    because the response has already started when its value becomes known.

        Attributes:
            commit_index (int | Unset): Last applied Raft index, the value the X-ArcadeDB-Commit-Index header carries on the
                buffered encoding
            id_mapping_size (int | Unset): Total number of temporary ids the load resolved. Check the number of mapping
                entries received across all the lines against it: a mapping that arrives in pieces can lose one to a truncated
                response without any single piece looking wrong.
            id_mapping_streamed (bool | Unset): Always true on this encoding when the load resolved any temporary id: the
                mapping travelled in the 'idMapping' of the progress lines rather than in this object, so 'idMapping' here is
                only whatever the last chunk resolved after the final acknowledgement - usually nothing. 'idMappingOmitted' is
                never sent on this encoding: the size cap it reports exists because the buffered encoding has to build the whole
                mapping before it can send anything, which streaming removes (issue #7353).
    """

    commit_index: int | Unset = UNSET
    id_mapping_size: int | Unset = UNSET
    id_mapping_streamed: bool | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        commit_index = self.commit_index

        id_mapping_size = self.id_mapping_size

        id_mapping_streamed = self.id_mapping_streamed

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if commit_index is not UNSET:
            field_dict["commitIndex"] = commit_index
        if id_mapping_size is not UNSET:
            field_dict["idMappingSize"] = id_mapping_size
        if id_mapping_streamed is not UNSET:
            field_dict["idMappingStreamed"] = id_mapping_streamed

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        commit_index = d.pop("commitIndex", UNSET)

        id_mapping_size = d.pop("idMappingSize", UNSET)

        id_mapping_streamed = d.pop("idMappingStreamed", UNSET)

        nd_json_batch_event_summary = cls(
            commit_index=commit_index,
            id_mapping_size=id_mapping_size,
            id_mapping_streamed=id_mapping_streamed,
        )

        nd_json_batch_event_summary.additional_properties = d
        return nd_json_batch_event_summary

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

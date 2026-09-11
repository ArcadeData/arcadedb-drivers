from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.nd_json_batch_event_error import NdJsonBatchEventError
    from ..models.nd_json_batch_event_progress import NdJsonBatchEventProgress
    from ..models.nd_json_batch_event_summary import NdJsonBatchEventSummary


T = TypeVar("T", bound="NdJsonBatchEvent")


@_attrs_define
class NdJsonBatchEvent:
    """One line of a streamed bulk load. Exactly one of 'progress', 'summary' or 'error' is present.

    Attributes:
        error (NdJsonBatchEventError | Unset): Terminal line of a failed load: the same object the buffered encoding
            carries, plus the 'status' it would have been sent under. The status line cannot be taken back once the stream
            has started, so the status travels in band.
        progress (NdJsonBatchEventProgress | Unset): A chunk acknowledgement, written while the request body is still
            being read. Emitted at every vertex commit and every 'commitEvery' edges. The counters are records ATTEMPTED,
            the same upper bound on what is durable that the partial-commit counters carry: vertices are committed at each
            flush, while edges are buffered and written when the load ends.
        summary (NdJsonBatchEventSummary | Unset): Terminal line of a successful load: the same object the buffered
            application/json response carries, plus 'commitIndex' on a replicated database - the read-your-writes bookmark,
            which cannot be a response header here because the response has already started when its value becomes known.
    """

    error: NdJsonBatchEventError | Unset = UNSET
    progress: NdJsonBatchEventProgress | Unset = UNSET
    summary: NdJsonBatchEventSummary | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        error: dict[str, Any] | Unset = UNSET
        if not isinstance(self.error, Unset):
            error = self.error.to_dict()

        progress: dict[str, Any] | Unset = UNSET
        if not isinstance(self.progress, Unset):
            progress = self.progress.to_dict()

        summary: dict[str, Any] | Unset = UNSET
        if not isinstance(self.summary, Unset):
            summary = self.summary.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if error is not UNSET:
            field_dict["error"] = error
        if progress is not UNSET:
            field_dict["progress"] = progress
        if summary is not UNSET:
            field_dict["summary"] = summary

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.nd_json_batch_event_error import NdJsonBatchEventError
        from ..models.nd_json_batch_event_progress import NdJsonBatchEventProgress
        from ..models.nd_json_batch_event_summary import NdJsonBatchEventSummary

        d = dict(src_dict)
        _error = d.pop("error", UNSET)
        error: NdJsonBatchEventError | Unset
        if isinstance(_error, Unset):
            error = UNSET
        else:
            error = NdJsonBatchEventError.from_dict(_error)

        _progress = d.pop("progress", UNSET)
        progress: NdJsonBatchEventProgress | Unset
        if isinstance(_progress, Unset):
            progress = UNSET
        else:
            progress = NdJsonBatchEventProgress.from_dict(_progress)

        _summary = d.pop("summary", UNSET)
        summary: NdJsonBatchEventSummary | Unset
        if isinstance(_summary, Unset):
            summary = UNSET
        else:
            summary = NdJsonBatchEventSummary.from_dict(_summary)

        nd_json_batch_event = cls(
            error=error,
            progress=progress,
            summary=summary,
        )

        nd_json_batch_event.additional_properties = d
        return nd_json_batch_event

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

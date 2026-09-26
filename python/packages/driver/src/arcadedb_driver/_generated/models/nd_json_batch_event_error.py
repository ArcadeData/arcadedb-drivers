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
            exception_args (str | Unset): Structured arguments of the failure, as the buffered error body carries them:
                present only for a failure that has any, e.g. 'index|keys|rid' for a duplicated key.
            status (int | Unset): HTTP status the buffered encoding would have used for the same failure - 400 or 408 for a
                malformed or truncated body, and for an engine failure raised after the stream started the status the standard
                error mapping gives it: 409 for a duplicated key, 503 for a retryable conflict, 413 for a body past
                arcadedb.server.httpBodyContentMaxSize, 403, 404, 500 (issue #7396).
    """

    commit_index: int | Unset = UNSET
    exception_args: str | Unset = UNSET
    status: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        commit_index = self.commit_index

        exception_args = self.exception_args

        status = self.status

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if commit_index is not UNSET:
            field_dict["commitIndex"] = commit_index
        if exception_args is not UNSET:
            field_dict["exceptionArgs"] = exception_args
        if status is not UNSET:
            field_dict["status"] = status

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        commit_index = d.pop("commitIndex", UNSET)

        exception_args = d.pop("exceptionArgs", UNSET)

        status = d.pop("status", UNSET)

        nd_json_batch_event_error = cls(
            commit_index=commit_index,
            exception_args=exception_args,
            status=status,
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

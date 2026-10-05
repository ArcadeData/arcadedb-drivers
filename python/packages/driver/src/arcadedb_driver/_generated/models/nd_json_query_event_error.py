from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="NdJsonQueryEventError")


@_attrs_define
class NdJsonQueryEventError:
    """A failure raised after the 200 had already been sent. The status code cannot be taken back at that point, so the
    failure is reported in band and no 'stats' line follows.

        Attributes:
            message (str): Why the stream failed
            status (int): HTTP status the buffered encoding would have answered the same failure with, decided by the same
                error mapping: 503 for a retryable conflict, 409 for a duplicated key, 403 for a security refusal, 413 when
                arcadedb.server.httpQueryMaxResultRows cut the result short, 500 for an unexpected failure (issue #8235). Key on
                this rather than on 'message' to decide whether to retry.
            exception (str | Unset): Class name of the reported exception, the value the buffered error body carries in its
                'exception' member.
            exception_args (str | Unset): Structured arguments of the failure, as the buffered error body carries them:
                present only for a failure that has any, e.g. 'index|keys|rid' for a duplicated key.
    """

    message: str
    status: int
    exception: str | Unset = UNSET
    exception_args: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        message = self.message

        status = self.status

        exception = self.exception

        exception_args = self.exception_args

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "message": message,
                "status": status,
            }
        )
        if exception is not UNSET:
            field_dict["exception"] = exception
        if exception_args is not UNSET:
            field_dict["exceptionArgs"] = exception_args

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        message = d.pop("message")

        status = d.pop("status")

        exception = d.pop("exception", UNSET)

        exception_args = d.pop("exceptionArgs", UNSET)

        nd_json_query_event_error = cls(
            message=message,
            status=status,
            exception=exception,
            exception_args=exception_args,
        )

        nd_json_query_event_error.additional_properties = d
        return nd_json_query_event_error

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

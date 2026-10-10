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
            message (str): Why the stream failed. Outside production mode the failure's own message; in production mode the
                classified label also carried in 'error', because the raw text can carry file paths and engine internals the
                buffered error body conceals for the same failure (issue #8899).
            status (int): HTTP status the buffered encoding would have answered the same failure with, decided by the same
                error mapping: 503 for a retryable conflict, 409 for a duplicated key, 403 for a security refusal, 413 when
                arcadedb.server.httpQueryMaxResultRows cut the result short, 500 for an unexpected failure (issue #8235). Key on
                this rather than on 'message' to decide whether to retry.
            detail (str | Unset): Cause chain of the failure, as the buffered error body carries it. Absent in production
                mode.
            error (str | Unset): Classified label of the failure, the value the buffered error body carries in its 'error'
                member.
            exception (str | Unset): Class name of the reported exception, the value the buffered error body carries in its
                'exception' member.
            exception_args (str | Unset): Structured arguments of the failure, as the buffered error body carries them:
                present only for a failure that has any, e.g. 'index|keys|rid' for a duplicated key.
            request_id (str | Unset): Correlation id echoing X-Request-Id, for cross-referencing the failure against the
                server log. Absent when the request carried no correlation id.
            retry_after (int | Unset): Seconds to wait before retrying, the value the buffered encoding sends as a Retry-
                After header for the same failure: present only for a refusal that carries one - 503 when the node cannot
                execute the request yet (e.g. a snapshot install), 409 when an identical request is still in flight. A header
                cannot be added once the stream has started, so the back-off travels in band (issue #8899).
    """

    message: str
    status: int
    detail: str | Unset = UNSET
    error: str | Unset = UNSET
    exception: str | Unset = UNSET
    exception_args: str | Unset = UNSET
    request_id: str | Unset = UNSET
    retry_after: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        message = self.message

        status = self.status

        detail = self.detail

        error = self.error

        exception = self.exception

        exception_args = self.exception_args

        request_id = self.request_id

        retry_after = self.retry_after

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "message": message,
                "status": status,
            }
        )
        if detail is not UNSET:
            field_dict["detail"] = detail
        if error is not UNSET:
            field_dict["error"] = error
        if exception is not UNSET:
            field_dict["exception"] = exception
        if exception_args is not UNSET:
            field_dict["exceptionArgs"] = exception_args
        if request_id is not UNSET:
            field_dict["requestId"] = request_id
        if retry_after is not UNSET:
            field_dict["retryAfter"] = retry_after

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        message = d.pop("message")

        status = d.pop("status")

        detail = d.pop("detail", UNSET)

        error = d.pop("error", UNSET)

        exception = d.pop("exception", UNSET)

        exception_args = d.pop("exceptionArgs", UNSET)

        request_id = d.pop("requestId", UNSET)

        retry_after = d.pop("retryAfter", UNSET)

        nd_json_query_event_error = cls(
            message=message,
            status=status,
            detail=detail,
            error=error,
            exception=exception,
            exception_args=exception_args,
            request_id=request_id,
            retry_after=retry_after,
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

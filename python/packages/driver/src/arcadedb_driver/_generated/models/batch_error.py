from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="BatchError")


@_attrs_define
class BatchError:
    """Failed bulk load. Carries how much of the payload was attempted, because a batch is not atomic and the caller has to
    reconcile before retrying.

        Attributes:
            bytes_read (int): Bytes of the upload the server consumed, so a client can verify its whole file arrived - and,
                on a truncated load, how far the server got. Never more than the client sent.
            edges_created (int): Edges attempted before the failure, with the same upper-bound caveat as 'verticesCreated'.
            error (str): Why the load failed. Carries the offending location, such as a line number or a temporary id,
                because a batch failure echoes client input rather than engine internals.
            lines_read (int): Lines the parser read, so 'linesRead' minus 'linesSkipped' can be checked against the records
                created
            lines_skipped (int): Lines that carried no record: blank lines, plus CSV headers and '---' separators
            partial_commit (bool): True when earlier chunks are durably committed. Retrying the whole payload then
                duplicates the already-committed vertices, because temporary ids are not keys.
            vertices_created (int): Vertices attempted before the failure. An upper bound on what is durable: records
                handled since the last commit boundary were rolled back.
            exception (str | Unset): Exception class name, for distinguishing failure classes programmatically. On the 400
                it is always present; on the 408 it is absent when nothing threw - a body that simply ended before its announced
                length, or a malformed record that turned out to be a cut upload. Key on the status for that distinction, not on
                this member.
            request_id (str | Unset): Correlation id echoing X-Request-Id, for cross-referencing the failure against the
                server log. Absent when the request carried no correlation id.
            vertices_without_id (int | Unset): Vertices created without an '@id' under refMode=id. They are loaded and
                durable, but no edge can reference them. Absent when zero.
    """

    bytes_read: int
    edges_created: int
    error: str
    lines_read: int
    lines_skipped: int
    partial_commit: bool
    vertices_created: int
    exception: str | Unset = UNSET
    request_id: str | Unset = UNSET
    vertices_without_id: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        bytes_read = self.bytes_read

        edges_created = self.edges_created

        error = self.error

        lines_read = self.lines_read

        lines_skipped = self.lines_skipped

        partial_commit = self.partial_commit

        vertices_created = self.vertices_created

        exception = self.exception

        request_id = self.request_id

        vertices_without_id = self.vertices_without_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "bytesRead": bytes_read,
                "edgesCreated": edges_created,
                "error": error,
                "linesRead": lines_read,
                "linesSkipped": lines_skipped,
                "partialCommit": partial_commit,
                "verticesCreated": vertices_created,
            }
        )
        if exception is not UNSET:
            field_dict["exception"] = exception
        if request_id is not UNSET:
            field_dict["requestId"] = request_id
        if vertices_without_id is not UNSET:
            field_dict["verticesWithoutId"] = vertices_without_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        bytes_read = d.pop("bytesRead")

        edges_created = d.pop("edgesCreated")

        error = d.pop("error")

        lines_read = d.pop("linesRead")

        lines_skipped = d.pop("linesSkipped")

        partial_commit = d.pop("partialCommit")

        vertices_created = d.pop("verticesCreated")

        exception = d.pop("exception", UNSET)

        request_id = d.pop("requestId", UNSET)

        vertices_without_id = d.pop("verticesWithoutId", UNSET)

        batch_error = cls(
            bytes_read=bytes_read,
            edges_created=edges_created,
            error=error,
            lines_read=lines_read,
            lines_skipped=lines_skipped,
            partial_commit=partial_commit,
            vertices_created=vertices_created,
            exception=exception,
            request_id=request_id,
            vertices_without_id=vertices_without_id,
        )

        batch_error.additional_properties = d
        return batch_error

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

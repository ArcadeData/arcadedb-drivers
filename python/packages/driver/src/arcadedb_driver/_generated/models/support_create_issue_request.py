from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="SupportCreateIssueRequest")


@_attrs_define
class SupportCreateIssueRequest:
    """A support issue

    Attributes:
        severity (str): S1, S2, S3 or S4
        title (str): 1 to 200 characters
        body (str | Unset): At most 20000 characters
        kind (str | Unset): bug, question, performance or other, optional
        preview_id (str | Unset): Preview whose files are attached, optional
    """

    severity: str
    title: str
    body: str | Unset = UNSET
    kind: str | Unset = UNSET
    preview_id: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        severity = self.severity

        title = self.title

        body = self.body

        kind = self.kind

        preview_id = self.preview_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "severity": severity,
                "title": title,
            }
        )
        if body is not UNSET:
            field_dict["body"] = body
        if kind is not UNSET:
            field_dict["kind"] = kind
        if preview_id is not UNSET:
            field_dict["previewId"] = preview_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        severity = d.pop("severity")

        title = d.pop("title")

        body = d.pop("body", UNSET)

        kind = d.pop("kind", UNSET)

        preview_id = d.pop("previewId", UNSET)

        support_create_issue_request = cls(
            severity=severity,
            title=title,
            body=body,
            kind=kind,
            preview_id=preview_id,
        )

        support_create_issue_request.additional_properties = d
        return support_create_issue_request

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

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.support_comment_request_screenshots import SupportCommentRequestScreenshots


T = TypeVar("T", bound="SupportCommentRequest")


@_attrs_define
class SupportCommentRequest:
    """A reply

    Attributes:
        body (str): At most 20000 characters
        screenshots (SupportCommentRequestScreenshots | Unset): Ids of held screenshots (at most 5) the reply shows:
            they are attached to the issue first
    """

    body: str
    screenshots: SupportCommentRequestScreenshots | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        body = self.body

        screenshots: dict[str, Any] | Unset = UNSET
        if not isinstance(self.screenshots, Unset):
            screenshots = self.screenshots.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "body": body,
            }
        )
        if screenshots is not UNSET:
            field_dict["screenshots"] = screenshots

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.support_comment_request_screenshots import SupportCommentRequestScreenshots

        d = dict(src_dict)
        body = d.pop("body")

        _screenshots = d.pop("screenshots", UNSET)
        screenshots: SupportCommentRequestScreenshots | Unset
        if isinstance(_screenshots, Unset):
            screenshots = UNSET
        else:
            screenshots = SupportCommentRequestScreenshots.from_dict(_screenshots)

        support_comment_request = cls(
            body=body,
            screenshots=screenshots,
        )

        support_comment_request.additional_properties = d
        return support_comment_request

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

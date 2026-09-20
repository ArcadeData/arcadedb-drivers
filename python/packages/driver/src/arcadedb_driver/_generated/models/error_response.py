from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ErrorResponse")


@_attrs_define
class ErrorResponse:
    """Error response object

    Attributes:
        error (str): Error message. The one member every error body carries
        detail (str | Unset): Error details, including the cause chain when there is one. Absent when there is nothing
            to add
        exception (str | Unset): Exception class name, for distinguishing failure classes programmatically. Absent when
            the failure was raised as a plain message rather than from an exception
        exception_args (str | Unset): Exception arguments, when the exception class carries any
        help_ (str | Unset): What to do about it, when the server can say
    """

    error: str
    detail: str | Unset = UNSET
    exception: str | Unset = UNSET
    exception_args: str | Unset = UNSET
    help_: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        error = self.error

        detail = self.detail

        exception = self.exception

        exception_args = self.exception_args

        help_ = self.help_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "error": error,
            }
        )
        if detail is not UNSET:
            field_dict["detail"] = detail
        if exception is not UNSET:
            field_dict["exception"] = exception
        if exception_args is not UNSET:
            field_dict["exceptionArgs"] = exception_args
        if help_ is not UNSET:
            field_dict["help"] = help_

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        error = d.pop("error")

        detail = d.pop("detail", UNSET)

        exception = d.pop("exception", UNSET)

        exception_args = d.pop("exceptionArgs", UNSET)

        help_ = d.pop("help", UNSET)

        error_response = cls(
            error=error,
            detail=detail,
            exception=exception,
            exception_args=exception_args,
            help_=help_,
        )

        error_response.additional_properties = d
        return error_response

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

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.support_preview_request_window import SupportPreviewRequestWindow


T = TypeVar("T", bound="SupportPreviewRequest")


@_attrs_define
class SupportPreviewRequest:
    """What to put in the bundle

    Attributes:
        include_diagnostics (bool | Unset): Include diagnostics.json (default true)
        include_logs (bool | Unset): Include the logs of the window (default false)
        include_threads (bool | Unset): Include a thread dump, threads.txt (default false)
        window (SupportPreviewRequestWindow | Unset): {preset: 10m|30m|1h|12h|24h|1w} or {from, to} in ISO-8601. A value
            without an offset is read in the time zone of the log
    """

    include_diagnostics: bool | Unset = UNSET
    include_logs: bool | Unset = UNSET
    include_threads: bool | Unset = UNSET
    window: SupportPreviewRequestWindow | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        include_diagnostics = self.include_diagnostics

        include_logs = self.include_logs

        include_threads = self.include_threads

        window: dict[str, Any] | Unset = UNSET
        if not isinstance(self.window, Unset):
            window = self.window.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if include_diagnostics is not UNSET:
            field_dict["includeDiagnostics"] = include_diagnostics
        if include_logs is not UNSET:
            field_dict["includeLogs"] = include_logs
        if include_threads is not UNSET:
            field_dict["includeThreads"] = include_threads
        if window is not UNSET:
            field_dict["window"] = window

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.support_preview_request_window import SupportPreviewRequestWindow

        d = dict(src_dict)
        include_diagnostics = d.pop("includeDiagnostics", UNSET)

        include_logs = d.pop("includeLogs", UNSET)

        include_threads = d.pop("includeThreads", UNSET)

        _window = d.pop("window", UNSET)
        window: SupportPreviewRequestWindow | Unset
        if isinstance(_window, Unset):
            window = UNSET
        else:
            window = SupportPreviewRequestWindow.from_dict(_window)

        support_preview_request = cls(
            include_diagnostics=include_diagnostics,
            include_logs=include_logs,
            include_threads=include_threads,
            window=window,
        )

        support_preview_request.additional_properties = d
        return support_preview_request

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

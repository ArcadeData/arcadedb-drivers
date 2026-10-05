from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.support_preview_files_item import SupportPreviewFilesItem
    from ..models.support_preview_log_time_zone import SupportPreviewLogTimeZone
    from ..models.support_preview_window import SupportPreviewWindow


T = TypeVar("T", bound="SupportPreview")


@_attrs_define
class SupportPreview:
    """The redacted files, ready to send or download

    Attributes:
        files (list[SupportPreviewFilesItem]): One entry per file
        preview_id (str): Identifier of the preview, valid 15 minutes
        warnings (list[str]): Warnings, e.g. an empty window
        expires_at (str | Unset): When the preview is deleted
        github_summary (str | Unset): Markdown of the environment and log summary for a public GitHub issue, without
            logs
        log_time_zone (SupportPreviewLogTimeZone | Unset): {id, name, offset, note}
        window (SupportPreviewWindow | Unset): {from, to} as instants, when logs were requested
    """

    files: list[SupportPreviewFilesItem]
    preview_id: str
    warnings: list[str]
    expires_at: str | Unset = UNSET
    github_summary: str | Unset = UNSET
    log_time_zone: SupportPreviewLogTimeZone | Unset = UNSET
    window: SupportPreviewWindow | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        files = []
        for files_item_data in self.files:
            files_item = files_item_data.to_dict()
            files.append(files_item)

        preview_id = self.preview_id

        warnings = self.warnings

        expires_at = self.expires_at

        github_summary = self.github_summary

        log_time_zone: dict[str, Any] | Unset = UNSET
        if not isinstance(self.log_time_zone, Unset):
            log_time_zone = self.log_time_zone.to_dict()

        window: dict[str, Any] | Unset = UNSET
        if not isinstance(self.window, Unset):
            window = self.window.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "files": files,
                "previewId": preview_id,
                "warnings": warnings,
            }
        )
        if expires_at is not UNSET:
            field_dict["expiresAt"] = expires_at
        if github_summary is not UNSET:
            field_dict["githubSummary"] = github_summary
        if log_time_zone is not UNSET:
            field_dict["logTimeZone"] = log_time_zone
        if window is not UNSET:
            field_dict["window"] = window

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.support_preview_files_item import SupportPreviewFilesItem
        from ..models.support_preview_log_time_zone import SupportPreviewLogTimeZone
        from ..models.support_preview_window import SupportPreviewWindow

        d = dict(src_dict)
        files = []
        _files = d.pop("files")
        for files_item_data in _files:
            files_item = SupportPreviewFilesItem.from_dict(files_item_data)

            files.append(files_item)

        preview_id = d.pop("previewId")

        warnings = cast(list[str], d.pop("warnings"))

        expires_at = d.pop("expiresAt", UNSET)

        github_summary = d.pop("githubSummary", UNSET)

        _log_time_zone = d.pop("logTimeZone", UNSET)
        log_time_zone: SupportPreviewLogTimeZone | Unset
        if isinstance(_log_time_zone, Unset):
            log_time_zone = UNSET
        else:
            log_time_zone = SupportPreviewLogTimeZone.from_dict(_log_time_zone)

        _window = d.pop("window", UNSET)
        window: SupportPreviewWindow | Unset
        if isinstance(_window, Unset):
            window = UNSET
        else:
            window = SupportPreviewWindow.from_dict(_window)

        support_preview = cls(
            files=files,
            preview_id=preview_id,
            warnings=warnings,
            expires_at=expires_at,
            github_summary=github_summary,
            log_time_zone=log_time_zone,
            window=window,
        )

        support_preview.additional_properties = d
        return support_preview

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

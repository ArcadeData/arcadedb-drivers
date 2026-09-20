from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.grafana_query_response_results_additional_property_frames_item import (
        GrafanaQueryResponseResultsAdditionalPropertyFramesItem,
    )


T = TypeVar("T", bound="GrafanaQueryResponseResultsAdditionalProperty")


@_attrs_define
class GrafanaQueryResponseResultsAdditionalProperty:
    """Result for one target. Carries 'error' instead of frames when the target could not be resolved.

    Attributes:
        frames (list[GrafanaQueryResponseResultsAdditionalPropertyFramesItem]): Frames produced by the target
        error (str | Unset): Why the target could not be resolved. Present only when it failed; 'frames' is then empty.
    """

    frames: list[GrafanaQueryResponseResultsAdditionalPropertyFramesItem]
    error: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        frames = []
        for frames_item_data in self.frames:
            frames_item = frames_item_data.to_dict()
            frames.append(frames_item)

        error = self.error

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "frames": frames,
            }
        )
        if error is not UNSET:
            field_dict["error"] = error

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.grafana_query_response_results_additional_property_frames_item import (
            GrafanaQueryResponseResultsAdditionalPropertyFramesItem,
        )

        d = dict(src_dict)
        frames = []
        _frames = d.pop("frames")
        for frames_item_data in _frames:
            frames_item = GrafanaQueryResponseResultsAdditionalPropertyFramesItem.from_dict(frames_item_data)

            frames.append(frames_item)

        error = d.pop("error", UNSET)

        grafana_query_response_results_additional_property = cls(
            frames=frames,
            error=error,
        )

        grafana_query_response_results_additional_property.additional_properties = d
        return grafana_query_response_results_additional_property

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

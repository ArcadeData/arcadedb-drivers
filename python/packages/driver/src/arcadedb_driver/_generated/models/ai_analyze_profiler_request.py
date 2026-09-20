from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.ai_analyze_profiler_request_profiler_data import AiAnalyzeProfilerRequestProfilerData


T = TypeVar("T", bound="AiAnalyzeProfilerRequest")


@_attrs_define
class AiAnalyzeProfilerRequest:
    """Profiler analysis request

    Attributes:
        profiler_data (AiAnalyzeProfilerRequestProfilerData): Profiler snapshot to analyse. An open map: the server
            forwards it to the assistant as it stands and derives the schema of every database named inside it, rather than
            reading a fixed set of keys out of it - so the shape follows whatever the profiler produced.
    """

    profiler_data: AiAnalyzeProfilerRequestProfilerData
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        profiler_data = self.profiler_data.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "profilerData": profiler_data,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.ai_analyze_profiler_request_profiler_data import AiAnalyzeProfilerRequestProfilerData

        d = dict(src_dict)
        profiler_data = AiAnalyzeProfilerRequestProfilerData.from_dict(d.pop("profilerData"))

        ai_analyze_profiler_request = cls(
            profiler_data=profiler_data,
        )

        ai_analyze_profiler_request.additional_properties = d
        return ai_analyze_profiler_request

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

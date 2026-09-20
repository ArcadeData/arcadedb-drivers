from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.ai_tool_call_args import AiToolCallArgs


T = TypeVar("T", bound="AiToolCall")


@_attrs_define
class AiToolCall:
    """One tool invocation, reported after the fact. The same pair of members the stream's 'tool_start' carries

    Attributes:
        tool (str): Name of the tool that was run
        args (AiToolCallArgs | Unset): Arguments it was run with, keyed by the tool's own parameter names
        error (str | Unset): Why it failed. Absent on a run that succeeded
    """

    tool: str
    args: AiToolCallArgs | Unset = UNSET
    error: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tool = self.tool

        args: dict[str, Any] | Unset = UNSET
        if not isinstance(self.args, Unset):
            args = self.args.to_dict()

        error = self.error

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tool": tool,
            }
        )
        if args is not UNSET:
            field_dict["args"] = args
        if error is not UNSET:
            field_dict["error"] = error

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.ai_tool_call_args import AiToolCallArgs

        d = dict(src_dict)
        tool = d.pop("tool")

        _args = d.pop("args", UNSET)
        args: AiToolCallArgs | Unset
        if isinstance(_args, Unset):
            args = UNSET
        else:
            args = AiToolCallArgs.from_dict(_args)

        error = d.pop("error", UNSET)

        ai_tool_call = cls(
            tool=tool,
            args=args,
            error=error,
        )

        ai_tool_call.additional_properties = d
        return ai_tool_call

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
